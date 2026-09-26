const $ = (id) => document.getElementById(id);
const CHECKS = ["time_out", "patient_confirmed", "site_confirmed", "allergies_confirmed", "count_confirmed", "close_requested"];
const CHECK_LABEL = {
  time_out: "time-out", patient_confirmed: "patient", site_confirmed: "site",
  allergies_confirmed: "allergies", count_confirmed: "count", close_requested: "close",
};
let alarmOn = false;
let prev = {};
let state = { rooms: [], sim: {}, ledger: { tail: [] }, metrics: {}, cloud_offline: false, vision_down: false };

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
function post(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
}
function toast(msg) {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast show";
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.className = "toast"; }, 2800);
}
function beep() {
  pulse(740, 0.04, 0.12);
}
let bedTimer = null;
function pulse(freq, level, seconds) {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  if (!Ctx) return;
  if (!pulse.ctx) pulse.ctx = new Ctx();
  const ctx = pulse.ctx;
  if (ctx.state === "suspended") ctx.resume();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = freq;
  osc.connect(gain);
  gain.connect(ctx.destination);
  gain.gain.setValueAtTime(level, ctx.currentTime);
  osc.start();
  osc.stop(ctx.currentTime + seconds);
}
function monitorBed(on) {
  if (!on) {
    if (bedTimer) clearInterval(bedTimer);
    bedTimer = null;
    return;
  }
  if (bedTimer) return;
  bedTimer = setInterval(() => {
    if (!voiceBusy || !voiceOn || !caseLive) {
      monitorBed(false);
      return;
    }
    pulse(880, 0.03, 0.06);
  }, 1000);
}

function expectFor(room, problem) {
  const kind = ["clean", "mismatch", "timeout"][(room - 1) % 3];
  if (kind === "mismatch" || Number(room) === Number(problem)) return "BLOCK";
  if (kind === "timeout") return "CAUTION";
  return "SAFE";
}
function pickValue(id) {
  return document.querySelector(`#${id} button.on`).dataset.value;
}
function renderLegend() {
  const legend = $("legend");
  if (!legend) return;
  const problem = $("problem") ? Number(pickValue("problem")) : 7;
  const n = $("ors") ? Number(pickValue("ors")) : 8;
  legend.innerHTML = Array.from({ length: n }, (_, i) => {
    const status = expectFor(i + 1, problem);
    return `<i>OR ${i + 1} · expect ${status}</i>`;
  }).join("");
}

function bay(room) {
  const cam = room.vision_count == null ? "—" : room.vision_count;
  const disagree = room.vision_count != null && room.vision_count !== room.removed;
  const pct = room.line_total ? Math.round((room.line_index / room.line_total) * 100) : 0;
  const pills = CHECKS.map((key) => `<span class="${(room.checklist || []).includes(key) ? "on" : ""}">${CHECK_LABEL[key]}</span>`).join("");
  const lines = (room.transcript || []).slice(-3).map((line) => `<div>${esc(line)}</div>`).join("");
  const photoSrc = room.photo_url || (room.photo ? `/media/photos/${room.photo}` : "");
  const photo = photoSrc ? `<img src="${esc(photoSrc)}" alt="Tray camera for OR ${room.or}" />` : "";
  const verdict = room.done ? (room.status === room.expected ? "PASS" : "MISS") : `EXPECT ${room.expected || ""}`;
  return `
    <div class="bay-top"><h3 class="ornum">OR ${room.or}</h3><div class="status">${esc(room.status)}</div></div>
    <div class="sub">${esc(room.procedure || "")}${room.chart ? " · " + esc(room.chart.name) : ""} · ${esc(room.phase || "")} · ${esc(verdict)}</div>
    <div class="nums">
      <div><b>${room.added}</b><span class="sub">IN</span></div>
      <div><b>${room.removed}</b><span class="sub">OUT</span></div>
      <div class="${disagree ? "bad" : ""}"><b>${cam}</b><span class="sub">CAM</span></div>
    </div>
    <div class="track"><span style="width:${pct}%"></span></div>
    <div class="pills">${pills}</div>
    <div class="critic">${esc(room.message || "Listening.")}</div>
    <div class="alerts">${(room.alerts || []).map(esc).join(" · ")}</div>
    <div class="transcript">${lines}</div>
    ${photo}
    <div class="phase">${esc(room.mode || "")} · risk ${room.risk || 0}</div>`;
}

