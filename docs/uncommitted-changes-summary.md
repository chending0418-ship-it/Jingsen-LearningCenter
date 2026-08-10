# 2026-08-10 发布内容说明

生成时间：2026-08-10

当前分支：`deploy/tencent-learningcenter-path`

基线提交：`7ec62a6`

功能提交：`7fceee4`

状态：已提交并推送到 `deploy/tencent-learningcenter-path`

## 1. Admin 模型选择

- 新增 `/admin/models` 页面和 Admin 入口，可读取当前服务端 Key 对应的 `/v1/models` 列表、搜索并保存全站默认模型。
- 新增受现有 Admin 会话保护的模型目录与设置 API；浏览器不会获得 API Key。
- 模型选择原子写入独立的 `data/model-settings.json`，并使用文件锁保护并发写入。
- AI 出题请求会在每次调用时读取当前选择，保存后无需重启；尚未保存时回退到 `.env` 的 `MODEL_NAME`。
- `OPENAI_BASE_URL` 同时兼容根域名和 `/v1` 地址，健康检查显示当前实际模型。

涉及文件：

- `.env.example`、`.gitignore`、`config.py`、`main.py`
- `api/model_settings.py`
- `models/model_settings_schemas.py`
- `services/model_settings_service.py`
- `core/ai_generator.py`
- `static/admin_models.html`、`static/admin.html`
- `tests/test_model_settings.py`

## 2. Learning Todo 任务 Reward 与积分构成

- 单次任务和重复任务模板新增自定义 `Reward 目标` 与 `Reward 点数`；每个重复任务实例独立确认、独立发放。
- 孩子端任务卡展示目标、分数及“完成后确认 / 等待家长确认 / 已发放”状态。
- 家长只能在任务完成后确认 Reward；确认接口幂等，重复请求不会重复加分。
- 发放时固化奖励点数和时间；已发放实例不能修改 Reward 配置，任务历史保留发放事件。
- 学习积分仍是同一种积分：
  - `总积分 = 连续完成积分 + 任务 Reward 积分`
  - 卡片同时显示总积分及两个来源小计。
- 孩子端 390px 手机布局已调整，累计分数不再被卡片边缘裁切。
- 家长任务管理新增“计划日期”精确筛选和清除按钮；日视图也可按指定日期查看并确认 Reward。
- iPad 横屏继续采用紧凑布局，没有页面级横向溢出。

涉及文件：

- `models/todo_schemas.py`
- `services/learning_todo_service.py`
- `api/todo.py`
- `static/admin_todo.html`、`static/todo.html`
- `tests/test_learning_todo_service.py`、`tests/test_todo_api.py`

Todo Reward 数据继续只保存在 `data/learning-todo/tasks/*.json` 的任务记录中，不会读写词库、Skills 或 Daily Reports。

## 3. 词库独立归档

- 新增 `data/library_archive.json`，保存归档词库的完整元数据和全部词条。
- 归档时先原子写入独立归档文件，再从活动注册表和对应的活动 `.txt` 文件中移出。
- 默认词库管理和出题流程只读取活动 `library_registry.json`，不会加载归档内容。
- Admin 可选择“显示已归档词库”，查看只读详情并恢复；恢复后默认停用，需要家长明确启用才重新参与出题。
- 恢复会保留原词库 ID 和词条内容，并重建活动 `.txt` 文件。
- 启动时兼容早期同注册表归档格式，并处理跨文件写入中断形成的重复项。

涉及文件：

- `models/schemas.py`
- `services/library_admin_service.py`
- `api/admin.py`
- `static/admin.html`、`static/admin_detail.html`
- `tests/test_library_archiving.py`

## 4. 持久化与部署文档

- 持久化校验摘要新增 `library_archive` 和 `model_settings`。
- 部署备份范围明确包括：活动词库、归档词库、Skills、Daily Reports、模型设置、Learning Todo 和 `.env`。
- 永久手工基线 `/www/wwwroot/learningcenter/backups/manual-pre-todo-20260728-220002` 继续标记为永不清理。

涉及文件：

- `scripts/validate_persistent_data.py`
- `DeployToDo.md`、`updateNew.md`、`README.md`
- `docs/learning-todo-implementation-plan.md`

## 5. 验证结果

- `/Users/JasonChan/anaconda3/bin/python -m pytest -q`：`19 passed`。
- `git diff --check`：通过。
- Todo、Admin Todo、Admin、词库详情和模型选择页面的内联 JavaScript 语法检查：通过。
- 真实浏览器：
  - 390×844 孩子端无横向溢出，总积分及两种来源完整显示。
  - 1180×820 Admin Todo 无页面级横向溢出。
  - 指定 `2026-08-10` 后，演示任务由 15 条准确筛选为当天 5 条。
  - 新增任务表单、日视图 Reward 待确认和已发放状态正常。
- 已知非阻塞警告：FastAPI 现有 `on_event` 写法有弃用提示，不影响当前功能。

## 6. 明确不提交的本地内容

- `.codebuddy/`
- `learningcenter-deploy.tar.gz`
- 所有 `__pycache__/` 和 `*.pyc`
- `data/library_archive.json`、`data/model-settings.json`、`data/learning-todo/` 等本地运行数据
- `.env` 与任何 API Key

上述内容之外，本说明列出的代码、测试和文档已一并提交和推送。
