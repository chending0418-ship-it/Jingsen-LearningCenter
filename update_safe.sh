#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/www/wwwroot/learningcenter/app"
BACKUP_ROOT="/www/wwwroot/learningcenter/backups"
BRANCH="deploy/tencent-learningcenter-path"
PYTHON_BIN="/www/server/pyporject_evn/versions/3.11.15/bin/python3"
DATA_BACKUP="$BACKUP_ROOT/data-newest"
ENV_BACKUP="$BACKUP_ROOT/env-newest"
REPORT_BACKUP="$BACKUP_ROOT/report-history-newest.json"
SKILLS_GIT_BACKUP="$BACKUP_ROOT/skills-from-git-newest"

log() {
  echo "[update_safe] $*"
}

run_git() {
  if command -v sudo >/dev/null 2>&1; then
    sudo -u www -H git -C "$APP_DIR" "$@"
  else
    su -s /bin/bash www -c "git -C '$APP_DIR' $*"
  fi
}

log "开始执行安全更新脚本"
cd "$APP_DIR"
mkdir -p "$BACKUP_ROOT"

if [ ! -d ".git" ]; then
  echo "错误：$APP_DIR 不是 Git 项目，未找到 .git。"
  echo "请先确认 APP_DIR 是否正确。"
  exit 1
fi

if [ -d "data" ]; then
  rm -rf "$DATA_BACKUP"
  cp -a data "$DATA_BACKUP"
  log "已备份线上 data 到: $DATA_BACKUP"
else
  log "警告：当前项目目录没有 data 文件夹，将继续更新。"
fi

if [ -f "data/report_history.json" ]; then
  cp -a "data/report_history.json" "$REPORT_BACKUP"
  log "已单独备份 report_history.json 到: $REPORT_BACKUP"
else
  log "提示：当前没有 data/report_history.json，跳过单独备份。"
fi

if [ -f ".env" ]; then
  cp -a .env "$ENV_BACKUP"
  log "已备份线上 .env 到: $ENV_BACKUP"
else
  log "警告：当前项目目录没有 .env 文件，将继续更新。"
fi

log "拉取远端最新代码"
run_git fetch origin
run_git checkout "$BRANCH"
run_git reset --hard "origin/$BRANCH"

if [ -d "data/skills" ]; then
  rm -rf "$SKILLS_GIT_BACKUP"
  mkdir -p "$SKILLS_GIT_BACKUP"
  cp -a data/skills/. "$SKILLS_GIT_BACKUP/"
  log "已暂存 Git 版本 Skills 到: $SKILLS_GIT_BACKUP"
fi

run_git clean -fd -e data -e .env

if [ -d "$DATA_BACKUP" ]; then
  rm -rf data
  cp -a "$DATA_BACKUP" data
  log "已恢复线上真实 data 到项目目录。"
else
  mkdir -p data
  log "没有找到更新前 data 备份，已创建空 data 目录。"
fi

if [ -d "$SKILLS_GIT_BACKUP" ]; then
  mkdir -p data/skills
  for f in index.json map_language_arts.json map_reading.json word_vocabulary_skills.json; do
    if [ ! -f "data/skills/$f" ] && [ -f "$SKILLS_GIT_BACKUP/$f" ]; then
      cp -a "$SKILLS_GIT_BACKUP/$f" "data/skills/$f"
      log "已补齐缺失 Skills 文件: data/skills/$f"
    fi
  done
fi

if [ -f "$ENV_BACKUP" ]; then
  cp -a "$ENV_BACKUP" .env
  log "已恢复线上 .env。"
fi

chown -R www:www "$APP_DIR"

log "安装/更新依赖"
"$PYTHON_BIN" -m pip install -r requirements.txt

log "执行健康检查"
curl http://127.0.0.1:8088/health

log "更新完成。请到宝塔面板重启 Python 项目，然后再检查公网页面。"
