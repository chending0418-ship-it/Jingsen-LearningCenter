# Jingsen 学习中心 1.0

## 项目简介

多学科智能题目生成系统，支持英语、语文、数学三个学科。

当前主线是英语模块升级：

- `English Learning` 拆分为 `Word Palace` 和 `MAP Test`。
- `Word Palace` 当前包含 `Daily Word` 既有词库练习能力，以及 `Vocabulary Skills` 按 Grade / Topic / Skill 的诊断练习。
- `Daily Word` 支持 `Cloze`、`Match`、`Passage Cloze` 三种题型；普通题和短文填空的干扰项优先使用所选词库中的其他词。
- `MAP Test` 当前包含 `Language Arts` 和 `Reading`。
- `MAP Language Arts` 已接入用户提供的 Skills 数据，支持按 `Grade -> Topic -> Skill` 出题，并按 `Detail` 做诊断报告。
- `MAP Reading` 已有 Skills 数据文件，但出题/评估/前端练习流程暂时 Pending。
- 新增 `Daily Reports`，将 Daily Word、Vocabulary Skills 和 MAP Language Arts 的每日练习历史保存到统一 SQLite 数据库。
- Word Palace 的普通 Daily Word（`cloze` / `match`）和 Vocabulary Skills 已改为异步分批出题：创建任务后立即返回，首批 3 题生成后即可开始答题，后续题目在后台继续生成。

当前版本以 `data/learning-center.sqlite3` 为统一持久化数据库；旧 JSON/TXT 数据会通过幂等迁移导入并继续作为部署备份来源保留。当前 Schema 版本为 `2`，详细字段见 [`SQLITE_DATABASE_SCHEMA.md`](SQLITE_DATABASE_SCHEMA.md)。

重要功能里程碑、线上部署基线和故障恢复记录见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## 当前阶段状态

### P0：English / MAP Test / Daily Reports 基础结构

状态：已完成并已验证。

已完成：

- `/english` 英语首页只显示模块入口。
- 点击 `Word Palace` 后进入独立子视图。
- 点击 `MAP Test` 后进入独立子视图。
- `MAP Test` 下展示 `Language Arts` / `Reading` 入口。
- `Daily Reports` 入口可查看本地历史报告。
- `Admin` 首页可选择 `词库管理` 或 `Skills 管理`。
- `/admin/skills` 可查看和维护 Skills 数据启用状态。
- 支持 `/learningcenter` 路径前缀。

验证结果：

- Python 编译通过。
- `static/english.html`、`static/admin.html`、`static/admin_skills.html` 内联 JS 语法通过。
- 关键路由已注册：
  - `/english`
  - `/admin`
  - `/admin/skills`
  - `/api/skills`
  - `/api/reports/history`

---

### P1：接入 MAP Language Arts Skills

状态：已完成并已验证。

原计划：

- 等用户提供 `MAP Language Arts` Skills 列表。
- 导入 Skills JSON。
- Language Arts 前端读取 Skills 树。
- 出题接口改为按 Skill 出题。
- Report 继续按 Skill / Detail 诊断。

实际完成：

- Skills 数据已拆分存储在 `data/skills/`，不是单个 `skills_registry.json`。
- `MAP Language Arts` Skills 已导入：`data/skills/map_language_arts.json`。
- 当前数量：`342` 条 Language Arts Skills。
- 前端读取 Skills Tree：`Grade -> Topic -> Skill -> Detail`。
- 前端选择流程：
  - `Grade`
  - `Topic`
  - `Skill`
  - 不直接选择 `Detail`
- 出题逻辑：
  - 按 `Grade + Topic + Skill` 选中一组 Details。
  - AI 出题时自动覆盖该 Skill 下的多个 Detail。
  - 题目顶部显示可读 `Detail`，不是 type id。
  - 题目中 `<u>...</u>` 会安全渲染为下划线。
- Report 逻辑：
  - `Weak Knowledge Points` 显示可读 Detail。
  - `Recommended Next Practice` 显示可读 Detail。
  - 后端会把 AI 返回的 detail id 映射为真实 Detail 文本。
  - 评估结果会写入 SQLite 练习报告表。

P1 说明：

- 原计划里写过“按 `skill_id` 出题”。现在根据产品确认，实际采用的是更适合学生的方式：按 `Grade / Topic / Skill` 出题，不让学生选择单个 Detail；系统内部自动覆盖多个 Detail，并在报告中指出薄弱 Detail。

验证结果：

