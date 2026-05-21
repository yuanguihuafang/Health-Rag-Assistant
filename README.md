# 身体健康智慧问答助手

一个面向健康科普场景的 RAG（Retrieval-Augmented Generation，检索增强生成）问答系统。项目以 Django + Vue 3 为主体，围绕“健康知识库检索、多轮问答、知识卡片、个性化推荐、后台管理”构建完整的前后端应用。

> 本项目用于健康科普与学习演示，不替代医生诊断、处方或急救建议。

## 项目亮点

- **健康 RAG 问答**：从本地健康知识库召回相关片段，再结合大模型生成回答。
- **混合检索策略**：融合 char n-gram、TF-IDF、关键词命中和主题加权，降低纯向量检索对外部服务的依赖。
- **多轮追问理解**：支持“老人呢”“女性呢”这类短追问，结合会话上下文扩展检索问题。
- **知识卡片生成**：每次回答后结构化展示核心要点、注意事项和参考来源。
- **个性化推荐**：根据用户近期问答主题推荐相关健康知识。
- **知识库后台管理**：支持文档上传、启停、删除、重建索引和检索验证。
- **语音提问能力**：预留火山引擎 ASR 配置，支持浏览器录音转文字后问答。
- **系统管理后台**：保留用户、角色、菜单、通知、日志和系统监控等管理能力，便于完整演示。

## 运行截图

### 登录与用户端

![登录页](image/登录.png)

![用户主页](image/用户主页.png)

### 健康 RAG 问答

![健康问答示例一](image/健康问答1.png)

![健康问答示例二](image/健康问答2.png)

### 健康知识推荐与知识库

![健康知识推荐](image/健康知识推荐.png)

![健康知识库](image/健康知识库.png)

### 后台管理

![系统管理仪表盘](image/仪表盘.png)

![用户管理](image/用户管理.png)

![日志管理](image/日志管理.png)

![知识库管理](image/知识库管理.png)

### 启动日志

![终端启动日志](image/终端日志.png)

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 | Python、Django、Django REST Framework、Channels、Daphne |
| 前端 | Vue 3、Vite、TypeScript、Ant Design Vue、Pinia、Axios |
| 数据库 | SQLite（默认本地演示）、MySQL（可扩展） |
| 检索 | scikit-learn、FAISS、规则关键词、主题重排 |
| 大模型 | 本地 Ollama 或 OpenAI 兼容 API |
| 语音识别 | 火山引擎 ASR WebSocket（可选配置） |
| 导出 | ReportLab PDF |

## 框架来源与二次开发说明

本项目是基于 **Hertz Admin / Hertz Studio Django** 相关现成组件继续开发：

- 后端复用了 Hertz 的用户认证、角色权限、菜单管理、通知公告、操作日志、系统监控、统一响应和部分工具组件。
- 前端复用了 Hertz Admin 的管理端布局、权限路由、请求封装、主题样式和基础管理页面。
- 本项目的主要业务增量集中在 `health_rag_assistant` 健康 RAG 模块，以及对应的健康问答、知识库管理、知识卡片、推荐和模型配置页面。

如果环境中存在 Hertz 官方依赖清单，`start.py init` 会尝试通过 Hertz 私有源安装相关依赖：

```text
https://hzpypi.hzsystems.cn
```

该依赖源通常需要可访问网络和对应授权环境。

## 核心流程

```text
用户问题
  -> 会话上下文补全
  -> 查询扩展与主题识别
  -> 知识库召回
  -> 混合重排评分
  -> 构造 Prompt
  -> 调用 LLM
  -> 返回回答、引用片段、知识卡片
```

## 目录结构

```text
.
├── start.py                         # 项目初始化、启动、停止、状态查看脚本
├── backend/
│   ├── manage.py                    # Django 管理入口
│   ├── start_server.py              # Daphne 后端启动器
│   ├── requirements.txt             # 后端依赖
│   ├── .env.example                 # 环境变量示例，不包含真实密钥
│   ├── data/                        # 本地运行数据
│   ├── hertz_server_django/         # Django 项目配置、路由、ASGI 入口
│   ├── health_rag_assistant/        # 健康 RAG 核心业务模块
│   │   ├── models.py                # 会话、问答记录、知识库文档等模型
│   │   ├── views.py                 # API 视图
│   │   ├── urls.py                  # RAG API 路由
│   │   ├── services/                # RAG、检索、LLM、推荐、ASR、PDF 等服务
│   │   ├── management/commands/     # 知识库初始化命令
│   │   └── datasets/                # 内置健康语料
│   ├── hertz_studio_django_auth/    # 登录、权限、用户体系
│   ├── hertz_studio_django_log/     # 操作日志
│   ├── hertz_studio_django_notice/  # 通知公告
│   └── hertz_studio_django_system_monitor/
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── api/                     # 前端 API 封装
        ├── router/                  # 路由
        ├── stores/                  # Pinia 状态
        ├── views/user_pages/        # 用户端健康问答页面
        └── views/admin_page/        # 后台管理页面
```

