const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const html = fs.readFileSync(path.join(__dirname, '../static/reading.html'), 'utf8');
const script = html.match(/<script id="reading-feedback-ui">([\s\S]*?)<\/script>/)[1];
const scope = {};
vm.runInNewContext(script, scope);
const {splitFeedback, renderAssessment} = scope.ReadingFeedback;
const plain = value => JSON.parse(JSON.stringify(value));
const feedback = 'Accurate: You connect the idea to action. Gap/misconception: You need resources and a practical first step. Next step: Write three parts: (1) his reason to believe, (2) his resources, and (3) his first practical action.';

test('splits existing inline feedback without dropping the actual assessment', () => {
    const parts = plain(splitFeedback(feedback));
    assert.equal(parts.accurate, 'You connect the idea to action.');
    assert.equal(parts.gap, 'You need resources and a practical first step.');
    assert.equal(parts.next_step, 'Write three parts: (1) his reason to believe, (2) his resources, and (3) his first practical action.');
    const rendered = renderAssessment(feedback, 'Keep exploring');
    assert.equal((rendered.match(/<article /g) || []).length, 3);
    assert.ok(rendered.includes('<ol class="assessment-steps">'));
    assert.equal((rendered.match(/<li>/g) || []).length, 3);
    assert.ok(rendered.includes('查看原始评估'));
    assert.ok(rendered.includes(feedback));
});

test('accepts paragraphs, markdown headings, case differences and plural steps', () => {
    const input = '**Accurate:** A correct idea.\n\n**Gap/misconception:** A missing detail.\n\n**Next steps:** Add a reason.';
    assert.deepEqual(plain(splitFeedback(input)), {accurate:'A correct idea.', gap:'A missing detail.', next_step:'Add a reason.'});
    assert.equal(splitFeedback('accurate：Good. GAP / MISCONCEPTION：Missing. NEXT STEP：Try again.').next_step, 'Try again.');
});

test('keeps ambiguous or unstructured historical feedback intact instead of inventing sections', () => {
    for (const input of ['An older assessment without headings.', 'Accurate: One idea. Next step: Add detail.', 'Gap/misconception: Gap. Accurate: Idea. Next step: Try.', 'Accurate: First. Gap/misconception: Gap. Accurate: Again. Next step: Try.', 'Accurate: Idea. Gap/misconception: Next step: Try.']) {
        assert.equal(splitFeedback(input), null);
        const output = renderAssessment(input, 'Mostly clear');
        assert.equal((output.match(/<article /g) || []).length, 3);
        assert.ok(output.includes(input));
        assert.ok(output.includes('Original assessment'));
        assert.ok(output.includes('没有单独保存'));
    }
});

test('does not treat decimal values as a numbered action plan', () => {
    const output = renderAssessment('Accurate: An idea. Gap/misconception: A gap. Next step: Compare 1.5 with 2.5 before explaining.', 'Keep exploring');
    assert.ok(!output.includes('<ol'));
    assert.ok(output.includes('1.5 with 2.5'));
});

test('escapes student and model markup, supports simple emphasis without executable HTML', () => {
    const output = renderAssessment('Accurate: <img src=x onerror=alert(1)> **an idea**. Gap/misconception: <script>alert(2)</script> a \\*real condition\\*. Next step: Explain it.', '<svg onload=alert(3)>');
    assert.ok(!output.includes('<img'));
    assert.ok(!output.includes('<script'));
    assert.ok(!output.includes('<svg'));
    assert.ok(output.includes('&lt;script&gt;'));
    assert.ok(output.includes('<strong>an idea</strong>'));
    assert.ok(output.includes('<strong>real condition</strong>'));
});

test('never changes the input and handles missing historical feedback', () => {
    const before = feedback;
    renderAssessment(feedback, 'Clear & thoughtful');
    assert.equal(feedback, before);
    assert.ok(renderAssessment(null, 'Completed').includes('未保存逐题点评'));
    assert.equal(splitFeedback(null), null);
});
