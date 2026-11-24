// ---------- map: state, check, coloured map, 2D editor, exact distances, grid template ----------
function mapJSON() { return JSON.stringify({ format: 'bumblebee-map/1', name: state.map.name, z: state.map.z, markers: state.map.markers }); }
let recheckTimer = null;
function mapChanged() {
  renderTable(); draw(); updateFieldNote(); updateMeasure(); store.set('map', mapJSON());
  state.sim = null; showSimGone();                     // a flight on the old map is not shown on the new one
  clearTimeout(recheckTimer); recheckTimer = setTimeout(recheckMap, 350);
  render3d(); autoSimSoon();
}
function snapshot() {                                  // before every change: Undo (Ctrl+Z) goes back one step
  state.undo.push(mapJSON()); if (state.undo.length > 50) state.undo.shift();
  $('undom').disabled = false;
}
function undoMap() {
  const s = state.undo.pop(); $('undom').disabled = !state.undo.length;
  if (!s) return;
  const m = JSON.parse(s);
  state.map = { name: m.name, z: m.z, markers: m.markers };
  $('mapname').value = state.map.name; state.sel = state.sel2 = null; state.view = null; mapChanged();
}
let checkSeq = 0;
async function recheckMap() {
  if (!state.ready) return;
  const my = ++checkSeq;
  let r;
  try { r = await api('map_check', [mapJSON()], 15000); } catch (e) { showMapMsgs({ error: e.message }); return; }
  if (my !== checkSeq) return;                       // a newer check is on its way
  state.check = r; showMapMsgs(r);
  if (!r.error && !r.errors.length && $('heat').checked) computeGrid(); else { state.grid = null; draw(); }
}
function showMapMsgs(r) {
  const ul = $('mapmsgs'); ul.innerHTML = '';
  for (const e of state.fileErrors) addMsg(ul, 'error', 'in the loaded file: ' + e);
  if (state.fileErrors.length) {
    // the file’s broken lines are NOT in the map on screen; saving is blocked until the person confirms
    const li = document.createElement('li'); li.className = 'warn';
    const b = document.createElement('button'); b.textContent = 'Understood: these lines are not in the map; go on';
    b.onclick = () => { state.fileErrors = []; recheckMap(); };
    li.appendChild(b); ul.appendChild(li);
  }
  if (r.error) { addMsg(ul, 'error', r.error); $('sha').textContent = ''; setExport(false); return; }
  for (const e of r.errors) addMsg(ul, 'error', e);
  for (const w of r.warnings) addMsg(ul, 'warn', w);
  if (!r.errors.length) addMsg(ul, 'info', 'Map has no errors: ' + r.summary);
  if (r.errors.length && $('heat').checked) addMsg(ul, 'warn', 'The coloured map is not computed while the map has errors.');
  if (state.gridNote) addMsg(ul, 'warn', state.gridNote);
  $('sha').textContent = 'sha256 ' + r.sha;
  setExport(!r.errors.length && !state.fileErrors.length);
}
function setExport(ok) { $('dltxt').disabled = $('dljson').disabled = !ok; }
let gridSeq = 0;
async function computeGrid() {
  if (!state.ready || !state.map.markers.length) { state.grid = null; draw(); return; }
  const my = ++gridSeq;
  setStatus('counting markers in view…');
  try {
    const g = await api('heat', [mapJSON(), takeoffH(), $('cam').value || 'gazebo', 0.1, parseFloat($('turn').value)], 30000);
    if (my !== gridSeq) return;
    state.grid = g.error ? null : g; state.gridNote = g.error || '';
    if (g.error && state.check) showMapMsgs(state.check);
  } catch (e) { state.grid = null; state.gridNote = e.message; }
  if (state.ready) setStatus('Python ready');
  state.hover = null; hoverSeq++; $('hint').hidden = true;     // a hint of the old map must not come back
  showHeights();
  draw(); render3d();
}

