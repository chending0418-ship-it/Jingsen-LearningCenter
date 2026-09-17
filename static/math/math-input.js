/* Click-only mathematical input and shared, text-only report rendering. */
(() => {
    const superscripts = '⁰¹²³⁴⁵⁶⁷⁸⁹';
    const format = value => String(value ?? '').replace(/\*\*/g, '^').replace(/\^(\d+)/g, (_, n) => [...n].map(d => superscripts[Number(d)]).join('')).replace(/\*/g, '·').replace(/-/g, '−');
    const element = (tag, className, text) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined) node.textContent = text;
        return node;
    };
    class MathPad {
        constructor(root, onChange) {
            this.root = root; this.onChange = onChange;
            this.rows = [[]]; this.active = 0; this.cursor = 0; this.history = []; this.locked = false;
            root.innerHTML = '<div class="pad-label"><span>最终答案</span><span id="pad-position" class="muted"></span></div><div class="pad-final"></div><div class="pad-scratch" hidden></div><div class="pad-tools"><div class="pad-tools-group"><button type="button" data-pad-action="left" aria-label="光标左移">← 左移</button><button type="button" data-pad-action="right" aria-label="光标右移">右移 →</button></div><button type="button" data-pad-action="add">＋ 草稿 / 推导</button></div><div class="pad-extra-keys" hidden><button type="button" data-pad-key="t">t</button><button type="button" data-pad-key="t²">t²</button><button type="button" data-pad-key="=">＝</button></div><div class="pad-keys"></div>';
            const keys = ['x', 'x²', 'x³', 'x⁴', '(', ')', '7', '8', '9', '+', '−', '退格', '4', '5', '6', '×', '平方', '撤销', '1', '2', '3', '0'];
            keys.forEach(key => {
                const button = element('button', /^\d$/.test(key) ? '' : 'pad-symbol', key);
                button.type = 'button';
                const action = {'退格': 'backspace', '平方': 'square', '撤销': 'undo'}[key];
                if (action) { button.dataset.padAction = action; button.classList.add('pad-edit'); }
                else button.dataset.padKey = key;
                button.setAttribute('aria-label', {'x²': 'x 平方', 'x³': 'x 三次方', 'x⁴': 'x 四次方', '(': '左括号，自动配对', ')': '右括号，跳出括号', '平方': '将前面的数字、字母或括号整体平方'}[key] || key);
                if (key === '0') button.style.gridColumn = 'span 3';
                root.querySelector('.pad-keys').append(button);
            });
            root.addEventListener('click', event => {
                const button = event.target.closest('button');
                if (!button || !root.contains(button) || this.locked || button.disabled) return;
                if (button.dataset.padKey !== undefined) this.insert(button.dataset.padKey);
                else if (button.dataset.padAction) this.action(button.dataset.padAction);
            });
            this.render();
        }
        value() { return {answer: this.rows[0].join(''), scratch: this.rows.slice(1).map(row => row.join(''))}; }
        load(value = {}) {
            const safe = v => typeof v === 'string' ? Array.from(v).slice(0, 240) : [];
            this.rows = [safe(value.answer), ...(Array.isArray(value.scratch) ? value.scratch.slice(0, 6).map(safe) : [])];
            this.active = 0; this.cursor = this.rows[0].length; this.history = []; this.render();
        }
        remember() {
            this.history.push({rows: this.rows.map(row => row.slice()), active: this.active, cursor: this.cursor});
            if (this.history.length > 100) this.history.shift();
        }
        insert(value) {
            if (this.locked || this.rows[this.active].length + value.length + 1 > 240) return;
            this.remember();
            const row = this.rows[this.active];
            if (value === '(') { row.splice(this.cursor, 0, '(', ')'); this.cursor++; }
            else if (value === ')' && row[this.cursor] === ')') this.cursor++;
            else { const tokens = Array.from(value); row.splice(this.cursor, 0, ...tokens); this.cursor += tokens.length; }
            this.changed();
        }
        canSquare() { return /^(x|t|[0-9]|\))$/.test(this.rows[this.active][this.cursor - 1] || ''); }
        action(action) {
            const row = this.rows[this.active];
            if (action === 'left') this.cursor = Math.max(0, this.cursor - 1);
            else if (action === 'right') this.cursor = Math.min(row.length, this.cursor + 1);
            else if (action === 'square') { if (this.canSquare()) this.insert('²'); return; }
            else if (action === 'backspace' && this.cursor) {
                this.remember(); row.splice(this.cursor - 1, row[this.cursor - 1] === '(' && row[this.cursor] === ')' ? 2 : 1); this.cursor--;
            } else if (action === 'undo') {
                const previous = this.history.pop(); if (previous) Object.assign(this, previous);
            } else if (action === 'add' && this.rows.length < 7) {
                this.remember(); this.rows.push([]); this.active = this.rows.length - 1; this.cursor = 0;
            }
            this.changed();
        }
        changed() { this.render(); if (this.onChange) this.onChange(this.value()); }
        setLocked(locked) { this.locked = locked; this.render(); }
        editor(row, index) {
            const button = element('button', 'pad-editor'); button.type = 'button'; button.disabled = this.locked;
            button.setAttribute('aria-pressed', String(index === this.active));
            button.setAttribute('aria-label', `${index === 0 ? '最终答案' : `草稿第 ${index} 行`}：${row.join('') || '空白'}`);
            for (let i = 0; i <= row.length; i++) {
                if (index === this.active && i === this.cursor) { const caret = element('span', 'pad-caret'); caret.setAttribute('aria-hidden', 'true'); button.append(caret); }
                if (i < row.length) button.append(element('span', 'pad-token', row[i]));
            }
            if (!row.length) button.append(element('span', 'pad-placeholder', index ? '可写 t = x² 等推导' : '点击下方按键输入'));
            button.addEventListener('click', () => { if (!this.locked) { this.active = index; this.cursor = row.length; this.render(); } });
            return button;
        }
        render() {
            this.root.querySelector('.pad-final').replaceChildren(this.editor(this.rows[0], 0));
            const scratch = this.root.querySelector('.pad-scratch'); scratch.hidden = this.rows.length === 1;
            scratch.replaceChildren(element('p', 'muted', '草稿会保存到记录中；按最终答案判分。'));
            this.rows.slice(1).forEach((row, i) => {
                const wrapper = element('div', 'pad-scratch-row');
                const remove = element('button', 'pad-remove', '删除'); remove.type = 'button'; remove.disabled = this.locked;
                remove.setAttribute('aria-label', `删除草稿第 ${i + 1} 行`);
                remove.addEventListener('click', () => {
                    if (this.locked) return;
                    this.remember(); this.rows.splice(i + 1, 1); this.active = Math.min(this.active, this.rows.length - 1); this.cursor = this.rows[this.active].length; this.changed();
                });
                wrapper.append(this.editor(row, i + 1), remove); scratch.append(wrapper);
            });
            this.root.querySelector('#pad-position').textContent = this.active ? `正在编辑草稿 ${this.active}` : '正在编辑答案';
            this.root.querySelector('.pad-extra-keys').hidden = this.active === 0;
            this.root.querySelectorAll('[data-pad-key], [data-pad-action]').forEach(button => {
                const a = button.dataset.padAction;
                button.disabled = this.locked || (a === 'left' || a === 'backspace') && this.cursor === 0 || a === 'right' && this.cursor === this.rows[this.active].length || a === 'square' && !this.canSquare() || a === 'undo' && !this.history.length || a === 'add' && this.rows.length >= 7;
            });
        }
    }
    function questionReview(question, open = false) {
        const details = element('details', 'review-item'); details.open = open;
        const summary = element('summary');
        summary.append(element('span', 'math-expression', `${String(question.position).padStart(2, '0')}  ${format(question.expression)}`));
        const correct = question.result?.correct;
        const label = !question.answered_at ? '未作答' : correct ? (question.hints_used ? '提示后答对' : '独立答对') : question.result?.error_code === 'skipped' ? '未完成' : question.result?.error_code === 'incomplete' ? '未分解彻底' : '错误';
        summary.append(element('span', `review-status${!question.answered_at ? ' pending' : correct ? '' : ' wrong'}`, label + ' ＋'));
        const content = element('div', 'review-content');
        content.append(element('p', 'muted', `${question.skill_label || '因式分解'}${question.is_challenge ? ' · 思考题' : ''} · 使用提示 ${question.hints_used} 次`));
        if (question.answered_at) {
            const pair = element('div', 'answer-pair');
            [['首次答案', question.student_answer || '未作答'], ['参考答案', question.correct_answer]].forEach(([label, answer]) => {
                const block = element('div'); block.append(element('small', '', label), element('div', 'math-expression', format(answer))); pair.append(block);
            });
            content.append(pair, element('p', '', question.result.feedback));
        } else content.append(element('p', 'muted', '这道题尚未提交。'));
        if (question.solution_steps?.length) {
            const list = element('ol', 'solution-steps'); question.solution_steps.forEach(step => list.append(element('li', '', format(step)))); content.append(list);
        }
        if (question.scratch?.some(line => line.trim())) {
            content.append(element('p', 'muted', '保存的草稿（不参与判分）'));
            question.scratch.forEach(line => { if (line.trim()) content.append(element('p', 'math-expression', format(line))); });
        }
        details.append(summary, content); return details;
    }
    function metric(label, value, caption = '') {
        const node = element('div', 'math-metric'); node.append(element('small', '', label), element('strong', '', value));
        if (caption) node.append(element('span', '', caption)); return node;
    }
    window.MathUI = {MathPad, format, element, questionReview, metric};
})();
