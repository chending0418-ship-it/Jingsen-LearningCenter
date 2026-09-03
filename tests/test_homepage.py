from fastapi.testclient import TestClient

import api.homepage as homepage_api
from main import app
from services.homepage_service import HomepageService


def test_homepage_service_defaults_updates_and_preserves_custom_hero(tmp_path):
    service = HomepageService(tmp_path / "data")

    defaults = service.get_settings()
    assert defaults["headline"].startswith("Curious by nature")
    assert [item["key"] for item in defaults["sections"]] == ["learning", "gallery", "baseball"]
    assert service.hero_path().name == "homepage-hero.webp"

    updated_payload = {
        key: defaults[key]
        for key in ("profile_label", "headline", "introduction", "ticker", "note", "hero_alt", "sections")
    }
    updated_payload["headline"] = "A local test headline."
    updated = service.update_settings(updated_payload)
    assert updated["headline"] == "A local test headline."

    png = b"\x89PNG\r\n\x1a\n" + b"test-image-content"
    with_hero = service.save_hero(png, "image/png")
    assert with_hero["hero_asset"].endswith(".png")
    assert service.hero_path().read_bytes() == png

    reset = service.reset_hero()
    assert reset["hero_asset"] is None
    assert service.hero_path().name == "homepage-hero.webp"


def test_homepage_routes_admin_auth_and_legacy_redirects(tmp_path, monkeypatch):
    service = HomepageService(tmp_path / "data")
    monkeypatch.setattr(homepage_api, "get_homepage_service", lambda: service)

    with TestClient(app, follow_redirects=False) as client:
        assert client.get("/").status_code == 200
        assert client.get("/gallery").status_code == 200
        assert client.get("/baseball").status_code == 200
        assert client.get("/learningcenter").headers["location"] == "/learningcenter/portal"
        learning_portal = client.get("/learningcenter/portal")
        assert learning_portal.status_code == 200
        assert 'href="/"' in learning_portal.text
        assert "BACK2INDEX" in learning_portal.text
        assert "01 / LEARN" in learning_portal.text
        learning_theme = client.get("/static/learning_front_theme.css")
        assert learning_theme.status_code == 200
        assert "--learn-acid" in learning_theme.text

        english_page = client.get("/learningcenter/english")
        assert english_page.status_code == 200
        assert "learning-english" in english_page.text
        assert "BACK2LEARNING" in english_page.text

        chinese_page = client.get("/learningcenter/chinese")
        math_page = client.get("/learningcenter/math")
        assert chinese_page.status_code == 200
        assert math_page.status_code == 200
        assert "learning-construction" in chinese_page.text
        assert "正在建设中" in chinese_page.text
        assert "learning-construction" in math_page.text
        assert client.get("/learningcenter/admin").headers["location"] == "/admin/learningcenter"
        detail_redirect = client.get("/learningcenter/admin/library?id=library-1")
        assert detail_redirect.headers["location"] == "/admin/learningcenter/library?id=library-1"

        public = client.get("/api/site/homepage")
        assert public.status_code == 200
        assert len(public.json()["sections"]) == 3
        assert client.get("/api/admin/homepage").status_code == 401

        assert client.post("/api/admin/session", json={"password": "0418"}).status_code == 200
        current = client.get("/api/admin/homepage").json()
        payload = {
            key: current[key]
            for key in ("profile_label", "headline", "introduction", "ticker", "note", "hero_alt", "sections")
        }
        payload["ticker"] = "TEST / TICKER / COPY ↗"
        payload["note"] = "TEST · NOTE"
        saved = client.put("/api/admin/homepage", json=payload)
        assert saved.status_code == 200
        assert saved.json()["note"] == "TEST · NOTE"
        assert saved.json()["ticker"] == "TEST / TICKER / COPY ↗"

        invalid_link = dict(payload)
        invalid_link["sections"] = [dict(item) for item in payload["sections"]]
        invalid_link["sections"][0]["href"] = "javascript:alert(1)"
        assert client.put("/api/admin/homepage", json=invalid_link).status_code == 422

        png = b"\x89PNG\r\n\x1a\n" + b"route-test"
        uploaded = client.put(
            "/api/admin/homepage/hero",
            content=png,
            headers={"Content-Type": "image/png"},
        )
        assert uploaded.status_code == 200
        hero = client.get("/api/site/homepage/hero")
        assert hero.status_code == 200
        assert hero.content == png
