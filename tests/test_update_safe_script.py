import getpass
import grp
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "update_safe.sh"


def _deployment_env(app_dir: Path, backup_root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "APP_DIR": str(app_dir),
        "BACKUP_ROOT": str(backup_root),
        "PYTHON_BIN": sys.executable,
        "RUN_AS_USER": getpass.getuser(),
        "RUN_AS_GROUP": grp.getgrgid(os.getgid()).gr_name,
        "SKIP_DEPENDENCY_INSTALL": "1",
        "SKIP_HEALTH_CHECK": "1",
    }


def _minimal_app(tmp_path: Path) -> tuple[Path, Path]:
    app_dir = tmp_path / "app"
    backup_root = tmp_path / "backups"
    (app_dir / ".git").mkdir(parents=True)
    (app_dir / "data").mkdir()
    (app_dir / "data" / "library_registry.json").write_text(
        json.dumps({"version": 1, "libraries": []}),
        encoding="utf-8",
    )
    return app_dir, backup_root


def test_update_safe_stops_before_git_when_archive_is_missing(tmp_path):
    app_dir, backup_root = _minimal_app(tmp_path)

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env=_deployment_env(app_dir, backup_root),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "library_archive.json" in result.stderr
    assert "INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING=1" in result.stderr
    assert not (app_dir / "data" / "library_archive.json").exists()


def test_first_archive_initialization_is_backed_up_before_git_sync(tmp_path):
    app_dir, backup_root = _minimal_app(tmp_path)
    environment = _deployment_env(app_dir, backup_root)
    environment["INITIALIZE_LIBRARY_ARCHIVE_IF_MISSING"] = "1"

    result = subprocess.run(
        ["bash", str(SCRIPT_PATH)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    # 这个最小测试仓库没有真实 Git 元数据，脚本应在完成快照后停在 fetch。
    assert result.returncode != 0
    archive_payload = json.loads(
        (app_dir / "data" / "library_archive.json").read_text(encoding="utf-8")
    )
    assert archive_payload == {"version": 1, "libraries": []}

    releases = list((backup_root / "releases").iterdir())
    assert len(releases) == 1
    snapshot = releases[0]
    assert (snapshot / "data" / "library_registry.json").is_file()
    assert (snapshot / "data" / "library_archive.json").is_file()
    receipt = json.loads((snapshot / "library-data-backup.json").read_text(encoding="utf-8"))
    assert {item["path"] for item in receipt["files"]} == {
        "library_registry.json",
        "library_archive.json",
    }
