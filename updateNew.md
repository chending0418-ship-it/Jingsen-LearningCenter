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

注意：`data/skills/*.json` 以后也属于线上生产数据。Admin Skills 页面可能会修改这些文件的启用状态，所以更新时不能直接覆盖线上已有的 `data/skills/`。

---

## 最安全更新命令

> 重要：请复制下面整段命令执行，不要只复制其中某一小段。

这版命令会：

1. 备份线上真实 `data/`。
2. 备份线上 `.env`。
3. 用 `www` 用户同步 Git 代码，避免 `dubious ownership`。
4. 暂存 Git 版本里的 `data/skills/`，用于首次上线 Skills 文件。
5. 恢复更新前的线上真实 `data/`，确保词库和报告不被覆盖。
6. 如果线上原本没有 `data/skills/` 或缺少某个 skills 文件，则从 Git 版本补齐缺失文件。
7. 不覆盖线上已有的 `data/skills/*.json`。

```bash
set -e

APP_DIR="/www/wwwroot/learningcenter/app"
BACKUP_ROOT="/www/wwwroot/learningcenter/backups"
BRANCH="deploy/tencent-learningcenter-path"
PYTHON_BIN="/www/server/pyporject_evn/versions/3.11.15/bin/python3"
TS=$(date +%Y%m%d-%H%M%S)

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
  cp -a data "$BACKUP_ROOT/data-before-update-$TS"
  echo "已备份线上 data 到: $BACKUP_ROOT/data-before-update-$TS"
else
  echo "警告：当前项目目录没有 data 文件夹，将继续更新。"
fi

# 2. 备份线上 .env，避免代码同步时影响线上环境变量
if [ -f ".env" ]; then
  cp -a .env "$BACKUP_ROOT/env-before-update-$TS"
  echo "已备份线上 .env 到: $BACKUP_ROOT/env-before-update-$TS"
else
  echo "警告：当前项目目录没有 .env 文件，将继续更新。"
fi

# 3. 拉取远端最新代码信息
run_git fetch origin

# 4. 切到部署分支，并强制同步到远端最新版本
# 说明：这会覆盖代码文件的本地改动，但 data 和 .env 已经提前备份，后面会恢复。
run_git checkout "$BRANCH"
run_git reset --hard "origin/$BRANCH"

# 5. 暂存 Git 版本里的 data/skills，用于首次上线或补齐缺失的 Skills 文件
if [ -d "data/skills" ]; then
  mkdir -p "$BACKUP_ROOT/skills-from-git-$TS"
  cp -a data/skills/. "$BACKUP_ROOT/skills-from-git-$TS/"
  echo "已暂存 Git 版本 Skills 到: $BACKUP_ROOT/skills-from-git-$TS"
fi

# 6. 清理未跟踪的临时文件，但保留 data 和 .env
run_git clean -fd -e data -e .env

# 7. 恢复更新前的线上真实 data，确保线上词库、报告和已维护 Skills 不被覆盖
if [ -d "$BACKUP_ROOT/data-before-update-$TS" ]; then
  rm -rf data
  cp -a "$BACKUP_ROOT/data-before-update-$TS" data
  echo "已恢复线上真实 data 到项目目录。"
else
  mkdir -p data
  echo "没有找到更新前 data 备份，已创建空 data 目录。"
fi

# 8. 如果线上 data 缺少 skills 文件，则从 Git 版本补齐；已有文件不覆盖
if [ -d "$BACKUP_ROOT/skills-from-git-$TS" ]; then
  mkdir -p data/skills
  for f in index.json map_language_arts.json map_reading.json word_vocabulary_skills.json; do
    if [ ! -f "data/skills/$f" ] && [ -f "$BACKUP_ROOT/skills-from-git-$TS/$f" ]; then
      cp -a "$BACKUP_ROOT/skills-from-git-$TS/$f" "data/skills/$f"
      echo "已补齐缺失 Skills 文件: data/skills/$f"
    fi
  done
fi

# 9. 恢复线上 .env
if [ -f "$BACKUP_ROOT/env-before-update-$TS" ]; then
  cp -a "$BACKUP_ROOT/env-before-update-$TS" .env
  echo "已恢复线上 .env。"
fi

# 10. 确保 app 目录主要文件仍归 www 用户所有，方便宝塔 Python 项目运行
chown -R www:www "$APP_DIR"

# 11. 安装/更新依赖
"$PYTHON_BIN" -m pip install -r requirements.txt

# 12. 健康检查
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

echo "检查公网："
curl -I https://jingsen.cc/learningcenter/
curl -i --max-time 90 'https://jingsen.cc/learningcenter/api/english/generate?count=1&mode=cloze' | head -c 500
```

如果能看到你的词库文件、`library_registry.json`、`data/skills/*.json`，说明词库和 Skills 数据都还在。

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

## 恢复指定 data 备份

如果发现词库、Skills 或历史报告不对，可以恢复某个备份，例如：

```text
data-before-update-20260510-222525
```

执行下面整段：

```bash
set -e

APP_DIR="/www/wwwroot/learningcenter/app"
BACKUP_ROOT="/www/wwwroot/learningcenter/backups"
BACKUP_NAME="data-before-update-20260510-222525"
TS=$(date +%Y%m%d-%H%M%S)

cd "$APP_DIR"

# 1. 确认目标备份存在
if [ ! -d "$BACKUP_ROOT/$BACKUP_NAME" ]; then
  echo "错误：找不到备份目录：$BACKUP_ROOT/$BACKUP_NAME"
  echo "请先执行：ls $BACKUP_ROOT"
  exit 1
fi

# 2. 先把当前 data 挪走，避免直接删除
if [ -d "data" ]; then
  mv data "$BACKUP_ROOT/data-bad-$TS"
  echo "当前 data 已备份到：$BACKUP_ROOT/data-bad-$TS"
fi

# 3. 恢复指定备份
cp -a "$BACKUP_ROOT/$BACKUP_NAME" data

# 4. 修正权限
chown -R www:www data

# 5. 检查恢复结果
echo "已恢复 data："
ls data

echo "检查 library_registry.json："
cat data/library_registry.json | head

echo "检查 skills："
ls data/skills 2>/dev/null || echo "当前备份里没有 data/skills"

python3 -m json.tool data/skills/index.json >/dev/null 2>&1 && echo "skills index ok" || true

echo "data 恢复完成。请到宝塔面板重启 Python 项目。"
```

如果要恢复其他备份，只改这一行：

```bash
BACKUP_NAME="data-before-update-你的时间戳"
```

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
ls /www/wwwroot/learningcenter/backups/skills-from-git-*
```

找到最新一个目录后执行：

```bash
cd /www/wwwroot/learningcenter/app
mkdir -p data/skills
cp -n /www/wwwroot/learningcenter/backups/skills-from-git-最新时间戳/* data/skills/
chown -R www:www data/skills
```

`cp -n` 表示只补齐缺失文件，不覆盖已有文件。

---

## 备注

如果以后再次遇到 `openai` 和 `httpx` 版本冲突，补执行：

```bash
/www/server/pyporject_evn/versions/3.11.15/bin/python3 -m pip install --upgrade --force-reinstall "httpx<0.28"
```