// ---------- the coloured map: height, heading, field, hint (18.11) ----------
function takeoffH() { return parseFloat($('zh').value); }
function showHeights() {
  const g = state.grid;
  if (!g || !g.heights) { $('heights').textContent = ''; return; }
  const pt = state.progTakeoff, lo = parseFloat($('zh').min), hi = parseFloat($('zh').max);
  const warn = pt && pt.h !== null && (pt.h < lo || pt.h > hi)
    ? ' WARNING: the program has takeoff(' + fmt(pt.h, 2) + '), outside the tested ' + fmt(lo, 1) + '–' + fmt(hi, 1) + ' m; the guard will refuse the takeoff.' : '';
  $('heights').textContent = 'Above the floor after takeoff(' + fmt(g.takeoff, 2) + '): drone centre ' + fmt(g.heights.base, 2)
    + ' m, camera ' + fmt(g.heights.camera, 2) + ' m (20EC reference: standing 0.217 and 0.183 m + the takeoff height). Heading ' + fmt(g.heading_deg, 0)
    + '° (0° = along the x axis, counter-clockwise; at the start ' + fmt(g.start_heading_deg, 0) + '°).' + warn;
  $('heights').classList.toggle('warnnote', !!warn);
}
// drone.takeoff(...) of the program, comments ignored: {h} a number (no argument: 1.0, the
// default of drone.takeoff), {h: null, why} when the height is not a plain number, null when there is no call
function programTakeoff() {
  for (const raw of code.value.split('\n')) {
    const line = raw.replace(/#.*/, '');
    const m = line.match(/\bdrone\.takeoff\(([^)]*)(\)?)/);
    if (!m) continue;
    if (!m[2]) return { h: null, why: 'takeoff over several lines' };
    const args = m[1].split(',').map(a => a.trim()).filter(a => a.length);
    const num = (s) => /^[0-9]*\.?[0-9]+$/.test(s) ? parseFloat(s) : null;
    if (!args.length) return { h: 1.0 };
    const kw = args.find(a => /^height\s*=/.test(a));
    const text = kw ? kw.replace(/^height\s*=\s*/, '') : (args[0].includes('=') ? '1.0' : args[0]);
    const h = num(text);
    return h === null ? { h: null, why: 'height "' + text + '" is not a number' } : { h };
  }
  return null;
}
state.followProgram = true;                  // the slider follows the program until the person moves it
state.progTakeoff = null;
let syncTimer = null;
function syncTakeoff() {
  const pt = programTakeoff(), b = $('zfromprog'), lo = parseFloat($('zh').min), hi = parseFloat($('zh').max);
  state.progTakeoff = pt;
  const h = pt ? pt.h : null;
  b.disabled = h === null || h < lo || h > hi;
  b.textContent = !pt ? 'no takeoff in the program' : (h === null ? 'takeoff: ' + pt.why : 'as in the program (' + fmt(h, 2) + ')');
  showHeights();
  // only when the program’s number changed, not on every edit: a recount is not free
  if (state.followProgram && h !== null && h >= lo && h <= hi && Math.abs(h - takeoffH()) > 0.005) {
    $('zh').value = h; $('zhv').textContent = takeoffH().toFixed(2); computeGrid();
  }
}
function updateFieldNote() {
  const ms = state.map.markers;
  let lo = Infinity, hi = 0;
  if (ms.length > 1) for (const a of ms) {
    let best = Infinity;
    for (const b of ms) if (b !== a) best = Math.min(best, Math.hypot(a.x - b.x, a.y - b.y));
    lo = Math.min(lo, best); hi = Math.max(hi, best);
  }
  $('fieldnote').textContent = 'The map must match the real field: on 16.11 the owner’s field had 63–100 cm between neighbouring markers, the map in the drone image 36–73 cm. '
    + (ms.length > 1 ? 'In this map the nearest neighbouring marker is ' + Math.round(lo * 100) + '–' + Math.round(hi * 100) + ' cm away. ' : '')
    + 'Before flying, check 2–3 distances with a tape measure.';
}
let blindPat = null, blindKey = '';
function blindPattern() {
  const key = css('--blind') + css('--hatch');
  if (blindPat && blindKey === key) return blindPat;
  const c = document.createElement('canvas'); c.width = c.height = 8; const x = c.getContext('2d');
  x.fillStyle = css('--blind'); x.fillRect(0, 0, 8, 8);
  x.strokeStyle = css('--hatch'); x.lineWidth = 1.6; x.beginPath(); x.moveTo(-2, 10); x.lineTo(10, -2); x.moveTo(-2, 2); x.lineTo(2, -2); x.moveTo(6, 10); x.lineTo(10, 6); x.stroke();
  blindPat = ctx.createPattern(c, 'repeat'); blindKey = key; return blindPat;
}
function shadeOf(n, g) { return n < g.blind_below ? 'blind' : (n < g.red_below ? 'red' : (n < g.green_from ? 'yellow' : 'green')); }
function drawHeading(g) {
  const W = cv.clientWidth, cx = W - 34, cy = 34, r = 22;
  ctx.save();
  ctx.fillStyle = css('--panel'); ctx.strokeStyle = css('--line'); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.arc(cx, cy, r + 6, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
  const dx = Math.cos(g.yaw), dy = -Math.sin(g.yaw);                    // screen y grows down
  ctx.strokeStyle = css('--path'); ctx.fillStyle = css('--path'); ctx.lineWidth = 3;
  ctx.beginPath(); ctx.moveTo(cx - dx * r * 0.7, cy - dy * r * 0.7); ctx.lineTo(cx + dx * r * 0.7, cy + dy * r * 0.7); ctx.stroke();
  const tx = cx + dx * r, ty = cy + dy * r, nx = -dy, ny = dx;
  ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - dx * 9 + nx * 6, ty - dy * 9 + ny * 6); ctx.lineTo(tx - dx * 9 - nx * 6, ty - dy * 9 - ny * 6); ctx.closePath(); ctx.fill();
  ctx.fillStyle = css('--ink'); ctx.font = '11px system-ui'; ctx.textAlign = 'center';
  ctx.fillText('nose, ' + fmt(g.heading_deg, 0) + '°', cx, cy + r + 18);
  ctx.restore();
}
function drawHover() {
  const p = state.hover; if (!p || !state.view) return;
  ctx.save();
  if (p.footprint && p.footprint.length) {
    const q = p.footprint.map(([x, y]) => toS(x, y));
    ctx.beginPath(); q.forEach((v, i) => i ? ctx.lineTo(v[0], v[1]) : ctx.moveTo(v[0], v[1])); ctx.closePath();
    ctx.setLineDash([4, 4]); ctx.strokeStyle = css('--ink'); ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
    ctx.clip();
  }
  if (p.cone) {
    const [cx, cy] = toS(p.cone[0], p.cone[1]);
    ctx.beginPath(); ctx.arc(cx, cy, p.cone[2] * state.view.s, 0, 2 * Math.PI);
    ctx.fillStyle = 'rgba(79, 140, 255, 0.12)'; ctx.fill(); ctx.strokeStyle = css('--path'); ctx.lineWidth = 1.5; ctx.stroke();
  }
  ctx.restore();
  const seen = new Set(p.ids || []);
  ctx.save(); ctx.strokeStyle = css('--seen'); ctx.lineWidth = 3;
  for (const m of state.map.markers) if (seen.has(m.id)) {
    const q = corners(m).map(c => toS(c[0], c[1]));
    ctx.beginPath(); q.forEach((v, i) => i ? ctx.lineTo(v[0], v[1]) : ctx.moveTo(v[0], v[1])); ctx.closePath(); ctx.stroke();
  }
  const [px, py] = toS(p.x, p.y);
  ctx.fillStyle = css('--path'); ctx.beginPath(); ctx.arc(px, py, 5, 0, 2 * Math.PI); ctx.fill();
  ctx.restore();
}
const SHADE_TEXT = { blind: 'blind spot', red: 'one marker: vision unreliable', yellow: 'about two markers', green: 'reliable' };
function showHint(p, px, py) {
  const h = $('hint');
  const ids = p.ids || [];
  h.textContent = '';
  const lines = [
    'point x ' + fmt(p.x, 2) + ', y ' + fmt(p.y, 2) + ' m',
    'mean ' + fmt(p.mean, 2) + ' markers in view (the point and 4 neighbours 12 cm away: the drone does not hold still): ' + (SHADE_TEXT[p.shade] || ''),
    ids.length ? 'visible from exactly this point: ' + ids.join(', ') + ' (' + ids.length + ')' : 'no marker is visible from exactly this point',
    'camera ' + fmt(p.camera, 2) + ' m above the floor; dashed: the frame, circle: where markers are still read',
  ];
  lines.forEach((t, i) => { if (i) h.appendChild(document.createElement('br')); h.appendChild(document.createTextNode(t)); });
  h.style.left = '0px'; h.style.top = '0px';           // measure at full width, not squeezed at the edge
  h.hidden = false;
  const wrap = $('mapwrap').getBoundingClientRect();
  const left = Math.min(px + 16, wrap.width - h.offsetWidth - 4), top = py + 16 + h.offsetHeight > wrap.height ? py - h.offsetHeight - 12 : py + 16;
  h.style.left = Math.max(4, left) + 'px'; h.style.top = Math.max(4, top) + 'px';
}
let hoverBusy = false, hoverNext = null, hoverSeq = 0;
function hoverAt(px, py) {
  if (!state.grid || !$('heat').checked || !state.ready || !state.view) return;
  hoverNext = [px, py];
  if (hoverBusy) return;
  const run = async () => {
    const [qx, qy] = hoverNext; hoverNext = null; hoverBusy = true;
    const my = ++hoverSeq; const [wx, wy] = toW(qx, qy);
    try {
      // no timeout: the Python thread may be busy with a simulation; the hint waits for it
      const p = await api('heat_point', [mapJSON(), wx, wy, takeoffH(), $('cam').value || 'gazebo', parseFloat($('turn').value)], 0);
      if (my === hoverSeq && !p.error && state.hoverOn) { state.hover = p; showHint(p, qx, qy); draw(); }
    } catch (e) { /* Python restarted: no hint */ }
    hoverBusy = false;
    if (hoverNext) run();
  };
  run();
}
function nextId() { const used = new Set(state.map.markers.map(m => m.id)); for (let i = 0; i < 100; i++) if (!used.has(i)) return i; return null; }
function addMarker(m) {
  if (m.id === null) { const ul = $('mapmsgs'); addMsg(ul, 'error', 'All IDs 0–99 are taken: no new marker can be added.'); return; }
  snapshot(); state.map.markers.push(m); setSel(m.id); mapChanged();
}
function selMarker() { return state.map.markers.find(m => m.id === state.sel) || null; }
function sel2Marker() { return state.sel2 === null ? null : (state.map.markers.find(m => m.id === state.sel2) || null); }
function setSel(id, second) {
  if (second) { if (id !== null && id !== state.sel) state.sel2 = id; }
  else { state.sel = id; state.sel2 = null; }
  $('delm').disabled = $('rotm').disabled = (state.sel === null);
  renderTable(); draw(); updateMeasure();
}

