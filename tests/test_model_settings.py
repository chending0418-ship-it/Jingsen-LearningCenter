import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

import services.model_settings_service as model_settings_module
from config import Config, config
from core.ai_generator import AIGenerator
from main import app
from services.model_settings_service import ModelSettingsService


def test_model_catalog_uses_openai_compatible_endpoint_and_normalizes_response(tmp_path):
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "gpt-test-b", "object": "model", "owned_by": "provider-b"},
                    {"id": "gpt-test-a", "object": "model", "owned_by": "provider-a"},
                    {"id": "gpt-test-a", "object": "model", "owned_by": "duplicate"},
                ],
            },
        )

    service = ModelSettingsService(
        settings_path=str(tmp_path / "data" / "model-settings.json"),
        api_key="test-secret-key",
        base_url="https://api.gpt.ge",
        fallback_model="gpt-fallback",
        http_transport=httpx.MockTransport(handler),
    )

    catalog = asyncio.run(service.fetch_available_models())

    assert observed == {
        "url": "https://api.gpt.ge/v1/models",
        "authorization": "Bearer test-secret-key",
    }
    assert [model["id"] for model in catalog["models"]] == ["gpt-test-a", "gpt-test-b"]
    assert catalog["selected_model"] == "gpt-fallback"
    assert catalog["selected_available"] is False
    assert "test-secret-key" not in str(catalog)


def test_root_provider_url_is_normalized_for_chat_completions(monkeypatch):
    monkeypatch.setattr(Config, "OPENAI_BASE_URL", "https://api.gpt.ge")
    assert Config.fix_base_url() == "https://api.gpt.ge/v1"

    monkeypatch.setattr(Config, "OPENAI_BASE_URL", "https://api.gpt.ge/v1")
    assert Config.fix_base_url() == "https://api.gpt.ge/v1"


def test_model_selection_persists_and_ai_generator_reads_it_dynamically(tmp_path, monkeypatch):
    settings_path = tmp_path / "data" / "model-settings.json"
    service = ModelSettingsService(
        settings_path=str(settings_path),
        api_key="test-key",
        base_url="https://api.gpt.ge/v1",
        fallback_model="gpt-fallback",
    )
    monkeypatch.setattr("core.ai_generator.get_model_settings_service", lambda: service)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(config, "OPENAI_BASE_URL", "https://api.gpt.ge/v1")

    generator = AIGenerator()
    assert generator.model == "gpt-fallback"

    saved = service.set_selected_model("gpt-selected")
    assert saved["source"] == "admin"
    assert generator.model == "gpt-selected"

    reloaded = ModelSettingsService(
        settings_path=str(settings_path),
        api_key="test-key",
        base_url="https://api.gpt.ge",
        fallback_model="another-fallback",
    )
    assert reloaded.get_selected_model() == "gpt-selected"
    assert not settings_path.exists()
    assert (settings_path.parent / "learning-center.sqlite3").is_file()
    assert settings_path.parent == Path(tmp_path / "data")


def test_ai_generator_uses_minimal_reasoning_for_gpt5_models(monkeypatch):
    observed = []

    def create(**kwargs):
        observed.append(kwargs)
        return "response"

    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    generator = AIGenerator()
    generator.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )

    result = asyncio.run(
        generator._create_chat_completion(
            model="gpt-5-mini-fast",
            messages=[],
        )
    )

    assert result == "response"
    assert observed[0]["reasoning_effort"] == "minimal"


def test_ai_generator_does_not_send_reasoning_effort_to_other_models(monkeypatch):
    observed = []

    def create(**kwargs):
        observed.append(kwargs)
        return "response"

    monkeypatch.setattr(config, "OPENAI_API_KEY", "test-key")
    generator = AIGenerator()
    generator.client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create),
        )
    )

    asyncio.run(
        generator._create_chat_completion(
            model="claude-opus-4-6-medium",
            messages=[],
        )
    )

    assert "reasoning_effort" not in observed[0]


def test_admin_model_api_requires_session_and_saves_only_available_model(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "gpt-alpha"}, {"id": "gpt-beta"}]},
        )

    service = ModelSettingsService(
        settings_path=str(tmp_path / "data" / "model-settings.json"),
        api_key="server-only-key",
        base_url="https://api.gpt.ge",
        fallback_model="gpt-alpha",
        http_transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(model_settings_module, "_model_settings_service", service)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "0418")
    monkeypatch.setattr(config, "ADMIN_SESSION_SECRET", "test-session-secret")

    with TestClient(app) as client:
        assert client.get("/api/admin/models").status_code == 401
        assert client.post("/api/admin/session", json={"password": "0418"}).status_code == 200

        catalog = client.get("/api/admin/models")
        assert catalog.status_code == 200
        assert catalog.json()["total"] == 2
        assert "server-only-key" not in catalog.text

        unavailable = client.put("/api/admin/model-settings", json={"model_id": "missing"})
        assert unavailable.status_code == 400

        saved = client.put("/api/admin/model-settings", json={"model_id": "gpt-beta"})
        assert saved.status_code == 200
        assert saved.json()["selected_model"] == "gpt-beta"
        assert saved.json()["source"] == "admin"

        prefixed = client.get("/learningcenter/api/admin/model-settings")
        assert prefixed.status_code == 200
        assert prefixed.json()["selected_model"] == "gpt-beta"
