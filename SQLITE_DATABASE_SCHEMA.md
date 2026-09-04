# SQLite 数据库表结构与字段字典

## 1. 文档说明

- 数据库类型：SQLite
- 默认数据库文件：`data/learning-center.sqlite3`
- Schema 定义来源：`database/sqlite.py` 中的 `SCHEMA`
- 当前 Schema 版本：`3`
- 表总数：`25`
- 本文中的“维度”指表中的字段（列）。
- SQLite 中的布尔值使用 `INTEGER` 保存：`1` 表示 `true`，`0` 表示 `false`。
- 日期时间通常使用 `TEXT` 保存 ISO 8601 字符串；日期使用 `YYYY-MM-DD`，月份使用 `YYYY-MM`。
- `*_json` 字段用于无损保存尚未完全拆分、需要兼容旧数据结构或可能扩展的数据。

## 2. 表清单

| 序号 | 表名 | 领域 | 用途 | 字段数 |
| ---: | --- | --- | --- | ---: |
| 1 | `schema_migrations` | 系统 | 记录已经应用的数据库 Schema 版本 | 2 |
| 2 | `app_state` | 系统 | 保存迁移完成状态等应用级键值数据 | 3 |
| 3 | `data_migration_sources` | 系统 | 记录旧 JSON/TXT 数据源及文件哈希 | 3 |
| 4 | `libraries` | 词库 | 保存词库主体及状态 | 11 |
| 5 | `library_items` | 词库 | 保存每个词库中的单条词汇或内容 | 7 |
| 6 | `skill_sections` | 技能 | 保存技能来源文件和分区元数据 | 8 |
| 7 | `skills` | 技能 | 保存每一条技能记录 | 12 |
| 8 | `skill_question_types` | 技能 | 保存技能支持的题型列表 | 3 |
| 9 | `skill_tags` | 技能 | 保存技能标签列表 | 3 |
| 10 | `practice_reports` | 练习报告 | 保存练习报告主体与汇总指标 | 9 |
| 11 | `practice_report_items` | 练习报告 | 保存练习报告的明细项 | 3 |
| 12 | `generation_jobs` | 异步出题 | 保存 Word Palace 异步生成任务、进度及题目 | 13 |
| 13 | `model_settings` | 设置 | 保存当前选择的模型 | 3 |
| 14 | `todo_settings` | Todo | 保存 Todo 全局设置 | 6 |
| 15 | `todo_subjects` | Todo | 保存 Todo 科目 | 6 |
| 16 | `todo_templates` | Todo | 保存 Todo 重复任务模板 | 8 |
| 17 | `todo_template_weekdays` | Todo | 保存模板的重复星期设置 | 3 |
| 18 | `todo_tasks` | Todo | 保存实际 Todo 任务 | 9 |
| 19 | `todo_task_history` | Todo | 保存 Todo 任务状态变更历史 | 5 |
| 20 | `todo_reports` | Todo | 保存 Todo 报告记录 | 3 |
| 21 | `points_ledger` | Todo | 保存积分收支流水 | 7 |
| 22 | `reading_books` | Book Reading | 保存上传书籍、资源路径和发布状态 | 15 |
| 23 | `reading_chapters` | Book Reading | 保存识别或人工修正后的章节及页内文字 | 10 |
| 24 | `reading_sessions` | Book Reading | 保存每次引导阅读及整体评估 | 13 |
| 25 | `reading_session_questions` | Book Reading | 保存逐题问答、追问、反馈及家长备注 | 18 |

## 3. 系统与迁移表

### 3.1 `schema_migrations`

用途：记录已执行的数据库结构版本，避免重复应用 Schema 迁移。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `version` | `INTEGER` | 否 | 无 | 主键 | Schema 版本号 |
| `applied_at` | `TEXT` | 否 | 无 |  | 该版本应用时间 |

### 3.2 `app_state`

