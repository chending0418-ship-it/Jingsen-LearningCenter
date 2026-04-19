# Jingsen 学习中心 1.0

## 项目简介

多学科智能题目生成系统，支持英语、语文、数学三个学科。

当前版本已完成**词库本地持久化升级**：
- 词库元数据存储在 `data/library_registry.json`。
- 词条内容存储在 `data/*.txt`。
- 应用重部署后，只要保留服务器目录，词库数据不会丢失。

---

## 技术栈

- 后端框架：FastAPI
- AI 服务：OpenAI API
- 数据持久化：本地文件（`library_registry.json` + `*.txt`）
- Python：3.11+（建议）

---

## 目录结构

```text
Jingsen-LearningCenter-V1/
├── api/              # API 路由层
├── services/         # 业务逻辑层（含词库文件存储服务）
├── core/             # 核心组件
├── models/           # 数据模型
├── data/             # 词库主存储目录（registry + txt）
├── config.py         # 配置管理
├── main.py           # 应用入口
└── requirements.txt  # 依赖管理
```

---

## 本地快速开始

### 1) 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2) 配置环境变量

创建 `.env` 文件：

```env
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-3.5-turbo
PORT=8000
# DATABASE_URL 已不再需要
```

> 词库直接保存在服务器本地 `data/` 目录，无需数据库配置。

### 3) 启动服务

```bash
python3 main.py
```

服务默认启动在：`http://localhost:8000`

---

## 词库持久化说明（重要）

应用启动时会执行以下逻辑：

1. 确保 `data/` 目录存在
2. 读取 `data/library_registry.json` 作为词库元数据
3. 读取对应的 `data/*.txt` 作为词条内容
4. 若缺少 registry，会根据现有 `*.txt` 自动生成基础元数据

因此：
- `data/` 是生产主存储目录，请务必做备份。
- 后续管理可通过 Admin 页面/API 修改本地文件词库。

---

## 页面入口

- `/portal`：学科门户
- `/english`：英语练习
- `/chinese`：语文练习
- `/admin`：词库后台（列表）
- `/admin/new`：新增词库
- `/admin/library?id=<library_id>`：词库详情/编辑

> 从 `/portal` 进入 `Library Admin` 需要输入固定密码 `0418`。

---

## 主要 API

### 英语

- `GET /api/english/generate`
  - 参数：`count`, `library`, `mode`（`cloze` / `match`）
- `GET /api/english/libraries`
  - 参数：`mode`（可选）
- `POST /api/english/grade`
- `GET /api/english/library/{library_name}`

### 语文

- `GET /api/chinese/generate`
  - 参数：`count`, `library`, `mode`（`word_discrim` / `conj_fill` / `idiom_fill`）
- `GET /api/chinese/libraries`
  - 参数：`mode`（可选）
- `POST /api/chinese/grade`

### 后台词库管理

- `GET /api/admin/libraries`
- `GET /api/admin/libraries/{library_id}`
- `POST /api/admin/libraries`
- `PUT /api/admin/libraries/{library_id}`
- `PATCH /api/admin/libraries/{library_id}/status`
- `PUT /api/admin/libraries/{library_id}/items`

### 数学

- `GET /api/math/generate`

---

## 服务器部署（本地文件持久化）

### 1) 准备环境变量

至少包含：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（可选）
- `MODEL_NAME`
- `PORT`（可选）

### 2) 构建与启动命令

- Build Command:

```bash
pip3 install -r requirements.txt
```

- Start Command:

```bash
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

### 3) 持久化结果

确保服务器上的项目目录（尤其是 `data/`）不被清理或覆盖，即可长期保留词库数据。

---

## 开发建议

- 词库变更优先通过 Admin API 操作。
- `data/` 是主存储目录，建议定期备份。
- 新词库可直接通过 Admin 新建，或手动维护 `data/*.txt` 与 `library_registry.json`。
