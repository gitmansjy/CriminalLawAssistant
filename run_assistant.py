# run_assistant.py
import subprocess
import sys
import os
from pathlib import Path

def check_environment():
    """检查环境是否准备好"""
    print("=" * 60)
    print("刑法知识问答助手 - 启动器")
    print("=" * 60)
    
    # 检查虚拟环境
    venv_path = Path(".venv")
    if not venv_path.exists():
        print("⚠️ 未检测到虚拟环境，请先创建")
        print("   python -m venv .venv")
        print("   .venv\\Scripts\\activate")
        return False
    
    # 检查books目录
    books_path = Path("books")
    if not books_path.exists():
        print("❌ books目录不存在")
        return False
    
    # 检查关键文件
    required_files = [
        "books/刑法.txt",
        "books/刑事诉讼法.txt",
        "books/司法解释全文"
    ]
    
    missing_files = []
    for f in required_files:
        if not Path(f).exists():
            missing_files.append(f)
    
    if missing_files:
        print("⚠️ 缺少以下文件：")
        for f in missing_files:
            print(f"   - {f}")
        print("\n请先运行转换脚本和爬虫")
        return False
    
    print("✅ 环境检查通过")
    return True

def show_file_stats():
    """显示文件统计信息"""
    print("\n📊 知识库统计：")
    
    books_path = Path("books")
    
    # 统计法律文件
    law_files = list(books_path.glob("*.txt")) 
    print(f"📄 法律文件: {len(law_files)} 个")
    for f in law_files:
        if f.name not in ["司法解释_完整列表.txt"]:
            size = f.stat().st_size / 1024
            print(f"   - {f.name} ({size:.1f} KB)")
    
    # 统计司法解释
    司法解释文件 = list(books_path.glob("司法解释全文/*.txt"))
    print(f"\n⚖️ 司法解释: {len(司法解释文件)} 个")
    if len(司法解释文件) > 0:
        print(f"   - 最新: {司法解释文件[0].name}")
        print(f"   - 最早: {司法解释文件[-1].name}")
    
    return len(司法解释文件) > 0

def main():
    """主函数"""
    if not check_environment():
        input("\n按回车键退出...")
        return
    
    has_interpretations = show_file_stats()
    
    print("\n" + "=" * 60)
    print("正在启动 Streamlit 应用...")
    print("=" * 60)
    
    if has_interpretations:
        print("✅ 司法解释已加载")
    else:
        print("⚠️ 未找到司法解释，建议先运行爬虫")
        print("   python crawl_judicial.py")
    
    print("\n🚀 启动中，请稍候...")
    print("   浏览器将自动打开")
    print("   如果未打开，请访问: http://localhost:8501")
    print("\n" + "=" * 60)
    
    # 运行 Streamlit 应用
    try:
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])
    except KeyboardInterrupt:
        print("\n\n👋 应用已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")

if __name__ == "__main__":
    main()