function renderFloor() {
  const root = $("bays");
  const rooms = state.rooms || [];
  if (!rooms.length) {
    root.innerHTML = `<div class="empty bay"><strong>FLOOR DARK</strong><p>Arm the rooms. Room 7 hides one sponge the nurse already counted out.</p></div>`;
    return;
  }
  const seen = new Set();
  rooms.forEach((room) => {
    seen.add(String(room.or));
    let el = root.querySelector(`[data-or="${room.or}"]`);
    const sig = [room.status, room.added, room.removed, room.vision_count, room.message, room.phase, room.photo, room.line_index, room.done, room.chart && room.chart.id, (room.transcript || []).at(-1)].join("|");
    if (!el) {
      el = document.createElement("article");
      el.dataset.or = room.or;
      root.appendChild(el);
    }
    el.className = `bay ${room.status || ""}`;
    if (el.dataset.sig !== sig) {
      el.dataset.sig = sig;
      el.innerHTML = bay(room);
    }
    if (prev[room.or] && prev[room.or] !== "BLOCK" && room.status === "BLOCK") {
      toast(`OR ${room.or} close blocked`);
      if (alarmOn) beep();
    }
    prev[room.or] = room.status;
  });
  [...root.querySelectorAll("[data-or]")].forEach((el) => {
    if (!seen.has(el.dataset.or)) el.remove();
  });
  const empty = root.querySelector(".empty");
  if (empty) empty.remove();
}

function renderMetrics() {
  const m = state.metrics || {};
  const fmt = (n) => (n == null ? "—" : Number(n).toFixed(3) + "s");
  const cards = [
    [m.live ?? 0, "Rooms live"],
    [fmt(m.p95), "p95 per line"],
    [`${m.cloud_calls || 0}/${m.routes || 0}`, "Cloud escalations"],
    [m.bytes || 0, "Anonymous bytes"],
    [m.held || 0, "Closes held"],
  ];
  $("metrics").innerHTML = cards.map(([value, label]) => `<div class="metric"><b>${esc(value)}</b><span>${label}</span></div>`).join("");
  if ($("cloudBtn")) $("cloudBtn").textContent = state.cloud_offline ? "RESTORE CLOUD" : "SEVER CLOUD";
  if ($("visionBtn")) $("visionBtn").textContent = state.vision_down ? "RESTORE CAMERA" : "KILL CAMERA";
  const station = $("station");
  if (station) station.textContent = (state.models && state.models.llm_backend) || "edge models";
  renderLegend();
}

function renderChain() {
  const tail = (state.ledger && state.ledger.tail) || [];
  $("chain").innerHTML = tail.length ? tail.map((entry) => `
    <div class="block">
      <b>#${esc((entry.hash || "").slice(0, 6))}</b>
      <div>${esc(entry.type)} ${entry.or ? "OR " + esc(entry.or) : ""} ${esc(entry.status || entry.route || "")}<br><small>${esc((entry.alerts || []).join(" · ") || entry.reason || "")}</small></div>
      <small>${esc(entry.prev || "").slice(0, 8)}</small>
    </div>`).join("") : `<p class="sub">No entries yet. Arm the floor or ask a protocol question.</p>`;
}

async function tick() {
  try {
    state = await api("/api/state");
    renderMetrics();
    renderFloor();
    if (!$("ledger").classList.contains("hidden")) renderChain();
    if (!$("live").classList.contains("hidden")) renderLive();
  } catch (err) {
    toast("Command link lost");
  }
}