用途：保存应用级状态。目前主要用于标记某个数据目录的旧数据是否已迁移。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `key` | `TEXT` | 否 | 无 | 主键 | 状态键，例如 `legacy_migrated:<path>` |
| `value` | `TEXT` | 否 | 无 |  | 状态值 |
| `updated_at` | `TEXT` | 否 | 无 |  | 最后更新时间 |

### 3.3 `data_migration_sources`

用途：记录参与初次迁移的 JSON/TXT 文件，以便追溯来源及校验内容。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `source_path` | `TEXT` | 否 | 无 | 主键 | 旧数据源文件的绝对路径 |
| `sha256` | `TEXT` | 否 | 无 |  | 文件内容的 SHA-256 哈希 |
| `imported_at` | `TEXT` | 否 | 无 |  | 导入数据库的时间 |

## 4. 词库表

### 4.1 `libraries`

用途：保存词库主体信息。每个词库中的具体词条保存在 `library_items`。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 词库唯一标识 |
| `subject` | `TEXT` | 否 | 无 |  | 所属科目，例如 `english`、`chinese` |
| `name` | `TEXT` | 否 | 无 | 唯一 | 词库名称 |
| `legacy_file_name` | `TEXT` | 是 | `NULL` | 唯一 | 迁移前对应的 TXT 文件名，不含扩展名 |
| `library_type` | `TEXT` | 是 | `NULL` |  | 词库类型 |
| `enabled` | `INTEGER` | 否 | 无 | 仅允许 `0` 或 `1` | 是否启用 |
| `archived` | `INTEGER` | 否 | 无 | 仅允许 `0` 或 `1` | 是否归档 |
| `created_at` | `TEXT` | 否 | 无 |  | 创建时间 |
| `updated_at` | `TEXT` | 否 | 无 |  | 更新时间 |
| `archived_at` | `TEXT` | 是 | `NULL` |  | 归档时间 |
| `extra_json` | `TEXT` | 否 | `'{}'` |  | 未独立拆列的扩展属性 |

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_libraries_subject_status` | `subject`, `archived`, `enabled` | 按科目和启用/归档状态筛选词库 |

### 4.2 `library_items`

用途：将词库中的每一个词、短语或内容保存为独立数据库记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `INTEGER` | 否 | 自动生成 | 主键、自增 | 词条内部编号 |
| `library_id` | `TEXT` | 否 | 无 | 外键 | 所属词库 ID，关联 `libraries.id` |
| `content` | `TEXT` | 否 | 无 |  | 词条原始内容 |
| `normalized_content` | `TEXT` | 否 | 无 |  | 去除首尾空白并执行大小写归一化后的内容 |
| `sort_order` | `INTEGER` | 否 | 无 | 与 `library_id` 联合唯一 | 词条在词库中的顺序，从 `0` 开始 |
| `created_at` | `TEXT` | 否 | 无 |  | 创建时间 |
| `updated_at` | `TEXT` | 否 | 无 |  | 更新时间 |

关系与级联：

- `library_items.library_id` -> `libraries.id`
- 删除词库时，其全部词条通过 `ON DELETE CASCADE` 自动删除。
- `library_id + sort_order` 唯一，保证同一词库内每个排序位置只有一条记录。

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_library_items_lookup` | `library_id`, `normalized_content` | 在指定词库中快速查找归一化词条 |

## 5. 技能表

### 5.1 `skill_sections`

用途：保存原技能文件对应的模块/分区元数据，也是 `skills` 的父表。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `source_file` | `TEXT` | 否 | 无 | 主键 | 迁移前的技能来源文件名 |
| `module` | `TEXT` | 是 | `NULL` |  | 模块标识 |
| `section` | `TEXT` | 是 | `NULL` |  | 分区标识 |
| `title` | `TEXT` | 是 | `NULL` |  | 分区标题 |
| `enabled` | `INTEGER` | 否 | `1` |  | 是否启用 |
| `sort_order` | `INTEGER` | 否 | `0` |  | 分区排序位置 |
| `index_entry_json` | `TEXT` | 否 | `'{}'` |  | 原技能索引中的完整条目 |
| `source_metadata_json` | `TEXT` | 否 | `'{}'` |  | 原技能源文件中除技能列表外的元数据 |

