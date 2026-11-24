// TraceLens live fix view. One page, two sources of events:
//   live:   EventSource(<events url>) while `tracelens fix --watch` runs on your machine
//   replay: a recorded events.json, played back with its real pacing, sped up
// Text from events is inserted with textContent; the only HTML inserted is the timeline SVG that
// TraceLens itself rendered from the trace.
(function () {
  "use strict";
  const root = document.getElementById("live");
  if (!root) return;
  const MODE = root.dataset.mode, URL_ = root.dataset.events;
  const $ = (id) => document.getElementById(id);
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  const STAGE_TEXT = {
    record_before: "Recording the original program on the QNX target",
    diagnose: "Reading the recordings to find the cause",
    patch: "Writing the QNX-specific fix",
    build: "Building the fixed program with qcc",
    record_after: "Recording the fixed program on the QNX target",
    verdict: "Comparing before and after",
  };
  const STAGE_LABEL = { record_before: "Record the original", diagnose: "Find the cause", patch: "Write the fix",
    build: "Build with qcc", record_after: "Record the fixed program", verdict: "Compare before and after" };
  const STATUS = {
    VERIFIED: ["Fixed and verified", "ok"], "NOT FIXED": ["Not fixed", "bad"], INCONCLUSIVE: ["No verdict: record again", "warn"],
    GUIDED: ["Fix by hand: lines shown", "info"], "NOTHING TO FIX": ["Nothing to fix", "ok"], "BUILD FAILED": ["The fix did not build", "bad"],
  };

  let S = { runs: 5, files: {}, file: null, base: "", fixed: "", marks: new Set(), changed: new Set(), diff: "", stages: [], cur: null, points: [], metric: null, done: false };

  // ------------------------------------------------------------------ status line
  function setStatus(text, cls) {
    const p = $("lv-status"); p.textContent = text; p.className = "pill " + (cls || "st-info") + (S.done ? "" : " busy");
  }
  const NAMES = { z1_infusion_pump: "infusion pump", z2_brake_by_wire: "brake-by-wire", z3_sensor_fusion: "sensor fusion",
    z4_camera_pipeline: "camera pipeline", z5_motor_encoder: "motor encoder" };
  function say(text) { $("lv-now").textContent = text; }
  function log(text) {
    const li = el("li", null, text); const box = $("lv-log"); box.prepend(li);
    while (box.children.length > 80) box.lastChild.remove();
  }

  // ------------------------------------------------------------------ stepper
  function stepKey(stage, round) { return stage + ":" + round; }
  function addStep(stage, round) {
    const key = stepKey(stage, round);
    if (S.stages.includes(key)) return;
    S.stages.push(key);
    const li = el("li", "todo"); li.dataset.key = key;
    li.append(el("span", "dot"), el("span", "lbl", STAGE_LABEL[stage] + (round > 1 && stage !== "record_before" ? " (round " + round + ")" : "")));
    $("lv-steps").append(li);
  }
  function planRound(r) { ["diagnose", "patch", "build", "record_after", "verdict"].forEach((s) => addStep(s, r)); }
  function enter(stage, round) {
    addStep(stage, round);
    const key = stepKey(stage, round);
    for (const li of $("lv-steps").children) {
      if (li.dataset.key === key) { li.className = "now"; break; }
      if (li.className !== "skip") li.className = "done";
    }
    S.cur = key;
    say(STAGE_TEXT[stage] + (round > 1 && stage !== "record_before" ? " (round " + round + ")" : "") + "…");
  }

  // ------------------------------------------------------------------ runs board
  function slotRow(side, round) {
    const id = "lv-row-" + side + "-" + round;
    let row = $(id);
    if (!row) {
      row = el("div", "runrow"); row.id = id;
      row.append(el("span", "rowlbl", side === "before" ? "Original program" : "Fixed program" + (round > 1 ? ", round " + round : "")));
      const slots = el("div", "slots");
      for (let i = 0; i < S.runs; i++) { const s = el("span", "slot"); s.title = "run " + (i + 1) + ": waiting"; slots.append(s); }
      row.append(slots); $("lv-runs").append(row);
    }
    return row.querySelector(".slots");
  }
  function slot(side, round, i) {
    const slots = slotRow(side, round);
    while (slots.children.length <= i) { const s = el("span", "slot"); s.title = "extra run (a recording lost events)"; slots.append(s); }
    return slots.children[i];
  }
  function runStart(e) { const s = slot(e.side, e.round, e.i); s.className = "slot rec"; s.title = "run " + (e.i + 1) + ": recording on the QNX target"; say((e.side === "before" ? "Recording the original program" : "Recording the fixed program") + ": run " + (e.i + 1) + " of " + S.runs + "…"); }
  function runDone(e) {
    const s = slot(e.side, e.round, e.i);
    const bad = !e.lossy && e.kinds.length > 0;
    s.className = "slot " + (e.lossy ? "lossy" : bad ? "bug" : "clean");
    let tip = "run " + (e.i + 1) + ": " + (e.lossy ? "events lost, not counted" : bad ? e.problems.join("; ") : "no problem found");
    const m = metricOf(e);
    if (m != null) tip += " · " + S.metric.label + " " + m.toFixed(2) + " ms";
    s.title = tip;
    log((e.side === "before" ? "Original" : "Fixed") + " run " + (e.i + 1) + ": " + (e.lossy ? "recording lost events, replaced" : bad ? e.problems.join("; ") : "clean"));
    if (m != null) { S.points.push({ side: e.side, round: e.round, v: m, lossy: e.lossy }); drawChart(); }
  }
  function metricOf(e) {
    const names = Object.keys(e.deadlines || {});
    if (names.length) {
      const d = e.deadlines[names[0]];
      if (!S.metric) S.metric = { label: "'" + names[0] + "' p99", budget: d.budget_ms, unit: "ms" };
      return d.p99_ms;
    }
    if (e.irq && e.irq.p99_masked_us != null) {
      if (!S.metric) S.metric = { label: "interrupt masked p99", budget: null, unit: "ms" };
      return e.irq.p99_masked_us / 1000;
    }
    if (S.metric && S.metric.label.startsWith("interrupt") && !e.lossy) return 0.0;
    return null;
  }
  function drawChart() {
    const box = $("lv-chart"); if (!S.metric || !S.points.length) return;
    const W = 520, H = 170, L = 44, R = 10, T = 14, B = 26;
    const vmax = Math.max(...S.points.map((p) => p.v), S.metric.budget || 0) * 1.15 || 1;
    const x = (i) => L + (i + 0.5) * ((W - L - R) / Math.max(S.points.length, 10));
    const y = (v) => T + (1 - v / vmax) * (H - T - B);
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg"); svg.setAttribute("viewBox", "0 0 " + W + " " + H); svg.setAttribute("class", "minichart");
    const add = (tag, attrs, text) => { const n = document.createElementNS(ns, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); if (text != null) n.textContent = text; svg.append(n); return n; };
    [0, vmax / 2, vmax].forEach((v) => { add("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), stroke: "var(--line)" }); add("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, v.toFixed(1)); });
    if (S.metric.budget) { add("line", { x1: L, x2: W - R, y1: y(S.metric.budget), y2: y(S.metric.budget), stroke: "var(--fg)", "stroke-dasharray": "4 4", "stroke-width": 1.5 }); add("text", { x: W - R, y: y(S.metric.budget) - 5, "text-anchor": "end" }, "budget " + S.metric.budget + " ms"); }
    S.points.forEach((p, i) => {
      const c = add("circle", { cx: x(i), cy: y(p.v), r: 6, fill: p.lossy ? "none" : p.side === "before" ? "var(--before)" : "var(--accent)", stroke: p.lossy ? "var(--faint)" : "var(--surface)", "stroke-width": 2 });
      const t = document.createElementNS(ns, "title"); t.textContent = (p.side === "before" ? "original" : "fixed, round " + p.round) + ": " + p.v.toFixed(2) + " ms"; c.append(t);
    });
    add("text", { x: L, y: H - 6 }, S.metric.label + " per run (ms)");
    box.replaceChildren(svg);
    $("lv-chart-legend").hidden = false;
  }

  // ------------------------------------------------------------------ code view
  function showCode(tab) {
    const pre = $("lv-code"); pre.replaceChildren();
    document.querySelectorAll("[data-tab]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tab === tab)));
    if (tab === "patch") {
      if (!S.diff) { pre.append(el("span", "muted", "The patch appears here once TraceLens writes it.")); return; }
      S.diff.split("\n").forEach((l) => {
        const cls = l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : l.startsWith("@@") ? "hunk" : null;
        pre.append(el("span", cls ? "ln " + cls : "ln", l)); });
      return;
    }
    const fixed = tab === "fixed";
    if (fixed && !S.fixed) { pre.append(el("span", "muted", "The fixed code appears here once TraceLens writes it.")); return; }
    const marks = fixed ? S.changed : S.marks, cls = fixed ? " chg" : " mark";
    let first = null;
    (fixed ? S.fixed : S.base).split("\n").forEach((l, i) => {
      const n = i + 1, row = el("span", "ln" + (marks.has(n) ? cls : ""));
      row.append(el("i", null, String(n).padStart(4, " ")), document.createTextNode(" " + l));
      if (first == null && marks.has(n)) first = row;
      pre.append(row);
    });
    if (first) pre.scrollTop = Math.max(0, first.offsetTop - pre.offsetTop - 60);
  }

  // ------------------------------------------------------------------ handlers
  const H = {
    start(e) {
      S.runs = e.runs; S.files = e.files || {}; S.file = Object.keys(S.files).find((f) => f.endsWith(".c")) || Object.keys(S.files)[0];
      $("lv-title").textContent = "Fixing the " + (NAMES[e.workload] || String(e.workload).replace(/^z\d+_/, "").replace(/_/g, " ")); $("lv-file").textContent = S.file || "";
      S.base = S.files[S.file] || "";
      setStatus("Working", "st-info"); addStep("record_before", 0); planRound(1); showCode("base");
      log("Started: " + e.runs + " recordings before and after, up to " + e.max_rounds + " rounds");
    },
    stage(e) { if (e.stage === "diagnose" && e.round > 1) planRound(e.round); enter(e.stage, e.round); },
    run_start: runStart,
    run: runDone,
    diagnosis(e) {
      const box = $("lv-where");
      if (e.round === 1) box.replaceChildren();
      const head = el("h3", null, e.round === 1 ? "What TraceLens found in the original program" : "Round " + e.round + ": what is still wrong in the fixed program");
      const wrap = el("div", "found"); wrap.append(head);
      if (!e.findings.length) wrap.append(el("p", "muted", "Nothing left to fix."));
      e.findings.forEach((f, i) => {
        const card = el("div", "fcard");
        const hd = el("div", "fhd"); hd.append(el("b", null, "#" + (i + 1) + " " + f.name), el("span", "pill sev-" + f.severity, f.severity === "critical" ? "Fix now" : f.severity === "high" ? "Fix" : f.severity === "medium" ? "Worth a look" : "Info"));
        card.append(hd, el("p", null, f.summary));
        if (f.timeline) { const t = el("div", "scroll"); t.innerHTML = f.timeline; card.append(el("div", "k", "The moment it happened"), t); }
        wrap.append(card);
      });
      if (e.radar && e.radar.length) {
        const r = el("div", "fcard");
        r.append(el("div", "fhd"), el("p", "muted", "Learned radar (not a rule, never auto-fixed): " +
          e.radar.map((x) => x.name + " behaves unlike healthy QNX" +
            (x.like ? ", closest known pattern " + x.like + (x.like_within ? "" : " (loosely)") : "") +
            " \u2014 score " + x.score + " vs " + x.threshold).join("; ") + "."));
        r.firstChild.append(el("b", null, "Second opinion"), el("span", "pill st-info", "Learned"));
        wrap.append(r);
      }
      box.prepend(wrap);  // newest round on top, earlier rounds stay below
      log("Found: " + (e.findings.map((f) => f.name).join("; ") || "nothing"));
    },
    remedy(e) {
      const box = $("lv-fix"); box.replaceChildren(el("h3", null, "Round " + e.round + ": the fix"));
      if (S.fixed) S.base = S.fixed;  // round 2 starts from round 1's fixed code
      S.marks = new Set(); S.changed = new Set(); S.fixed = ""; S.diff = "";
      e.remedies.filter((r) => r.rule !== "symptom").forEach((r) => {
        const c = el("div", "rcard"); const hd = el("p");
        hd.append(el("span", "pill " + (r.automatic ? "st-ok" : "st-info"), r.automatic ? "Fixed automatically" : "Fix by hand"), document.createTextNode(" "), el("b", null, r.title));
        c.append(hd, el("p", "muted small", r.rationale));
        const where = (r.locations || []).filter(([path]) => path === S.file);
        where.forEach(([, line]) => S.marks.add(line));
        if (where.length) c.append(el("p", "small", "Where: " + S.file + " line" + (where.length > 1 ? "s " : " ") + where.map(([, n]) => n).join(", ")));
        (r.guidance || []).forEach((g) => c.append(el("p", "small", g)));
        box.append(c);
      });
      if (e.diff && e.files && e.files[S.file] != null) {
        S.diff = e.diff; S.fixed = e.files[S.file]; let n = 0;
        e.diff.split("\n").forEach((l) => {
          const m = l.match(/^@@ -\d+(?:,\d+)? \+(\d+)/); if (m) { n = +m[1]; return; }
          if (l.startsWith("+++") || l.startsWith("---")) return;
          if (l.startsWith("+")) { S.changed.add(n); n++; } else if (!l.startsWith("-")) { n++; }
        });
      }
      showCode("base");  // first: the original code, where the problem is
      log("Fix written: " + e.remedies.filter((r) => r.rule !== "symptom").map((r) => r.title).join("; "));
    },
    build(e) { log(e.ok ? "Built with qcc (round " + e.round + ")" : "Build failed (round " + e.round + ")"); },
    verdict(e) {
      const v = e.verdict, ok = v.verdict === "VERIFIED";
      const box = $("lv-verdict");
      if (box.querySelector("p.muted")) box.replaceChildren();
      const c = el("div", "vcard " + (ok ? "ok" : v.verdict === "NOT FIXED" ? "bad" : "warn"));
      c.append(el("b", null, "Round " + e.round + ": " + (ok ? "verified on the QNX target" : v.verdict === "NOT FIXED" ? "not fixed yet" : "no verdict")));
      const ul = el("ul");
      Object.entries(v.targets || {}).forEach(([k, t]) => ul.append(el("li", null, k.replace(/_/g, " ") + ": in " + Math.round(t.before_rate * 100) + "% of runs before, " + Math.round(t.after_rate * 100) + "% after")));
      (v.deadlines || []).forEach((d) => ul.append(el("li", null, "'" + d.name + "' worst-case response " + (d.before_p99 / 1e6).toFixed(2) + " → " + (d.after_p99 / 1e6).toFixed(2) + " ms (budget " + (d.budget_ns / 1e6).toFixed(0) + " ms); late jobs " + d.before_misses + " → " + d.after_misses)));
      (v.reasons || []).forEach((r) => ul.append(el("li", "muted", r)));
      c.append(ul); box.append(c);
      log("Verdict, round " + e.round + ": " + v.verdict);
    },
    done(e) {
      S.done = true;
      for (const li of $("lv-steps").children) if (li.className === "now") li.className = "done";
      const [txt, cls] = STATUS[e.status] || [e.status, "info"];
      setStatus(txt, "st-" + cls); say(txt + (e.rounds ? " after " + e.rounds + " round" + (e.rounds > 1 ? "s" : "") : "") + (e.note ? ". " + e.note : "."));
      $("lv-final").hidden = false;
      log("Done: " + e.status);
    },
    log(e) { log(e.message); },
  };
  function handle(e) { (H[e.type] || (() => {}))(e); }

  document.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => showCode(b.dataset.tab)));

  // ------------------------------------------------------------------ sources
  if (MODE === "live") {
    const es = new EventSource(URL_);
    es.onmessage = (m) => { const e = JSON.parse(m.data); handle(e); if (e.type === "done") es.close(); };
    es.onerror = () => { if (S.done) es.close(); else say("Waiting for the fix process…"); };
  } else {
    let events = [], i = 0, timer = null, speed = 20, paused = false;
    const ctl = $("lv-controls"); ctl.hidden = false;
    const next = () => {
      if (paused || i >= events.length) return;
      handle(events[i]); i++;
      if (i < events.length) {
        const gap = Math.max(0, events[i].t - events[i - 1].t);
        timer = setTimeout(next, Math.min(2500, Math.max(60, (gap * 1000) / speed)));
      }
    };
    const restart = () => { clearTimeout(timer); i = 0; S = Object.assign(S, { marks: new Set(), changed: new Set(), diff: "", stages: [], cur: null, points: [], metric: null, done: false });
      ["lv-steps", "lv-runs", "lv-where", "lv-fix", "lv-verdict", "lv-log", "lv-chart"].forEach((id) => $(id).replaceChildren());
      S.base = S.files[S.file] || ""; S.fixed = "";
      $("lv-final").hidden = true; $("lv-chart-legend").hidden = true; paused = false; $("lv-pause").textContent = "Pause"; next(); };
    $("lv-pause").addEventListener("click", () => { paused = !paused; $("lv-pause").textContent = paused ? "Play" : "Pause"; if (!paused) next(); });
    $("lv-speed").addEventListener("change", (ev) => { speed = +ev.target.value; });
    $("lv-end").addEventListener("click", () => { clearTimeout(timer); paused = false; while (i < events.length) { handle(events[i]); i++; } });
    $("lv-again").addEventListener("click", restart);
    fetch(URL_).then((r) => r.json()).then((list) => { events = list; next(); })
      .catch(() => say("The recorded fix could not be loaded."));
  }
})();