let voiceOn = true;
let voiceHeard = 0;
let voiceQueue = [];
let voiceBusy = false;
let voiceCursor = -1;
let voiceCase = "";
let voiceToken = 0;
let caseLive = false;
let armStarted = 0;
let scrubLock = false;
function resetVoice() {
  voiceToken += 1;
  voiceHeard = 0;
  voiceQueue = [];
  voiceBusy = false;
  voiceCursor = -1;
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  monitorBed(false);
}

function syncVoice(tape, caseId, started) {
  if (!caseLive) return;
  if (started && armStarted && started < armStarted - 2) return;
  if (caseId !== voiceCase) {
    voiceCase = caseId;
    resetVoice();
    voiceCase = caseId;
  }
  if (!voiceOn || $("live").classList.contains("hidden") || !window.speechSynthesis) return;
  while (voiceHeard < tape.length) {
    voiceQueue.push({ i: voiceHeard, text: tape[voiceHeard].text || "" });
    voiceHeard += 1;
  }
  if (voiceBusy || !voiceQueue.length) return;
  const next = voiceQueue.shift();
  voiceCursor = next.i;
  voiceBusy = true;
  wavePhase.amp = 1;
  monitorBed(true);
  const token = ++voiceToken;
  const utter = new SpeechSynthesisUtterance(next.text);
  utter.rate = 0.92;
  const done = () => {
    if (token !== voiceToken) return;
    voiceToken += 1;
    voiceBusy = false;
    if (!voiceQueue.length) monitorBed(false);
    renderLive();
  };
  utter.onend = done;
  utter.onerror = done;
  window.speechSynthesis.cancel();
  window.setTimeout(() => {
    if (token !== voiceToken) return;
    window.speechSynthesis.speak(utter);
  }, 60);
}
const wavePhase = { amp: 0.15 };

function stageHTML(photo, boxes, frameW, frameH, live, photoUrl) {
  if (!photo && !photoUrl) return `<div class="empty"><strong>NO FRAME</strong><p>Waiting for the tray camera.</p></div>`;
  const src = photoUrl || `/media/photos/${photo}?v=2`;
  const color = { sponge: "#ff5a72", instrument: "#7ee7ff", sharp: "#ffc14d", missing: "#ff3355" };
  const marks = (boxes || []).map((box) => {
    const stroke = color[box.kind] || "#ff5a72";
    const name = (box.label || box.kind || "item").toUpperCase();
    const dash = box.kind === "missing" ? ' stroke-dasharray="8 4"' : "";
    return `<rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" fill="none" stroke="${stroke}" stroke-width="3"${dash}/>
    <text class="tag" x="${box.x}" y="${Math.max(16, box.y - 4)}" fill="${stroke}">${esc(name)}</text>`;
  }).join("");
  const stamp = live ? "LIVE · OR CAM 2 · TRAY" : "BLACK BOX · PLAYBACK";
  const fit = arguments[6] ? " fit" : "";
  return `<div class="cam ${live ? "live" : "tape"}${fit}">
    <img src="${esc(src)}" alt="Overhead tray camera" />
    <div class="vignette"></div>
    <div class="grain"></div>
    <div class="hud"><span>${stamp}</span><span class="tc"></span></div>
    <svg viewBox="0 0 ${frameW || 640} ${frameH || 480}" preserveAspectRatio="none">${marks}</svg>
  </div>`;
}