### 5.2 `skills`

用途：保存每一条可选择或用于出题的技能记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 技能唯一标识 |
| `source_file` | `TEXT` | 否 | 无 | 外键 | 来源分区，关联 `skill_sections.source_file` |
| `module` | `TEXT` | 是 | `NULL` |  | 模块 |
| `section` | `TEXT` | 是 | `NULL` |  | 分区 |
| `grade` | `TEXT` | 是 | `NULL` |  | 年级 |
| `topic` | `TEXT` | 是 | `NULL` |  | 主题 |
| `skill` | `TEXT` | 是 | `NULL` |  | 技能名称 |
| `detail` | `TEXT` | 是 | `NULL` |  | 技能详细描述 |
| `difficulty` | `TEXT` | 是 | `NULL` |  | 难度 |
| `enabled` | `INTEGER` | 否 | `1` |  | 是否启用 |
| `sort_order` | `INTEGER` | 否 | `0` |  | 在来源文件中的排序位置 |
| `extra_json` | `TEXT` | 否 | `'{}'` |  | 未独立拆列的扩展属性 |

关系与级联：

- `skills.source_file` -> `skill_sections.source_file`
- 删除技能分区时，其技能通过 `ON DELETE CASCADE` 自动删除。

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_skills_filters` | `module`, `section`, `grade`, `topic`, `skill`, `enabled`, `sort_order` | 支持技能多维筛选和排序 |

### 5.3 `skill_question_types`

用途：保存技能所支持的题型。数组中的每一项都是独立记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `skill_id` | `TEXT` | 否 | 无 | 联合主键、外键 | 所属技能，关联 `skills.id` |
| `position` | `INTEGER` | 否 | 无 | 联合主键 | 题型在数组中的位置 |
| `value` | `TEXT` | 否 | 无 |  | 题型值 |

关系与级联：

- 主键为 `skill_id + position`。
- 删除技能时，其题型通过 `ON DELETE CASCADE` 自动删除。

### 5.4 `skill_tags`

用途：保存技能标签。数组中的每一个标签都是独立记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `skill_id` | `TEXT` | 否 | 无 | 联合主键、外键 | 所属技能，关联 `skills.id` |
| `position` | `INTEGER` | 否 | 无 | 联合主键 | 标签在数组中的位置 |
| `value` | `TEXT` | 否 | 无 |  | 标签内容 |

关系与级联：

- 主键为 `skill_id + position`。
- 删除技能时，其标签通过 `ON DELETE CASCADE` 自动删除。

## 6. 练习报告表

### 6.1 `practice_reports`

用途：保存练习报告主体、时间、模块和答题汇总。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 报告唯一标识 |
| `position` | `INTEGER` | 否 | 无 |  | 报告在历史记录中的排序位置 |
| `created_at` | `TEXT` | 是 | `NULL` |  | 报告创建时间 |
| `report_date` | `TEXT` | 是 | `NULL` |  | 报告日期 |
| `module` | `TEXT` | 是 | `NULL` |  | 练习模块标识 |
| `module_label` | `TEXT` | 是 | `NULL` |  | 练习模块显示名称 |
| `total_count` | `INTEGER` | 是 | `NULL` |  | 总题数 |
| `correct_count` | `INTEGER` | 是 | `NULL` |  | 正确题数 |
| `payload_json` | `TEXT` | 否 | 无 |  | 报告完整原始数据，用于无损兼容 |

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_practice_reports_history` | `module`, `created_at DESC` | 按模块和创建时间倒序查询历史报告 |

### 6.2 `practice_report_items`

