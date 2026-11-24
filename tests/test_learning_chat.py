import json
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import learning_chat as api
from config import config
from database import database_for_data_root
from services import learning_chat_service as chat

ROOT = "/learningcenter/api/learning-chat"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(tmp_path / "chat.sqlite3"))
    monkeypatch.setattr(config, "FAMILY_CHAT_PASSWORD", "测试家庭学习口令")
    monkeypatch.setattr(config, "ADMIN_COOKIE_SECURE", False)
    app = FastAPI()
    app.include_router(api.router, prefix="/learningcenter")
    return TestClient(app)


def unlock(client):
    return client.post(ROOT + "/login", json={"password": config.FAMILY_CHAT_PASSWORD})


def events(response):
    assert response.status_code == 200
    return [json.loads(line) for line in response.text.splitlines()]


def test_private_access_and_rotation(client, monkeypatch):
    for method, route in [("get","/workspace"),("post","/projects"),("get","/threads/" + str(uuid4())),
                          ("post","/threads/" + str(uuid4()) + "/turns")]:
        assert client.request(method, ROOT + route).status_code == 401
    assert unlock(client).headers["set-cookie"].count("HttpOnly") == 1
    assert client.get(ROOT + "/workspace").headers["cache-control"] == "no-store"
    assert client.get(ROOT + "/workspace", headers={"Sec-Fetch-Site":"cross-site"}).status_code == 403
    token = client.cookies.get(api.sessions.COOKIE)
    client.post(ROOT + "/logout")
    client.cookies.set(api.sessions.COOKIE, token)
    assert client.get(ROOT + "/workspace").status_code == 401
    client.cookies.clear()
    unlock(client)
    monkeypatch.setattr(config, "FAMILY_CHAT_PASSWORD", "changed")
    assert client.get(ROOT + "/workspace").status_code == 401
    monkeypatch.setattr(config, "FAMILY_CHAT_PASSWORD", "")
    assert client.post(ROOT + "/login",json={"password":"anything"}).status_code == 503


def test_limits_password_attempts(client):
    for _ in range(10):
        assert client.post(ROOT + "/login",json={"password":"wrong"}).status_code == 401
    assert unlock(client).status_code == 429


def test_multi_turn_project_instructions_and_replay(client, monkeypatch):
    calls = []
    async def chunks(messages):
        calls.append(messages)
        yield "第一步"
        yield "，画图。"
    monkeypatch.setattr(api,"model_chunks",chunks)
    unlock(client)
    project = client.post(ROOT + "/projects",json={"name":"数学","instructions":"先给提示"}).json()
    thread = str(uuid4())
    route = ROOT + "/threads/" + thread
    first = {"id":str(uuid4()), "question":"怎么解？","create_thread":True}
    assert [e["type"] for e in events(client.post(route+"/turns",json=first))] == ["delta","delta","done"]
    assert client.put(route,json={"title":"因式分解","project_id":project["id"]}).is_success
    client.put(ROOT + "/projects/" + project["id"],json={"name":"数学","instructions":"用中文提示"})
    second = {"id":str(uuid4()),"question":"接着呢？"}
    events(client.post(route+"/turns",json=second))
    assert calls[-1][0]["content"].endswith("用中文提示")
    assert [m["content"] for m in calls[-1][1:]] == ["怎么解？","第一步，画图。","接着呢？"]
    events(client.post(route+"/turns",json=second))
    assert len(calls) == 2
    other = str(uuid4())
    events(client.post(ROOT+"/threads/"+other+"/turns",json={**first,"id":str(uuid4()),"project_id":project["id"]}))
    assert len(calls[-1]) == 2 and "用中文提示" in calls[-1][0]["content"]
    second_device = TestClient(client.app)
    unlock(second_device)
    assert len(second_device.get(route).json()["turns"]) == 2
    assert second_device.get(route).json()["project_id"] == project["id"]
    assert client.put(route,json={"title":"数学","project_id":str(uuid4())}).status_code == 404
    assert client.get(route).json()["title"] == "因式分解"


