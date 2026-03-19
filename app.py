import streamlit as st
import os
from pathlib import Path
from typing import Any, List, Mapping, Optional
import hashlib
import warnings
import re
import time

# 设置 Hugging Face 镜像（解决下载问题）
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
os.environ['HF_HUB_TIMEOUT'] = '120'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

# LangChain 基础导入
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.language_models.llms import LLM

# 文档加载器
from langchain_community.document_loaders import (
    TextLoader, 
    PyPDFLoader, 
    Docx2txtLoader,
    UnstructuredExcelLoader,
    CSVLoader
)

# Embedding 和向量存储
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# 阿里云通义千问
import dashscope
from dashscope import Generation

# 忽略警告
warnings.filterwarnings('ignore')

# ==================== 配置区域 ====================
# 在这里设置你的API Key
DASHSCOPE_API_KEY = "sk-c5f85b787a954210a04b8fe8f9481ee2"  # 替换为你的API Key
os.environ['DASHSCOPE_API_KEY'] = DASHSCOPE_API_KEY
dashscope.api_key = DASHSCOPE_API_KEY

# 支持的文件格式
SUPPORTED_EXTENSIONS = {
    '.txt': TextLoader,
    '.pdf': PyPDFLoader,
    '.docx': Docx2txtLoader,
    '.doc': Docx2txtLoader,
    '.xlsx': UnstructuredExcelLoader,
    '.xls': UnstructuredExcelLoader,
    '.csv': CSVLoader,
}

# 需要过滤的版权声明关键词
COPYRIGHT_KEYWORDS = [
    "爱上阅读", "www.isyd.net", "isyd.net",
    "声明：本书来自互联网",
    "敬告：请在下载后的24小时内删除",
    "书名：", "作者：",
    "章节数：", "字数：",
    "========简介========",
    "本书由", "搜集整理",
    "版权归作者所有",
    "仅供参考", "查阅资料"
]

# ==================== 自定义LLM类 ====================
class DashScopeLLM(LLM):
    """自定义 DashScope LLM 包装器"""
    
    model: str = "qwen-plus"
    temperature: float = 0.2
    api_key: str = DASHSCOPE_API_KEY
    
    @property
    def _llm_type(self) -> str:
        return "dashscope"
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None, **kwargs) -> str:
        """调用 DashScope API"""
        try:
            response = Generation.call(
                model=self.model,
                prompt=prompt,
                temperature=self.temperature,
                api_key=self.api_key
            )
            
            if response.status_code == 200:
                return response.output.text
            else:
                return f"API调用失败: {response.message}"
        except Exception as e:
            return f"错误: {str(e)}"
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model": self.model, "temperature": self.temperature}


# ==================== 文档清理函数 ====================
def clean_document_content(content: str, filename: str = "") -> str:
    """
    清理文档内容，移除版权声明等无关信息
    """
    original_length = len(content)
    
    if len(content) < 500:
        return content
    
    # 按行分割
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        # 跳过空行和版权声明
        if not line:
            continue
        if any(keyword in line for keyword in COPYRIGHT_KEYWORDS):
            continue
        # 跳过太短的行（可能是页码或目录）
        if len(line) < 5:
            continue
        cleaned_lines.append(line)
    
    cleaned = '\n'.join(cleaned_lines)
    print(f"  清理前: {original_length} 字符, 清理后: {len(cleaned)} 字符")
    
    return cleaned


