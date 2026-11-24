// ---------- code editor: highlighting, line numbers, autocomplete, signature help, live check ----------
// A plain <textarea id="code"> holds the text (the drone bridge and the tests read code.value);
// a <pre> under it shows the same text coloured. Both scroll together.
const code = $('code');
const LINE_H = 20, PAD = 10;
const API = new Map(APIDOCS.commands.map(c => [c.name, c]));
const KW = new Set(['False', 'None', 'True', 'and', 'as', 'assert', 'break', 'class', 'continue', 'def', 'del', 'elif', 'else', 'except',
  'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try',
  'while', 'with', 'yield']);
const BUILTIN = new Set(['print', 'range', 'len', 'abs', 'min', 'max', 'round', 'int', 'float', 'str', 'list', 'dict', 'tuple', 'set',
  'enumerate', 'zip', 'sorted', 'sum', 'exit', 'Exception', 'isinstance', 'bool', 'any', 'all', 'reversed', 'map', 'filter']);
const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');   // " too: used in title="" (review 24.11, m2)
// One pass over the whole text: triple-quoted strings may span lines.
const TOKEN = /("""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)|"(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?)|(#[^\n]*)|\b(\d+\.?\d*(?:e[+-]?\d+)?|\.\d+)\b|\b(drone)\s*\.\s*([A-Za-z_]\w*)|\b([A-Za-z_]\w*)\b(?=\s*\()|\b([A-Za-z_]\w*)\b/g;
function highlight(text) {
  let out = '', last = 0, m;
  TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(text))) {
    if (m.index === last && m[0] === '') { TOKEN.lastIndex++; continue; }
    out += esc(text.slice(last, m.index));
    if (m[1] !== undefined) out += '<span class="t-str">' + esc(m[1]) + '</span>';
    else if (m[2] !== undefined) out += '<span class="t-com">' + esc(m[2]) + '</span>';
    else if (m[3] !== undefined) out += '<span class="t-num">' + esc(m[3]) + '</span>';
    else if (m[4] !== undefined) {
      const ok = API.has(m[5]);
      out += '<span class="t-kw">drone</span>' + esc(m[0].slice(5, m[0].length - m[5].length)) + '<span class="' + (ok ? 't-api' : 't-api t-bad') + '"' + (ok ? '' : ' title="not a drone command"') + '>' + esc(m[5]) + '</span>';
    } else if (m[6] !== undefined) out += '<span class="' + (KW.has(m[6]) ? 't-kw' : (BUILTIN.has(m[6]) ? 't-bi' : 't-fn')) + '">' + esc(m[6]) + '</span>';
    else { const w = m[7]; out += KW.has(w) ? '<span class="t-kw">' + esc(w) + '</span>' : (BUILTIN.has(w) ? '<span class="t-bi">' + esc(w) + '</span>' : esc(w)); }
    last = TOKEN.lastIndex;
  }
  return out + esc(text.slice(last));
}
function caretLine() { return code.value.slice(0, code.selectionStart).split('\n').length; }
function renderEditor() {
  const text = code.value, lines = text.split('\n');
  const marks = {};
  const lint = state.lint;
  if (lint) {
    for (const w of lint.warnings) if (w.line) marks[w.line] = 'warn';
    for (const e of lint.errors) if (e.line) marks[e.line] = 'err';
  }
  const cur = caretLine();
  // split the highlighted HTML back into lines: spans never cross a newline except strings/comments,
  // so close and reopen open spans at every newline
  const html = highlight(text);
  const parts = []; let open = [], buf = '';
  for (let i = 0; i < html.length; i++) {
    const ch = html[i];
    if (ch === '<') {
      const j = html.indexOf('>', i); const tag = html.slice(i, j + 1);
      if (tag.startsWith('</')) open.pop(); else open.push(tag);
      buf += tag; i = j; continue;
    }
    if (ch === '\n') { parts.push(buf + '</span>'.repeat(open.length)); buf = open.join(''); continue; }
    buf += ch;
  }
  parts.push(buf + '</span>'.repeat(open.length));
  $('hl').innerHTML = parts.map((p, i) => '<span class="L' + (marks[i + 1] ? ' ' + marks[i + 1] : '') + (i + 1 === cur ? ' cur' : '') + '">' + (p || ' ') + '</span>').join('\n') + '\n';
  let g = '';
  for (let i = 1; i <= lines.length; i++) g += '<div class="' + (marks[i] || '') + (i === cur ? ' cur' : '') + '"' + (marks[i] ? ' title="' + esc(lineProblem(i)) + '"' : '') + '>' + i + '</div>';
  $('gutter').innerHTML = g;
  syncScroll();
}
function lineProblem(n) {
  const l = state.lint; if (!l) return '';
  return l.errors.concat(l.warnings).filter(e => e.line === n).map(e => e.text).join('; ');
}
function syncScroll() { $('hl').scrollTop = code.scrollTop; $('hl').scrollLeft = code.scrollLeft; $('gutter').scrollTop = code.scrollTop; }
code.addEventListener('scroll', () => { syncScroll(); hideAC(); });
function gotoLine(n) {
  const lines = code.value.split('\n'); let p = 0; for (let i = 0; i < n - 1 && i < lines.length; i++) p += lines[i].length + 1;
  code.focus(); code.setSelectionRange(p, p + (lines[n - 1] || '').length); code.scrollTop = Math.max(0, (n - 5) * LINE_H);
  renderEditor();
}
// Every change goes through the browser's own editing command, so Ctrl+Z undoes it (review 24.11, M4);
// setRangeText is only the fallback where insertText is not supported.
function editText(text, s, e, select) {
  code.focus(); code.setSelectionRange(s, e);
  let ok = false;
  try { ok = text === '' ? (s === e || document.execCommand('delete', false)) : document.execCommand('insertText', false, text); } catch (err) { ok = false; }
  if (!ok || code.value.slice(s, s + text.length) !== text) code.setRangeText(text, s, e, select ? 'select' : 'end');
  else if (select) code.setSelectionRange(s, s + text.length);
  onEdit();
}
function insertAtCaret(text) { editText(text, code.selectionStart, code.selectionEnd, false); }

// ---------- autocomplete ----------
const ac = { open: false, items: [], idx: 0, start: 0 };
let charW = 0;
function measureChar() {
  const s = document.createElement('span'); s.className = 'mono'; s.style.cssText = 'position:absolute;visibility:hidden;font-size:13px;white-space:pre';
  s.textContent = 'x'.repeat(100); $('editor').appendChild(s); charW = s.getBoundingClientRect().width / 100; s.remove();
}
function wordBefore() {
  const pos = code.selectionStart, before = code.value.slice(0, pos);
  const m = before.match(/(drone\s*\.\s*)?([A-Za-z_][\w.]*)?$/);
  return { drone: !!(m && m[1]), word: (m && m[2]) || '', start: pos - ((m && m[2]) || '').length };
}
function inStringOrComment() {
  const line = code.value.slice(0, code.selectionStart).split('\n').pop();
  let q = null;
  for (const ch of line) { if (q) { if (ch === q) q = null; } else if (ch === '"' || ch === "'") q = ch; else if (ch === '#') return true; }
  return !!q;
}
function showAC(force) {
  if (inStringOrComment()) { hideAC(); return; }
  const w = wordBefore();
  let items;
  if (w.drone) items = APIDOCS.commands.filter(c => c.name.startsWith(w.word)).map(c => ({ label: c.name, detail: c.sig, insert: c.snippet, help: c.help }));
  else {
    if (!force && w.word.length < 2) { hideAC(); return; }
    // review 24.11, M2: nothing pops up after import/from by itself, and "time.sleep" is offered
    // only once a dot is typed ("import time" + Enter must stay "import time")
    const lineBefore = code.value.slice(0, w.start).split('\n').pop();
    if (!force && /^\s*(import|from)\b/.test(lineBefore)) { hideAC(); return; }
    const dotted = w.word.includes('.');
    const words = ['drone'].concat(APIDOCS.words).filter(x => x.includes('.') === dotted);
    items = words.filter(x => x.startsWith(w.word) && x !== w.word).map(x => ({ label: x, detail: x === 'drone' ? 'the drone module' : '', insert: x }));
  }
  if (!items.length || (items.length === 1 && items[0].label === w.word && !w.drone)) { hideAC(); return; }
  ac.open = true; ac.items = items.slice(0, 40); ac.idx = 0; ac.start = w.start; ac.forced = !!force; ac.drone = w.drone; ac.nav = false;
  const box = $('ac'); box.innerHTML = '';
  ac.items.forEach((it, i) => {
    const d = document.createElement('div'); if (i === 0) d.className = 'on';
    const b = document.createElement('span'); b.className = 'mono'; b.textContent = it.label;
    const s = document.createElement('small'); s.textContent = it.detail || '';
    d.append(b, s); d.title = it.help || '';
    d.onmousedown = (e) => { e.preventDefault(); ac.idx = i; acceptAC(); };
    box.appendChild(d);
  });
  const before = code.value.slice(0, code.selectionStart).split('\n');
  const line = before.length - 1, col = before[before.length - 1].replace(/\t/g, '    ').length;
  if (!charW) measureChar();
  const ed = $('editor'), gw = $('gutter').offsetWidth;
  let x = gw + PAD + 2 + col * charW - code.scrollLeft, y = PAD + (line + 1) * LINE_H - code.scrollTop + 2;
  box.hidden = false;
  if (y + box.offsetHeight > ed.clientHeight) y = Math.max(0, y - LINE_H - box.offsetHeight - 4);
  box.style.left = Math.min(x, ed.clientWidth - box.offsetWidth - 6) + 'px'; box.style.top = y + 'px';
}
function hideAC() { ac.open = false; $('ac').hidden = true; }
function moveAC(d) {
  if (!ac.open) return;
  const ch = $('ac').children; ch[ac.idx].className = '';
  ac.idx = (ac.idx + d + ac.items.length) % ac.items.length; ch[ac.idx].className = 'on'; ch[ac.idx].scrollIntoView({ block: 'nearest' });
}
function acceptAC() {
  const it = ac.items[ac.idx]; if (!it) return;
  let text = it.insert, end = code.selectionStart;
  // do not double the brackets when the call is already written: drone.fly_|(1, 2)
  if (code.value[end] === '(' && text.includes('(')) text = text.slice(0, text.indexOf('('));
  const start = ac.start;
  hideAC();
  editText(text, start, end, false);
  // select the first argument so typing replaces it
  const open = text.indexOf('('), close = text.lastIndexOf(')');
  if (open >= 0 && close > open + 1) { const a = start + open + 1, args = text.slice(open + 1, close), comma = args.indexOf(','); code.setSelectionRange(a, a + (comma >= 0 ? comma : args.length)); updateSig(); }
}

// ---------- signature help under the editor ----------
function updateSig() {
  const before = code.value.slice(0, code.selectionStart);
  let depth = 0, i = before.length - 1;
  for (; i >= 0; i--) { const ch = before[i]; if (ch === '\n' && depth === 0) break; if (ch === ')') depth++; else if (ch === '(') { if (depth === 0) break; depth--; } }
  let c = null;
  if (i >= 0 && before[i] === '(') { const m = before.slice(0, i).match(/drone\s*\.\s*(\w+)\s*$/); if (m) c = API.get(m[1]); }
  if (!c) { const m = before.match(/drone\s*\.\s*(\w+)$/); if (m) c = API.get(m[1]); }
  const bar = $('sigbar'); bar.textContent = '';
  if (c) { const b = document.createElement('b'); b.className = 'mono'; b.textContent = 'drone.' + c.sig; bar.append(b, document.createTextNode('  ' + c.help)); }
  else { const p = lineProblem(caretLine()); bar.textContent = p ? 'Line ' + caretLine() + ': ' + p : 'Type drone. to see the commands, or press Ctrl+Space.'; }
}

// ---------- typing ----------
let saveTimer = null, lintTimer = null;
function onEdit() {
  renderEditor(); updateSig();
  clearTimeout(saveTimer); saveTimer = setTimeout(() => store.set('program', code.value), 500);
  clearTimeout(syncTimer); syncTimer = setTimeout(syncTakeoff, 600);
  lintSoon(700);
  if (state.sim) { state.sim.stale = true; showStale(); }
  autoSimSoon();
}
code.addEventListener('input', (e) => {
  onEdit();
  if (e.inputType && e.inputType.startsWith('insert') && /[\w.]$/.test(code.value.slice(0, code.selectionStart))) showAC(false);
  else hideAC();
});
code.addEventListener('click', () => { hideAC(); renderEditor(); updateSig(); });
code.addEventListener('keyup', (e) => { if (/^Arrow|Home|End|Page/.test(e.key)) { renderEditor(); updateSig(); } });
code.addEventListener('blur', () => setTimeout(hideAC, 150));
code.addEventListener('keydown', (e) => {
  const mod = e.ctrlKey || e.metaKey;
  if (ac.open) {
    if (e.key === 'ArrowDown') { e.preventDefault(); ac.nav = true; moveAC(1); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); ac.nav = true; moveAC(-1); return; }
    // Tab always takes the suggestion; Enter only for drone commands, after the arrows or Ctrl+Space,
    // otherwise Enter is a new line (review 24.11, M2)
    if (e.key === 'Tab' || (e.key === 'Enter' && (ac.nav || ac.forced || ac.drone))) { e.preventDefault(); acceptAC(); return; }
    if (e.key === 'Escape') { e.preventDefault(); hideAC(); return; }
    if (e.key === 'Enter') hideAC();
  }
  // keyboard way out of the editor (review 24.11, m8): Esc, then Tab moves the focus on
  if (e.key === 'Escape') { state.escTab = true; return; }
  if (e.key === 'Tab' && state.escTab) { state.escTab = false; return; }
  if (e.key !== 'Shift') state.escTab = false;
  if (mod && (e.key === ' ' || e.code === 'Space')) { e.preventDefault(); showAC(true); return; }
  if (mod && e.key === 'Enter') { e.preventDefault(); $('btnsim').click(); return; }
  if (mod && e.key === '/') { e.preventDefault(); toggleComment(); return; }
  if (e.key === 'Tab') { e.preventDefault(); indent(e.shiftKey); return; }
  if (e.key === 'Enter') {
    e.preventDefault();
    const before = code.value.slice(0, code.selectionStart), line = before.split('\n').pop();
    let ind = (line.match(/^\s*/) || [''])[0];
    if (/:\s*(#.*)?$/.test(line)) ind += '    ';
    if (/^\s*(return|pass|break|continue|raise)\b/.test(line) && ind.length >= 4) ind = ind.slice(4);
    insertAtCaret('\n' + ind); return;
  }
  if (e.key === 'Backspace' && code.selectionStart === code.selectionEnd) {
    const before = code.value.slice(0, code.selectionStart), line = before.split('\n').pop();
    if (line.length && /^ +$/.test(line) && line.length % 4 === 0) { e.preventDefault(); editText('', code.selectionStart - 4, code.selectionStart, false); }
  }
});
function selLines() {
  const v = code.value, s = v.lastIndexOf('\n', code.selectionStart - 1) + 1;
  let e2 = v.indexOf('\n', Math.max(code.selectionEnd - (code.selectionEnd > code.selectionStart && v[code.selectionEnd - 1] === '\n' ? 1 : 0), code.selectionStart));
  if (e2 < 0) e2 = v.length;
  return [s, e2];
}
function indent(back) {
  const [s, e2] = selLines();
  if (!back && code.selectionStart === code.selectionEnd) { insertAtCaret('    '); return; }
  const block = code.value.slice(s, e2).split('\n').map(l => back ? l.replace(/^ {1,4}/, '') : '    ' + l).join('\n');
  if (block !== code.value.slice(s, e2)) editText(block, s, e2, true);
}
function toggleComment() {
  const [s, e2] = selLines();
  const lines = code.value.slice(s, e2).split('\n');
  const all = lines.filter(l => l.trim()).every(l => /^\s*#/.test(l));
  const block = lines.map(l => !l.trim() ? l : (all ? l.replace(/^(\s*)# ?/, '$1') : l.replace(/^(\s*)/, '$1# '))).join('\n');
  if (block !== code.value.slice(s, e2)) editText(block, s, e2, true);
}

// ---------- live code check (layer 1, the same check as on the drone) ----------
let lintSeq = 0;
function lintSoon(ms) { clearTimeout(lintTimer); lintTimer = setTimeout(lint, ms); }
async function lint() {
  if (!state.ready || state.busy) return;
  const my = ++lintSeq, text = code.value;
  let r; try { r = await api('check_code_hints', [text], 15000); } catch (e) { return; }
  if (my !== lintSeq || text !== code.value) return;
  state.lint = r; renderEditor(); updateSig();
  const ul = $('codemsgs'); ul.innerHTML = '';
  for (const e of r.errors) addMsg(ul, 'error', e.text, e.line, e.fix);
  for (const w of r.warnings) addMsg(ul, 'warn', w.text, w.line, w.fix);
}

// ---------- the command list ----------
function renderApiList() {
  const box = $('apilist'); box.innerHTML = '';
  for (const [g, title] of APIDOCS.groups) {
    const h = document.createElement('h3'); h.textContent = title; box.appendChild(h);
    const ul = document.createElement('ul'); ul.className = 'msgs';
    for (const c of APIDOCS.commands.filter(x => x.group === g)) {
      const li = document.createElement('li'); li.className = 'click';
      const b = document.createElement('span'); b.className = 'mono'; b.style.color = 'var(--tok-api)'; b.textContent = 'drone.' + c.sig;
      const s = document.createElement('span'); s.className = 'note'; s.style.display = 'block'; s.style.margin = '0'; s.textContent = c.help;
      li.append(b, s); li.onclick = () => { showTab('program'); insertAtCaret('drone.' + c.snippet); };
      ul.appendChild(li);
    }
    box.appendChild(ul);
  }
}
for (const name of Object.keys(EXAMPLES)) { const o = document.createElement('option'); o.value = name; o.textContent = name.replace(/_student\.py$/, '').replace(/_/g, ' '); $('examples').appendChild(o); }
// Picking an example replaces the program through the editing command (Ctrl+Z brings the old one
// back) and keeps a copy with a button to restore it (review 24.11, M3).
$('examples').onchange = () => {
  const old = code.value, ex = EXAMPLES[$('examples').value];
  const isExample = Object.values(EXAMPLES).some(t => t === old);
  editText(ex, 0, old.length, false); code.setSelectionRange(0, 0); code.scrollTop = 0;
  store.set('program', code.value); syncTakeoff();
  if (old.trim() && !isExample) {
    store.set('program.backup', old);
    const ul = $('restoremsg'); ul.innerHTML = ''; const li = document.createElement('li'); li.className = 'info';
    li.textContent = 'Your previous program was replaced by the example. ';
    const b = document.createElement('button'); b.className = 'ghost'; b.textContent = 'Bring my program back';
    b.onclick = () => { editText(old, 0, code.value.length, false); li.remove(); };
    li.appendChild(b); ul.prepend(li);
  }
};
