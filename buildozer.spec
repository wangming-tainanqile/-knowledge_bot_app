[app]
title = 知识库问答
package.name = knowledgebot
package.domain = com.yourcompany
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,txt,db,gguf
version = 1.0.0

# 关键：添加所有依赖
requirements = python3,kivy==2.3.0,llama-cpp-python,langchain,langchain-community,chromadb,sentence-transformers,pypdf,python-docx,numpy

# 模型文件路径：将其包含在APK中
# 将 qwen-model.gguf 放到项目目录的 models/ 文件夹
# 然后通过以下方式包含
source.include_dirs = models

orientation = portrait
fullscreen = 0

android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.sdk = 33

# 指定模型文件为二进制类型
android.add_src = models/qwen-model.gguf