用途：保存练习报告中的明细列表，每个答题明细为独立记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `report_id` | `TEXT` | 否 | 无 | 联合主键、外键 | 所属报告，关联 `practice_reports.id` |
| `position` | `INTEGER` | 否 | 无 | 联合主键 | 明细在报告中的位置 |
| `payload_json` | `TEXT` | 否 | 无 |  | 单条明细的完整数据 |

关系与级联：

- 主键为 `report_id + position`。
- 删除报告时，其全部明细通过 `ON DELETE CASCADE` 自动删除。

### 6.3 `generation_jobs`

用途：保存 Word Palace 异步出题任务。接口先创建任务并立即返回任务 ID；后台按批次生成题目，前端取得首批 3 题后即可开始答题。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 任务 ID |
| `kind` | `TEXT` | 否 | 无 |  | 任务类型，例如每日单词或词汇技能 |
| `status` | `TEXT` | 否 | 无 |  | 任务状态 |
| `requested_count` | `INTEGER` | 否 | 无 |  | 请求生成的题目总数 |
| `generated_count` | `INTEGER` | 否 | `0` |  | 已持久化的题目数 |
| `request_json` | `TEXT` | 否 | 无 |  | 创建任务时的请求参数 |
| `plan_json` | `TEXT` | 否 | 无 |  | 后台分批生成计划 |
| `metadata_json` | `TEXT` | 否 | `'{}'` |  | 任务元数据及生成上下文 |
| `questions_json` | `TEXT` | 否 | `'[]'` |  | 已生成题目数组；每批完成后追加保存 |
| `error` | `TEXT` | 是 | `NULL` |  | 失败或部分失败时的错误信息 |
| `created_at` | `TEXT` | 否 | 无 |  | 创建时间 |
| `updated_at` | `TEXT` | 否 | 无 |  | 最后进度更新时间 |
| `expires_at` | `TEXT` | 否 | 无 |  | 任务过期时间，用于清理临时任务 |

任务状态：

- `queued`：已入队，尚未开始生成。
- `generating`：后台正在生成；已有题目可被前端读取和作答。
- `completed`：请求数量已全部生成。
- `partial_failed`：后续批次失败，但保留并返回已经生成的题目。
- `failed`：首批即失败，没有可用题目。
- `cancelled`：用户取消任务，后台停止后续批次。