## 快速开始

### 1. 环境要求

- Python 3.10+
- Node.js 18+
- Windows PowerShell / macOS / Linux Shell
- 可选：Redis、Ollama、本地或云端 OpenAI 兼容模型服务

### 2. 配置环境变量

复制示例配置：

```bash
copy backend\.env.example backend\.env
```

Linux/macOS：

```bash
cp backend/.env.example backend/.env
```

如使用本地 Ollama：

```env
OLLAMA_BASE_URL=http://localhost:11434
HEALTH_RAG_MODEL_NAME=deepseek-r1:1.5b
HEALTH_RAG_API_KEY=
```

如使用 OpenAI 兼容 API：

```env
OLLAMA_BASE_URL=https://api.example.com/v1
HEALTH_RAG_MODEL_NAME=deepseek-chat
HEALTH_RAG_API_KEY=sk-xxx
```

请不要把真实的 `backend/.env`、API Key、数据库文件提交到 GitHub。

### 3. 初始化依赖

```bash
python start.py init
```

该命令会创建后端虚拟环境、安装 Python 依赖，并执行前端 `npm install`。

### 4. 启动项目

```bash
python start.py
```

或显式运行：

```bash
python start.py start
```

默认地址：

- 前端：http://127.0.0.1:3000
- 后端：http://127.0.0.1:8000

启动后日志会直接显示在当前终端。按 `Ctrl+C` 可停止本次由 `start.py` 启动的前后端进程。

### 5. 查看或停止服务

```bash
python start.py status
python start.py stop
```

`stop` 会停止占用 8000 和 3000 端口的进程，使用前请确认这两个端口确实属于本项目。

## 初始化知识库

进入后端目录后可执行：

```bash
cd backend
venv\Scripts\python manage.py seed_health_rag_kb --normalize-paths
```

Linux/macOS：

```bash
cd backend
./venv/bin/python manage.py seed_health_rag_kb --normalize-paths
```

初始化后可以在后台知识库页面查看文档，也可以上传新的 `txt` / `md` 文档并重建索引。

## 默认账号

| 角色 | 用户名 | 密码 |
| --- | --- | --- |
| 超级管理员 | hertz | hertz |
| 普通用户 | demo | 123456 |

如数据库重新初始化，账号以实际初始化脚本或数据库内容为准。

## 主要接口

健康 RAG 接口前缀：`/api/health-rag/`

| 接口 | 方法 | 说明 |
| --- | --- | --- |
| `health/` | GET | 健康检查 |
| `chat/ask/` | POST | 提交健康问题 |
| `chat/sessions/` | GET | 获取会话列表 |
| `chat/sessions/create/` | POST | 新建会话 |
| `chat/history/` | GET | 获取问答历史 |
| `chat/history/export/pdf/` | POST | 导出历史 PDF |
| `chat/transcribe/` | POST | 语音转写 |
| `recommend/` | GET | 个性化推荐 |
| `kb/documents/` | GET | 知识库文档列表 |
| `kb/documents/create/` | POST | 上传知识文档 |
| `kb/documents/update/` | POST | 更新知识文档 |
| `kb/documents/delete/` | POST | 删除知识文档 |
| `kb/reindex/` | POST | 重建知识库索引 |
| `model/status/` | GET | 查看模型状态 |
| `model/status/custom/` | POST | 检查自定义模型配置 |
| `model/switch/` | POST | 切换模型配置 |
| `model/restart/` | POST | 重启模型连接 |


## 当前项目边界

- 系统提供健康科普问答能力，不提供医疗诊断结论。
- LLM 服务不可用时，系统会返回知识库检索片段作为兜底参考。
- 语音识别依赖第三方 ASR 配置，未配置时不影响文字问答。
- SQLite 适合本地演示；多人协作或线上部署建议切换到 MySQL/PostgreSQL，并单独配置 Redis。


## License

仅用于学习。如需商用，请自行确认模板代码、依赖库、语料数据和第三方服务的授权范围。
