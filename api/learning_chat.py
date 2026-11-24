"""Private family learning conversations, including incremental text replies."""
import asyncio
import json
import logging
from contextlib import aclosing
from urllib.parse import urlsplit
from typing import Annotated, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, StringConstraints

from config import config
from core.ai_generator import AIGenerator
from services import family_chat_session as sessions
from services import learning_chat_service as chat
from services.model_settings_service import get_model_settings_service


logger = logging.getLogger(__name__)
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class Password(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class Project(BaseModel):
    name: Name
    instructions: str = Field(default="", max_length=2000)


class ThreadSettings(BaseModel):
    title: Name
    project_id: Optional[UUID] = None


class Turn(BaseModel):
    id: UUID
    question: Question
    create_thread: bool = False
    project_id: Optional[UUID] = None


def same_origin(request: Request, response: Response):
    # The site has a permissive global CORS policy; this workspace is private.
    origin = request.headers.get("origin")
    site = request.headers.get("sec-fetch-site")
    if (site in {"same-site", "cross-site"}
            or (origin and site != "same-origin" and urlsplit(origin).netloc != request.headers.get("host"))):
        raise HTTPException(403, "请从学习页面打开")
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/learning-chat", dependencies=[Depends(same_origin)])
private = APIRouter(dependencies=[Depends(sessions.require_family)])


@router.post("/login")
def login(body: Password, request: Request, response: Response):
    sessions.login(request, response, body.password)
    return {"ok": True}


@private.post("/logout")
def logout(request: Request, response: Response):
    sessions.logout(request, response)
    return {"ok": True}


@private.get("/workspace")
def workspace():
    return chat.workspace()


@private.post("/projects")
def create_project(body: Project):
    return chat.save_project(str(uuid4()), body.name, body.instructions.strip(), create=True)


@private.put("/projects/{project_id}")
def edit_project(project_id: UUID, body: Project):
    return chat.save_project(str(project_id), body.name, body.instructions.strip(), create=False)


@private.get("/threads/{thread_id}")
def get_thread(thread_id: UUID):
    return chat.transcript(str(thread_id))


@private.put("/threads/{thread_id}")
def edit_thread(thread_id: UUID, body: ThreadSettings):
    chat.update_thread(str(thread_id), body.title, str(body.project_id) if body.project_id else None)
    return {"ok": True}


async def model_chunks(messages):
    model = get_model_settings_service().get_selected_model()
    async with AsyncOpenAI(api_key=config.OPENAI_API_KEY, base_url=config.fix_base_url(),
                           timeout=config.AI_REQUEST_TIMEOUT, max_retries=0) as client:
        stream = await client.chat.completions.create(
            model=model, messages=messages, stream=True, max_tokens=2048,
            extra_body=AIGenerator.completion_options(model),
        )
        finished = False
        async with stream:
            async for chunk in stream:
                for choice in chunk.choices or []:
                    if choice.delta and choice.delta.content:
                        yield choice.delta.content
                    if choice.finish_reason in {"stop", "length"}:
                        finished = True
        if not finished:
            raise RuntimeError("incomplete gateway stream")


def event(kind, **data):
    return json.dumps({"type": kind, **data}, ensure_ascii=False) + "\n"


async def reply(turn_id, attempt, messages):
    if attempt is None:
        yield event("delta", text=messages)
        yield event("done")
        return
    parts = []
    saved = False
    try:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + chat.STREAM_SECONDS
        async with aclosing(model_chunks(messages)) as chunks:
            while True:
                try:
                    text = await asyncio.wait_for(chunks.__anext__(), deadline - loop.time())
                except StopAsyncIteration:
                    break
                parts.append(text)
                yield event("delta", text=text)
        if not parts:
            raise ValueError("empty gateway reply")
        chat.finish_turn(turn_id, attempt, "".join(parts), "done")
        saved = True
    except Exception as exc:
        logger.warning("Family chat generation failed (%s)", type(exc).__name__)
    finally:
        if not saved:
            chat.finish_turn(turn_id, attempt, "".join(parts), "failed")
    yield event("done") if saved else event("error", message="回复中断，你的问题已保存，可以重试。")


@private.post("/threads/{thread_id}/turns")
def send(thread_id: UUID, body: Turn):
    turn_id = str(body.id)
    attempt, messages = chat.start_turn(str(thread_id), turn_id, body.question,
                                        str(body.project_id) if body.project_id else None, body.create_thread)
    return StreamingResponse(reply(turn_id, attempt, messages), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"})


router.include_router(private)