function renderLive() {
  const rooms = state.rooms || [];
  const roomId = document.querySelector("#caseRooms button.on")?.dataset.room || "8";
  const room = rooms.find((item) => String(item.or) === String(roomId)) || null;
  if (!room) {
    $("liveStage").innerHTML = `<div class="empty"><strong>CHANNEL DARK</strong><p>Play the hidden-tray case.</p></div>`;
    $("boxStage").innerHTML = "";
    return;
  }
  $("recDot").className = room.done ? "rec" : "rec on";
  $("recDot").textContent = room.done ? "HOLD" : "REC";
  const tape = room.tape || [];
  const caseId = `${room.or}:${room.started || 0}`;
  syncVoice(tape, caseId, room.started || 0);
  const followVoice = voiceOn && voiceCursor >= 0;
  const idx = followVoice ? voiceCursor : Math.max(0, tape.length - 1);
  const frameNow = tape[idx] || null;
  const photo = frameNow ? frameNow.photo : room.photo;
  const photoUrl = frameNow ? frameNow.photo_url : room.photo_url;
  const boxes = frameNow ? frameNow.boxes : room.boxes;
  $("liveStage").innerHTML = stageHTML(photo, boxes, frameNow ? frameNow.frame_w : room.frame_w, frameNow ? frameNow.frame_h : room.frame_h, true, photoUrl);
  const line = frameNow ? frameNow.text : "Listening for the circulating nurse.";
  $("liveCaption").textContent = line;
  const agents = room.last_agents || {};
  const vital = (frameNow && frameNow.vitals) || room.vitals || {};
  $("monitor").innerHTML = `
    <div><b>${vital.hr || "--"}</b><span>HR</span></div>
    <div><b>${vital.sys || "--"}/${vital.dia || "--"}</b><span>BP</span></div>
    <div><b>${vital.spo2 || "--"}</b><span>SpO2</span></div>
    <div><b>${vital.glucose || room.glucose || "--"}</b><span>BG</span></div>
    <div><b>${vital.rr || "--"}</b><span>RR</span></div>
    <div><b>${esc(vital.phase || room.phase || "")}</b><span>CASE</span></div>`;
  const checks = (frameNow && frameNow.checklist) || room.checklist || [];
  $("checklist").innerHTML = CHECKS.map((key) => `<span class="${checks.includes(key) ? "on" : ""}">${CHECK_LABEL[key]}</span>`).join("");
  const log = room.patient_log || [];
  const heard = followVoice ? tape.slice(0, idx + 1) : tape;
  const current = heard.length - 1;
  $("procedureLog").innerHTML = heard.length
    ? heard.map((mark, index) => `<div class="${index === current ? "now" : ""}">${esc(mark.t)}s ${esc(mark.text)}</div>`).join("")
    : "<div>The full script appears here from time-out through close, one line at a time.</div>";
  const logBox = $("procedureLog");
  if (!room.done) logBox.scrollTop = logBox.scrollHeight;
  $("orNow").textContent = `${room.procedure || ""}\n${room.op_phase || room.phase || ""}\nLine ${room.line_index || 0} of ${room.line_total || 0}`;
  const chart = room.chart;
  const head = chart
    ? `${chart.name}\nBirth date ${chart.birthdate} · age ${chart.age} · ${chart.gender}\nMRN ${chart.id}\n${chart.city}, ${chart.state}\nAllergies: ${(chart.allergies || []).join(", ") || "none listed"}\n`
    : "";
  $("patientNow").textContent = head + (log.length ? log.map((item) => `${item.t}s  ${item.text}`).join("\n") : "Vitals steady. No infusion change yet.");
  $("alertNow").textContent = (room.alerts || []).join("\n") || "No alert right now.";
  $("analytics").textContent = room.done
    ? `${room.procedure}\nFinal ${room.status}. In ${room.added} out ${room.removed} camera ${room.vision_count}.\nTools still inside: ${(room.tools_inside || []).join(", ") || "none"}.\nFocus ${room.scenario || "complete"}.\nThis room is on the floor dashboard.`
    : "The summary appears when the case ends.";
  const shown = followVoice ? tape.slice(0, idx + 1) : tape;
  $("modelConsole").innerHTML = shown.length
    ? shown.map((mark, index) => {
        const model = mark.model || {};
        const event = model.event && model.event !== "none" ? model.event : "none";
        const bad = mark.status === "BLOCK" || mark.status === "CAUTION";
        return `<div class="line${index === shown.length - 1 ? " now" : ""}"><span class="dim">${esc(mark.t)}s  ${esc(model.backend || "model")}  ${esc(model.ms || 0)}ms</span><br><span class="heard">&gt; HEARD    ${esc(mark.text)}</span><br>&gt; PREDICT  counter +${model.added || 0} / -${model.removed || 0}   checklist ${esc(event)}<br>&gt; VISION   tray ${mark.vision_count == null ? "—" : mark.vision_count}<br><span class="${bad ? "bad" : "pred"}">&gt; MARK     ${esc(mark.kind)}   ${esc(mark.status)}</span></div>`;
      }).join("<br>")
    : `<span class="dim">waiting for the first spoken line…</span>`;
  const box = $("modelConsole");
  box.scrollTop = box.scrollHeight;
  const scrub = $("scrub");
  scrub.max = Math.max(0, tape.length - 1);
  if (!scrubLock && tape.length) scrub.value = String(followVoice ? idx : tape.length - 1);
  let frame = tape[Number(scrub.value)] || null;
  if (frame && !frame.photo) {
    for (let i = Number(scrub.value); i >= 0; i--) {
      if (tape[i].photo) {
        frame = Object.assign({}, frame, { photo: tape[i].photo, photo_url: tape[i].photo_url, boxes: tape[i].boxes, frame_w: tape[i].frame_w, frame_h: tape[i].frame_h });
        break;
      }
    }
  }
  $("tapeMeta").textContent = tape.length ? `${tape.length} marks · t ${frame ? frame.t : 0}s` : "no tape yet";
  $("boxStage").innerHTML = frame ? stageHTML(frame.photo, frame.boxes, frame.frame_w, frame.frame_h, false, frame.photo_url) : `<div class="empty"><strong>TAPE EMPTY</strong></div>`;
  $("marks").innerHTML = tape.map((mark, index) => `<button type="button" class="${index === Number(scrub.value) ? "on" : ""} ${(mark.alerts || []).length ? "alert" : ""}" data-i="${index}">${esc(mark.t)}s ${esc(mark.kind)}</button>`).join("");
  const alertText = frame && (frame.alerts || []).length ? frame.alerts.join("\n") : "No alert on this mark.";
  $("boxAnalysis").textContent = frame
    ? `Recorded “${frame.text}”\nMark ${frame.kind} · in ${frame.added} out ${frame.removed} cam ${frame.vision_count == null ? "—" : frame.vision_count}\nRules at that moment: ${frame.status}\n${frame.message || ""}\n${alertText}`
    : "The black box fills as the case is heard.";
  if (!voiceBusy) wavePhase.amp *= 0.92;
}