# ==================== 文档加载函数 ====================
def load_documents_from_folder(folder_path):
    """
    从文件夹加载所有支持的文档（支持递归子文件夹）
    """
    folder = Path(folder_path)
    if not folder.exists():
        return [], [], {"error": "文件夹不存在"}
    
    all_documents = []
    failed_files = []
    file_stats = {
        'total_files': 0,
        'supported_files': 0,
        'unsupported_files': 0,
        'by_category': {},
        'file_details': []
    }
    
    print(f"\n📂 扫描文件夹: {folder_path}")
    
    # 递归遍历所有子文件夹
    for file_path in folder.rglob('*'):
        if file_path.is_file():
            file_stats['total_files'] += 1
            file_extension = file_path.suffix.lower()
            
            print(f"发现文件: {file_path.name} (类型: {file_extension})")
            
            if file_extension in SUPPORTED_EXTENSIONS:
                file_stats['supported_files'] += 1
                
                try:
                    documents = []
                    
                    # 自动判断文件类别
                    category = '其他'
                    file_name_lower = file_path.name.lower()
                    file_path_str = str(file_path).lower()
                    
                    if '刑法' in file_name_lower or '刑法' in file_path_str:
                        category = '刑法'
                    elif '刑事诉讼法' in file_name_lower or '刑诉' in file_name_lower:
                        category = '刑事诉讼法'
                    elif '司法解释' in file_path_str or '解释' in file_name_lower:
                        category = '司法解释'
                    
                    # 对不同格式使用不同编码
                    if file_extension == '.txt':
                        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']
                        loaded = False
                        
                        for encoding in encodings:
                            try:
                                loader = SUPPORTED_EXTENSIONS[file_extension](str(file_path), encoding=encoding)
                                documents = loader.load()
                                loaded = True
                                print(f"  ✅ 使用 {encoding} 编码加载成功")
                                break
                            except Exception as e:
                                print(f"  ⚠️  {encoding} 编码失败: {e}")
                                continue
                        
                        if not loaded:
                            print(f"  ❌ 所有编码都失败，无法加载文件")
                            failed_files.append(f"{file_path.name}: 编码问题")
                            continue
                    else:
                        # 非TXT文件
                        loader = SUPPORTED_EXTENSIONS[file_extension](str(file_path))
                        documents = loader.load()
                        print(f"  ✅ 加载成功")
                    
                    if documents and len(documents) > 0:
                        # 清理文档内容
                        original_content = documents[0].page_content
                        cleaned_content = clean_document_content(original_content, file_path.name)
                        
                        # 更新文档内容
                        documents[0].page_content = cleaned_content
                        
                        # 记录文件详情
                        file_stats['file_details'].append({
                            'name': file_path.name,
                            'category': category,
                            'size': len(cleaned_content),
                            'preview': cleaned_content[:100]
                        })
                        
                        # 按类别统计
                        file_stats['by_category'][category] = file_stats['by_category'].get(category, 0) + 1
                        
                        # 给文档添加元数据
                        for doc in documents:
                            doc.metadata['source'] = str(file_path)
                            doc.metadata['file_name'] = file_path.name
                            doc.metadata['file_type'] = file_extension
                            doc.metadata['file_path'] = str(file_path.relative_to(folder))
                            doc.metadata['category'] = category
                            doc.metadata['cleaned'] = True
                        
                        all_documents.extend(documents)
                    else:
                        print(f"  ⚠️  文档内容为空")
                        failed_files.append(f"{file_path.name}: 内容为空")
                    
                except Exception as e:
                    print(f"  ❌ 加载失败: {e}")
                    failed_files.append(f"{file_path.name}: {str(e)}")
            else:
                file_stats['unsupported_files'] += 1
                print(f"  ⚠️  不支持的格式")
    
    print(f"\n📊 加载统计:")
    print(f"  总文件数: {file_stats['total_files']}")
    print(f"  成功加载: {file_stats['supported_files']}")
    print(f"  文档片段数: {len(all_documents)}")
    print(f"  分类统计: {file_stats['by_category']}")
    
    return all_documents, failed_files, file_stats


# ==================== 检索增强函数 ====================
def filter_copyright_docs(docs):
    """过滤掉包含版权声明的文档"""
    filtered = []
    for doc in docs:
        content = doc.page_content
        if any(keyword in content for keyword in COPYRIGHT_KEYWORDS):
            continue
        if len(content) < 50:
            continue
        filtered.append(doc)
    return filtered


