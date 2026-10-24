const $ = (id) => document.getElementById(id);
const videos = [$('video0'), $('video1')];
const overlays = [$('overlay0'), $('overlay1')];
let session = null;
let authoritative = null;
let selected = null;
let time = 0;
let playing = false;
let rate = 1;
let lastTick = performance.now();
let cropCamera = 0;
let cropCenter = null;
let sceneView = null;
let loadGeneration = 0;
let actionBusy = false;
let loading = false;
let reached = new Set();
let sourceStamps = [null, null];
let lastAdvance = -1;
let advancing = false;
let advanceSupported = true;
let toastTimer;
const originalCrop = document.createElement('video');
originalCrop.id = 'originalCropSource'; originalCrop.hidden = true; document.body.append(originalCrop);
originalCrop.muted = true; originalCrop.playsInline = true; originalCrop.preload = 'metadata';
let originalCamera = -1;
let originalSeekTimer;
function dataset() { return isSynthetic() ? 'synthetic' : 'recorded'; }
function teamName(id) { return id === 'A' ? $('nameA').textContent : id === 'B' ? $('nameB').textContent : id ?? 'player'; }

function number(value, fallback = 0) { return Number.isFinite(Number(value)) ? Number(value) : fallback; }
function duration() { return Math.max(0, number(session?.duration_s ?? session?.duration)); }
function clamp(value, min, max) { return Math.max(min, Math.min(max, value)); }
function format(value, decimals = 2) {
  const n = Math.max(0, number(value));
  return `${Math.floor(n / 60)}:${(n % 60).toFixed(decimals).padStart(decimals ? decimals + 3 : 2, '0')}`;
}
function pretty(value) { return String(value ?? '').replaceAll('_', ' '); }
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function toast(message) {
  document.querySelector('.toast')?.remove();
  const box = document.createElement('div'); box.className = 'toast'; box.setAttribute('role', 'status'); box.textContent = message;
  document.body.append(box); clearTimeout(toastTimer); toastTimer = setTimeout(() => box.remove(), 4500);
}
async function api(path, body) {
  const response = await fetch(path, body === undefined ? {cache: 'no-store'} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  if (!response.ok) {
    let reason = `${response.status} ${response.statusText}`;
    try { const result = await response.json(); reason = result.error ?? result.detail ?? reason; } catch { /* retain HTTP status */ }
    const error = new Error(typeof reason === 'string' ? reason : JSON.stringify(reason)); error.status = response.status; throw error;
  }
  return response.json();
}
function isSynthetic() { return $('sessionMode').value === 'synthetic' || session?.synthetic === true; }
function cameras() { return session?.cameras ?? []; }
function sourceTime(index, game = time) {
  const camera = cameras()[index] ?? {};
  return game * number(camera.drift, 1) + number(camera.offset_s);
}
function gameTime(index, source) {
  const camera = cameras()[index] ?? {};
  return (source - number(camera.offset_s)) / number(camera.drift, 1);
}
function cameraRows(index) { return cameras()[index]?.frames ?? []; }
function rowTime(row) { return number(row.t_source_s ?? row.timestamp_seconds ?? row.t_s); }
function nearestRow(index, stamp = videos[index].currentTime) {
  const rows = cameraRows(index); if (!rows.length) return null;
  let low = 0, high = rows.length - 1;
  while (low < high) { const middle = (low + high) >> 1; if (rowTime(rows[middle]) < stamp) low = middle + 1; else high = middle; }
  if (low > 0 && Math.abs(rowTime(rows[low - 1]) - stamp) < Math.abs(rowTime(rows[low]) - stamp)) low--;
  const row = rows[low];
  // No marker is carried through missing frames or across distant timestamps.
  const maxGap = 1.6 / number(cameras()[index]?.fps, 60);
  return Math.abs(rowTime(row) - stamp) <= maxGap ? {...row, _index: low} : null;
}
function hasPosition(row) { return row && row.x !== null && row.y !== null && Number.isFinite(row.x) && Number.isFinite(row.y); }
function getPoint() { return (session?.points ?? []).find((point) => point.id === selected); }
function currentResolution(point) {
  const current = authoritative?.calls?.find((call) => call.rally_id === point?.id);
  if (current && ['point','let'].includes(current.status)) return current;
  const history = authoritative?.history ?? [];
  for (let i = history.length - 1; i >= 0; i--) if ((history[i].rally_id ?? history[i].point_id) === point?.id && ['point','let'].includes(history[i].status ?? history[i].kind)) return history[i];
  return null;
}
function speak(text) {
  if (!$('voice').checked || !('speechSynthesis' in window) || !text) return;
  speechSynthesis.cancel(); const utterance = new SpeechSynthesisUtterance(text); utterance.rate = 1; speechSynthesis.speak(utterance);
}
function updateScore(state, announce = false) {
  if (!state) return;
  const previous = authoritative;
  authoritative = state.state ?? state;
  const points = authoritative.points ?? authoritative.score ?? {A: 0, B: 0};
  $('scoreA').textContent = points.A ?? 0; $('scoreB').textContent = points.B ?? 0;
  $('games').textContent = `GAMES ${authoritative.games?.A ?? 0} — ${authoritative.games?.B ?? 0}`;
  const server = authoritative.server ?? authoritative.server_team_id;
  $('serveA').hidden = server !== 'A'; $('serveB').hidden = server !== 'B';
  const history = authoritative.history ?? [];
  $('historyCount').textContent = `${history.length} EVENT${history.length === 1 ? '' : 'S'}`;
  $('history').replaceChildren();
  for (const entry of [...history].reverse()) {
    const li = document.createElement('li'); const title = document.createElement('strong');
    const winner = entry.winner ?? entry.winner_team_id;
    title.textContent = entry.speech ?? entry.summary ?? `${pretty(entry.status ?? entry.kind ?? 'Decision')}${winner ? ` · ${winner}` : ''}`;
    li.append(title, document.createTextNode(entry.reason ?? entry.explanation ?? entry.rally_id ?? 'Audited referee event'));
    $('history').append(li);
  }
  const latest = history.at(-1);
  if (announce && (history.length > (previous?.history?.length ?? 0) || JSON.stringify(points) !== JSON.stringify(previous?.points))) {
    speak(latest?.speech ?? ((latest?.status ?? latest?.kind) === 'let' ? 'Let. Replay the point.' : latest?.winner ? `Point to ${teamName(latest.winner)}. ${points.A} to ${points.B}.` : 'Decision recorded.'));
  }
  $('scoreOrigin').textContent = isSynthetic() ? 'SYNTHETIC · separate fixture referee state' : authoritative.match_winner ? `Match winner: ${authoritative.match_winner}` : history.length ? 'Authoritative referee state · audited decisions' : 'Recorded demo · initial score 0–0';
  renderPoints(); renderDecision();
}
function renderPoints() {
  const points = session?.points ?? []; $('pointCount').textContent = `${points.length} ${isSynthetic() ? 'test cases' : 'candidate rallies'}`;
  $('pointList').replaceChildren(); $('pointMarks').replaceChildren();
  if (!points.length) {
    const empty = document.createElement('div'); empty.className = 'empty-points';
    empty.textContent = 'No supported rally boundaries have been exported yet. Both views and manual frame inspection remain available.';
    $('pointList').append(empty);
  }
  for (const [i, point] of points.entries()) {
    const resolution = currentResolution(point);
    const resolved = !!resolution || ['resolved', 'validated', 'point', 'let', 'manual'].includes(point.status);
    const button = document.createElement('button'); button.className = `point-item${selected === point.id ? ' active' : ''}${resolved ? ' resolved' : ''}`;
    button.setAttribute('aria-pressed', String(selected === point.id));
    const top = document.createElement('span'); top.className = 'point-top';
    const label = document.createElement('span'); label.textContent = point.label ?? `${isSynthetic() ? 'Case' : 'Point'} ${String(i + 1).padStart(2, '0')}`;
    const symbol = document.createElement('span'); symbol.className = 'tiny'; symbol.textContent = selected === point.id ? '↗' : '↗'; top.append(label, symbol);
    const stamp = document.createElement('span'); stamp.className = 'point-time'; stamp.textContent = `${format(point.start_s, 1)} — ${format(point.end_s, 1)}`;
    const status = document.createElement('span'); status.className = 'point-state';
    const winner = resolution?.winner ?? point.winner;
    status.textContent = isSynthetic() && !resolution ? ({toss_fault_supported:'KNOWN TOSS FAULT',toss_checks_pass:'TOSS CHECKS PASS',review_needed:'UNCERTAIN',unavailable:'MISSING EVIDENCE'}[point.assessment?.status] ?? 'SYNTHETIC INPUT') : resolution ? ((resolution.status ?? resolution.kind) === 'let' ? 'LET · MANUAL' : `${winner ?? ''} · ${resolution.source === 'validated_evidence' ? 'SUPPORTED' : 'MANUAL'}`) : resolved ? pretty(point.status).toUpperCase() : 'REVIEW NEEDED';
    button.append(top, stamp, status); button.onclick = () => selectPoint(point.id, true); $('pointList').append(button);
    const mark = document.createElement('span'); mark.className = `point-mark${selected === point.id ? ' active' : ''}${resolved ? ' resolved' : ''}`;
    mark.style.left = `${100 * number(point.start_s) / Math.max(.01, duration())}%`; mark.style.width = `${Math.max(.25, 100 * (number(point.end_s) - number(point.start_s)) / Math.max(.01, duration()))}%`;
    $('pointMarks').append(mark);
  }
}
function renderDecision() {
  const point = getPoint();
  for (const id of ['evidence', 'challenge']) $(id).disabled = !point;
  document.querySelectorAll('[data-winner]').forEach((button) => button.disabled = !point || actionBusy || isSynthetic());
  $('resolutionReason').disabled = !point || isSynthetic();
  $('measurement').hidden = true;
  if (!point) {
    $('decisionStatus').textContent = 'PLAYERS DECIDE'; $('decisionStatus').className = 'status-pill pending';
    $('decisionTitle').textContent = 'Select a point.'; $('decisionReason').textContent = 'Review the original views and the evidence behind each candidate rally.'; return;
  }
  const resolution = currentResolution(point);
  const winner = resolution?.winner ?? point.winner;
  const synthetic = isSynthetic();
  let heading = 'Review needed.';
  if (resolution) heading = (resolution.status ?? resolution.kind) === 'let' ? 'Let. Play again.' : `Point to ${teamName(winner)}.`;
  else if (point.kind === 'serve' || point.kind === 'serve_toss') heading = 'Inspect the toss.';
  else if (point.kind === 'edge') heading = 'Edge or side?';
  if (synthetic && !resolution && point.assessment?.status === 'toss_fault_supported') heading = point.assessment.height === 'fail' ? 'Toss below 16 cm.' : 'Toss beyond 30°.';
  if (synthetic && !resolution && point.assessment?.status === 'toss_checks_pass') heading = 'Toss checks pass.';
  if (point.title) heading = point.title;
  $('decisionTitle').textContent = heading;
  $('decisionReason').textContent = resolution?.reason ?? point.reason ?? 'The recording does not yet establish a supported point outcome.';
  $('decisionStatus').textContent = synthetic ? 'SYNTHETIC TEST CASE' : resolution ? (resolution.source === 'validated_evidence' ? 'SUPPORTED DECISION' : 'MANUALLY RESOLVED') : 'PLAYERS DECIDE';
  $('decisionStatus').className = `status-pill ${synthetic ? 'synthetic' : resolution ? 'resolved' : 'pending'}`;
  const reference = resolution?.rule_refs ?? resolution?.rule_ref ?? resolution?.rule_id ?? point.rule_ref ?? point.rule_id;
  $('ruleRef').textContent = reference ? `${Array.isArray(reference) ? reference.join(' · ') : reference} · ITTF 2026 profile` : 'ITTF 2.5 / 2.10 · insufficient evidence remains unresolved';
  const measurement = point.measurement ?? point.measurements ?? point.toss;
  if (measurement && typeof measurement === 'object') {
    $('measurement').replaceChildren(); $('measurement').hidden = false;
    for (const [key, value] of Object.entries(measurement)) {
      if (value === null || (typeof value === 'object' && !Array.isArray(value)) || typeof value === 'boolean') continue;
      const line = document.createElement('p'); line.textContent = `${pretty(key)}: ${Array.isArray(value) ? value.map((v) => Number(number(v).toFixed(4))).join(' — ') : typeof value === 'number' ? Number(value.toFixed(4)) : value}`; $('measurement').append(line);
    }
    if (synthetic) { const note = document.createElement('p'); note.textContent = 'Known synthetic input. This is not accuracy measured on your recordings.'; $('measurement').append(note); }
  }
  $('timelineHint').textContent = `Candidate in play ${format(point.start_s)}–${format(point.end_s)} · clip padding is separate`;
}
function selectPoint(id, doSeek = false) {
  selected = id; $('reviewDetails').hidden = true; cropCenter = null;
  renderPoints(); renderDecision();
  const point = getPoint(); if (doSeek && point) seek(Math.max(0, number(point.start_s) - .5));
}
function pause() { playing = false; requestOriginalCrop(); videos.forEach((video) => video.pause()); $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play both views'); }
async function play() {
  if (loading || !session || !duration()) return;
  if (time >= duration() - .02) seek(0);
  playing = true; $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause both views');
  syncVideos(true);
  const results = await Promise.allSettled(videos.map((video, index) => cameras()[index]?.url ? video.play() : Promise.resolve()));
  if (results.some((result) => result.status === 'rejected')) { pause(); toast('Playback needs another click, or the source video is unavailable.'); }
}
function seek(value) {
  time = clamp(number(value), 0, duration()); sourceStamps = [null, null]; syncVideos(true); updateClock(); drawSources(); sceneView?.draw(time, getPoint()); requestOriginalCrop();
}
function syncVideos(force = false) {
  videos.forEach((video, index) => {
    const camera = cameras()[index]; if (!camera?.url || video.readyState === 0) return;
    const rawTarget = sourceTime(index); const available = rawTarget >= 0 && (!Number.isFinite(video.duration) || rawTarget <= video.duration + .02);
    const target = clamp(rawTarget, 0, Number.isFinite(video.duration) ? Math.max(0, video.duration - .001) : Infinity);
    const error = target - video.currentTime;
    if (force || (index > 0 && Math.abs(error) > .1)) {
      if (!video.seeking && Math.abs(error) > .002) video.currentTime = target;
    }
    const base = rate * number(camera.drift, 1);
    video.playbackRate = clamp(base + (index > 0 && playing && Math.abs(error) <= .1 ? error * .5 : 0), .0625, 16);
    if (!available) { video.pause(); $('empty' + index).hidden = false; $('empty' + index).textContent = 'Outside this recording’s coverage'; }
    else if ($('empty' + index).textContent === 'Outside this recording’s coverage') { $('empty' + index).hidden = true; if (playing) video.play().catch(() => {}); }
  });
}
function updateClock() {
  $('clock').replaceChildren(document.createTextNode(format(time) + ' ')); const span = document.createElement('small'); span.textContent = `/ ${format(duration())}`; $('clock').append(span);
  $('timeline').value = String(time);
}
function sourceSize(index) { return [videos[index].videoWidth || number(cameras()[index]?.width, 1920), videos[index].videoHeight || number(cameras()[index]?.height, 1080)]; }
function rowXY(row, index, dimensions = sourceSize(index)) {
  const source = row.source_size ?? [number(cameras()[index]?.width, dimensions[0]), number(cameras()[index]?.height, dimensions[1])];
  return [row.x * dimensions[0] / source[0], row.y * dimensions[1] / source[1]];
}
function requestOriginalCrop() {
  clearTimeout(originalSeekTimer);
  if (playing || isSynthetic() || !cameras()[cropCamera]?.original_url) return;
  originalSeekTimer = setTimeout(() => {
    const url = cameras()[cropCamera]?.original_url; if (!url) return;
    if (originalCamera !== cropCamera) { originalCamera = cropCamera; originalCrop.src = url; originalCrop.load(); }
    else if (originalCrop.readyState >= 1 && !originalCrop.seeking) originalCrop.currentTime = clamp(sourceTime(cropCamera), 0, Math.max(0, originalCrop.duration - .001));
  }, 120);
}
originalCrop.addEventListener('loadedmetadata', () => { if (!playing && originalCamera === cropCamera) originalCrop.currentTime = clamp(sourceTime(cropCamera), 0, Math.max(0, originalCrop.duration - .001)); });
originalCrop.addEventListener('seeked', () => drawCrop());
function syntheticView(canvas, index) {
  const ctx = canvas.getContext('2d'); const width = 960, height = 540; if (canvas.width !== width) { canvas.width = width; canvas.height = height; }
  ctx.clearRect(0, 0, width, height); const point = getPoint();
  ctx.fillStyle = '#0c1a23'; ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = '#203d4c'; ctx.lineWidth = 1;
  for (let x = 0; x < width; x += 45) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); }
  for (let y = 0; y < height; y += 45) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); }
  const measure = point?.measurement ?? point?.measurements ?? point?.toss ?? {};
  const heightM = number(measure.height_m ?? measure.rise_m ?? point?.height_m, 0);
  const angle = number(measure.angle_deg ?? measure.rise_angle_deg ?? point?.rise_angle_deg ?? point?.angle_deg, 0);
  const localTime = time - number(point?.start_s);
  const progress = clamp(localTime - .5, 0, 1);
  const phase = 4 * progress * (1 - progress);
  const pxPerM = 950; const origin = [width * .4, height * .8];
  ctx.strokeStyle = '#5c9199'; ctx.setLineDash([5, 5]); ctx.beginPath(); ctx.moveTo(origin[0], 75); ctx.lineTo(origin[0], origin[1]); ctx.stroke();
  ctx.strokeStyle = '#e6bb7c'; ctx.beginPath(); ctx.moveTo(origin[0] - 115, origin[1] - .16 * pxPerM); ctx.lineTo(origin[0] + 230, origin[1] - .16 * pxPerM); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = '#e6bb7c'; ctx.font = '18px system-ui'; ctx.fillText('0.16 m minimum rise', origin[0] + 120, origin[1] - .16 * pxPerM - 12);
  ctx.strokeStyle = '#7ee7de'; ctx.lineWidth = 3; ctx.beginPath();
  for (let j = 0; j <= 50; j++) { const u = j / 50; const y = 4*u*(1-u) * heightM * pxPerM; const x = Math.min(1,u*2) * Math.tan(angle * Math.PI / 180) * heightM * pxPerM; j ? ctx.lineTo(origin[0] + x, origin[1] - y) : ctx.moveTo(origin[0] + x, origin[1] - y); } if (heightM > 0) ctx.stroke();
  const x = origin[0] + Math.min(1,progress*2) * Math.tan(angle * Math.PI / 180) * heightM * pxPerM; const y = origin[1] - phase * heightM * pxPerM;
  if (heightM > 0 && localTime >= .5 && localTime <= 1.5) { ctx.fillStyle = '#ffca7d'; ctx.beginPath(); ctx.arc(x, y, 9, 0, 2 * Math.PI); ctx.fill(); }
  ctx.fillStyle = '#d5ecee'; ctx.font = '23px system-ui'; ctx.fillText('SYNTHETIC / KNOWN INPUT', 36, 45);
  ctx.fillStyle = '#8faeba'; ctx.font = '17px system-ui'; ctx.fillText(index ? 'Rule boundary visualization · not a camera view' : point?.label ?? 'Threshold fixture · not recorded footage', 36, 77);
}
function drawSources() {
  cameras().slice(0, 2).forEach((camera, index) => {
    const video = videos[index]; const canvas = overlays[index];
    if (!camera.url && isSynthetic()) { syntheticView(canvas, index); $('frameReadout' + index).textContent = `Synthetic time ${time.toFixed(3)} s · known fixture, no observed source frame`; return; }
    const [width, height] = sourceSize(index);
    if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
    const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, width, height);
    const stamp = sourceStamps[index] ?? video.currentTime;
    const row = nearestRow(index, stamp);
    const seq = row?.seq ?? row?.frame_index;
    $('frameReadout' + index).textContent = `SOURCE ${stamp.toFixed(3)}s · SESSION ${gameTime(index, stamp).toFixed(3)}s${seq !== undefined ? ` · #${seq}` : ''}${row ? ` · ${pretty(row.status ?? (hasPosition(row) ? 'detected' : 'missing'))}` : ''}`;
    if (!$('showTrack').checked || !hasPosition(row)) return;
    const color = row?.status === 'color_candidate_2d' ? '#ffbd69' : (index ? '#f4c289' : '#7ff1e5'); const scale = width / 1280;
    ctx.strokeStyle = color; ctx.lineWidth = 2 * scale; ctx.shadowBlur = 3 * scale; ctx.shadowColor = '#001820';
    const trail = []; const rows = cameraRows(index);
    for (let i = Math.max(0, row._index - 8); i <= row._index; i++) {
      if (!hasPosition(rows[i]) || (i > 0 && rowTime(rows[i]) - rowTime(rows[i - 1]) > .05)) trail.length = 0;
      if (hasPosition(rows[i])) trail.push(rows[i]);
    }
    if (trail.length > 1) { ctx.beginPath(); trail.forEach((r, i) => { const [x, y] = rowXY(r, index); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); }
    const [x, y] = rowXY(row, index);
    ctx.beginPath(); ctx.arc(x, y, 10 * scale, 0, 2 * Math.PI); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(x - 16 * scale, y); ctx.lineTo(x - 6 * scale, y); ctx.moveTo(x + 6 * scale, y); ctx.lineTo(x + 16 * scale, y); ctx.moveTo(x, y - 16 * scale); ctx.lineTo(x, y - 6 * scale); ctx.moveTo(x, y + 6 * scale); ctx.lineTo(x, y + 16 * scale); ctx.stroke();
  });
  drawCrop();
}
function drawCrop() {
  const canvas = $('crop'); const ctx = canvas.getContext('2d'); const video = videos[cropCamera]; const camera = cameras()[cropCamera];
  ctx.fillStyle = '#0b151b'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (isSynthetic() && !camera?.url) {
    ctx.drawImage(overlays[cropCamera], 0, 0, canvas.width, canvas.height); $('cropCaption').textContent = 'SYNTHETIC · threshold illustration'; return;
  }
  if (!camera || video.readyState < 2) { ctx.fillStyle = '#7294a4'; ctx.font = '18px system-ui'; ctx.textAlign = 'center'; ctx.fillText('Source close-up appears when video is ready', canvas.width / 2, canvas.height / 2); ctx.textAlign = 'start'; return; }
  const fullResolution = !playing && originalCamera === cropCamera && originalCrop.readyState >= 2 && !originalCrop.seeking && Math.abs(originalCrop.currentTime - sourceTime(cropCamera)) < .04;
  const sourceVideo = fullResolution ? originalCrop : video;
  const [width, height] = fullResolution ? [originalCrop.videoWidth, originalCrop.videoHeight] : sourceSize(cropCamera);
  const row = nearestRow(cropCamera, fullResolution ? originalCrop.currentTime : sourceStamps[cropCamera] ?? video.currentTime);
  const xy = hasPosition(row) ? rowXY(row, cropCamera, [width, height]) : null;
  const center = cropCenter ?? (xy ? [xy[0] / width, xy[1] / height] : [.5, .5]);
  const zoom = number($('cropZoom').value, 3); const cropWidth = width / zoom; const cropHeight = cropWidth * canvas.height / canvas.width;
  const left = clamp(center[0] * width - cropWidth / 2, 0, Math.max(0, width - cropWidth)); const top = clamp(center[1] * height - cropHeight / 2, 0, Math.max(0, height - cropHeight));
  ctx.imageSmoothingEnabled = false; ctx.drawImage(sourceVideo, left, top, cropWidth, cropHeight, 0, 0, canvas.width, canvas.height);
  if (hasPosition(row) && $('showTrack').checked) {
    const x = (xy[0] - left) / cropWidth * canvas.width; const y = (xy[1] - top) / cropHeight * canvas.height;
    ctx.strokeStyle = '#80ece3'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(x, y, 15, 0, 2 * Math.PI); ctx.stroke();
  }
  $('cropCaption').textContent = `${camera.label ?? 'Camera'} · ${fullResolution ? 'ORIGINAL 4K' : 'playback proxy'} · ${zoom.toFixed(1)}× · ${(fullResolution ? originalCrop.currentTime : sourceStamps[cropCamera] ?? video.currentTime).toFixed(3)}s`;
}
function applySetup() {
  const sync = session?.sync ?? {}; const offset = number(cameras()[1]?.offset_s ?? sync.offset_s);
  const uncertainty = sync.uncertainty_s === null || sync.uncertainty_s === undefined ? 'uncertainty unverified' : `±${(number(sync.uncertainty_s) * 1000).toFixed(1)} ms estimate`;
  $('offsetValue').textContent = `${offset >= 0 ? '+' : ''}${offset.toFixed(4)} s`;
  $('manualOffset').value = offset.toFixed(4);
  $('syncSummary').textContent = isSynthetic() ? 'SYNTHETIC FIXTURES · no capture timing' : `Estimated alignment · ${uncertainty}`;
  $('syncMethod').textContent = `${sync.method ?? 'Manual offset; not verified'}${sync.verified ? ' · checked across multiple moments' : ' · capture timing not independently verified'}`;
  const calibration = session?.calibration ?? {};
  $('calibrationStatus').textContent = calibration.trusted ? 'Validated geometry' : 'Metric evidence limited';
  $('calibrationDetails').textContent = calibration.status ?? 'Camera intrinsics, motion and table pose have not been validated.';
  $('limitations').replaceChildren();
  for (const value of session?.limitations ?? []) { const li = document.createElement('li'); li.textContent = String(value); $('limitations').append(li); }
  $('benchmark').replaceChildren();
  if (session?.benchmark) {
    const paragraph = document.createElement('p');
    const measurements = Object.entries(session.benchmark).filter(([,value]) => value && typeof value === 'object' && Number.isFinite(value.end_to_end_fps));
    paragraph.textContent = typeof session.benchmark === 'string' ? session.benchmark : session.benchmark.summary ?? (measurements.length ? measurements.map(([name,value]) => `${pretty(name)}: ${value.end_to_end_fps.toFixed(1)} processing FPS (${value.device ?? 'CPU'})`).join(' · ') + '. Coverage is not recall; playback FPS is separate.' : 'Processing benchmark is included in exported measurements; browser playback is not inference throughput.');
    $('benchmark').append(paragraph);
  }
}
async function loadSession() {
  const generation = ++loadGeneration; pause(); loading = true;
  for (const id of ['play','stepBack','stepForward','timeline']) $(id).disabled = true;
  showError(''); selected = null; reached = new Set(); lastAdvance = -1; advanceSupported = true;
  try {
    const data = await api($('sessionMode').value === 'synthetic' ? '/api/synthetic' : '/api/session');
    if (generation !== loadGeneration) return;
    session = data; time = 0; cropCenter = null; originalCamera = -1; $('reviewDetails').hidden = true;
    if (isSynthetic() && !data.cameras?.length) data.cameras = [{id:'synthetic-front',label:'Known toss geometry',fps:30,offset_s:0,drift:1,frames:[]},{id:'synthetic-profile',label:'Rule boundary view',fps:30,offset_s:0,drift:1,frames:[]}];
    $('sessionLabel').textContent = data.label ?? 'Your two recordings · one shared evidence timeline';
    $('recordedTag').classList.toggle('synthetic', isSynthetic());
    $('recordedTag').replaceChildren(); const dot = document.createElement('span'); dot.className = 'dot';
    $('recordedTag').append(dot, document.createTextNode(isSynthetic() ? 'SYNTHETIC · KNOWN TEST INPUTS' : 'RECORDED · PREPROCESSED'));
    $('nameA').textContent = data.teams?.A?.name ?? data.teams?.find?.((t) => t.id === 'A')?.name ?? data.names?.A ?? 'Player A'; $('nameB').textContent = data.teams?.B?.name ?? data.teams?.find?.((t) => t.id === 'B')?.name ?? data.names?.B ?? 'Player B';
    $('timeline').max = String(duration()); $('timeline').value = '0';
    videos.forEach((video, index) => {
      video.pause(); sourceStamps[index] = null; const camera = cameras()[index];
      $('camLabel' + index).textContent = (camera?.label ?? (index ? 'DIAGONAL CAMERA' : 'SIDE CAMERA')).toUpperCase();
      $('camRate' + index).textContent = camera?.fps ? `${number(camera.fps).toFixed(2).replace(/\.00$/, '')} FPS` : isSynthetic() ? 'SYNTHETIC' : 'UNAVAILABLE';
      $('cropCamera').options[index].textContent = camera?.label ?? (index ? 'Diagonal camera' : 'Side camera');
      video.hidden = !camera?.url && isSynthetic();
      if (camera?.url) { video.src = camera.url; video.load(); $('empty' + index).hidden = true; }
      else { video.removeAttribute('src'); video.load(); $('empty' + index).hidden = isSynthetic(); $('empty' + index).textContent = 'Source video unavailable'; }
    });
    if (data.points?.length) selected = data.points[0].id;
    applySetup(); renderPoints(); renderDecision(); updateClock();
    try { updateScore(await api('/api/state?dataset=' + dataset())); } catch { updateScore({points: {A: 0, B: 0}, games: {A: 0, B: 0}, history: []}); toast('Referee state is unavailable. Evidence playback remains available.'); }
    if (isSynthetic()) $('scoreOrigin').textContent = 'SYNTHETIC · separate fixture referee state';
    sceneView?.destroy(); sceneView = null; $('sceneEmpty').hidden = false; $('sceneStatus').textContent = data.scene?.frames?.length ? (isSynthetic() ? 'SYNTHETIC GEOMETRY' : 'ILLUSTRATIVE POSE') : 'SOURCE REVIEW AVAILABLE';
    $('sceneReason').textContent = data.scene?.frames?.length ? 'Loading estimated 3D presentation…' : 'Metric reconstruction requires validated calibration and timing. Inspect the source close-up while those inputs remain uncertain.';
    if (data.scene?.frames?.length) {
      try {
        const {createScene} = await import('./scene.js');
        if (generation !== loadGeneration) return;
        const created = await createScene($('viewport'), data.scene, {synthetic: isSynthetic(), trusted: !!data.calibration?.trusted});
        if (generation !== loadGeneration) { created.destroy(); return; }
        sceneView = created;
        $('sceneEmpty').hidden = true;
        $('sceneDisclaimer').textContent = isSynthetic() ? 'Synthetic geometry and test trajectories. No real-world tracking accuracy is implied.' : 'Estimated player and paddle poses; approximate camera geometry. Missing ball positions remain hidden.';
      } catch (error) {
        $('sceneReason').textContent = `3D unavailable: ${error.message}. Synchronized source evidence remains available.`; $('sceneStatus').textContent = 'SOURCE REVIEW AVAILABLE';
      }
    }
    document.querySelectorAll('[data-view]').forEach((button) => button.disabled = !sceneView);
    seek(0);
  } catch (error) { showError(`The recorded session could not be loaded: ${error.message}. Run the clip preparation command and start the demo server.`); $('sessionLabel').textContent = 'Session unavailable'; }
  finally { if (generation === loadGeneration) { loading = false; for (const id of ['play','stepBack','stepForward','timeline']) $(id).disabled = !session || !duration(); } }
}
async function advanceReferee() {
  if (!playing || advancing || !advanceSupported) return;
  const candidates = (session?.points ?? []).filter((p) => number(p.end_s) <= time && !reached.has(p.id));
  if (!candidates.length) return;
  advancing = true;
  try {
    const result = await api('/api/advance', {t_game_s: time, dataset: dataset()});
    candidates.forEach((point) => reached.add(point.id)); updateScore(result.state ?? result, true); lastAdvance = time;
  } catch (error) {
    if ([404, 405, 501].includes(error.status)) advanceSupported = false;
    else if (time - lastAdvance > 1) { lastAdvance = time; toast(`Referee update pending: ${error.message}`); }
  } finally { advancing = false; }
}
async function resolvePoint(winner) {
  const point = getPoint(); if (!point || actionBusy || isSynthetic()) return;
  actionBusy = true; renderDecision();
  try {
    const result = await api('/api/resolve', {dataset: dataset(), event_id: 'manual-' + crypto.randomUUID(), rally_id: point.id, winner: winner === 'let' ? null : winner, kind: winner === 'let' ? 'let' : 'point', reason: $('resolutionReason').value.trim() || 'Player / official review of synchronized original footage'});
    updateScore(result.state ?? result, true); $('resolutionReason').value = ''; toast('Manual decision recorded in referee history.');
  } catch (error) { toast(`Decision was not recorded: ${error.message}`); }
  finally { actionBusy = false; renderDecision(); }
}
$('play').onclick = () => playing ? pause() : play();
$('timeline').oninput = () => {
  const target = number($('timeline').value);
  const point = (session?.points ?? []).find((candidate) => target >= candidate.start_s && target <= candidate.end_s);
  if (point && point.id !== selected) selectPoint(point.id);
  seek(target);
};
$('speed').onchange = () => { rate = number($('speed').value, 1); syncVideos(); };
$('sessionMode').onchange = loadSession;
$('stepBack').onclick = () => { pause(); seek(time - 1 / number(cameras()[0]?.fps, 60)); };
$('stepForward').onclick = () => { pause(); seek(time + 1 / number(cameras()[0]?.fps, 60)); };
$('showTrack').onchange = drawSources;
$('audio').onchange = () => { videos[0].muted = !$('audio').checked; videos[1].muted = true; };
$('cropCamera').onchange = () => { cropCamera = number($('cropCamera').value); cropCenter = null; drawCrop(); requestOriginalCrop(); };
$('cropZoom').oninput = drawCrop;
$('evidence').onclick = () => { const point = getPoint(); if (point) { pause(); rate = .25; $('speed').value = '0.25'; seek(number(point.evidence_s ?? point.end_s)); } };
$('challenge').onclick = async () => {
  const point = getPoint(); if (!point) return; pause(); rate = .25; $('speed').value = '0.25'; seek(number(point.evidence_s ?? point.end_s));
  $('reviewDetails').hidden = false;
  if (isSynthetic()) { $('reviewDetails').textContent = 'Synthetic rule-boundary case. Inspect known inputs and expected uncertainty; this is not a challenge to a real point.'; return; }
  try {
    const response = await api('/api/challenge', {rally_id: point.id, dataset: dataset()});
    $('reviewDetails').textContent = response.reason ?? response.message ?? 'Review opened. Both source views are paused at the evidence. The score changes only after an audited referee resolution.';
    if (response.state || response.history || response.calls) updateScore(response.state ?? response);
  } catch (error) { $('reviewDetails').textContent = `Source review available. The referee could not register this challenge: ${error.message}`; }
};
for (const button of document.querySelectorAll('[data-winner]')) button.onclick = () => resolvePoint(button.dataset.winner);
for (const button of document.querySelectorAll('[data-inspect]')) button.onclick = () => { cropCamera = number(button.dataset.inspect); $('cropCamera').value = String(cropCamera); cropCenter = null; drawCrop(); requestOriginalCrop(); $('crop').scrollIntoView({behavior: 'smooth', block: 'nearest'}); };
for (let index = 0; index < 2; index++) {
  $('videoWrap' + index).addEventListener('click', (event) => {
    if (event.target.closest('button')) return;
    const bounds = $('videoWrap' + index).getBoundingClientRect(); cropCamera = index; $('cropCamera').value = String(index);
    const [width, height] = sourceSize(index); const sourceRatio = width / height; const boxRatio = bounds.width / bounds.height;
    let x = (event.clientX - bounds.left) / bounds.width, y = (event.clientY - bounds.top) / bounds.height;
    if (sourceRatio > boxRatio) y = (y - (1 - boxRatio / sourceRatio) / 2) / (boxRatio / sourceRatio);
    else x = (x - (1 - sourceRatio / boxRatio) / 2) / (sourceRatio / boxRatio);
    cropCenter = [clamp(x, 0, 1), clamp(y, 0, 1)]; drawCrop(); requestOriginalCrop();
  });
  videos[index].addEventListener('loadedmetadata', () => syncVideos(true));
  videos[index].addEventListener('seeked', () => { sourceStamps[index] = null; if (!playing) syncVideos(true); drawSources(); });
  videos[index].addEventListener('error', () => {
    if (cameras()[index]?.url) { $('empty' + index).hidden = false; $('empty' + index).textContent = 'This source could not be decoded. Check the local media file.'; }
  });
  if ('requestVideoFrameCallback' in videos[index]) {
    const callback = (_, metadata) => { sourceStamps[index] = metadata.mediaTime; videos[index].requestVideoFrameCallback(callback); };
    videos[index].requestVideoFrameCallback(callback);
  }
}
$('offsetMinus').onclick = () => { $('manualOffset').value = (number($('manualOffset').value) - 1 / number(cameras()[1]?.fps, 60)).toFixed(4); };
$('offsetPlus').onclick = () => { $('manualOffset').value = (number($('manualOffset').value) + 1 / number(cameras()[1]?.fps, 60)).toFixed(4); };
$('saveOffset').onclick = async () => {
  const offset = number($('manualOffset').value, NaN); if (!Number.isFinite(offset)) return toast('Enter a finite camera offset.');
  if (isSynthetic()) return toast('Synthetic fixtures have no camera alignment.');
  try {
    await api('/api/sync', {offset_s: offset, dataset: dataset()});
    if (cameras()[1]) cameras()[1].offset_s = offset;
    session.sync = {...session.sync, offset_s: offset, method: 'Manual user alignment', verified: false};
    applySetup(); seek(time); toast('Manual alignment applied. Capture-time uncertainty remains unverified.');
  } catch (error) { toast(`Alignment could not be saved: ${error.message}`); }
};
for (const button of document.querySelectorAll('[data-view]')) button.onclick = () => {
  sceneView?.setView(button.dataset.view, getPoint());
  document.querySelectorAll('[data-view]').forEach((item) => item.classList.toggle('active', item === button));
};
document.addEventListener('keydown', (event) => {
  if (['INPUT', 'TEXTAREA', 'SELECT', 'BUTTON'].includes(document.activeElement?.tagName)) return;
  if (event.code === 'Space') { event.preventDefault(); playing ? pause() : play(); }
  if (event.code === 'ArrowLeft' || event.code === 'ArrowRight') { event.preventDefault(); pause(); seek(time + (event.code === 'ArrowRight' ? 1 : -1) / number(cameras()[0]?.fps, 60)); }
});
function tick(now) {
  const dt = Math.min(.1, (now - lastTick) / 1000); lastTick = now;
  if (playing) {
    const activePoint = (session?.points ?? []).find((point) => number(point.start_s) <= time && number(point.end_s) >= time);
    if (activePoint && selected !== activePoint.id) selectPoint(activePoint.id);
    if (cameras()[0]?.url && videos[0].readyState >= 2) time = clamp(gameTime(0, videos[0].currentTime), 0, duration());
    else if (isSynthetic()) time = clamp(time + dt * rate, 0, duration());
    syncVideos(); advanceReferee();
    if (time >= duration() - .005 || (videos[0].ended && cameras()[0]?.url)) { time = duration(); pause(); }
  }
  updateClock(); drawSources(); sceneView?.draw(time, getPoint()); requestAnimationFrame(tick);
}
loadSession(); requestAnimationFrame(tick);
