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
│   │   ├── *.txt
│   │   ├── skills/
│   │   ├── report_history.json
│   │   └── learning-todo/
│   └── .env
└── backups/
    ├── releases/<时间>/         # 每次发布前的完整快照
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

不要上传本地运行产生的 `data/report_history.json` 或 `data/learning-todo/`
覆盖服务器。服务启动后会在缺失时自动创建 Todo 的独立默认文件。

## `.env`

在 `/www/wwwroot/learningcenter/app/.env` 配置：

```env
OPENAI_API_KEY=<API Key>
OPENAI_BASE_URL=<API 地址>
MODEL_NAME=gpt-3.5-turbo
HOST=127.0.0.1
PORT=8088

ADMIN_PASSWORD=0418
ADMIN_SESSION_SECRET=<至少 32 字节的随机字符串>
ADMIN_SESSION_HOURS=12
ADMIN_COOKIE_SECURE=1

TODO_TIMEZONE=Asia/Shanghai
```

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

脚本会：

1. 在应用目录外创建版本化 `data/` 和 `.env` 快照。
2. 生成发布前 SHA-256 清单并校验全部 JSON。
3. 同步部署分支代码。
4. 原样恢复发布前的服务器 `data/`。
5. 仅补充新代码中缺失的数据种子，不覆盖线上数据。
6. 逐文件验证发布前清单。
7. 导入应用并校验 Todo 存储。

脚本完成后在宝塔重启 Python 项目。详细恢复步骤见
[`updateNew.md`](updateNew.md)。

## 发布验收

```bash
cd /www/wwwroot/learningcenter/app
/www/server/pyporject_evn/versions/3.11.15/bin/python3 \
  scripts/validate_persistent_data.py data
```

随后检查：

- `/learningcenter/admin`：词库和 Skills 数据未变化。
- `/learningcenter/english`：Daily Reports 历史存在。
- `/learningcenter/admin/todo`：任务、科目、统计和评语存在。
- `/learningcenter/todo`：孩子端完成与取消完成正常。

不要把“页面能打开”当作数据验收；必须同时执行数据校验并人工抽查三类历史内容。
