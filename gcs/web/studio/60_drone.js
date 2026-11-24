// ---------- drone (copied unchanged from GCS 1.3.0 flight_template.html, except the one marked line) ----------
// ---------- drone: the mission server (6 commands, owner 17.11 «Да, 6 команд») ----------
// Standalone (a browser): fetch to the mission server typed in the address field.
// Embedded (the GCS app, WebView2): the page has no network to the drone at all -- every
// command goes to the app as a chrome.webview message {bb, id, cmd, body, since}; the app
// talks to the drone and shows its own «Взлёт?» dialog. The six paths are spelled out here
// so that gcs/tools/check_watch_only.py sees them.
const ROUTES = {
  map_status: ['GET', '/api/map/status'],
  map_put: ['POST', '/api/map'],
  mission_check: ['POST', '/api/mission/check'],
  mission_start: ['POST', '/api/mission/start'],
  mission_stop: ['POST', '/api/mission/stop'],
  mission_status: ['GET', '/api/mission/status'],
};
const hostBridge = (() => {
  if (!CONFIG.embedded) return null;
  const wv = window.chrome && window.chrome.webview;                 // the Windows app: WebView2
  const wk = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.bbflight;   // the Mac app: WKWebView
  let n = 0;
  const reply = (m) => ({ code: m.code | 0, data: (m.data && typeof m.data === 'object') ? m.data : {} });
  const silent = () => new Error('the app did not answer');
  if (wv) {
    const waiting = new Map();
    wv.addEventListener('message', (e) => {
      const m = e.data; if (!m || m.bb !== 1) return;
      const w = waiting.get(m.id); if (!w) return;
      waiting.delete(m.id); clearTimeout(w.timer);
      w.resolve(reply(m));
    });
    return (cmd, body, since, timeoutMs) => new Promise((resolve, reject) => {
      const id = ++n;
      const timer = setTimeout(() => { waiting.delete(id); reject(silent()); }, timeoutMs);
      waiting.set(id, { resolve, timer });
      wv.postMessage({ bb: 1, id, cmd, body: body === undefined ? null : body, since: since || 0 });
    });
  }
  if (wk) {
    // The message goes as JSON text and the answer comes back as JSON text (null: no answer).
    return (cmd, body, since, timeoutMs) => new Promise((resolve, reject) => {
      const id = ++n;
      const timer = setTimeout(() => reject(silent()), timeoutMs);
      wk.postMessage(JSON.stringify({ bb: 1, id, cmd, body: body === undefined ? null : body, since: since || 0 })).then((text) => {
        clearTimeout(timer);
        let m = null;
        try { m = typeof text === 'string' ? JSON.parse(text) : null; } catch (e) { m = null; }
        if (m && m.bb === 1 && m.id === id) resolve(reply(m)); else reject(silent());
      }, () => { clearTimeout(timer); reject(silent()); });
    });
  }
  return null;
})();
const drone = { url: '', ok: false, hostName: '', token: null, tokenUntil: 0, tokenProgram: '', since: 0, run: undefined, trail: [], statusTimer: null };
async function shaHex(text) {              // the same number the app shows in «Взлёт?»
  if (!(window.crypto && crypto.subtle)) return '';
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, '0')).join('');
}
function dmsg(level, text) { const ul = $('dronemsgs'); ul.innerHTML = ''; addMsg(ul, level, text); }
async function dcall(cmd, body, since) {
  // The app’s «Взлёт?» dialog waits for the person (it closes itself after a minute). Every other
  // command: the app gives the drone 12 s (Stop: three tries, 9 s), so the page waits a little longer.
  const timeoutMs = cmd === 'mission_start' ? 120000 : 15000;
  if (hostBridge) return hostBridge(cmd, body, since, timeoutMs);
  const [method, path] = ROUTES[cmd];
  const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const opt = { method, signal: ctl.signal };
    if (method === 'POST' && body !== undefined && body !== null) { opt.headers = { 'Content-Type': 'application/json' }; opt.body = JSON.stringify(body); }
    const r = await fetch(drone.url + path + (cmd === 'mission_status' ? '?since=' + (since || 0) : ''), opt);
    let data = {}; try { data = await r.json(); } catch (e) { /* empty body */ }
    return { code: r.status, data };
  } finally { clearTimeout(timer); }
}
function droneButtons() {
  $('sendmap').disabled = $('dronecheck').disabled = !drone.ok;
  const tokOk = drone.token && Date.now() < drone.tokenUntil && drone.tokenProgram === code.value;
  const boxes = $('c_battery').checked && $('c_rc').checked && $('c_people').checked;
  $('takeoff').disabled = !(drone.ok && tokOk && boxes);
  $('tokstate').textContent = tokOk ? 'permission valid for ' + Math.round((drone.tokenUntil - Date.now()) / 1000) + ' s more' : (drone.token ? 'permission expired or the program changed: check again' : '');
}
setInterval(droneButtons, 1000);
['c_battery', 'c_rc', 'c_people'].forEach(id => $(id).onchange = droneButtons);
async function droneConnect() {
  try {
    if (hostBridge) {
      const h = await hostBridge('hello', null, 0, 5000);
      if (h.code !== 200 || !h.data.connected) { drone.ok = false; $('srvstate').textContent = 'the app is not connected to a drone'; droneButtons(); return; }
      const nm = String(h.data.name || ''), ho = String(h.data.host || '');
      drone.hostName = nm && nm !== ho ? nm + ' (' + ho + ')' : ho;
    } else {
      drone.url = $('srv').value.trim().replace(/\/+$/, '');
    }
    const r = await dcall('map_status');
    drone.ok = r.code === 200;
    const a = r.data.active;
    const who = hostBridge ? 'drone ' + drone.hostName + ': ' : 'connected; ';
    $('srvstate').textContent = drone.ok
      ? who + 'on the drone ' + (a ? 'map "' + a.name + '", ' + a.n + ' markers, sha ' + String(a.sha).slice(0, 12) + (r.data.confirmed ? ', confirmed by the detector' : ', NOT confirmed by the detector') : 'no map')
      : (hostBridge ? 'drone ' + drone.hostName + ': ' : '') + (r.data.error || 'error ' + r.code);
  } catch (e) { drone.ok = false; $('srvstate').textContent = 'no connection: ' + e.message; }
  droneButtons();
  if (drone.ok) pollStatus();
}
$('srvconnect').onclick = droneConnect;
$('sendmap').onclick = async () => {
  if (!state.check || state.check.error || state.check.errors.length || state.fileErrors.length) { dmsg('error', 'Fix the map errors first.'); return; }
  try {
    const r = await dcall('map_put', { map: JSON.parse(mapJSON()) });
    if (r.code === 200 && r.data.accepted) dmsg('info', 'The drone accepted the map: ' + r.data.summary + '. The detector confirmed the same sha.');
    else dmsg('error', (r.data.error || 'error ' + r.code) + (r.data.check ? ': ' + r.data.check.errors.join('; ') : ''));
    droneConnect();
  } catch (e) { dmsg('error', 'no connection: ' + e.message); }
};
$('dronecheck').onclick = async () => {
  try {
    const prog = code.value;
    const r = await dcall('mission_check', { program: prog });
    if (r.code !== 200) { dmsg('error', r.data.error || 'error ' + r.code); return; }
    const ul = $('dronemsgs'); ul.innerHTML = '';
    for (const e of r.data.check.errors) addMsg(ul, 'error', e.text, e.line);
    for (const w of r.data.check.warnings) addMsg(ul, 'warn', w.text, w.line);
    if (r.data.error) addMsg(ul, 'error', r.data.error);
    if (r.data.token) {
      drone.token = r.data.token; drone.tokenProgram = prog; drone.tokenUntil = Date.now() + (r.data.token_ttl_s - 5) * 1000;
      const sha = await shaHex(prog);
      addMsg(ul, 'info', 'The drone checked the program' + (sha ? ' (sha ' + sha.slice(0, 12) + ')' : '') + '. Tick the three items and press “TAKEOFF…”.');
    }
    droneButtons();
  } catch (e) { dmsg('error', 'no connection: ' + e.message); }
};
let takeoffArmTimer = null;
$('takeoff').onclick = () => {
  if (hostBridge) { startMission(); return; }       // the app asks «Взлёт?» in its own window
  // standalone: the first click only shows the second, explicit button for 10 s
  $('takeoff2').hidden = false; $('takeoff').disabled = true;
  dmsg('warn', 'Really take off? Press “Yes, take off” within 10 s. RC in hand: CH8 stops.');
  clearTimeout(takeoffArmTimer); takeoffArmTimer = setTimeout(() => { $('takeoff2').hidden = true; droneButtons(); }, 10000);
};
$('takeoff2').onclick = () => { clearTimeout(takeoffArmTimer); $('takeoff2').hidden = true; startMission(); };
async function startMission() {
  const confirm = { battery_multimeter: $('c_battery').checked, rc_in_hand_ch8: $('c_rc').checked, people_clear: $('c_people').checked, takeoff_clicked: true };
  const tok = drone.token; drone.token = null;          // one token = one attempt
  if (hostBridge) dmsg('warn', 'Confirm the takeoff in the app’s window. RC in hand: CH8 stops.');
  try {
    const r = await dcall('mission_start', { program: code.value, token: tok, confirm });
    if (r.code === 200) {
      dmsg('info', 'Mission started (' + r.data.run + '). STOP is always available.');
      drone.trail = []; drone.since = 0; drone.run = r.data.run || null; $('liveevents').innerHTML = '';
      ['c_battery', 'c_rc', 'c_people'].forEach(id => { $(id).checked = false; });   // every takeoff: confirm again
    } else dmsg('error', r.data.error || 'error ' + r.code);
  } catch (e) { dmsg('error', 'no connection: ' + e.message); }
  droneButtons();
}
$('dronestop').onclick = async () => {    // always: no token, no checks
  if (!hostBridge) drone.url = ($('srv').value.trim() || drone.url).replace(/\/+$/, '');
  try {
    const r = await dcall('mission_stop');
    if (r.code === 200) dmsg('warn', 'STOP sent.');
    else dmsg('error', 'STOP: ' + (r.data.error || 'error ' + r.code) + '. Stop with the RC (CH8).');
  } catch (e) { dmsg('error', 'STOP did not get through: ' + e.message + '. Stop with the RC (CH8).'); }
};
let pollGen = 0;
function pollStatus() {
  clearTimeout(drone.statusTimer);
  const gen = ++pollGen;                 // a second «Подключиться» must not start a second loop
  const tick = async () => {
    if (!drone.ok || gen !== pollGen) return;
    try {
      const r = await dcall('mission_status', undefined, drone.since);
      if (r.code === 200) {
        const ev = $('liveevents');
        // Another run than the one shown (started from another PC, or the server restarted):
        // its events are numbered from zero again, so start over.
        const run = r.data.run || null, known = drone.run !== undefined;
        const lastSeq = typeof r.data.last_seq === 'number' ? r.data.last_seq : Infinity;
        if (run !== drone.run || lastSeq < drone.since) {
          drone.run = run;
          if (known || drone.since > 0) { drone.since = 0; drone.trail = []; ev.innerHTML = ''; draw(); r.data.events = []; }
        }
        for (const e of (r.data.events || [])) {
          drone.since = Math.max(drone.since, e.seq || 0);
          if (e.type === 'pos') { drone.trail.push(e); if (drone.trail.length > 3000) drone.trail.shift(); }
          else if (e.type === 'event') addMsg(ev, e.level, (e.t !== undefined ? e.t.toFixed(1) + ' s: ' : '') + e.text, e.line);
          else if (e.type === 'end') addMsg(ev, e.ok ? 'info' : 'error', 'End: ' + e.reason);
          else if (e.type === 'preflight') addMsg(ev, 'info', 'Pre-flight check passed (map ' + String(e.map_sha).slice(0, 12) + ')');
          else if (e.type === 'log') addMsg(ev, 'info', (e.t !== undefined ? e.t.toFixed(1) + ' s: ' : '') + e.text);
        }
        if ((r.data.events || []).length) { draw(); render3d(); }      // 1.4: the live drone is also drawn in 3D
      }
    } catch (e) { /* keep polling */ }
    if (gen === pollGen) drone.statusTimer = setTimeout(tick, 500);
  };
  tick();
}
if (CONFIG.embedded) {                   // inside the app: the app knows the drone, no address to type
  $('srv').hidden = true; $('srvlabel').hidden = true; $('srvconnect').textContent = 'Refresh';
  $('takeoff').textContent = 'TAKEOFF (the app will ask)';
  setTimeout(droneConnect, 500);
}