首批固定生成 3 题，后续批次在后台继续。任务和题目进度保存在 SQLite 中，因此 Gunicorn 多 worker 可读取同一状态；任务超时及过期机制可防止前端无限 loading。

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_generation_jobs_expiry` | `expires_at` | 查找并清理过期生成任务 |

## 7. 模型设置表

### 7.1 `model_settings`

用途：保存系统当前选用的模型。该表设计为全局单例，只允许存在 `id = 1`。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `INTEGER` | 否 | 无 | 主键，仅允许 `1` | 单例记录 ID |
| `selected_model` | `TEXT` | 是 | `NULL` |  | 当前选择的模型名称 |
| `updated_at` | `TEXT` | 是 | `NULL` |  | 最后更新时间 |

## 8. Todo 表

### 8.1 `todo_settings`

用途：保存 Todo 模块的全局设置。该表设计为全局单例，只允许存在 `id = 1`。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `INTEGER` | 否 | 无 | 主键，仅允许 `1` | 单例记录 ID |
| `timezone` | `TEXT` | 否 | 无 |  | Todo 使用的时区 |
| `recurrence_horizon_days` | `INTEGER` | 否 | 无 |  | 重复任务向未来生成的天数范围 |
| `backup_retention` | `INTEGER` | 否 | 无 |  | 备份保留数量 |
| `updated_at` | `TEXT` | 是 | `NULL` |  | 最后更新时间 |
| `extra_json` | `TEXT` | 否 | `'{}'` |  | 未独立拆列的设置项 |

### 8.2 `todo_subjects`

用途：保存 Todo 任务所属科目。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 科目唯一标识 |
| `name` | `TEXT` | 否 | 无 |  | 科目名称 |
| `color` | `TEXT` | 否 | 无 |  | 科目显示颜色 |
| `sort_order` | `INTEGER` | 否 | 无 |  | 科目排序位置 |
| `enabled` | `INTEGER` | 否 | 无 | 仅允许 `0` 或 `1` | 是否启用 |
| `payload_json` | `TEXT` | 否 | 无 |  | 科目完整原始数据，用于无损兼容 |

### 8.3 `todo_templates`

用途：保存用于生成 Todo 任务的单次或重复任务模板。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 模板唯一标识 |
| `subject_id` | `TEXT` | 否 | 无 | 外键 | 所属科目，关联 `todo_subjects.id` |
| `title` | `TEXT` | 否 | 无 |  | 模板标题 |
| `start_date` | `TEXT` | 是 | `NULL` |  | 模板生效日期 |
| `end_date` | `TEXT` | 是 | `NULL` |  | 模板结束日期 |
| `repeat_kind` | `TEXT` | 否 | 无 |  | 重复类型，例如单次或按星期重复 |
| `active` | `INTEGER` | 否 | 无 | 仅允许 `0` 或 `1` | 模板是否生效 |
| `payload_json` | `TEXT` | 否 | 无 |  | 模板完整数据，不包含已拆分的重复星期数组 |

关系：

- `todo_templates.subject_id` -> `todo_subjects.id`
- 此外键未设置级联删除；存在模板时不能直接删除关联科目。

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_todo_templates_active` | `active`, `start_date`, `end_date` | 按启用状态和日期范围筛选模板 |

### 8.4 `todo_template_weekdays`

用途：保存重复任务模板选择的星期。一周中的每个选中日为独立记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `template_id` | `TEXT` | 否 | 无 | 联合主键、外键 | 所属模板，关联 `todo_templates.id` |
| `position` | `INTEGER` | 否 | 无 | 联合主键 | 星期值在模板数组中的顺序 |
| `weekday` | `INTEGER` | 否 | 无 |  | 星期编号 |

关系与级联：

- 主键为 `template_id + position`。
- 删除模板时，其星期设置通过 `ON DELETE CASCADE` 自动删除。

### 8.5 `todo_tasks`

用途：保存已经生成并展示在日历中的实际 Todo 任务。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 任务唯一标识 |
| `position` | `INTEGER` | 否 | 无 |  | 任务在所属月份数据中的排序位置 |
| `subject_id` | `TEXT` | 否 | 无 | 外键 | 所属科目，关联 `todo_subjects.id` |
| `template_id` | `TEXT` | 是 | `NULL` | 外键 | 来源模板，关联 `todo_templates.id`；手动任务可以为空 |
| `title` | `TEXT` | 否 | 无 |  | 任务标题 |
| `planned_date` | `TEXT` | 否 | 无 |  | 计划完成日期 |
| `lifecycle_status` | `TEXT` | 否 | 无 |  | 任务生命周期状态 |
| `completed_at` | `TEXT` | 是 | `NULL` |  | 实际完成时间 |
| `payload_json` | `TEXT` | 否 | 无 |  | 任务完整数据，不包含已拆分的历史数组 |

关系：

- `todo_tasks.subject_id` -> `todo_subjects.id`
- `todo_tasks.template_id` -> `todo_templates.id`
- 两个外键均未设置级联删除，以防误删科目或模板后破坏历史任务。

索引：

| 索引名 | 字段 | 用途 |
| --- | --- | --- |
| `idx_todo_tasks_calendar` | `planned_date`, `lifecycle_status`, `subject_id` | 按日期、状态及科目查询日历任务 |

### 8.6 `todo_task_history`