def rewrite_question_with_llm(question):
    """
    使用大模型理解并改写问题，使其更适合在法律文本中检索
    """
    prompt = f"""你是一个专业的法律问题改写助手，专门为刑法知识问答系统服务。
请将用户的问题改写成更适合在法律文本中检索的形式。

用户问题：{question}

改写要求：
1. 提取核心法律概念（如罪名、刑期、情节等）
2. 如果是问量刑，要加上"刑罚"、"量刑"、"判刑"等词
3. 如果是问构成要件，要加上"构成"、"要件"、"标准"等词
4. 如果是问具体罪名，要加上该罪名的全称
5. 输出格式：只输出改写后的查询语句，不要任何解释

改写结果："""
    
    try:
        response = Generation.call(
            model="qwen-plus",
            prompt=prompt,
            temperature=0.1,
            api_key=DASHSCOPE_API_KEY
        )
        
        if response.status_code == 200:
            rewritten = response.output.text.strip()
            if rewritten:
                return rewritten
    except Exception as e:
        print(f"问题改写失败: {e}")
    
    return question


def rerank_docs_by_question(question: str, docs: List) -> List:
    """
    根据问题对文档进行重排序，优先法律条文和司法解释
    """
    if not docs:
        return docs
    
    # 提取问题关键词
    words = re.findall(r'[\u4e00-\u9fff]+', question)
    keywords = [w for w in words if len(w) > 1]
    
    # 判断问题类型
    is_sentence_question = any(kw in question for kw in ["判刑", "量刑", "刑罚", "怎么判", "处罚"])
    is_crime_question = any(kw in question for kw in ["罪", "罪名", "构成"])
    
    scored_docs = []
    for doc in docs:
        content = doc.page_content
        metadata = doc.metadata
        score = 0
        
        # 1. 根据文档类型加分
        category = metadata.get('category', '')
        if category == '刑法':
            score += 20
        elif category == '司法解释':
            score += 15
        elif category == '刑事诉讼法':
            score += 10
        
        # 2. 基础关键词匹配
        for keyword in keywords:
            count = content.count(keyword)
            score += count * 2
        
        # 3. 如果是量刑问题，给包含刑罚相关词的文档加分
        if is_sentence_question:
            sentence_words = ["处", "有期徒刑", "无期徒刑", "死刑", "拘役", "管制", "罚金"]
            for word in sentence_words:
                if word in content:
                    score += 5
        
        # 4. 如果是罪名问题，给包含"罪"的文档加分
        if is_crime_question:
            if "罪" in content:
                score += 5
        
        # 5. 包含具体法条编号的加分
        if re.search(r'第[一二三四五六七八九十百千]+条', content):
            score += 8
        
        # 6. 包含司法解释关键词的加分
        if "解释" in content or "规定" in content:
            score += 3
        
        scored_docs.append((score, doc))
    
    # 按分数排序
    scored_docs.sort(key=lambda x: x[0], reverse=True)
    return [doc for score, doc in scored_docs[:5]]


