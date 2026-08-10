import json

import pytest

from scripts.validate_persistent_data import (
    build_manifest,
    validate_required_files,
    verify_manifest,
)


def test_required_library_files_and_subset_manifest_are_verified(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "library_registry.json").write_text(
        json.dumps({"version": 1, "libraries": [{"id": "active"}]}),
        encoding="utf-8",
    )
    (data_dir / "library_archive.json").write_text(
        json.dumps({"version": 1, "libraries": [{"id": "archived"}]}),
        encoding="utf-8",
    )

    required = validate_required_files(
        data_dir,
        ["library_registry.json", "library_archive.json"],
    )
    assert required == ["library_registry.json", "library_archive.json"]

    manifest = build_manifest(data_dir)
    manifest["files"] = [
        item
        for item in manifest["files"]
        if item["path"] in {"library_registry.json", "library_archive.json"}
    ]
    manifest_path = tmp_path / "library-data-backup.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    verify_manifest(data_dir, manifest_path)


def test_required_library_archive_missing_or_unsafe_path_fails(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "library_registry.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="library_archive.json"):
        validate_required_files(
            data_dir,
            ["library_registry.json", "library_archive.json"],
        )

    with pytest.raises(ValueError, match="不安全"):
        validate_required_files(data_dir, ["../library_archive.json"])
