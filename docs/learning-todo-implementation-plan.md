# Jingsen Learning Center「Learning Todo」架构评审与实施计划

> 状态：已完成实现，待 Review（已按 2026-07-28 决策取消 Todo 独立家长密码）
> 评审范围：现有架构适配、业务规则补全、数据与接口设计、实施顺序、测试与上线方案
> 本文记录最终方案、已实现口径与验收标准。

## 1. 结论摘要

Learning Todo 可以继续使用当前项目的 FastAPI、静态 HTML + Tailwind CSS + 原生 JavaScript、腾讯云宝塔/Nginx/Gunicorn 和本地 JSON 持久化方式，不需要引入独立 App、前端框架、数据库或完整账号体系。

整体适配度为“高”。Todo 管理直接作为现有 Admin 的一个栏目，不增加 Todo 独立密码、家长会话、二次验证、退出入口或密码设置。

实现中已处理一个关键技术前置条件：

1. **Todo JSON 写入必须使用跨进程文件锁。**
   Todo 存储同时使用线程锁和 `fcntl` 文件锁，适配 Gunicorn 多 worker；JSON 通过同目录临时文件、`fsync` 和 `os.replace` 原子替换。

Todo 继续沿用当前 Admin 的入口和访问方式：通过门户现有 Admin 密码进入 Admin 首页，再直接点击“Todo 管理”。本功能不单独改造现有 Admin 鉴权。Todo 数据使用独立目录、月份文件、跨进程锁、原子写入、版本号、修改历史和备份清单。

现有 Admin 密码保持不变，但验证已移到服务端，并使用 HMAC 签名的 HttpOnly Cookie 维持 Admin 会话。Todo 管理复用该会话，不增加第二套密码；`/api/admin/todo/*` 同时执行服务端 Admin 会话校验。

## 2. 当前架构与适配情况

| 领域 | 当前实现 | 适配结论 |
|---|---|---|
| 后端 | FastAPI 单体应用，API 按模块拆分 | 适合新增 `todo` 和 `admin_todo` 路由 |
| 前端 | 静态 HTML、Tailwind CDN、原生 JS | 适合新增孩子 H5 和 Admin Todo 页面，不需构建链 |
| 路由 | 根路径和 `/learningcenter` 前缀同时注册 | 新页面和 API 必须继续双路径验证 |
| Admin 入口 | 保留现有门户密码弹窗 | 密码改由服务端校验，Admin 首页增加 Todo 入口 |
| Admin API | 原 `/api/admin/*` 无统一鉴权依赖 | Todo 管理 API 复用新的 Admin 服务端会话，不新增第二套密码 |
| JSON 存储 | `data/` 下 JSON/TXT，部分服务原子替换 | 可复用思路，但要补跨进程锁、校验、版本与备份 |
| 生产部署 | 宝塔 + Nginx + Gunicorn，线上 `data/` 会在更新前备份 | 新 Todo 目录可被现有数据备份流程覆盖 |
| 时区 | 多处使用无时区的 `datetime.now()` | Todo 必须独立使用 `Asia/Shanghai` 和 UTC 时间戳 |
| 测试 | 仓库没有正式自动化测试目录 | Todo 的日期、重复任务、统计和并发风险要求新增测试 |

### 2.1 可以直接复用的部分

- `config.DATA_DIR` 和线上 `data/` 保留机制。
- `APIRouter -> service -> JSON` 的模块分层。
- `temp file + os.replace` 的原子替换思路。
- 页面根据 `window.location.pathname` 处理 `/learningcenter` 前缀的方式。
- Admin 首页卡片式入口和现有视觉语言。
- FastAPI/Pydantic 的请求校验和响应模型。

### 2.2 Todo 实现中不应直接复用的部分

- 只使用 `threading.RLock` 的写入保护。
- 读取损坏 JSON 后静默返回空数据的方式。Todo 数据不能把“损坏”误判成“没有任务”。
- 无时区的本地时间计算。
- 把用户输入直接拼进 `innerHTML`。任务名称和说明必须用 `textContent` 或统一转义，避免持久化 XSS。