# ==================== 知识库加载函数 ====================
@st.cache_resource(show_spinner=False)
def load_knowledge_base(folder_path):
    """
    从文件夹加载知识库（带缓存）
    """
    try:
        progress_bar = st.progress(0, text="开始加载知识库...")
        
        # 步骤1: 加载所有文档
        progress_bar.progress(10, text="正在扫描文件夹并加载文档...")
        documents, failed_files, file_stats = load_documents_from_folder(folder_path)
        
        if not documents:
            st.error("没有找到可用的文档！")
            progress_bar.empty()
            return None, None, file_stats
        
        # 步骤2: 分割文档
        progress_bar.progress(30, text=f"正在分割文档 (共{len(documents)}个文档片段)...")
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
        )
        docs = text_splitter.split_documents(documents)
        
        # 过滤分割后的片段
        docs = [doc for doc in docs if len(doc.page_content) > 50 and 
                not any(kw in doc.page_content for kw in COPYRIGHT_KEYWORDS)]
        
        # 步骤3: 创建向量存储
        progress_bar.progress(60, text=f"正在创建向量数据库 ({len(docs)}个文本块)...")
        try:
            print("正在加载 embeddings 模型...")
            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},
                encode_kwargs={'normalize_embeddings': True}
            )
            print("✅ embeddings 加载成功")
        except Exception as e:
            print(f"❌ embeddings 加载失败: {e}")
            st.error(f"无法加载 embeddings 模型: {e}")
            st.info("请检查网络连接或手动下载模型")
            return None, None, file_stats
        
        folder_hash = hashlib.md5(folder_path.encode()).hexdigest()[:8]
        persist_dir = f"./chroma_db_{folder_hash}"
        
        if os.path.exists(persist_dir) and os.listdir(persist_dir):
            vectorstore = Chroma(
                persist_directory=persist_dir, 
                embedding_function=embeddings
            )
            st.sidebar.info("📦 使用缓存的向量数据库")
        else:
            vectorstore = Chroma.from_documents(
                docs, 
                embeddings,
                persist_directory=persist_dir
            )
            st.sidebar.info("🆕 创建新的向量数据库")
        
        # 获取检索参数（从session_state）
        top_k = st.session_state.get('top_k', 6)
        
        # ===== 创建纯向量检索器（完全移除混合搜索）=====
        progress_bar.progress(70, text="正在创建检索器...")
        print(f"📊 创建向量检索器，检索数量: {top_k}")
        
        retriever = vectorstore.as_retriever(
            search_type="mmr",
            search_kwargs={
                "k": top_k,
                "fetch_k": top_k * 3,
                "lambda_mult": 0.6
            }
        )
        
        # 步骤5: 创建LLM
        progress_bar.progress(80, text="正在初始化问答模型...")
        llm = DashScopeLLM()
        
        # 创建提示模板
        prompt = ChatPromptTemplate.from_template(
            """你是一个专业的刑法知识助手，专注于回答关于中国刑法及相关法律法规的问题。

基于以下从法律法规中检索到的内容回答问题：

{context}

问题：{question}

回答要求：
1. 严格基于提供的法律条文回答，不得自行编造
2. 回答时必须引用具体法条，格式为：根据《中华人民共和国刑法》第X条...
3. 如果同时有法律和司法解释，先引用法律，再引用司法解释
4. 如果涉及量刑，要说明具体刑期范围
5. 如果问题包含多个方面，要分点回答
6. 如果检索到的内容不足以回答，请明确告知
7. 回答要严谨、准确，用中文

回答："""
        )
        
        # ===== 增强检索函数（使用纯向量检索） =====
        def enhanced_retrieve_with_llm(question):
            """
            使用大模型理解并改写问题，然后进行向量检索
            """
            # 步骤1: 用大模型改写问题
            print(f"🤔 正在理解问题: {question}")
            rewritten_query = rewrite_question_with_llm(question)
            
            # 将改写结果保存到session_state
            st.session_state.last_rewritten_query = rewritten_query
            
            # 步骤2: 用改写后的查询检索
            docs1 = retriever.invoke(rewritten_query)
            
            # 步骤3: 同时用原始问题检索
            docs2 = retriever.invoke(question)
            
            # 步骤4: 专门针对刑法问题的特殊处理
            if "罪" in question or "刑法" in question:
                law_query = f"刑法 {question}"
                docs3 = retriever.invoke(law_query)
            else:
                docs3 = []
            
            # 步骤5: 合并所有结果，去重
            all_docs = []
            seen_ids = set()
            
            for doc in docs1 + docs2 + docs3:
                if id(doc) not in seen_ids:
                    all_docs.append(doc)
                    seen_ids.add(id(doc))
            
            # 步骤6: 过滤版权内容
            all_docs = filter_copyright_docs(all_docs)
            
            # 步骤7: 重排序
            all_docs = rerank_docs_by_question(question, all_docs)
            
            # 记录检索到的文档数量
            st.session_state.last_retrieved_count = len(all_docs)
            
            return all_docs
        
        # 格式化文档函数
        def format_docs_with_sources(docs):
            if not docs:
                return "没有找到相关法律条文。"
            
            formatted_docs = []
            for i, doc in enumerate(docs):
                source = doc.metadata.get('file_name', '未知来源')
                category = doc.metadata.get('category', '其他')
                content = doc.page_content.strip()
                formatted_docs.append(f"[{category}]《{source}》\n{content}")
            
            return "\n\n---\n\n".join(formatted_docs)
        
        # 构建问答链
        chain = (
            RunnableParallel({
                "context": lambda x: format_docs_with_sources(enhanced_retrieve_with_llm(x)),
                "question": RunnablePassthrough()
            })
            | prompt
            | llm
            | StrOutputParser()
        )
        
        progress_bar.progress(100, text="✅ 知识库加载完成！")
        progress_bar.empty()
        
        file_stats['chunk_count'] = len(docs)
        
        return chain, enhanced_retrieve_with_llm, file_stats
        
    except Exception as e:
        st.error(f"加载知识库时出错: {e}")
        import traceback
        with st.expander("查看详细错误"):
            st.code(traceback.format_exc())
        return None, None, {}


