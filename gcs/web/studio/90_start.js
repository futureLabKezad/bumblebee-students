// ---------- start ----------
{ const saved = store.get('program'); code.value = (saved && saved.trim()) ? saved : EXAMPLES[Object.keys(EXAMPLES)[0]]; }
$('live').checked = store.get('live') !== '0';
{ const u = store.get('units'); if (u === 'm' || u === 'cm') $('units').value = u; }
$('mapname').value = state.map.name;
renderApiList();
applyTheme(store.get('theme') || DEFAULT_THEME);
{ const v = store.get('view'); setView(['free', 'top', 'side', 'follow'].includes(v) ? v : 'free'); }
showTab(['program', 'map', 'drone'].includes(store.get('tab')) ? store.get('tab') : 'program');
renderTable(); renderEditor(); updateSig(); syncTakeoff(); updateFieldNote(); updateMeasure(); updateSimGate();
draw(); render3d(); drawChart();
startPython();
