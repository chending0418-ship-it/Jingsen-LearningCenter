# 线上安全更新命令（learningcenter）

以后每次本地代码已经 `git push` 到远端之后，登录服务器，直接执行下面这一整段命令。

这份文档的目标：**更新代码，但不覆盖线上词库、线上学习记录、线上 Skills 维护数据和线上 `.env`**。

---

## 当前线上约定

- 项目目录：`/www/wwwroot/learningcenter/app`
- Git 分支：`deploy/tencent-learningcenter-path`
- Python 端口：`127.0.0.1:8088`
- 公网入口：`https://jingsen.cc/learningcenter/`
- 线上数据目录：`/www/wwwroot/learningcenter/app/data`
- 线上备份目录：`/www/wwwroot/learningcenter/backups`
- 项目文件所属用户：`www`

---

## 这次版本新增需要保护的数据

线上重要数据都在：

```text
/www/wwwroot/learningcenter/app/data
```

其中包括：

- `data/library_registry.json`：词库元数据
- `data/*.txt`：词库内容
- `data/report_history.json`：Daily Reports 历史记录
- `data/skills/index.json`：Skills 文件索引
- `data/skills/map_language_arts.json`：MAP Language Arts Skills
- `data/skills/map_reading.json`：MAP Reading Skills
- `data/skills/word_vocabulary_skills.json`：Word Palace Vocabulary Skills

注意：

- `data/skills/*.json` 以后也属于线上生产数据。Admin Skills 页面可能会修改这些文件的启用状态，所以更新时不能直接覆盖线上已有的 `data/skills/`。
- `data/report_history.json` 现在也属于线上生产数据，更新前必须备份，不能再按 mock 文件看待。

---

## 最安全更新命令

> 重要：请复制下面整段命令执行，不要只复制其中某一小段。

这版命令会：

1. 把线上真实 `data/` 备份到固定目录 `data-newest`，每次覆盖为最新版本。
2. 把线上 `.env` 备份到固定文件 `env-newest`，每次覆盖为最新版本。
3. 额外把 `data/report_history.json` 单独备份为 `report-history-newest.json`，方便快速检查或单独恢复。
4. 用 `www` 用户同步 Git 代码，避免 `dubious ownership`。
5. 暂存 Git 版本里的 `data/skills/` 到 `skills-from-git-newest`，用于首次上线 Skills 文件。
6. 恢复更新前的线上真实 `data/`，确保词库、Reports 和已维护 Skills 不被覆盖。
7. 如果线上原本没有 `data/skills/` 或缺少某个 Skills 文件，则从 Git 版本补齐缺失文件。
8. 不覆盖线上已有的 `data/skills/*.json`。