- `data/skills/map_language_arts.json` 可读取。
- Skills tree 可生成。
- `/api/map/language-arts/skills/tree` 可访问。
- `/api/map/language-arts/generate` 路由已注册。
- `/api/map/language-arts/evaluate` 路由已注册。
- 模拟 AI 验证通过：
  - 能按 `Grade 6 / Grammar and mechanics / Spelling` 生成题目。
  - detail id 会映射为真实 Detail。
  - Report 的 weak point 和 recommendation 都显示真实 Detail。

---

### P2：接入 MAP Reading Skills

状态：Pending。

已完成基础：

- `MAP Reading` Skills 数据已导入：`data/skills/map_reading.json`。
- 当前数量：`154` 条 Reading Skills。
- Skills 管理后台可以查看和启用/停用 Reading Details。

待完成：

1. 新增 Reading 后端服务：
   - `services/map_reading_service.py`
2. 新增 Reading API：
   - `GET /api/map/reading/skills`
   - `GET /api/map/reading/skills/tree`
   - `POST /api/map/reading/generate`
   - `POST /api/map/reading/evaluate`
3. Reading 前端接通：
   - `Grade -> Topic -> Skill` 选择。
   - 不直接选择 Detail。
   - 题目覆盖多个 Detail。
4. Reading 题型策略：
   - passage comprehension
   - inference
   - vocabulary in context
   - textual evidence
   - source-based reasoning
5. Reading Report：
   - 按 Skill / Detail 诊断。
   - Weak Knowledge Points 显示可读 Detail。
   - Recommended Next Practice 指向具体 Detail。
6. Daily Reports：
   - Reading 完成评估后写入 SQLite 练习报告表。
   - Daily Reports 前端增加 `MAP Reading` 模块过滤项。

注意：P2 当前保持 Pending，不在本轮继续实现。

---

### P3：接入 Word Palace Vocabulary Skills

状态：已完成并已验证。

已完成：

- `Word Palace Vocabulary Skills` 数据已导入：`data/skills/word_vocabulary_skills.json`。
- 当前数量：`139` 条 Vocabulary Skills。
- Skills 管理后台可以查看和启用/停用 Vocabulary Skills Details。
- Word Palace 前端已拆分二级入口：
  - `Daily Word`
  - `Vocabulary Skills`
- `Daily Word` 保留词库选择、题量、`cloze / match / passage_cloze`、批改和 Daily Reports；答题流程已改为先选择答案，再点击 `Submit Answer` 后显示结果。
- `Passage Cloze` 会先从所选词库选择 5 / 10 / 15 / 20 个单词，生成一段上下文通顺的短文，并让学生为每个空选择唯一正确答案。
- `Daily Reports` 的 Word Palace 历史卡片会直接展示错词，展开详情后可查看每题或每个空的学生答案、正确答案和解析。
- `Vocabulary Skills` 前端读取 Skills Tree，选择流程为：
  - `Grade`
  - `Topic`
  - `Skill`
  - 不让学生直接选择 Detail。
- 选择 Skill 后，页面会展示该 Skill 下启用的 Detail，方便确认练习覆盖范围。
- 新增后端服务：`services/vocabulary_skills_service.py`。
- 新增 API：`api/vocabulary_skills.py`。
- API 已同时注册根路径和 `/learningcenter` 前缀。
- 出题逻辑会根据 `Grade / Topic / Skill` 自动覆盖多个 Detail。
- 题目、评估报告和 Daily Reports 都显示真实 Detail 文本，不显示内部 detail id。
- 评估报告输出：
  - `score`
  - `total`
  - `correct_count`
  - `accuracy`
  - `question_results`
  - `weak_knowledge_points`
  - `recommended_next_practice`
- 评估完成后写入 SQLite 练习报告表：
  - `module`: `word_vocabulary_skills`
  - `module_label`: `Vocabulary Skills`
- Daily Reports 前端已支持筛选和展示 `Vocabulary Skills` 历史报告。

报告页一致性：

- Daily Word、Vocabulary Skills、MAP Language Arts 的结果页都提供：
  - `Practice Same Skill`
  - `Back to Selection`
  - 对应 Home 入口
- Vocabulary Skills 和 MAP Language Arts 的 Weak Knowledge Points 支持按弱项 Detail 单独再练。
- Vocabulary Skills 和 MAP Language Arts 的 Recommended Next Practice 会提升一个难度等级并可直接生成练习。

---

### P4：Word Palace 异步分批出题

状态：已完成并已验证。

