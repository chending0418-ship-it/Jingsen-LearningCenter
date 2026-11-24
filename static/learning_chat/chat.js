"use strict";
const el = id => document.getElementById(id);
const api = (location.pathname.startsWith("/learningcenter/") ? "/learningcenter" : "") + "/api/learning-chat";
let projects = [], threads = [], filter = null, current = null, turns = [];
let busy = false, editMode = "", editId = null, poll = 0, revision = 0;
let unsent = null, webMode = "auto";
const projectName = id => projects.find(project => project.id === id)?.name || "未归类";

function notice(text) { el("notice").textContent = text; }

function setGate(show) {
    el("loading").hidden = true;
    el("gate").hidden = !show;
    el("workspace").hidden = show;
    el("logout").hidden = show;
    if (show) {
        clearTimeout(poll);
        revision++;
        projects = []; threads = []; turns = []; current = null; filter = null; unsent = null;
        el("messages").replaceChildren(); el("threads").replaceChildren(); el("projects").replaceChildren();
        el("question").value = ""; el("threadTitle").textContent = "新对话";
        if (el("editor").open) el("editor").close();
        toggleNav(false);
    }
}

async function request(path, method = "GET", body, stream = false) {
    const response = await fetch(api + path, {
        method, cache:"no-store", credentials:"same-origin",
        headers: body ? {"Content-Type":"application/json"} : {},
        body: body ? JSON.stringify(body) : undefined
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        if (response.status === 401 && path !== "/login") setGate(true);
        const error = new Error(typeof data.detail === "string" ? data.detail : "操作未完成，请再试一次。");
        error.status = response.status;
        throw error;
    }
    return stream ? response : response.json();
}

function action(label, handler, className = "item") {
    const button = document.createElement("button");
    button.type = "button"; button.className = className; button.title = label;
    const span = document.createElement("span"); span.textContent = label; button.append(span);
    button.onclick = () => Promise.resolve(handler()).catch(error => notice(error.message));
    button.disabled = busy;
    return button;
}

function icon(name) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg"), use = document.createElementNS(ns, "use");
    use.setAttribute("href", "#" + name); svg.setAttribute("aria-hidden","true"); svg.append(use);
    return svg;
}

function toggleNav(open) {
    el("sidebar").classList.toggle("open",open); el("scrim").hidden = !open;
    document.querySelector(".desk").inert = open;
    el("openNav").setAttribute("aria-expanded",String(open));
    if (open) el("closeNav").focus();
}

function remember(id) {
    const url = new URL(location.href);
    if (id) url.searchParams.set("chat",id); else url.searchParams.delete("chat");
    history.replaceState(null,"",url);
}

function renderLists() {
    const all = action("所有对话", () => selectProject(null));
    all.setAttribute("aria-current",String(filter === null));
    el("projects").replaceChildren(all);
    for (const p of projects) {
        const row = document.createElement("div"); row.className = "project-row";
        const choose = action(p.name, () => selectProject(p.id));
        choose.prepend(icon("folder")); choose.setAttribute("aria-current",String(filter === p.id));
        const edit = action("设置项目「" + p.name + "」", () => openEditor("project",p), "icon");
        edit.replaceChildren(icon("edit")); edit.setAttribute("aria-label",edit.title);
        row.append(choose,edit); el("projects").append(row);
    }
    el("listTitle").textContent = filter ? "项目对话" : "最近对话";
    const list = el("threads"); list.replaceChildren();
    for (const thread of threads.filter(t => !filter || t.project_id === filter)) {
        const item = action(thread.title, () => openThread(thread.id));
        item.setAttribute("aria-current",String(current?.id === thread.id)); list.append(item);
    }
    if (!list.children.length) {
        const empty = document.createElement("p"); empty.className = "list-empty";
        empty.textContent = filter ? "在这个项目中开始第一段对话。" : "发出第一个问题后，会保存在这里。";
        list.append(empty);
    }
}

function updateControls() {
    const pending = turns.some(turn => turn.status === "pending");
    for (const id of ["newChat","newProject","settings","logout"]) el(id).disabled = busy;
    el("send").disabled = busy || pending || !el("question").value.trim();
    el("question").disabled = busy || pending;
    el("webMode").disabled = busy || pending;
    el("settings").hidden = !current;
}

function header() {
    el("contextLabel").textContent = current ? projectName(current.project_id) : (filter ? projectName(filter) : "家庭学习空间");
    el("threadTitle").textContent = current?.title || "新对话";
}

