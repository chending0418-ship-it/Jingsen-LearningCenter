# Jingsen 学习中心 1.0

## 项目简介

多学科智能题目生成系统，支持英语、语文、数学三个学科的题目自动生成。

## 阶段进度（Roadmap）

- Phase 1：已完成（词库注册表与后台管理 API）
- Phase 2：已完成（出题逻辑接入“仅启用词库”）
- Phase 3：已完成（后台列表/新增/详情三页面 + 门户管理入口）
- Phase 4：已完成（前台英语/语文页面动态加载启用词库并按题型联动）
- Phase 5：已完成（稳定性与异常提示收敛）
  - 出题与词库接口增加题型参数校验与明确错误信息
  - 前台页面在“无可用词库”时禁用开始按钮并展示原因
  - 后台保存类动作统一成功/失败提示，网络异常也会明确提示
  - 词库类型、词条保存增加服务端校验（含空词条拦截）

## 技术栈

- **后端框架**: FastAPI
- **AI 服务**: OpenAI API
- **Python 版本**: 3.8+

## 目录结构

```
Jingsen-LearningCenter-V1/
├── api/              # API 路由层
├── services/         # 业务逻辑层
├── core/             # 核心组件
├── models/           # 数据模型
├── data/             # 数据文件(词库等)
├── config.py         # 配置管理
├── main.py           # 应用入口
└── requirements.txt  # 依赖管理
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件并配置以下变量:

```
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-3.5-turbo
PORT=8000
```

### 3. 运行服务

```bash
python main.py
```

服务将在 `http://localhost:8000` 启动。

> 管理后台入口说明：从 `/portal` 点击 `Library Admin` 时需要输入固定密码 `0418` 才可进入。

## API 接口

### 英语学科

- `GET /api/english/generate` - 生成英语题目
  - 参数: `count`, `library`, `mode` (cloze/match)
- `GET /api/english/libraries` - 获取英语可用词库
  - 参数: `mode`（可选，cloze/match）

### 语文学科

- `GET /api/chinese/generate` - 生成语文题目
  - 模式: `word_discrim` (词语辨析), `conj_fill` (关联词填空), `idiom_fill`（成语填空）
  - 特色: 关联词模式支持五联题交互，支持点击填空与 AI 深度解析
- `GET /api/chinese/libraries` - 获取语文可用词库
  - 参数: `mode`（可选，word_discrim/conj_fill/idiom_fill）

### 后台词库管理

- 页面路由：
  - `/admin`（列表）
  - `/admin/new`（新增）
  - `/admin/library?id=<library_id>`（详情/编辑）
- 管理 API：
  - `GET /api/admin/libraries`
  - `GET /api/admin/libraries/{library_id}`
  - `POST /api/admin/libraries`
  - `PUT /api/admin/libraries/{library_id}`
  - `PATCH /api/admin/libraries/{library_id}/status`
  - `PUT /api/admin/libraries/{library_id}/items`

### 数学学科

- `GET /api/math/generate` - 生成数学题目 (已上线)

## 部署说明 (Render)

### 1. 环境变量配置
在 Render 控制面板设置以下变量：
- `PYTHON_VERSION`: `3.11.7`
- `OPENAI_API_KEY`: 您的 API 密钥
- `OPENAI_BASE_URL`: API 代理地址 (可选)
- `MODEL_NAME`: 模型名称 (如 `gpt-4o`)

### 2. 命令配置
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`

## 开发说明

- 各学科逻辑独立封装在 `services/` 目录
- 公共组件(AI生成器、词库管理)位于 `core/` 目录
- 遵循轻量级设计原则，易于维护和扩展
