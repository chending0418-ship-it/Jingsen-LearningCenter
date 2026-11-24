"use strict";

// Keep the saved Markdown as the source of truth. Only the assistant's display is formatted.
const answerMarkdown = (() => {
    if (!window.markdownit) return null;
    const md = window.markdownit({html:false, breaks:true, linkify:false});
    const escape = md.utils.escapeHtml;

    // Recognize TeX before Markdown treats backslashes as escapes. Fenced and inline
    // code are already consumed by their own rules, so examples stay literal.
    const delimiters = [
        {open:"\\[", close:"\\]", display:true},
        {open:"\\(", close:"\\)", display:false},
        {open:"$$", close:"$$", display:true},
        {open:"$", close:"$", display:false},
    ];
    md.inline.ruler.before("escape","learning_math",(state,silent) => {
        const {src, pos, posMax} = state;
        const pair = delimiters.find(item => src.startsWith(item.open,pos));
        if (!pair) return false;
        const from = pos + pair.open.length;
        if (pair.open === "$" && /\s/.test(src[from] || " ")) return false;
        let end = src.indexOf(pair.close,from);
        while (end >= from && end + pair.close.length <= posMax) {
            let slash = end;
            while (slash > from && src[slash-1] === "\\") slash--;
            const escaped = (end - slash) % 2 !== 0;
            if (!escaped) {
                if (end === from) return false;
                if (pair.open === "$" && (/\s/.test(src[end-1]) || /\d/.test(src[end+1] || "")
                        || src.slice(from,end).includes("`"))) return false;
                if (!silent) {
                    const token = state.push("learning_math","",0);
                    token.content = src.slice(from,end);
                    token.markup = pair.open;
                }
                state.pos = end + pair.close.length;
                return true;
            }
            end = src.indexOf(pair.close,end + pair.close.length);
        }
        return false;
    });

    // A standalone display can span paragraphs and interrupt the preceding paragraph.
    md.block.ruler.before("fence","learning_display",(state,start,end,silent) => {
        if (state.sCount[start] - state.blkIndent >= 4) return false;
        const lineAt = n => state.src.slice(state.bMarks[n] + state.tShift[n],state.eMarks[n]).trimEnd();
        const first = lineAt(start);
        const pair = delimiters.find(item => item.display && first.startsWith(item.open));
        if (!pair) return false;
        const lines = [];
        for (let n = start; n < end; n++) {
            if (n > start && !state.isEmpty(n) && state.sCount[n] < state.blkIndent) return false;
            const line = n === start ? first.slice(pair.open.length) : lineAt(n);
            const closing = line.indexOf(pair.close);
            if (closing >= 0) {
                if (closing + pair.close.length !== line.length) return false;
                if (!silent) {
                    lines.push(line.slice(0,closing));
                    const token = state.push("learning_math","",0);
                    token.content = lines.join("\n").trim();
                    token.block = true; token.markup = pair.open; token.map = [start,n+1];
                    state.line = n+1;
                }
                return true;
            }
            lines.push(line);
        }
        return false;
    },{alt:["paragraph","reference","blockquote","list"]});

    md.renderer.rules.learning_math = (tokens,index) => {
        const token = tokens[index];
        const pair = delimiters.find(item => item.open === token.markup);
        try {
            const math = window.katex.renderToString(token.content,{
                displayMode:pair.display, output:"mathml", trust:false, strict:"ignore",
                throwOnError:true, maxSize:12, maxExpand:500,
            });
            return pair.display ? '<span class="display-math">' + math + '</span>' : math;
        } catch {
            return escape(pair.open + token.content + pair.close);
        }
    };
    md.renderer.rules.table_open = () => '<div class="table-scroll"><table>';
    md.renderer.rules.table_close = () => '</table></div>\n';
    // External image links in a saved answer must not request a resource when it is opened.
    md.renderer.rules.image = (tokens,index,options,env,renderer) =>
        escape(renderer.renderInlineAsText(tokens[index].children || [],options,env));
    return md;
})();

function formatAnswer(container, source) {
    if (answerMarkdown) {
        try {
            container.innerHTML = answerMarkdown.render(source);
            container.classList.remove("plain-reply");
            return;
        } catch { /* Keep the original answer readable if a renderer fails. */ }
    }
    container.classList.add("plain-reply");
    container.textContent = source;
}