Todo 页面不复制密码逻辑，也不增加 Todo 专用密码；管理接口统一复用 Admin 服务端会话。

## 3. 推荐目标架构

```text
Portal / Admin 首页
    ├── /todo                         孩子 H5
    │     └── /api/todo/*             公共只读 + 完成/取消完成
    │
    └── 现有 Admin 密码
          └── 现有 Admin 首页
                └── Todo 管理按钮
                      ├── /admin/todo
                      └── /api/admin/todo/*

FastAPI
    ├── api/todo.py
    ├── api/admin_todo.py
    ├── models/todo_schemas.py
    └── services/learning_todo/
          ├── storage.py
          ├── task_service.py
          ├── recurrence_service.py
          ├── calendar_service.py
          ├── statistics_service.py
          └── backup_service.py

data/learning-todo/
    ├── learning-todo-settings.json
    ├── learning-todo-subjects.json
    ├── learning-todo-templates.json
    ├── learning-todo-tasks/
    │     └── YYYY-MM.json
    ├── learning-todo-reports/
    ├── learning-todo-backups/
    └── .learning-todo.lock
```

使用独立 `data/learning-todo/` 目录是对原需求建议结构的小调整，原因是：

- 不与现有词库、Skills、Daily Reports 文件混在一起。
- 备份、恢复、格式校验和权限设置可以限定在一个目录。
- 现有 `update_safe.sh` 已备份整个 `data/`，无需另建部署体系。
- 备份时需排除 `learning-todo-backups/` 自身，避免递归膨胀。

### 3.1 Todo 数据隔离约束

Todo 存储必须遵守以下硬性边界：

- Todo 服务只允许读写 `data/learning-todo/` 及其子目录。
- 不复用、不迁移、不修改 `data/library_registry.json`。
- 不修改现有 `data/*.txt` 词库文件。
- 不复用、不修改 `data/report_history.json`；Todo 完成记录和 Word Palace、Vocabulary Skills、MAP 等练习完成记录完全分开。
- 不修改 `data/skills/index.json` 或任何 `data/skills/*.json`。
- Todo 的科目是独立业务数据，不引用或改写现有词库、Skills 的学科字段。
- Todo 的周/月统计与评语只保存在 `data/learning-todo/learning-todo-reports/`，不写入现有 Daily Reports。
- Todo 备份只打包 `data/learning-todo/`，不在模块内部恢复或覆盖其他 `data/` 文件。
- 所有 Todo 存储路径由一个固定的 storage root 生成；API 和业务服务不得自行拼接到 `config.DATA_DIR` 下的其他路径。

目录名、文件名和 JSON 顶层 schema 均使用 `learning-todo` 命名空间，任务 ID、科目 ID、模板 ID 分别使用 `task_`、`sub_`、`tpl_` 前缀，避免和现有数据 ID 混淆。

## 4. 入口与访问边界

### 4.1 已确认的 Admin 行为

- 现有门户 Admin 卡片、密码弹窗和进入方式保持不变。
- `static/admin.html` 增加“Todo 管理”入口，与“词库管理”“Skills 管理”同级。
- 点击后直接进入 `/admin/todo`，不再输入任何密码。
- `/admin/todo` 不提供单独退出、修改密码或会话设置。
- Todo 管理 API 使用 `/api/admin/todo/*` 命名，并校验同一 Admin 服务端会话。

### 4.2 入口行为

| 场景 | 行为 |
|---|---|
| 从门户正常进入 Admin | 输入现有 Admin 密码并进入当前 Admin 首页 |
| 在 Admin 点击 Todo 管理 | 直接进入 `/admin/todo` |
| 刷新 `/admin/todo` | Admin 会话有效时直接刷新，不进行二次验证 |
| 从 Todo 管理返回 | 返回现有 `/admin` 首页 |
| 直接访问 `/admin/todo` | 页面可加载；管理数据 API 在没有 Admin 会话时返回 401 |

### 4.3 访问边界

