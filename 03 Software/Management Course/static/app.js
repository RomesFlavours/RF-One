/* RF One Selection and Training (test).

   Two pages share this file:
   - the hiring team's page (CVs in order, each candidate, Training), and
   - the candidate's interview page, opened from their own link
     (window.RF_CANDIDATE is set there).
   Candidates and interviews are kept on the server. Training progress is
   kept in this browser (localStorage).

   Words on screen: a "course" is a group of "modules". In Pino's model a
   module here is one pill (the unit that is scored), and a course is a pill
   group (never scored itself). */
(function () {
  "use strict";

  // Training: the units of the course file. Selection: the interview's own
  // modules (the candidate review shows them).
  const COURSES = window.RF_MODULES;
  const SEL = window.RF_SELECTION || [];
  const LEVELS = window.RF_LEVELS || [];
  const IDLE = window.RF_IDLE || 120;
  const CAND = window.RF_CANDIDATE || null;
  // The management course runs on the same engine as its own service: no tests,
  // no practical checks, and the reasoning is kept as evidence.
  const MGMT = window.RF_KIND === "management";
  const SESSION_MIN = window.RF_SESSION_MIN || 20;
  const TITLE = window.RF_COURSE_TITLE || "Server Course";
  const unitLabel = id => MGMT ? (id === "W5" ? "After the four modules" : "Module " + id.slice(1)) : "Unit " + id;
  const partWord = MGMT ? "part" : "module";
  const MODS = {};
  COURSES.forEach(c => c.pills.forEach(p => { MODS[p.id] = Object.assign({ course: c.id }, p); }));
  // v2: the Server Course (Pino's master course, 15 units). Progress from the
  // earlier 12-course version is kept under v1 and not mixed in.
  // A named hire (their own link) keeps progress on the server; this device
  // only holds a copy. The shared link keeps progress on the device.
  const HIRE = window.RF_HIRE || null;
  const KEY = "rfTrainer.v2" + (HIRE ? "." + HIRE.id : "");
  const CATS = { capability: "Capability", trainability: "Trainability", guidability: "Guidability", unsafe: "Unsafe / not suitable", unknown: "Unknown" };
  const STATUS = { EVIDENCED: "Evidenced", PARTIAL: "Partial", NOT_EVIDENCED: "Not evidenced", NOT_ASSESSED: "Not asked" };
  const CHECK = { CLEAR: "Answered", PARTLY: "Partly answered", OPEN: "Still open", NOT_ASKED: "Not asked" };

  // ---------- storage (training progress only) ----------
  function blank() { return { trainee: null, progress: { understood: {}, sessions: {}, last_note: {}, referrals: [], tests: {}, time: {} } }; }
  function load() {
    try {
      const s = JSON.parse(localStorage.getItem(KEY));
      if (s && s.progress) { s.progress.tests = s.progress.tests || {}; s.progress.time = s.progress.time || {}; return s; }
    } catch (e) { /* fall through */ }
    return blank();
  }
  let S = load();
  if (HIRE) S.trainee = { name: HIRE.name.split(" ")[0], fullName: HIRE.name, location: HIRE.location, hire: true };
  let syncTimer = null;
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* private mode: keep in memory */ }
    if (HIRE) {
      clearTimeout(syncTimer);
      syncTimer = setTimeout(() => fetch("api/progress", { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ last_note: S.progress.last_note, sessions: S.progress.sessions, prefs: S.prefs || {} }) }).catch(() => {}), 800);
    }
  }
  // The server's record wins for a named hire: modules, tests and time.
  async function syncFromServer() {
    if (!HIRE) return;
    try {
      const d = await api("api/progress");
      if (!d.hire) return;
      const p = d.progress || {};
      S.progress.understood = p.understood || {};
      S.progress.tests = p.tests || {};
      S.progress.time = p.time || {};
      S.progress.referrals = p.referrals || [];
      Object.entries(p.sessions || {}).forEach(([k, v]) => { S.progress.sessions[k] = Math.max(S.progress.sessions[k] || 0, v); });
      Object.entries(p.last_note || {}).forEach(([k, v]) => { if (v) S.progress.last_note[k] = v; });
      if (p.prefs && "readAloud" in p.prefs) { S.prefs = S.prefs || {}; S.prefs.readAloud = p.prefs.readAloud; }
      try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) { /* ignore */ }
      if (!$("v-home").hidden) renderHome();
    } catch (e) { /* keep the device copy */ }
  }

  // ---------- helpers ----------
  const $ = id => document.getElementById(id);
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "class") n.className = v; else if (k === "html") n.innerHTML = v; else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    });
    kids.flat().forEach(k => { if (k !== "" && k != null) n.append(k instanceof Node ? k : document.createTextNode(String(k))); });
    return n;
  }
  function today() { return new Date().toLocaleString(); }
  const dateOf = iso => iso ? new Date(iso).toLocaleDateString() : "";
  const courseBy = id => COURSES.find(c => c.id === id);
  const doneCount = c => c.pills.filter(p => S.progress.understood[p.id]).length;
  const modulesDone = c => doneCount(c) === c.pills.length;
  const testPassed = c => !c.test_count || !!(S.progress.tests[c.id] || {}).passed;
  // A course is complete when every module is done and its test is passed.
  const courseDone = c => modulesDone(c) && testPassed(c);
  const allDone = () => COURSES.every(courseDone);
  const courseMinutes = c => c.pills.length * 5 + (c.test_count ? 2 : 0);
  // Units follow the course's order: a unit opens when its prerequisites are
  // complete. The hiring team can open any unit to try it.
  // Management: the next module opens once the case and the card are done; the real task can come later.
  const readyToMoveOn = c => MGMT ? c.pills.filter(p => !p.id.endsWith(".task")).every(p => S.progress.understood[p.id]) : courseDone(c);
  const missingFor = c => (c.prerequisites || []).filter(id => !readyToMoveOn(courseBy(id)));
  const isOpen = c => !window.RF_TRAINEE || !!(window.RF_HIRE && window.RF_HIRE.tester) || !missingFor(c).length;
  const fmtMin = sec => { const m = Math.round((sec || 0) / 60); return m < 60 ? m + " min" : Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0") + " min"; };
  const totalTime = () => Object.values(S.progress.time || {}).reduce((a, b) => a + b, 0);
  const plural = (n, w) => n + " " + w + (n === 1 ? "" : "s");
  async function api(path, opts) {
    const r = await fetch(path, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const e = new Error(data.error || "Something went wrong (" + r.status + ").");
      e.status = r.status; e.busy = !!data.busy; e.data = data;
      throw e;
    }
    return data;
  }
  const sleep = ms => new Promise(r => setTimeout(r, ms));

  // ---------- views ----------
  function show(name) {
    document.querySelectorAll(".view").forEach(v => { v.hidden = v.id !== "v-" + name; });
    window.scrollTo(0, 0);
    if (name === "home") renderHome();
    if (name === "candidates") renderCandidates();
    if (name === "home") renderHires();
    if (name !== "test") test = null;
    voice.stop();
  }
  document.addEventListener("click", e => {
    const go = e.target.closest("[data-go]");
    if (!go) return;
    if (chat && chat.busy) return;
    if (chat && !chat.closed && chat.history.length > 1 && !confirm("Leave this session? The conversation so far won't be kept.")) return;
    reportTime();
    chat = null;
    clearInterval(clockTimer);
    show(go.dataset.go);
  });

  // ---------- chat (training here, the interview on the candidate's page) ----------
  let chat = null;
  let clockTimer = null;

  // Counted training time (Pino's rule): a gap with no activity counts only up
  // to IDLE seconds; waiting for the AI always counts; declared breaks are
  // kept apart. The interview keeps its plain clock.
  function counting() { return chat && chat.mode === "training"; }
  function liveCounted() {
    if (!counting()) return 0;
    if (chat.paused || chat.closed) return chat.counted;
    const gap = (Date.now() - chat.lastMark) / 1000;
    return chat.counted + (chat.waiting ? gap : Math.min(gap, IDLE));
  }
  function markActive() {
    if (!counting() || chat.paused || chat.closed) return;
    chat.counted = liveCounted();
    chat.lastMark = Date.now();
  }
  ["keydown", "pointerdown", "touchstart", "scroll", "wheel"].forEach(ev => document.addEventListener(ev, () => { if (counting()) markActive(); }, { passive: true }));
  const minutes = () => !chat ? 0 : counting() ? Math.floor(liveCounted() / 60) : Math.floor((Date.now() - chat.startedAt) / 60000);

  // Time is sent in pieces: every minute while the session runs, when the page
  // is hidden, and once more at the end. Each piece carries only what wasn't
  // sent yet, so nothing is counted twice and at most a minute can be lost.
  function sendTime(counted, breaks, final) {
    const body = JSON.stringify({ kind: "time", module_id: chat.course, counted, breaks, final });
    try {
      if (!(navigator.sendBeacon && navigator.sendBeacon("/api/track", new Blob([body], { type: "application/json" }))))
        fetch("/api/track", { method: "POST", headers: { "Content-Type": "application/json" }, body, keepalive: true }).catch(() => {});
    } catch (e) { /* the time stays on this device */ }
  }
  function flushTime(final) {
    const counted = Math.round(final ? chat.counted : liveCounted()), breaks = Math.round(chat.breaks);
    const dc = Math.max(0, counted - (chat.sentCounted || 0)), db = Math.max(0, breaks - (chat.sentBreaks || 0));
    if (!final && !dc && !db) return counted;
    chat.sentCounted = counted;
    chat.sentBreaks = breaks;
    S.progress.time[chat.course] = (S.progress.time[chat.course] || 0) + dc;
    save();
    sendTime(dc, db, final);
    return counted;
  }
  function reportTime() {
    if (!counting() || chat.reported) return;
    markActive();
    if (chat.paused) { chat.breaks += (Date.now() - chat.paused) / 1000; chat.paused = null; }
    chat.reported = true;
    return flushTime(true);
  }
  setInterval(() => { if (counting() && !chat.closed && !chat.reported) flushTime(false); }, 60000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden" && counting() && !chat.closed && !chat.reported) flushTime(false);
  });
  window.addEventListener("pagehide", () => { if (chat && !chat.closed) reportTime(); });

  function addMsg(kind, text, who) {
    const b = el("div", { class: "msg " + kind });
    if (who) b.append(el("span", { class: "who" }, who));
    text.split(/\n{2,}/).forEach(par => b.append(el("p", {}, par)));
    if (kind === "t" && !CAND && voice.ok) {
      b.append(el("button", { type: "button", class: "listen", "aria-label": "Listen to this message", onclick: () => voice.say(text) }, "▶ Listen"));
    }
    $("log").append(b);
    b.scrollIntoView({ block: "end", behavior: "smooth" });
    return b;
  }

  // ---------- read aloud (training) ----------
  // The device's own voices (free, nothing sent anywhere): a female voice
  // where the device has one. "Read aloud" reads each new Trainer message;
  // "Listen" reads one message. The choice is kept on this device.
  const voice = (function () {
    const ok = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
    const FEMALE = /(female|woman|samantha|ava|allison|susan|zoe|joanna|salli|kendra|kimberly|ivy|ruth|aria|jenny|michelle|emma|sonia|libby|zira|hazel|susan|heera|catherine|karen|moira|tessa|fiona|veena|serena|victoria|kate|google us english|google uk english female)/i;
    const MALE = /(\bmale\b|daniel|alex|fred|tom|aaron|guy|davis|tony|ryan|christopher|eric|roger|steffan|brian|matthew|justin|joey|mark|david|george|james|richard|rishi|google uk english male)/i;
    let chosen = null;
    function pick() {
      if (!ok) return null;
      const all = speechSynthesis.getVoices();
      const en = all.filter(v => /^en/i.test(v.lang));
      const pool = en.length ? en : all;
      const female = pool.filter(v => FEMALE.test(v.name) && !MALE.test(v.name));
      const notMale = pool.filter(v => !MALE.test(v.name));
      // The device's own voices first: Chrome's online voices (Google ...)
      // often stay silent or stop after about 15 seconds.
      const rank = v => (/^en[-_]US/i.test(v.lang) ? 0 : 1) + (v.localService ? -4 : 0) + (/(natural|neural|premium|enhanced)/i.test(v.name) ? -2 : 0);
      const list = (female.length ? female : notMale.length ? notMale : pool).slice().sort((a, b) => rank(a) - rank(b));
      chosen = list[0] || null;
      return chosen;
    }
    if (ok) { pick(); speechSynthesis.addEventListener && speechSynthesis.addEventListener("voiceschanged", pick); }
    function clean(t) { return t.replace(/[“”]/g, '"').replace(/\s+/g, " ").trim(); }
    // Chrome drops speech queued right after cancel() and cuts long text, so
    // the message is read sentence by sentence after a short pause, and the
    // pieces are kept referenced until they're spoken.
    let queue = [];
    function say(text) {
      if (!ok) return;
      speechSynthesis.cancel();
      const parts = clean(text).match(/[^.!?]+[.!?]*["')]*\s*/g) || [clean(text)];
      const v = chosen || pick();
      queue = parts.map(p => p.trim()).filter(Boolean).map(p => {
        const u = new SpeechSynthesisUtterance(p);
        if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = "en-US"; }
        u.rate = 1; u.pitch = 1.05;
        return u;
      });
      const mine = queue;
      setTimeout(() => {
        if (queue !== mine) return;
        speechSynthesis.resume();
        mine.forEach(u => speechSynthesis.speak(u));
      }, 80);
    }
    function stop() { queue = []; if (ok) speechSynthesis.cancel(); }
    return { ok, say, stop, name: () => (chosen || pick() || {}).name || "" };
  })();
  function readAloudOn() { return !!(S.prefs && S.prefs.readAloud); }
  function renderReadAloud() {
    const b = $("read-btn");
    if (!b) return;
    b.hidden = !voice.ok || !chat || chat.mode !== "training";
    b.textContent = readAloudOn() ? "Read aloud: on" : "Read aloud: off";
    b.setAttribute("aria-pressed", readAloudOn() ? "true" : "false");
    b.title = voice.name() ? "Voice: " + voice.name() : "";
  }

  function tick() {
    if (!chat) return;
    const s = Math.floor(counting() ? liveCounted() : (Date.now() - chat.startedAt) / 1000);
    $("clock").textContent = Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") + (chat.paused ? " · on a break" : "");
    $("clock").title = counting() ? "Counted time. A pause over " + Math.round(IDLE / 60) + " minutes isn't counted beyond " + Math.round(IDLE / 60) + " minutes." : "";
    $("clock").classList.toggle("late", s >= 17 * 60);
  }

  function openChat(title, railTitle, railSub, how) {
    $("chat-title").textContent = title;
    $("rail-title").textContent = railTitle;
    $("rail-sub").textContent = railSub;
    $("rail-how").replaceChildren(...how.map(h => el("li", {}, h)));
    $("log").replaceChildren();
    $("say").hidden = false;
    $("msg").value = "";
    $("status").textContent = "";
    show("chat");
    renderReadAloud();
    if ($("break-btn")) { $("break-btn").hidden = !counting(); $("break-btn").textContent = "Take a break"; }
    clearInterval(clockTimer);
    clockTimer = setInterval(tick, 1000);
    tick();
  }

  function renderRail() {
    const ul = $("rail-modules");
    ul.replaceChildren();
    if (!chat || chat.mode !== "training") { ul.hidden = true; return; }
    ul.hidden = false;
    const c = courseBy(chat.course);
    c.pills.forEach(p => ul.append(el("li", { class: S.progress.understood[p.id] ? "ok" : "", title: p.known }, p.title)));
    if (c.test_count) ul.append(el("li", { class: testPassed(c) ? "ok" : "" }, "Short test"));
    (c.practical || []).forEach(x => ul.append(el("li", { class: "practical", title: x.visible }, "With your lead: " + x.title)));
    $("rail-sub").textContent = c.subtitle + " · " + doneCount(c) + "/" + c.pills.length + " modules done";
    $("rail-guides").replaceChildren(...guideLinks(c));
    $("rail-guides").parentElement.hidden = !(c.guides || []).length;
  }

  function keepInterview() {
    if (!CAND) return;
    try { localStorage.setItem("rfInterview." + CAND.id, JSON.stringify({ history: chat.history, startedAt: chat.startedAt })); } catch (e) { /* ignore */ }
  }

  async function turn(userText, shown) {
    if (chat.busy || chat.closed) return;
    if (chat.paused) resumeBreak();
    markActive();
    // The session's counted time is up (20 minutes; the management course sets its own): the Trainer closes on this turn.
    const timeUp = counting() && userText !== null && minutes() >= SESSION_MIN;
    chat.busy = true;
    chat.waiting = true;
    $("send").disabled = true;
    if (userText !== null) {
      chat.history.push({ role: "user", text: "[" + minutes() + " min]\n" + userText
        + (timeUp ? "\n\n(Note to the AI: the " + SESSION_MIN + " minutes are up. Answer briefly, take stock in one sentence and close now.)" : "") });
      addMsg("s", shown || userText, "You");
    }
    const typing = addMsg("t typing", "…", chat.aiName);
    $("status").textContent = chat.aiName + " is writing…";
    try {
      const body = CAND ? { history: chat.history } : {
        mode: "training", module_id: chat.course, history: chat.history, profile: chat.profile, session: chat.startedAt,
        progress: { understood: S.progress.understood, sessions: chat.anySessions || 0, last_note: S.progress.last_note[chat.course] || "" },
      };
      let data = null;
      for (let attempt = 0; ; attempt++) {
        try {
          data = await api(CAND ? "/api/i/" + CAND.id + "/turn" : "api/turn", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
          });
          break;
        } catch (err) {
          if (!err.busy || attempt >= 3) throw err;
          const wait = [8, 15, 25][attempt];
          typing.querySelector("p").textContent = "The Trainer is busy for a moment. Trying again in " + wait + " seconds…";
          await sleep(wait * 1000);
          typing.querySelector("p").textContent = "…";
        }
      }
      typing.remove();
      markActive(); chat.waiting = false;
      if (data.text) {
        chat.history.push({ role: "assistant", text: data.text });
        addMsg("t", data.text, chat.aiName);
        if (!CAND && readAloudOn()) voice.say(data.text);
      }
      keepInterview();
      (data.events || []).forEach(handleEvent);
      if (CAND && data.finished) finishInterview();
    } catch (err) {
      typing.remove();
      if (chat) { markActive(); chat.waiting = false; }
      addMsg("note", "The AI didn't answer (" + err.message + "). Try sending again.");
      if (userText !== null) chat.history.pop();
    } finally {
      if (chat) {
        chat.busy = false;
        chat.waiting = false;
        $("send").disabled = false;
        $("status").textContent = "";
        if (!chat.closed) $("msg").focus();
        if (timeUp && !chat.closed) {
          const last = [...chat.history].reverse().find(h => h.role === "assistant");
          if (last) { S.progress.last_note[chat.course] = last.text.slice(0, 600); save(); }
          closeChat("Twenty minutes: that's the session.");
        }
      }
    }
  }

  // A declared break: the clock stops, and the break is kept apart.
  function resumeBreak() {
    if (!chat || !chat.paused) return;
    chat.breaks += (Date.now() - chat.paused) / 1000;
    chat.paused = null;
    chat.lastMark = Date.now();
    $("break-btn").textContent = "Take a break";
    $("msg").disabled = false;
    tick();
  }
  if ($("break-btn")) $("break-btn").addEventListener("click", () => {
    if (!counting() || chat.closed) return;
    if (chat.paused) { resumeBreak(); return; }
    markActive();
    chat.paused = Date.now();
    $("break-btn").textContent = "Resume";
    $("msg").disabled = true;
    tick();
  });

  function handleEvent(ev) {
    const i = ev.input || {};
    if (ev.tool === "finish_interview") {
      finishInterview();
    } else if (ev.tool === "pill_understood" && MODS[i.pill_id]) {
      const first = !S.progress.understood[i.pill_id];
      S.progress.understood[i.pill_id] = { evidence: i.evidence || "", source: "training", date: today() };
      save(); renderRail();
      const c = courseBy(chat.course);
      if (first && modulesDone(c)) setTimeout(() => modulesFinished(c), 900);
    } else if (ev.tool === "log_referral") {
      S.progress.referrals.push({ type: i.type, question: i.question, course: chat.course, date: today() });
      save();
    }
  }

  $("say").addEventListener("submit", e => {
    e.preventDefault();
    const t = $("msg").value.trim();
    if (!t) return;
    $("msg").value = "";
    turn(t);
  });
  $("msg").addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("say").requestSubmit(); }
  });
  if ($("read-btn")) $("read-btn").addEventListener("click", () => {
    S.prefs = S.prefs || {};
    S.prefs.readAloud = !readAloudOn();
    save();
    renderReadAloud();
    // Starting speech from the tap unlocks it on phones; read the last message.
    if (readAloudOn()) {
      const last = chat && [...chat.history].reverse().find(h => h.role === "assistant");
      voice.say(last ? last.text : "Read aloud is on.");
    } else voice.stop();
  });

  $("end-btn").addEventListener("click", async () => {
    if (!chat || chat.closed || chat.busy) return;
    if (CAND) {
      if (!confirm("End the interview now? You won't be able to continue it.")) return;
      await turn("(The interview has to stop here. Please close now.)", "I need to stop here.");
      if (chat && !chat.closed) finishInterview();
    } else {
      await turn("(I need to stop here for today. Please close the session.)", "I need to stop here for today.");
      const last = [...chat.history].reverse().find(h => h.role === "assistant");
      if (last) { S.progress.last_note[chat.course] = last.text.slice(0, 600); save(); }
      closeChat("Session saved. Pick it up any time from the course.");
    }
  });

  function closeChat(msg) {
    const counted = reportTime();
    chat.closed = true;
    clearInterval(clockTimer);
    $("say").hidden = true;
    if ($("break-btn")) $("break-btn").hidden = true;
    const time = counted != null ? " This session: " + fmtMin(counted) + " counted. This " + (MGMT ? "module" : "unit") + " so far: " + fmtMin(S.progress.time[chat.course]) + ". The whole course: " + fmtMin(totalTime()) + "." : "";
    $("log").append(el("div", { class: "msg note" }, el("p", {}, msg + time + " "), el("button", { class: "ghost", type: "button", "data-go": "home" }, "Back to the " + TITLE)));
  }

  // ---------- the candidate's interview page ----------
  function finishInterview() {
    if (!chat || chat.closed) return;
    chat.closed = true;
    clearInterval(clockTimer);
    $("say").hidden = true;
    fetch("/api/i/" + CAND.id + "/finish", { method: "POST" }).catch(() => {});
    try { localStorage.removeItem("rfInterview." + CAND.id); } catch (e) { /* ignore */ }
    setTimeout(() => { chat = null; show("sel-done"); }, 4000);
  }

  function startInterview() {
    if (CAND.finished) { show("sel-done"); return; }
    let kept = null;
    try { kept = JSON.parse(localStorage.getItem("rfInterview." + CAND.id)); } catch (e) { /* ignore */ }
    chat = { mode: "selection", history: (kept && kept.history) || [], startedAt: (kept && kept.startedAt) || Date.now(), aiName: "RF One" };
    openChat("Interview", "Rome's Flavours", "Server · " + CAND.location, [
      "A few questions about your availability and your CV, then some real situations on a shift.",
      "Answer the way you really would. There are no trick questions.",
      "It's fine to say you don't know. Any language is fine.",
      "About 15 minutes. The AI doesn't decide: the hiring team reads your answers.",
    ]);
    renderRail();
    if (chat.history.length) {
      chat.history.forEach(h => h.role === "assistant" ? addMsg("t", h.text, chat.aiName) : addMsg("s", h.text.replace(/^\[\d+ min\]\n/, ""), "You"));
    } else {
      turn(null);
    }
  }

  if (CAND) { startInterview(); return; }

  // The new hire's link, for the hiring team to copy and send.
  if ($("tr-link")) {
    $("tr-link").value = location.origin + $("tr-link").dataset.path;
    $("tr-copy").addEventListener("click", () => {
      $("tr-link").select();
      (navigator.clipboard ? navigator.clipboard.writeText($("tr-link").value) : Promise.reject()).catch(() => document.execCommand("copy"));
      $("tr-copy").textContent = "Copied";
      setTimeout(() => { $("tr-copy").textContent = "Copy link"; }, 1500);
    });
  }

  // Training activity, for the hiring team: who opened it and how far they got.
  async function renderActivity() {
    const out = $("tr-activity");
    if (!out) return;
    let rows;
    try { rows = (await api("/api/training-activity")).activity || []; }
    catch (e) { out.textContent = "Couldn't load the activity."; return; }
    if (!rows.length) { out.textContent = "Nobody has used the training yet."; return; }
    const when = iso => iso ? new Date(iso).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "";
    out.replaceChildren(...rows.map(r => {
      const courses = Object.values(r.courses || {}).sort((a, b) => a.n - b.n).map(c => {
        const t = c.test;
        const test = t ? " · test " + t.score + "/" + t.total + (t.passed ? " passed" : " not passed") + (t.tries > 1 ? " (" + t.tries + " tries)" : "") : "";
        return el("li", {}, (c.code ? "Unit " + c.code : "Course " + c.n) + ", " + c.title + ": " + c.modules_done + " of " + c.modules + " modules" + test + (c.seconds ? " · " + fmtMin(c.seconds) : ""));
      });
      const extra = [];
      if (r.guides) extra.push(r.guides + " guide" + (r.guides > 1 ? "s" : "") + " opened");
      if (r.certificate) extra.push("certificate downloaded " + when(r.certificate.date));
      if (r.seconds) extra.unshift(fmtMin(r.seconds) + " of training counted" + (r.break_seconds ? " (" + fmtMin(r.break_seconds) + " of breaks, not counted)" : ""));
      return el("div", { class: "act" },
        el("b", {}, "Visitor " + r.id), " · " + r.source + " · " + r.device,
        el("div", {}, "First opened " + when(r.first) + " · last active " + when(r.last) + (r.visits ? " · " + r.visits + " visit" + (r.visits > 1 ? "s" : "") : "")),
        courses.length ? el("ul", {}, ...courses) : el("div", {}, "No course started yet."),
        extra.length ? el("div", {}, extra.join(" · ")) : "");
    }));
  }
  renderActivity();

  // ---------- home (hiring team) ----------
  async function renderHome() {
    const t = S.trainee;
    const completed = COURSES.filter(courseDone).length;
    $("overall").textContent = t ? (t.fullName || t.name) + " · " + t.location + " · " + completed + "/" + COURSES.length + (MGMT ? " modules done" : " units complete") + (totalTime() ? " · " + fmtMin(totalTime()) + " of training counted" : "") : "";
    if ($("total-time")) {
      const all = COURSES.reduce((a, c) => a + courseMinutes(c), 0);
      $("total-time").textContent = "The conversation part takes about " + fmtMin(all * 60) + " in all, in sessions of up to 20 minutes, plus the practical checks with your lead.";
    }
    if (!window.RF_TRAINEE) api("api/candidates").then(d => { $("cand-count").textContent = d.candidates.length ? "(" + d.candidates.length + ")" : ""; }).catch(() => {});

    const tb = $("trainee-box");
    tb.replaceChildren();
    if (HIRE) {
      // Their own link: nothing to fill in.
    } else if (!t) {
      const f = el("form", { class: "box trainee" },
        el("label", { for: "tr-name" }, "Who's training?"),
        el("input", { id: "tr-name", required: "", placeholder: "Name", autocomplete: "off" }),
        el("select", { id: "tr-loc" }, el("option", {}, "Winter Park"), el("option", {}, "Mount Dora")),
        el("button", { type: "submit" }, "Save"));
      f.addEventListener("submit", ev => {
        ev.preventDefault();
        S.trainee = { name: $("tr-name").value.trim(), location: $("tr-loc").value };
        save(); renderHome();
      });
      tb.append(f);
    } else {
      tb.append(el("p", { class: "small" }, el("button", { type: "button", class: "linkish", onclick: () => {
        if (confirm("Clear " + t.name + "'s training progress on this device?")) { S.trainee = null; S.progress = blank().progress; save(); renderHome(); }
      } }, "Switch person")));
    }

    const grid = $("course-grid");
    grid.replaceChildren();
    let level = null;
    COURSES.forEach((c, i) => {
      if (c.level !== level) {
        level = c.level;
        const lv = LEVELS.find(x => x.id === level) || { title: "" };
        grid.append(el("div", { class: "level-h" }, el("span", { class: "tag" }, MGMT ? "Management" : "Level " + level), el("h2", { class: "h2" }, lv.title), lv.question ? el("p", { class: "small" }, lv.question) : ""));
      }
      const done = doneCount(c), total = c.pills.length, complete = courseDone(c), testReady = modulesDone(c) && !complete;
      const missing = missingFor(c), locked = !isOpen(c);
      const after = missing.length > 2 ? "the earlier units" : missing.join(" and ");
      const chipText = complete ? (MGMT ? "Done ✓" : "Complete ✓") : locked ? (MGMT ? "After " + missing.map(unitLabel).join(" and ") : "After " + (missing.length > 2 ? "earlier units" : after)) : testReady ? "Test ready" : c.safety_critical ? "Safety first" : plural(total, partWord);
      const action = complete ? "Review" : locked ? "Opens after " + (MGMT ? missing.map(unitLabel).join(" and ") : after) : testReady ? "Take the test" : done ? "Continue" : (MGMT ? "Start" : "Start learning");
      const steps = total + (c.test_count ? 1 : 0), stepsDone = done + (c.test_count && testPassed(c) ? 1 : 0);
      const needTrainee = () => { if (!S.trainee) { $("tr-name").focus(); return true; } return false; };
      const card = el("article", { class: "course" + (complete ? " complete" : "") + (locked ? " locked" : "") },
        el("div", { class: "banner" }, el("span", { class: "art", "aria-hidden": "true", html: (window.RF_BANNERS || {})[c.banner || c.id] || "" }),
          el("span", { class: "chip" + (complete ? " done" : testReady ? " ready" : "") }, chipText)),
        el("div", { class: "body" },
          el("span", { class: "num" }, unitLabel(c.id)),
          el("h3", {}, c.title),
          el("span", { class: "small" }, c.subtitle),
          el("span", { class: "meta" }, MGMT ? "" : el("span", {}, "◷ about " + courseMinutes(c) + " min"), el("span", {}, "▤ " + done + "/" + total + " " + partWord + "s"),
            c.test_count ? el("span", {}, testPassed(c) ? "✓ test" : "✎ test") : "",
            (c.practical || []).length ? el("span", { title: c.practical.map(x => x.title).join(", ") }, "✋ " + plural(c.practical.length, "practical check") + " with your lead") : ""),
          el("span", { class: "progress" }, el("span", { style: "width:" + Math.round(100 * stepsDone / steps) + "%" })),
          el("button", Object.assign({ type: "button", class: complete ? "ghost" : "", onclick: () => {
            if (locked || needTrainee()) return;
            if (testReady) startTest(c.id); else startTraining(c.id);
          } }, locked ? { disabled: "" } : {}), action),
          complete && c.test_count ? el("button", { type: "button", class: "linkish", onclick: () => { if (!needTrainee()) startTest(c.id); } }, "Retake the test") : "",
          el("span", { class: "guides" }, ...guideLinks(c))));
      grid.append(card);
    });
  }

  // ---------- candidates: CVs in order ----------
  async function renderCandidates() {
    const box = $("cand-items");
    box.replaceChildren(el("p", { class: "small" }, "Loading…"));
    let rows = [];
    try { rows = (await api("api/candidates")).candidates; } catch (err) { box.replaceChildren(el("p", { class: "bad" }, err.message)); return; }
    box.replaceChildren();
    if (!rows.length) { box.append(el("p", { class: "small" }, "No CVs yet. Upload some above.")); return; }
    let n = 0;
    rows.forEach(r => {
      const out = r.stage === "Not moving on";
      const pos = out ? "–" : String(++n);
      box.append(el("button", { type: "button", class: "review-item cand" + (out ? " out" : ""), onclick: () => renderCandidate(r.id) },
        el("span", { class: "pos" }, pos),
        el("span", { class: "who" }, el("b", {}, r.name), el("span", { class: "small" }, r.location + " · " + r.source + " · " + dateOf(r.created))),
        el("span", { class: "chance c-" + (r.chance || "").split(" ")[0].toLowerCase() }, r.chance || ""),
        el("span", { class: "small" }, plural(r.flags, "red flag")),
        el("span", { class: "stage" }, r.stage + (r.interviewed ? " ✓" : ""))));
    });
  }

  $("cv-form").addEventListener("submit", async e => {
    e.preventDefault();
    const files = [...$("cv-files").files];
    if (!files.length) return;
    $("cv-go").disabled = true;
    const msgs = [];
    for (let i = 0; i < files.length; i++) {
      $("cv-msg").textContent = "Reading " + (i + 1) + " of " + files.length + ": " + files[i].name + "…";
      const fd = new FormData();
      fd.append("cv", files[i]); fd.append("source", $("cv-source").value); fd.append("location", $("cv-loc").value);
      try { await api("api/candidates", { method: "POST", body: fd }); } catch (err) { msgs.push(err.message); }
    }
    $("cv-go").disabled = false;
    $("cv-files").value = "";
    $("cv-msg").textContent = msgs.length ? msgs.join(" ") : "Done. The list below is in order.";
    renderCandidates();
  });

  // ---------- one candidate ----------
  let current = null;
  let reviewTimer = null;
  function saveReview() {
    clearTimeout(reviewTimer);
    reviewTimer = setTimeout(() => api("api/candidates/" + current.id, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ review: current.review }),
    }).catch(err => { $("rv-msg").textContent = "Not saved: " + err.message; }), 600);
  }

  async function renderCandidate(id) {
    try { current = (await api("api/candidates/" + id)).candidate; } catch (err) { alert(err.message); return; }
    current.review = current.review || {};
    const iv = current.interview || {};
    current.evidence = iv.evidence || {};
    const s = current.screen || {};
    show("candidate");
    $("rv-name").textContent = current.name;
    $("rv-title").textContent = current.name;
    $("rv-meta").textContent = [current.location, current.source, "applied " + dateOf(current.created), current.email, current.phone].filter(Boolean).join(" · ");
    $("rv-cv").href = "candidates/" + current.id + "/cv";
    $("rv-msg").textContent = "";
    $("rv-confirm").checked = false;

    // Stage and link
    const st = $("rv-stage");
    st.replaceChildren(...window.RF_STAGES.map(x => el("option", {}, x)));
    st.value = current.stage;
    st.onchange = () => api("api/candidates/" + current.id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stage: st.value }) })
      .then(() => { current.stage = st.value; }).catch(err => alert(err.message));
    const link = location.origin + "/i/" + current.id;
    $("rv-link").value = link;
    $("rv-copy").onclick = async () => {
      try { await navigator.clipboard.writeText(link); } catch (e) { $("rv-link").select(); document.execCommand("copy"); }
      $("rv-copy").textContent = "Copied";
      setTimeout(() => { $("rv-copy").textContent = "Copy link"; }, 1500);
      if (["New", "Called"].includes(current.stage)) { st.value = "Interview link sent"; st.onchange(); }
    };

    // CV screening
    $("rv-chance").textContent = (s.chance || "") + " · score " + (s.total || 0);
    $("rv-fit").textContent = s.fit_note || "";
    $("rv-strengths").replaceChildren(...(s.strengths || []).map(x => el("li", {}, x)));
    $("rv-flags").replaceChildren(...(s.red_flags || []).map(f => el("li", {}, el("b", {}, f.flag), el("span", { class: "small" }, " Question: " + f.question))));
    if (!(s.red_flags || []).length) $("rv-flags").append(el("li", { class: "small" }, "None found."));
    $("rv-crit").replaceChildren(...window.RF_CRITERIA.map(c => {
      const v = (s.criteria || {})[c.id] || {};
      const lvl = (s.levels || {})[c.id] || 0;
      return el("tr", {}, el("td", {}, c.name + (c.direction < 0 ? " (counts against)" : "")), el("td", { class: "num" }, lvl + "/4"),
        el("td", { class: "small" }, v.evidence || ""), el("td", { class: "num small" }, "x" + c.coefficient));
    }));
    $("rv-summary").textContent = s.cv_summary || "";

    // Interview
    const has = iv.started;
    $("rv-iv-none").hidden = !!has;
    $("rv-iv").hidden = !has;
    if (has) {
      const mins = iv.finished ? Math.max(1, Math.round((new Date(iv.finished) - new Date(iv.started)) / 60000)) : null;
      $("rv-iv-meta").textContent = iv.finished ? "Done " + dateOf(iv.finished) + " · " + mins + " min" : "Started " + dateOf(iv.started) + ", not finished yet";
      $("rv-note").textContent = iv.note ? "AI's note on the conversation: " + iv.note : "";
      $("rv-checks").replaceChildren(...(current.checks_asked || []).map(ch => {
        const a = (iv.checks || {})[ch.id] || { status: "NOT_ASKED" };
        return el("div", { class: "box rv" },
          el("div", { class: "rv-head" }, el("b", {}, ch.id === "availability" ? "Availability" : "From the CV"), el("span", { class: "pillstatus s-" + a.status }, CHECK[a.status] || a.status)),
          el("p", { class: "small" }, ch.ask.replace(/^Availability: |^From the CV: /, "")),
          a.quote ? el("blockquote", {}, "“" + a.quote + "”") : "",
          a.note ? el("p", { class: "small" }, a.note) : "");
      }));
    }
    const box = $("rv-modules");
    box.replaceChildren();
    SEL.forEach((c, i) => {
      const asked = c.pills.filter(p => current.evidence[p.id]);
      box.append(el("h2", { class: "mod-h" }, "Course " + (i + 1) + ": " + c.title + (c.safety_critical ? " · always taught" : "")));
      (asked.length ? asked : []).forEach(p => box.append(moduleReview(p)));
      const rest = c.pills.filter(p => !current.evidence[p.id]);
      if (rest.length) box.append(el("p", { class: "small" }, "Not asked in the interview: " + rest.map(p => p.title).join(", ") + "."));
    });
    renderPlan();
  }

  function moduleReview(p) {
    const ev = current.evidence[p.id] || { status: "NOT_ASSESSED" };
    const rv = current.review[p.id] || (current.review[p.id] = {});
    const scoreSel = el("select", { "aria-label": "Score for " + p.title },
      el("option", { value: "" }, "Not evaluated"), ...[1, 2, 3, 4, 5].map(n => el("option", { value: String(n) }, String(n))));
    scoreSel.value = rv.score || "";
    const catSel = el("select", { "aria-label": "Category for " + p.title },
      el("option", { value: "" }, "Category…"), ...Object.entries(CATS).map(([k, v]) => el("option", { value: k }, v)));
    catSel.value = rv.category || "";
    const reason = el("input", { placeholder: "Your reason (required with a score)", value: rv.reason || "" });
    function upd() {
      rv.score = scoreSel.value; rv.category = catSel.value; rv.reason = reason.value.trim();
      reason.classList.toggle("need", !!rv.score && !rv.reason);
      saveReview(); renderPlan();
    }
    [scoreSel, catSel].forEach(s => s.addEventListener("change", upd));
    reason.addEventListener("input", upd);
    reason.classList.toggle("need", !!rv.score && !rv.reason);
    return el("div", { class: "box rv" },
      el("div", { class: "rv-head" }, el("b", {}, "Module: " + p.title), el("span", { class: "pillstatus s-" + ev.status }, STATUS[ev.status] || ev.status)),
      el("p", { class: "small" }, "Situation: " + p.scenario),
      el("p", { class: "small" }, el("b", {}, "Shown when: "), p.known),
      ev.quote ? el("blockquote", {}, "“" + ev.quote + "”") : el("p", { class: "small" }, "No answer on this module."),
      ev.missing ? el("p", { class: "small" }, "Not in the answer: " + ev.missing) : "",
      el("div", { class: "rv-inputs" }, scoreSel, catSel, reason));
  }

  // The Server Course has one path for everyone (Pino's master course): what
  // the interview showed lets the Trainer go faster, it doesn't skip units.
  function planFor() { return COURSES; }
  function renderPlan() {
    $("rv-plan").replaceChildren(el("p", { class: "small" }, "The Server Course, in order: " + COURSES.length + " units, from " + COURSES[0].id + " to " + COURSES[COURSES.length - 1].id + ". Where the interview already showed something, the Trainer shortens the explanation and keeps the checks."));
  }

  $("rv-delete").addEventListener("click", async () => {
    if (!confirm("Delete " + current.name + "'s CV and interview? This can't be undone.")) return;
    try { await api("api/candidates/" + current.id, { method: "DELETE" }); show("candidates"); } catch (err) { alert(err.message); }
  });

  $("rv-handoff").addEventListener("click", () => {
    const missing = Object.entries(current.review).filter(([, r]) => r.score && !r.reason).length;
    if (missing) { $("rv-msg").textContent = "Add a reason to every module you scored first."; return; }
    if (!$("rv-confirm").checked) { $("rv-msg").textContent = "Tick the trainer confirmation first."; return; }
    api("api/hires", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: current.name, location: current.location || "Winter Park" }) })
      .then(d => {
        api("api/candidates/" + current.id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ stage: "Hired" }) }).catch(() => {});
        renderHire(d.id);
      })
      .catch(err => { $("rv-msg").textContent = err.message; });
  });

  // ---------- training ----------
  function startTraining(courseId) {
    const c = courseBy(courseId);
    const anySessions = Object.values(S.progress.sessions).reduce((a, b) => a + b, 0);
    chat = { mode: "training", course: courseId, history: [], startedAt: Date.now(), aiName: "Trainer",
      profile: { name: S.trainee.name, location: S.trainee.location },
      counted: 0, breaks: 0, lastMark: Date.now(), waiting: false, paused: null, reported: false, anySessions };
    openChat(unitLabel(c.id) + ": " + c.title, unitLabel(c.id) + ": " + c.title, c.subtitle, MGMT ? [
      "Answer the way you really would. Any language is fine, short answers are fine.",
      "There's no right answer to guess: we look at the reasoning.",
      "Each part is ticked once we've worked it through. The real task happens in your own work: come back and tell the Trainer how it went. You can start the next module before that.",
      "A pause longer than " + Math.round(IDLE / 60) + " minutes isn't counted beyond " + Math.round(IDLE / 60) + " minutes; use Take a break for a real break.",
    ] : [
      "Answer the way you really would. Any language is fine.",
      "Each module is ticked when you show it in your own words.",
      "Sessions are up to 20 minutes of counted time. A pause longer than " + Math.round(IDLE / 60) + " minutes isn't counted beyond " + Math.round(IDLE / 60) + " minutes; use Take a break for a real break.",
      "Then a short test. Practical checks are done in person with your lead.",
    ]);
    renderRail();
    if (modulesDone(c)) addMsg("note", courseDone(c) ? "This unit is already complete. You can still review it with the Trainer."
      : "Every module in this unit is done. You can review with the Trainer, or go back and take the test.");
    turn(null).then(() => { S.progress.sessions[courseId] = (S.progress.sessions[courseId] || 0) + 1; save(); });
  }

  // ---------- celebration ----------
  function celebrate(c) {
    const completed = COURSES.filter(courseDone).length;
    const next = nextCourse();
    $("cel-title").textContent = c.title;
    $("cel-text").textContent = MGMT ? "Thank you, " + S.trainee.name + ". " + unitLabel(c.id) + " is done, " + completed + "/" + COURSES.length + " overall." + (next ? " Next: " + unitLabel(next.id) + ", " + next.title + "." : " That's the whole course.") :
      "Well done, " + S.trainee.name + ". You've completed unit " + c.id + ", and " + completed + "/" + COURSES.length + " units overall." +
      ((c.practical || []).length ? " Your lead will do its practical checks with you in person." : "") +
      (next ? " Next up: " + next.id + ", " + next.title + "." : " That's the whole conversation part of the Server Course. The practical checks and the decision about working tables alone are with your lead.");
    $("celebrate").hidden = false;
    confetti($("confetti"));
  }
  $("cel-close").addEventListener("click", () => {
    $("celebrate").hidden = true;
    if (chat && !chat.closed) closeChat("Course complete.");
    if (!$("v-test").hidden) show("home");
  });

  // The next course to work on: the first incomplete one in the trainer's
  // confirmed path (Guest safety first), then any other incomplete one.
  function nextCourse() {
    const plan = (S.trainee && S.trainee.plan) || [];
    return COURSES.find(x => plan.includes(x.id) && !courseDone(x) && isOpen(x)) || COURSES.find(x => !courseDone(x) && isOpen(x)) || COURSES.find(x => !courseDone(x)) || null;
  }

  // ---------- support documents ----------
  function guideLinks(c) {
    return (c.guides || []).map(g => el("a", { href: g.href, target: "_blank", rel: "noopener", class: "guide" }, "⤓ " + g.title + " (PDF)"));
  }

  // ---------- the short test at the end of each course ----------
  let test = null;
  function shuffled(a) { const b = a.slice(); for (let i = b.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [b[i], b[j]] = [b[j], b[i]]; } return b; }

  function modulesFinished(c) {
    if (testPassed(c)) { celebrate(c); return; }
    if (chat && !chat.closed) {
      chat.closed = true;
      clearInterval(clockTimer);
      $("say").hidden = true;
      $("log").append(el("div", { class: "msg note" },
        el("p", {}, "Every module in this unit is done. Last step: a short test, " + c.test_count + " questions, about two minutes."),
        el("button", { type: "button", onclick: () => { reportTime(); chat = null; startTest(c.id); } }, "Take the test now"), " ",
        el("button", { class: "ghost", type: "button", "data-go": "home" }, "Later")));
    }
  }

  async function startTest(courseId) {
    const c = courseBy(courseId);
    show("test");
    $("test-title").textContent = "Unit " + c.id + ": " + c.title;
    $("test-crumb").textContent = "Unit " + c.id + " test";
    $("test-rule").textContent = "";
    $("test-step").textContent = "";
    $("test-bar").style.width = "0%";
    $("test-box").replaceChildren(el("p", { class: "small" }, "Preparing your questions…"));
    let d;
    try { d = await api("api/test/" + c.id); }
    catch (err) {
      $("test-box").replaceChildren(el("p", {}, err.message), el("div", { class: "row" },
        err.data && err.data.needs_trainer ? el("button", { type: "button", onclick: () => startTraining(c.id) }, "Review with the Trainer") : "",
        el("button", { type: "button", class: "ghost", "data-go": "home" }, "Back to the " + TITLE)));
      return;
    }
    test = { course: c, d, i: 0, answers: {}, counted: 0, lastMark: Date.now() };
    $("test-rule").textContent = d.total + " questions. " + (d.safety
      ? "This is a safety unit: every answer has to be right to pass."
      : "Get " + d.pass_mark + " right to pass.") + " The questions change each time, and you'll see what to review at the end.";
    renderQuestion();
  }

  function renderQuestion() {
    const t = test, q = t.d.questions[t.i], box = $("test-box");
    $("test-step").textContent = "Question " + (t.i + 1) + " of " + t.d.questions.length;
    $("test-bar").style.width = Math.round(100 * t.i / t.d.questions.length) + "%";
    const opts = el("div", { class: "options", role: "group", "aria-label": "Answers" });
    q.options.forEach(o => opts.append(el("button", { type: "button", class: "option", onclick: () => {
      if (test !== t) return;
      const now = Date.now();
      t.counted += Math.min((now - t.lastMark) / 1000, IDLE); t.lastMark = now;
      t.answers[q.id] = o;
      t.i += 1;
      if (t.i < t.d.questions.length) renderQuestion(); else finishTest();
    } }, o)));
    box.replaceChildren(el("h2", { class: "q" }, q.q), opts);
    const first = opts.querySelector("button"); if (first) first.focus();
  }

  async function finishTest() {
    const t = test, c = t.course, box = $("test-box");
    $("test-bar").style.width = "100%";
    $("test-step").textContent = "Your result";
    box.replaceChildren(el("p", { class: "small" }, "Marking…"));
    const wasComplete = courseDone(c);
    let r;
    try {
      r = await api("api/test/" + c.id, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers: t.answers }) });
    } catch (err) {
      box.replaceChildren(el("p", {}, err.message), el("button", { type: "button", onclick: () => startTest(c.id) }, "Start the test again"));
      return;
    }
    const prev = S.progress.tests[c.id] || {};
    S.progress.tests[c.id] = Object.assign({}, prev, { score: r.score, total: r.total, passed: r.passed || !!prev.passed, date: today(), tries: (prev.tries || 0) + 1 });
    if (r.passed && allDone() && !S.progress.completed_at) S.progress.completed_at = new Date().toISOString();
    const testSec = Math.round(t.counted);
    S.progress.time[c.id] = (S.progress.time[c.id] || 0) + testSec;
    save();
    fetch("api/track", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "time", module_id: c.id, counted: testSec, breaks: 0 }) }).catch(() => {});
    const review = (r.missed || []).length ? el("div", { class: "review" },
      el("h2", { class: "h2" }, r.passed ? "One to go over" + (r.missed.length > 1 ? " (" + r.missed.length + ")" : "") : "To review before you try again"),
      el("ul", {}, ...r.missed.map(m => el("li", {}, el("b", {}, m.q), el("br"), m.why)))) : "";
    box.replaceChildren(
      el("div", { class: "result " + (r.passed ? "pass" : "fail") },
        el("div", { class: "score" }, r.score + "/" + r.total),
        el("h2", { class: "q" }, r.passed ? "Passed" : "Not passed yet"),
        el("p", {}, r.passed
          ? (modulesDone(c) ? "Well done. Unit " + c.id + " is complete." + ((c.practical || []).length ? " Its practical checks are done with your lead." : "") : "Well done. Finish the remaining modules to complete the unit.")
          : "You need " + r.pass_mark + " right" + (r.pass_mark === r.total ? ", every answer," : "") + " to pass." +
            (r.needs_trainer ? " Two tries in a row didn't pass, so the next step is a short session with the Trainer on this unit." : " Go over the points below, then try again: the questions change."))),
      review,
      el("div", { class: "row" },
        r.passed ? el("button", { type: "button", "data-go": "home" }, "Back to the " + TITLE)
          : r.needs_trainer ? el("button", { type: "button", onclick: () => startTraining(c.id) }, "Review with the Trainer")
          : el("button", { type: "button", onclick: () => startTest(c.id) }, "Try again"),
        r.passed ? "" : el("button", { type: "button", class: "ghost", "data-go": "home" }, "Back to the " + TITLE)),
      el("p", { class: "guides" }, ...guideLinks(c)));
    if (r.passed && !wasComplete && courseDone(c)) setTimeout(() => celebrate(c), 700);
  }

  // ---------- the team: named hires, practical checks, readiness ----------
  const PSTATUS = { demonstrated: "Demonstrated", repeat: "Repeat required", not_observed: "Not yet observed" };
  const signer = () => { try { return localStorage.getItem("rfTrainer.signer") || ""; } catch (e) { return ""; } };
  let hiresCache = [];

  async function renderHires() {
    const out = $("hire-list");
    if (!out) return;
    let d;
    try { d = await api("api/hires"); } catch (e) { out.textContent = "Couldn't load the new hires."; return; }
    hiresCache = d.hires;
    const rows = d.hires.filter(h => !h.archived);
    if (!rows.length) { out.replaceChildren(el("p", { class: "small" }, "No new hires yet. Add one above to get their link.")); return; }
    out.replaceChildren(...rows.map(h => el("button", { type: "button", class: "review-item hire", onclick: () => renderHire(h.id) },
      el("span", { class: "who" }, el("b", {}, h.name), el("span", { class: "small" }, h.location + (h.last ? " · last active " + new Date(h.last).toLocaleDateString() : " · not started"))),
      el("span", { class: "small" }, h.units_complete + "/" + d.units + (MGMT ? " modules" : " units")),
      MGMT ? el("span", { class: "small" }, plural((h.reasoning || []).length, "reasoning record")) : el("span", { class: "small" }, h.checks_done + "/" + h.checks_total + " practical" + (h.checks_repeat ? " · " + h.checks_repeat + " to repeat" : "")),
      el("span", { class: "small" }, fmtMin(h.seconds)),
      MGMT ? el("span", { class: "small" }, plural((h.work_notes || []).length, "process note")) : el("span", { class: "stage" + (h.ready && h.ready.value ? " ready" : "") }, h.ready && h.ready.value ? "Ready to work alone ✓" : "Not yet alone"))));
  }

  if ($("hire-form")) $("hire-form").addEventListener("submit", async e => {
    e.preventDefault();
    const name = $("hire-name").value.trim();
    if (!name) return;
    try {
      const d = await api("api/hires", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, location: $("hire-loc").value }) });
      $("hire-name").value = "";
      $("hire-msg").textContent = "Added. Their link is on their page: open it below and copy it.";
      await renderHires();
      renderHire(d.id);
    } catch (err) { $("hire-msg").textContent = err.message; }
  });

  async function renderHire(id) {
    let h = hiresCache.find(x => x.id === id);
    try { const d = await api("api/hires"); hiresCache = d.hires; h = d.hires.find(x => x.id === id); } catch (e) { /* use the cache */ }
    if (!h) { alert("Not found."); return; }
    show("hire");
    const patch = async body => {
      try { const d = await api("api/hires/" + id, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); return d.hire; }
      catch (err) { alert(err.message); return null; }
    };
    $("hr-name").textContent = h.name;
    $("hr-title").textContent = h.name;
    $("hr-meta").textContent = h.location + " · added " + dateOf(h.created) + (h.last ? " · last active " + new Date(h.last).toLocaleString() : " · hasn't opened the link yet") + (h.device ? " · " + h.device : "");
    $("hr-link").value = location.origin + h.link;
    $("hr-copy").onclick = async () => {
      try { await navigator.clipboard.writeText($("hr-link").value); } catch (e) { $("hr-link").select(); document.execCommand("copy"); }
      $("hr-copy").textContent = "Copied"; setTimeout(() => { $("hr-copy").textContent = "Copy link"; }, 1500);
    };
    $("hr-signer").value = signer();
    $("hr-signer").onchange = () => { try { localStorage.setItem("rfTrainer.signer", $("hr-signer").value.trim()); } catch (e) { /* ignore */ } };

    // Ready to work alone: only a lead signs it, and only when everything is done.
    const rb = $("hr-ready");
    const can = h.units_complete === h.units.length && h.checks_done === h.checks_total;
    const ready = h.ready && h.ready.value;
    rb.replaceChildren(el("h2", { class: "h2" }, "Ready to work tables alone?"),
      ready ? el("p", {}, el("b", {}, "Yes. "), "Signed by " + (h.ready.by || "a lead") + " on " + new Date(h.ready.date).toLocaleString() + (h.ready.note ? ". " + h.ready.note : "."))
        : el("p", { class: "small" }, can ? "Every unit and every practical check is complete. A lead can sign it below."
          : "Not yet. Still needed: " + [h.units_complete < h.units.length ? (h.units.length - h.units_complete) + " unit" + (h.units.length - h.units_complete > 1 ? "s" : "") + " (modules and test)" : "",
            h.checks_done < h.checks_total ? (h.checks_total - h.checks_done) + " practical check" + (h.checks_total - h.checks_done > 1 ? "s" : "") + " demonstrated" : ""].filter(Boolean).join(" and ") + ". Until it's signed, they work with a lead or a trainer server, never alone."
          + (h.ready && h.ready.note ? " (" + h.ready.note + ")" : "")),
      ready ? el("button", { type: "button", class: "ghost", onclick: async () => { if (confirm("Withdraw the sign-off?") && await patch({ ready: { value: false, by: $("hr-signer").value } })) renderHire(id); } }, "Withdraw")
        : can ? el("button", { type: "button", onclick: async () => {
            if (!$("hr-signer").value.trim()) { $("hr-signer").focus(); alert("Add your role first (for example 'Lead on shift')."); return; }
            if (confirm("Sign that " + h.name + " is ready to work tables alone?") && await patch({ ready: { value: true, by: $("hr-signer").value.trim() } })) renderHire(id);
          } }, "Sign: ready to work alone") : "");

    // Units: modules, test, time, and the practical checks to mark.
    $("hr-units").replaceChildren(...h.units.map(u => {
      const t = u.test || {};
      const testLine = t.tries ? "Test: " + (t.passed ? "passed" : "not passed yet") + ", last " + t.score + "/" + t.total + ", best " + (t.best || t.score) + ", " + t.tries + " tr" + (t.tries > 1 ? "ies" : "y") : "Test: not taken";
      const missed = !t.passed && (t.missed || []).length ? el("p", { class: "small" }, el("b", {}, "Missed last time: "), t.missed.join(" · ")) : "";
      const checks = u.practical.map(x => {
        const sel = el("select", { "aria-label": x.title + " outcome" }, ...Object.entries(PSTATUS).map(([k, v]) => el("option", { value: k }, v)));
        sel.value = x.status || "not_observed";
        const note = el("input", { placeholder: "Note (the error to repeat, if any)", value: x.note || "", "aria-label": x.title + " note" });
        const btn = el("button", { type: "button", class: "small-btn" }, "Save");
        btn.addEventListener("click", async () => {
          if (sel.value === "repeat" && !note.value.trim()) { note.focus(); alert("Name the error to repeat."); return; }
          if (await patch({ practical: { unit: u.id, title: x.title, status: sel.value, note: note.value.trim(), by: $("hr-signer").value.trim() } })) renderHire(id);
        });
        return el("div", { class: "check-row" }, el("div", {}, el("b", {}, x.title), el("span", { class: "small" }, " " + x.visible),
          x.date ? el("div", { class: "small" }, PSTATUS[x.status] + (x.by ? " · " + x.by : "") + " · " + new Date(x.date).toLocaleDateString()) : ""),
          el("div", { class: "row" }, sel, note, btn));
      });
      return el("div", { class: "box rv" + (u.complete ? " done" : "") },
        el("div", { class: "rv-head" }, el("b", {}, unitLabel(u.id) + ": " + u.title), el("span", { class: "pillstatus " + (u.complete ? "s-EVIDENCED" : u.modules_done ? "s-PARTIAL" : "s-NOT_ASSESSED") }, u.complete ? "Complete" : u.modules_done + "/" + u.modules + " modules")),
        el("p", { class: "small" }, (MGMT ? "" : testLine) + (u.seconds ? (MGMT ? "" : " · ") + fmtMin(u.seconds) : "")), missed, ...checks);
    }));

    // Time: counted, with corrections.
    const mins = el("input", { type: "number", placeholder: "Minutes, + or -", "aria-label": "Minutes to add or remove", style: "max-width:9em" });
    const why = el("input", { placeholder: "Reason (for example: reading the guide, a technical problem)", "aria-label": "Reason" });
    $("hr-time").replaceChildren(el("h2", { class: "h2" }, "Training time"),
      el("p", {}, fmtMin(h.seconds) + " counted" + (h.time_adjustments.length ? ", including corrections" : "") + "."),
      h.time_adjustments.length ? el("ul", { class: "small" }, ...h.time_adjustments.map(a => el("li", {}, (a.seconds > 0 ? "+" : "") + Math.round(a.seconds / 60) + " min: " + a.reason + (a.by ? " (" + a.by + ")" : "") + ", " + new Date(a.date).toLocaleDateString()))) : "",
      el("p", { class: "small" }, "Correct the time when something counted wrongly (Pino's course: time records must be correctable)."),
      el("div", { class: "row" }, mins, why, el("button", { type: "button", onclick: async () => {
        if (await patch({ time_adjust: { minutes: mins.value, reason: why.value, by: $("hr-signer").value.trim() } })) renderHire(id);
      } }, "Add correction")));

    if (MGMT) renderEvidence(h);

    // Questions the Trainer sent to a lead.
    $("hr-refs").replaceChildren(el("h2", { class: "h2" }, "Questions for a lead"),
      h.referrals.length ? el("ul", { class: "small" }, ...h.referrals.slice().reverse().map(r => el("li", {}, "Unit " + r.unit + " · " + r.type + ": " + r.question + " (" + new Date(r.date).toLocaleDateString() + ")")))
        : el("p", { class: "small" }, "None yet. When the Trainer says a detail comes from the lead, the question shows up here."));
    $("hr-archive").textContent = h.archived ? "Bring back to the list" : "Archive (remove from the list)";
    $("hr-archive").onclick = async () => { if (await patch({ archived: !h.archived })) show("home"); };
  }

  // ---------- management course: the evidence it keeps ----------
  const CHAR_NAMES = ["", "Understanding the objective", "Accountability and reliability", "Technical competence", "Quality of reasoning and decisions",
    "Planning and prioritization", "Ability to deliver results", "Resource stewardship and economic value", "Quality and verification", "Communication",
    "Collaboration and delegation", "Transparency and respect", "Learning and development", "Self-management and readiness for work",
    "Managing emotional reactions and difficult situations", "Initiative and ownership", "Customer and reputation", "Safety and compliance"];
  const KIND_LABEL = { "simulation": "Training evidence (simulation)", "self-reported real work": "Real work, self-reported, not verified", "own account": "Their own account" };

  function renderEvidence(h) {
    const rs = h.reasoning || [], ws = h.work_notes || [];
    $("hr-reasoning").replaceChildren(el("h2", { class: "h2" }, "Reasoning (for People)"),
      el("p", { class: "small" }, "Training evidence, kept separate from real work. No score. Characteristics by the numbers in the Manager Model."),
      rs.length ? el("div", { class: "stack" }, ...rs.slice().reverse().map(r => el("div", { class: "box rv" },
        el("div", { class: "rv-head" }, el("b", {}, unitLabel(r.unit) + " · " + ((MODS[r.module] || {}).title || r.module)), el("span", { class: "small" }, KIND_LABEL[r.kind] || r.kind)),
        el("p", { class: "small" }, "Characteristics: " + (r.characteristics || []).map(n => n + " " + CHAR_NAMES[n]).join(", ")),
        el("p", {}, "\u201C" + r.quote + "\u201D"),
        r.included ? el("p", { class: "small" }, el("b", {}, "Included: "), r.included) : "",
        r.missing ? el("p", { class: "small" }, el("b", {}, "Not yet in the reasoning: "), r.missing) : "",
        el("p", { class: "small" }, new Date(r.date).toLocaleString()))))
        : el("p", { class: "small" }, "Nothing yet. Each case, card and real task adds one record once it's worked through."));
    $("hr-work").replaceChildren(el("h2", { class: "h2" }, "How the work runs (for Organization, to verify)"),
      el("p", { class: "small" }, "What they described about how a process actually works here, without names. Current reality to check against the procedures, never an approved procedure on its own."),
      ws.length ? el("ul", { class: "small" }, ...ws.slice().reverse().map(w => el("li", {}, el("b", {}, w.process + ": "), w.described + " (" + w.source + ", " + new Date(w.date).toLocaleDateString() + ")")))
        : el("p", { class: "small" }, "Nothing yet."));
  }

  // ---------- certificate of completion ----------
  function completionDate() {
    if (S.progress.completed_at) return S.progress.completed_at;
    const isos = COURSES.map(c => (S.progress.tests[c.id] || {}).iso).filter(Boolean).sort();
    return isos[isos.length - 1] || new Date().toISOString();
  }
  function localISO(iso) { const d = new Date(iso); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }

  function renderCertificateBox() {
    const box = $("cert-box");
    box.replaceChildren();
    const t = S.trainee;
    if (!t) { box.hidden = true; return; }
    box.hidden = false;
    const completed = COURSES.filter(courseDone).length;
    if (!allDone()) {
      box.className = "cert-box pending";
      box.append(el("div", { class: "cert-icon", "aria-hidden": "true" }, "★"),
        el("div", {}, el("b", {}, "Rome's Flavours Academy certificate"),
          el("p", { class: "small" }, "Complete every course and its short test to receive your certificate of completion. " + completed + " of " + COURSES.length + " done.")));
      return;
    }
    const when = completionDate();
    const nameIn = el("input", { id: "cert-name", value: t.fullName || t.name, "aria-label": "Name on the certificate", maxlength: "60" });
    const msg = el("p", { class: "small" });
    const btn = el("button", { type: "button" }, "Download my certificate (PDF)");
    btn.addEventListener("click", async () => {
      const name = nameIn.value.trim();
      if (!name) { nameIn.focus(); return; }
      if (name !== t.fullName) { t.fullName = name; save(); }
      btn.disabled = true; msg.textContent = "Preparing your certificate…";
      try {
        const r = await fetch("certificate.pdf", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, date: localISO(when), location: t.location }) });
        if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "Something went wrong (" + r.status + ").");
        const url = URL.createObjectURL(await r.blob());
        const a = el("a", { href: url, download: "Rome's Flavours Academy certificate - " + name + ".pdf" });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        msg.textContent = "Downloaded. Congratulations!";
      } catch (err) { msg.textContent = err.message; } finally { btn.disabled = false; }
    });
    box.className = "cert-box done";
    box.append(el("div", { class: "cert-icon", "aria-hidden": "true" }, "★"),
      el("div", { class: "cert-main" },
        el("span", { class: "tag" }, "Server Training complete · " + new Date(when).toLocaleDateString()),
        el("h2", { class: "h2" }, "Congratulations, " + t.name + "!"),
        el("p", { class: "small" }, "You've completed every course and test of the Server Training program. Download your certificate of completion from Rome's Flavours Academy."),
        el("label", { for: "cert-name" }, "Name on the certificate"),
        el("div", { class: "row" }, nameIn, btn), msg));
  }

  function confetti(canvas) {
    const ctx = canvas.getContext("2d");
    const W = canvas.width = window.innerWidth, H = canvas.height = window.innerHeight;
    const colors = ["#5d6d2f", "#7c8f52", "#c7d1a8", "#b23a26", "#e2b33c", "#ffffff", "#2e7d4f"];
    const parts = Array.from({ length: 180 }, () => ({
      x: W / 2 + (Math.random() - 0.5) * W * 0.3, y: H * 0.35,
      vx: (Math.random() - 0.5) * 16, vy: -Math.random() * 16 - 4,
      r: Math.random() * 6 + 4, c: colors[Math.floor(Math.random() * colors.length)],
      a: Math.random() * Math.PI, va: (Math.random() - 0.5) * 0.3,
    }));
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let frames = reduce ? 199 : 0;
    (function step() {
      ctx.clearRect(0, 0, W, H);
      parts.forEach(p => {
        p.vy += 0.35; p.vx *= 0.99; p.x += p.vx; p.y += p.vy; p.a += p.va;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.a); ctx.fillStyle = p.c;
        ctx.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / 2); ctx.restore();
      });
      if (++frames < 200) requestAnimationFrame(step); else ctx.clearRect(0, 0, W, H);
    })();
  }

  // ?preview=test opens a test and ?preview=celebrate the course-complete
  // screen, for checking the design.
  if (!window.RF_TRAINEE && new URLSearchParams(location.search).get("preview") === "test") {
    S.trainee = S.trainee || { name: "Preview", location: "Winter Park" };
    setTimeout(() => startTest(COURSES[1].id), 300);
  }
  if (!window.RF_TRAINEE && new URLSearchParams(location.search).get("preview") === "celebrate") {
    S.trainee = S.trainee || { name: "Preview", location: "Winter Park" };
    setTimeout(() => celebrate(COURSES[1]), 300);
  }
  show("home");
  renderHires();
  syncFromServer();
})();
