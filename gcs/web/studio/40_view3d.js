// ---------- 3D flight preview: a small perspective renderer on a 2D canvas (no WebGL, no library) ----------
// World = the map frame: x, y on the floor (metres), z up. The floor is the marker plane (map z).
const v3 = $('view3d'), g3 = v3.getContext('2d');
const cam3 = { mode: 'free', az: -2.25, el: 0.62, dist: null, target: null, fov: 50 * Math.PI / 180, user: false };
const ARM = 0.226, ROTOR_R = 0.19;            // 20EC model 1:1: motor axes ±0.2262 m, 15" props
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const crs = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const nrm = (a) => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
function floorZ() { return Number.isFinite(+state.map.z) ? +state.map.z : -0.32; }
function sceneBounds() {
  const ms = state.map.markers;
  if (!ms.length) return [-1, -1, 1, 1];
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const m of ms) for (const [x, y] of corners(m)) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}
function camBasis() {
  const [bx0, by0, bx1, by1] = sceneBounds();
  const span = Math.max(bx1 - bx0, by1 - by0, 1.5);
  if (!cam3.target || !cam3.user) cam3.target = [(bx0 + bx1) / 2, (by0 + by1) / 2, floorZ() + 0.4];
  if (!cam3.dist || !cam3.user) cam3.dist = span * 1.25 + 1.2;
  let az = cam3.az, el = cam3.el, dist = cam3.dist, target = cam3.target;
  if (cam3.mode === 'top') { az = -Math.PI / 2; el = 1.5607; }
  else if (cam3.mode === 'side') { az = -Math.PI / 2; el = 0.10; }
  else if (cam3.mode === 'follow') {
    const p = state.sim ? sampleAt(state.t) : null, yaw = state.sim ? state.sim.yaw : 0;
    if (p) target = [p[1], p[2], p[3]];
    az = yaw + Math.PI; el = 0.42; dist = 2.4;
  }
  const eye = [target[0] + dist * Math.cos(el) * Math.cos(az), target[1] + dist * Math.cos(el) * Math.sin(az), target[2] + dist * Math.sin(el)];
  const f = nrm(sub(target, eye)), r = nrm(crs(f, [0, 0, 1])), u = crs(r, f);
  return { eye, f, r, u };
}
let B = null, W3 = 0, H3 = 0, F3 = 1;
const NEAR = 0.05;
function toCam(p) { const d = sub(p, B.eye); return [dot(d, B.r), dot(d, B.u), dot(d, B.f)]; }
function scr(c) { return [W3 / 2 + F3 * c[0] / c[2], H3 / 2 - F3 * c[1] / c[2], c[2]]; }
function proj(p) { const c = toCam(p); return c[2] < NEAR ? null : scr(c); }
function seg(p0, p1) {                       // a segment clipped at the near plane
  let a = toCam(p0), b = toCam(p1);
  if (a[2] < NEAR && b[2] < NEAR) return null;
  if (a[2] < NEAR) { const k = (NEAR - a[2]) / (b[2] - a[2]); a = [a[0] + k * (b[0] - a[0]), a[1] + k * (b[1] - a[1]), NEAR]; }
  if (b[2] < NEAR) { const k = (NEAR - b[2]) / (a[2] - b[2]); b = [b[0] + k * (a[0] - b[0]), b[1] + k * (a[1] - b[1]), NEAR]; }
  return [scr(a), scr(b)];
}
function line3(p0, p1) { const s = seg(p0, p1); if (!s) return; g3.beginPath(); g3.moveTo(s[0][0], s[0][1]); g3.lineTo(s[1][0], s[1][1]); g3.stroke(); }
function poly3(pts, fill, stroke) {
  // clip the polygon at the near plane in camera space (Sutherland–Hodgman), so a floor or a
  // rotor that reaches behind the camera is cut, not dropped (review 24.11, m7)
  const cs = pts.map(toCam), inside = [];
  for (let i = 0; i < cs.length; i++) {
    const a = cs[i], b = cs[(i + 1) % cs.length], ain = a[2] >= NEAR, bin = b[2] >= NEAR;
    if (ain) inside.push(a);
    if (ain !== bin) { const k = (NEAR - a[2]) / (b[2] - a[2]); inside.push([a[0] + k * (b[0] - a[0]), a[1] + k * (b[1] - a[1]), NEAR]); }
  }
  if (inside.length < 3) return null;
  const q = inside.map(scr);
  g3.beginPath(); q.forEach((v, i) => i ? g3.lineTo(v[0], v[1]) : g3.moveTo(v[0], v[1])); g3.closePath();
  if (fill) { g3.fillStyle = fill; g3.fill(); }
  if (stroke) { g3.strokeStyle = stroke; g3.stroke(); }
  return q;
}
function circle3(cx, cy, cz, r, n) { const out = []; for (let i = 0; i < n; i++) { const a = 2 * Math.PI * i / n; out.push([cx + r * Math.cos(a), cy + r * Math.sin(a), cz]); } return out; }
function render3d() {
  const dpr = window.devicePixelRatio || 1; W3 = v3.clientWidth; H3 = v3.clientHeight;
  if (W3 < 10 || H3 < 10) return;
  if (v3.width !== Math.round(W3 * dpr) || v3.height !== Math.round(H3 * dpr)) { v3.width = Math.round(W3 * dpr); v3.height = Math.round(H3 * dpr); }
  g3.setTransform(dpr, 0, 0, dpr, 0, 0);
  const sky = g3.createLinearGradient(0, 0, 0, H3); sky.addColorStop(0, css('--sky-top')); sky.addColorStop(1, css('--sky-bot'));
  g3.fillStyle = sky; g3.fillRect(0, 0, W3, H3);
  B = camBasis(); F3 = (H3 / 2) / Math.tan(cam3.fov / 2);
  const zf = floorZ(), [bx0, by0, bx1, by1] = sceneBounds();
  // floor: a plate under the field and a 0.5 m grid
  const gx0 = Math.floor((bx0 - 1.0) * 2) / 2, gx1 = Math.ceil((bx1 + 1.0) * 2) / 2, gy0 = Math.floor((by0 - 1.0) * 2) / 2, gy1 = Math.ceil((by1 + 1.0) * 2) / 2;
  if ((gx1 - gx0) > 120 || (gy1 - gy0) > 120) {
    g3.fillStyle = css('--muted'); g3.font = '13px system-ui'; g3.textAlign = 'center';
    g3.fillText('The map is larger than 120 m: check the units of the marker positions (metres).', W3 / 2, H3 / 2); g3.textAlign = 'start';
    return;
  }
  g3.lineWidth = 1;
  poly3([[gx0, gy0, zf], [gx1, gy0, zf], [gx1, gy1, zf], [gx0, gy1, zf]], css('--floor'), null);
  for (let x = gx0; x <= gx1 + 1e-9; x += 0.5) { g3.strokeStyle = Math.abs(x - Math.round(x)) < 1e-6 ? css('--floor-line') : css('--grid'); line3([x, gy0, zf], [x, gy1, zf]); }
  for (let y = gy0; y <= gy1 + 1e-9; y += 0.5) { g3.strokeStyle = Math.abs(y - Math.round(y)) < 1e-6 ? css('--floor-line') : css('--grid'); line3([gx0, y, zf], [gx1, y, zf]); }
  // axes from the map origin
  g3.lineWidth = 2; g3.strokeStyle = '#ff3b30'; line3([0, 0, zf], [0.5, 0, zf]); g3.strokeStyle = '#34c759'; line3([0, 0, zf], [0, 0.5, zf]); g3.strokeStyle = css('--path'); line3([0, 0, zf], [0, 0, zf + 0.5]);
  g3.font = '11px system-ui'; g3.fillStyle = css('--muted');
  for (let x = Math.ceil(gx0); x <= gx1; x++) { const p = proj([x, gy0, zf]); if (p) g3.fillText(x + ' m', p[0] + 2, p[1] - 3); }
  for (let y = Math.ceil(gy0); y <= gy1; y++) { const p = proj([gx0, y, zf]); if (p) g3.fillText(y + ' m', p[0] + 2, p[1] - 3); }
  // guard border: the map + margin; beyond it the guard lands the drone
  if (state.map.markers.length) {
    const mg = (state.sim && state.sim.limits && state.sim.limits.field_margin) || 0.30;
    g3.setLineDash([6, 5]); g3.lineWidth = 1.5;
    poly3([[bx0 - mg, by0 - mg, zf], [bx1 + mg, by0 - mg, zf], [bx1 + mg, by1 + mg, zf], [bx0 - mg, by1 + mg, zf]], null, css('--err'));
    g3.setLineDash([]);
  }
  // markers: a white frame, the black square, the ID
  for (const m of state.map.markers) {
    const z = zf + 0.002, big = Object.assign({}, m, { length: m.length * 1.28 });
    poly3(corners(big).map(([x, y]) => [x, y, z]), '#ffffff', css('--floor-line'));
    poly3(corners(m).map(([x, y]) => [x, y, z]), m.id === state.sel ? css('--accent') : '#1d1d1f', null);
    const c = proj([m.x, m.y, z]);
    if (c) { const fs = Math.max(8, Math.min(22, F3 * m.length * 0.42 / c[2])); g3.font = '600 ' + fs.toFixed(0) + 'px system-ui'; g3.fillStyle = '#ffffff'; g3.textAlign = 'center'; g3.textBaseline = 'middle'; g3.fillText(String(m.id), c[0], c[1]); g3.textAlign = 'start'; g3.textBaseline = 'alphabetic'; }
  }
  const r = state.sim, p = r ? sampleAt(state.t) : null;
  $('viewempty').hidden = !!(r && r.trace && r.trace.length);
  if (r && r.trace && r.trace.length) {
    const tr = r.trace;
    // camera frame and detection circle on the floor
    const fp = p ? cameraFrame(r, p) : null;
    if (fp) {
      poly3(fp.rect.map(([x, y]) => [x, y, zf + 0.003]), 'rgba(0, 113, 227, 0.08)', css('--path'));
      if (fp.cone) { g3.setLineDash([4, 4]); poly3(circle3(fp.cone[0], fp.cone[1], zf + 0.003, fp.cone[2], 36), 'rgba(0, 113, 227, 0.10)', css('--path')); g3.setLineDash([]); }
    }
    // shadow of the path on the floor, then the path coloured by markers in view
    g3.lineWidth = 2.5; g3.strokeStyle = 'rgba(70, 70, 80, 0.55)';     // the path's shadow: where it is over the floor (review 24.11, d1)
    for (let k = 1; k < tr.length; k++) if (tr[k][5] || tr[k - 1][5]) line3([tr[k - 1][1], tr[k - 1][2], zf + 0.004], [tr[k][1], tr[k][2], zf + 0.004]);
    g3.lineWidth = 3;
    for (let k = 1; k < tr.length; k++) {
      if (!tr[k][5] && !tr[k - 1][5]) continue;
      g3.strokeStyle = levelColor(tr[k][4]); g3.globalAlpha = tr[k][0] <= state.t ? 1 : 0.35;
      line3([tr[k - 1][1], tr[k - 1][2], tr[k - 1][3]], [tr[k][1], tr[k][2], tr[k][3]]);
    }
    g3.globalAlpha = 1;
    // problems on the path: click one to jump there
    state.pins = [];
    for (const f of (r.preflight ? r.preflight.findings : [])) {
      if (f.t === null || f.t === undefined || f.level === 'info') continue;
      const q = sampleAt(f.t); if (!q) continue;
      const s = proj([q[1], q[2], q[3]]); if (!s) continue;
      g3.fillStyle = f.level === 'error' ? css('--err') : css('--warn');
      g3.beginPath(); g3.arc(s[0], s[1], 6, 0, 2 * Math.PI); g3.fill(); g3.strokeStyle = '#ffffff'; g3.lineWidth = 2; g3.stroke();
      state.pins.push({ x: s[0], y: s[1], f });
    }
    if (p) drawDrone3(p, r.yaw);
  }
  // the real drone, live from the mission server
  if (drone.trail.length > 1) {
    g3.strokeStyle = '#ff9500'; g3.lineWidth = 2;
    for (let k = 1; k < drone.trail.length; k++) { const a = drone.trail[k - 1], b = drone.trail[k]; line3([a.x, a.y, a.z], [b.x, b.y, b.z]); }
  }
  updateViewInfo(p);
}
function drawDrone3(p, yaw) {
  const [x, y, z] = [p[1], p[2], p[3]], zf = floorZ();
  g3.setLineDash([3, 4]); g3.strokeStyle = css('--muted'); g3.lineWidth = 1; line3([x, y, z], [x, y, zf]); g3.setLineDash([]);
  poly3(circle3(x, y, zf + 0.004, 0.16, 20), 'rgba(0, 0, 0, 0.12)', null);          // shadow
  const parts = [];
  for (let i = 0; i < 4; i++) {
    const a = yaw + Math.PI / 4 + i * Math.PI / 2, mx = x + ARM * Math.cos(a), my = y + ARM * Math.sin(a);
    const c = toCam([mx, my, z]); parts.push({ depth: c[2], mx, my, a });
  }
  parts.sort((a, b) => b.depth - a.depth);                                        // far rotors first
  for (const q of parts) {
    g3.strokeStyle = css('--drone'); g3.lineWidth = 3; line3([x, y, z], [q.mx, q.my, z]);
    poly3(circle3(q.mx, q.my, z + 0.02, ROTOR_R, 22), css('--rotor'), css('--path'));
  }
  const c = Math.cos(yaw), s = Math.sin(yaw), h = 0.07;
  const body = [[1.4 * h, h], [1.4 * h, -h], [-h, -h], [-h, h]].map(([f, l]) => [x + c * f - s * l, y + s * f + c * l, z + 0.03]);
  poly3(body, css('--drone'), null);
  g3.strokeStyle = '#ff9500'; g3.lineWidth = 3; line3([x, y, z + 0.04], [x + c * 0.32, y + s * 0.32, z + 0.04]);     // nose
}
function updateViewInfo(p) {
  const box = $('viewinfo'); box.textContent = '';
  const add = (k, v) => { const d = document.createElement('div'); d.append(document.createTextNode(k + ' '), Object.assign(document.createElement('b'), { textContent: v })); box.appendChild(d); };
  if (!p) { add('map', '“' + (state.map.name || '') + '”, ' + state.map.markers.length + ' markers'); return; }
  const r = state.sim, zr = (r.trace[0] || p)[3];
  add('t', fmt(p[0], 1) + ' s');
  add('x, y', fmt(p[1], 2) + ', ' + fmt(p[2], 2) + ' m');
  add('above the floor', fmt(p[3] - zr, 2) + ' m');
  add('markers in view', fmt(p[4], 1));
  add('', p[5] ? 'in the air' : 'on the ground');
}
// ---------- mouse: rotate, pan, zoom; click a problem pin ----------
let drag3 = null;
v3.addEventListener('pointerdown', (e) => {
  const rect = v3.getBoundingClientRect(), px = e.clientX - rect.left, py = e.clientY - rect.top;
  const pin = (state.pins || []).find(q => Math.hypot(q.x - px, q.y - py) < 9);
  if (pin) { seek(pin.f.t); highlightFinding(pin.f); return; }
  drag3 = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey };
  v3.setPointerCapture(e.pointerId); v3.classList.add('drag');
});
v3.addEventListener('pointermove', (e) => {
  if (!drag3) return;
  const dx = e.clientX - drag3.x, dy = e.clientY - drag3.y; drag3.x = e.clientX; drag3.y = e.clientY;
  if (cam3.mode !== 'free') setView('free');
  cam3.user = true; camBasis();
  if (drag3.pan) {
    const k = cam3.dist / F3;
    const rx = B.r[0], ry = B.r[1], fx = B.f[0], fy = B.f[1], fl = Math.hypot(fx, fy) || 1;
    cam3.target = [cam3.target[0] - (rx * dx - fx / fl * dy) * k, cam3.target[1] - (ry * dx - fy / fl * dy) * k, cam3.target[2]];
  } else { cam3.az -= dx * 0.008; cam3.el = Math.max(0.05, Math.min(1.55, cam3.el + dy * 0.008)); }
  render3d();
});
const end3 = () => { drag3 = null; v3.classList.remove('drag'); };
v3.addEventListener('pointerup', end3); v3.addEventListener('pointercancel', end3);
v3.addEventListener('contextmenu', (e) => e.preventDefault());
v3.addEventListener('wheel', (e) => { e.preventDefault(); camBasis(); cam3.user = true; cam3.dist = Math.max(0.6, Math.min(80, cam3.dist * Math.pow(1.0015, e.deltaY))); render3d(); }, { passive: false });
v3.addEventListener('dblclick', () => { cam3.user = false; cam3.az = -2.25; cam3.el = 0.62; render3d(); });
v3.tabIndex = 0;
v3.addEventListener('keydown', (e) => { if (e.key === ' ') { e.preventDefault(); $('play').click(); } });
function setView(mode) {
  cam3.mode = mode;
  for (const b of document.querySelectorAll('#views button')) b.setAttribute('aria-pressed', String(b.dataset.view === mode));
  store.set('view', mode); render3d();
}
for (const b of document.querySelectorAll('#views button')) b.onclick = () => setView(b.dataset.view);