// ---------- units, table ----------
const unitK = () => ($('units').value === 'm' ? 1 : 100);          // metres -> shown unit
const unitName = () => $('units').value;
function renderTable() {
  const tb = $('tbody'); tb.innerHTML = '';
  const k = unitK(), dig = k === 1 ? 3 : 1, step = k === 1 ? 0.001 : 0.1;
  for (const th of document.querySelectorAll('#tablewrap th')) if (th.cellIndex >= 1 && th.cellIndex <= 3) th.textContent = ['', 'side', 'x', 'y'][th.cellIndex] + ', ' + unitName();
  for (const u of document.querySelectorAll('.unit')) u.textContent = unitName();
  const count = {}; for (const m of state.map.markers) count[m.id] = (count[m.id] || 0) + 1;
  const rows = [...state.map.markers].sort((a, b) => a.id - b.id);
  for (const m of rows) {
    const tr = document.createElement('tr'); if (m.id === state.sel) tr.className = 'sel'; if (count[m.id] > 1) tr.className = 'dup';
    if (count[m.id] > 1) tr.title = 'ID ' + m.id + ' is used twice: the detector cannot tell these markers apart';
    const cell = (val, st, key, conv) => {
      const td = document.createElement('td'); const inp = document.createElement('input'); inp.type = 'number'; inp.step = st; inp.value = val;
      inp.onfocus = () => { if (state.sel !== m.id) { state.sel = m.id; state.sel2 = null; $('delm').disabled = $('rotm').disabled = false; draw(); updateMeasure(); } };
      inp.onchange = () => { const v = parseFloat(inp.value); if (!isFinite(v)) return; snapshot(); if (key === 'id') { m.id = Math.round(v); state.sel = m.id; } else m[key] = conv ? conv(v) : v; mapChanged(); };
      td.appendChild(inp); tr.appendChild(td);
    };
    cell(m.id, 1, 'id');
    cell((m.length * k).toFixed(dig), step, 'length', v => v / k); cell((m.x * k).toFixed(dig), step, 'x', v => v / k); cell((m.y * k).toFixed(dig), step, 'y', v => v / k);
    cell((m.rot_z * 180 / Math.PI).toFixed(1), 1, 'rot_z', v => v * Math.PI / 180);
    tb.appendChild(tr);
  }
}
$('units').onchange = () => { store.set('units', unitName()); renderTable(); updateMeasure(); draw(); };

