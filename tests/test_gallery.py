from fastapi.testclient import TestClient

import api.gallery as gallery_api
from main import app
from services.gallery_service import GalleryService


PNG = b"\x89PNG\r\n\x1a\n" + b"gallery-test-image"


def test_gallery_service_create_update_remove_and_keep_asset(tmp_path):
    service = GalleryService(tmp_path / "data")
    assert service.list_items() == []

    created = service.create_item(
        PNG,
        "image/png",
        title="First frame",
        caption="A test photograph",
        location="Beijing",
        shot_date="2026-09-03",
        alt="A test frame",
    )
    assert created["title"] == "First frame"
    assert created["image_url"].endswith(f"/{created['id']}/image")
    asset_path = service.image_path(created["id"])
    assert asset_path.read_bytes() == PNG

    updated = service.update_item(created["id"], {
        "title": "Updated frame",
        "caption": "Updated caption",
        "location": "Shanghai",
        "shot_date": None,
        "alt": "Updated description",
    })
    assert updated["title"] == "Updated frame"
    assert updated["shot_date"] is None

    removed = service.remove_item(created["id"])
    assert removed["id"] == created["id"]
    assert service.list_items() == []
    assert asset_path.is_file()


def test_gallery_routes_and_admin_information_architecture(tmp_path, monkeypatch):
    service = GalleryService(tmp_path / "data")
    monkeypatch.setattr(gallery_api, "get_gallery_service", lambda: service)

    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/gallery").status_code == 200
        assert client.get("/api/site/gallery").json() == {"items": [], "total": 0}
        assert client.get("/admin").status_code == 200

        protected = client.get("/admin/learningcenter")
        assert protected.status_code == 303
        assert protected.headers["location"].startswith("/admin?next=")
        assert client.get("/admin/gallery").status_code == 303
        assert client.get("/api/admin/gallery").status_code == 401
        assert client.get("/api/admin/libraries").status_code == 401
        assert client.patch("/api/skills/example", json={"enabled": False}).status_code == 401

        assert client.post("/api/admin/session", json={"password": "0418"}).status_code == 200
        assert client.get("/admin/index").status_code == 200
        learning_admin = client.get("/admin/learningcenter")
        assert learning_admin.status_code == 200
        assert "BACK2ADMIN" in learning_admin.text
        assert "Learning Center" in learning_admin.text
        theme = client.get("/static/admin_learning_theme.css")
        assert theme.status_code == 200
        assert "--lc-acid" in theme.text
        for path in (
            "/admin/learningcenter/new",
            "/admin/learningcenter/skills",
            "/admin/learningcenter/todo",
        ):
            page = client.get(path)
            assert page.status_code == 200
            assert "admin-context-line" in page.text
            assert "BACK2ADMIN" in page.text

        models_page = client.get("/admin/learningcenter/models")
        assert models_page.status_code == 200
        assert "admin-context-line" in models_page.text
        assert 'id="header-save-button"' not in models_page.text
        assert client.get("/admin/gallery").status_code == 200
        assert client.get("/admin/baseball").status_code == 200

        uploaded = client.post(
            "/api/admin/gallery/items",
            params={
                "title": "Route frame",
                "caption": "Route caption",
                "location": "Hangzhou",
                "shot_date": "2026-09-03",
                "alt": "A route test frame",
            },
            content=PNG,
            headers={"Content-Type": "image/png"},
        )
        assert uploaded.status_code == 201
        item = uploaded.json()
        feed = client.get("/api/site/gallery").json()
        assert feed["total"] == 1
        assert feed["items"][0]["title"] == "Route frame"
        assert client.get(item["image_url"]).content == PNG

        changed = client.put(
            f"/api/admin/gallery/items/{item['id']}",
            json={
                "title": "Edited frame",
                "caption": "",
                "location": "",
                "shot_date": None,
                "alt": "Edited route frame",
            },
        )
        assert changed.status_code == 200
        assert changed.json()["title"] == "Edited frame"

        assert client.delete(f"/api/admin/gallery/items/{item['id']}").status_code == 200
        assert client.get("/api/site/gallery").json()["total"] == 0

        assert client.get("/admin/homepage").headers["location"] == "/admin/index"
        assert client.get("/admin/todo").headers["location"] == "/admin/learningcenter/todo"
