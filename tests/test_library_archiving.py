import sqlite3
from pathlib import Path

import pytest

from config import config
from services.library_admin_service import LibraryAdminService


def test_archive_moves_library_out_of_active_registry_and_restores_without_data_loss(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", str(data_dir))
    service = LibraryAdminService()

    created = service.create_library(
        subject="english",
        name="archive-me",
        items=["alpha", "beta", "gamma"],
        enabled=True,
    )
    library_id = created["id"]
    assert service.get_enabled_library_names("english") == ["archive-me"]

    archived = service.set_library_archived(library_id, True)
    assert archived["archived"] is True
    assert archived["enabled"] is False
    assert archived["total_items"] == 3

    with sqlite3.connect(service._database.path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM libraries WHERE archived=0").fetchone()[0] == 0
        assert connection.execute("SELECT archived FROM libraries WHERE id=?", (library_id,)).fetchone()[0] == 1
        assert [row[0] for row in connection.execute("SELECT content FROM library_items WHERE library_id=? ORDER BY sort_order", (library_id,))] == ["alpha", "beta", "gamma"]
    assert not (data_dir / "archive-me.txt").exists()

    assert service.list_libraries() == []
    assert service.list_libraries(include_archived=True)[0]["archived"] is True
    assert service.get_enabled_library_names("english") == []
    with pytest.raises(ValueError, match="已归档"):
        service.resolve_enabled_library("english", "archive-me")

    restored = service.set_library_archived(library_id, False)
    assert restored["id"] == library_id
    assert restored["archived"] is False
    assert restored["enabled"] is False
    assert service.get_library(library_id)["items"] == ["alpha", "beta", "gamma"]
    assert not (data_dir / "archive-me.txt").exists()

    with sqlite3.connect(service._database.path) as connection:
        assert connection.execute("SELECT archived FROM libraries WHERE id=?", (library_id,)).fetchone()[0] == 0
    service.set_library_enabled(library_id, True)
    assert service.get_enabled_library_names("english") == ["archive-me"]