// ---------- exact distances between two markers ----------
function updateMeasure() {
  const a = selMarker(), b = sel2Marker();
  $('measbox').hidden = !(a && b);
  $('measnote').textContent = !a ? 'Click a marker, then Shift+click a second one.' : (!b ? 'Marker ' + a.id + ' selected. Shift+click a second marker.' : 'From marker ' + a.id + ' to marker ' + b.id + ' (centre to centre):');
  if (!(a && b)) return;
  const k = unitK(), dig = k === 1 ? 3 : 1, d = Math.hypot(b.x - a.x, b.y - a.y);
  $('measd').textContent = (d * k).toFixed(dig) + ' ' + unitName();
  $('measxy').textContent = 'Δx ' + ((b.x - a.x) * k).toFixed(dig) + ' ' + unitName() + ', Δy ' + ((b.y - a.y) * k).toFixed(dig) + ' ' + unitName()
    + '. Gap between the marker edges along this line ≈ ' + (Math.max(0, d - (a.length + b.length) / 2) * k).toFixed(dig) + ' ' + unitName();
  if (document.activeElement !== $('setd')) $('setd').value = (d * k).toFixed(dig);
  if (document.activeElement !== $('setdx')) $('setdx').value = ((b.x - a.x) * k).toFixed(dig);
  if (document.activeElement !== $('setdy')) $('setdy').value = ((b.y - a.y) * k).toFixed(dig);
}
const r4 = (v) => Math.round(v * 10000) / 10000;          // 0.1 mm: no float noise in map.txt
$('applyd').onclick = () => {
  const a = selMarker(), b = sel2Marker(); if (!a || !b) return;
  const want = parseFloat($('setd').value) / unitK(), d = Math.hypot(b.x - a.x, b.y - a.y);
  if (!(want > 0) || want > 50) { addMsg($('mapmsgs'), 'error', 'The distance must be more than 0 and at most 50 m (5000 cm).'); return; }
  const ux = d > 1e-9 ? (b.x - a.x) / d : 1, uy = d > 1e-9 ? (b.y - a.y) / d : 0;
  snapshot(); b.x = r4(a.x + ux * want); b.y = r4(a.y + uy * want); mapChanged();
};
$('applydxy').onclick = () => {
  const a = selMarker(), b = sel2Marker(); if (!a || !b) return;
  const dx = parseFloat($('setdx').value) / unitK(), dy = parseFloat($('setdy').value) / unitK();
  if (!isFinite(dx) || !isFinite(dy) || Math.abs(dx) > 50 || Math.abs(dy) > 50 || (dx === 0 && dy === 0)) {    // review 24.11, m5
    addMsg($('mapmsgs'), 'error', 'Δx and Δy must be numbers within ±50 m (±5000 cm), not both zero.'); return;
  }
  snapshot(); b.x = r4(a.x + dx); b.y = r4(a.y + dy); mapChanged();
};

