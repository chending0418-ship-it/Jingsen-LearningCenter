# Jingsen Learning Center：JSON/TXT 全量迁移 SQLite 计划

> 状态：Review 完成，已进入代码实施阶段；尚未推送。

## 1. 目标

将当前由 JSON 和 TXT 文件承担的运行时数据管理完整迁移到 SQLite。

迁移完成后：

- 词库本身是数据库记录。
- 每一条单词、中文词语、成语或连接词都是独立数据库记录。
- Skills、练习报告、模型设置和 Learning Todo 都从 SQLite 读取并写入 SQLite。
- JSON/TXT 不再作为运行时数据源，只保留为首次导入备份或人工导出格式。
- 前端页面和现有 API 的请求、响应结构尽量保持不变。
- 数据库默认位于 `data/learning-center.sqlite3`。

## 2. 为什么选择 SQLite

当前应用部署在单台服务器，使用 FastAPI/Gunicorn，数据规模也适合单机数据库。SQLite 不需要单独运行数据库服务，Python 自带 `sqlite3` 驱动，因此没有 MySQL 的账号、端口、服务进程和网络权限维护成本。

计划启用：

- WAL 日志模式，改善多个 Gunicorn worker 的读写并发。
- 外键约束，避免词库删除后残留孤立词条。
- `busy_timeout`，降低短时间写锁直接报错的概率。
- 显式事务，保证批量导入和多表更新要么全部成功，要么全部回滚。
- `PRAGMA integrity_check`，用于部署后和备份后的数据库完整性检查。

如果未来变成多台应用服务器，再将相同 Repository 接口切换到 MySQL 或 PostgreSQL，不让 API 和页面直接依赖 SQLite 语法。

## 3. 数据范围

本次迁移覆盖以下全部运行数据：

| 当前数据 | 当前来源 | 迁移后的主要表 |
| --- | --- | --- |
| 活动及归档词库 | `data/library_registry.json`、`data/library_archive.json` | `libraries` |
| 词库中的每一条词条 | `data/*.txt`、归档 JSON 中的 `items` | `library_items` |
| Skills 文件目录 | `data/skills/index.json` | `skill_sections` |
| Skills 知识点 | `data/skills/*.json` | `skills`、`skill_question_types`、`skill_tags` |
| 每日练习报告 | `data/report_history.json` | `practice_reports`、`practice_report_items` |
| 默认模型设置 | `data/model-settings.json` | `model_settings` |
| Todo 科目 | `data/learning-todo/subjects.json` | `todo_subjects` |
| Todo 重复模板 | `data/learning-todo/templates.json` | `todo_templates`、`todo_template_weekdays` |
| Todo 月任务 | `data/learning-todo/tasks/*.json` | `todo_tasks`、`todo_task_history` |
| Todo 报告 | `data/learning-todo/reports.json` | `todo_reports` |
| 积分流水 | `data/learning-todo/points-ledger.json` | `points_ledger` |
| Todo 设置 | `data/learning-todo/settings.json` | `todo_settings` |

Podcast 计划、Markdown 文档、前端静态文件和应用配置代码不属于业务数据，不进入数据库。

## 4. 词库关系模型

### 4.1 `libraries`

每一个词库一条记录，活动和归档词库不再分成两个文件。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | TEXT PRIMARY KEY | 保留现有词库 ID |
| `subject` | TEXT NOT NULL | `english` 或 `chinese` |
| `name` | TEXT NOT NULL UNIQUE | 词库名称 |
| `legacy_file_name` | TEXT UNIQUE | 原 TXT 文件名，仅用于迁移追踪 |
| `library_type` | TEXT NULL | 中文词库题型分类 |
| `enabled` | INTEGER NOT NULL | 是否参与出题 |
| `archived` | INTEGER NOT NULL | 是否归档 |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 更新时间 |
| `archived_at` | TEXT NULL | 归档时间 |

约束：

- `enabled` 和 `archived` 只能是 `0` 或 `1`。
- 已归档词库必须为未启用状态。
- 同名词库不能重复。
- 删除词库前默认必须先归档；真正删除需要单独的危险操作。

### 4.2 `library_items`

每一个词条一条记录，不再从 TXT 文件实时读取。

建议字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | 词条内部 ID |
| `library_id` | TEXT NOT NULL | 外键关联 `libraries.id` |
| `content` | TEXT NOT NULL | 原始词条内容 |
| `normalized_content` | TEXT NOT NULL | 用于查重的规范化内容 |
| `sort_order` | INTEGER NOT NULL | 保留原文件顺序 |
| `created_at` | TEXT NOT NULL | 创建时间 |
| `updated_at` | TEXT NOT NULL | 更新时间 |

约束与索引：

- 外键 `library_id` 引用 `libraries.id`。
- 唯一约束 `library_id + sort_order`，保证词条顺序稳定。
- 索引 `library_id + normalized_content`，用于后台搜索和新增时查重。
- 历史重复词条不会在迁移时删除，避免迁移过程改变现有数据。

归档时只更新 `libraries.archived`，词条记录不会移动或删除。恢复归档时也不需要重建 TXT 文件。

