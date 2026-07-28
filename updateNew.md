# Jingsen Learning Center 线上安全更新

当前生产数据继续使用服务器本地文件，不随 Git 发布覆盖。统一使用项目根目录的：

```bash
bash update_safe.sh
```

不要再直接执行 `git pull`、`git reset --hard` 后重启，也不要用本地 `data/`
覆盖服务器 `data/`。

## 服务器约定

- 应用目录：`/www/wwwroot/learningcenter/app`
- 持久数据：`/www/wwwroot/learningcenter/app/data`
- 发布快照：`/www/wwwroot/learningcenter/backups/releases/<时间>`
- 最新快照软链接：`/www/wwwroot/learningcenter/backups/latest`
- 部署分支：`deploy/tencent-learningcenter-path`
- 内部服务：`http://127.0.0.1:8088`
- 公网入口：`https://jingsen.cc/learningcenter/`

## 一次发布会保护哪些数据

`update_safe.sh` 在同步代码前快照整个 `data/`，因此统一保护：

- `data/library_registry.json` 与 `data/*.txt`：词库元数据和内容。
- `data/skills/`：Admin 维护的 Skills。
- `data/report_history.json`：Daily Word、Vocabulary Skills、MAP Test 等 Daily Reports。
- `data/learning-todo/`：Todo 科目、设置、重复模板、月任务、评语和 Todo 内部备份。
- `.env`：API Key、Admin 密码、Session Secret、端口等服务器配置。

同步代码后，脚本先原样恢复发布前的整个 `data/`，再仅补充新版代码中新增但
服务器上不存在的种子文件。发布前清单中的每个数据文件都必须保持相同 SHA-256，
否则部署会直接失败。

## 正式更新步骤

```bash
cd /www/wwwroot/learningcenter/app
bash update_safe.sh
```

脚本成功后：

1. 在宝塔 Python 项目管理器中重启 `app`。
2. 执行：

```bash
curl -fsS http://127.0.0.1:8088/health
curl -I https://jingsen.cc/learningcenter/
```

3. 校验持久数据：

```bash
cd /www/wwwroot/learningcenter/app
/www/server/pyporject_evn/versions/3.11.15/bin/python3 \
  scripts/validate_persistent_data.py data
```

输出中应看到：

- `library_registry: true`
- `daily_reports: true`（已有报告数据时）
- `todo_directory: true`（Todo 服务首次启动后）
- 合理的 `library_text_files`、`todo_task_months` 数量

4. 页面验收：

- Admin 词库列表和 Skills 数据仍在。
- English → Daily Reports 历史仍在。
- Admin → Todo 管理中的任务、科目和评语仍在。
- 孩子端 Todo 能完成和取消完成任务。

## 快照恢复

先停止或暂停 Python 项目写入，再执行。`latest` 指向最近一次发布前快照：

```bash
set -Eeuo pipefail

APP_DIR="/www/wwwroot/learningcenter/app"
LATEST="/www/wwwroot/learningcenter/backups/latest"
RECOVERY="/www/wwwroot/learningcenter/backups/manual-recovery-$(date +%Y%m%d-%H%M%S)"

[ -d "$LATEST/data" ]
mkdir -p "$RECOVERY"

cd "$APP_DIR"
if [ -d data ]; then
  mv data "$RECOVERY/data-before-restore"
fi
cp -a "$LATEST/data" data
if [ -f "$LATEST/app.env" ]; then
  cp -a "$LATEST/app.env" .env
fi
chown -R www:www "$APP_DIR"

/www/server/pyporject_evn/versions/3.11.15/bin/python3 \
  scripts/validate_persistent_data.py data \
  --verify-manifest "$LATEST/data-manifest.json"
```

恢复完成后在宝塔重启 Python 项目。`data-before-restore` 被移到独立恢复目录，
不会直接删除。

## 环境变量

生产 `.env` 至少应包含：

```env
OPENAI_API_KEY=...
OPENAI_BASE_URL=...
MODEL_NAME=...
PORT=8088

ADMIN_PASSWORD=0418
ADMIN_SESSION_SECRET=请替换为长随机字符串
ADMIN_SESSION_HOURS=12
ADMIN_COOKIE_SECURE=1

TODO_TIMEZONE=Asia/Shanghai
```

不设置 `TODO_DATA_DIR` 时默认使用 `data/learning-todo/`。不要将它指向词库、
Skills 或 `report_history.json` 所在文件。

## 失败处理

- 部署命令失败时不要连续重复执行，也不要删除 `backups/releases/`。
- 先查看终端最后一个错误，以及本次输出的快照目录。
- 数据清单失败说明服务器数据缺失或被改写，应先按快照恢复。
- JSON 校验失败时先保留损坏文件并从快照恢复，不要创建空文件覆盖。
- `health` 失败但数据校验通过时，先重启 Python 项目并查看宝塔项目日志。
