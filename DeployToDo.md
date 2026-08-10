# 腾讯云宝塔部署手册 — Jingsen Learning Center

目标地址：`https://jingsen.cc/learningcenter/`

本项目不使用 MySQL 或 PostgreSQL。词库、Skills、Daily Reports 和 Learning
Todo 均通过服务器本地文件持久化，因此部署的重点是让代码目录可以更新，同时
保证 `data/` 和 `.env` 永远先备份、后恢复、再校验。

## 目录与权限

```text
/www/wwwroot/learningcenter/
├── app/                         # Git 代码目录
│   ├── data/                    # 服务器真实持久数据
│   │   ├── library_registry.json
│   │   ├── library_archive.json # 归档词库元数据与完整词条
│   │   ├── *.txt
│   │   ├── skills/
│   │   ├── report_history.json
│   │   └── learning-todo/       # 含任务、评语和 points-ledger.json 积分支出流水
│   └── .env
└── backups/
    ├── releases/<时间>/         # 每次发布前的完整快照
    │   ├── data/                # 完整 data 快照
    │   ├── data-manifest.json   # 完整数据 SHA-256 清单
    │   └── library-data-backup.json # 两个词库 JSON 的专项 SHA-256 凭据
    └── latest -> releases/<时间>
```

初始化：

```bash
mkdir -p /www/wwwroot/learningcenter/backups/releases
chown -R www:www /www/wwwroot/learningcenter
```

## 首次取得代码

```bash
cd /www/wwwroot/learningcenter
sudo -u www -H git clone <仓库地址> app
cd app
sudo -u www -H git checkout deploy/tencent-learningcenter-path
```

不要上传本地运行产生的 `data/report_history.json`、`data/library_archive.json` 或
`data/learning-todo/` 覆盖服务器。服务启动后会在缺失时自动创建 Todo 默认文件
和独立词库归档文件。

词库执行“归档”时，完整词条会先写入 `data/library_archive.json`，随后从活动
`library_registry.json` 和对应的活动 `.txt` 中移出；恢复时会重建 `.txt`，且默认
保持停用，避免未经确认重新参与出题。

## `.env`

在 `/www/wwwroot/learningcenter/app/.env` 配置：

```env
OPENAI_API_KEY=<API Key>
OPENAI_BASE_URL=https://api.gpt.ge
MODEL_NAME=gpt-3.5-turbo
MODEL_LIST_TIMEOUT=15
HOST=127.0.0.1
PORT=8088

ADMIN_PASSWORD=0418
ADMIN_SESSION_SECRET=<至少 32 字节的随机字符串>
ADMIN_SESSION_HOURS=12
ADMIN_COOKIE_SECURE=1

TODO_TIMEZONE=Asia/Shanghai
```

`MODEL_NAME` 是尚未在 Admin 保存模型选择时的回退值。Admin → 模型选择会由
服务端使用 `OPENAI_API_KEY` 请求兼容 OpenAI 格式的 `/v1/models`，选择结果
保存到 `data/model-settings.json`。API Key 不会下发浏览器。

可以在服务器生成 Session Secret：

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

`.env` 权限建议：

```bash
chown www:www /www/wwwroot/learningcenter/app/.env
chmod 600 /www/wwwroot/learningcenter/app/.env
```

## Python 项目

宝塔 Python 项目管理器：

- 项目目录：`/www/wwwroot/learningcenter/app`
- Python：3.11
- 绑定：`127.0.0.1:8088`
- 启动命令：

```text
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --timeout 180 --graceful-timeout 30 --bind 127.0.0.1:8088
```

Todo 写入同时使用进程内锁、服务器文件锁和原子替换，支持多个 Gunicorn worker。

## Nginx 反向代理

应用已经同时注册根路径和 `/learningcenter` 前缀路由，建议保留前缀转发，不做
额外 rewrite：

```nginx
location /learningcenter/ {
    proxy_pass http://127.0.0.1:8088;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_connect_timeout 30s;
    proxy_send_timeout 180s;
    proxy_read_timeout 180s;
}
```

