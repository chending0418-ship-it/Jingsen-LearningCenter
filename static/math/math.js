(() => {
    const {MathPad, format, element, questionReview, metric} = window.MathUI;
    const $ = id => document.getElementById(id);
    const base = location.pathname.startsWith('/learningcenter') ? '/learningcenter' : '';
    const key = 'jlc-math-factorization-v1';
    const draftKey = 'jlc-math-factorization-drafts-v1';
    let session = null, token = '', selectedId = null, busy = false, drafts = {};
    $('back-link').href = base + '/portal';
    function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
    function store(name, value) {
        try { localStorage.setItem(name, JSON.stringify(value)); }
        catch { notice('浏览器未能保存继续练习的位置，请保持此页面打开。已提交的答案仍保存在服务器。'); }
    }
    function read(name) {
        try { return JSON.parse(localStorage.getItem(name) || 'null'); } catch { return null; }
    }
    function remove(name) { try { localStorage.removeItem(name); } catch {} }
    const pad = new MathPad($('math-pad'), value => {
        if (session && selectedId) {
            drafts[selectedId] = value;
            store(draftKey, {session_id: session.id, drafts});
        }
        $('submit-button').disabled = busy || !pad.value().answer.trim();
    });
    async function api(path, payload) {
        const response = await fetch(base + '/api/math/factorization' + path, {
            method: payload === undefined ? 'GET' : 'POST', cache: 'no-store',
            headers: {'Content-Type': 'application/json', ...(token ? {'X-Math-Session': token} : {})},
            ...(payload === undefined ? {} : {body: JSON.stringify(payload)}),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            const error = new Error(typeof data.detail === 'string' ? data.detail : `请求未完成（${response.status}），请重试。`);
            error.status = response.status; throw error;
        }
        return data;
    }
    function show(view) { ['home-view', 'practice-view', 'result-view'].forEach(id => { $(id).hidden = id !== view; }); }
    function setBusy(value) {
        busy = value; pad.setLocked(value);
        ['start-button', 'again-button', 'resume-button', 'pause-button', 'hint-button', 'skip-button', 'confirm-skip-button', 'cancel-skip-button', 'next-button'].forEach(id => { $(id).disabled = value; });
        $('submit-button').disabled = value || !pad.value().answer.trim();
        if (!value && session) { const q = session.questions.find(q => q.id === selectedId); if (q) $('hint-button').disabled = q.hints_used >= q.hint_count; }
    }
    function current() { return session?.questions.find(q => !q.answered_at); }
    function home() {
        show('home-view');
        $('resume-button').hidden = !session || session.status === 'completed';
        $('start-button').hidden = Boolean(session && session.status === 'active');
        $('home-status').textContent = session?.status === 'active' ? `已完成 ${session.answered_count}/10 题，点击继续。` : '每题自动保存，完成后查看正确率与错题。';
        $('session-counter').textContent = '10 道题 / 每轮';
    }
    async function start() {
        if (busy) return;
        notice(); setBusy(true);
        try {
            const created = await api('/sessions', {question_count: 10});
            session = created; token = created.access_token; drafts = {};
            store(key, {id: session.id, token}); store(draftKey, {session_id: session.id, drafts});
            selectedId = session.questions[0].id; renderQuestion();
        } catch (error) { notice(error.message); }
        finally { setBusy(false); }
    }
    function renderHints(q) {
        $('hints').replaceChildren(...q.visible_hints.map((hint, i) => element('p', '', `${i + 1}. ${format(hint)}`)));
        $('hints').hidden = !q.visible_hints.length;
        $('hint-button').textContent = q.hints_used >= q.hint_count ? '已显示全部提示' : q.hints_used ? '再给一点提示' : '给我一点提示';
        $('hint-button').disabled = busy || q.hints_used >= q.hint_count;
    }
    function renderQuestion() {
        const q = session.questions.find(q => q.id === selectedId);
        if (!q) { renderResults(); return; }
        show('practice-view');
        $('session-counter').textContent = `已完成 ${session.answered_count} / 10`;
        $('progress-fill').style.width = `${session.answered_count * 10}%`;
        document.querySelector('.math-progress').setAttribute('aria-valuenow', session.answered_count);
        const currentId = current()?.id;
        $('question-nav').replaceChildren(...session.questions.map(item => {
            const button = element('button'); button.type = 'button';
            button.disabled = !item.answered_at && item.id !== currentId;
            button.setAttribute('aria-current', String(item.id === selectedId));
            button.setAttribute('aria-label', `第 ${item.position} 题${item.answered_at ? item.result.correct ? '，答对' : '，需复习' : ''}`);
            button.append(element('span', '', String(item.position).padStart(2, '0')), element('span', 'q-mark', item.answered_at ? item.result.correct ? '✓' : '×' : item.is_challenge ? '⋆' : '·'));
            button.addEventListener('click', () => { if (!busy) { selectedId = item.id; notice(); renderQuestion(); } });
            return button;
        }));
        $('question-number').textContent = `QUESTION ${String(q.position).padStart(2, '0')} / 10`;
        $('challenge-label').hidden = !q.is_challenge;
        $('question-expression').textContent = format(q.expression);
        $('skip-confirm').hidden = true;
        $('answer-area').hidden = Boolean(q.answered_at);
        $('question-feedback').hidden = !q.answered_at;
        $('next-button').hidden = !q.answered_at;
        if (q.answered_at) {
            $('question-feedback').replaceChildren(questionReview(q, true));
            $('next-button').textContent = current() ? '继续下一题 →' : '查看本轮结果 →';
        } else {
            pad.load(drafts[q.id] || {}); renderHints(q);
            $('submit-button').disabled = busy || !pad.value().answer.trim();
        }
    }
    async function submit(skipped = false) {
        if (busy) return;
        const q = current(); if (!q || q.id !== selectedId) return;
        const value = pad.value();
        if (!skipped && !value.answer.trim()) { notice('先点击按键填写最终答案。'); return; }
        notice(); setBusy(true);
        try {
            session = await api(`/sessions/${session.id}/answers`, {question_id: q.id, ...value, skipped});
            delete drafts[q.id]; store(draftKey, {session_id: session.id, drafts}); renderQuestion();
        } catch (error) {
            notice(error.message);
            if (error.status === 409) {
                try { session = await api(`/sessions/${session.id}`); renderQuestion(); } catch {}
            }
        } finally { setBusy(false); }
    }
    async function hint() {
        if (busy) return;
        const q = current(); if (!q || q.id !== selectedId || q.hints_used >= q.hint_count) return;
        notice(); setBusy(true);
        try { session = await api(`/sessions/${session.id}/hints`, {question_id: q.id, level: q.hints_used + 1}); renderHints(session.questions.find(item => item.id === q.id)); }
        catch (error) { notice(error.message); } finally { setBusy(false); }
    }
    function renderResults() {
        show('result-view'); selectedId = null;
        $('session-counter').textContent = '10 / 10 已完成';
        const basic = session.questions.slice(0, 8).filter(q => q.result.correct).length;
        const thinking = session.questions.slice(8).filter(q => q.result.correct).length;
        $('result-metrics').replaceChildren(
            metric('本轮正确率', `${session.accuracy}%`, `${session.correct_count}/10 首次提交正确`),
            metric('独立答对', `${session.independent_correct_count}/10`, '未查看提示并首次答对'),
            metric('常规与进阶', `${basic}/8`, '公因式、公式与连续分解'),
            metric('思考题', `${thinking}/2`, '换元与添项配方'),
        );
        const visible = session.questions.filter(q => !$('only-mistakes').checked || !q.result.correct);
        $('result-questions').replaceChildren(...(visible.length ? visible.map(q => questionReview(q, !q.result.correct)) : [element('div', 'empty-state', '这轮没有错题。')]));
    }
    async function resume() {
        const saved = read(key);
        if (!saved?.id || !saved?.token) return;
        token = saved.token; setBusy(true); $('home-status').textContent = '正在读取上次训练…';
        try {
            session = await api(`/sessions/${encodeURIComponent(saved.id)}`);
            const cached = read(draftKey); drafts = cached?.session_id === session.id && cached.drafts && typeof cached.drafts === 'object' ? cached.drafts : {};
            if (session.status === 'completed') renderResults();
            else { selectedId = current().id; renderQuestion(); }
        } catch (error) {
            if (error.status === 404 || error.status === 422) { remove(key); remove(draftKey); token = ''; }
            notice(error.message); home();
        } finally { setBusy(false); }
    }
    $('start-button').addEventListener('click', start); $('again-button').addEventListener('click', start);
    $('resume-button').addEventListener('click', () => { if (!busy) { selectedId = current().id; renderQuestion(); } });
    $('pause-button').addEventListener('click', () => { if (!busy) home(); });
    $('submit-button').addEventListener('click', () => submit(false)); $('hint-button').addEventListener('click', hint);
    $('skip-button').addEventListener('click', () => { $('skip-confirm').hidden = false; });
    $('cancel-skip-button').addEventListener('click', () => { $('skip-confirm').hidden = true; });
    $('confirm-skip-button').addEventListener('click', () => submit(true));
    $('next-button').addEventListener('click', () => { notice(); if (current()) { selectedId = current().id; renderQuestion(); } else renderResults(); });
    $('only-mistakes').addEventListener('change', renderResults);
    resume();
})();