def test_interruption_retry_and_conflicts(client, monkeypatch):
    unlock(client)
    async def broken(messages):
        yield "开头"
        raise ConnectionError()
    monkeypatch.setattr(api,"model_chunks",broken)
    thread, turn = str(uuid4()), str(uuid4())
    route = ROOT+"/threads/"+thread
    body = {"id":turn,"question":"第一步？","create_thread":True}
    assert events(client.post(route+"/turns",json=body))[-1]["type"] == "error"
    saved = client.get(route).json()["turns"][0]
    assert saved["status"] == "failed" and saved["answer"] == "开头"
    attempt, _ = chat.start_turn(thread,turn,body["question"],None,False)
    assert client.post(route+"/turns",json={**body,"id":str(uuid4())}).status_code == 409
    with database_for_data_root().transaction() as db:
        db.execute("UPDATE chat_turns SET started_at=0")
    assert client.get(route).json()["turns"][0]["status"] == "failed"
    async def fixed(messages):
        yield "完整回复"
    monkeypatch.setattr(api,"model_chunks",fixed)
    events(client.post(route+"/turns",json=body))
    chat.finish_turn(turn,attempt,"过期尝试","failed")
    assert client.get(route).json()["turns"] == [{"id":turn,"question":"第一步？","answer":"完整回复","status":"done"}]
    assert client.post(route+"/turns",json={**body,"question":"变更"}).status_code == 409


def test_history_budget_keeps_complete_pairs(client, monkeypatch):
    thread = str(uuid4())
    for question in ("甲"*500, "乙"*100):
        turn = str(uuid4())
        attempt, _ = chat.start_turn(thread,turn,question,None,True)
        chat.finish_turn(turn,attempt,"回复"*30,"done")
    monkeypatch.setattr(chat,"HISTORY_CHARS",320)
    _, messages = chat.start_turn(thread,str(uuid4()),"追问",None,False)
    assert [m["role"] for m in messages] == ["system","user","assistant","user"]
    assert messages[1]["content"] == "乙"*100
    assert len(chat.transcript(thread)["turns"]) == 3



@pytest.mark.parametrize("terminated, expected", [(True, "done"), (False, "failed")])
def test_gateway_stream_must_finish_before_marking_saved(client, monkeypatch, terminated, expected):
    import httpx
    from openai import AsyncOpenAI

    def gateway(request):
        payload = json.loads(request.content)
        assert payload["stream"] and payload["thinking"] == {"type": "disabled"}
        assert payload["model"] == "deepseek-v4.1-flash"
        def chunk(content, reason):
            return "data: " + json.dumps({"id":"test", "model":payload["model"], "created":0,
                "object":"chat.completion.chunk", "choices":[{"index":0, "delta":content,
                "finish_reason":reason}]}) + "\n\n"
        stream = chunk({"role":"assistant","content":"提示"}, None)
        if terminated:
            stream += chunk({}, "stop") + "data: [DONE]\n\n"
        return httpx.Response(200, headers={"Content-Type":"text/event-stream"}, text=stream)

    def sdk(**options):
        return AsyncOpenAI(**{**options, "api_key":"test", "base_url":"https://example.invalid/v1"},
                           http_client=httpx.AsyncClient(transport=httpx.MockTransport(gateway)))

    monkeypatch.setattr(api,"AsyncOpenAI",sdk)
    monkeypatch.setattr(api.get_model_settings_service(),"get_selected_model",lambda:"deepseek-v4.1-flash")
    unlock(client)
    thread = ROOT+"/threads/"+str(uuid4())
    result = events(client.post(thread+"/turns",json={"id":str(uuid4()),"question":"问题","create_thread":True}))
    assert result[0] == {"type":"delta","text":"提示"}
    assert result[-1]["type"] == ("done" if terminated else "error")
    assert client.get(thread).json()["turns"][0]["status"] == expected
