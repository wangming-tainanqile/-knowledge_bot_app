"""
知识库问答 App - Qwen 1.5B 离线版
模型大小：约900MB
内存需求：约1.5GB
许可证：MIT（免费商用）
"""

import os
import sys
import threading
import json
from pathlib import Path

# 修复Android路径
if hasattr(sys, 'android'):
    from android.storage import primary_external_storage_path
    BASE_DIR = primary_external_storage_path()
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Kivy GUI
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle

# 设置窗口
Window.size = (400, 700)

# 尝试导入llama.cpp
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False
    print("⚠️ llama-cpp-python 未安装，请运行: pip install llama-cpp-python")

# LangChain组件
try:
    from langchain.document_loaders import TextLoader, PyPDFLoader, UnstructuredWordDocumentLoader
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.embeddings import HuggingFaceEmbeddings
    from langchain.vectorstores import Chroma
    from langchain.chains import RetrievalQA
    from langchain.prompts import PromptTemplate
    from langchain.llms.base import LLM
    from typing import Optional, List, Any, Mapping
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("⚠️ LangChain 未安装")


class LlamaCppLLM(LLM):
    """将llama.cpp模型包装为LangChain兼容的LLM"""
    
    def __init__(self, model_path, n_ctx=2048, n_threads=2, n_batch=512):
        super().__init__()
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_batch = n_batch
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """加载模型"""
        if not LLAMA_AVAILABLE:
            print("llama_cpp 不可用")
            return
        
        try:
            print(f"正在加载模型: {self.model_path}")
            self.model = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                n_batch=self.n_batch,
                n_gpu_layers=0,
                verbose=False
            )
            print("模型加载成功")
        except Exception as e:
            print(f"模型加载失败: {e}")
    
    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:
        """生成回答"""
        if self.model is None:
            return "模型未加载，请检查模型文件是否存在"
        
        try:
            response = self.model(
                prompt,
                max_tokens=256,
                temperature=0.7,
                top_p=0.9,
                top_k=40,
                repeat_penalty=1.1,
                stop=stop or ["<|im_end|>", "\n\n\n"]
            )
            return response['choices'][0]['text'].strip()
        except Exception as e:
            return f"生成出错: {str(e)}"
    
    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        return {"model_path": self.model_path}
    
    @property
    def _llm_type(self) -> str:
        return "llama_cpp"