- Daily Word 的 `cloze` / `match` 与 Vocabulary Skills 创建后台生成任务后立即返回 `job_id`，页面不再等待全部题目一次性生成。
- 首批固定生成 3 题；前端收到首批后立即进入答题，轮询期间会追加后续题目，并保留学生已经选择的答案。
- 学生答到尚未生成的位置时，只在当前题位等待，不阻塞已经可答的题目。
- `Passage Cloze` 需要一次生成完整短文及全部空位，继续使用同步完整生成流程。
- 任务状态保存在 SQLite `generation_jobs` 表中，支持 Gunicorn 多 worker 共享进度。
- 状态包括 `queued`、`generating`、`completed`、`partial_failed`、`failed` 和 `cancelled`。
- 后续批次失败时保留已经生成的题目；取消、超时和过期清理可避免页面无限 loading。
- 原有同步 `/generate` API 保留兼容。

验证结果：完整测试集 `33 passed`；SQLite 迁移幂等、完整性检查及外键检查通过。

---

## Skills 数据结构

Skills 统一存储在：

```text
data/skills/
├── index.json
├── map_language_arts.json
├── map_reading.json
└── word_vocabulary_skills.json
```

当前 Skills 数量：

| 文件 | 模块 | 数量 | 状态 |
|---|---|---:|---|
| `map_language_arts.json` | MAP Language Arts | 342 | P1 已接通 |
| `map_reading.json` | MAP Reading | 154 | P2 Pending |
| `word_vocabulary_skills.json` | Word Palace Vocabulary Skills | 139 | P3 已接通 |

每条 Skill 使用统一结构：

```text
Grade | Topic | Skill | Detail
```

例如：

```text
Grade 6 | Grammar and mechanics | Spelling | Learn to spell words with prefixes: ex-, in-, mid-
```

---

## 技术栈

- 后端框架：FastAPI
- AI 服务：OpenAI API
- 前端：静态 HTML + Tailwind CSS + 原生 JavaScript
- 数据持久化：SQLite（WAL 模式，统一数据库）
- Python：3.11+

---

## 本地持久化数据

生产数据主要在 `data/`：

```text
data/learning-center.sqlite3   # 统一数据库：词库、Skills、报告、Todo、异步生成任务等
data/library_registry.json     # 旧词库元数据及迁移/部署备份来源
data/library_archive.json      # 旧归档词库数据及迁移/部署备份来源
data/*.txt                     # 旧活动词库内容及迁移来源
data/report_history.json       # 旧报告迁移来源
data/skills/*.json             # Skills 种子与旧数据迁移来源
```

SQLite Schema 由 `database/sqlite.py` 定义；应用启动和 `scripts/migrate_to_sqlite.py` 会幂等应用 Schema 版本并迁移尚未导入的旧数据。部署时必须完整保留服务器上的 `data/`，不要用本地 `data/` 覆盖线上数据。

---

## 页面入口

- `/portal`：学科门户
- `/english`：英语模块首页
- `/admin`：Admin 首页，可选择词库管理或 Skills 管理
- `/admin/new`：新增词库
- `/admin/library?id=<library_id>`：词库详情/编辑
- `/admin/skills`：Skills 知识点查看和启用/停用维护
- `/chinese`：语文练习
- `/math`：数学页面

> 从 `/portal` 进入 `Library Admin` 需要输入固定密码 `0418`。

---

## 主要 API

### Word Palace / Daily Word

- `POST /api/english/generation-jobs`
  - `cloze` / `match` 的异步分批生成入口；创建后返回 `job_id`。
- `GET /api/english/generation-jobs/{job_id}`
  - 参数：`after`；返回游标后的新题和 `queued/generating/completed/partial_failed/failed/cancelled` 状态。
- `DELETE /api/english/generation-jobs/{job_id}`
  - 取消尚未完成的后台生成任务。
- `GET /api/english/generate`
  - 参数：`count`, `library`, `mode`（`cloze` / `match` / `passage_cloze`）
  - 保留兼容；`passage_cloze` 继续使用此完整生成接口，`count` 只支持 `5`, `10`, `15`, `20`。
- `GET /api/english/libraries`
- `GET /api/english/library/{library_name}`
- `POST /api/english/grade`
  - 批改完成后写入 SQLite 练习报告表。
  - `passage_cloze` 会按每个 blank 单独计分，并保存错词到历史报告。

### Word Palace / Vocabulary Skills

- `POST /api/word-palace/vocabulary-skills/generation-jobs`
- `GET /api/word-palace/vocabulary-skills/generation-jobs/{job_id}`
  - 参数：`after`；前端在首批 3 题后开始作答，并继续获取后续批次。