function drawWave() {
  const canvas = $("wave");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = "#3ee0a2";
  ctx.beginPath();
  const t = performance.now() / 180;
  for (let x = 0; x < w; x++) {
    const y = h / 2 + Math.sin(x / 12 + t) * (h * 0.36) * wavePhase.amp;
    if (x === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();
  requestAnimationFrame(drawWave);
}

let livePictures = "synthetic";

function liveCopy() {
  const synthetic = livePictures !== "demo";
  const title = $("liveTitle");
  const blurb = $("liveBlurb");
  if (title) title.textContent = synthetic ? "Synthetic Live" : "Demo";
  if (blurb) {
    blurb.textContent = synthetic
      ? "Drawn tray photos and the black box. The procedure, the speech, and the rules are the same case."
      : "The same case. Tray photos come from data/composites/train.";
  }
}

function show(tab) {
  document.body.classList.toggle("on-live", tab === "live");
  document.body.classList.toggle("on-floor", tab === "floor");
  document.body.classList.toggle("on-real", tab === "real");
  document.querySelectorAll(".tab").forEach((btn) => {
    const picturesOk = btn.dataset.tab !== "live" || btn.dataset.pictures === livePictures;
    btn.classList.toggle("on", btn.dataset.tab === tab && picturesOk);
  });
  document.querySelectorAll(".view").forEach((view) => view.classList.toggle("hidden", view.id !== tab));
  if (tab === "ledger") renderChain();
  if (tab === "evidence") loadTests(false);
  if (tab === "models") { loadFilm(); loadTrained(); }
  if (tab === "live") {
    liveCopy();
    renderLive();
  }
  if (tab === "real") loadDetect();
}

async function loadDetect() {
  const film = $("detectFilm");
  if (!film || film.dataset.ready) return;
  const data = await api("/api/detect/samples");
  film.innerHTML = data.images.map((photo) => `
    <button type="button" data-name="${esc(photo.name)}" data-needle="${esc(photo.needle || "")}">
      <img src="${esc(photo.url)}" width="640" height="640" alt="${esc(photo.needle || photo.name)}" />
      <span>${esc(photo.needle || photo.name)}</span>
    </button>`).join("");
  film.dataset.ready = "1";
  film.onclick = async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const url = `/media/composites/train/${button.dataset.name}`;
    $("detectStage").innerHTML = stageHTML(button.dataset.name, [], 640, 640, false, url, true);
    $("detectRead").textContent = `Photo loaded. Detector ${data.address} is reading it…\nNeedle on tray: ${button.dataset.needle}`;
    const result = await post("/api/detect", { name: button.dataset.name });
    const needles = (result.boxes || []).filter((box) => box.kind === "sharp").map((box) => box.label);
    $("detectStage").innerHTML = stageHTML(result.name, result.boxes, result.width, result.height, false, url, true);
    $("detectRead").textContent = `${result.address} · ${result.width}×${result.height}\n${result.ms} ms · cotton ${result.cotton} · tools ${result.tools} · hands ${result.hands}\nNeedle on tray: ${needles.join(", ") || button.dataset.needle}`;
  };
}

async function loadTests(force) {
  $("evidenceBody").textContent = "Running the suite…";
  const report = await api("/api/selftest" + (force ? "?force=true" : ""));
  $("evidenceBody").innerHTML = `<p class="${report.ok ? "pass" : "fail"}">${report.passed}/${report.total} passed · vision ${report.vision.exact}/${report.vision.n} · router ${report.router.local} local / ${report.router.cloud} cloud</p>` +
    report.tests.map((item) => `<div class="test"><div class="${item.ok ? "pass" : "fail"}">${item.ok ? "PASS" : "FAIL"}</div><div><b>${esc(item.name)}</b><div class="sub">${esc(item.detail)}</div></div></div>`).join("");
}

async function loadTrained() {
  const note = $("trainedNote");
  if (!note || note.dataset.ready) return;
  const report = await api("/api/trained");
  if (!report.ready) {
    note.textContent = "Weights are not on disk yet. Training has to finish first.";
    return;
  }
  const counter = report.counter || {};
  const tool = report.tool || {};
  note.textContent = `Counter held-out ${counter.exact}/${counter.n} exact, MAE ${counter.mae}. Instrument mask held-out IoU ${tool.iou} on ${tool.n_test} frames after ${tool.n_train} training images. Device ${report.device}.`;
  const photos = await api("/api/photos");
  $("trainedFilm").innerHTML = photos.photos.map((photo) => `
    <button type="button" data-name="${esc(photo.name)}">
      <img src="/media/photos/${esc(photo.name)}" alt="Tray ${photo.truth}" />
      <span>label ${photo.truth}</span>
    </button>`).join("");
  $("trainedFilm").onclick = async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const result = await post("/api/trained/count", { name: button.dataset.name });
    $("trainedCount").textContent = `Trained model ${result.count} (raw ${result.raw}) · label ${result.truth} · ${result.match ? "MATCH" : "MISS"}`;
  };
  const tools = await api("/api/trained/tools");
  $("toolFilm").innerHTML = (tools.samples || []).map((name) => `
    <button type="button" data-name="${esc(name)}">
      <img src="/media/kvasir/${esc(name)}" alt="Instrument frame" />
      <span>${esc(name)}</span>
    </button>`).join("");
  $("toolFilm").onclick = async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const result = await post("/api/trained/tool", { name: button.dataset.name });
    const box = result.box;
    const marks = box ? `<rect x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}" fill="none" stroke="#7ee7ff" stroke-width="4"/><text class="tag" x="${box.x}" y="${Math.max(16, box.y - 4)}" fill="#7ee7ff">TRAINED TOOL</text>` : "";
    $("toolStage").innerHTML = `<div class="cam tape"><img src="/media/kvasir/${esc(result.name)}" alt="Instrument frame" /><svg viewBox="0 0 ${result.width} ${result.height}" preserveAspectRatio="none">${marks}</svg></div>`;
    $("trainedTool").textContent = box ? `Box x ${box.x} y ${box.y} w ${box.w} h ${box.h}` : "No tool pixels above the threshold.";
  };
  note.dataset.ready = "1";
}

