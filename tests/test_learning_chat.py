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
    async def chunks(messages, mode):
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
    async def broken(messages, mode):
        yield "开头"
        raise ConnectionError()
    monkeypatch.setattr(api,"model_chunks",broken)
    thread, turn = str(uuid4()), str(uuid4())
    route = ROOT+"/threads/"+thread
    body = {"id":turn,"question":"第一步？","create_thread":True}
    assert events(client.post(route+"/turns",json=body))[-1]["type"] == "error"
    saved = client.get(route).json()["turns"][0]
    assert saved["status"] == "failed" and saved["answer"] == "开头"
    attempt, _, _ = chat.start_turn(thread,turn,body["question"],None,False)
    assert client.post(route+"/turns",json={**body,"id":str(uuid4())}).status_code == 409
    with database_for_data_root().transaction() as db:
        db.execute("UPDATE chat_turns SET started_at=0")
    assert client.get(route).json()["turns"][0]["status"] == "failed"
    async def fixed(messages, mode):
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
        attempt, _, _ = chat.start_turn(thread,turn,question,None,True)
        chat.finish_turn(turn,attempt,"回复"*30,"done")
    monkeypatch.setattr(chat,"HISTORY_CHARS",320)
    _, messages, _ = chat.start_turn(thread,str(uuid4()),"追问",None,False)
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
        assert "max_tokens" not in payload
        assert "max_completion_tokens" not in payload
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

def test_search_pref_is_authoritative_and_once_is_temporary(client, monkeypatch):
    modes = []

    async def chunks(messages, mode):
        modes.append(mode)
        yield "回答"

    monkeypatch.setattr(api, "model_chunks", chunks)
    unlock(client)
    route = ROOT + "/threads/" + str(uuid4())
    def send(**options):
        return events(client.post(route + "/turns", json={
            "id": str(uuid4()), "question": "问", **options}))
    send(create_thread=True, web_mode="off")
    send(web_mode="auto")
    send(search_once=True)
    assert client.get(route).json()["web_mode"] == "off"
    assert client.patch(route + "/search", json={"web_mode":"auto"}).is_success
    send()
    assert modes == ["off", "off", "once", "auto"]


def test_grounding_links_prioritize_cited_pages_and_ignore_non_web_chunks():
    first, cited = "https://example.org/", "https://science.nasa.gov/moon/"
    metadata = {"groundingChunks": [
        {"web":{"uri":first}}, {"web":{"uri":"javascript:invalid"}}, {"maps":{"uri":first}},
        {"web":{"uri":cited, "title":"nasa.gov"}}, {"web":{"uri":cited}}],
        "groundingSupports":[{"groundingChunkIndices":[-1, 10, 3, 3], "segment":{"text":"月球同步自转"}}]}
    links = api.search.grounding_links(metadata)
    assert list(links) == [cited, first]
    assert links[cited]["title"] == "nasa.gov · 月球同步自转"


def test_streamed_tool_round_trip_save_replay_and_failure(client, monkeypatch):
    import httpx
    from openai import AsyncOpenAI

    requests, queries = [], []

    def gateway(request):
        body = json.loads(request.content)
        requests.append(body)
        if body["messages"][-1]["role"] == "tool":
            assert "tools" not in body
            assert json.loads(body["messages"][-1]["content"]) == {"notes":"NASA 资料", "sources":["NASA"]}
            parts = [({"content":"潮汐锁定。"}, None), ({}, "stop")]
        else:
            assert body["tools"][0]["function"]["name"] == "search_web"
            def call(name, args):
                return {"tool_calls":[{"index":0, "function":{"name":name,"arguments":args}}]}
            parts = [(call("search_web", '{"query":"NA'), None), (call("", 'SA 月球"}'), None), ({}, "tool_calls")]
        text = ""
        for delta, reason in parts:
            text += "data: " + json.dumps({"id":"synthetic", "model":body["model"], "created":0,
                "object":"chat.completion.chunk", "choices":[{"index":0,"delta":delta,"finish_reason":reason}]}) + "\n\n"
        return httpx.Response(200, headers={"Content-Type":"text/event-stream"}, text=text+"data: [DONE]\n\n")

    def sdk(**options):
        return AsyncOpenAI(**{**options,"api_key":"test","base_url":"https://example.invalid/v1"},
                           http_client=httpx.AsyncClient(transport=httpx.MockTransport(gateway)))

    async def research(query):
        queries.append(query)
        sources = [{"title":"NASA","url":"https://science.nasa.gov/moon/"}]
        yield "sources", sources
        if len(queries) > 1:
            raise api.search.SearchUnavailable()
        yield "evidence", {"notes":"NASA 资料", "sources":sources}

    monkeypatch.setattr(api, "AsyncOpenAI", sdk)
    monkeypatch.setattr(api.search, "search_web", research)
    unlock(client)
    route = ROOT + "/threads/" + str(uuid4())
    body = {"id":str(uuid4()), "question":"根据资料讲讲月球", "create_thread":True}
    first = events(client.post(route+"/turns",json=body))
    assert [e["type"] for e in first] == ["searching","sources","delta","delta","done"]
    assert first[1]["sources"][0]["title"] == "NASA"
    persisted = client.get(route).json()["turns"][0]["answer"]
    assert "https://science.nasa.gov/moon/" in persisted
    assert events(client.post(route+"/turns",json=body))[0]["text"] == persisted
    assert len(requests) == 2 and queries == ["NASA 月球"]
    failed = events(client.post(route+"/turns",json={**body,"id":str(uuid4())}))
    assert failed[-1]["type"] == "error" and "未能取得" in failed[-1]["message"]
    assert client.get(route).json()["turns"][-1]["status"] == "failed"
    assert "science.nasa.gov" not in client.get(route).json()["turns"][-1]["answer"]


