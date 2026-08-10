#!/usr/bin/env bash
set -Eeuo pipefail

# 可通过环境变量覆盖，便于测试或迁移服务器目录。
APP_DIR="${APP_DIR:-/www/wwwroot/learningcenter/app}"
BACKUP_ROOT="${BACKUP_ROOT:-/www/wwwroot/learningcenter/backups}"
BRANCH="${BRANCH:-deploy/tencent-learningcenter-path}"
PYTHON_BIN="${PYTHON_BIN:-/www/server/pyporject_evn/versions/3.11.15/bin/python3}"
RUN_AS_USER="${RUN_AS_USER:-www}"
RUN_AS_GROUP="${RUN_AS_GROUP:-$RUN_AS_USER}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8088/health}"
SKIP_DEPENDENCY_INSTALL="${SKIP_DEPENDENCY_INSTALL:-0}"
SKIP_HEALTH_CHECK="${SKIP_HEALTH_CHECK:-0}"
INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING="${INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING:-0}"

DEPLOY_STAMP="$(date +%Y%m%d-%H%M%S)-$$"
SNAPSHOT_DIR="$BACKUP_ROOT/releases/$DEPLOY_STAMP"
DATA_SNAPSHOT="$SNAPSHOT_DIR/data"
ENV_SNAPSHOT="$SNAPSHOT_DIR/app.env"
DATA_MANIFEST="$SNAPSHOT_DIR/data-manifest.json"
LIBRARY_DATA_RECEIPT="$SNAPSHOT_DIR/library-data-backup.json"
LATEST_LINK="$BACKUP_ROOT/latest"
CODE_DATA_TEMP=""
CRITICAL_LIBRARY_FILES=("library_registry.json" "library_archive.json")

log() {
  echo "[update_safe] $*"
}

fail() {
  echo "[update_safe] 错误：$*" >&2
  exit 1
}

cleanup() {
  if [ -n "$CODE_DATA_TEMP" ] && [ -d "$CODE_DATA_TEMP" ]; then
    rm -rf "$CODE_DATA_TEMP"
  fi
}
trap cleanup EXIT

run_git() {
  if [ "$(id -un)" = "$RUN_AS_USER" ]; then
    git -C "$APP_DIR" "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo -u "$RUN_AS_USER" -H git -C "$APP_DIR" "$@"
  else
    su -s /bin/bash "$RUN_AS_USER" -c "git -C '$APP_DIR' $*"
  fi
}

require_critical_library_files() {
  local root="$1"
  local label="$2"
  local relative
  for relative in "${CRITICAL_LIBRARY_FILES[@]}"; do
    [ -f "$root/$relative" ] || fail "$label 缺少关键词库数据: $root/$relative"
  done
}

initialize_library_archive_if_requested() {
  local archive_path="$APP_DIR/data/library_archive.json"
  if [ -f "$archive_path" ]; then
    return
  fi
  if [ "$INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING" != "1" ]; then
    fail "缺少 ${archive_path}。若确认这是词库归档功能首次上线且从未产生归档数据，请仅本次使用 INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING=1；否则应先从备份恢复。"
  fi
  "$PYTHON_BIN" - "$archive_path" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

target = Path(sys.argv[1])
target.parent.mkdir(parents=True, exist_ok=True)
descriptor, temporary_name = tempfile.mkstemp(prefix=".library-archive-init-", suffix=".json", dir=target.parent)
try:
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump({"version": 1, "libraries": []}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary_name, target)
finally:
    if os.path.exists(temporary_name):
        os.unlink(temporary_name)
PY
  log "已按首次上线选项初始化空归档文件: $archive_path"
}