```bash
set -e

APP_DIR="/www/wwwroot/learningcenter/app"
BACKUP_ROOT="/www/wwwroot/learningcenter/backups"
BRANCH="deploy/tencent-learningcenter-path"
PYTHON_BIN="/www/server/pyporject_evn/versions/3.11.15/bin/python3"
DATA_BACKUP="$BACKUP_ROOT/data-newest"
ENV_BACKUP="$BACKUP_ROOT/env-newest"
REPORT_BACKUP="$BACKUP_ROOT/report-history-newest.json"
SKILLS_GIT_BACKUP="$BACKUP_ROOT/skills-from-git-newest"

cd "$APP_DIR"
mkdir -p "$BACKUP_ROOT"

# 用 www 用户执行 git，避免 root 执行 git 时出现 dubious ownership 报错
run_git() {
  sudo -u www -H git -C "$APP_DIR" "$@"
}

# 0. 确认这是 Git 项目
if [ ! -d ".git" ]; then
  echo "错误：$APP_DIR 不是 Git 项目，未找到 .git。"
  echo "请先确认 APP_DIR 是否正确。"
  exit 1
fi

# 1. 先备份线上真实 data，词库、Skills 和每日报告都在这里
if [ -d "data" ]; then
  rm -rf "$DATA_BACKUP"
  cp -a data "$DATA_BACKUP"
  echo "已备份线上 data 到: $DATA_BACKUP"
else
  echo "警告：当前项目目录没有 data 文件夹，将继续更新。"
fi

# 2. 单独备份 report_history.json，便于快速恢复 Daily Reports
if [ -f "data/report_history.json" ]; then
  cp -a "data/report_history.json" "$REPORT_BACKUP"
  echo "已单独备份 report_history.json 到: $REPORT_BACKUP"
else
  echo "提示：当前没有 data/report_history.json，跳过单独备份。"
fi

# 3. 备份线上 .env，避免代码同步时影响线上环境变量
if [ -f ".env" ]; then
  cp -a .env "$ENV_BACKUP"
  echo "已备份线上 .env 到: $ENV_BACKUP"
else
  echo "警告：当前项目目录没有 .env 文件，将继续更新。"
fi

# 4. 拉取远端最新代码信息
run_git fetch origin

# 5. 切到部署分支，并强制同步到远端最新版本
# 说明：这会覆盖代码文件的本地改动，但 data 和 .env 已经提前备份，后面会恢复。
run_git checkout "$BRANCH"
run_git reset --hard "origin/$BRANCH"

# 6. 暂存 Git 版本里的 data/skills，用于首次上线或补齐缺失的 Skills 文件
if [ -d "data/skills" ]; then
  rm -rf "$SKILLS_GIT_BACKUP"
  mkdir -p "$SKILLS_GIT_BACKUP"
  cp -a data/skills/. "$SKILLS_GIT_BACKUP/"
  echo "已暂存 Git 版本 Skills 到: $SKILLS_GIT_BACKUP"
fi

# 7. 清理未跟踪的临时文件，但保留 data 和 .env
run_git clean -fd -e data -e .env

# 8. 恢复更新前的线上真实 data，确保线上词库、报告和已维护 Skills 不被覆盖
if [ -d "$DATA_BACKUP" ]; then
  rm -rf data
  cp -a "$DATA_BACKUP" data
  echo "已恢复线上真实 data 到项目目录。"
else
  mkdir -p data
  echo "没有找到更新前 data 备份，已创建空 data 目录。"
fi

# 9. 如果线上 data 缺少 skills 文件，则从 Git 版本补齐；已有文件不覆盖
if [ -d "$SKILLS_GIT_BACKUP" ]; then
  mkdir -p data/skills
  for f in index.json map_language_arts.json map_reading.json word_vocabulary_skills.json; do
    if [ ! -f "data/skills/$f" ] && [ -f "$SKILLS_GIT_BACKUP/$f" ]; then
      cp -a "$SKILLS_GIT_BACKUP/$f" "data/skills/$f"
      echo "已补齐缺失 Skills 文件: data/skills/$f"
    fi
  done
fi

# 10. 恢复线上 .env
if [ -f "$ENV_BACKUP" ]; then
  cp -a "$ENV_BACKUP" .env
  echo "已恢复线上 .env。"
fi

# 11. 确保 app 目录主要文件仍归 www 用户所有，方便宝塔 Python 项目运行
chown -R www:www "$APP_DIR"

# 12. 安装/更新依赖
"$PYTHON_BIN" -m pip install -r requirements.txt

# 13. 健康检查
curl http://127.0.0.1:8088/health

echo "更新完成。请到宝塔面板重启 Python 项目，然后再检查公网页面。"
```

---

## 更新后必须检查

执行：