// ---------- grid from a template ----------
$('g_make').onclick = () => {
  const rows = Math.round(+$('g_rows').value), cols = Math.round(+$('g_cols').value), id0 = Math.round(+$('g_id0').value);
  const k = unitK(), dx = +$('g_dx').value / k, dy = +$('g_dy').value / k, side = +$('g_side').value / k;
  const bad = [];
  if (!(rows >= 1 && rows <= 10 && cols >= 1 && cols <= 10)) bad.push('rows and columns: 1–10');
  if (!(id0 >= 0 && id0 + rows * cols - 1 <= 99)) bad.push('IDs must stay within 0–99');
  if (!(side >= 0.05 && side <= 1.0)) bad.push('marker side: 5–100 cm');
  if (!(dx > side && dy > side)) bad.push('the step must be larger than the marker side (else markers overlap)');
  if (dx * cols > 50 || dy * rows > 50) bad.push('the grid is larger than 50 m: check the units');
  if (bad.length) { $('g_note').textContent = 'Not made: ' + bad.join('; ') + '.'; $('g_note').className = 'note warnnote'; return; }
  snapshot();
  const ms = [];
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) ms.push({ id: id0 + r * cols + c, length: r4(side), x: r4(c * dx), y: r4(r * dy), rot_z: Math.PI / 2 });
  state.map.markers = ms; state.sel = state.sel2 = null; state.view = null;
  $('g_note').textContent = 'Made ' + ms.length + ' markers. Undo brings the old map back.'; $('g_note').className = 'note';
  mapChanged();
};