- Admin 密码不再保存在 Todo 前端，也不由浏览器直接比较。
- Todo 管理接口要求有效的 Admin HttpOnly 会话。
- 孩子页面也按需求不设密码，知道地址的人可以查看任务并调用完成接口。
- 公共孩子响应仍必须严格排除家长备注、历史详情和管理字段。
- 若以后继续强化安全，应把统一 Admin 会话扩展到所有遗留 Admin 接口；不要恢复 Todo 专用密码。

## 5. 领域模型

### 5.1 科目

```json
{
  "id": "sub_xxx",
  "name": "英语",
  "color": "#3B82F6",
  "sort_order": 10,
  "enabled": true,
  "created_at": "2026-07-28T08:00:00Z",
  "updated_at": "2026-07-28T08:00:00Z",
  "version": 1
}
```

首次启动且科目文件不存在时，写入英语、数学、中文、阅读、科学、其他六个默认科目。停用科目后：

- 历史任务继续显示原科目和颜色。
- 新建任务默认不能选择该科目。
- 不能物理删除已被任务引用的科目。

### 5.2 任务实例

```json
{
  "id": "task_xxx",
  "title": "完成英语回家作业",
  "subject_id": "sub_english",
  "description": "完成第 18 页",
  "parent_note": "注意检查拼写",
  "planned_date": "2026-07-27",
  "lifecycle_status": "active",
  "completed_at": "2026-07-28T10:15:30Z",
  "completed_local_date": "2026-07-28",
  "completed_by": "child",
  "cancelled_at": null,
  "voided_at": null,
  "recurrence": {
    "template_id": "tpl_xxx",
    "occurrence_key": "2026-07-27",
    "template_revision": 2
  },
  "created_at": "2026-07-20T01:00:00Z",
  "updated_at": "2026-07-28T10:15:30Z",
  "version": 3,
  "history": []
}
```

设计原则：

- 文件归属月份按当前 `planned_date` 决定；跨月改期时在全局锁内移动文件。
- `parent_note` 只在家长接口返回。
- 每次创建、编辑、完成、撤销、改期、取消、作废都向 `history` 追加事件。
- API 更新必须提交 `expected_version`；版本不一致返回 `409 Conflict`，避免多个标签页互相覆盖。
- 任务 ID 使用不可预测的 UUID，不使用连续数字。

### 5.3 状态不直接存“逾期”

持久化只保存生命周期和完成事实：

- `lifecycle_status`: `active | cancelled | voided`
- `completed_at`: 可空
- `completed_local_date`: 可空

接口根据查询日期返回计算状态：

- `pending`：计划日期为今天或未来、未完成。
- `completed`：已完成。
- `overdue`：计划日期早于今天、未完成且仍有效。
- `cancelled`：家长明确免除任务。
- `voided`：任务记录有误，软删除。

这样不需要每天午夜批量把任务改成“逾期”，也不会产生日期切换写入竞态。

### 5.4 取消与作废

计划默认采用以下语义：

- **取消**：任务曾经有效，但家长决定不再要求完成。
- **作废**：任务本身创建错误，相当于软删除。
- 两者都保留历史，默认不进入完成率分母。
- 取消/作废发生之前已经形成的历史黄色日期不回写成绿色。
- 家长任务历史中可以筛选和查看两种状态。

如果业务希望“已取消仍计入计划任务总数”，需要在实现前调整统计口径。

## 6. 重复任务设计

### 6.1 模板结构

模板保存：

- 名称、科目、说明、家长备注。
- `frequency`: `daily | weekly | monthly`。
- 每周规则：星期一至星期日数组。
- 每月规则：1–31 或 `last_day`。
- 开始日期。
- 可选结束日期；为空表示长期。
- 启用状态、模板版本、创建/更新时间。

“自定义多个星期”归入 weekly + 多个 weekday，不单独创建第四种频率。

### 6.2 实例生成

- 不为“长期重复”一次性生成无限数据。
- 创建模板时生成近期实例；每次查询日/周/月范围前，确保目标范围内实例已经物化。
- 生成过程持有跨进程锁，并以 `(template_id, occurrence_key)` 去重，多次查询不会重复创建。
- 每个实例都有独立任务 ID、完成时间、状态、版本和历史。
- 逾期实例不会被下一次重复实例覆盖。
- 月末规则按当月实际最后一天计算，覆盖闰年。