```bash
cd /www/wwwroot/learningcenter/app

echo "检查 data："
ls data

echo "检查词库 registry："
cat data/library_registry.json | head

echo "检查 report history："
python3 -m json.tool data/report_history.json >/dev/null && echo "report history ok" || echo "report history missing"

echo "检查 Skills 文件："
ls data/skills
python3 -m json.tool data/skills/index.json >/dev/null && echo "skills index ok"
python3 -m json.tool data/skills/map_language_arts.json >/dev/null && echo "map language arts skills ok"
python3 -m json.tool data/skills/map_reading.json >/dev/null && echo "map reading skills ok"
python3 -m json.tool data/skills/word_vocabulary_skills.json >/dev/null && echo "word vocabulary skills ok"

echo "检查后端："
curl http://127.0.0.1:8088/health
curl http://127.0.0.1:8088/api/map/language-arts/skills/tree | head -c 200
curl http://127.0.0.1:8088/api/skills?module=map_test\&section=language_arts\&enabled_only=true | head -c 200
curl -i --max-time 90 'http://127.0.0.1:8088/api/english/generate?count=1&mode=cloze' | head -c 500
curl -i --max-time 120 'http://127.0.0.1:8088/api/english/generate?count=5&mode=passage_cloze' | head -c 500
curl -i 'http://127.0.0.1:8088/api/reports/history?module=word_palace&days=7' | head -c 500

echo "检查公网："
curl -I https://jingsen.cc/learningcenter/
curl -i --max-time 90 'https://jingsen.cc/learningcenter/api/english/generate?count=1&mode=cloze' | head -c 500
curl -i --max-time 120 'https://jingsen.cc/learningcenter/api/english/generate?count=5&mode=passage_cloze' | head -c 500
```

如果能看到你的词库文件、`library_registry.json`、`data/report_history.json`、`data/skills/*.json`，说明词库、Reports 和 Skills 数据都还在。

---

## 宝塔重启

如果 Python 项目没有自动热更新，到宝塔面板：

- `Python 项目管理器`
- 找到项目 `app`
- 点一次 **重启**

然后再执行：

```bash
curl http://127.0.0.1:8088/health
curl -I https://jingsen.cc/learningcenter/
```

---

## SSL 证书正式更新

如果 SSL 证书已经续签或重新签发，正式更新建议走宝塔面板，避免手动改 Nginx 路径出错：

1. 登录宝塔面板。
2. 进入 **网站**，找到 `jingsen.cc` 对应站点。
3. 打开 **SSL** 选项卡。
4. 如果是宝塔自动申请的 Let's Encrypt 证书：
   - 点击 **续签** 或确认新证书已签发。
   - 开启 **强制 HTTPS**。
5. 如果你拿到的是新证书文件：
   - 将 `.crt` / `.pem` 内容粘贴到证书框。
   - 将 `.key` 内容粘贴到私钥框。
   - 保存并部署。
6. 保存后重载 Nginx：

```bash
nginx -t
/etc/init.d/nginx reload
```

7. 验证证书到期时间：

```bash
echo | openssl s_client -connect jingsen.cc:443 -servername jingsen.cc 2>/dev/null | openssl x509 -noout -dates -issuer -subject
curl -I https://jingsen.cc/learningcenter/
```

注意：更新 SSL 不需要覆盖 app 目录，也不要动 `/www/wwwroot/learningcenter/app/data`。

---

## 恢复最新 data 备份

如果发现词库、Skills 或历史报告不对，可以直接恢复最近一次备份：

```bash
set -e

APP_DIR="/www/wwwroot/learningcenter/app"
BACKUP_ROOT="/www/wwwroot/learningcenter/backups"
DATA_BACKUP="$BACKUP_ROOT/data-newest"
CURRENT_BAD_BACKUP="$BACKUP_ROOT/data-current-before-restore"

cd "$APP_DIR"

# 1. 确认目标备份存在
if [ ! -d "$DATA_BACKUP" ]; then
  echo "错误：找不到备份目录：$DATA_BACKUP"
  exit 1
fi

# 2. 先把当前 data 挪走，避免直接删除
if [ -d "data" ]; then
  rm -rf "$CURRENT_BAD_BACKUP"
  mv data "$CURRENT_BAD_BACKUP"
  echo "当前 data 已备份到：$CURRENT_BAD_BACKUP"
fi

# 3. 恢复最新备份
cp -a "$DATA_BACKUP" data

# 4. 修正权限
chown -R www:www data

# 5. 检查恢复结果
echo "已恢复 data："
ls data

echo "检查 library_registry.json："
cat data/library_registry.json | head

echo "检查 report history："
python3 -m json.tool data/report_history.json >/dev/null 2>&1 && echo "report history ok" || echo "当前备份里没有 data/report_history.json"

echo "检查 skills："
ls data/skills 2>/dev/null || echo "当前备份里没有 data/skills"
python3 -m json.tool data/skills/index.json >/dev/null 2>&1 && echo "skills index ok" || true

echo "data 恢复完成。请到宝塔面板重启 Python 项目。"
```

