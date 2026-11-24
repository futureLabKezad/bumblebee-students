// ---------- check, simulate, pre-flight list, console ----------
$('btncheck').onclick = async () => {
  const ul = $('codemsgs'); ul.innerHTML = '';
  let r; try { r = await api('check_code_hints', [code.value], 15000); } catch (e) { addMsg(ul, 'error', e.message); return; }
  state.lint = r; renderEditor();
  for (const e of r.errors) addMsg(ul, 'error', e.text, e.line, e.fix);
  for (const w of r.warnings) addMsg(ul, 'warn', w.text, w.line, w.fix);
  if (r.ok) addMsg(ul, 'info', 'Code check passed. Commands: ' + r.used.join(', '));
};
// The drone's time guard: bb_mission starts every mission with budget 300 s (guards.LIMITS, the
// page sends no budget). The simulation uses the same number; it is not adjustable (review 24.11, K1).
const DRONE_BUDGET_S = 300;
const SIM_TIMEOUT_MS = 30000;      // a stuck program (endless loop, one huge line) is killed after 30 s
async function runSim(auto) {
  const ul = $('codemsgs');
  if (!state.ready) { if (!auto) { ul.innerHTML = ''; addMsg(ul, 'error', 'Python is not ready yet'); } return; }
  if (state.busy) { if (auto) autoSimSoon(800); else state.wantSim = true; return; }
  // review 24.11, d4: a live run shows Stop and its status only if it takes longer than 1.5 s
  const busyNote = setTimeout(() => { if (state.busy) { $('btnstop').hidden = false; setStatus(auto ? 'live: simulating…' : 'simulating…'); } }, auto ? 1500 : 0);
  $('btnsim').disabled = !auto; state.busy = true; state.stopReason = '';
  const prog = code.value, mapText = mapJSON(), cam = $('cam').value || 'gazebo';
  try {
    const r = await api('studio', [prog, mapText, cam, JSON.stringify({ time_budget_s: DRONE_BUDGET_S })], SIM_TIMEOUT_MS);
    if (r.error) { ul.innerHTML = ''; addMsg(ul, 'error', r.error); }
    else if (prog === code.value && mapText === mapJSON() && cam === ($('cam').value || 'gazebo')) { r.program = prog; r.mapText = mapText; r.camName = cam; showSim(r); }
    else {
      // review 24.11, M1: the program, the map or the camera changed while it ran -- its result is not shown
      // as fresh (also for a manual run); simulate the current one instead
      if ($('live').checked) autoSimSoon(200); else { ul.innerHTML = ''; addMsg(ul, 'warn', 'The program or the map changed during the simulation. Press ▶ Simulate again.'); }
    }
  } catch (e) {
    ul.innerHTML = '';
    if (state.stopReason === 'user') addMsg(ul, 'info', 'Simulation stopped.');   // review 24.11, m3
    else {
      addMsg(ul, 'error', 'Simulation stopped: ' + e.message + '. Looks like an endless loop or a very long computation.', 0, 'Give every loop an end (for i in range(...), or a break).');
      if (auto) { $('live').checked = false; addMsg(ul, 'warn', 'Live simulation is switched off until you press ▶ Simulate.'); }
    }
  }
  clearTimeout(busyNote);
  state.busy = false;
  $('btnsim').disabled = false; $('btnstop').hidden = true;
  if (state.ready) setStatus('Python ready');
  if (state.wantSim) { state.wantSim = false; runSim(false); }      // Simulate was pressed during a live run
}
$('btnsim').onclick = () => runSim(false);
// Live: simulate again by itself a moment after the program or the map changed (owner 24.11:
// «прогаешь и сразу видно в 3д твой полёт»). A program the code check refuses is not simulated.
let autoTimer = null;
function autoSimSoon(ms) {
  clearTimeout(autoTimer);
  if (!$('live').checked) return;
  autoTimer = setTimeout(() => runSim(true), ms === undefined ? 1200 : ms);   // with code errors it only lists them (fast)
}
$('live').onchange = () => { store.set('live', $('live').checked ? '1' : '0'); if ($('live').checked) autoSimSoon(100); };
$('btnstop').onclick = () => { state.stopReason = 'user'; restartPython('stopped with the Stop button'); };
const VERDICT = {
  ready: ['Ready: no problems found in the simulation.', 'The real drone can still differ: wind, light on the markers, battery.'],
  check: ['Check the warnings before flying.', 'The drone will fly this program, but something may go wrong. Each warning below says how to fix it.'],
  not_ready: ['Not ready: fix the errors first.', 'The drone would refuse a command or land early.'],
};
function showSim(r) {
  const ul = $('codemsgs'); ul.innerHTML = '';
  state.lint = r.check; renderEditor();
  const pf = r.preflight || { verdict: r.check.ok ? 'ready' : 'not_ready', findings: [], stats: {} };
  const v = $('verdict'); v.hidden = false; v.className = pf.verdict; v.textContent = ''; delete v.dataset.stale;
  const nE = pf.findings.filter(f => f.level === 'error').length, nW = pf.findings.filter(f => f.level === 'warn').length;
  v.append(document.createTextNode(VERDICT[pf.verdict][0] + ' '), Object.assign(document.createElement('small'), { textContent: nE + ' errors, ' + nW + ' warnings. ' + VERDICT[pf.verdict][1]
    + ' The simulation uses the same limits as the mission server on the drone (bb_mission 0.2.0).' }));
  $('preempty').hidden = true;
  const cnt = pf.findings.filter(f => f.level !== 'info').length;
  document.querySelector('#outtabs button[data-out="problems"]').textContent = 'Pre-flight check' + (cnt ? ' (' + cnt + ')' : '');
  const box = $('findings'); box.innerHTML = '';
  for (const f of pf.findings) box.appendChild(findingItem(f));
  if (!r.ran) { $('simbox').hidden = true; state.sim = null; renderConsole(r); draw(); render3d(); drawChart(); updateSimGate(); return; }
  state.sim = r; state.t = 0; $('simbox').hidden = false;
  const errs = r.events.filter(e => e.level === 'error').length, warns = r.events.filter(e => e.level === 'warn').length;
  $('simkv').innerHTML = '';
  const st = pf.stats || {};
  const kv = [['result', r.ok ? 'no errors' : 'errors'], ['time', r.duration_s + ' s'], ['in the air', r.flight_s + ' s'], ['in the red zone', r.red_zone_s + ' s'],
              ['errors', errs], ['warnings', warns], ['end', r.end_reason], ['guard landed', r.landed_by_guard ? 'yes' : 'no'],
              ['highest', st.max_height_m !== undefined ? fmt(st.max_height_m, 2) + ' m' : '—'], ['path', st.path_m !== undefined ? fmt(st.path_m, 1) + ' m' : '—'],
              ['rangefinder', st.rangefinder_m !== undefined ? '≈' + fmt(st.rangefinder_m, 2) + ' m' : '—'], ['to the border', st.edge_m !== undefined && st.edge_m !== null ? fmt(st.edge_m * 100, 0) + ' cm' : '—']];
  for (const [k, val] of kv) { const a = document.createElement('span'); a.textContent = k; const b = document.createElement('b'); b.textContent = val; $('simkv').append(a, b); }
  if (st.battery) { const p = document.createElement('p'); p.className = 'note'; p.style.gridColumn = '1 / -1'; p.textContent = 'Battery: ' + st.battery; $('simkv').appendChild(p); }
  const ev = $('simevents'); ev.innerHTML = '';
  for (const e of r.events) addMsg(ev, e.level, e.t.toFixed(1) + ' s: ' + e.text, e.line);
  $('simlog').textContent = r.log.map(l => l.t.toFixed(1).padStart(6) + '  ' + l.text).join('\n');
  $('tslider').max = r.duration_s; $('tslider').value = 0; $('tnow').textContent = '0.0 s';
  renderConsole(r);
  if (cam3.mode === 'follow') setView('follow');
  seek(0); draw(); updateSimGate();
}
function findingItem(f) {
  const li = document.createElement('li'); li.className = f.level; f._li = li;
  const tt = document.createElement('div'); tt.className = 'tt'; tt.textContent = f.title;
  if (f.line) { const a = document.createElement('button'); a.className = 'ghost go'; a.textContent = 'line ' + f.line; a.onclick = () => { showTab('program'); gotoLine(f.line); }; tt.appendChild(a); }
  if (f.t !== null && f.t !== undefined) { const a = document.createElement('button'); a.className = 'ghost go'; a.textContent = 'at ' + f.t.toFixed(1) + ' s'; a.onclick = () => { seek(f.t); }; tt.appendChild(a); }
  li.appendChild(tt);
  if (f.why) { const d = document.createElement('div'); d.className = 'why'; d.textContent = f.why; li.appendChild(d); }
  if (f.fix) { const d = document.createElement('div'); d.className = 'fix'; d.textContent = f.fix; li.appendChild(d); }
  return li;
}
function highlightFinding(f) {
  showTab('program'); showOut('problems');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const li = f._li || [...$('findings').children].find(x => x.textContent.startsWith(f.title));
  if (li) { li.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' }); if (!reduce) li.animate([{ outline: '3px solid ' + css('--accent') }, { outline: '3px solid transparent' }], { duration: 1400 }); }
}
function renderConsole(r) {
  const con = $('console'); con.textContent = '';
  const rows = [];
  for (const l of (r.log || [])) rows.push([l.t, /^===/.test(l.text) ? 'cmd' : '', l.text]);
  for (const e of (r.events || [])) rows.push([e.t, e.level === 'info' ? '' : e.level, (e.level === 'info' ? '• ' : (e.level === 'error' ? '✖ ' : '▲ ')) + e.text + (e.line ? '  (line ' + e.line + ')' : '')]);
  rows.sort((a, b) => a[0] - b[0]);
  if (!r.ran) rows.push([0, 'error', 'The program did not run: fix the code errors above.']);
  for (const [t, cls, text] of rows) {
    const tt = document.createElement('span'); tt.className = 'c-t'; tt.textContent = (t || 0).toFixed(1).padStart(6) + ' s  ';
    const tx = document.createElement('span'); if (cls) tx.className = 'c-' + cls; tx.textContent = text;
    con.append(tt, tx, document.createTextNode('\n'));
  }
  if (r.ran) { const tx = document.createElement('span'); tx.className = 'c-t'; tx.textContent = '   end: ' + r.end_reason + ', ' + r.duration_s + ' s'; con.appendChild(tx); }
}
$('clearcon').onclick = () => { $('console').textContent = ''; };
function showOut(name) {
  for (const b of document.querySelectorAll('#outtabs button')) b.setAttribute('aria-pressed', String(b.dataset.out === name));
  $('out-problems').hidden = name !== 'problems'; $('out-console').hidden = name !== 'console'; $('clearcon').hidden = name !== 'console';
}
for (const b of document.querySelectorAll('#outtabs button')) b.onclick = () => showOut(b.dataset.out);
function showStale() {
  const v = $('verdict'); if (v.hidden || v.dataset.stale) return;
  v.dataset.stale = '1';
  v.appendChild(Object.assign(document.createElement('small'), { textContent: '  The program changed: simulate again.' }));
  updateSimGate();
}
function showSimGone() {
  const v = $('verdict'); if (v.hidden) return;
  v.className = 'check'; v.textContent = $('live').checked ? 'The map changed: simulating again…' : 'The map changed: simulate again.';
  $('findings').innerHTML = ''; $('simbox').hidden = true; state.t = 0; state.playing = false; $('play').textContent = '▶';
  $('tslider').value = 0; $('tnow').textContent = '0.0 s'; drawChart(); updateSimGate();
}
// The Drone tab says whether the program on screen was simulated without errors. It does not block:
// the drone checks the program itself (its own code check and guards) before «Взлёт?».
function updateSimGate() {
  const g = $('simgate'), r = state.sim;
  const fresh = r && !r.stale && r.program === code.value && r.mapText === mapJSON() && r.camName === ($('cam').value || 'gazebo');
  if (!fresh) { g.textContent = 'This program has not been simulated with the current map. Simulate it in the Program tab first.'; g.className = 'note warnnote'; return; }
  const v = r.preflight ? r.preflight.verdict : (r.ok ? 'ready' : 'not_ready');
  g.textContent = v === 'ready' ? 'Simulated: no problems found.' : (v === 'check' ? 'Simulated with warnings: read them in the Program tab before flying.' : 'The simulation found errors: fix them before sending the program.');
  g.className = v === 'not_ready' ? 'note warnnote' : 'note';
}