write_library_backup_receipt() {
  "$PYTHON_BIN" - "$DATA_SNAPSHOT" "$LIBRARY_DATA_RECEIPT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
files = []
for relative in ("library_registry.json", "library_archive.json"):
    path = root / relative
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({"path": relative, "size": path.stat().st_size, "sha256": digest})
receipt_path.write_text(
    json.dumps({"version": 1, "root": "data", "files": files}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
}

log "开始安全更新：代码与服务器数据分离"
[ -d "$APP_DIR" ] || fail "项目目录不存在: $APP_DIR"
[ -d "$APP_DIR/.git" ] || fail "$APP_DIR 不是 Git 项目"
[ -x "$PYTHON_BIN" ] || fail "Python 不可执行: $PYTHON_BIN"

cd "$APP_DIR"
mkdir -p "$BACKUP_ROOT/releases"
mkdir -p "$SNAPSHOT_DIR"

# 归档功能首次上线时允许显式创建空文件；之后缺失必须视为数据事故并停止部署。
[ -f "data/library_registry.json" ] || fail "缺少活动词库注册文件: $APP_DIR/data/library_registry.json"
initialize_library_archive_if_requested
require_critical_library_files "$APP_DIR/data" "发布前检查"

# 1. 发布前对整个 data 做不可覆盖的版本化快照。
if [ -d "data" ]; then
  cp -a "data" "$DATA_SNAPSHOT"
  log "已快照全部服务器数据: $DATA_SNAPSHOT"
else
  mkdir -p "$DATA_SNAPSHOT"
  log "当前没有 data，已记录空数据快照"
fi

require_critical_library_files "$DATA_SNAPSHOT" "发布前快照"
for relative in "${CRITICAL_LIBRARY_FILES[@]}"; do
  cmp -s "$APP_DIR/data/$relative" "$DATA_SNAPSHOT/$relative" \
    || fail "关键词库数据快照与源文件不一致: $relative"
  log "已确认关键词库数据进入快照: $DATA_SNAPSHOT/$relative"
done
write_library_backup_receipt
log "词库专项 SHA-256 备份凭据: $LIBRARY_DATA_RECEIPT"

if [ -f ".env" ]; then
  cp -a ".env" "$ENV_SNAPSHOT"
  chmod 600 "$ENV_SNAPSHOT"
  log "已快照 .env"
fi

if [ -f "scripts/validate_persistent_data.py" ]; then
  "$PYTHON_BIN" scripts/validate_persistent_data.py "$DATA_SNAPSHOT" --manifest-out "$DATA_MANIFEST"
else
  # 首次升级到新部署方案时，至少先验证所有 JSON 可解析。
  "$PYTHON_BIN" - "$DATA_SNAPSHOT" "$DATA_MANIFEST" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
manifest_path = Path(sys.argv[2])
files = []
for path in sorted(item for item in root.rglob("*") if item.is_file()):
    relative = path.relative_to(root).as_posix()
    if path.suffix == ".json":
        with path.open("r", encoding="utf-8") as handle:
            json.load(handle)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    files.append({"path": relative, "size": path.stat().st_size, "sha256": digest})
manifest_path.write_text(
    json.dumps({"version": 1, "root": "data", "files": files}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY
fi

ln -sfn "$SNAPSHOT_DIR" "$LATEST_LINK"
log "最新快照链接: $LATEST_LINK"

# 2. 同步代码。真实数据已在 APP_DIR 外部完成快照。
log "同步远端分支: $BRANCH"
run_git fetch origin
run_git checkout "$BRANCH"
run_git reset --hard "origin/$BRANCH"

# 暂存新代码版本自带的数据种子，恢复真实数据后只补缺，不覆盖。
CODE_DATA_TEMP="$(mktemp -d "$BACKUP_ROOT/.code-data.XXXXXX")"
if [ -d "data" ]; then
  cp -a "data/." "$CODE_DATA_TEMP/"
fi

run_git clean -fd -e .env

# 3. 原样恢复发布前的整个 data；词库、Skills、Reports、Todo 一起恢复。
rm -rf "$APP_DIR/data"
cp -a "$DATA_SNAPSHOT" "$APP_DIR/data"
log "已恢复发布前服务器 data"

# 新版本新增的种子文件只在服务器数据中不存在时补入。
if [ -d "$CODE_DATA_TEMP" ]; then
  "$PYTHON_BIN" scripts/merge_missing_data.py "$CODE_DATA_TEMP" "$APP_DIR/data"
fi

if [ -f "$ENV_SNAPSHOT" ]; then
  cp -a "$ENV_SNAPSHOT" "$APP_DIR/.env"
  log "已恢复 .env"
fi

# 4. 清单校验保证发布前已有的每个数据文件都还在且内容未变化。
"$PYTHON_BIN" scripts/validate_persistent_data.py \
  "$APP_DIR/data" \
  --verify-manifest "$DATA_MANIFEST" \
  --verify-manifest "$LIBRARY_DATA_RECEIPT" \
  --require-file "library_registry.json" \
  --require-file "library_archive.json"
log "持久数据清单验证通过"

chown -R "$RUN_AS_USER:$RUN_AS_GROUP" "$APP_DIR"

if [ "$SKIP_DEPENDENCY_INSTALL" != "1" ]; then
  log "安装/更新依赖"
  "$PYTHON_BIN" -m pip install -r requirements.txt
else
  log "已按配置跳过依赖安装"
fi

# 导入应用会执行 Todo JSON 启动校验，并在首次上线时创建独立目录默认文件。
log "执行应用导入和 Todo 存储校验"
"$PYTHON_BIN" -c "from main import app; from services.learning_todo_service import get_learning_todo_service; get_learning_todo_service().validate_storage(); print(app.title)"
"$PYTHON_BIN" scripts/validate_persistent_data.py \
  "$APP_DIR/data" \
  --require-file "library_registry.json" \
  --require-file "library_archive.json" \
  --require-file "learning-todo/points-ledger.json"

# 这里检查当前进程是否仍可用；代码更新后仍需在宝塔重启 Python 项目。
if [ "$SKIP_HEALTH_CHECK" != "1" ]; then
  log "检查当前服务健康状态"
  curl -fsS "$HEALTH_URL"
  echo
else
  log "已按配置跳过当前进程健康检查"
fi

log "安全更新完成，快照保留在: $SNAPSHOT_DIR"
log "请在宝塔重启 Python 项目，然后再次运行健康检查和页面验收。"