function renderTurns() {
    const messages = el("messages"); messages.replaceChildren();
    el("empty").hidden = turns.length > 0;
    for (const [i,turn] of turns.entries()) {
        const group = document.createElement("article"); group.className = "turn";
        const user = document.createElement("div"); user.className = "user";
        const question = document.createElement("p"); question.className = "ask"; question.textContent = turn.question;
        user.setAttribute("aria-label","你的问题"); user.append(question);
        const assistant = document.createElement("div"); assistant.className = "assistant";
        const speaker = document.createElement("p"); speaker.className = "speaker"; speaker.textContent = "学习助手";
        const answer = document.createElement("div"); answer.className = "answer";
        if (turn.answer) formatAnswer(answer,turn.answer);
        else answer.textContent = turn.answer || (turn.status === "pending" ? "正在思考…" : "");
        assistant.append(speaker,answer);
        if (turn.answer && turn.status !== "pending") {
            const copy = action("复制原文", async () => {
                try {
                    await navigator.clipboard.writeText(turn.answer);
                    notice("已复制 Markdown 原文");
                } catch { notice("无法访问剪贴板，请在浏览器中允许复制。"); }
            }, "copy-source");
            assistant.append(copy);
        }
        if (turn.status === "failed") {
            const msg = document.createElement("span"); msg.className = "failed"; msg.textContent = "回复中断";
            assistant.append(msg);
            if (i === turns.length - 1) assistant.append(action("重新生成", () => sendTurn(turn), "retry"));
        }
        group.append(user,assistant); messages.append(group);
    }
    header(); updateControls();
}

function bottom() { const area = el("scroller"); area.scrollTop = area.scrollHeight; }

async function loadLists() {
    const data = await request("/workspace");
    projects = data.projects; threads = data.threads; renderLists();
}

function newThread() {
    clearTimeout(poll); revision++; unsent = null;
    current = null; turns = []; webMode = "auto"; el("webMode").value = webMode; remember(null); notice(""); el("question").value = "";
    renderLists(); renderTurns(); toggleNav(false);
}

function selectProject(id) {
    filter = id; newThread();
    // Keep the project directory open on phones so a saved conversation is one tap away.
    if (matchMedia("(max-width:760px)").matches) toggleNav(true);
}

function scheduleRefresh(id, stamp) {
    clearTimeout(poll);
    if (!turns.some(t => t.status === "pending")) return;
    poll = setTimeout(async () => {
        try {
            const data = await request("/threads/" + id);
            if (revision !== stamp) return;
            turns = data.turns; current = data; renderTurns(); scheduleRefresh(id,stamp);
        } catch (error) {
            if (revision === stamp) { notice(error.message); scheduleRefresh(id,stamp); }
        }
    },2000);
}

async function openThread(id) {
    clearTimeout(poll);
    const stamp = ++revision;
    const data = await request("/threads/" + id);
    if (revision !== stamp) return;
    current = data; turns = data.turns; unsent = null;
    webMode = data.web_mode || "auto"; el("webMode").value = webMode;
    el("question").value = ""; remember(id); notice(""); toggleNav(false);
    renderTurns(); renderLists(); bottom(); scheduleRefresh(id,stamp);
}

async function openWorkspace() {
    await loadLists(); setGate(false); newThreadFromUrl();
}

function newThreadFromUrl() {
    const id = new URL(location.href).searchParams.get("chat");
    if (id && threads.some(thread => thread.id === id)) {
        openThread(id).catch(error => notice(error.message));
    } else newThread();
}

function openEditor(mode, item) {
    editMode = mode; editId = item?.id;
    const thread = mode === "thread";
    el("editorTitle").textContent = thread ? "整理对话" : item ? "项目设置" : "新建项目";
    el("nameLabel").textContent = thread ? "对话标题" : "项目名称";
    el("name").value = item?.name || item?.title || "";
    el("instructions").value = item?.instructions || "";
    el("instructionField").hidden = thread; el("projectField").hidden = !thread;
    el("moveTo").replaceChildren(new Option("未归类",""),...projects.map(p => new Option(p.name,p.id)));
    el("moveTo").value = item?.project_id || ""; el("editError").textContent = "";
    el("editor").showModal(); el("name").focus();
}

el("editForm").onsubmit = async event => {
    event.preventDefault(); const submit = event.submitter; submit.disabled = true;
    try {
        const name = el("name").value.trim();
        if (!name) throw new Error("请输入名称");
        if (editMode === "thread") {
            const project_id = el("moveTo").value || null;
            await request("/threads/" + editId,"PUT",{title:name,project_id});
            current = {...current,title:name,project_id}; filter = project_id;
        } else {
            const saved = await request(editId ? "/projects/" + editId : "/projects",editId ? "PUT" : "POST",
                {name,instructions:el("instructions").value});
            if (!editId) { filter = saved.id; newThread(); }
        }
        await loadLists(); header(); el("editor").close();
    } catch (error) { el("editError").textContent = error.message; }
    finally { submit.disabled = false; }
};

