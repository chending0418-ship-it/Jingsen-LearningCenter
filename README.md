# Jingsen 学习中心 1.0

## 项目简介

多学科智能题目生成系统，支持英语、语文、数学三个学科。

当前版本重点完成了英语模块升级：

- 英语大模块拆分为 `Word Palace` 和 `MAP Test`。
- `Word Palace` 承接原英语词汇练习，并完成选项混淆项优化、数量扩展和英语词库通用化。
- `MAP Test` 已先跑通 `Language Arts` 前后端流程；`Reading` 暂时保留入口，后续继续。
- 新增 `Daily Reports`，将 Word Palace 和 MAP Language Arts 的每日练习历史保存到服务器本地文件。

当前版本仍使用本地文件持久化：

- 词库元数据存储在 `data/library_registry.json`。
- 词条内容存储在 `data/*.txt`。
- 每日练习报告存储在 `data/report_history.json`。
- 应用重部署后，只要保留服务器目录，词库和历史报告数据不会丢失。

---

## 技术栈

- 后端框架：FastAPI
- AI 服务：OpenAI API
- 前端：静态 HTML + Tailwind CSS + 原生 JavaScript
- 数据持久化：本地文件（`library_registry.json`、`*.txt`、`report_history.json`）
- Python：3.11+（建议）

---

## 目录结构

```text
Jingsen-LearningCenter-V1/
├── api/                         # API 路由层
│   ├── english.py               # Word Palace 英语词汇练习接口
│   ├── map_language_arts.py     # MAP Language Arts 生成/评估/skills 接口
│   ├── report_history.py        # Daily Reports 历史报告接口
│   └── admin.py                 # 词库后台接口
├── services/                    # 业务逻辑层
│   ├── english_service.py       # Word Palace 出题/批改/报告保存
│   ├── map_language_arts_service.py
│   ├── report_history_service.py
│   └── library_admin_service.py
├── core/                        # AI 生成器等核心组件
├── models/                      # Pydantic 数据模型
├── static/                      # 前端页面
├── data/                        # 本地持久化目录
├── config.py                    # 配置管理
├── main.py                      # 应用入口
└── requirements.txt             # 依赖管理
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

> 词库和报告历史直接保存在服务器本地 `data/` 目录，无需数据库配置。

### 3) 启动服务

```bash
python3 main.py
```

服务默认启动在：`http://localhost:8000`

---

## 英语模块说明

### English 首页

`/english` 现在是英语大模块首页，只展示两个入口：

- `Word Palace`
- `MAP Test`

点击入口后才进入对应子模块视图。首页不直接展示后续设置。

### Word Palace

`Word Palace` 是原英语词汇练习升级版。

已完成：

- 词库选择。
- 题型选择：`cloze` / `match`。
- 数量选择：`10`、`20`、`30`、`50`、自定义。
- 自定义数量限制：`1-50`。
- 英语词库不再绑定具体练习类型，所有英语词库均可用于所有 Word Palace 练习类型。
- 后台英语词库统一显示为“通用”。
- 英语新增/编辑词库时不再选择 `cloze` / `match`。
- 出题后端会对 AI 返回的选项做后处理：
  - 校验正确答案。
  - 选项去重。
  - 从完整词库候选池补足混淆项。
  - 降低同一套题中选项重复。
  - 随机打乱选项顺序。

### MAP Test

`MAP Test` 下包含：

- `Language Arts`：已完成前后端跑通。
- `Reading`：暂时 Pending。

#### MAP Language Arts

当前 `Language Arts` 不是随机出题器，而是按 Skill 组织的练习系统。

支持 8 个 Skill：

1. `grammar_usage`：Grammar & Usage 语法与用法
2. `pronoun_reference`：Pronoun Reference 代词指代
3. `punctuation`：Punctuation 标点
4. `capitalization`：Capitalization 大小写
5. `sentence_combining`：Sentence Combining 句子合并
6. `sentence_revision`：Sentence Revision 句子修改
7. `paragraph_organization`：Paragraph Organization 段落组织
8. `research_source_integration`：Research & Source Integration 信息整合

已完成流程：

- 选择 Skill。
- 选择年级。
- 选择题量：`5`、`10`、`15`、`20`、自定义。
- 选择难度：`Easy`、`Medium`、`Hard`、`Adaptive`。
- AI 生成结构化 MAP-style Language Arts 题目。
- 做题时显示具体知识点标签，例如 `vague pronouns`、`subject-verb agreement`、`capitalization in letters`。
- 已选选项有明显高亮和 `Selected` 标记。
- 提交后显示正确/错误和解析。
- 完成后生成评估报告。
- 报告中明确展示薄弱知识点。
- 可点击薄弱知识点进入专项练习。

---

## Daily Reports 历史报告

英语页顶部有 `Daily Reports` 入口。