# ==================== 页面配置 ====================
st.set_page_config(
    page_title="刑法知识问答助手",
    page_icon="⚖️",
    layout="wide"
)

# 初始化会话状态
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'current_folder' not in st.session_state:
    st.session_state.current_folder = ""

if 'chain' not in st.session_state:
    st.session_state.chain = None

if 'retriever_func' not in st.session_state:
    st.session_state.retriever_func = None

if 'file_stats' not in st.session_state:
    st.session_state.file_stats = {}

if 'last_rewritten_query' not in st.session_state:
    st.session_state.last_rewritten_query = None

if 'last_retrieved_count' not in st.session_state:
    st.session_state.last_retrieved_count = 0

# 初始化检索参数
if 'keyword_weight' not in st.session_state:
    st.session_state.keyword_weight = 0.3

if 'top_k' not in st.session_state:
    st.session_state.top_k = 6


# ==================== 侧边栏界面 ====================
with st.sidebar:
    st.title("⚖️ 刑法知识问答助手")
    
    folder_path = st.text_input(
        "输入法律法规文件夹路径",
        value=r"D:\py\CriminalLawAssistant\books",
        placeholder="例如: D:/laws"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        load_button = st.button("📂 加载知识库", type="primary", use_container_width=True)
    with col2:
        if st.button("🔄 重置对话", use_container_width=True):
            st.session_state.messages = []
            st.rerun()
    
    if st.button("🗑️ 清除缓存并重新加载", use_container_width=True):
        st.cache_resource.clear()
        st.session_state.messages = []
        st.session_state.chain = None
        st.session_state.retriever_func = None
        st.rerun()
    
    st.markdown("---")
    
    # ===== 检索参数调节滑块 =====
    st.markdown("### 🔧 检索参数调节")
    
    # 检索数量滑块
    top_k = st.slider(
        "📊 检索数量",
        min_value=2,
        max_value=15,
        value=st.session_state.top_k,
        step=1,
        help="每次检索返回的文档数量"
    )
    st.session_state.top_k = top_k
    
    st.markdown("---")
    
    # 显示改写结果
    if st.session_state.last_rewritten_query:
        st.markdown("### 🔄 问题理解")
        st.info(f"📝 **原始:** {st.session_state.messages[-2]['content'] if len(st.session_state.messages) >= 2 else ''}\n\n✍️ **改写:** {st.session_state.last_rewritten_query}")
    
    if st.session_state.last_retrieved_count > 0:
        st.info(f"🔍 检索到 {st.session_state.last_retrieved_count} 个相关法条")
    
    # 显示知识库统计
    if st.session_state.file_stats:
        st.markdown("---")
        st.markdown("### 📊 知识库统计")
        stats = st.session_state.file_stats
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("总文件数", stats.get('total_files', 0))
        with col2:
            st.metric("文本块数", stats.get('chunk_count', 0))
        
        # 显示分类统计
        if stats.get('by_category'):
            st.markdown("**文件分类:**")
            for cat, count in stats['by_category'].items():
                st.markdown(f"- {cat}: {count}个")
        
        # 显示文件列表
        if stats.get('file_details'):
            with st.expander("📋 已加载文件"):
                for f in stats['file_details']:
                    st.markdown(f"**{f['name']}**")
                    st.markdown(f"类别: {f.get('category', '未知')}")
                    st.markdown(f"大小: {f.get('size', 0)} 字符")
                    st.markdown("---")
    
    st.markdown("---")
    st.markdown("### 💡 使用提示")
    st.markdown("""
    **可以问这些问题：**
    - 故意杀人罪怎么判？
    - 盗窃罪的立案标准
    - 什么是正当防卫？
    - 贪污多少钱判死刑？
    - 未成年人犯罪处理
    - 袭警罪的最新规定
    - 洗钱罪的认定标准
    """)


# ==================== 主界面 ====================
st.title("⚖️ 刑法知识问答助手")
st.markdown("---")

# 处理加载按钮点击
if load_button and folder_path:
    if folder_path != st.session_state.current_folder:
        st.session_state.current_folder = folder_path
        with st.spinner("正在初始化知识库，这可能需要几分钟..."):
            chain, retriever_func, stats = load_knowledge_base(folder_path)
            if chain:
                st.session_state.chain = chain
                st.session_state.retriever_func = retriever_func
                st.session_state.file_stats = stats
                st.success(f"✅ 知识库加载成功！")
                st.rerun()
            else:
                st.error("❌ 知识库加载失败，请检查文件夹路径和文件格式")

# 显示聊天历史
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if "references" in message and message["references"]:
            with st.expander("📖 查看参考法条"):
                for i, ref in enumerate(message["references"]):
                    st.markdown(f"**来源: {ref['source']}**")
                    st.markdown(f"```\n{ref['content'][:300]}...\n```")
                    if i < len(message["references"]) - 1:
                        st.markdown("---")

# 聊天输入框
if prompt := st.chat_input("请输入您的法律问题", disabled=not st.session_state.chain):
    # 添加用户消息
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("user"):
        st.markdown(prompt)
    
    with st.chat_message("assistant"):
        with st.spinner("🔍 正在检索相关法条..."):
            try:
                if st.session_state.chain and st.session_state.retriever_func:
                    # 显示当前检索参数
                    st.caption(f"⚙️ 当前检索参数：检索数量 {st.session_state.top_k}")
                    
                    # 清除之前的改写结果
                    st.session_state.last_rewritten_query = None
                    st.session_state.last_retrieved_count = 0
                    
                    # 检索文档
                    docs = st.session_state.retriever_func(prompt)
                    
                    references = []
                    for doc in docs[:3]:
                        references.append({
                            'source': doc.metadata.get('file_name', '未知来源'),
                            'content': doc.page_content
                        })
                    
                    # 获取回答
                    answer = st.session_state.chain.invoke(prompt)
                    
                    st.markdown(answer)
                    
                    message_data = {"role": "assistant", "content": answer}
                    if references:
                        message_data["references"] = references
                    st.session_state.messages.append(message_data)
                    
                    if references:
                        with st.expander("📖 查看参考法条"):
                            for i, ref in enumerate(references):
                                st.markdown(f"**📄 {ref['source']}**")
                                st.markdown(f"```\n{ref['content'][:300]}...\n```")
                                if i < len(references) - 1:
                                    st.markdown("---")
                    
                    if len(docs) < 2:
                        st.info("💡 只找到少量相关法条，可以尝试换个问法")
                    
                    # 刷新侧边栏显示改写结果
                    st.rerun()
                else:
                    st.error("❌ 知识库未加载，请先在侧边栏加载文件夹")
                    
            except Exception as e:
                st.error(f"❌ 发生错误: {e}")
                import traceback
                with st.expander("查看详细错误"):
                    st.code(traceback.format_exc())

# 欢迎信息
if not st.session_state.chain:
    with st.chat_message("assistant"):
        st.markdown("""
        👋 你好！我是刑法知识问答助手。
        
        请先在左侧边栏：
        1. 输入包含法律法规的文件夹路径
        2. 点击"加载知识库"按钮
        3. 等待系统处理完文档后，就可以开始提问了
        
        **可以问这些问题试试：**
        - 故意杀人罪怎么判？
        - 盗窃罪的立案标准
        - 什么是正当防卫？
        - 袭警罪的最新规定
        - 洗钱罪的认定标准
        """)


# ==================== 页脚 ====================
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray; padding: 10px;'>"
    "刑法知识问答系统 | 基于 LangChain + Streamlit + 通义千问 | 纯向量检索 v1.0 | 仅供参考，不构成法律意见"
    "</div>", 
    unsafe_allow_html=True
)