- `DELETE /api/word-palace/vocabulary-skills/generation-jobs/{job_id}`
- `GET /api/word-palace/vocabulary-skills/skills`
  - 参数：`grade`, `topic`, `skill`, `enabled_only`
- `GET /api/word-palace/vocabulary-skills/skills/tree`
  - 返回：`Grade -> Topic -> Skill -> Details`
- `POST /api/word-palace/vocabulary-skills/generate`
  - 当前请求重点字段：`grade_level`, `topic`, `skill`, `difficulty`, `question_count`, `option_count`, `include_explanation`, `detail_focus`。
- `POST /api/word-palace/vocabulary-skills/evaluate`
  - 评估完成后写入 SQLite 练习报告表，模块标识为 `word_vocabulary_skills`。

### MAP Language Arts

- `GET /api/map/language-arts/skills`
- `GET /api/map/language-arts/skills/tree`
- `POST /api/map/language-arts/generate`
  - 当前请求重点字段：`grade_level`, `topic`, `skill`, `difficulty`, `question_count`, `option_count`, `include_explanation`, `subskill_focus`。
- `POST /api/map/language-arts/evaluate`
  - 评估完成后写入 SQLite 练习报告表。

### Skills 管理

- `GET /api/skills`
  - 参数：`module`, `section`, `grade`, `topic`, `skill`, `enabled_only`
- `GET /api/skills/tree`
  - 参数：`module`, `section`, `enabled_only`
- `GET /api/skills/sections`
- `PATCH /api/skills/{skill_id}`
  - 当前主要用于启用/停用 Detail。

### Daily Reports

- `GET /api/reports/history`
  - 参数：`days`
  - 参数：`module`

### 语文

- `GET /api/chinese/generate`
- `GET /api/chinese/libraries`
- `POST /api/chinese/grade`

### 数学

- `GET /api/math/generate`

---

## `/learningcenter` 前缀兼容

当前后端路由同时注册根路径和 `/learningcenter` 前缀，例如：

- `/api/map/language-arts/generate`
- `/learningcenter/api/map/language-arts/generate`
- `/api/word-palace/vocabulary-skills/generate`
- `/learningcenter/api/word-palace/vocabulary-skills/generate`
- `/api/skills`
- `/learningcenter/api/skills`
- `/api/reports/history`
- `/learningcenter/api/reports/history`

前端页面会根据当前路径自动处理 `/learningcenter` 前缀。

---

## Codex 交接说明

迁移到 Codex 后建议先做以下检查：

```bash
python3 -m py_compile main.py api/skills.py api/map_language_arts.py api/vocabulary_skills.py api/report_history.py models/schemas.py services/skills_service.py services/map_language_arts_service.py services/vocabulary_skills_service.py services/report_history_service.py services/english_service.py
node -e "const fs=require('fs'); for (const f of ['static/english.html','static/admin.html','static/admin_skills.html']) { const html=fs.readFileSync(f,'utf8'); const scripts=[...html.matchAll(/<script[^>]*>([\\s\\S]*?)<\\/script>/gi)].map(m=>m[1]); scripts.forEach(s=>new Function(s)); console.log(f+': ok'); }"
```

然后启动：

```bash
python3 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

重点查看：

- `http://127.0.0.1:8000/english`
- `http://127.0.0.1:8000/admin`
- `http://127.0.0.1:8000/admin/skills`

---

## 后续优先级

1. **P2：MAP Reading**
   - 保持 Pending。
   - 等 Vocabulary Skills 稳定后再做 Reading 出题和评估。
2. **OCR / 图片上传 / Vision**
   - 已取消，不再作为后续计划。

---

## 服务器更新提醒

线上 app 目录：

```bash
/www/wwwroot/learningcenter/app
```

线上更新时请使用 `updateNew.md` 中的安全更新命令，确保：

- 先备份线上 `data/`
- 保留线上 `.env`
- 不覆盖线上词库和 Skills 数据
- 使用 `www` 用户执行 git，避免 `dubious ownership`
- 运行 `scripts/migrate_to_sqlite.py`，幂等升级到 SQLite Schema v2
- 运行 `scripts/validate_persistent_data.py` 并确认 SQLite 完整性
- 更新完成后重启或平滑重载 Gunicorn，再检查 `/health` 和异步 generation-jobs API

仓库内的 `update_safe.sh` 已包含数据快照、代码同步、依赖更新、SQLite 迁移、持久数据校验和更新前健康检查；脚本成功后仍需重载应用进程，才能让 worker 使用新代码。
