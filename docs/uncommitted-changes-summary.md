# 当前未提交内容说明

生成时间：2026-07-28
当前分支：`deploy/tencent-learningcenter-path`
状态：未暂存、未提交、未推送

## 1. Learning Todo 功能代码

### 后端与配置

- `api/todo.py`
  - 新增孩子端 Todo API。
  - 新增公开积分查询，今日任务响应同步返回积分状态。
  - 新增 Admin Todo 管理 API。
  - 新增 Admin 登录会话 API。
  - 根路径和 `/learningcenter` 前缀均可用。
- `models/todo_schemas.py`
  - 科目、单次/重复任务、复制、评语、设置、备份恢复请求模型。
- `services/learning_todo_service.py`
  - 独立 `data/learning-todo/` JSON 存储。
  - 默认科目、任务按月拆分、跨月查询。
  - 每天、每周指定星期、每月日期和月末重复。
  - 独立任务实例、三种重复计划修改范围。
  - 完成、取消完成、取消、软作废和任务历史。
  - 逾期顺延、日/周/月 Grid、周/月统计和家长评语。
  - 按计划日实时推导学习积分：连续完成递增、中断重置、无任务日不中断。
  - 原子写入、线程锁、跨进程文件锁、启动 JSON 校验。
  - Todo 内部自动备份、手动备份和安全恢复。
- `services/admin_session_service.py`
  - 沿用现有 Admin 密码。
  - 服务端 HMAC 签名 HttpOnly Cookie 会话。
  - 不增加 Todo 独立密码或二次登录。
- `config.py`、`.env.example`
  - 新增 Admin 会话、Cookie、Todo 数据目录和时区配置。
- `main.py`
  - 注册 Todo 页面和 API。
  - 同时注册根路径与 `/learningcenter` 前缀。
- `.gitignore`
  - 忽略服务器运行数据 `data/report_history.json` 和 `data/learning-todo/`。

### 前端

- `static/todo.html`
  - 孩子端移动优先 H5。
  - 今日进度、逾期、待完成和今日已完成。
  - 学习积分卡片：累计积分、连续完成任务日、今天已获得或可获得分数。
  - 完成后快捷撤销。
  - 已完成列表可随时手动取消完成。
  - 完成或取消完成后积分即时联动；演示模式也覆盖积分变化。
  - 默认使用真实 API；`?demo=1` 保留纯前端演示。
- `static/admin_todo.html`
  - 今日概览、任务管理、日/周/月视图、统计、科目和设置。
  - 任务创建、编辑、完成、取消完成和软作废连接真实 API。
  - 每周星期选择完整显示周日到周六。
  - 重复任务编辑支持本次、本次及以后、整个计划。
  - Admin 评语、科目启停、手动备份连接真实 API。
  - 复制当天和复制上周任务连接真实 API。
  - iPad 横屏紧凑布局和统一清晰字体。
- `static/portal.html`
  - 新增孩子 Todo 入口。
  - 保持原 Admin 密码弹窗，但改为服务端校验和会话。
- `static/admin.html`
  - 新增 Todo 管理入口。
- `static/admin_create.html`、`static/admin_detail.html`、`static/admin_skills.html`、
  `static/chinese.html`、`static/english.html`、`static/math.html`
  - 统一字体栈。

## 2. 数据隔离与部署保护

- Todo 只读写 `data/learning-todo/`，不会读写：
  - `data/library_registry.json`
  - `data/*.txt`
  - `data/skills/`
  - `data/report_history.json`
- `update_safe.sh`
  - 每次部署前在应用目录外生成不可覆盖的版本化 `data/` 和 `.env` 快照。
  - 为发布前全部数据文件生成 SHA-256 清单。
  - Git 强制同步后原样恢复整个服务器 `data/`。
  - 新版本数据种子只补缺，不覆盖服务器已有文件。
  - 发布后逐文件验证发布前清单。
  - 导入应用并执行 Todo JSON 启动校验。
- `scripts/validate_persistent_data.py`
  - 校验所有 JSON。
  - 统计词库、Skills、Daily Reports、Todo 月任务和备份。
  - 生成和验证持久数据清单。
- `scripts/merge_missing_data.py`
  - 仅复制服务器上不存在的数据种子文件。
- `DeployToDo.md`、`updateNew.md`
  - 更新为当前 JSON 持久化架构。
  - 记录安全发布、校验、回滚和生产环境变量。
- `docs/learning-todo-implementation-plan.md`
  - 完整需求适配、接口、存储、权限、测试与部署计划。

## 3. 自动化测试

- `tests/test_learning_todo_service.py`
  - Todo 与词库/Reports/Skills 文件隔离。
  - 跨月七天重复实例。
  - 逾期、完成、手动取消完成。
  - 补做后历史日期保持黄色。
  - 当天待办为黄色但不误报逾期。
  - 单实例重复任务的未来作废。
  - 整个重复计划修改不会把实例日期合并。
  - 闰年每月最后一天。
  - 备份恢复。
  - 复制任务生成新的未完成实例。
  - 积分连续递增、中断后重启、无任务日不中断、当天未完成不提前清零。
- `tests/test_todo_api.py`
  - 无 Admin 会话返回 401。
  - 原 Admin 密码登录。
  - Admin 创建任务和孩子端公开完成。
  - 今日响应和独立积分接口。
  - 公共 API 不暴露家长备注和任务历史。
  - `/learningcenter` 前缀接口。
  - 主动退出 Admin 会话。
- `tests/conftest.py`
  - 测试运行路径设置。

当前结果：

- `pytest -q`：12 项通过。
- Python 编译检查：通过。
- 三个 Todo 相关 HTML 内联 JavaScript 语法：通过。
- `update_safe.sh` Shell 语法：通过。
- 本地接口：`health=200`、前缀健康检查 `200`、无会话 Admin `401`、
  登录 `200`、Todo 存储校验 `200`、孩子今日任务 `200`。
- 真实浏览器流程：Admin 登录、创建每周任务、孩子完成、孩子手动取消完成、
  Admin 作废全部通过。
- 临时 Git 发布演练：词库改动、Daily Report 和 Todo 月任务在强制同步后
  均通过发布前 SHA-256 清单，结果 `PASS`。

已知非阻塞警告：

- FastAPI 提示现有 `on_event` 生命周期写法已弃用；这是项目原有写法，不影响本次测试。

## 4. 运行数据（已忽略，不作为代码提交）

- `data/report_history.json`
  - 现有 Daily Reports 服务器/本地运行数据。
- `data/learning-todo/`
  - 本地联调生成的 Todo 默认配置、一个已作废的联调任务和 Todo 自动备份。
  - 已被 `.gitignore` 排除，部署时由 `update_safe.sh` 单独保护。

## 5. 当前工作区中其他未提交内容

以下内容已经存在于工作区，但不属于本次 Todo 功能的正式代码范围：

- `.codebuddy/`
  - CodeBuddy 计划和规则文件，当前全部未跟踪。
- `learningcenter-deploy.tar.gz`
  - 未跟踪的部署压缩包，本次未重建或覆盖。
- 已跟踪的多个 `__pycache__/*.pyc`
  - 本地 Python 运行产生的二进制变化，不应纳入正式代码提交。

提交前建议明确排除 `.codebuddy/`、部署压缩包和 `__pycache__/*.pyc`，并仅选择
Todo 功能、测试、部署脚本和文档文件。当前未执行任何暂存或提交操作。