---

## 只恢复最新 report_history.json

如果只是 Daily Reports 出问题，不想动整个 `data/`，可以单独恢复：

```bash
set -e

APP_DIR="/www/wwwroot/learningcenter/app"
BACKUP_ROOT="/www/wwwroot/learningcenter/backups"
REPORT_BACKUP="$BACKUP_ROOT/report-history-newest.json"
REPORT_CURRENT_BACKUP="$BACKUP_ROOT/report-history-current-before-restore.json"

cd "$APP_DIR"

if [ ! -f "$REPORT_BACKUP" ]; then
  echo "错误：找不到备份文件：$REPORT_BACKUP"
  exit 1
fi

mkdir -p data

if [ -f "data/report_history.json" ]; then
  cp -a "data/report_history.json" "$REPORT_CURRENT_BACKUP"
  echo "当前 report_history.json 已备份到：$REPORT_CURRENT_BACKUP"
fi

cp -a "$REPORT_BACKUP" "data/report_history.json"
chown www:www "data/report_history.json"
python3 -m json.tool data/report_history.json >/dev/null && echo "report history restore ok"
```

---

## 部署流程简化建议

如果你觉得现在的流程仍然偏复杂，建议按下面优先级优化：

### 方案 A：保持当前目录结构，但把命令落成服务器脚本（最推荐，改动最小）

做法：

- 把上面的“最安全更新命令”保存成服务器脚本，例如：
  - `/www/wwwroot/learningcenter/update_safe.sh`
- 以后每次上线只执行：

```bash
bash /www/wwwroot/learningcenter/update_safe.sh
```

#### `update_safe.sh` 实际使用方法

首次使用：

1. 先把本仓库里的 `update_safe.sh` 上传到服务器：
   - 建议放到：`/www/wwwroot/learningcenter/update_safe.sh`
2. 给脚本执行权限：

```bash
chmod +x /www/wwwroot/learningcenter/update_safe.sh
```

3. 执行脚本：

```bash
bash /www/wwwroot/learningcenter/update_safe.sh
```

或：

```bash
/www/wwwroot/learningcenter/update_safe.sh
```

执行前建议先确认脚本里的这 3 个变量是否和线上一致：

- `APP_DIR="/www/wwwroot/learningcenter/app"`
- `BRANCH="deploy/tencent-learningcenter-path"`
- `PYTHON_BIN="/www/server/pyporject_evn/versions/3.11.15/bin/python3"`

如果你的服务器项目目录、部署分支或 Python 环境路径不同，先改完再执行。

脚本执行完成后，再到宝塔面板：

1. 重启 Python 项目 `app`
2. 再访问页面或执行健康检查：

```bash
curl http://127.0.0.1:8088/health
```

这个脚本会自动完成以下事情：

- 备份线上真实 `data/` 到 `data-newest`
- 备份线上 `.env` 到 `env-newest`
- 单独备份 `data/report_history.json` 到 `report-history-newest.json`
- 拉取远端最新代码并强制对齐分支
- 恢复线上真实 `data/` 和 `.env`
- 必要时补齐 Git 里的 `data/skills/*`
- 安装 `requirements.txt` 依赖
- 执行本地健康检查