async function readReply(response,onText,onSearch) {
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = "", done = false;
    try {
        while (true) {
            const chunk = await reader.read();
            buffer += decoder.decode(chunk.value,{stream:!chunk.done});
            const lines = buffer.split("\n"); buffer = lines.pop();
            for (const line of lines) {
                if (!line) continue;
                const event = JSON.parse(line);
                if (event.type === "delta") onText(event.text);
                else if (event.type === "searching") onSearch();
                else if (event.type === "error") throw new Error(event.message);
                else if (event.type === "done") done = true;
            }
            if (chunk.done) break;
        }
    } finally { reader.releaseLock(); }
    if (!done) throw new Error("连接中断，请检查已保存的回复。");
}

async function sendTurn(retry) {
    if (busy) return;
    const question = (retry?.question || el("question").value).trim();
    if (!question) return;
    const fresh = !current;
    const once = el("webMode").value === "once";
    const draft = unsent?.question === question ? unsent : null;
    const threadId = current?.id || draft?.threadId || crypto.randomUUID();
    const id = retry?.id || draft?.id || crypto.randomUUID();
    const turn = {id,question,answer:"",status:"pending"};
    const previous = turns.slice();
    busy = true; revision++; clearTimeout(poll); notice("正在连接学习助手…");
    turns = retry ? [...turns.slice(0,-1),turn] : [...turns,turn];
    renderTurns(); renderLists(); bottom();
    let accepted = false, renderTimer;
    try {
        const response = await request("/threads/" + threadId + "/turns","POST",
            {id,question,create_thread:fresh,project_id:filter,web_mode:webMode,search_once:once},true);
        accepted = true; unsent = null; el("webMode").value = webMode;
        if (fresh) current = {id:threadId,title:question.slice(0,36),project_id:filter};
        remember(threadId); header(); el("question").value = ""; notice("正在回复…");
        const answer = el("messages").lastElementChild.querySelector(".answer");
        const paint = () => {
            renderTimer = undefined;
            const area = el("scroller");
            const nearEnd = area.scrollHeight - area.clientHeight - area.scrollTop < 90;
            formatAnswer(answer,turn.answer);
            if (nearEnd) bottom();
        };
        await readReply(response, text => {
            if (el("notice").textContent !== "正在回复…") notice("正在回复…");
            turn.answer += text;
            if (renderTimer === undefined) renderTimer = setTimeout(paint,100);
        }, () => { notice("正在查资料…"); if (!turn.answer) answer.textContent = "正在联网检索…"; });
        turn.status = "done"; notice("已自动保存");
    } catch (error) {
        if (el("workspace").hidden) return;
        notice(error.message);
        if (accepted) turn.status = "failed";
        else { turns = previous; unsent = {question,threadId,id}; }
        try {
            const data = await request("/threads/" + threadId);
            current = data; turns = data.turns; remember(threadId);
            if (turns.some(t => t.id === id)) { unsent = null; el("question").value = ""; }
        } catch { /* An unaccepted first turn has no server-side thread yet. */ }
    } finally {
        clearTimeout(renderTimer);
        busy = false;
        if (!el("workspace").hidden) {
            renderTurns(); renderLists();
            try { await loadLists(); } catch (error) { notice(error.message); }
            if (current) scheduleRefresh(current.id,revision);
        }
    }
}

el("loginForm").onsubmit = async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    el("loginError").textContent = "";
    try {
        await request("/login","POST",{password:el("password").value});
        el("password").value = ""; await openWorkspace();
    } catch (error) { el("loginError").textContent = error.message; }
    finally { button.disabled = false; }
};
el("logout").onclick = async () => {
    try { await request("/logout","POST"); remember(null); setGate(true); }
    catch (error) { notice(error.message); }
};
el("newChat").onclick = () => { newThread(); el("question").focus(); };
el("newProject").onclick = () => openEditor("project");
el("settings").onclick = () => openEditor("thread",current);
el("cancel").onclick = () => el("editor").close();
el("openNav").onclick = () => toggleNav(true);
el("closeNav").onclick = el("scrim").onclick = () => { toggleNav(false); el("openNav").focus(); };
document.addEventListener("keydown",event => {
    if (event.key === "Escape" && !el("editor").open && el("sidebar").classList.contains("open")) el("closeNav").click();
});
matchMedia("(max-width:760px)").addEventListener("change", () => toggleNav(false));
el("webMode").onchange = async () => {
    const value = el("webMode").value;
    if (value === "once") { notice("下一次提问将联网检索"); return; }
    if (!current) { webMode = value; notice(""); return; }
    busy = true; updateControls(); renderLists();
    try {
        await request("/threads/" + current.id + "/search","PATCH",{web_mode:value});
        webMode = value; notice("已保存联网设置");
    } catch (error) { el("webMode").value = webMode; notice(error.message); }
    finally { busy = false; updateControls(); renderLists(); }
};
el("question").oninput = updateControls;
el("question").onkeydown = event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
        event.preventDefault(); if (!el("send").disabled) el("composer").requestSubmit();
    }
};
el("composer").onsubmit = event => { event.preventDefault(); sendTurn(); };
openWorkspace().catch(error => {
    setGate(true);
    if (error.status !== 401) el("loginError").textContent = error.message;
});
