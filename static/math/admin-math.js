(() => {
    const {element, questionReview, metric} = window.MathUI;
    const $ = id => document.getElementById(id);
    let offset = 0, selected = null, latest = [], busy = false, requestVersion = 0;
    const limit = 20;
    const date = value => new Date(value).toLocaleString('zh-CN', {timeZone: 'Asia/Shanghai', hour12: false});
    async function api(path) {
        const response = await fetch('/api/admin/math' + path, {cache: 'no-store'});
        if (response.status === 401) { location.href = '/admin?next=' + encodeURIComponent(location.pathname); throw new Error('请重新登录 Admin。'); }
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '读取记录失败，请重试。');
        return data;
    }
    function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
    function renderList() {
        $('history-list').replaceChildren(...(latest.length ? latest.map(row => {
            const button = element('button', 'history-item'); button.type = 'button'; button.setAttribute('aria-pressed', String(row.id === selected));
            button.append(element('strong', '', date(row.created_at)), element('span', '', row.status === 'completed' ? `正确率 ${row.accuracy}% · ${row.correct_count}/10 答对` : `进行中 · 已完成 ${row.answered_count}/10 题`));
            button.addEventListener('click', () => { if (!busy) loadDetail(row.id); }); return button;
        }) : [element('div', 'empty-state', '还没有符合条件的数学训练记录。')]));
    }
    async function loadDetail(id) {
        selected = id; renderList(); const version = ++requestVersion;
        $('history-detail').replaceChildren(element('div', 'empty-state', '正在读取这轮训练…')); notice();
        try {
            const session = await api(`/sessions/${encodeURIComponent(id)}`);
            if (version !== requestVersion) return;
            const target = $('history-detail'); target.replaceChildren();
            target.append(element('h2', '', '因式分解 · 10 道题'), element('p', 'muted', `开始：${date(session.created_at)}${session.completed_at ? ` · 完成：${date(session.completed_at)}` : ' · 进行中'}`));
            const incorrect = session.questions.filter(q => q.answered_at && !q.result.correct).length;
            target.append(element('div', 'history-summary', session.status === 'completed'
                ? `正确率 ${session.accuracy}%　·　首次答对 ${session.correct_count}/10　·　独立答对 ${session.independent_correct_count}/10　·　错误或未完成 ${incorrect} 题`
                : `已提交 ${session.answered_count}/10　·　已答对 ${session.correct_count} 题　·　错误或跳过 ${incorrect} 题。整轮正确率将在完成后计算。`));
            const heading = element('div', 'review-heading'); heading.append(element('h3', '', '逐题记录'));
            const label = element('label'); const checkbox = element('input'); checkbox.type = 'checkbox';
            label.append(checkbox, document.createTextNode('只看错误与跳过')); heading.append(label); target.append(heading);
            const list = element('div', 'result-questions'); target.append(list);
            const renderQuestions = () => {
                const visible = session.questions.filter(q => !checkbox.checked || q.answered_at && !q.result.correct);
                list.replaceChildren(...(visible.length ? visible.map(q => questionReview(q, Boolean(q.answered_at && !q.result.correct))) : [element('div', 'empty-state', '这轮目前没有错误或跳过的题目。')]));
            };
            checkbox.addEventListener('change', renderQuestions); renderQuestions();
        } catch (error) { if (version === requestVersion) { notice(error.message); $('history-detail').replaceChildren(element('div', 'empty-state', '未能读取记录，点击左侧记录重试。')); } }
    }
    async function load() {
        if (busy) return;
        busy = true; $('refresh-button').disabled = true; $('history-status').disabled = true;
        $('previous-button').disabled = true; $('more-button').disabled = true; notice();
        try {
            const params = new URLSearchParams({limit, offset});
            if ($('history-status').value) params.set('status', $('history-status').value);
            const data = await api('/sessions?' + params); latest = data.sessions;
            const stats = data.summary;
            $('history-metrics').replaceChildren(metric('累计正确率', stats.accuracy === null ? '—' : `${stats.accuracy}%`, '全部已完成训练'), metric('完成训练', stats.completed_sessions, '每轮固定 10 道题'), metric('错误与未完成', stats.incorrect_count, '包含跳过和未分解彻底'), metric('独立答对', stats.independent_correct_count, `${stats.total_questions} 道题中未用提示答对`));
            $('page-info').textContent = data.total ? `${offset + 1}–${offset + latest.length} / 共 ${data.total} 轮` : '共 0 轮';
            $('previous-button').disabled = offset === 0; $('more-button').disabled = offset + limit >= data.total;
            if (!latest.some(row => row.id === selected)) selected = latest[0]?.id || null;
            renderList();
            if (selected) await loadDetail(selected);
            else { requestVersion++; $('history-detail').replaceChildren(element('div', 'empty-state', '孩子完成训练后，记录会出现在这里。')); }
        } catch (error) { notice(error.message); }
        finally { busy = false; $('refresh-button').disabled = false; $('history-status').disabled = false; }
    }
    $('refresh-button').addEventListener('click', load);
    $('history-status').addEventListener('change', () => { offset = 0; load(); });
    $('previous-button').addEventListener('click', () => { if (!busy) { offset = Math.max(0, offset - limit); load(); } });
    $('more-button').addEventListener('click', () => { if (!busy) { offset += limit; load(); } });
    load();
})();