## 5. 其他核心表设计

### 5.1 Skills

- `skill_sections`：对应原 `index.json` 中的文件/模块目录。
- `skills`：一条知识点一条记录，保存 `module`、`section`、`grade`、`topic`、`skill`、`detail`、`difficulty`、`enabled` 和 `sort_order`。
- `skill_question_types`：一个 Skill 对应多个题型。
- `skill_tags`：一个 Skill 对应多个标签。

不把 `question_types` 和 `tags` 整体塞进一个 JSON 字段，保证它们可以通过 SQL 查询和筛选。

### 5.2 练习报告

- `practice_reports`：保存一次练习的公共信息，如模块、日期、分数、总题数和正确数。
- `practice_report_items`：每一道题或每一个明细一条记录，关联报告 ID。

实施前需要对 `details` 的全部历史形态做一次结构盘点，再冻结字段；无法统一的非核心展示信息可以保留一个受控的 `extra_json` 字段，但查询所需字段必须是独立列。

### 5.3 模型设置

`model_settings` 使用单例记录，保存：

- `id = 1`
- `selected_model`
- `updated_at`

API Key 仍只存在环境变量，不写入数据库。

### 5.4 Learning Todo

- `todo_subjects`：科目。
- `todo_templates`：重复任务模板。
- `todo_template_weekdays`：每周重复日期，一天一条关联记录。
- `todo_tasks`：任务主体，不再按月份拆文件。
- `todo_task_history`：任务完成、取消、作废等历史事件，一次事件一条记录。
- `todo_reports`：周报、月报和评语。
- `points_ledger`：积分支出流水。
- `todo_settings`：时区、重复任务生成范围和备份保留数量。

`todo_tasks.planned_date`、`subject_id`、`template_id` 和状态字段建立索引，替代遍历全部月份 JSON 的做法。

## 6. 代码结构计划

新增独立存储层，业务 Service 不直接拼 SQL：

```text
database/
├── connection.py
├── migrations/
│   └── 001_initial_schema.sql
└── repositories/
    ├── library_repository.py
    ├── skills_repository.py
    ├── report_repository.py
    ├── model_settings_repository.py
    └── todo_repository.py
```

职责划分：

- `connection.py`：连接、事务、WAL、外键和超时设置。
- `migrations/`：数据库版本升级，禁止靠应用启动时临时猜测表结构。
- Repository：只负责 SQL 和数据库对象转换。
- Service：保留业务校验、出题规则、归档规则和 API 所需数据结构。
- API：原则上不修改请求与响应格式。

## 7. 数据迁移流程

### 阶段 A：迁移前盘点

1. 统计所有 JSON/TXT 文件、文件大小和 SHA-256。
2. 统计活动词库数、归档词库数和各词库词条数。
3. 检查同名词库、重复词条、空词条和缺失 TXT。
4. 统计 Skills、练习报告、Todo 科目、模板、任务、历史事件和积分流水数量。
5. 确认历史报告 `details` 的所有结构变体。
6. 输出只读盘点报告，不修改任何原始数据。

### 阶段 B：建库与迁移脚本

1. 创建临时数据库 `data/learning-center.migration.sqlite3`。
2. 执行版本化 Schema Migration。
3. 在一个主事务中导入全部数据。
4. 先导入父记录，再导入子记录：词库后导入词条，Todo 模板后导入任务。
5. 将原 JSON/TXT 路径和 SHA-256 写入 `data_migration_sources`，保证迁移可审计、可重复判断。
6. 任一文件失败时回滚整个迁移，不产生半套数据库。

### 阶段 C：迁移校验

必须全部通过以下核对：

- 每个活动词库在 `libraries` 中有且只有一条记录。
- 每个归档词库及其词条完整存在。
- 每个词库的原始词条数等于 `library_items` 中的记录数；如因重复词条需要减少，必须生成逐条差异报告并由人工确认。
- Skills 各模块记录数与原文件一致。
- 练习报告总数和每日报告数一致。
- Todo 各月任务数、模板数、科目数、历史事件数和积分流水数一致。
- 随机抽样比较 API 需要的重建对象与原始 JSON 内容。
- `PRAGMA foreign_key_check` 无结果。
- `PRAGMA integrity_check` 返回 `ok`。

校验通过后，将临时数据库原子重命名为 `data/learning-center.sqlite3`。

### 阶段 D：代码切换

建议增加临时环境变量：

```dotenv
STORAGE_BACKEND=json
SQLITE_DATABASE_PATH=/www/wwwroot/learningcenter/app/data/learning-center.sqlite3
```

切换顺序：

1. Repository 与 SQLite Schema 先进入代码，但默认仍使用 JSON。
2. 在测试环境把 `STORAGE_BACKEND` 改为 `sqlite`。
3. 对词库增删改查、归档恢复、随机抽题、Skills 更新、报告写入和 Todo 全流程验收。
4. 生产服务器进入短维护窗口，停止写请求。
5. 备份当前 `data/`，执行最终迁移和校验。
6. 将 `STORAGE_BACKEND=sqlite`，重启 Gunicorn。
7. 健康检查和人工验收通过后恢复访问。