用途：保存每个 Todo 任务的状态变化或操作历史。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `task_id` | `TEXT` | 否 | 无 | 联合主键、外键 | 所属任务，关联 `todo_tasks.id` |
| `position` | `INTEGER` | 否 | 无 | 联合主键 | 事件在任务历史中的位置 |
| `event_type` | `TEXT` | 否 | 无 |  | 事件类型 |
| `event_at` | `TEXT` | 是 | `NULL` |  | 事件发生时间 |
| `details_json` | `TEXT` | 否 | `'{}'` |  | 事件中除类型和时间外的详细数据 |

关系与级联：

- 主键为 `task_id + position`。
- 删除任务时，其历史记录通过 `ON DELETE CASCADE` 自动删除。

### 8.7 `todo_reports`

用途：保存 Todo 模块生成的报告。每份报告为独立记录。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `record_key` | `TEXT` | 否 | 无 | 主键 | 报告 ID；无原始 ID 时由内容生成稳定键 |
| `position` | `INTEGER` | 否 | 无 |  | 报告排序位置 |
| `payload_json` | `TEXT` | 否 | 无 |  | 报告完整数据 |

### 8.8 `points_ledger`

用途：保存积分增加或扣减流水。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `record_key` | `TEXT` | 否 | 无 | 主键 | 流水 ID；无原始 ID 时由内容生成稳定键 |
| `position` | `INTEGER` | 否 | 无 |  | 流水排序位置 |
| `transaction_type` | `TEXT` | 否 | 无 |  | 流水类型，例如获得或消费 |
| `points` | `INTEGER` | 否 | 无 |  | 积分数量 |
| `purpose` | `TEXT` | 否 | 无 |  | 积分用途或原因 |
| `created_at` | `TEXT` | 是 | `NULL` |  | 流水创建时间 |
| `payload_json` | `TEXT` | 否 | 无 |  | 流水完整原始数据 |

## 9. Book Reading 表

### 9.1 `reading_books`

用途：保存 Admin 上传的 PDF 书籍、可选封面、解析状态和孩子端发布状态。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 书籍 ID |
| `title` | `TEXT` | 否 | 无 |  | 书名 |
| `author` | `TEXT` | 否 | `''` |  | 作者 |
| `description` | `TEXT` | 否 | `''` |  | 给孩子的简介 |
| `age_level` | `TEXT` | 否 | `''` |  | 适读年龄或年级 |
| `language` | `TEXT` | 否 | `'English'` |  | 书籍语言 |
| `pdf_asset` | `TEXT` | 否 | 无 |  | 原始 PDF 的服务器路径，不通过公开接口暴露 |
| `cover_asset` | `TEXT` | 是 | `NULL` |  | 可选封面路径 |
| `pdf_sha256` | `TEXT` | 否 | 无 | 唯一 | PDF 内容哈希，用于阻止重复上传 |
| `page_count` | `INTEGER` | 否 | 无 |  | PDF 总页数 |
| `status` | `TEXT` | 否 | 无 | `draft/published/archived` | 发布状态 |
| `extraction_status` | `TEXT` | 否 | 无 |  | `ready` 或 `needs_ocr` |
| `created_at` | `TEXT` | 否 | 无 |  | 创建时间 |
| `updated_at` | `TEXT` | 否 | 无 |  | 更新时间 |
| `extra_json` | `TEXT` | 否 | `'{}'` |  | 可读字符数等扩展信息 |

### 9.2 `reading_chapters`

用途：保存从 PDF 书签、章节标题或模型识别出的目录。Admin 修改页码后会重新提取对应页文字。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 章节 ID |
| `book_id` | `TEXT` | 否 | 无 | 外键 | 关联 `reading_books.id` |
| `title` | `TEXT` | 否 | 无 |  | 章节名称 |
| `start_page` | `INTEGER` | 否 | 无 |  | PDF 起始页 |
| `end_page` | `INTEGER` | 否 | 无 |  | PDF 结束页 |
| `sort_order` | `INTEGER` | 否 | 无 | 与 `book_id` 联合唯一 | 章节顺序 |
| `detection_source` | `TEXT` | 否 | 无 |  | `pdf_outline/page_heading/ai_detected/admin/fallback` |
| `confidence` | `REAL` | 否 | `0` |  | 自动识别置信度 |
| `content_text` | `TEXT` | 否 | `''` |  | 带 PDF 页码标记的章节文字，供问题生成使用 |
| `extra_json` | `TEXT` | 否 | `'{}'` |  | 扩展信息 |