### 6.3 三种修改范围

| 操作 | 实现规则 |
|---|---|
| 仅修改本次 | 修改当前实例并记录模板例外，不改其他实例 |
| 修改本次及以后 | 原模板在本次前一天结束，从本次日期创建后继模板；保留之前历史 |
| 修改整个重复计划 | 更新原模板；已完成/已取消/已作废历史实例不重写，未完成实例按新规则预览后重建 |

批量修改前必须：

- 展示受影响实例数和日期范围。
- 创建自动备份。
- 在同一全局文件锁内执行。
- 记录模板修改事件和新旧版本。

## 7. 日期、逾期、Grid 和统计口径

### 7.1 时间规则

- 业务时区固定为 `Asia/Shanghai`，配置项可见但首版不建议由 UI 随意修改。
- 所有时刻以带时区 UTC ISO 8601 保存。
- 所有“今天、原计划日期、实际完成日期”由后端按业务时区计算，不能依赖孩子设备的时区。
- 周从星期一开始，使用 ISO 周编号保存周评语。

### 7.2 孩子页面任务分组

`GET /api/todo/today` 一次返回服务端日期和四个区域所需数据：

1. 今日进度：只统计今天计划的有效任务。
2. 逾期任务：`planned_date < today`、未完成、未取消、未作废。
3. 今日待完成：`planned_date == today` 且未完成。
4. 今日已完成：`planned_date == today` 且已完成。

当天完成的历史逾期任务仍显示在任务结果中，但应标记“原计划日期”和“逾期完成”；UI 可在本次成功反馈后归入一个“今天完成的逾期任务”子组，避免任务突然消失造成困惑。

孩子完成任务后显示 **10 秒** 快捷撤销提示；此外，“今天已完成”中的每个任务始终提供手动取消完成操作，不受快捷提示时间限制。家长端也可以随时取消完成状态。

### 7.3 学习积分

孩子端积分由任务历史实时推导，不另存积分账本：

- 某个计划日的全部有效任务都在原计划日期当天完成，该日得分等于当前连续完成任务日数：首次 `1` 分、下一次连续完成 `2` 分、再下一次 `3` 分。
- 某个有计划任务的历史日期没有全部按时完成，该日为 `0` 分并中断连续记录；下一个全部按时完成的任务日从 `1` 分重新开始。
- 没有安排任务的日期为中性日：`0` 分，但不打断连续记录。
- 当天尚未结束且仍有待办时不提前清零，页面展示“今天全部完成可得 +N 分”；全部完成后才计分。
- 逾期补做不回补原计划日积分；取消完成会根据当前任务事实重新计算积分。
- 取消或作废的任务按其生效日期参与历史口径，不单独生成或修改其他业务数据。

孩子端积分卡片展示累计积分、当前连续完成任务日数、今天已获得或可争取分数。积分只读取 `data/learning-todo/tasks/*.json`，不会读写词库、Skills 或 Daily Reports。

### 7.4 历史日期 Grid

按某日 `D` 的日终事实计算：

1. `D > today`：白色或浅灰色。
2. 如果 `D` 日终仍存在 `planned_date <= D` 的未解决任务：黄色。
3. 如果 `D` 当天有有效计划任务，且当天任务全部按时完成，同时日终没有遗留逾期：绿色。
4. 没有当天计划任务，也没有日终遗留逾期：灰色。

由此得到：

- 7 月 27 日未完成，7 月 27 日为黄色。
- 7 月 28 日补做完成后，7 月 27 日仍为黄色。
- 如果 7 月 28 日自己的任务也全部完成，且日终没有其他逾期，7 月 28 日可以是绿色。
- 仅补做一项逾期但当天没有计划任务时，当日仍按“无计划任务”显示灰色，可附“完成逾期任务”标识，但不算绿色日期。

任务取消或作废需要使用其生效时间：生效前的历史黄色不被改写，生效后的日期不再把它当成遗留逾期。

### 7.5 周/月统计

统计以“原计划日期落在所选周期内的有效任务”为队列：

