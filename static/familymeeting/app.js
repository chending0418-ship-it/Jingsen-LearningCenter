'use strict';
(() => {
  const ROOT = '/baseball/familymeeting/query';
  const API = '/api/baseball/familymeeting/meetings';
  const $ = (s, root = document) => root.querySelector(s);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const clone = value => JSON.parse(JSON.stringify(value));
  const roles = {dad:'爸爸', mom:'妈妈', owner:'会议管理'};
  const S = {schema:null, context:null, state:null, links:null, step:0, mode:'landing', tab:'guide', draft:{}, revision:0, dirty:false, notes:{}, notesRevision:0, notesDirty:false, saveChain:Promise.resolve(), noteChain:Promise.resolve(), saveTimer:null, noteTimer:null, poll:null, grant:'', saveMessage:'已同步', conflict:false, localRecovery:null};
  const noteFields = [
    ['common','已经达成的共识','text','full','写下两个人都认可的目标、事实与原则。'],
    ['differences','保留的分歧','text','','分别记录双方的理由；暂时不一致也可以保留。'],
    ['unknowns','还要核实的事情','text','','写清要向谁了解什么，不急着把推测写成结论。'],
    ['direction','下一阶段的方向','direction','','选择共同方案，或记录暂未达成一致。'],
    ['child_state','孩子的参与与确认','child','','未听取孩子意见时，先记录父母的暂定方案。'],
    ['conditions','执行这个方向的条件与投入范围','text','full','包括时间、费用、组织责任，以及开始前必须落实的条件。'],
    ['next_action','下一步行动','text','full','尽量写成具体、可完成的一两件事。'],
    ['owner','由谁负责','input','','可以按事项分工。'],
    ['due_date','下一步完成日期','date','',''],
    ['review_date','一起复盘的日期','date','','届时结合实际体验和孩子的意见重新评估。'],
    ['fallback','如果条件没有落实，怎样调整','text','full','可以写备选方案、降低投入、阶段性暂停或结束，以及再次讨论的时间。']
  ];
  function storeGet(key, session=false) { try { const raw = (session?sessionStorage:localStorage).getItem(key); return raw ? JSON.parse(raw) : null; } catch { return null; } }
  function storeSet(key, value, session=false) { try { (session?sessionStorage:localStorage).setItem(key, JSON.stringify(value)); return true; } catch { return false; } }
  function storeRemove(key) { try { localStorage.removeItem(key); } catch {} }
  const draftKey = () => `fm_draft_${S.context.id}_${S.state.role}`;
  const notesKey = () => `fm_notes_${S.context.id}`;
  const grantKey = () => `fm_view_${S.context.id}_${S.context.token.slice(0,12)}`;
  const pathName = id => S.schema.paths.find(p => p.id===id)?.label || (id==='unknown'?'目前还没有想清楚':id==='undecided'?'暂未达成一致':String(id||''));
  const stanceName = id => S.schema.stances.find(p=>p.id===id)?.label || '尚未选择';
  const today = () => new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  function toast(message) { const el=$('#toast'); el.textContent=message; el.hidden=false; clearTimeout(toast.timer); toast.timer=setTimeout(()=>el.hidden=true,6500); }
  async function request(url, options={}) {
    const headers = {'Content-Type':'application/json', ...options.headers};
    if (S.context && url.startsWith(`${API}/`)) headers.Authorization=`Bearer ${S.context.token}`;
    if (S.grant && url.startsWith(`${API}/`)) headers['X-Meeting-View']=S.grant;
    const controller=new AbortController(); const timeout=setTimeout(()=>controller.abort(),20000);
    try {
      const response=await fetch(url,{...options,headers,credentials:'same-origin',cache:'no-store',signal:controller.signal});
      let data; try { data=await response.json(); } catch { throw new Error('服务器暂时没有响应，请稍后重试。'); }
      if (!response.ok) { const error=new Error(typeof data.detail==='string'?data.detail:'请检查填写内容后重试。'); error.status=response.status; throw error; }
      return data;
    } catch(error) { if (error.name==='AbortError') throw new Error('连接超时。请保留页面，稍后重试。'); throw error; }
    finally { clearTimeout(timeout); }
  }
  const meetingRequest=(suffix='',options={})=>request(`${API}/${S.context.id}${suffix}`,options);
  function contextUrl(id,token) { return `${location.origin}${ROOT}#m=${encodeURIComponent(id)}&k=${encodeURIComponent(token)}`; }
  function rememberLinks(access) { storeSet(`fm_owner_${access.id}`,access); S.links=access; }
  function statusText(person) { return person?.ready?'已提交，准备交流':person?.has_submission?'有修改，待重新提交':'正在准备'; }
  function statusMarkup() { return ['dad','mom'].map(role=>`<span class="badge ${S.state.participants[role].ready?'good':''}">${roles[role]} · ${esc(statusText(S.state.participants[role]))}</span>`).join(''); }
  function openButton(light=false) { return `<button class="button ${light?'light':'secondary'}" data-action="unlock" ${S.state.can_open?'':'disabled'}>${S.state.opened_at?'进入共同查看 ↗':'开始共同查看 ↗'}</button>`; }
  function header() { return `<div class="meeting-heading"><div><div class="eyebrow">FAMILY MEETING / ${esc(S.state.meeting_date)}</div><h1>${esc(S.state.title)}</h1><div class="meta-line"><span class="badge">${roles[S.state.role]}${S.mode==='answer'?' · 独立填写':''}</span><span>先求同，再理解分歧，一起选择下一阶段。</span></div></div><div class="button-row">${S.mode==='meeting'?`<button class="button secondary" data-action="leave-meeting">返回${S.state.role==='owner'?'会议管理':'我的答案'}</button>`:openButton()}${S.links&&S.state.role!=='owner'?'<button class="button ghost" data-action="owner">管理与分享</button>':''}</div></div>`; }
  function renderLanding(admin=false, meetings=[]) {
    S.mode='landing';
    const recentContext=storeGet('fm_recent');
    $('#main').innerHTML=`<div class="page"><section class="hero"><div><div class="eyebrow">A FAMILY DECISION, TOGETHER.</div><h1>先各自想清楚，<br>再一起选方向。</h1><p class="lead">关于棒球，也关于孩子想走的路、家庭愿意承担的投入，以及我们怎样彼此支持。</p><p class="help">约 15–25 分钟独立填写 · 可以留空或写「暂时不知道」</p></div><div class="hero-art" aria-hidden="true"><div class="field-lines"></div><div class="paper-note second"><span>YOUR THOUGHTS</span><b>你的想法，<br>值得被听见。</b></div><div class="paper-note first"><span>OUR NEXT CHAPTER</span><b>求同存异，<br>一起往前。</b></div><div class="art-caption">TWO VOICES / ONE CONVERSATION</div></div></section><section class="intro-steps" aria-label="使用方法"><div class="intro-step"><span>01</span><strong>分别填写</strong><p>爸爸、妈妈各用自己的链接记录想法，草稿自动保存。</p></div><div class="intro-step"><span>02</span><strong>提交后，带密码一起看</strong><p>双方都提交，再点击按钮输入会议密码，才展示彼此答案。</p></div><div class="intro-step"><span>03</span><strong>形成阶段性共识</strong><p>按照对话流程，记录方向、分歧、分工和复盘时间。</p></div></section><section class="panel" id="create-panel"><h2>${admin?'准备一次家庭会议':'从一次平静的交流开始'}</h2>${admin?`<form id="create-form" class="create-grid"><div class="field-compact"><label for="meeting-title">会议名称</label><input id="meeting-title" maxlength="100" value="棒球与下一阶段的家庭方向" required></div><div class="field-compact"><label for="meeting-date">会议日期</label><input id="meeting-date" type="date" value="${today()}" required></div><button class="button" type="submit">创建会议 ↗</button></form><p class="help">创建后会生成两份专属填写链接。会议密码由网站管理员设置，分享链接不包含密码。</p>`:`<p class="muted">发起人登录 Jingsen 后台后创建会议。收到爸爸或妈妈专属链接的人，可以直接填写。</p><a class="button" href="/admin?next=${encodeURIComponent(ROOT)}">登录并准备会议 ↗</a>`}${recentContext?'<div style="margin-top:16px"><button class="inline-link" data-action="resume">在此设备继续上次会议 →</button></div>':''}</section>${admin&&meetings.length?`<section class="recent"><h2 style="font-size:21px">已有会议</h2>${meetings.map(m=>`<div class="recent-item"><div><strong>${esc(m.title)}</strong><p>${esc(m.meeting_date)} · ${m.opened_at?'已开启交流':'准备中'}</p></div><button class="button secondary small" data-action="manage-existing" data-id="${esc(m.id)}">管理与继续 ↗</button></div>`).join('')}</section>`:''}<p class="help">这些问题没有标准答案，也不会计算谁更支持孩子。留队、换队、自建队、降低投入、暂停和结束，都可以认真讨论。</p></div>`;
    $('#create-form')?.addEventListener('submit',async event=>{ event.preventDefault(); const button=$('button[type=submit]',event.target); button.disabled=true; try{const access=await request(API,{method:'POST',body:JSON.stringify({title:$('#meeting-title').value,meeting_date:$('#meeting-date').value})});rememberLinks(access);await openContext(access.id,access.tokens.owner);}catch(error){toast(error.message);}finally{button.disabled=false;} });
  }
  async function landing() {
    let admin=false, meetings=[];
    try { const session=await request('/api/admin/session'); admin=!!session.authenticated; if(admin) meetings=await request(API); } catch(error){if(error.status!==401) toast('暂时未能加载已有会议，可以稍后刷新。');}
    renderLanding(admin,meetings);
  }
  async function openContext(id,token) {
    if(S.dirty) await flushDraft();
    if(S.notesDirty) await flushNotes();
    clearInterval(S.poll);clearTimeout(S.saveTimer);clearTimeout(S.noteTimer);
    S.context={id,token};S.grant=storeGet(grantKey(),true)||'';S.links=storeGet(`fm_owner_${id}`);S.conflict=false;S.dirty=false;S.notesDirty=false;S.saveChain=Promise.resolve();S.noteChain=Promise.resolve();
    S.state=await meetingRequest();
    storeSet('fm_recent',{id,token,role:S.state.role});
    history.replaceState(null,'',`${ROOT}#m=${encodeURIComponent(id)}&k=${encodeURIComponent(token)}`);
    S.step=0;S.mode=S.state.role==='owner'?'owner':'answer';
    if(S.state.own){S.draft=clone(S.state.own.answers);S.revision=S.state.own.revision;S.localRecovery=storeGet(draftKey());S.saveMessage=S.state.own.ready?'已提交，仍可修改':'草稿已同步';}
    render();
    S.poll=setInterval(poll,8000);
  }
  function renderOwner() {
    $('#main').innerHTML=`<div class="page">${header()}<div class="notice">把两份链接分别发给对应的人。独立填写时，只能看到自己的内容；双方提交后，再输入密码共同查看。</div><div class="owner-cards">${['dad','mom'].map(role=>`<section class="person-card"><div class="person-top"><div class="person-icon">${role==='dad'?'爸':'妈'}</div><span id="owner-status-${role}" class="badge ${S.state.participants[role].ready?'good':''}">${esc(statusText(S.state.participants[role]))}</span></div><h2>${roles[role]}的独立填写</h2><p>记录自己的期待、顾虑、承受范围和阶段性建议。</p><div class="button-row"><button class="button" data-action="fill-role" data-role="${role}">在这里填写 ↗</button><button class="button secondary" data-action="copy-role" data-role="${role}">复制专属链接</button></div></section>`).join('')}</div><section class="panel owner-open"><div><h3>都准备好以后，把话放到一起。</h3><p id="owner-wait-message">${S.state.can_open?'已具备查看条件，输入会议密码即可进入。':'等待双方各自提交；一方完成后，也可以先休息。'}</p><p class="help">共同查看包括并排答案、45 分钟对话引导和共识记录。</p></div><div id="owner-open-button">${openButton(true)}</div></section><section class="panel" style="margin-top:22px"><h3>今晚准备确定什么？</h3><p class="muted">一份家庭能共同接受的阶段性方案：走哪条路、在什么条件下执行、谁做什么，以及什么时候再评估。尚未听取孩子意见的部分，会标记为父母暂定方案。</p><button class="inline-link" data-action="preview-guide">先看今晚的对话流程 →</button></section><button class="inline-link" style="margin-top:20px" data-action="home">返回会议列表</button></div>`;
  }
  function allFields() { return S.schema.sections.flatMap(section=>section.fields); }
  function answered(field) {
    const value=S.draft[field.id];
    if(field.type==='paths') return !!value&&Object.values(value).some(item=>item.stance||item.conditions?.trim());
    return typeof value==='number'||(Array.isArray(value)?value.length>0:typeof value==='string'&&value.trim().length>0);
  }
  function countAnswers() { return allFields().filter(answered).length; }
  function updateProgress() {
    const total=allFields().length, count=countAnswers();
    const p=$('#progress-text');if(p)p.textContent=`已记录 ${count} / ${total} 项`;
    const fill=$('#progress-fill');if(fill)fill.style.width=`${count/total*100}%`;
    S.schema.sections.forEach((section,index)=>{const node=$(`[data-step-check="${index}"]`);if(node)node.textContent=section.fields.some(answered)?'·':'';});
  }
  function fieldHtml(field) {
    const value=S.draft[field.id], id=`field-${field.id}`, hint=`${id}-hint`;
    const label=`<label for="${id}">${esc(field.label)}</label>${field.hint?`<p class="hint" id="${hint}">${esc(field.hint)}</p>`:''}`;
    const described=field.hint?`aria-describedby="${hint}"`:'';
    let control='';
    if(field.type==='text') control=`<textarea id="${id}" data-field="${field.id}" maxlength="6000" ${described} placeholder="写下你此刻的想法，也可以暂时不知道。">${esc(value||'')}</textarea><div class="field-foot"><button class="unknown-button" data-action="unknown" data-field-id="${field.id}" type="button">暂时不知道</button><span data-counter="${field.id}">${(value||'').length} / 6000</span></div>`;
    if(field.type==='number') control=`<div class="input-unit"><input type="number" id="${id}" data-field="${field.id}" value="${value===undefined?'':esc(value)}" min="${field.min}" max="${field.max}" step="0.5" inputmode="decimal" ${described}><span>${esc(field.unit)}</span></div>`;
    if(field.type==='date') control=`<input type="date" id="${id}" data-field="${field.id}" value="${esc(value||'')}" ${described}>`;
    if(field.type==='select'||field.type==='path_select') {
      const opts=field.type==='select'?field.options.map(v=>({id:v,label:v})):[...S.schema.paths,{id:'unknown',label:'目前还没有想清楚'}];
      control=`<select id="${id}" data-field="${field.id}" ${described}><option value="">请选择，也可以先留空</option>${opts.map(v=>`<option value="${esc(v.id)}" ${value===v.id?'selected':''}>${esc(v.label)}</option>`).join('')}</select>`;
    }
    if(field.type==='rank') {
      const selected=value||[];
      control=`<div id="${id}" class="rank-options" role="group" aria-label="${esc(field.label)}">${field.options.map((option,i)=>`<button class="rank-option ${selected.includes(option)?'selected':''}" type="button" data-action="rank" data-field-id="${field.id}" data-option="${i}" aria-pressed="${selected.includes(option)}">${selected.includes(option)?`<span class="rank-index">${selected.indexOf(option)+1}</span>`:''}${esc(option)}</button>`).join('')}</div>`;
    }
    if(field.type==='paths') control=S.schema.paths.map(path=>{const item=value?.[path.id]||{};return `<section class="path-card"><h3>${esc(path.label)}</h3><p>${esc(path.description)}</p><div class="stance-options" role="group" aria-label="${esc(path.label)}的态度">${S.schema.stances.map(stance=>`<button type="button" class="stance-option ${item.stance===stance.id?'selected':''}" data-action="stance" data-path="${path.id}" data-stance="${stance.id}" aria-pressed="${item.stance===stance.id}">${esc(stance.label)}</button>`).join('')}</div><label for="path-${path.id}">接受的条件、顾虑或待查信息</label><textarea id="path-${path.id}" data-path-condition="${path.id}" maxlength="3000" placeholder="什么条件下你会接受？哪些信息还缺少？">${esc(item.conditions||'')}</textarea></section>`;}).join('');
    return `<div class="field" data-field-wrapper="${field.id}">${label}${control}</div>`;
  }
  function renderAnswer() {
    const section=S.schema.sections[S.step];
    $('#main').innerHTML=`<div class="page">${header()}${S.state.own.ready?'<div class="submitted-top">你的想法已经提交。修改会先保存为自己的草稿，重新提交后才会更新共同查看中的内容。</div>':''}${S.localRecovery?`<div class="edit-warning">此设备还有一份未同步的草稿。${S.localRecovery.baseRevision===S.revision?'可以恢复后继续填写。':'服务器版本已有变化，请先下载草稿，再按需补充到最新答案。'} <div class="button-row" style="margin-top:8px">${S.localRecovery.baseRevision===S.revision?'<button class="button secondary small" data-action="restore-draft">恢复本机草稿</button>':''}<button class="button secondary small" data-action="download-recovery">下载草稿备份</button><button class="inline-link" data-action="dismiss-recovery">使用服务器版本</button></div></div>`:''}<div class="workspace"><aside class="sidebar"><div class="progress-head"><span id="progress-text"></span><span>可留空</span></div><div class="progress-track"><div id="progress-fill" class="progress-fill"></div></div><nav class="step-nav" aria-label="填写章节">${S.schema.sections.map((sec,i)=>`<button type="button" class="step-button ${i===S.step?'active':''}" data-action="step" data-step="${i}" ${i===S.step?'aria-current="step"':''}><span class="step-number">${String(i+1).padStart(2,'0')}</span>${esc(sec.label)}<span class="step-check" data-step-check="${i}"></span></button>`).join('')}</nav><p class="side-note">写下个人看法即可。<br>彼此的答案会在双方提交、输入密码后展示。<br><br>未填写不会被当作同意或反对，也不会计分。</p><button class="inline-link" data-action="download-own">下载我的草稿备份</button></aside><section class="form-panel"><div class="section-head"><div class="section-index">${String(S.step+1).padStart(2,'0')} / 07 · YOUR OWN VOICE</div><h2 id="section-title" tabindex="-1">${esc(section.label)}</h2><p>${esc(section.intro)}</p></div><form id="answer-form">${section.fields.map(fieldHtml).join('')}</form>${S.step===6?'<div class="notice">提交的是你此刻的个人建议。共同方向会在会议交流后另行记录；结束棒球也是可讨论的选择。</div>':''}<div class="form-bottom"><span class="save-status" id="save-status" role="status"><span class="small-dot"></span><span>${esc(S.saveMessage)}</span></span><div class="form-actions">${S.step>0?'<button class="button secondary" data-action="previous">上一步</button>':''}${S.step<6?'<button class="button" data-action="next">下一步 →</button>':'<button class="button" data-action="submit">提交我的想法 ↗</button>'}</div></div><section class="waiting"><h3>准备好，再开始共同查看。</h3><div class="status-pair" id="participant-status">${statusMarkup()}</div><p class="help" id="waiting-message">${S.state.can_open?'已具备查看条件，可点击按钮输入会议密码。':'双方各自提交后，才可点击按钮输入会议密码。'}</p><div id="answer-open-button" style="margin-top:14px">${openButton()}</div></section></section></div></div>`;
    $('#answer-form').addEventListener('submit',event=>event.preventDefault());
    $('#answer-form').addEventListener('input',handleAnswerInput);
    $('#answer-form').addEventListener('change',handleAnswerInput);
    updateProgress();
  }
  function setSaveStatus(message,failed=false) {
    S.saveMessage=message;
    const node=$('#save-status'); if(node){node.classList.toggle('failed',failed);node.innerHTML=`<span class="small-dot"></span><span>${esc(message)}</span>`;}
  }
  function preserveDraft() { storeSet(draftKey(),{answers:S.draft,baseRevision:S.revision,updatedAt:new Date().toISOString()}); }
  function changed() {
    S.dirty=true;preserveDraft();S.state.own.ready=false;S.state.participants[S.state.role].ready=false;
    if(!S.state.opened_at)S.state.can_open=false;
    updateProgress();updateStatuses();setSaveStatus('已存本机，正在同步…');
    clearTimeout(S.saveTimer);S.saveTimer=setTimeout(()=>enqueueDraft().catch(()=>{}),900);
  }
  function handleAnswerInput(event) {
    const node=event.target;
    if(node.dataset.field){const field=allFields().find(f=>f.id===node.dataset.field);if(field.type==='number'){if(node.value==='')delete S.draft[field.id];else S.draft[field.id]=Number(node.value);}else S.draft[field.id]=node.value;const counter=$(`[data-counter="${field.id}"]`);if(counter)counter.textContent=`${node.value.length} / 6000`;changed();}
    if(node.dataset.pathCondition){const id=node.dataset.pathCondition;S.draft.path_views={...S.draft.path_views,[id]:{...S.draft.path_views?.[id],conditions:node.value}};changed();}
  }
  function enqueueDraft() {
    S.saveChain=S.saveChain.catch(()=>{}).then(async()=>{
      if(!S.dirty)return;
      if(S.conflict)throw new Error('请先下载本机草稿，再刷新读取最新版本。');
      const answers=clone(S.draft),fingerprint=JSON.stringify(answers);
      try{const result=await meetingRequest('/answers',{method:'PUT',body:JSON.stringify({answers,revision:S.revision,submit:false})});S.revision=result.revision;S.dirty=JSON.stringify(S.draft)!==fingerprint;if(!S.dirty){storeRemove(draftKey());setSaveStatus('草稿已同步');}else{preserveDraft();setSaveStatus('正在同步新的修改…');}}
      catch(error){if(error.status===409)S.conflict=true;preserveDraft();setSaveStatus(error.status===409?'版本有更新，请下载备份':'仅存本机，尚未同步',true);toast(error.message||'未能同步，草稿已保存在此设备。');throw error;}
    });
    return S.saveChain;
  }
  async function flushDraft(){clearTimeout(S.saveTimer);await enqueueDraft();if(S.dirty)await enqueueDraft();}
  function rerenderField(id) {const field=allFields().find(f=>f.id===id);const wrap=$(`[data-field-wrapper="${id}"]`);if(wrap)wrap.outerHTML=fieldHtml(field);}
  function updateStatuses(){
    if(!S.state)return;
    const pair=$('#participant-status');if(pair)pair.innerHTML=statusMarkup();
    ['dad','mom'].forEach(role=>{const node=$(`#owner-status-${role}`);if(node){node.textContent=statusText(S.state.participants[role]);node.className=`badge ${S.state.participants[role].ready?'good':''}`;}});
    document.querySelectorAll('[data-action="unlock"]').forEach(button=>{button.disabled=!S.state.can_open;button.textContent=S.state.opened_at?'进入共同查看 ↗':'开始共同查看 ↗';});
    const ownerMessage=$('#owner-wait-message');if(ownerMessage)ownerMessage.textContent=S.state.can_open?'已具备查看条件，输入会议密码即可进入。':'等待双方各自提交；一方完成后，也可以先休息。';
    const waiting=$('#waiting-message');if(waiting)waiting.textContent=S.state.can_open?'已具备查看条件，可点击按钮输入会议密码。':'双方各自提交后，才可点击按钮输入会议密码。';
  }
  async function poll(){
    if(!S.context||document.hidden)return;
    try{
      const fresh=await meetingRequest();
      const previous=S.state;
      if(S.mode==='answer'&&fresh.own&&fresh.own.revision!==S.revision&&!S.dirty){S.conflict=true;setSaveStatus('另一设备有更新，请刷新',true);}
      S.state=fresh;
      if(S.dirty&&S.state.own){S.state.own.ready=false;S.state.participants[S.state.role].ready=false;if(!S.state.opened_at)S.state.can_open=false;}
      updateStatuses();
      if(S.mode==='meeting'&&!fresh.unlocked){S.mode=S.state.role==='owner'?'owner':'answer';render();toast('共同查看已过期，请重新输入会议密码。');return;}
      const active=document.activeElement,editing=active&&active.matches('input,textarea,select');
      if(S.mode==='meeting'&&S.tab==='compare'&&!editing&&JSON.stringify(previous.participants)!==JSON.stringify(fresh.participants))renderMeeting();
      if(S.mode==='meeting'&&S.tab==='notes'&&fresh.notes_revision!==S.notesRevision&&!S.notesDirty&&!editing){S.notes=clone(fresh.notes||{});S.notesRevision=fresh.notes_revision;renderMeeting();}
    }catch{}
  }
  const guideSteps=[
    ['5 分钟','先确认共同目标','各自从期待里选一项最重要的，说清为什么。另一方先听；不急着讨论谁更懂棒球。','我们都希望孩子和家庭获得什么？'],
    ['8 分钟','轮流表达，各说四分钟','一人讲自己的首选道路、顾虑与承受范围，另一人先不打断。然后交换。','我的建议是……我最担心的是……我能承担到……'],
    ['8 分钟','先复述，再讨论分歧','各自复述对方最看重与最担心的事，请对方修正。确认理解后，再挑出今晚最需要处理的一两个分歧。','我听到你最在意的是……我理解得对吗？'],
    ['15 分钟','按同样条件比较道路','查看六条路的态度与条件。优先讨论双方都能考虑的方案；把需要查证的信息单独记下。对结束或暂停，也认真讨论孩子的意愿与后续安排。','什么条件落实后，这条路才值得选择？条件没落实时，我们接受什么备选？'],
    ['9 分钟','记录当前方向与下一步','写下共识、保留的分歧、具体行动、分工和复盘日期。尚未听孩子意见时，标记父母暂定方案；若未达成路线共识，先约定过渡安排和补充信息。','我们目前共同接受的是……接下来由谁在何时完成什么？']
  ];
  function guideHtml(){return `<div class="guide-intro"><div class="eyebrow">TONIGHT / ABOUT 45 MINUTES</div><h2>先理解彼此，再一起作选择。</h2><p class="muted">这些答案是对话的起点。选项重合可以提供线索，文字不同也不一定代表真正分歧。请亲口确认彼此的意思。</p></div>${guideSteps.map((step,i)=>`<section class="guide-step"><div class="guide-time">0${i+1}<br>${step[0]}</div><div><h3>${step[1]}</h3><p>${step[2]}</p><div class="prompt">${step[3]}</div></div></section>`).join('')}<div class="notice">如果一方需要暂停，先约定何时继续。今晚可以留下分歧，也可以只确定一段过渡方案。孩子的意愿和实际体验需要继续进入后续决定。</div><div class="button-row"><button class="button" data-action="view-tab" data-tab="compare">并排看答案 →</button><button class="button secondary" data-action="view-tab" data-tab="notes">记录共识与行动 →</button></div>`;}
  function formattedAnswer(field,answer){
    const value=answer?.[field.id];
    if(value===undefined||value===null||value===''||(Array.isArray(value)&&!value.length))return '<span class="answer-empty">未填写 · 不代表同意或反对</span>';
    if(field.type==='rank')return `<div class="chips">${value.map((text,index)=>`<span class="chip">${index+1}. ${esc(text)}</span>`).join('')}</div>`;
    let text=field.type==='path_select'?pathName(value):field.type==='number'?`${value} ${field.unit}`:String(value);
    return `<div class="answer-text">${esc(text)}</div>`;
  }
  function commonHtml(id){const dad=S.state.participants.dad.answers?.[id]||[],mom=S.state.participants.mom.answers?.[id]||[];const common=dad.filter(value=>mom.includes(value));return common.length?`<div class="chips">${common.map(value=>`<span class="chip">${esc(value)}</span>`).join('')}</div>`:'<p class="muted">暂未出现相同选择，可以先听听彼此的理由。</p>';}
  function pathsComparison(){return `<div class="table-wrap"><table class="paths-compare"><thead><tr><th scope="col">道路</th><th scope="col">爸爸</th><th scope="col">妈妈</th></tr></thead><tbody>${S.schema.paths.map(path=>`<tr><td>${esc(path.label)}</td>${['dad','mom'].map(role=>{const value=S.state.participants[role].answers?.path_views?.[path.id]||{};return `<td><span class="badge ${value.stance==='prefer'||value.stance==='conditional'?'good':value.stance==='no'?'orange':''}">${esc(stanceName(value.stance))}</span>${value.conditions?`<p>${esc(value.conditions)}</p>`:''}</td>`;}).join('')}</tr>`).join('')}</tbody></table></div>`;}
  function comparisonHtml(){return `<div class="summary-grid"><section class="panel"><h3>共同选中的期待</h3>${commonHtml('goals')}</section><section class="panel"><h3>共同选中的必要条件</h3>${commonHtml('must_haves')}</section></div><p class="help">这里只展示选择的重合，不代表已经形成共识。请继续确认优先顺序和接受条件。未重新提交的修改仍保留在个人草稿中。</p><section class="panel" style="margin:25px 0"><h3>六条路，放在一起看</h3>${pathsComparison()}</section>${S.schema.sections.map((section,index)=>`<details class="comparison-section" ${index===0?'open':''}><summary>${String(index+1).padStart(2,'0')} / ${esc(section.label)}</summary>${section.fields.filter(field=>field.type!=='paths').map(field=>`<div class="comparison-item"><div class="comparison-label">${esc(field.label)}</div><div class="answer-pair">${['dad','mom'].map(role=>`<div class="answer-cell"><div class="answer-name">${roles[role]}</div>${formattedAnswer(field,S.state.participants[role].answers)}</div>`).join('')}</div></div>`).join('')}${index===3?pathsComparison():''}</details>`).join('')}`;}
  function notesHtml(){return `<div class="notes-intro"><div class="eyebrow" style="color:#d9e6c1">OUR NEXT CHAPTER</div><h2>把今晚的共识，变成下一步。</h2><p>这是共同记录。选择一人主要填写，另一人确认，能减少同时修改的冲突。分歧与未知也值得保留。</p></div>${S.localNotesRecovery?'<div class="edit-warning">此设备有未同步的会议记录。<button class="inline-link" data-action="download-note-recovery">先下载本机记录备份</button>，再与当前版本核对。</div>':''}<form id="notes-form" class="notes-grid">${noteFields.map(([id,label,type,width,hint])=>{const value=S.notes[id]||'';let input;if(type==='direction')input=`<select id="note-${id}" data-note="${id}"><option value="">请选择共同方向</option>${[...S.schema.paths,{id:'undecided',label:'暂未达成一致，先确定过渡安排'}].map(path=>`<option value="${path.id}" ${value===path.id?'selected':''}>${esc(path.label)}</option>`).join('')}</select>`;else if(type==='child')input=`<select id="note-${id}" data-note="${id}"><option value="">请选择当前状态</option><option value="pending" ${value==='pending'?'selected':''}>父母暂定，待听取孩子意见</option><option value="heard" ${value==='heard'?'selected':''}>已听取孩子意见，尚未共同确认</option><option value="confirmed" ${value==='confirmed'?'selected':''}>孩子参与讨论并共同确认</option></select>`;else if(type==='text')input=`<textarea id="note-${id}" data-note="${id}" maxlength="8000">${esc(value)}</textarea>`;else input=`<input id="note-${id}" data-note="${id}" type="${type==='date'?'date':'text'}" maxlength="8000" value="${esc(value)}">`;return `<div class="field ${width}"><label for="note-${id}">${label}</label>${hint?`<p class="hint">${hint}</p>`:''}${input}</div>`;}).join('')}</form><div class="form-bottom"><span id="notes-save-status" class="save-status" role="status"><span class="small-dot"></span><span>${S.notesDirty?'本机有未同步修改':'会议记录已同步'}</span></span><button class="button" data-action="save-notes">保存会议记录</button></div>`;}
  function renderMeeting(){
    if(!S.state.unlocked)return;
    $('#main').innerHTML=`<div class="page">${header()}<nav class="view-tabs" aria-label="共同查看内容">${[['guide','今晚怎么谈'],['compare','并排看答案'],['notes','共识与行动']].map(([id,label])=>`<button class="view-tab ${S.tab===id?'active':''}" data-action="view-tab" data-tab="${id}" ${S.tab===id?'aria-current="page"':''}>${label}</button>`).join('')}</nav><section id="shared-content">${S.tab==='guide'?guideHtml():S.tab==='compare'?comparisonHtml():notesHtml()}</section><section class="export-panel"><div class="button-row"><button class="button secondary small" data-action="export-markdown">导出答案与会议记录</button><button class="button secondary small" data-action="export-json">下载完整备份</button><button class="button ghost small" data-action="copy-report">复制给后续讨论</button><button class="button ghost small" data-action="print">打印当前页面</button></div><p class="help">导出文件包含双方已提交的答案与共同记录，不包含密码、专属链接或未提交草稿。可保存后带回继续讨论。</p></section></div>`;
    $('#notes-form')?.addEventListener('submit',event=>event.preventDefault());
    $('#notes-form')?.addEventListener('input',event=>{const id=event.target.dataset.note;if(id){S.notes[id]=event.target.value;notesChanged();}});
    $('#notes-form')?.addEventListener('change',event=>{const id=event.target.dataset.note;if(id){S.notes[id]=event.target.value;notesChanged();}});
  }
  function notesStatus(message,failed=false){const node=$('#notes-save-status');if(node){node.classList.toggle('failed',failed);node.innerHTML=`<span class="small-dot"></span><span>${esc(message)}</span>`;}}
  function notesChanged(){S.notesDirty=true;storeSet(notesKey(),{notes:S.notes,baseRevision:S.notesRevision});notesStatus('已存本机，正在同步…');clearTimeout(S.noteTimer);S.noteTimer=setTimeout(()=>enqueueNotes().catch(()=>{}),1100);}
  function enqueueNotes(){
    S.noteChain=S.noteChain.catch(()=>{}).then(async()=>{if(!S.notesDirty)return;const notes=clone(S.notes),fingerprint=JSON.stringify(notes);try{const result=await meetingRequest('/notes',{method:'PUT',body:JSON.stringify({notes,revision:S.notesRevision})});S.notesRevision=result.notes_revision;S.notesDirty=JSON.stringify(S.notes)!==fingerprint;if(!S.notesDirty){storeRemove(notesKey());notesStatus('会议记录已同步');}else storeSet(notesKey(),{notes:S.notes,baseRevision:S.notesRevision});}catch(error){notesStatus('尚未同步，请先导出备份',true);toast(error.message);throw error;}});
    return S.noteChain;
  }
  async function flushNotes(){clearTimeout(S.noteTimer);await enqueueNotes();if(S.notesDirty)await enqueueNotes();}
  function render(){if(S.mode==='owner')renderOwner();else if(S.mode==='answer')renderAnswer();else if(S.mode==='meeting')renderMeeting();}
  function plain(field,answers){const value=answers?.[field.id];if(value===undefined||value===null||value===''||(Array.isArray(value)&&!value.length))return '未填写（不代表同意或反对）';if(field.type==='rank')return value.map((text,index)=>`${index+1}. ${text}`).join('；');if(field.type==='path_select')return pathName(value);if(field.type==='number')return `${value} ${field.unit}`;return String(value);}
  function exportData(){if(!S.state.unlocked)throw new Error('请先输入密码共同查看。');return {format:'jingsen-familymeeting-v1',title:S.state.title,meeting_date:S.state.meeting_date,exported_at:new Date().toISOString(),questionnaire:S.schema,answers:{dad:S.state.participants.dad.answers,mom:S.state.participants.mom.answers},notes:clone(S.notes),child_participation:S.notes.child_state||'pending'};}
  function report(){
    const data=exportData();let output=`# ${data.title}\n\n会议日期：${data.meeting_date}\n\n## 共识与行动\n\n`;
    noteFields.forEach(([id,label,type])=>{let value=data.notes[id];if(id==='direction')value=pathName(value);if(id==='child_state')value={pending:'父母暂定，待听取孩子意见',heard:'已听取孩子意见，尚未共同确认',confirmed:'孩子参与讨论并共同确认'}[value]||'尚未记录，待确认孩子意见';output+=`### ${label}\n\n${value||'尚未记录'}\n\n`;});
    output+='## 双方独立填写的答案\n\n';S.schema.sections.forEach(section=>{output+=`### ${section.label}\n\n`;section.fields.forEach(field=>{output+=`**${field.label}**\n\n`;if(field.type==='paths'){S.schema.paths.forEach(path=>{output+=`${path.label}\n`;['dad','mom'].forEach(role=>{const value=data.answers[role]?.path_views?.[path.id]||{};output+=`- ${roles[role]}：${stanceName(value.stance)}；${value.conditions||'未补充条件'}\n`;});output+='\n';});}else{['dad','mom'].forEach(role=>output+=`${roles[role]}：${plain(field,data.answers[role])}\n\n`);}});});
    return output+'\n未填写不代表同意或反对。道路与预算尚需结合共同记录理解。\n';
  }
  function download(name,content,type='text/plain;charset=utf-8'){const blob=new Blob([content],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);}
  async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制。');}catch{download('家庭会议-复制内容.txt',text);toast('浏览器未允许复制，已改为下载文件。');}}
  async function enterShared(){await flushDraftIfNeeded();S.state=await meetingRequest();if(!S.state.unlocked){$('#meeting-password').value='';$('#unlock-error').hidden=true;$('#unlock-dialog').showModal();$('#meeting-password').focus();return;}S.mode='meeting';S.tab='guide';S.notes=clone(S.state.notes||{});S.notesRevision=S.state.notes_revision;S.localNotesRecovery=storeGet(notesKey());render();}
  async function flushDraftIfNeeded(){if(S.context&&S.state?.role!=='owner'&&S.dirty)await flushDraft();}
  async function stepTo(index){S.step=Math.max(0,Math.min(6,index));renderAnswer();$('#section-title')?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'instant'});}
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-action]');if(!button||button.disabled)return;
    const action=button.dataset.action;
    try{
      if(action==='resume'){const value=storeGet('fm_recent');if(value)await openContext(value.id,value.token);}
      if(action==='manage-existing'){const access=await request(`${API}/${button.dataset.id}/access`,{method:'POST',body:'{}'});rememberLinks(access);await openContext(access.id,access.tokens.owner);}
      if(action==='fill-role'){if(!S.links)throw new Error('请从会议管理页重新获取填写链接。');await openContext(S.context.id,S.links.tokens[button.dataset.role]);}
      if(action==='copy-role'){if(!S.links)throw new Error('请从会议管理页重新获取链接。');await copy(contextUrl(S.context.id,S.links.tokens[button.dataset.role]));}
      if(action==='owner'){await openContext(S.context.id,S.links.tokens.owner);}
      if(action==='home'){await flushDraftIfNeeded();if(S.notesDirty)await flushNotes();clearInterval(S.poll);S.context=null;S.grant='';history.replaceState(null,'',ROOT);await landing();}
      if(action==='step')await stepTo(Number(button.dataset.step));
      if(action==='previous')await stepTo(S.step-1);
      if(action==='next')await stepTo(S.step+1);
      if(action==='unknown'){const id=button.dataset.fieldId;S.draft[id]='暂时不知道';changed();rerenderField(id);}
      if(action==='rank'){const id=button.dataset.fieldId,field=allFields().find(f=>f.id===id),value=field.options[Number(button.dataset.option)],selected=[...(S.draft[id]||[])],index=selected.indexOf(value);if(index>=0)selected.splice(index,1);else if(selected.length<3)selected.push(value);else{toast('最多选三项。取消一项后可以重新排序。');return;}S.draft[id]=selected;changed();rerenderField(id);}
      if(action==='stance'){const id=button.dataset.path;const stance=S.draft.path_views?.[id]?.stance===button.dataset.stance?'':button.dataset.stance;S.draft.path_views={...S.draft.path_views,[id]:{...S.draft.path_views?.[id],stance}};changed();rerenderField('path_views');}
      if(action==='submit'){await flushDraft();$('#submit-message').textContent=`你已记录 ${countAnswers()} 项想法。没有填写的问题会保留为空白，不会被当作同意或反对。`;$('#submit-dialog').showModal();}
      if(action==='close-submit')$('#submit-dialog').close();
      if(action==='confirm-submit'){button.disabled=true;try{await flushDraft();const result=await meetingRequest('/answers',{method:'PUT',body:JSON.stringify({answers:S.draft,revision:S.revision,submit:true})});S.revision=result.revision;S.dirty=false;storeRemove(draftKey());$('#submit-dialog').close();S.state=await meetingRequest();S.saveMessage='已提交，准备交流';renderAnswer();toast('已提交。双方都提交后，可输入密码开始共同查看。');}finally{button.disabled=false;}}
      if(action==='unlock')await enterShared();
      if(action==='close-unlock')$('#unlock-dialog').close();
      if(action==='view-tab'){if(S.notesDirty)await flushNotes();S.tab=button.dataset.tab;renderMeeting();window.scrollTo({top:0,behavior:'instant'});}
      if(action==='leave-meeting'){if(S.notesDirty)await flushNotes();S.mode=S.state.role==='owner'?'owner':'answer';render();}
      if(action==='preview-guide'){const dialog=document.createElement('dialog');dialog.innerHTML=`<div class="eyebrow">TONIGHT / 45 MINUTES</div><h2>今晚的对话顺序</h2>${guideSteps.map(step=>`<p><strong>${step[0]} · ${step[1]}</strong><br>${step[2]}</p>`).join('')}<button class="button" data-action="close-preview">知道了</button>`;dialog.id='preview-dialog';document.body.append(dialog);dialog.showModal();}
      if(action==='close-preview'){$('#preview-dialog').close();$('#preview-dialog').remove();}
      if(action==='download-own')download(`${S.state.meeting_date}-${roles[S.state.role]}-我的草稿.json`,JSON.stringify({title:S.state.title,role:S.state.role,questionnaire:S.schema,answers:S.draft},null,2),'application/json');
      if(action==='download-recovery')download('家庭会议-未同步草稿.json',JSON.stringify(S.localRecovery,null,2),'application/json');
      if(action==='restore-draft'){S.draft=clone(S.localRecovery.answers);S.localRecovery=null;changed();renderAnswer();}
      if(action==='dismiss-recovery'){S.localRecovery=null;storeRemove(draftKey());renderAnswer();}
      if(action==='download-note-recovery')download('家庭会议-未同步记录.json',JSON.stringify(S.localNotesRecovery,null,2),'application/json');
      if(action==='save-notes'){await flushNotes();toast('会议记录已保存。');}
      if(action==='export-markdown')download(`${S.state.meeting_date}-家庭会议记录.md`,report(),'text/markdown;charset=utf-8');
      if(action==='export-json')download(`${S.state.meeting_date}-家庭会议完整备份.json`,JSON.stringify(exportData(),null,2),'application/json');
      if(action==='copy-report')await copy(report());
      if(action==='print'){document.querySelectorAll('.comparison-section').forEach(details=>details.open=true);window.print();}
    }catch(error){toast(error.message||'暂时未能完成，请稍后重试。');}
  });
  $('#unlock-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=$('button[type=submit]',event.target);button.disabled=true;$('#unlock-error').hidden=true;
    try{const result=await meetingRequest('/unlock',{method:'POST',body:JSON.stringify({password:$('#meeting-password').value})});S.grant=result.view_grant;storeSet(grantKey(),S.grant,true);$('#meeting-password').value='';S.state=await meetingRequest();$('#unlock-dialog').close();S.mode='meeting';S.tab='guide';S.notes=clone(S.state.notes||{});S.notesRevision=S.state.notes_revision;S.localNotesRecovery=storeGet(notesKey());render();}
    catch(error){$('#unlock-error').textContent=error.message;$('#unlock-error').hidden=false;}
    finally{button.disabled=false;}
  });
  window.addEventListener('beforeunload',event=>{if(S.dirty||S.notesDirty){event.preventDefault();event.returnValue='';}});
  window.addEventListener('online',()=>{if(S.dirty)enqueueDraft().catch(()=>{});if(S.notesDirty)enqueueNotes().catch(()=>{});});
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
  async function boot(){
    try{S.schema=await request('/baseball/familymeeting/assets/questions.json');const params=new URLSearchParams(location.hash.slice(1));if(params.get('m')&&params.get('k'))await openContext(params.get('m'),params.get('k'));else await landing();}
    catch(error){$('#main').innerHTML=`<div class="fatal"><div class="eyebrow">FAMILY MEETING</div><h1 style="font-size:31px">暂时没有打开这份会议</h1><p>${esc(error.message||'请检查网络，或重新使用专属链接。')}</p><a class="button" href="${ROOT}">返回会议入口</a></div>`;}
  }
  boot();
})();