### 9.3 `reading_sessions`

用途：保存一次选定章节的引导式阅读过程及最终理解评估。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 阅读记录 ID |
| `access_token_hash` | `TEXT` | 否 | 无 |  | 孩子端随机访问凭证的 SHA-256；不保存原凭证 |
| `book_id` | `TEXT` | 否 | 无 | 外键 | 关联书籍 |
| `chapter_ids_json` | `TEXT` | 否 | 无 |  | 所选章节 ID 列表 |
| `status` | `TEXT` | 否 | 无 | `active/completed/abandoned` | 进度状态 |
| `question_count` | `INTEGER` | 否 | 无 |  | 本次问题数 |
| `overall_level` | `TEXT` | 是 | `NULL` |  | `clear/mostly_clear/needs_support` |
| `student_summary` | `TEXT` | 是 | `NULL` |  | 孩子可见总结 |
| `parent_summary` | `TEXT` | 是 | `NULL` |  | 仅 Admin 可见总结 |
| `evaluation_json` | `TEXT` | 否 | `'{}'` |  | 优势、回看重点和建议 |
| `created_at` | `TEXT` | 否 | 无 |  | 开始时间 |
| `updated_at` | `TEXT` | 否 | 无 |  | 最近互动时间 |
| `completed_at` | `TEXT` | 是 | `NULL` |  | 完成时间 |

### 9.4 `reading_session_questions`

用途：保存每道开放问题、孩子回答、最多一次追问、即时反馈及家长侧评估依据。

| 字段 | 类型 | 可空 | 默认值 | 键/约束 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `id` | `TEXT` | 否 | 无 | 主键 | 问题 ID |
| `session_id` | `TEXT` | 否 | 无 | 外键 | 关联阅读记录 |
| `position` | `INTEGER` | 否 | 无 | 与 `session_id` 联合唯一 | 问题顺序 |
| `question_text` | `TEXT` | 否 | 无 |  | 给孩子的问题 |
| `question_type` | `TEXT` | 否 | 无 |  | 回忆、推理、因果、联系或预测等 |
| `purpose` | `TEXT` | 否 | `''` |  | 评估目的 |
| `reference_answer` | `TEXT` | 否 | `''` |  | 仅 Admin/模型使用的参考理解 |
| `evidence_json` | `TEXT` | 否 | `'[]'` |  | PDF 页码与短证据 |
| `child_answer` | `TEXT` | 是 | `NULL` |  | 孩子的原始答案文字 |
| `input_mode` | `TEXT` | 是 | `NULL` |  | `text` 或 `voice`；语音原文件不保存 |
| `feedback` | `TEXT` | 是 | `NULL` |  | 首次回答的即时反馈 |
| `understanding_level` | `TEXT` | 是 | `NULL` |  | 本题理解层级 |
| `parent_note` | `TEXT` | 是 | `NULL` |  | 仅 Admin 可见备注 |
| `follow_up_question` | `TEXT` | 是 | `NULL` |  | 可选的一次引导追问 |
| `follow_up_answer` | `TEXT` | 是 | `NULL` |  | 追问答案 |
| `follow_up_feedback` | `TEXT` | 是 | `NULL` |  | 追问反馈 |
| `answered_at` | `TEXT` | 是 | `NULL` |  | 本题及必要追问完成时间 |
| `extra_json` | `TEXT` | 否 | `'{}'` |  | 扩展信息 |

## 10. 表关系总览