// ---------- drawing ----------
const cv = $('map'); const ctx = cv.getContext('2d');
function fitView() {
  const ms = state.map.markers; let x0 = -1, y0 = -1, x1 = 1, y1 = 1;
  if (ms.length) { x0 = Math.min(...ms.map(m => m.x)); x1 = Math.max(...ms.map(m => m.x)); y0 = Math.min(...ms.map(m => m.y)); y1 = Math.max(...ms.map(m => m.y)); }
  const pad = 0.9; x0 -= pad; x1 += pad; y0 -= pad; y1 += pad;
  const W = cv.clientWidth, H = cv.clientHeight; const s = Math.min(W / (x1 - x0), H / (y1 - y0));
  state.view = { s, ox: (W - s * (x1 - x0)) / 2 - s * x0, oy: (H + s * (y1 - y0)) / 2 + s * y0 };
}
const toS = (x, y) => [state.view.ox + state.view.s * x, state.view.oy - state.view.s * y];
const toW = (px, py) => [(px - state.view.ox) / state.view.s, (state.view.oy - py) / state.view.s];
function corners(m) { const h = m.length / 2, c = Math.cos(m.rot_z), s = Math.sin(m.rot_z); return [[-h, h], [h, h], [h, -h], [-h, -h]].map(([dx, dy]) => [m.x + c * dx - s * dy, m.y + s * dx + c * dy]); }
function label(text, x, y) {
  ctx.save(); ctx.font = '600 11px system-ui'; const w = ctx.measureText(text).width + 10;
  ctx.fillStyle = css('--panel'); ctx.strokeStyle = css('--line'); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x - w / 2, y - 9, w, 18, 9) : ctx.rect(x - w / 2, y - 9, w, 18); ctx.fill(); ctx.stroke();
  ctx.fillStyle = css('--ink'); ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, x, y + 0.5); ctx.restore();
}
function drawRulers() {
  const a = selMarker(); if (!a) return;
  const k = unitK(), dig = k === 1 ? 2 : 0, u = unitName();
  const b = sel2Marker();
  const others = b ? [b] : state.map.markers.filter(m => m !== a).map(m => [m, Math.hypot(m.x - a.x, m.y - a.y)]).sort((p, q) => p[1] - q[1]).slice(0, 4).map(p => p[0]);
  ctx.save();
  for (const m of others) {
    const [x0, y0] = toS(a.x, a.y), [x1, y1] = toS(m.x, m.y);
    ctx.strokeStyle = b ? css('--accent') : css('--muted'); ctx.lineWidth = b ? 2 : 1; ctx.setLineDash(b ? [] : [4, 4]);
    ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); ctx.setLineDash([]);
    label((Math.hypot(m.x - a.x, m.y - a.y) * k).toFixed(dig) + ' ' + u, (x0 + x1) / 2, (y0 + y1) / 2);
  }
  ctx.restore();
}
function draw() {
  const dpr = window.devicePixelRatio || 1; const W = cv.clientWidth, H = cv.clientHeight;
  if (W < 10 || H < 10) { state.view = null; return; }          // hidden or not laid out yet
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, W, H);
  if (!state.view || !state.drag) fitView();
  if (!(state.view.s > 0) || !isFinite(state.view.s)) return;
  // grid 0.5 m (at most 200 lines each way)
  ctx.strokeStyle = css('--grid'); ctx.lineWidth = 1; ctx.fillStyle = css('--muted'); ctx.font = '11px system-ui';
  const [wx0, wy1] = toW(0, 0), [wx1, wy0] = toW(W, H);
  if ((wx1 - wx0) > 100 || (wy1 - wy0) > 100) return;
  for (let x = Math.ceil(wx0 * 2) / 2; x <= wx1; x += 0.5) { const [px] = toS(x, 0); ctx.beginPath(); ctx.moveTo(px, 0); ctx.lineTo(px, H); ctx.stroke(); if (Math.abs(x % 1) < 1e-6) ctx.fillText(x.toFixed(0) + ' m', px + 2, H - 4); }
  for (let y = Math.ceil(wy0 * 2) / 2; y <= wy1; y += 0.5) { const [, py] = toS(0, y); ctx.beginPath(); ctx.moveTo(0, py); ctx.lineTo(W, py); ctx.stroke(); if (Math.abs(y % 1) < 1e-6) ctx.fillText(y.toFixed(0) + ' m', 3, py - 2); }
  // heat
  const g = state.grid;
  if (g && $('heat').checked) {
    const s = state.view.s * g.step; const cols = { blind: blindPattern(), red: css('--red'), yellow: css('--yellow'), green: css('--green') };
    for (let j = 0; j < g.ny; j++) for (let i = 0; i < g.nx; i++) {
      const [px, py] = toS(g.x0 + i * g.step, g.y0 + j * g.step); ctx.fillStyle = cols[shadeOf(g.counts[j][i], g)]; ctx.fillRect(px - s / 2, py - s / 2, s + 0.5, s + 0.5);
    }
  }
  // markers
  const count = {}; for (const m of state.map.markers) count[m.id] = (count[m.id] || 0) + 1;
  for (const m of state.map.markers) {
    const pts = corners(m).map(p => toS(p[0], p[1]));
    ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath();
    ctx.fillStyle = css('--marker'); ctx.fill();
    if (count[m.id] > 1) { ctx.lineWidth = 3; ctx.strokeStyle = css('--err'); ctx.stroke(); }
    if (m.id === state.sel || m.id === state.sel2) { ctx.lineWidth = 3; ctx.strokeStyle = css('--accent'); ctx.stroke(); }
    // orientation tick near the edge, so it does not cross the ID (review 24.11, d2)
    const [cx, cy] = toS(m.x, m.y); const [fx, fy] = toS(m.x + Math.cos(m.rot_z) * m.length * 0.28, m.y + Math.sin(m.rot_z) * m.length * 0.28);
    const [tx, ty] = toS(m.x + Math.cos(m.rot_z) * m.length * 0.46, m.y + Math.sin(m.rot_z) * m.length * 0.46);
    ctx.strokeStyle = css('--marker-ink'); ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(fx, fy); ctx.lineTo(tx, ty); ctx.stroke();
    ctx.fillStyle = css('--marker-ink'); ctx.font = 'bold 12px system-ui'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(String(m.id), cx, cy);
    ctx.textAlign = 'start'; ctx.textBaseline = 'alphabetic';
  }
  drawRulers();
  drawHover();
  if (g && $('heat').checked) drawHeading(g);
  drawSim();
  drawLive();
}
function levelColor(n) { return n < 1.5 ? css('--err') : (n < 2.5 ? css('--warn') : css('--ok')); }
function drawSim() {
  const r = state.sim; if (!r || !r.trace || !r.trace.length) return;
  const tr = r.trace;
  ctx.lineWidth = 3;
  for (let k = 1; k < tr.length; k++) {
    if (!tr[k][5] && !tr[k - 1][5]) continue;
    const [x0, y0] = toS(tr[k - 1][1], tr[k - 1][2]), [x1, y1] = toS(tr[k][1], tr[k][2]);
    ctx.strokeStyle = levelColor(tr[k][4]); ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
  }
  const p = sampleAt(state.t); if (!p) return;
  const [px, py] = toS(p[1], p[2]);
  const fp = cameraFrame(r, p);
  if (fp) {
    ctx.save();
    const rect = fp.rect.map(([x, y]) => toS(x, y));
    ctx.beginPath(); rect.forEach((q, i) => i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1])); ctx.closePath();
    ctx.setLineDash([2, 4]); ctx.strokeStyle = css('--muted'); ctx.lineWidth = 1; ctx.stroke(); ctx.setLineDash([]);
    ctx.clip();
    if (fp.cone) {
      const [cx, cy] = toS(fp.cone[0], fp.cone[1]);
      ctx.beginPath(); ctx.arc(cx, cy, fp.cone[2] * state.view.s, 0, 2 * Math.PI);
      ctx.fillStyle = 'rgba(37, 99, 235, 0.10)'; ctx.fill();
      ctx.setLineDash([5, 4]); ctx.strokeStyle = css('--path'); ctx.lineWidth = 1.5; ctx.stroke(); ctx.setLineDash([]);
    }
    ctx.restore();
  }
  ctx.fillStyle = css('--path'); ctx.beginPath(); ctx.arc(px, py, 8, 0, 2 * Math.PI); ctx.fill();
  const [hx, hy] = toS(p[1] + Math.cos(r.yaw) * 0.18, p[2] + Math.sin(r.yaw) * 0.18);
  ctx.strokeStyle = css('--path'); ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(hx, hy); ctx.stroke();
}
// What the down camera can use at sample p: the image frame on the floor (forward reaches further
// than back: cy of the drone's K) and the detection cone max_tan. Shared by the 2D map and the 3D view.
function cameraFrame(r, p) {
  const h = p[3] - r.mount_down - r.z_floor;
  if (!r.cam_K || !p[5] || h <= 0.05) return null;
  const K = r.cam_K, c = Math.cos(r.yaw), s = Math.sin(r.yaw);
  const ox = p[1] + c * r.mount_fwd, oy = p[2] + s * r.mount_fwd;
  const fwd = K.cy * h / K.fy, back = (K.H - K.cy) * h / K.fy, left = K.cx * h / K.fx, right = (K.W - K.cx) * h / K.fx;
  const rect = [[fwd, left], [fwd, -right], [-back, -right], [-back, left]].map(([f, l]) => [ox + c * f - s * l, oy + s * f + c * l]);
  return { rect, cone: r.max_tan ? [ox, oy, r.max_tan * h] : null, origin: [ox, oy], h };
}
function drawLive() {
  const tr = drone.trail; if (!tr.length || !state.view) return;
  ctx.strokeStyle = '#ff9500'; ctx.lineWidth = 2; ctx.beginPath();
  tr.forEach((p, i) => { const [x, y] = toS(p.x, p.y); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke();
  const p = tr[tr.length - 1]; const [x, y] = toS(p.x, p.y);
  ctx.fillStyle = '#ff9500'; ctx.beginPath(); ctx.arc(x, y, 9, 0, 2 * Math.PI); ctx.fill();
  ctx.fillStyle = css('--ink'); ctx.font = '11px system-ui'; ctx.fillText('drone z=' + p.z.toFixed(2) + (p.armed ? ' in the air' : ''), x + 12, y - 8);
}
function sampleAt(t) {
  const tr = state.sim && state.sim.trace; if (!tr || !tr.length) return null;
  let lo = 0, hi = tr.length - 1; if (t <= tr[0][0]) return tr[0]; if (t >= tr[hi][0]) return tr[hi];
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (tr[mid][0] <= t) lo = mid; else hi = mid; }
  const a = tr[lo], b = tr[hi], k = (t - a[0]) / Math.max(1e-6, b[0] - a[0]);
  return [t, a[1] + k * (b[1] - a[1]), a[2] + k * (b[2] - a[2]), a[3] + k * (b[3] - a[3]), a[4], a[5]];
}

// ---------- map interaction ----------
function hit(px, py) {
  const [wx, wy] = toW(px, py);
  let best = null, bd = 1e9;
  for (const m of state.map.markers) { const d = Math.hypot(m.x - wx, m.y - wy); if (d < m.length * 0.75 && d < bd) { best = m; bd = d; } }
  return best;
}
cv.addEventListener('pointerdown', (e) => {
  if (!state.view) return;
  const rect = cv.getBoundingClientRect(); const px = e.clientX - rect.left, py = e.clientY - rect.top;
  const m = hit(px, py);
  if (m && e.shiftKey && state.sel !== null) { setSel(m.id, true); return; }
  if (m) { setSel(m.id); const [wx, wy] = toW(px, py); state.drag = { m, dx: m.x - wx, dy: m.y - wy, before: mapJSON(), moved: false }; cv.setPointerCapture(e.pointerId); }
  else setSel(null);
});
cv.addEventListener('pointermove', (e) => {
  if (!state.drag) { const r = cv.getBoundingClientRect(); state.hoverOn = true; hoverAt(e.clientX - r.left, e.clientY - r.top); return; }
  state.hoverOn = false; $('hint').hidden = true; state.hover = null;
  const rect = cv.getBoundingClientRect(); const [wx, wy] = toW(e.clientX - rect.left, e.clientY - rect.top);
  const snap = $('snap').checked ? 0.01 : 0.001;
  state.drag.m.x = r4(Math.round((wx + state.drag.dx) / snap) * snap); state.drag.m.y = r4(Math.round((wy + state.drag.dy) / snap) * snap);
  state.drag.moved = true;
  draw(); updateMeasure();
});
const endDrag = () => {
  if (!state.drag) return;
  const d = state.drag; state.drag = null;
  if (d.moved) { state.undo.push(d.before); if (state.undo.length > 50) state.undo.shift(); $('undom').disabled = false; mapChanged(); }
};
cv.addEventListener('pointerup', endDrag);
cv.addEventListener('pointercancel', endDrag);
cv.addEventListener('pointerleave', () => { state.hoverOn = false; hoverSeq++; $('hint').hidden = true; if (state.hover) { state.hover = null; draw(); } });
cv.addEventListener('dblclick', (e) => {
  const rect = cv.getBoundingClientRect(); const px = e.clientX - rect.left, py = e.clientY - rect.top;
  if (hit(px, py)) return;                            // a double click on a marker does not put a new one on top
  const [wx, wy] = toW(px, py);
  addMarker({ id: nextId(), length: 0.29, x: Math.round(wx * 100) / 100, y: Math.round(wy * 100) / 100, rot_z: Math.PI / 2 });
});
$('addm').onclick = () => {
  const ms = state.map.markers; const cx = ms.length ? ms.reduce((s, m) => s + m.x, 0) / ms.length : 0; const cy = ms.length ? Math.max(...ms.map(m => m.y)) + 0.7 : 0;
  state.view = null;
  addMarker({ id: nextId(), length: ms.length ? 0.29 : 0.19, x: Math.round(cx * 100) / 100, y: Math.round(cy * 100) / 100, rot_z: Math.PI / 2 });
};
// one marker only, also when two share an ID (review 24.11, m6)
$('delm').onclick = () => { const i = state.map.markers.findIndex(m => m.id === state.sel); if (i < 0) return; snapshot(); state.map.markers.splice(i, 1); setSel(null); state.view = null; mapChanged(); };
$('rotm').onclick = () => { const m = selMarker(); if (!m) return; snapshot(); m.rot_z = Math.atan2(Math.sin(m.rot_z + Math.PI / 2), Math.cos(m.rot_z + Math.PI / 2)); mapChanged(); };
$('undom').onclick = undoMap;
document.addEventListener('keydown', (e) => {
  if (state.tab !== 'map' || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== 'z') return;
  const t = document.activeElement; if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return;
  e.preventDefault(); undoMap();
});
$('mapname').onchange = () => { snapshot(); state.map.name = $('mapname').value.trim(); mapChanged(); };
$('heat').onchange = () => recheckMap();
$('cam').onchange = () => { updateCamNote(); recheckMap(); if (state.sim) { state.sim.stale = true; showStale(); } autoSimSoon(); };   // review 24.11, m4
$('zh').oninput = () => { state.followProgram = false; $('zhv').textContent = takeoffH().toFixed(2); };
$('zh').onchange = () => computeGrid();
$('zfromprog').onclick = () => { state.followProgram = true; syncTakeoff(); };
$('turn').onchange = () => computeGrid();
function updateCamNote() {
  const v = $('cam').value;
  $('camnote').textContent = v === 'drone'
    ? 'The drone’s camera (calibration from the drone). The detection limit is taken from Gazebo: not measured on the real drone, and Gazebo is more optimistic (the detector runs at 7 frames/s on the Pi against 23). This is an estimate.'
    : 'Gazebo: the limit was fitted on half of the runs of the real map and checked on the other half: the marker count is right within ±1 in 92 % of frames.';
}
function download(name, text) { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain' })); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); }
$('dltxt').onclick = () => { if (state.check && state.check.txt && !$('dltxt').disabled) download('map.txt', state.check.txt); };
$('dljson').onclick = () => { if (state.check && state.check.json && !$('dljson').disabled) download((state.map.name || 'map') + '.json', state.check.json); };
async function loadText(text, fname) {
  // messages on the page, not alert(): alert may be swallowed inside WKWebView (review item 15)
  const ul = $('mapmsgs');
  let m = null, fileErrors = [];
  const t = text.trim();
  if (t.startsWith('{')) {
    try { m = JSON.parse(t); } catch (e) { ul.innerHTML = ''; addMsg(ul, 'error', 'Bad JSON: ' + e.message); return; }
  } else {
    let r;
    try { r = await api('map_from_txt', [text, (fname || 'field').replace(/\.[^.]+$/, '')], 15000); }
    catch (e) { ul.innerHTML = ''; addMsg(ul, 'error', e.message); return; }
    if (r.error) { ul.innerHTML = ''; addMsg(ul, 'error', 'File not read: ' + r.error); return; }
    m = r; fileErrors = (r._check && r._check.errors) || [];   // e.g. a short line the detector would skip (review item 12)
  }
  snapshot();
  state.fileErrors = fileErrors;
  state.map = { name: String(m.name || 'field'), z: Number.isFinite(+m.z) ? +m.z : -0.32,
                markers: (Array.isArray(m.markers) ? m.markers : []).slice(0, 200).map(k => ({ id: +k.id, length: +k.length, x: +k.x, y: +k.y, rot_z: +(k.rot_z || 0) })) };
  $('mapname').value = state.map.name; state.view = null; setSel(null); mapChanged();
}
$('file').onchange = async (e) => { const f = e.target.files[0]; if (f) await loadText(await f.text(), f.name); e.target.value = ''; };
$('usepaste').onclick = () => loadText($('paste').value, 'field');
