const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const dir = path.resolve(__dirname,"../static/learning_chat");
const window = {
    markdownit:require(path.join(dir,"vendor/markdown-it-15.0.3.min.js")),
    katex:require(path.join(dir,"vendor/katex-0.19.1.min.js")),
};
const script = fs.readFileSync(path.join(dir,"answer-format.js"),"utf8");
const renderer = vm.createContext({window});
vm.runInContext(script,renderer);

function render(source) {
    const result = {classList:{remove() {}, add() {}}};
    renderer.formatAnswer(result,source);
    return result.innerHTML;
}

test("renders a Markdown lesson with inline and multiline fractions", () => {
    const lesson = "# Fractions\n\n1. Divide\n2. Multiply\n\n" +
        "\\[\n\\frac{3}{4}=\\frac{6}{8}\n\\]\n" +
        "| Fraction | Numerator |\n|---|---|\n| $\\frac{3}{4}$ | 3 |";
    const html = render(lesson);
    assert.match(html,/<h1>Fractions<\/h1>/);
    assert.match(html,/<ol>\s*<li>Divide<\/li>\s*<li>Multiply<\/li>/);
    assert.equal((html.match(/<mfrac>/g) || []).length,3);
    assert.match(html,/<th>Fraction<\/th>/);
    assert.match(html,/<td><span class="katex">/);
    assert.match(html,/<math [^>]*display="block"/);
});

test("completed math survives a partial stream and the last fraction appears when closed", () => {
    const prefix = "Already formatted $x^2$.\n\n$$\n\\frac{1}{3}";
    const partial = render(prefix);
    assert.match(partial,/<msup>/);
    assert.doesNotMatch(partial,/<mfrac>/);
    assert.match(render(prefix+"\n$$"),/<mfrac>/);
    assert.match(render("Before \\(x^2\\) after"),/<msup>/);
    assert.match(render("$$x^2$$ and then prose"),/and then prose/);
});

test("keeps code examples, text prices, unsupported math and raw HTML readable", () => {
    const ticks = String.fromCharCode(96);
    const source = [
        "Prices: $5 and $10. "+ticks+"$x$"+ticks,
        ticks.repeat(3)+"js\nconst price = '$x$';\n"+ticks.repeat(3),
        "<aside>example</aside>", "$\\NotARealMathCommand{x}$",
        "![diagram](https://example.invalid/diagram.png)",
    ].join("\n\n");
    const html = render(source);
    assert.match(html,/Prices: \$5 and \$10/);
    assert.match(html,/<code>\$x\$<\/code>/);
    assert.match(html,/<pre><code class="language-js">const price = '\$x\$';/);
    assert.match(html,/&lt;aside&gt;example&lt;\/aside&gt;/);
    assert.match(html,/\\NotARealMathCommand/);
    assert.doesNotMatch(html,/<math |<img /);
});

test("falls back to the original multiline reply when the Markdown bundle is unavailable", () => {
    const context = vm.createContext({window:{}});
    vm.runInContext(script,context);
    const result = {classList:{add(name) {assert.equal(name,"plain-reply");}}};
    const raw = "# Title\n\nOriginal content";
    context.formatAnswer(result,raw);
    assert.equal(result.textContent,raw);
});