- 计划任务总数：周期内任务，排除取消和作废。
- 已完成数：上述任务中当前已完成的数量。
- 按时完成数：`completed_local_date == planned_date`。
- 逾期完成数：`completed_local_date > planned_date`。
- 当前未完成数：当前仍未完成的有效任务。
- 总体完成率：已完成数 / 计划任务总数。
- 按时完成率：按时完成数 / 计划任务总数。
- 分母为 0 时返回 `0` 和 `rate_applicable=false`，UI 显示 `—`，不显示误导性的 0%。

逾期任务在 8 月补做，但原计划日期是 7 月时：

- 归入 7 月计划任务统计。
- 7 月“已完成数”和“逾期完成数”会增加。
- 7 月对应日期 Grid 继续保持黄色。

周/月评语分别使用 `YYYY-Www` 和 `YYYY-MM` 作为键，和动态统计结果分开保存。

## 8. API 规划

所有 API 同时支持根路径和 `/learningcenter` 前缀。

### 8.1 公共孩子端

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/todo/today` | 今日进度、逾期、待完成、今日已完成 |
| GET | `/api/todo/reward` | 当前累计积分、连续完成任务日数和今日积分状态 |
| POST | `/api/todo/tasks/{task_id}/complete` | 幂等完成任务 |
| POST | `/api/todo/tasks/{task_id}/undo-completion` | 快捷撤销或手动取消已完成状态 |

公共接口不允许创建、编辑、删除、改期、读取统计、读取家长备注或读取任务完整历史。

### 8.2 Admin Todo 管理 API

按资源划分：

- `/api/admin/todo/overview`
- `/api/admin/todo/subjects`
- `/api/admin/todo/tasks`
- `/api/admin/todo/tasks/{id}`
- `/api/admin/todo/tasks/{id}/history`
- `/api/admin/todo/tasks/{id}/completion`
- `/api/admin/todo/tasks/copy-day`
- `/api/admin/todo/tasks/copy-week`
- `/api/admin/todo/templates`
- `/api/admin/todo/templates/{id}`
- `/api/admin/todo/calendar/day`
- `/api/admin/todo/calendar/week`
- `/api/admin/todo/calendar/month`
- `/api/admin/todo/statistics/week`
- `/api/admin/todo/statistics/month`
- `/api/admin/todo/reports/week/{period_key}`
- `/api/admin/todo/reports/month/{period_key}`
- `/api/admin/todo/settings`
- `/api/admin/todo/backups`

列表 API 统一支持日期范围、科目、完成状态、生命周期状态和分页。批量复制和重复计划修改先提供 preview，再提交 apply，避免误操作。

由于当前 Admin 没有服务端会话，首版不开放 Web 恢复接口。数据恢复通过服务器本地管理命令执行，避免把高破坏性的恢复能力暴露成无服务端鉴权的 HTTP API。

## 9. JSON 一致性、备份与恢复

### 9.1 写入协议

所有 Todo 读改写流程必须经过同一个存储层：

1. 获取 `.learning-todo.lock` 跨进程独占锁。
2. 读取并按 Pydantic 模型校验目标文件。
3. 检查文件 revision 和任务 `expected_version`。
4. 在同目录创建临时文件。
5. 写入、flush、`fsync`。
6. `os.replace` 原子替换。
7. 必要时同步目录元数据。
8. 释放文件锁。

禁止 API 或业务服务绕过存储层直接 `open(..., "w")`。

读请求不能永久依赖进程内缓存；多个 Gunicorn worker 下应每次读取 revision，或按 mtime/revision 失效缓存。

### 9.2 跨文件修改

改期跨月、重复任务批量更新、恢复备份会修改多个文件。采用：

- 全局独占锁。
- 操作前快照。
- 操作清单/恢复标记。
- 全部新文件先写入 staging 目录并校验。
- 再按清单替换正式文件。
- 启动时检测未完成操作并自动回滚到操作前快照。

### 9.3 备份

以下操作前自动备份：

- 批量改重复计划。
- 复制整周任务。
- 批量作废。
- 手动恢复。

备份包含：

- schema version。
- 创建时间和触发人。
- 文件清单。
- SHA-256 校验值。

设置保留数量或天数，默认保留最近 30 个自动备份；生产部署脚本仍继续做整个 `data/` 的外层备份。

### 9.4 恢复

- 首版只允许在服务器本地通过受控管理命令恢复，不提供 HTTP 恢复接口。
- 命令先列出备份和校验结果，要求操作者明确输入确认短语。
- 恢复前再创建 `pre-restore` 备份。
- staging 校验通过后才替换。
- 恢复后重新校验所有 JSON，并返回恢复摘要。
- 任何校验失败都不改正式数据。

### 9.5 启动校验与故障隔离

应用启动时：

- 初始化缺失的设置、默认科目和空模板文件。
- 校验全部 Todo JSON 的 schema、月份键、任务 ID 唯一性、科目引用和重复实例唯一性。
- 检测未完成的跨文件操作。
- 损坏时记录明确错误，并让 Todo 路由返回 `503`；不应因为 Todo 单个文件损坏而使英语、数学、中文等现有模块全部无法启动。
- `/health` 增加 `learning_todo_storage` 状态，但不返回密码、文件内容或绝对路径。

## 10. 前端页面规划

### 10.1 门户

- `portal.html` 的课程 Grid 增加 Todo 卡片。
- 桌面端从 4 列调整为能容纳 5 个入口的响应式布局。
- Todo 直接进入 `/todo`，不显示密码弹窗。

### 10.2 孩子 H5 `/todo`

移动优先，单页包含：

- 日期与今日 `完成数/总数`。
- 进度条。
- 学习积分卡片：累计积分、连续完成任务日、今日可得/已得分数。
- 逾期任务。
- 今日待完成。
- 今日已完成。
- 网络失败、空状态、提交中、完成成功和撤销倒计时状态。

交互要求：

- 勾选期间禁用重复提交。
- 完成 API 幂等。
- 完成后展示可撤销提示，不立刻隐藏全部上下文。
- 科目颜色只用于任务卡片标识。
- 逾期明确显示原计划日期和逾期天数。
- 触控目标至少 44px，支持键盘、屏幕阅读器和减少动画设置。
- 所有任务文本安全输出，不执行 HTML。

### 10.3 Admin Todo `/admin/todo`

首版使用一个管理壳页面和响应式栏目，不引入 SPA 框架：

- 今日概览。
- 任务管理。
- 日视图。
- 周视图。
- 月视图。
- 周统计。
- 月统计。
- 科目管理。
- 设置。

建议把 HTML、CSS、JS 拆成独立静态文件，避免继续扩大现有内联脚本。静态资源同时提供根路径和 `/learningcenter` 前缀。

## 11. 分阶段实施计划

每个阶段独立提交并通过测试后再进入下一阶段。

### Phase 0：规格冻结与模块骨架

- 确认本文第 15 节剩余的 Review 决策。
- 保持现有 Admin 登录方式，不新增 Todo 密码或会话。
- 在 Admin 首页增加同级“Todo 管理”入口。
- 建立 `/todo`、`/admin/todo` 和两组 API 的空路由。
- 增加根路径和 `/learningcenter` 的路由回归测试。

完成门槛：现有 Admin 行为无变化，Todo 两个入口在双路径下都可正确打开。

### Phase 1：Todo 存储与核心领域

- 建立 `services/learning_todo/`、Pydantic 数据模型和 Clock/Timezone 抽象。
- 实现目录初始化、默认科目、JSON schema version。
- 实现跨进程锁、原子写、revision、任务 version。
- 实现任务状态、逾期、按时/逾期完成和 Grid 纯函数。
- 实现启动校验和 Todo 独立 503 故障状态。

完成门槛：日期和状态矩阵单元测试通过；多进程并发写测试无数据丢失。

### Phase 2：科目与基础任务 CRUD

- 实现科目 CRUD/排序/停用。
- 实现单次任务创建、编辑、改期、完成、取消完成、取消、作废和历史。
- 实现筛选、分页和 optimistic concurrency。

完成门槛：科目和单次任务 CRUD API 集成测试通过。

### Phase 3：重复任务与复制

- 实现 daily/weekly/monthly/last-day 规则。
- 实现按查询范围幂等物化实例。
- 实现仅本次、本次及以后、整个计划三种修改。
- 实现复制某日、复制上周的 preview/apply。
- 实现跨月、跨年、闰年和逾期实例并存。

完成门槛：重复读取不产生重复实例；批量修改失败时可恢复到操作前状态。

### Phase 4：孩子 Todo H5

- 门户新增 Todo 入口。
- 实现 `/todo` 页面和公共查询、完成、快捷撤销及手动取消完成接口。
- 实现由任务历史实时计算的连续完成积分和孩子端积分卡片。
- 完成移动端、平板、电脑布局。
- 隔离家长备注和管理字段。
- 增加离线/网络错误、重复点击和过期撤销提示。

完成门槛：孩子端只能执行需求允许的三类操作；手机宽度下无横向溢出。

### Phase 5：Admin Todo 管理视图与统计

- Admin 首页新增 Todo 管理按钮，点击后直接进入。
- 实现今日概览、任务管理、日/周/月视图。
- 实现周/月 Grid、科目筛选和任务明细。
- 实现周/月统计、科目统计、绿色/黄色日期数。
- 实现周评语和月评语。

完成门槛：7 月 27 日未完成、7 月 28 日补做的示例在页面和 API 中完全符合需求。

### Phase 6：备份、恢复与设置

- 实现自动备份、清单、校验和保留策略。
- 实现 Admin 内备份列表和服务器本地恢复命令。
- 实现即时撤销提示时长等非鉴权设置入口。
- 增加恢复失败、损坏 JSON 和未完成事务的故障测试。

完成门槛：从备份恢复后任务、模板、科目、设置和评语引用一致。

### Phase 7：回归、部署与上线

- 完整自动化测试、JS 语法校验和静态资源检查。
- 使用真实 Nginx 前缀行为验证 `/learningcenter/todo` 和 `/learningcenter/admin/todo`。
- 更新 `.env.example`、README、部署和恢复文档。
- 更新 `update_safe.sh` 的 Todo 数据检查和备份校验。
- 先以功能开关关闭状态部署，完成初始化和 smoke test 后开启。

完成门槛：现有 English/Chinese/Math/Admin 功能无回归，线上备份和回滚演练通过。

## 12. 测试计划

### 12.1 单元测试

- 待完成、按时完成、逾期完成、当前逾期、取消、作废。
- 7 月 27 日遗漏、7 月 28 日补做后历史 Grid 不变绿。
- 有/无当天任务、有/无遗留逾期的 Grid 颜色组合。
- 周跨月、月跨年、2 月闰年、每月最后一天。
- 重复计划幂等生成和三种编辑范围。
- 统计分母为 0。
- 科目停用不破坏历史。
- 孩子快捷撤销、已完成任务手动取消和家长取消完成。
- 积分首日为 1、连续递增、中断归零并重启、无任务日不中断、当天待办不提前清零。
- 时区午夜边界。

### 12.2 API 集成测试

- 公共 API 不返回 `parent_note` 和任务历史。
- 根路径与 `/learningcenter` 前缀响应一致。
- `expected_version` 冲突返回 409。
- 完成接口重复提交幂等。
- 跨月改期和跨月逾期查询。

### 12.3 存储与恢复测试

- 两个独立进程并发创建/完成任务。
- 写到临时文件后进程中断。
- 单个 JSON 截断或 schema 错误。
- 批量重复任务修改中断。
- 备份校验值错误时拒绝恢复。
- 恢复前自动备份和完整恢复。
- 多个月份文件中任务 ID 唯一。
- 对现有 `library_registry.json`、词库 TXT、`report_history.json` 和 `data/skills/*.json` 生成操作前校验值；执行 Todo 创建、完成、统计、备份和恢复后，校验值必须完全不变。
- Todo 备份和恢复清单中如果出现 `data/learning-todo/` 以外的路径，操作必须立即拒绝。

### 12.4 页面验收

- 360px 手机、平板、桌面三档布局。
- Chrome/Safari 常用版本。
- 键盘操作、焦点状态、屏幕阅读器标签。
- 慢网络、断网、接口 409/401/403/503。
- 防重复勾选和撤销倒计时。
- 页面刷新后会话和任务状态正确。

## 13. 部署、迁移与回滚

### 13.1 新配置

建议新增：

- `TODO_TIMEZONE=Asia/Shanghai`
- `ADMIN_PASSWORD`（沿用现有 Admin 密码）
- `ADMIN_SESSION_SECRET`
- `ADMIN_SESSION_HOURS`

### 13.2 数据迁移

当前没有 Todo 历史数据，因此首版只需 bootstrap，不需要业务数据迁移：

- 创建 Todo 数据目录。
- 写入 schema version。
- 创建默认科目。

运行期文件加入 `.gitignore`，代码更新继续保留线上 `data/learning-todo/`。

### 13.3 上线顺序

1. 运行 `update_safe.sh`，在应用目录外创建版本化 `data/` 与 `.env` 快照。
2. 设置 Admin 会话和 Todo 时区环境变量。
3. 同步代码后原样恢复线上 `data/`，并通过发布前 SHA-256 清单。
4. 启动并检查 Todo JSON 校验状态。
5. 验证现有词库、Skills、Daily Reports 和 Admin 登录。
6. 验证 `/learningcenter/todo`、Admin Todo 入口、创建/完成/撤销、周月视图。
7. 创建一次 Todo 手动备份并通过服务器命令做恢复演练。

### 13.4 回滚

- 代码回滚不删除 `data/learning-todo/`。
- 数据问题优先从 Todo 内部 `pre-restore` 或部署前 `data/` 备份恢复。
- 不使用 Git 覆盖或恢复线上 Todo 生产数据。

## 14. 明确不做

- 独立 App。
- MySQL/PostgreSQL 或其他数据库。
- 孩子账号、家长账号、多用户、注册、找回密码。
- 推送通知。
- 任务完成时长。
- 孩子端统计、评语或管理入口。
- 复杂多孩子/多家庭隔离。
- 在首版中把 Todo 与 AI 出题或 Daily Reports 自动关联。

## 15. Review 时需要确认的决策

计划已给出推荐默认值；如无异议，实施时按推荐值执行。

已确认：Todo 管理直接加入现有 Admin，不增加独立密码、家长会话或二次验证。现有 Admin 登录弹窗和同一密码保持不变，但密码改由服务端验证并签发 HttpOnly Admin 会话，Todo 管理接口复用该会话。

1. **孩子取消完成方式**
   已确认：完成后显示 10 秒快捷撤销；已完成列表可随时手动取消完成状态，家长端也可取消。

2. **取消/作废的统计口径**
   推荐：两者均保留历史但不进入完成率分母；取消表示免除，作废表示错误记录。

3. **历史无计划日补做逾期任务的颜色**
   推荐：仍为灰色，可显示“当天完成逾期任务”标识；绿色只表示当天有计划且全部按时完成。

4. **公共孩子端的访问风险**
   按需求不设密码，任何知道地址的人都可能查看和勾选任务。推荐首版明确接受；若不能接受，需要另加设备码或私密链接，这会改变当前需求。

## 16. Definition of Done

只有同时满足以下条件才视为完成：

- 需求中的两个入口、单次/重复任务、顺延、状态、日周月视图、统计、科目、评语、备份恢复全部可用。
- Todo 管理已直接集成到现有 Admin，复用同一 Admin 密码和会话，没有第二套密码或二次验证。
- 孩子 API 只暴露允许的数据和操作。
- 孩子积分遵循连续完成规则，并在完成或取消完成后实时更新。
- Todo 的任何创建、编辑、完成、统计、备份和恢复操作都不会修改现有词库、Skills 或练习报告数据。
- JSON 多进程并发测试、损坏恢复测试和跨月/跨年测试通过。
- 历史 Grid 与统计口径通过固定案例测试。
- 根路径与 `/learningcenter` 前缀均通过验收。
- 现有学习模块和 Admin 现有能力无回归。
- 线上数据备份、恢复和代码回滚完成演练。