该功能用于查看每日练习历史，覆盖：

- `Word Palace`
- `MAP Language Arts`

实现方式：

- 不使用数据库。
- 每次完成练习后写入 `data/report_history.json`。
- 每次打开 Daily Reports 时读取本地文件并聚合展示。

展示内容：

- 每天练习次数。
- 每天总题数。
- 每天正确数。
- 每天总准确率。
- Word Palace / MAP Language Arts 分模块统计。
- 最近练习记录。
- MAP Language Arts 的薄弱知识点标签。

> `data/report_history.json` 是生产数据文件，部署和备份时需要保留。

---

## 词库持久化说明（重要）

应用启动时会执行以下逻辑：

1. 确保 `data/` 目录存在。
2. 读取 `data/library_registry.json` 作为词库元数据。
3. 读取对应的 `data/*.txt` 作为词条内容。
4. 若缺少 registry，会根据现有 `*.txt` 自动生成基础元数据。

因此：

- `data/` 是生产主存储目录，请务必做备份。
- 后续管理可通过 Admin 页面/API 修改本地文件词库。
- `data/report_history.json` 也属于生产数据，需要一起备份。

---

## 页面入口

- `/portal`：学科门户
- `/english`：英语模块首页（Word Palace / MAP Test / Daily Reports）
- `/chinese`：语文练习
- `/math`：数学页面
- `/admin`：词库后台（列表）
- `/admin/new`：新增词库
- `/admin/library?id=<library_id>`：词库详情/编辑

> 从 `/portal` 进入 `Library Admin` 需要输入固定密码 `0418`。

---

## 主要 API

### Word Palace / 英语词汇练习

- `GET /api/english/generate`
  - 参数：`count`, `library`, `mode`（`cloze` / `match`）
- `GET /api/english/libraries`
  - 兼容 `mode` 参数，但英语词库不再按题型过滤。
- `POST /api/english/grade`
  - 批改完成后会写入 `data/report_history.json`。
- `GET /api/english/library/{library_name}`

### MAP Language Arts

- `GET /api/map/language-arts/skills`
  - 返回 8 个 Language Arts Skill 元数据。
- `POST /api/map/language-arts/generate`
  - 请求字段：`skill_area`、`grade_level`、`difficulty`、`question_count`、`option_count`、`include_explanation`、`subskill_focus`（可选）。
- `POST /api/map/language-arts/evaluate`
  - 评估完成后会写入 `data/report_history.json`。

### Daily Reports

- `GET /api/reports/history`
  - 参数：`days`（默认 30）
  - 参数：`module`（可选：`word_palace` / `map_language_arts`）

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

## `/learningcenter` 前缀兼容

当前后端路由同时注册根路径和 `/learningcenter` 前缀，例如：

- `/api/map/language-arts/generate`
- `/learningcenter/api/map/language-arts/generate`
- `/api/reports/history`
- `/learningcenter/api/reports/history`

前端页面会根据当前路径自动处理 `/learningcenter` 前缀。

---

## 服务器部署（本地文件持久化）

### 1) 准备环境变量

至少包含：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（可选）
- `MODEL_NAME`
- `PORT`（可选）

### 2) 构建与启动命令

Build Command:

```bash
pip3 install -r requirements.txt
```

Start Command:

```bash
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

### 3) 持久化结果

确保服务器上的项目目录，尤其是 `data/`，不被清理或覆盖，即可长期保留：

- 词库元数据
- 词条内容
- 每日练习报告

---

## 后续 TODO（下次继续）

### P0 收尾

- 继续检查 `Daily Reports` 的真实做题数据展示效果。
- 根据实际学生使用反馈微调 Language Arts report 的文案和布局。
- 清理本地 mock report 数据，避免部署时混入测试数据。
- 清理不需要提交的 `__pycache__`、`server.log`、打包文件等变更。
- 运行一次完整手动回归：Word Palace、MAP Language Arts、Daily Reports、Admin 词库。

### P1：MAP Test 后续

- 继续增强 `MAP Language Arts` 的题型模板质量。
- 为每个 Skill 拆更细的 subskill 配置和 prompt 策略。
- 增加更稳定的专项练习推荐策略。
- 后续接入用户提供的 skills，让每个知识点由独立 skill 控制出题策略。
- `Reading` 暂时 Pending，等 Language Arts 稳定后再开始。

### P2：OCR / 图片上传

- 图片上传、拍照、OCR、Vision、多模态识别建库暂时 Pending。
- 目前未接入相关依赖和接口。

---

## 开发建议

- 词库变更优先通过 Admin API 操作。
- `data/` 是主存储目录，建议定期备份。
- `data/report_history.json` 会持续增长，后续可考虑增加归档或分页策略。
- 新词库可直接通过 Admin 新建，或手动维护 `data/*.txt` 与 `library_registry.json`。