优点：

- 不用每次复制一大段命令
- 不会再手改备份名
- 最符合你现在的使用习惯
- 风险最低，今天就能用

### 方案 B：把持久化数据移出代码目录（中期最优）

做法：

- 把真实数据放到固定目录，例如：
  - `/www/wwwroot/learningcenter/shared/data`
  - `/www/wwwroot/learningcenter/shared/.env`
- 项目里改成软链接：
  - `app/data -> /www/wwwroot/learningcenter/shared/data`
  - `app/.env -> /www/wwwroot/learningcenter/shared/.env`

这样以后部署代码时，`git reset --hard` 只更新代码，不碰真实数据。

优点：

- 部署会大幅简化
- 不再需要“先备份 data 再恢复 data”这一步
- 更适合以后 Reports、Skills、词库继续增长

### 方案 C：做发布目录 + 当前目录软链接（长期最标准）

做法：

- 每次代码发布到新目录，例如：
  - `/www/wwwroot/learningcenter/releases/20260511-2029`
- `current` 软链接指向当前版本
- 持久化数据仍放 `shared/`
- Python 项目始终指向 `current`

优点：

- 回滚最快
- 发布最干净
- 后续多人协作最稳

缺点：

- 需要重新整理宝塔部署方式
- 现在实施成本比方案 A / B 高

### 当前最实用建议

按你的项目现状，建议这样落地：

1. **马上做方案 A**：先把更新命令固化成 `update_safe.sh`。
2. **下一步做方案 B**：把 `data/` 和 `.env` 挪到 `shared/`。
3. 暂时**不用急着做方案 C**，除非后面发布频率明显变高。

---

## 常见错误处理

### 1. `fatal: not a git repository`

说明当前命令没有在 Git 项目目录里执行。

先检查：

```bash
cd /www/wwwroot/learningcenter/app
ls -la .git
```

如果能看到 `.git`，说明目录正确。以后复制完整更新命令，不要只复制中间的 `git fetch` 或 `git pull`。

---

### 2. `fatal: detected dubious ownership`

说明当前登录用户和项目文件所属用户不一致。

不要执行：

```bash
git config --global --add safe.directory /www/wwwroot/learningcenter/app
```

本文件里的安全更新命令已经用：

```bash
sudo -u www -H git -C "$APP_DIR" ...
```

来避免这个问题。

---

### 3. `sudo: command not found`

如果服务器提示没有 `sudo`，先测试：

```bash
su -s /bin/bash www -c "git -C /www/wwwroot/learningcenter/app status"
```

如果这条能运行，把安全更新命令里的 `run_git` 函数替换成：

```bash
run_git() {
  su -s /bin/bash www -c "git -C '$APP_DIR' $*"
}
```

---

### 4. `curl http://127.0.0.1:8088/health` 失败

先到宝塔面板重启 Python 项目 `app`，然后再执行：

```bash
curl http://127.0.0.1:8088/health
```

如果仍失败，检查宝塔 Python 项目日志。

---

### 5. `data/skills` 不存在

如果更新后提示：

```text
ls: cannot access 'data/skills': No such file or directory
```

说明线上 `data/` 是旧备份，且 Git 版本中的 Skills 没有成功补齐。

先检查本次更新暂存的 Git Skills：

```bash
ls /www/wwwroot/learningcenter/backups/skills-from-git-newest
```

如果目录存在，再执行：

```bash
cd /www/wwwroot/learningcenter/app
mkdir -p data/skills
cp -n /www/wwwroot/learningcenter/backups/skills-from-git-newest/* data/skills/
chown -R www:www data/skills
```

`cp -n` 表示只补齐缺失文件，不覆盖已有文件。

---

## 备注

如果以后再次遇到 `openai` 和 `httpx` 版本冲突，补执行：

```bash
/www/server/pyporject_evn/versions/3.11.15/bin/python3 -m pip install --upgrade --force-reinstall "httpx<0.28"
```