class ChatBubble(BoxLayout):
    """聊天气泡组件"""
    def __init__(self, text, is_user=True, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.padding = [10, 8, 10, 8]
        self.spacing = 8
        
        # 计算高度
        lines = text.count('\n') + 1
        max_chars_per_line = 35
        estimated_lines = max(lines, (len(text) // max_chars_per_line) + 1)
        self.height = max(50, estimated_lines * 22 + 20)
        
        # 头像
        avatar = Label(
            text='👤' if is_user else '🤖',
            font_size='28sp',
            size_hint_x=0.12,
            size_hint_y=None,
            height=44
        )
        
        # 气泡标签
        label = Label(
            text=text,
            color=(0.1, 0.1, 0.1, 1) if is_user else (1, 1, 1, 1),
            size_hint_x=0.8,
            text_size=(Window.width * 0.65, None),
            halign='left',
            valign='top',
            font_size='14sp',
            markup=True
        )
        label.bind(size=self._update_label_height)
        
        self.add_widget(avatar)
        self.add_widget(label)
        
        # 气泡背景
        with self.canvas.before:
            if is_user:
                Color(0.2, 0.65, 0.9, 1)
            else:
                Color(0.85, 0.85, 0.85, 1)
            self.bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])
        
        self.bind(pos=self._update_bg, size=self._update_bg)
    
    def _update_bg(self, instance, value):
        self.bg.pos = instance.pos
        self.bg.size = instance.size
    
    def _update_label_height(self, instance, value):
        if instance.texture_size[1] > 0:
            new_height = instance.texture_size[1] + 20
            if new_height > self.height:
                self.height = new_height
                instance.height = new_height


class KnowledgeBotApp(App):
    """主应用"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.qa_chain = None
        self.is_processing = False
        
        # 路径配置
        self.docs_path = os.path.join(BASE_DIR, '知识库文档')
        self.vector_db_path = os.path.join(BASE_DIR, '知识库索引')
        self.model_path = os.path.join(BASE_DIR, 'models', 'qwen2.5-1.5b-instruct-q4_k_m.gguf')
        
        self.llm = None
        
    def build(self):
        """构建界面"""
        self.root_layout = BoxLayout(orientation='vertical', padding=12, spacing=10)
        
        # 标题栏
        title_bar = BoxLayout(size_hint_y=0.08, spacing=10)
        title = Label(
            text='📚 知识库问答',
            font_size='22sp',
            bold=True,
            color=(0.2, 0.6, 0.9, 1),
            size_hint_x=0.6
        )
        self.status_label = Label(
            text='● 初始化中',
            color=(0.9, 0.6, 0.2, 1),
            size_hint_x=0.4,
            font_size='12sp'
        )
        title_bar.add_widget(title)
        title_bar.add_widget(self.status_label)
        self.root_layout.add_widget(title_bar)
        
        # 知识库信息栏
        info_card = BoxLayout(
            orientation='vertical',
            size_hint_y=0.09,
            spacing=5,
            padding=[10, 5, 10, 5]
        )
        
        kb_row = BoxLayout(orientation='horizontal', spacing=8)
        kb_row.add_widget(Label(text='📁 知识库目录:', size_hint_x=0.3, font_size='12sp', color=(0.5,0.5,0.5,1)))
        self.kb_path_label = Label(
            text=self._shorten_path(self.docs_path),
            size_hint_x=0.5,
            font_size='11sp',
            color=(0.6, 0.6, 0.6, 1)
        )
        select_btn = Button(text='📂 更换', size_hint_x=0.2, font_size='12sp', background_color=(0.3,0.3,0.3,1))
        select_btn.bind(on_press=self.select_folder)
        kb_row.add_widget(self.kb_path_label)
        kb_row.add_widget(select_btn)
        
        info_card.add_widget(kb_row)
        self.root_layout.add_widget(info_card)
        
        # 聊天区域
        self.chat_scroll = ScrollView(size_hint_y=0.66)
        self.chat_layout = BoxLayout(orientation='vertical', size_hint_y=None, spacing=10)
        self.chat_layout.bind(minimum_height=self.chat_layout.setter('height'))
        self.chat_scroll.add_widget(self.chat_layout)
        self.root_layout.add_widget(self.chat_scroll)
        
        # 欢迎消息
        self.add_chat_message(
            "🤖 你好！我是知识库助手\n\n"
            "📖 **使用说明**：\n"
            "1. 点击「📂 更换」选择你的文档文件夹\n"
            "2. 将 PDF/Word/TXT 文件放入该文件夹\n"
            "3. 点击下方「📖 构建知识库」\n"
            "4. 开始提问！\n\n"
            "💡 **支持格式**：.txt .pdf .docx\n"
            "⚡ **AI模型**：Qwen 1.5B（已内置）\n"
            "🔒 **完全离线**，无需联网",
            is_user=False
        )
        
        # 输入区域
        input_layout = BoxLayout(size_hint_y=0.09, spacing=10)
        self.text_input = TextInput(
            hint_text='输入问题...',
            multiline=False,
            font_size='15sp',
            size_hint_x=0.75,
            background_color=(0.95, 0.95, 0.95, 1)
        )
        self.text_input.bind(on_text_validate=self.send_question)
        
        self.send_btn = Button(
            text='📤 发送',
            size_hint_x=0.25,
            font_size='14sp',
            background_color=(0.2, 0.7, 0.3, 1),
            disabled=True
        )
        self.send_btn.bind(on_press=self.send_question)
        
        input_layout.add_widget(self.text_input)
        input_layout.add_widget(self.send_btn)
        self.root_layout.add_widget(input_layout)
        
        # 底部按钮栏
        btn_layout = BoxLayout(size_hint_y=0.08, spacing=10)
        
        build_btn = Button(
            text='📖 构建知识库',
            background_color=(0.2, 0.6, 0.9, 1),
            font_size='14sp'
        )
        build_btn.bind(on_press=self.build_knowledge_base)
        
        clear_btn = Button(
            text='🗑️ 清空对话',
            background_color=(0.7, 0.4, 0.2, 1),
            font_size='14sp'
        )
        clear_btn.bind(on_press=self.clear_chat)
        
        btn_layout.add_widget(build_btn)
        btn_layout.add_widget(clear_btn)
        self.root_layout.add_widget(btn_layout)
        
        # 进度条
        self.progress = ProgressBar(size_hint_y=0.02, value=0)
        self.progress.opacity = 0
        self.root_layout.add_widget(self.progress)
        
        # 初始化
        self._init_folders()
        threading.Thread(target=self.init_llm, daemon=True).start()
        
        return self.root_layout
    
    def _init_folders(self):
        """创建必要文件夹"""
        os.makedirs(self.docs_path, exist_ok=True)
        os.makedirs(self.vector_db_path, exist_ok=True)
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
    
    def _shorten_path(self, path):
        if len(path) > 35:
            return '...' + path[-32:]
        return path
    
    def init_llm(self):
        """初始化LLM模型"""
        Clock.schedule_once(lambda dt: self._update_status('● 加载AI模型中...', (0.9, 0.6, 0.2, 1)), 0)
        
        if not LLAMA_AVAILABLE:
            Clock.schedule_once(lambda dt: self.add_chat_message(
                "❌ **缺少依赖**\n\n请运行以下命令安装：\n`pip install llama-cpp-python`",
                is_user=False
            ), 0)
            return
        
        # 检查模型文件
        if not os.path.exists(self.model_path):
            Clock.schedule_once(lambda dt: self.add_chat_message(
                f"⚠️ **模型文件不存在**\n\n请将 `qwen2.5-1.5b-instruct-q4_k_m.gguf`\n放入以下文件夹：\n`{self.model_path}`\n\n"
                "📥 **下载地址**：\nhttps://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF",
                is_user=False
            ), 0)
            Clock.schedule_once(lambda dt: self._update_status('● 缺少模型', (0.9, 0.3, 0.3, 1)), 0)
            return
        
        try:
            model_size = os.path.getsize(self.model_path) / (1024 * 1024)
            Clock.schedule_once(lambda dt: self.add_chat_message(
                f"✅ 找到模型文件 ({model_size:.0f}MB)\n⏳ 正在加载，请稍候...",
                is_user=False
            ), 0)
            
            self.llm = LlamaCppLLM(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=2,
                n_batch=256
            )
            
            Clock.schedule_once(lambda dt: self._update_status('● AI已就绪', (0.4, 0.8, 0.4, 1)), 0)
            Clock.schedule_once(lambda dt: self.add_chat_message(
                "✅ AI模型加载成功！现在可以构建知识库了。",
                is_user=False
            ), 0)
            
            self.load_knowledge_base()
            
        except Exception as e:
            Clock.schedule_once(lambda dt: self.add_chat_message(
                f"❌ **模型加载失败**\n\n{str(e)[:150]}",
                is_user=False
            ), 0)
            Clock.schedule_once(lambda dt: self._update_status('● 模型错误', (0.9, 0.3, 0.3, 1)), 0)
    
    def _update_status(self, text, color):
        self.status_label.text = text
        self.status_label.color = color
    
    def select_folder(self, instance):
        """选择文件夹"""
        content = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        start_path = '/storage/emulated/0' if hasattr(sys, 'android') else os.path.expanduser('~')
        filechooser = FileChooserListView(
            path=start_path,
            dirselect=True,
            size_hint_y=0.85
        )
        
        btn_layout = BoxLayout(size_hint_y=0.15, spacing=10)
        confirm_btn = Button(text='✓ 选择此文件夹', background_color=(0.2, 0.7, 0.3, 1))
        cancel_btn = Button(text='✗ 取消')
        
        popup = Popup(title='📁 选择知识库文件夹', content=content, size_hint=(0.95, 0.9))
        
        def confirm(instance):
            if filechooser.selection:
                selected = filechooser.selection[0]
                if os.path.isdir(selected):
                    self.docs_path = selected
                    self.kb_path_label.text = self._shorten_path(selected)
                    popup.dismiss()
                    self.add_chat_message(
                        f"📁 知识库已切换到：**{selected}**\n\n"
                        "点击「📖 构建知识库」开始学习你的文档。",
                        is_user=False
                    )
                else:
                    self.add_chat_message("⚠️ 请选择一个文件夹", is_user=False)
        
        confirm_btn.bind(on_press=confirm)
        cancel_btn.bind(on_press=popup.dismiss)
        
        btn_layout.add_widget(confirm_btn)
        btn_layout.add_widget(cancel_btn)
        
        content.add_widget(filechooser)
        content.add_widget(btn_layout)
        
        popup.open()
    
    def load_knowledge_base(self):
        """加载已有知识库"""
        if not LANGCHAIN_AVAILABLE:
            Clock.schedule_once(lambda dt: self.add_chat_message(
                "⚠️ LangChain未安装，知识库功能不可用",
                is_user=False
            ), 0)
            return
        
        if not os.path.exists(self.vector_db_path) or not os.listdir(self.vector_db_path):
            return
        
        try:
            Clock.schedule_once(lambda dt: self.add_chat_message(
                "📂 正在加载已有知识库...",
                is_user=False
            ), 0)
            
            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'}
            )
            
            vectorstore = Chroma(
                persist_directory=self.vector_db_path,
                embedding_function=embeddings
            )
            
            self._create_qa_chain(vectorstore)
            
        except Exception as e:
            print(f"加载知识库失败: {e}")
    
    def _create_qa_chain(self, vectorstore):
        """创建问答链"""
        prompt_template = """你是一个专业的问答助手。请严格基于以下提供的资料回答问题。

参考资料：
{context}

问题：{question}

请基于参考资料给出简洁准确的答案。如果资料中没有相关信息，请说"根据现有资料无法回答这个问题"。"""
        
        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )
        
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": PROMPT},
            return_source_documents=True
        )
        
        Clock.schedule_once(lambda dt: setattr(self.send_btn, 'disabled', False), 0)
        Clock.schedule_once(lambda dt: self.add_chat_message(
            "✅ 知识库已加载，可以开始提问了！",
            is_user=False
        ), 0)
    
    def build_knowledge_base(self, instance):
        """构建知识库"""
        if not self.llm:
            self.add_chat_message("⚠️ AI模型正在加载中，请稍后再试...", is_user=False)
            return
        
        if not LANGCHAIN_AVAILABLE:
            self.add_chat_message(
                "❌ **缺少依赖**\n\n请运行：\n`pip install langchain chromadb sentence-transformers pypdf python-docx`",
                is_user=False
            )
            return
        
        if self.is_processing:
            self.add_chat_message("⚠️ 正在处理中，请稍后...", is_user=False)
            return
        
        def build():
            self.is_processing = True
            Clock.schedule_once(lambda dt: setattr(self.progress, 'opacity', 1), 0)
            Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 0), 0)
            Clock.schedule_once(lambda dt: self._update_status('● 构建知识库...', (0.9, 0.6, 0.2, 1)), 0)
            
            try:
                if not os.path.exists(self.docs_path):
                    os.makedirs(self.docs_path)
                    Clock.schedule_once(lambda dt: self.add_chat_message(
                        f"📁 已创建文件夹，请放入文档后重新点击构建",
                        is_user=False
                    ), 0)
                    return
                
                documents = []
                files = os.listdir(self.docs_path)
                supported = ('.txt', '.pdf', '.docx')
                found = [f for f in files if f.lower().endswith(supported)]
                
                if not found:
                    Clock.schedule_once(lambda dt: self.add_chat_message(
                        f"❌ 文件夹中没有支持的文档\n\n支持的格式：.txt, .pdf, .docx",
                        is_user=False
                    ), 0)
                    return
                
                Clock.schedule_once(lambda dt: self.add_chat_message(
                    f"📄 找到 **{len(found)}** 个文档，正在加载...",
                    is_user=False
                ), 0)
                
                for i, file in enumerate(files):
                    file_path = os.path.join(self.docs_path, file)
                    def update_progress(p):
                        Clock.schedule_once(lambda dt, val=p: setattr(self.progress, 'value', val), 0)
                    update_progress(i / len(files) * 0.4)
                    
                    try:
                        if file.lower().endswith('.txt'):
                            loader = TextLoader(file_path, encoding='utf-8')
                        elif file.lower().endswith('.pdf'):
                            loader = PyPDFLoader(file_path)
                        elif file.lower().endswith('.docx'):
                            loader = UnstructuredWordDocumentLoader(file_path)
                        else:
                            continue
                        
                        docs = loader.load()
                        documents.extend(docs)
                    except Exception as e:
                        print(f"加载失败 {file}: {e}")
                
                if not documents:
                    Clock.schedule_once(lambda dt: self.add_chat_message(
                        "❌ 没有找到可读的文档内容",
                        is_user=False
                    ), 0)
                    return
                
                Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 0.5), 0)
                Clock.schedule_once(lambda dt: self.add_chat_message(
                    f"✂️ 正在处理文档（共 {len(documents)} 页/段）...",
                    is_user=False
                ), 0)
                
                text_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=500,
                    chunk_overlap=50
                )
                chunks = text_splitter.split_documents(documents)
                
                Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 0.7), 0)
                Clock.schedule_once(lambda dt: self.add_chat_message(
                    f"💾 正在创建向量索引（共 {len(chunks)} 个片段）...",
                    is_user=False
                ), 0)
                
                embeddings = HuggingFaceEmbeddings(
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    model_kwargs={'device': 'cpu'}
                )
                
                vectorstore = Chroma.from_documents(
                    documents=chunks,
                    embedding=embeddings,
                    persist_directory=self.vector_db_path
                )
                vectorstore.persist()
                
                self._create_qa_chain(vectorstore)
                
                Clock.schedule_once(lambda dt: setattr(self.progress, 'value', 1), 0)
                Clock.schedule_once(lambda dt: self.add_chat_message(
                    f"✅ **知识库构建完成！**\n\n"
                    f"📄 处理了 {len(found)} 个文档\n"
                    f"📝 生成了 {len(chunks)} 个知识片段\n"
                    f"🎉 现在可以开始提问了！",
                    is_user=False
                ), 0)
                
            except Exception as e:
                Clock.schedule_once(lambda dt: self.add_chat_message(
                    f"❌ **构建失败**\n\n{str(e)[:200]}",
                    is_user=False
                ), 0)
            
            finally:
                self.is_processing = False
                Clock.schedule_once(lambda dt: setattr(self.progress, 'opacity', 0), 0)
                Clock.schedule_once(lambda dt: self._update_status('● 就绪', (0.4, 0.8, 0.4, 1)), 0)
        
        threading.Thread(target=build, daemon=True).start()
    
    def send_question(self, instance):
        """发送问题"""
        if self.is_processing:
            self.add_chat_message("⏳ 请稍后，正在处理中...", is_user=False)
            return
        
        if not self.qa_chain:
            self.add_chat_message("⚠️ 请先点击「📖 构建知识库」", is_user=False)
            return
        
        question = self.text_input.text.strip()
        if not question:
            return
        
        self.add_chat_message(question, is_user=True)
        self.text_input.text = ''
        
        def ask():
            self.is_processing = True
            Clock.schedule_once(lambda dt: setattr(self.send_btn, 'disabled', True), 0)
            Clock.schedule_once(lambda dt: self._update_status('● AI思考中...', (0.9, 0.6, 0.2, 1)), 0)
            
            try:
                result = self.qa_chain({"query": question})
                answer = result['result']
                
                sources = []
                for doc in result['source_documents'][:2]:
                    content = doc.page_content[:200]
                    source_name = os.path.basename(doc.metadata.get('source', '未知'))
                    sources.append(f"📖 **参考**：《{source_name}》\n> {content}...")
                
                if sources:
                    answer += "\n\n" + "\n".join(sources)
                
                Clock.schedule_once(lambda dt: self.add_chat_message(answer, is_user=False), 0)
                
            except Exception as e:
                Clock.schedule_once(lambda dt: self.add_chat_message(
                    f"❌ **出错了**\n\n{str(e)[:150]}",
                    is_user=False
                ), 0)
            
            finally:
                self.is_processing = False
                Clock.schedule_once(lambda dt: setattr(self.send_btn, 'disabled', False), 0)
                Clock.schedule_once(lambda dt: self._update_status('● 就绪', (0.4, 0.8, 0.4, 1)), 0)
        
        threading.Thread(target=ask, daemon=True).start()
    
    def add_chat_message(self, text, is_user=True):
        """添加聊天消息"""
        bubble = ChatBubble(text, is_user)
        self.chat_layout.add_widget(bubble)
        Clock.schedule_once(lambda dt: setattr(self.chat_scroll, 'scroll_y', 0), 0.1)
    
    def clear_chat(self, instance):
        """清空对话"""
        self.chat_layout.clear_widgets()
        self.add_chat_message("🗑️ 对话已清空", is_user=False)


if __name__ == '__main__':
    KnowledgeBotApp().run()