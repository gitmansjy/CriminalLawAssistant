import requests
from bs4 import BeautifulSoup
import re
from pathlib import Path
import time
import random
from urllib.parse import urljoin, urlparse
import json

class JudicialInterpretationSpider:
    """最高人民法院公报司法解释爬虫"""
    
    def __init__(self, base_url, output_dir="D:/py/CriminalLawAssistant/books"):
        self.base_url = base_url
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 设置请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,en-US;q=0.5,en;q=0.3',
            'Connection': 'keep-alive',
            'Referer': 'http://gongbao.court.gov.cn/',
        }
        
        # 存储所有司法解释的元数据
        self.interpretations = []
        
        # 创建子目录
        self.txt_dir = self.output_dir / "司法解释全文"
        self.txt_dir.mkdir(exist_ok=True)
    
    def get_page_content(self, url, retry=3):
        """获取页面内容，支持重试"""
        for i in range(retry):
            try:
                # 随机延时，避免被封
                time.sleep(random.uniform(1, 3))
                
                response = requests.get(url, headers=self.headers, timeout=15)
                response.encoding = 'utf-8'
                
                if response.status_code == 200:
                    return response.text
                else:
                    print(f"⚠️ 请求失败，状态码: {response.status_code}，重试 {i+1}/{retry}")
            except Exception as e:
                print(f"⚠️ 请求异常: {e}，重试 {i+1}/{retry}")
                time.sleep(2)
        
        return None
    
    def parse_list_page(self, html, base_url):
        """
        解析列表页，提取司法解释条目和链接
        
        根据你提供的列表页HTML结构，司法解释条目都在<ul>列表中
        """
        soup = BeautifulSoup(html, 'html.parser')
        items = []
        
        # 方法1：查找所有可能包含司法解释的链接
        # 公报官网的列表页中，司法解释通常是在<ul>中的<li>里的<a>标签
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            link_text = link.get_text().strip()
            href = link['href']
            
            # 过滤条件：
            # 1. 链接文本包含"最高人民法院"（司法解释的特征）
            # 2. 链接指向详情页（通常包含"/Details/"）
            if ('最高人民法院' in link_text or '最高人民检察院' in link_text) and '/Details/' in href:
                link_text = re.sub(r'\s+', ' ', link_text)
                
                # 提取年份和期号
                year_match = re.search(r'(\d{4})年', link_text)
                issue_match = re.search(r'(\d+)期', link_text)
                
                # 获取完整URL
                full_url = urljoin(base_url, href)
                
                item = {
                    'title': link_text,
                    'year': year_match.group(1) if year_match else '未知',
                    'issue': issue_match.group(1) if issue_match else '未知',
                    'url': full_url
                }
                
                items.append(item)
                print(f"  发现司法解释: {link_text[:50]}... -> {full_url}")
        
        return items
    
    def get_next_page_url(self, soup, current_url):
        """
        获取下一页URL
        
        根据公报官网的翻页机制，通常有"下一页"链接或分页参数
        """
        # 方法1：找包含"下一页"文本的链接
        next_link = soup.find('a', string=re.compile(r'下一页|下页|>'))
        if next_link and next_link.get('href'):
            next_url = urljoin(current_url, next_link['href'])
            return next_url
        
        # 方法2：找分页区域中的链接
        pagination = soup.find('div', class_=re.compile(r'page|pagination|分页'))
        if pagination:
            links = pagination.find_all('a', href=True)
            for link in links:
                if '下一页' in link.get_text() or '下页' in link.get_text():
                    return urljoin(current_url, link['href'])
        
        # 方法3：手动构造分页URL（如果网站使用page参数）
        # 例如：http://gongbao.court.gov.cn/ArticleList.html?serial_no=sfjs&page=2
        parsed = urlparse(current_url)
        if 'page=' not in current_url:
            # 第一页，尝试加page=2
            if '?' in current_url:
                return current_url + '&page=2'
            else:
                return current_url + '?page=2'
        else:
            # 已有page参数，递增
            import urllib.parse
            query_dict = dict(urllib.parse.parse_qsl(parsed.query))
            current_page = int(query_dict.get('page', '1'))
            next_page = current_page + 1
            query_dict['page'] = str(next_page)
            new_query = urllib.parse.urlencode(query_dict)
            return parsed._replace(query=new_query).geturl()
        
        return None
    
    def crawl_list_pages(self, max_pages=20):
        """爬取所有列表页"""
        current_url = self.base_url
        page_num = 1
        all_items = []
        
        print(f"开始爬取列表页...")
        print(f"初始URL: {current_url}")
        
        while current_url and page_num <= max_pages:
            print(f"\n📄 正在爬取第 {page_num} 页: {current_url}")
            
            html = self.get_page_content(current_url)
            if not html:
                print(f"❌ 第 {page_num} 页获取失败")
                break
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # 解析当前页的司法解释
            items = self.parse_list_page(html, current_url)
            print(f"✅ 第 {page_num} 页找到 {len(items)} 条司法解释")
            
            # 添加到总列表
            all_items.extend(items)
            
            # 获取下一页URL
            next_url = self.get_next_page_url(soup, current_url)
            if next_url and next_url != current_url:
                current_url = next_url
                page_num += 1
            else:
                print("没有更多页了")
                break
        
        # 最终去重（基于标题和URL）
        seen_urls = set()
        for item in all_items:
            if item['url'] not in seen_urls:
                seen_urls.add(item['url'])
                self.interpretations.append(item)
        
        print(f"\n📊 共找到 {len(self.interpretations)} 条唯一司法解释")
    
    def parse_detail_page(self, html, item):
        """
        解析详情页，提取司法解释全文
        
        根据你提供的详情页示例，结构如下：
        - 标题在 <title> 或 <h1>
        - 正文在 <div> 或 <p> 中
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # 移除脚本和样式
        for script in soup(["script", "style"]):
            script.decompose()
        
        # 提取标题
        title = None
        # 尝试从h1获取
        h1 = soup.find('h1')
        if h1:
            title = h1.get_text().strip()
        else:
            # 从title标签获取
            title_tag = soup.find('title')
            if title_tag:
                title = title_tag.get_text().strip()
        
        # 提取正文内容
        content_parts = []
        
        # 方法1：查找所有段落
        paragraphs = soup.find_all('p')
        for p in paragraphs:
            p_text = p.get_text().strip()
            # 过滤掉太短的、可能不是正文的段落
            if len(p_text) > 20 and not any(keyword in p_text for keyword in ['主办', '主管', '总编辑', '副总编辑']):
                content_parts.append(p_text)
        
        # 方法2：如果没有找到足够段落，尝试获取整个body
        if len(content_parts) < 3:
            body = soup.find('body')
            if body:
                # 移除明显是页眉页脚的部分
                for div in body.find_all('div', class_=re.compile(r'header|footer|nav|menu')):
                    div.decompose()
                body_text = body.get_text()
                # 按行分割并过滤
                lines = body_text.split('\n')
                for line in lines:
                    line = line.strip()
                    if len(line) > 30 and not any(keyword in line for keyword in ['主办', '主管', '总编辑']):
                        content_parts.append(line)
        
        # 格式化内容
        if content_parts:
            # 合并内容
            full_content = '\n\n'.join(content_parts)
            
            # 清理多余空白
            full_content = re.sub(r'\n{3,}', '\n\n', full_content)
            
            return full_content, title
        else:
            return None, title
    
    def download_detail_content(self):
        """下载所有司法解释的详情内容"""
        print(f"\n📥 开始下载司法解释全文，共 {len(self.interpretations)} 条...")
        
        success_count = 0
        for i, item in enumerate(self.interpretations, 1):
            print(f"\n[{i}/{len(self.interpretations)}] 处理: {item['title']}")
            
            # 生成文件名（移除非法字符）
            safe_title = re.sub(r'[\\/*?:"<>|]', '', item['title'])
            # 限制文件名长度
            if len(safe_title) > 50:
                safe_title = safe_title[:50]
            filename = f"{item['year']}_{safe_title}.txt"
            filepath = self.txt_dir / filename
            
            # 如果文件已存在，跳过
            if filepath.exists():
                print(f"⏭️ 文件已存在，跳过: {filename}")
                success_count += 1
                continue
            
            # 如果没有详情页URL，记录并跳过
            if not item['url']:
                print(f"⚠️ 没有详情页URL，跳过")
                continue
            
            print(f"  正在获取: {item['url']}")
            
            # 获取详情页
            html = self.get_page_content(item['url'])
            if not html:
                print(f"❌ 详情页获取失败")
                continue
            
            # 解析内容
            content, extracted_title = self.parse_detail_page(html, item)
            if content:
                # 保存到文件
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"标题：{item['title']}\n")
                    if extracted_title and extracted_title != item['title']:
                        f.write(f"页面标题：{extracted_title}\n")
                    f.write(f"年份：{item['year']}年\n")
                    f.write(f"期号：{item['issue']}期\n")
                    f.write(f"来源：{item['url']}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(content)
                
                print(f"✅ 已保存: {filename}")
                success_count += 1
            else:
                print(f"❌ 内容解析失败")
                # 保存HTML以便调试
                debug_file = self.txt_dir / f"debug_{filename}.html"
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"📝 已保存HTML供调试: {debug_file}")
            
            # 随机延时，避免被封
            time.sleep(random.uniform(2, 5))
        
        return success_count
    
    def save_metadata(self):
        """保存司法解释元数据"""
        # 保存为JSON
        json_path = self.output_dir / "司法解释_元数据.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump({
                'total': len(self.interpretations),
                'items': self.interpretations
            }, f, ensure_ascii=False, indent=2)
        print(f"✅ 元数据已保存: {json_path}")
        
        # 保存为TXT列表
        txt_path = self.output_dir / "司法解释_完整列表.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"最高人民法院公报司法解释列表\n")
            f.write(f"总数：{len(self.interpretations)}条\n")
            f.write(f"抓取时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            # 按年份分组
            by_year = {}
            for item in self.interpretations:
                year = item['year']
                if year not in by_year:
                    by_year[year] = []
                by_year[year].append(item)
            
            # 按年份倒序输出
            for year in sorted(by_year.keys(), reverse=True):
                f.write(f"\n【{year}年】共{len(by_year[year])}条\n")
                f.write("-" * 40 + "\n")
                for i, item in enumerate(by_year[year], 1):
                    f.write(f"{i:3d}. {item['title']}\n")
                    f.write(f"     链接：{item['url']}\n")
        
        print(f"✅ 列表已保存: {txt_path}")
    
    def run(self, max_pages=20, download_content=True):
        """运行爬虫"""
        print("=" * 60)
        print("最高人民法院公报司法解释爬虫")
        print("=" * 60)
        print(f"输出目录：{self.output_dir}")
        print("=" * 60)
        
        # 步骤1：爬取列表页
        self.crawl_list_pages(max_pages)
        
        # 步骤2：保存元数据
        self.save_metadata()
        
        # 步骤3：下载详情内容
        if download_content:
            success = self.download_detail_content()
            print(f"\n✅ 成功下载 {success}/{len(self.interpretations)} 条司法解释全文")
        
        print("\n" + "=" * 60)
        print("爬取完成！")
        print("=" * 60)
        print(f"📁 文件保存位置：{self.output_dir}")
        print(f"   - 司法解释_完整列表.txt：所有司法解释列表（含链接）")
        print(f"   - 司法解释_元数据.json：元数据")
        print(f"   - 司法解释全文/：存放所有司法解释的全文")

if __name__ == "__main__":
    # 目标网址（列表页）
    url = "http://gongbao.court.gov.cn/ArticleList.html?serial_no=sfjs"
    
    # 创建爬虫实例
    spider = JudicialInterpretationSpider(
        base_url=url,
        output_dir="D:/py/CriminalLawAssistant/books"
    )
    
    # 运行爬虫
    # max_pages: 最大爬取页数（公报官网可能有几十页）
    # download_content: 是否下载详情内容
    spider.run(max_pages=30, download_content=True)