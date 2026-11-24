// ---------- Flight Studio (GCS 1.4, 24.11.2026): core -- data, Python worker, tabs, theme ----------
const $ = (id) => document.getElementById(id);
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const CONFIG = JSON.parse($('bbconfig').textContent);      // {embedded, pyodide}: set by build_html.py
// The program and the map survive a restart (per browser / per app profile). May be unavailable: then nothing is kept.
const store = {
  get(k) { try { return localStorage.getItem('bbflight.' + k); } catch (e) { return null; } },
  set(k, v) { try { localStorage.setItem('bbflight.' + k, v); } catch (e) { /* private window, blocked storage */ } },
};
const state = { map: null, sel: null, sel2: null, check: null, grid: null, gridNote: '', sim: null, t: 0, playing: false, ready: false,
                view: null, drag: null, fileErrors: [], undo: [], tab: 'program', lint: null };
const PYFILES = JSON.parse($('pyfiles').textContent);
const EXAMPLES = JSON.parse($('examplesdata').textContent);
const APIDOCS = JSON.parse($('apidocs').textContent);       // {commands: [...], groups: [...], words: [...]}: bbflight/apidoc.py
state.map = JSON.parse($('defaultmap').textContent);
try {
  const saved = JSON.parse(store.get('map') || 'null');
  if (saved && Array.isArray(saved.markers) && saved.markers.length && saved.markers.length <= 200) {
    state.map = { name: String(saved.name || 'field'), z: Number.isFinite(+saved.z) ? +saved.z : -0.32,
                  markers: saved.markers.map(k => ({ id: +k.id, length: +k.length, x: +k.x, y: +k.y, rot_z: +(k.rot_z || 0) })) };
  }
} catch (e) { /* a broken saved map: keep the default */ }
const fmt = (v, d) => (Number.isFinite(v) ? v.toFixed(d) : '—');

// ---------- Python in a Web Worker ----------
// The student’s program runs there: no DOM, no GCS bridge, and a stuck program is
// killed with terminate() by a wall-clock timer or the Stop button (review 17.11, items 1, 3, 15).
const PYODIDE = CONFIG.pyodide ? new URL(CONFIG.pyodide, location.href).href : 'https://cdn.jsdelivr.net/npm/pyodide@0.26.4/';
const WORKER_SRC = `
let api = null;
self.onmessage = async (e) => {
  const { id, fn, args, files } = e.data;
  try {
    if (fn === '__init') {
      importScripts('${PYODIDE}pyodide.js');
      const py = await loadPyodide({ indexURL: '${PYODIDE}' });
      py.FS.mkdirTree('/bb/bbflight');
      for (const [p, t] of Object.entries(files)) if (!p.startsWith('_')) py.FS.writeFile('/bb/' + p, t);
      py.runPython("import sys; sys.path.insert(0, '/bb')");
      api = py.pyimport('bbflight.webapi');
      // defence in depth: a program that escapes the checks cannot simply "import js"
      py.runPython("import sys; sys.modules['js'] = None; sys.modules['pyodide_js'] = None");
      self.postMessage({ id, ok: true, result: api.cameras() });
    } else {
      self.postMessage({ id, ok: true, result: api[fn](...args) });
    }
  } catch (err) { self.postMessage({ id, ok: false, error: String(err) }); }
};`;
let worker = null, seq = 0;
const pending = new Map();
function setStatus(text, bad) { const p = $('pystatus'); p.textContent = text; p.classList.toggle('bad', !!bad); }
function makeWorker() {
  worker = new Worker(URL.createObjectURL(new Blob([WORKER_SRC], { type: 'text/javascript' })));
  worker.onmessage = (e) => {
    const p = pending.get(e.data && e.data.id); if (!p) return;
    pending.delete(e.data.id); clearTimeout(p.timer);
    if (e.data.ok) p.resolve(e.data.result); else p.reject(new Error(e.data.error));
  };
  worker.onerror = (e) => setStatus('Python thread error: ' + (e.message || e), true);
}
function call(fn, args, timeoutMs) {
  return new Promise((resolve, reject) => {
    const id = ++seq;
    const timer = timeoutMs ? setTimeout(() => { if (pending.has(id)) { pending.delete(id); restartPython('time is up'); reject(new Error('time is up (' + timeoutMs / 1000 + ' s): Python restarted')); } }, timeoutMs) : null;
    pending.set(id, { resolve, reject, timer });
    worker.postMessage(fn === '__init' ? { id, fn, files: PYFILES } : { id, fn, args });
  });
}
async function api(fn, args, timeoutMs) { if (!state.ready) throw new Error('Python is not ready yet'); return JSON.parse(await call(fn, args, timeoutMs)); }
async function startPython() {
  setStatus('Loading Python…');
  makeWorker();
  try {
    const cams = JSON.parse(await call('__init', null, 0));
    state.ready = true; setStatus('Python ready');
    if (!$('cam').options.length) for (const [k, v] of Object.entries(cams)) { const o = document.createElement('option'); o.value = k; o.textContent = v.label; $('cam').appendChild(o); }
    updateCamNote(); recheckMap(); lintSoon(50); autoSimSoon(400);
  } catch (e) { setStatus('Python did not load: ' + e.message, true); }
}
function restartPython(why) {
  state.ready = false; state.busy = false;
  for (const [, p] of pending) { clearTimeout(p.timer); p.reject(new Error(why)); }
  pending.clear();
  if (worker) worker.terminate();
  $('btnstop').hidden = true; $('btnsim').disabled = false;
  setStatus('Python is restarting (' + why + ')…');
  startPython();
}

// ---------- messages ----------
function addMsg(ul, level, text, line, fix) {
  const li = document.createElement('li'); li.className = level; li.textContent = (line ? 'line ' + line + ': ' : '') + text;
  if (fix) { const f = document.createElement('span'); f.className = 'fix'; f.textContent = fix; li.appendChild(f); }
  if (line) { li.classList.add('click'); li.onclick = () => { showTab('program'); gotoLine(line); }; }
  ul.appendChild(li);
}

// ---------- tabs and theme ----------
function showTab(name) {
  state.tab = name;
  for (const b of document.querySelectorAll('#tabs button')) { b.setAttribute('aria-pressed', String(b.dataset.tab === name)); b.setAttribute('aria-selected', String(b.dataset.tab === name)); }
  for (const p of document.querySelectorAll('.tabpane')) p.hidden = p.id !== 'tab-' + name;
  store.set('tab', name);
  if (name === 'map') { state.view = null; draw(); }
  if (name === 'program') renderEditor();
}
for (const b of document.querySelectorAll('#tabs button')) b.onclick = () => showTab(b.dataset.tab);
const THEMES = ['auto', 'light', 'dark'];
function applyTheme(t) {
  if (t === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', t);
  $('themebtn').textContent = t === 'auto' ? '◐' : (t === 'light' ? '☀' : '☾');      // review 24.11, d5: an icon, not a blue word
  $('themebtn').title = 'Appearance: ' + (t === 'auto' ? 'as the system' : t) + '. Click to change.';
  store.set('theme', t);
  blindPat = null;
  requestAnimationFrame(() => { draw(); drawChart(); render3d(); renderEditor(); });
}
const DEFAULT_THEME = 'dark';   // owner 24.11 ~19:35: «тема темная» -- dark unless the user picks light or auto
$('themebtn').onclick = () => { const cur = store.get('theme') || DEFAULT_THEME; applyTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]); };
if (window.matchMedia) {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  const redraw = () => { blindPat = null; draw(); drawChart(); render3d(); };
  if (mq.addEventListener) mq.addEventListener('change', redraw);
}