async function loadFilm() {
  if ($("film").dataset.ready) return;
  const data = await api("/api/photos");
  $("film").innerHTML = data.photos.map((photo) => `
    <button type="button" data-name="${esc(photo.name)}">
      <img src="/media/photos/${esc(photo.name)}" alt="Tray labeled ${photo.truth}" />
      <span>label ${photo.truth}</span>
    </button>`).join("");
  $("film").dataset.ready = "1";
  $("film").onclick = async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const result = await post("/api/vision/count", { name: button.dataset.name });
    $("visionOut").textContent = `TrayCount ${result.count} · label ${result.truth} · ${result.match ? "MATCH" : "MISS"} · ${result.backend} · ${result.seconds}s`;
  };
}

document.querySelectorAll(".tab").forEach((btn) => btn.onclick = () => {
  if (btn.dataset.pictures) livePictures = btn.dataset.pictures;
  show(btn.dataset.tab);
});
["ors", "speed", "problem"].forEach((id) => {
  const box = $(id);
  if (!box) return;
  box.onclick = (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    box.querySelectorAll("button").forEach((item) => item.classList.toggle("on", item === button));
    renderLegend();
  };
});
$("askBtn").onclick = async () => {
  const result = await post("/api/ask", { question: $("question").value, urgent: $("urgent").checked });
  $("privacyOut").innerHTML = `
    <div class="route">Route ${esc(result.route)} · confidence ${Number(result.confidence).toFixed(2)} · ${result.bytes_sent || 0} bytes sent</div>
    <div class="panes">
      <div class="pane"><h3>Stayed on the station</h3><pre>${esc(result.question)}</pre></div>
      <div class="pane"><h3>Sent out</h3><pre>${esc(result.sent || "Nothing left the building")}</pre></div>
    </div>
    <p class="sub">Stripper preview, not a transmission: ${esc(result.preview)}</p>
    <p>${esc(result.answer)}</p>`;
  tick();
};
$("presetPhi").onclick = () => {
  $("question").value = "Patient Maria Lopez, DOB 03/14/1971, MRN 4471923, left laparoscopic appendectomy. Which counts are required before closing?";
  $("urgent").checked = false;
};
$("presetSynthea").onclick = async () => {
  const result = await api("/api/synthea/next");
  $("question").value = result.question;
  $("urgent").checked = false;
};
$("presetClean").onclick = () => {
  $("question").value = "What is a retained surgical item?";
  $("urgent").checked = false;
};
$("presetLow").onclick = () => {
  $("question").value = "Which surgical specialties most often skip instrument counts?";
  $("urgent").checked = false;
};
const presets = ["Adding five sponges.", "Sponge out.", "Two sponges out.", "Let's do a time out.", "Okay, let's close.", "Scalpel please."];
$("linePresets").innerHTML = presets.map((line) => `<button type="button" class="chip" data-line="${esc(line)}">${esc(line)}</button>`).join("");
$("linePresets").onclick = (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  $("probeLine").value = button.dataset.line;
  $("probeBtn").click();
};
$("probeBtn").onclick = async () => {
  const result = await post("/api/probe", { text: $("probeLine").value });
  $("probeOut").textContent = `${result.backend} · ${result.ms} ms\ncounter ${JSON.stringify(result.counter)}\nchecklist ${JSON.stringify(result.checklist)}`;
};
$("retest").onclick = () => loadTests(true);
let caseFocus = "complete";
let caseProcedure = "appendectomy";
$("procedures").onclick = (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  caseProcedure = button.dataset.procedure;
  document.querySelectorAll("#procedures button").forEach((item) => item.classList.toggle("on", item === button));
};
$("caseRooms").onclick = (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  document.querySelectorAll("#caseRooms button").forEach((item) => item.classList.toggle("on", item === button));
};
$("focuses").onclick = (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  caseFocus = button.dataset.focus;
  document.querySelectorAll("#focuses button").forEach((item) => item.classList.toggle("on", item === button));
};
$("liveArm").onclick = async () => {
  scrubLock = false;
  caseLive = false;
  armStarted = Date.now() / 1000;
  resetVoice();
  voiceCase = "";
  await post("/api/case", {
    procedure: caseProcedure,
    focus: caseFocus,
    room: Number(document.querySelector("#caseRooms button.on").dataset.room),
    pictures: livePictures,
  });
  caseLive = true;
  $("caseSetup").classList.add("hidden");
  $("caseTheater").classList.remove("hidden");
  show("live");
  toast("Checklist and black box are recording");
  tick();
};
$("voiceBtn").onclick = () => {
  voiceOn = !voiceOn;
  $("voiceBtn").textContent = voiceOn ? "VOICE ON" : "VOICE OFF";
  if (!voiceOn) resetVoice();
};
$("scrub").oninput = () => { scrubLock = true; renderLive(); };
$("marks").onclick = (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  scrubLock = true;
  $("scrub").value = button.dataset.i;
  renderLive();
};
requestAnimationFrame(drawWave);
function paintHosts(data) {
  const box = $("hostSwitch");
  if (!box || !data.hosts) return;
  const current = data.hosts.find((item) => item.id === data.active) || data.hosts[0];
  const detectPort = (data.ports && data.ports.Detector) || 8002;
  box.innerHTML = data.hosts.map((item) => {
    const on = item.id === data.active ? " on" : "";
    const off = item.host ? "" : " disabled";
    const address = item.host || "no address";
    return `<button type="button" class="${on.trim()}" data-host="${esc(item.id)}"${off}><b>${esc(item.label)}</b><small>${esc(address)}</small></button>`;
  }).join("");
  if (current && current.host) {
    if ($("detectHost")) $("detectHost").textContent = `${current.host}:${detectPort}`;
    if ($("archHost")) $("archHost").textContent = current.host;
    if ($("archDetect")) $("archDetect").textContent = `${current.host}:${detectPort}`;
  }
}
async function loadModelLamps() {
  const box = $("modelLamps");
  if (!box) return;
  try {
    const data = await api("/api/models/live");
    paintHosts(data);
    box.innerHTML = data.models.map((item) =>
      `<div class="lamp ${item.up ? "up" : ""}"><i></i><b>${esc(item.name)}</b> ${esc(item.address)}<em>${item.up ? "UP" : "DOWN"}</em></div>`
    ).join("");
  } catch (error) {
    box.textContent = "model status unavailable";
  }
}
const hostSwitch = $("hostSwitch");
if (hostSwitch) {
  hostSwitch.onclick = async (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    try {
      await post("/api/host", { id: button.dataset.host });
      await loadModelLamps();
    } catch (error) {
      toast(String(error.message || error).replace(/^"|"$/g, ""));
    }
  };
}
setInterval(() => { $("clock").textContent = new Date().toLocaleTimeString(); }, 1000);
loadModelLamps();
setInterval(loadModelLamps, 4000);
$("clock").textContent = new Date().toLocaleTimeString();
renderLegend();
tick();
setInterval(tick, 400);
loadTests(false);