| 父表 | 子表 | 外键 | 删除父记录时的行为 |
| --- | --- | --- | --- |
| `libraries` | `library_items` | `library_items.library_id` | 级联删除词条 |
| `skill_sections` | `skills` | `skills.source_file` | 级联删除技能 |
| `skills` | `skill_question_types` | `skill_question_types.skill_id` | 级联删除题型 |
| `skills` | `skill_tags` | `skill_tags.skill_id` | 级联删除标签 |
| `practice_reports` | `practice_report_items` | `practice_report_items.report_id` | 级联删除报告明细 |
| `todo_subjects` | `todo_templates` | `todo_templates.subject_id` | 阻止删除仍被引用的科目 |
| `todo_subjects` | `todo_tasks` | `todo_tasks.subject_id` | 阻止删除仍被引用的科目 |
| `todo_templates` | `todo_template_weekdays` | `todo_template_weekdays.template_id` | 级联删除星期设置 |
| `todo_templates` | `todo_tasks` | `todo_tasks.template_id` | 阻止删除仍被引用的模板 |
| `todo_tasks` | `todo_task_history` | `todo_task_history.task_id` | 级联删除任务历史 |
| `reading_books` | `reading_chapters` | `reading_chapters.book_id` | 级联删除章节 |
| `reading_books` | `reading_sessions` | `reading_sessions.book_id` | 阻止删除仍有历史记录的书籍 |
| `reading_sessions` | `reading_session_questions` | `reading_session_questions.session_id` | 级联删除逐题记录 |

## 11. 索引总览

除主键和唯一约束自动产生的 SQLite 索引外，Schema 显式定义了以下索引：

| 索引名 | 表 | 字段 |
| --- | --- | --- |
| `idx_libraries_subject_status` | `libraries` | `subject`, `archived`, `enabled` |
| `idx_library_items_lookup` | `library_items` | `library_id`, `normalized_content` |
| `idx_skills_filters` | `skills` | `module`, `section`, `grade`, `topic`, `skill`, `enabled`, `sort_order` |
| `idx_practice_reports_history` | `practice_reports` | `module`, `created_at DESC` |
| `idx_generation_jobs_expiry` | `generation_jobs` | `expires_at` |
| `idx_todo_templates_active` | `todo_templates` | `active`, `start_date`, `end_date` |
| `idx_todo_tasks_calendar` | `todo_tasks` | `planned_date`, `lifecycle_status`, `subject_id` |
| `idx_reading_books_status` | `reading_books` | `status`, `updated_at DESC` |
| `idx_reading_chapters_book` | `reading_chapters` | `book_id`, `sort_order` |
| `idx_reading_sessions_history` | `reading_sessions` | `created_at DESC`, `book_id` |
| `idx_reading_questions_session` | `reading_session_questions` | `session_id`, `position` |

## 12. 数据完整性规则

- 数据库连接启用 `PRAGMA foreign_keys = ON`，因此外键和级联规则会实际生效。
- 数据库使用 WAL 日志模式，写入事务使用 `BEGIN IMMEDIATE`。
- `enabled`、`archived`、`active` 等关键布尔字段通过 `CHECK` 约束限制为 `0` 或 `1`；`skill_sections.enabled` 与 `skills.enabled` 目前只有默认值，没有 `CHECK` 约束。
- 词库名称 `libraries.name` 全局唯一。
- 旧词库文件名 `libraries.legacy_file_name` 在非空时全局唯一。
- 单例设置表通过 `CHECK(id = 1)` 保证最多只有一条有效配置记录。
- 所有父子表的顺序型数据均通过 `position` 或 `sort_order` 保留原 JSON 数组顺序。
- 异步生成任务的状态、进度和题目通过事务写入统一 SQLite 数据库，可由多个应用 worker 安全共享。
- Book Reading 的 PDF、封面和 SQLite 记录都位于 `data/` 范围内，会被现有全量快照与清单校验保护；原始语音不写入服务器磁盘。