不建议长期双写 JSON 和 SQLite。双写会产生“数据库成功、文件失败”或相反的分叉状态。迁移期间可以双读比较，但正式切换后只允许 SQLite 写入。

## 8. 服务器安装与权限计划

Python 已自带 SQLite 驱动。服务器只建议安装 `sqlite3` 命令行工具，方便人工检查。

Ubuntu/Debian 计划命令：

```bash
sudo apt update
sudo apt install -y sqlite3
sqlite3 --version
```

CentOS/Rocky Linux/AlmaLinux 计划命令：

```bash
sudo dnf install -y sqlite
sqlite3 --version
```

数据库目录必须允许 Gunicorn 用户写入，因为 WAL 模式会在同目录创建 `-wal` 和 `-shm` 文件：

```bash
sudo chown -R www:www /www/wwwroot/learningcenter/app/data
sudo chmod 750 /www/wwwroot/learningcenter/app/data
sudo chmod 640 /www/wwwroot/learningcenter/app/data/learning-center.sqlite3
```

上述命令仅是计划，执行前需要根据服务器真实系统和 Gunicorn 用户确认。

## 9. 备份与部署计划

SQLite 不能在服务持续写入时仅靠普通 `cp` 保证一致性。部署脚本需要改为：

1. 使用 Python `sqlite3.Connection.backup()` 或 SQLite `.backup` 创建一致性快照。
2. 对快照执行 `PRAGMA integrity_check`。
3. 将快照放入现有版本化备份目录。
4. 数据库、`.env` 和迁移版本一并记录到部署清单。
5. 排除运行时的 `learning-center.sqlite3-wal` 和 `learning-center.sqlite3-shm`，它们不能作为独立备份文件恢复。
6. 恢复时先停服务，再恢复主数据库文件，确认目录无旧 WAL/SHM，最后启动服务。

Todo 后台的内部备份可以继续导出 ZIP，但 ZIP 内容应由数据库查询生成 JSON。这是导出格式，不再是运行时存储；恢复 ZIP 时通过事务写回数据库。

## 10. 回滚计划

代码切换前保留：

- 完整 `data/` 快照。
- 原始 JSON/TXT 的 SHA-256 清单。
- 已通过完整性检查的 SQLite 快照。
- SQLite 到旧 JSON/TXT 格式的导出脚本。

回滚分两种情况：

- 尚未产生新数据：切回旧代码并恢复迁移前 `data/` 快照。
- SQLite 已产生新数据：先停止服务，用导出脚本生成兼容的 JSON/TXT，再核对数量后切回旧代码，避免丢失切换后的新增记录。

## 11. 验收标准

- 后台新建词库后，`libraries` 增加一条记录。
- 批量添加 100 个词条后，`library_items` 准确增加 100 条，不生成新 TXT。
- 编辑、去重、排序和删除词条均只操作数据库。
- 归档词库不会删除词条；恢复后可以立即参与管理，启用后可以参与出题。
- 英语和中文出题服务从数据库随机选择词条。
- Skills 后台修改后数据库记录立即更新。
- 练习报告和 Todo 新数据只进入 SQLite。
- 重启两个或更多 Gunicorn worker 后数据一致。
- 部署备份、恢复演练和数据库完整性检查成功。
- 正式切换后业务代码不再调用 JSON/TXT 的持久化读写方法。

## 12. 建议实施顺序

1. 数据盘点脚本和只读报告。
2. SQLite Schema 和 Migration Runner。
3. 词库与词条迁移、Repository、API 回归。
4. Skills 迁移。
5. 练习报告和模型设置迁移。
6. Learning Todo 迁移。
7. 全量迁移校验工具和数据库导出工具。
8. 部署备份脚本调整。
9. 测试环境切换及验收。
10. 生产维护窗口内完成最终迁移。

## 13. Review 时需要确认的决定

- 数据库默认路径是否使用 `data/learning-center.sqlite3`。
- 同一词库中的历史重复词条原样保留，避免迁移过程擅自改变现有数据；新写入的重复控制由业务校验负责。
- 删除词库是否只允许归档，还是后台还需要“永久删除”。建议默认只归档。
- 旧 JSON/TXT 在生产切换后保留多久。建议至少保留两个完整发布周期，并设置为只读备份。
- 是否接受短维护窗口完成最终迁移。建议接受，避免双写带来的数据分叉。
- 历史报告中不规则的 `details` 是否允许保留一个受控 `extra_json` 字段。

代码实施完成后仍需先完成测试与迁移演练，再执行生产服务器安装和正式数据切换。

## 14. Review 结论

- 当前 Todo 功能由上述 8 张业务表完整覆盖，不需要新增用户或孩子表。
- 为保证无损迁移，历史重复词条原样保留；后续新增时再由业务校验阻止重复。
- 各业务表保留受控扩展 JSON，只承载当前无法统一的展示字段；可查询和关联字段均使用独立列或子表。
- `schema_migrations`、`app_state` 和 `data_migration_sources` 是数据库基础设施表，不属于 Todo 业务表。
- 正式切换后 JSON/TXT 只作为迁移源和回滚资料，业务读写全部进入 SQLite。
