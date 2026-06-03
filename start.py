"""
start.py - Python 启动脚本
双击运行或命令行执行: python start.py
"""

import os
import sys
import subprocess
import platform

def main():
    print("=" * 50)
    print("  知识库问答系统 v1.5")
    print("  AI模型: Qwen 2.5-1.5B")
    print("=" * 50)
    print()
    
    # 切换到脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # 创建文件夹
    print("[1/4] 初始化文件夹...")
    os.makedirs("models", exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    os.makedirs("vector_db", exist_ok=True)
    
    # 检查模型
    model_path = os.path.join("models", "qwen2.5-1.5b-instruct-q4_k_m.gguf")
    
    if not os.path.exists(model_path):
        print()
        print("[提示] 未找到AI模型文件 (约1.12G)")
        download = input("是否现在下载？(y/n): ").strip().lower()
        
        if download == 'y':
            print()
            print("正在下载模型，使用国内镜像加速...")
            print("文件较大，请耐心等待...")
            
            url = "https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
            
            try:
                import requests
                from tqdm import tqdm
                
                response = requests.get(url, stream=True)
                total_size = int(response.headers.get('content-length', 0))
                
                with open(model_path, 'wb') as f:
                    with tqdm(total=total_size, unit='B', unit_scale=True, desc="下载进度") as pbar:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                pbar.update(len(chunk))
                
                print("✅ 模型下载完成！")
            except ImportError:
                # 如果没有 tqdm，使用简单下载
                import urllib.request
                urllib.request.urlretrieve(url, model_path)
                print("✅ 模型下载完成！")
            except Exception as e:
                print(f"❌ 下载失败: {e}")
                print()
                print("请手动下载模型：")
                print("1. 打开浏览器访问: https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct-GGUF")
                print(f"2. 下载后放到: {os.path.abspath(model_path)}")
                input("按回车键退出")
                return
        else:
            print("请手动下载模型后重新运行")
            input("按回车键退出")
            return
    
    # 检查模型文件大小
    model_size = os.path.getsize(model_path) / (1024 * 1024)
    if model_size < 800:
        print(f"⚠️ 模型文件可能不完整 ({model_size:.0f}MB / ~900MB)")
        print("建议重新下载")
    
    # 安装依赖
    print()
    print("[2/4] 检查并安装依赖包...")
    
    packages = [
        "kivy==2.3.0",
        "llama-cpp-python",
        "langchain",
        "langchain-community",
        "chromadb",
        "sentence-transformers",
        "pypdf",
        "python-docx"
    ]
    
    for pkg in packages:
        print(f"  检查 {pkg}...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", pkg.split("==")[0]],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  安装 {pkg}...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg, "-i", "https://pypi.tuna.tsinghua.edu.cn/simple"],
                capture_output=True
            )
    
    # 启动应用
    print()
    print("[3/4] 启动应用...")
    print("=" * 50)
    print()
    
    # 运行主程序
    main_py = os.path.join(script_dir, "main.py")
    result = subprocess.run([sys.executable, main_py])
    
    print()
    print("应用已退出")
    input("按回车键关闭")


if __name__ == "__main__":
    main()