// ---------- player and chart ----------
function seek(t) {
  if (!state.sim) return;
  state.t = Math.max(0, Math.min(state.sim.duration_s, t));
  $('tslider').value = state.t; $('tnow').textContent = state.t.toFixed(1) + ' s';
  if (state.tab === 'map') draw();
  render3d(); drawChart();
}
const ch = $('chart'); const cctx = ch.getContext('2d');
function drawChart() {
  const dpr = window.devicePixelRatio || 1; const W = ch.clientWidth, H = ch.clientHeight;
  if (W < 10 || H < 10) return;
  ch.width = Math.round(W * dpr); ch.height = Math.round(H * dpr); cctx.setTransform(dpr, 0, 0, dpr, 0, 0); cctx.clearRect(0, 0, W, H);
  const r = state.sim; if (!r) { cctx.fillStyle = css('--muted'); cctx.font = '12px system-ui'; cctx.fillText('height and markers in view over time', 12, H / 2 + 4); return; }
  const T = Math.max(1, r.duration_s), tr = r.trace, z0 = tr.length ? tr[0][3] : 0; const zx = (t) => 34 + (W - 44) * t / T;
  const zmin = -0.1, zmax = 1.5, cmax = 6;
  const zy = (z) => H - 16 - (H - 26) * (z - zmin) / (zmax - zmin), cy = (c) => H - 16 - (H - 26) * Math.min(c, cmax) / cmax;
  cctx.strokeStyle = css('--grid'); cctx.fillStyle = css('--muted'); cctx.font = '10px system-ui';
  for (const z of [0, 0.5, 1.0]) { cctx.beginPath(); cctx.moveTo(34, zy(z)); cctx.lineTo(W - 10, zy(z)); cctx.stroke(); cctx.fillText(z.toFixed(1) + ' m', 2, zy(z) + 3); }
  for (const f of (r.preflight ? r.preflight.findings : [])) if (f.t !== null && f.t !== undefined && f.level !== 'info') {
    cctx.fillStyle = f.level === 'error' ? css('--err') : css('--warn'); cctx.fillRect(zx(f.t) - 1, 4, 2, H - 20);
  }
  cctx.lineWidth = 2; cctx.strokeStyle = css('--path'); cctx.beginPath(); tr.forEach((p, i) => i ? cctx.lineTo(zx(p[0]), zy(p[3] - z0)) : cctx.moveTo(zx(p[0]), zy(p[3] - z0))); cctx.stroke();
  cctx.lineWidth = 1.5; cctx.strokeStyle = '#ff9500'; cctx.beginPath(); tr.forEach((p, i) => i ? cctx.lineTo(zx(p[0]), cy(p[4])) : cctx.moveTo(zx(p[0]), cy(p[4]))); cctx.stroke();
  cctx.strokeStyle = css('--ink'); cctx.lineWidth = 1; cctx.beginPath(); cctx.moveTo(zx(state.t), 4); cctx.lineTo(zx(state.t), H - 12); cctx.stroke();
  cctx.fillStyle = css('--muted'); cctx.fillText('0', 34, H - 3); cctx.fillText(T.toFixed(0) + ' s', W - 34, H - 3);
}
ch.addEventListener('pointerdown', (e) => { if (!state.sim) return; const r = ch.getBoundingClientRect(); seek((e.clientX - r.left - 34) / (r.width - 44) * Math.max(1, state.sim.duration_s)); });
let last = null;
function frame(ts) {
  if (!state.playing || !state.sim) { last = null; return; }
  if (last !== null) { state.t += (ts - last) / 1000 * parseFloat($('speed').value); }
  last = ts;
  if (state.t >= state.sim.duration_s) { state.t = state.sim.duration_s; state.playing = false; $('play').textContent = '▶'; }
  seek(state.t);
  requestAnimationFrame(frame);
}
$('play').onclick = () => { if (!state.sim) return; state.playing = !state.playing; $('play').textContent = state.playing ? '❚❚' : '▶'; if (state.playing) { if (state.t >= state.sim.duration_s) state.t = 0; requestAnimationFrame(frame); } };
$('tslider').oninput = () => seek(parseFloat($('tslider').value));
function relayout() { state.view = null; draw(); drawChart(); render3d(); }
window.addEventListener('resize', relayout);
document.addEventListener('visibilitychange', relayout);
if (window.ResizeObserver) { const ro = new ResizeObserver(relayout); ro.observe(cv); ro.observe(v3); }