def test_family_companion_name_survives_reload_and_reaches_existing_threads(client, monkeypatch):
    route = ROOT + "/companion"
    assert client.put(route, json={"name":"小满"}).status_code == 401
    unlock(client)
    assert client.get(ROOT + "/workspace").json()["companion_name"] == ""
    thread_id, first_id = str(uuid4()), str(uuid4())
    attempt, _, _ = chat.start_turn(thread_id, first_id, "上一题", None, True)
    chat.finish_turn(first_id, attempt, "原来的回复", "done")
    assert client.put(route, json={"name":"  小满  "}).json() == {"companion_name":"小满"}
    other = TestClient(client.app)
    unlock(other)
    assert other.get(ROOT + "/workspace").json()["companion_name"] == "小满"
    for invalid in ["  ", "字"*25, "一行\n两行"]:
        assert other.put(route, json={"name":invalid}).status_code == 422
    assert other.put(route, json={"name":"云朵"}).is_success
    prompts = []
    async def chunks(messages, mode):
        prompts.append(messages)
        yield "云朵"
    monkeypatch.setattr(api,"model_chunks",chunks)
    client.post(ROOT + "/threads/" + thread_id + "/turns", json={"id":str(uuid4()),"question":"你叫什么？"})
    assert '"云朵"' in prompts[0][0]["content"] and "小满" not in prompts[0][0]["content"]
    assert client.get(ROOT + "/threads/" + thread_id).json()["turns"][0]["answer"] == "原来的回复"


@pytest.mark.parametrize("ending", [
    "completed", "interrupted", "blocked", "error", "json", "json-array", "no-search", "no-sources", "no-notes",
])
def test_search_stream_uses_verified_sources_before_final_evidence(monkeypatch, ending):
    import asyncio
    from contextlib import asynccontextmanager
    import httpx

    url = "https://science.nasa.gov/moon/"
    chunks = [{"web":{"uri":url, "title":"NASA"}}, {"web":{"uri":url}}, {"web":{"uri":"javascript:invalid"}}]
    parts = [{"text":"隐藏思考", "thought":True}]
    if ending != "no-notes":
        parts.append({"text":"检索笔记"})
    queries = [] if ending == "no-search" else ["NASA 月球"]
    metadata = {"webSearchQueries":queries, "groundingChunks":[] if ending == "no-sources" else chunks}
    def chunk(**fields):
        return {"candidates":[fields]}
    def frame(value):
        return ("data: " + json.dumps(value) + "\n\n").encode()
    visible = []

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b": heartbeat\n\n"
            yield frame(chunk(content={"parts":parts}, groundingMetadata={"groundingChunks":metadata["groundingChunks"]}))
            assert visible == []
            yield frame(chunk(groundingMetadata={"webSearchQueries":queries}))
            if ending not in {"no-search", "no-sources"}:
                assert [kind for kind, _ in visible] == ["sources"]
            yield frame(chunk(groundingMetadata=metadata))
            if ending == "error":
                yield frame({"error":{"code":503}})
            elif ending != "interrupted":
                yield frame(chunk(finishReason="SAFETY" if ending == "blocked" else "STOP"))

    @asynccontextmanager
    async def upstream(self, method, endpoint, *, headers, json):
        assert method == "POST" and endpoint == "https://example.invalid/v1beta/models/gemini-3.5-flash-lite-search:streamGenerateContent?alt=sse"
        assert json["contents"] == [{"role":"user","parts":[{"text":"NASA 月球"}]}]
        assert json["tools"] == [{"google_search":{}}] and headers == {"x-goog-api-key":"test"}
        request = httpx.Request(method, endpoint)
        if ending.startswith("json"):
            full = chunk(content={"parts":parts}, groundingMetadata=metadata, finishReason="STOP")
            response = httpx.Response(200, request=request, json=[full] if ending == "json-array" else full)
        else:
            response = httpx.Response(200, request=request, stream=Stream(), headers={"Content-Type":"text/event-stream"})
        try:
            yield response
        finally:
            await response.aclose()

    monkeypatch.setattr(httpx.AsyncClient, "stream", upstream)
    monkeypatch.setattr(api.search.config, "fix_base_url", lambda: "https://example.invalid/v1")
    monkeypatch.setattr(api.search.config, "OPENAI_API_KEY", "test")
    async def run():
        async for update in api.search.search_web("NASA 月球"):
            visible.append(update)
    if ending in {"completed", "json", "json-array"}:
        asyncio.run(run())
        assert [kind for kind, _ in visible] == ["sources","evidence"]
        assert visible[-1][1] == {"notes":"检索笔记","sources":[{"title":"NASA","url":url}]}
    else:
        with pytest.raises(api.search.SearchUnavailable):
            asyncio.run(run())
        assert [kind for kind, _ in visible] == ([] if ending in {"no-search","no-sources"} else ["sources"])