保存后：

```bash
nginx -t
/etc/init.d/nginx reload
```

## 首次启动校验

```bash
cd /www/wwwroot/learningcenter/app
/www/server/pyporject_evn/versions/3.11.15/bin/python3 -m pip install -r requirements.txt
/www/server/pyporject_evn/versions/3.11.15/bin/python3 -c \
  "from main import app; from services.learning_todo_service import get_learning_todo_service; print(get_learning_todo_service().validate_storage())"
```

然后在宝塔启动项目并检查：

```bash
curl -fsS http://127.0.0.1:8088/health
curl -I https://jingsen.cc/learningcenter/
```

## 后续发布

每次只使用：

```bash
cd /www/wwwroot/learningcenter/app
bash update_safe.sh
```

脚本默认要求以下两个文件在同步代码之前都已存在：

- `data/library_registry.json`
- `data/library_archive.json`

如果缺少任意一个，部署会在 `git fetch/reset` 之前停止。只有第一次上线词库归档
功能、且已经确认从未产生过归档数据时，才允许使用一次：

```bash
cd /www/wwwroot/learningcenter/app
INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING=1 bash update_safe.sh
```

该选项会先原子创建空的 `library_archive.json`，然后再把两个词库 JSON 一起纳入
本次发布前快照。归档功能投入使用后，如果此文件缺失，禁止再使用初始化选项，
必须从历史备份恢复。

如果服务器上还是旧版 `update_safe.sh`，第一次切换到新版流程时不要先覆盖整个
项目，可从远端只读取脚本到临时路径，再由该脚本完成备份和同步：

```bash
cd /www/wwwroot/learningcenter/app
git fetch origin deploy/tencent-learningcenter-path
git show origin/deploy/tencent-learningcenter-path:update_safe.sh > /tmp/learningcenter-update-safe.sh
INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING=1 bash /tmp/learningcenter-update-safe.sh
```

只有确认线上从未产生归档数据时才保留第三行的初始化变量；如果线上已经存在
`data/library_archive.json`，直接执行 `bash /tmp/learningcenter-update-safe.sh`。

脚本会：

1. 在应用目录外创建版本化 `data/` 和 `.env` 快照。
2. 强制确认两个词库 JSON 已复制且与源文件逐字节一致。
3. 生成完整数据清单及 `library-data-backup.json` 词库专项 SHA-256 凭据。
4. 校验快照中的全部 JSON。
5. 同步部署分支代码。
6. 原样恢复发布前的服务器 `data/`。
7. 仅补充新代码中缺失的数据种子，不覆盖线上数据。
8. 同时验证完整数据清单和词库专项凭据。
9. 导入应用并再次强制确认两个词库 JSON 存在。

脚本完成后在宝塔重启 Python 项目。详细恢复步骤见
[`updateNew.md`](updateNew.md)。

## 发布验收

```bash
cd /www/wwwroot/learningcenter/app
/www/server/pyporject_evn/versions/3.11.15/bin/python3 \
  scripts/validate_persistent_data.py data \
  --verify-manifest /www/wwwroot/learningcenter/backups/latest/library-data-backup.json \
  --require-file library_registry.json \
  --require-file library_archive.json \
  --require-file learning-todo/points-ledger.json
```

随后检查：

- `/learningcenter/admin`：词库和 Skills 数据未变化。
- `/learningcenter/admin`：归档词库只在勾选“显示已归档词库”时出现，且不参与出题。
- `/learningcenter/admin/models`：可读取当前 Key 的模型列表并保存默认模型。
- `/learningcenter/english`：Daily Reports 历史存在。
- `/learningcenter/admin/todo`：任务、Reward 配置/发放、积分支出流水、科目、统计和评语存在。
- `/learningcenter/todo`：孩子端完成、取消完成、Reward 目标、累计获得/支出和可用积分正常。

不要把“页面能打开”当作数据验收；必须同时执行数据校验并人工抽查三类历史内容。
