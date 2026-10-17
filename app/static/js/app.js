// Rozi frontend: hash router + views. All business math happens on the server (/api/domain/*);
// this file only stores data locally, calls the API and formats results.

const LS = "rozi.";
const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(LS + key);
      return raw === null ? fallback : JSON.parse(raw);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(LS + key, JSON.stringify(value));
    } catch {
      toast("Could not save on this device.");
    }
  },
};

const DEFAULTS = { lang: "en", persona: "delivery", name: "", goal: 1200, minWage: "", fontScale: 1, contrast: false, lite: false, alertCap: 3, quiet: false, manualVoice: false, consentAI: false, reportOptIn: false };
const settings = () => ({ ...DEFAULTS, ...store.get("settings", {}) });
const saveSettings = (patch) => {
  store.set("settings", { ...settings(), ...patch });
  applySettings();
};
const list = (name) => store.get(name, []);
const saveList = (name, items) => store.set(name, items);
const uid = () => (crypto.randomUUID ? crypto.randomUUID() : String(Date.now() + Math.random()));
const todayISO = () => new Date().toLocaleDateString("en-CA");
const nowLocalISO = () => {
  const d = new Date();
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
};

// ---------- formatting only ----------
const inr = (n) => (n === null || n === undefined ? "-" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(n));
const signed = (n) => (n > 0 ? "+" : "") + inr(n);

// ---------- DOM helpers (textContent only, never innerHTML) ----------
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const card = (...c) => h("section", { class: "card" }, ...c);
const btn = (label, onclick, cls = "") => h("button", { type: "button", class: `btn ${cls}`, onclick }, label);
const kv = (k, v) => h("div", { class: "kv" }, h("span", {}, k), h("strong", { class: "num" }, v));
function field(label, input) {
  const id = "f-" + uid().slice(0, 8);
  input.id = id;
  return h("div", { class: "field" }, h("label", { for: id }, label), input);
}
const input = (attrs) => h("input", attrs);
function select(options, value) {
  const s = h("select", {});
  for (const [v, l] of options) s.append(h("option", { value: v, selected: v === value }, l));
  return s;
}
function toast(msg) {
  const t = h("div", { class: "toast", role: "status" }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), 3500);
}
function speakBtn(getText) {
  if (!("speechSynthesis" in window)) return null;
  return btn("🔊 Read aloud", () => {
    const u = new SpeechSynthesisUtterance(getText());
    u.lang = { en: "en-IN", hi: "hi-IN", ta: "ta-IN", pa: "pa-IN" }[settings().lang];
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
  }, "btn--ghost");
}
const verifyNote = (e) => (e.needs_verification ? h("p", { class: "notice" }, `Please verify on the official website. Last verified: ${e.verified_on || "not yet"}.`) : null);

// ---------- PII redaction in the browser (server redacts again) ----------
function redact(text) {
  return text
    .replace(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g, "[EMAIL]")
    .replace(/(^|\D)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)/g, "$1[AADHAAR]")
    .replace(/(\+91[\s-]?|(^|\D))[6-9]\d{4}[\s-]?\d{5}(?!\d)/g, "$2[PHONE]")
    .replace(/\b[A-Z]{5}\d{4}[A-Z]\b/gi, "[PAN]")
    .replace(/(^|\D)\d{9,18}(?!\d)/g, "$1[BANK_ACCOUNT]");
}

// ---------- API ----------
const recentErrors = [];
async function api(path, body, { method, raw } = {}) {
  const opts = { method: method || (body === undefined ? "GET" : "POST"), headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) {
    opts.body = JSON.stringify(body);
    opts.headers["content-type"] = "application/json";
  }
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 20000);
  try {
    const res = await fetch(path, { ...opts, signal: ctrl.signal });
    if (raw) return res;
    const data = await res.json();
    if (!res.ok) {
      const code = (data.error && data.error.code) || `HTTP_${res.status}`;
      recentErrors.push(String(code).toUpperCase().slice(0, 30));
      throw new Error(data.error ? data.error.message : code);
    }
    if (data && data.meta) showDegraded(data.meta);
    return data;
  } catch (err) {
    if (err.name === "AbortError" || err instanceof TypeError) {
      recentErrors.push(navigator.onLine ? "NETWORK" : "OFFLINE");
      throw new Error(navigator.onLine ? "Server not reachable. Please try again." : "You are offline.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
function showDegraded(meta) {
  const banner = document.getElementById("banner");
  if (meta.degraded) {
    banner.textContent = `AI help is not available right now (${meta.reason || "offline"}). Showing verified, built-in content instead.`;
    banner.hidden = false;
  } else banner.hidden = true;
}

// ---------- shared data payloads ----------
const workLog = () => ({
  entries: list("entries").map(({ day, hours, base_pay, incentive, start_hour, platform }) => ({ day, hours, base_pay, incentive, start_hour, platform })),
  expenses: list("expenses").map(({ day, category, amount }) => ({ day, category, amount })),
});
async function summary() {
  const s = settings();
  try {
    const result = await api("/api/domain/earnings/summary", { ...workLog(), today: todayISO(), goal: Number(s.goal) || null, min_wage_daily: Number(s.minWage) || null });
    store.set("lastSummary", { at: Date.now(), result });
    return { result, stale: false };
  } catch {
    const last = store.get("lastSummary", null);
    return { result: last && last.result, stale: true };
  }
}

// ---------- demo data ----------
function seedDemo() {
  const entries = [];
  const expenses = [];
  for (let i = 0; i < 45; i += 1) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    const day = d.toLocaleDateString("en-CA");
    if (i % 7 === 6) continue;
    entries.push({ id: uid(), demo: true, day, hours: 4 + (i % 3), base_pay: 380 + ((i * 37) % 160), incentive: i % 4 === 0 ? 120 : 0, start_hour: [8, 12, 17][i % 3], platform: i % 2 ? "Platform A" : "Platform B" });
    entries.push({ id: uid(), demo: true, day, hours: 3, base_pay: 300 + ((i * 13) % 90), incentive: 0, start_hour: 18, platform: "Platform A" });
    expenses.push({ id: uid(), demo: true, day, category: "fuel", amount: 110 + (i % 5) * 10 });
  }
  saveList("entries", entries);
  saveList("expenses", expenses);
  const due = new Date();
  due.setDate(due.getDate() - 9);
  saveList("payments", [{ id: uid(), platform: "Platform A", due_date: due.toLocaleDateString("en-CA"), amount: 2450, paid: false }]);
  saveList("wages", [{ id: uid(), contractor: "Site contractor", day: todayISO(), amount: 650, paid: false }]);
  const exp = new Date();
  exp.setDate(exp.getDate() + 20);
  saveList("docs", [{ id: "lic1", kind: "licence", label: "Driving licence", expires_on: exp.toLocaleDateString("en-CA") }]);
  saveSettings({ demo: true, name: settings().name || "Ravi", onboarded: true });
  toast("DEMO data loaded");
}

// ---------- views ----------
const views = {};

views.onboarding = (root) => {
  const s = settings();
  const lang = select([["en", "English"], ["hi", "हिन्दी"], ["ta", "தமிழ்"], ["pa", "ਪੰਜਾਬੀ"]], s.lang);
  const persona = select([["delivery", "Delivery partner"], ["driver", "Driver"], ["daily_wage", "Daily-wage worker"]], s.persona);
  const name = input({ type: "text", maxlength: 30, value: s.name, autocomplete: "given-name" });
  const goal = input({ type: "number", min: 0, inputmode: "numeric", value: s.goal });
  root.append(
    h("h1", {}, "Welcome to Rozi"),
    h("p", {}, "Track earnings, stay safe, know your rights, and write complaints in simple language. Your data stays on your phone."),
    card(field("Language", lang), field("I work as", persona), field("First name (optional)", name), field("Daily goal (₹, after costs)", goal),
      btn("Start", () => {
        saveSettings({ lang: lang.value, persona: persona.value, name: name.value.trim(), goal: Number(goal.value) || 0, onboarded: true });
        location.hash = "#/home";
      }, "btn--wide"),
      btn("Try with demo data", () => { seedDemo(); location.hash = "#/home"; }, "btn--ghost btn--wide")),
  );
};

views.home = async (root) => {
  const s = settings();
  const shift = store.get("activeShift", null);
  root.append(h("h1", {}, `Namaste${s.name ? ", " + s.name : ""} 👋`));
  const shiftCard = card();
  const sumCard = card(h("p", { class: "muted" }, "Updating…"));
  const alertCard = card(h("h2", {}, "Alerts"), h("p", { class: "muted" }, "Checking…"));
  root.append(shiftCard, sumCard, alertCard,
    h("nav", { class: "tiles", "aria-label": "Quick actions" },
      ...[["#/gist", "🎙 Voice note"], ["#/earnings", "➕ Add earning"], ["#/earnings", "⛽ Add expense"], ["#/grievance", "📝 Complaint"], ["#/rights", "🪪 e-Shram"], ["#/emergency", "🆘 Emergency"], ["#/checkin", "✅ Shift-end check-in"], ["#/payments", "⏰ Late payments"], ["#/safety", "🌦 Weather & heat"]]
        .map(([href, label]) => h("a", { href }, label))));

  const { result: sum, stale } = await summary();
  sumCard.replaceChildren();
  if (!sum) sumCard.append(h("p", {}, "No totals yet. Add your first earning."));
  else {
    const t = sum.today;
    sumCard.append(
      h("h2", {}, "Today, after costs"), stale ? h("span", { class: "tag tag--warn" }, "Out of date") : null,
      h("p", { class: "big-number" }, inr(t.net)),
      kv("Net per hour", inr(t.net_hourly)), kv("Hours", String(t.hours)), kv("Gross / costs", `${inr(t.gross)} / ${inr(t.expenses)}`),
      kv("vs yesterday", signed(sum.delta_net)), kv("Last 7 days", inr(sum.week_net)),
      sum.goal ? h("div", {}, h("p", {}, `Goal ${inr(sum.goal.goal)}: ${sum.goal.percent}%`), h("div", { class: "progress", role: "progressbar", "aria-valuenow": sum.goal.percent, "aria-valuemin": 0, "aria-valuemax": 100 }, h("span", { "data-w": sum.goal.percent }))) : null,
      sum.min_wage && sum.min_wage.below ? h("p", { class: "notice" }, `Your net hourly rate is below the minimum wage you entered (${inr(sum.min_wage.hourly_floor)}/hr).`) : null,
    );
    sumCard.querySelectorAll("[data-w]").forEach((el) => { el.style.width = `${el.dataset.w}%`; });
  }

  let guardian = null;
  try {
    guardian = await api("/api/domain/guardian", { hours_today: sum ? sum.today.hours : 0, now: nowLocalISO(), last_shift_end: store.get("lastShiftEnd", null) });
  } catch { /* guardian unavailable: allow shift */ }
  const blocked = guardian && !guardian.can_start_shift;
  shiftCard.append(
    h("h2", {}, shift ? "Shift running" : "Ready to work?"),
    guardian && guardian.level !== "ok" ? h("p", { class: "notice alert-critical" }, guardian.level === "rest" ? `Rest Mode: please rest until ${new Date(guardian.rest_until).toLocaleTimeString()}. Logging past work still works.` : "You have worked many hours. A 15-minute break helps you stay safe.") : null,
    shift
      ? btn("■ End shift", async () => {
          store.set("activeShift", null);
          store.set("lastShiftEnd", nowLocalISO());
          try {
            const r = await api("/api/domain/shift/hours", { start: shift.start, end: nowLocalISO() });
            store.set("pendingShift", r);
            toast(`Shift: ${r.hours} hours. Add what you earned.`);
          } catch { toast("Shift ended. Add your hours and earnings."); }
          location.hash = "#/earnings";
        }, "btn--accent btn--wide")
      : btn("▶ Start shift", () => { store.set("activeShift", { start: nowLocalISO() }); render(); }, "btn--wide"),
  );
  if (blocked) shiftCard.querySelector("button").disabled = true;

  try {
    const alerts = await evaluateAlerts(sum, shift);
    alertCard.replaceChildren(h("h2", {}, "Alerts"));
    if (!alerts.length) alertCard.append(h("p", { class: "muted" }, "All good. No alerts right now."));
    for (const a of alerts) {
      alertCard.append(h("div", { class: `card ${a.priority === "critical" ? "alert-critical" : ""}` },
        h("strong", {}, a.title), h("p", {}, a.body), a.cta ? h("a", { class: "btn btn--ghost", href: a.cta.route }, a.cta.label) : null,
        btn("Snooze 1 hour", (e) => { snooze(a.dedupe_key); e.target.closest(".card").remove(); }, "btn--ghost")));
    }
  } catch (err) {
    alertCard.replaceChildren(h("h2", {}, "Alerts"), h("p", { class: "muted" }, err.message));
  }
};

function snooze(key) {
  const sn = store.get("snoozed", {});
  sn[key] = Date.now() + 3600000;
  store.set("snoozed", sn);
}

async function evaluateAlerts(sum, shift) {
  const s = settings();
  const weather = store.get("weather", null);
  const context = {
    lang: s.lang, now: nowLocalISO(), hours_today: sum ? sum.today.hours : 0, net_today: sum ? sum.today.net : 0, delta_net: sum ? sum.delta_net : 0,
    goal: Number(s.goal) || null, shift_active: Boolean(shift),
    payments: list("payments").map(({ platform, due_date, paid }) => ({ platform, due_date, paid })),
    documents: list("docs").map(({ kind, expires_on }) => ({ kind, expires_on })),
    doc_titles: { licence: "licence", insurance: "insurance", vehicle_rc: "vehicle RC", puc: "PUC", id: "ID", permit: "permit", other: "document" },
  };
  const w = weather ? { rain_probability_max: weather.rain_probability_max, rain_time: weather.rain_time, apparent_max_c: weather.apparent_max_c } : null;
  const all = await api("/api/alerts/evaluate", { context, weather: w });
  // Local policy: snooze, quiet hours (22-06, except critical) and the daily nudge cap.
  const snoozed = store.get("snoozed", {});
  const hour = new Date().getHours();
  const quiet = s.quiet && (hour >= 22 || hour < 6);
  let nudges = 0;
  return all.filter((a) => {
    if ((snoozed[a.dedupe_key] || 0) > Date.now()) return false;
    if (a.priority === "critical") return true;
    if (quiet) return false;
    if (a.priority === "nudge") { nudges += 1; return nudges <= s.alertCap; }
    return true;
  });
}

views.earnings = async (root) => {
  const pending = store.get("pendingShift", null);
  const day = input({ type: "date", value: pending ? pending.day : todayISO(), required: true });
  const hours = input({ type: "number", step: "0.25", min: 0, max: 24, inputmode: "decimal", value: pending ? pending.hours : "" });
  const base = input({ type: "number", min: 0, inputmode: "decimal" });
  const incentive = input({ type: "number", min: 0, inputmode: "decimal", value: 0 });
  const startHour = input({ type: "number", min: 0, max: 23, value: pending ? pending.start_hour : "" });
  const platform = input({ type: "text", maxlength: 40, placeholder: "e.g. Platform A" });
  const expDay = input({ type: "date", value: todayISO() });
  const cat = select([["fuel", "Fuel"], ["emi", "Vehicle EMI"], ["data", "Data recharge"], ["maintenance", "Maintenance"], ["parking", "Parking"], ["other", "Other"]], "fuel");
  const amount = input({ type: "number", min: 0, inputmode: "decimal" });
  const out = card(h("h2", {}, "Check my numbers"), h("p", { class: "muted" }, "See how today's total is calculated, step by step."));

  root.append(
    h("h1", {}, "Earnings & costs"),
    card(h("h2", {}, "Add earning"), field("Day", day), field("Hours worked", hours), field("Base pay (₹)", base), field("Incentive / bonus (₹)", incentive), field("Start hour (0-23)", startHour), field("Platform", platform),
      btn("Save earning", () => {
        if (!hours.value || !base.value) return toast("Please add hours and base pay.");
        saveList("entries", [...list("entries"), { id: uid(), day: day.value, hours: Number(hours.value), base_pay: Number(base.value), incentive: Number(incentive.value) || 0, start_hour: startHour.value === "" ? null : Number(startHour.value), platform: platform.value.trim() }]);
        store.set("pendingShift", null);
        toast("Saved ✓");
        render();
      }, "btn--wide")),
    card(h("h2", {}, "Add expense"), field("Day", expDay), field("Type", cat), field("Amount (₹)", amount),
      btn("Save expense", () => {
        if (!amount.value) return toast("Please add an amount.");
        saveList("expenses", [...list("expenses"), { id: uid(), day: expDay.value, category: cat.value, amount: Number(amount.value) }]);
        toast("Saved ✓");
        render();
      }, "btn--wide")),
    out,
  );
  out.append(btn("Explain today's total", async () => {
    try {
      const r = await api("/api/domain/earnings/explain", { ...workLog(), day: todayISO() });
      out.append(...r.steps.map((st) => kv(st.key.replace(/_/g, " "), `${st.expression}${st.result ? " = " + st.result : ""}`)));
    } catch (err) { toast(err.message); }
  }, "btn--ghost"));

  const month = card(h("h2", {}, "This month (for a lender)"));
  const best = card(h("h2", {}, "Best hours for you"));
  root.append(month, best, fairPayCard());
  const now = new Date();
  try {
    const m = await api("/api/domain/earnings/month", { ...workLog(), year: now.getFullYear(), month: now.getMonth() + 1 });
    month.append(kv("Days worked", m.days_worked), kv("Hours", m.hours), kv("Gross", inr(m.gross)), kv("Costs", inr(m.expenses)), kv("Net", inr(m.net)), kv("Net per day", inr(m.avg_net_per_day)), btn("🖨 Print / save PDF", () => print(), "btn--ghost no-print"));
    const b = await api("/api/domain/insights/best-hours", workLog());
    if (!b.enough_data) best.append(h("p", { class: "muted" }, `Add at least ${b.min_entries} shifts with a start hour to see this.`));
    else {
      best.append(h("p", {}, `Best time: ${b.best_time || "-"} · Best day: ${b.best_weekday || "-"}`));
      best.append(...b.by_time.map((x) => kv(x.key, x.net_hourly === null ? "-" : `${inr(x.net_hourly)}/hr`)));
    }
  } catch (err) { month.append(h("p", { class: "muted" }, err.message)); }

  const rows = [...list("entries")].sort((a, b) => (a.day < b.day ? 1 : -1)).slice(0, 10);
  root.append(card(h("h2", {}, "Recent entries"), ...rows.map((e) => h("div", { class: "kv" }, h("span", {}, `${e.day} · ${e.platform || "-"} · ${e.hours}h`),
    btn("Delete", () => { saveList("entries", list("entries").filter((x) => x.id !== e.id)); render(); }, "btn--ghost")))));
};

function fairPayCard() {
  const fare = input({ type: "number", min: 0 });
  const payout = input({ type: "number", min: 0 });
  const stated = input({ type: "number", min: 0, max: 100 });
  const principal = input({ type: "number", min: 0 });
  const rate = input({ type: "number", min: 0, max: 60, step: "0.1" });
  const months = input({ type: "number", min: 1, max: 120 });
  const out = h("div", { "aria-live": "polite" });
  return card(h("h2", {}, "Fair pay check"),
    field("Fare the customer paid (₹)", fare), field("What you received (₹)", payout), field("Commission the platform says (%)", stated),
    btn("Check commission", async () => {
      try {
        const r = await api("/api/domain/fairpay/commission", { gross_fare: Number(fare.value), net_payout: Number(payout.value), stated_pct: stated.value === "" ? null : Number(stated.value) });
        out.replaceChildren(kv("Taken", inr(r.deducted)), kv("Real commission", `${r.effective_pct}%`), r.higher_than_stated ? h("p", { class: "notice" }, `This is ${r.difference_pp} points higher than stated. You can ask the platform in writing.`) : null);
      } catch (err) { toast(err.message); }
    }, "btn--ghost"),
    h("h3", {}, "Vehicle loan EMI"), field("Loan amount (₹)", principal), field("Interest per year (%)", rate), field("Months", months),
    btn("Calculate EMI", async () => {
      try {
        const r = await api("/api/domain/fairpay/emi", { principal: Number(principal.value), annual_rate_pct: Number(rate.value), months: Number(months.value) });
        out.replaceChildren(kv("Monthly EMI", inr(r.emi)), kv("Total interest", inr(r.total_interest)), h("p", { class: "small muted" }, "Estimate only. Not financial advice."));
      } catch (err) { toast(err.message); }
    }, "btn--ghost"),
    out);
}

views.gist = (root) => {
  const s = settings();
  const text = h("textarea", { maxlength: 1000, placeholder: "e.g. Worked 8 hours, earned 950 rupees, payment from Platform A is late" });
  const out = h("div", { "aria-live": "polite" });
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  root.append(h("h1", {}, "Voice Day Gist"),
    h("p", { class: "notice" }, "Voice typing may use your browser's cloud service. Numbers like phone or Aadhaar are removed before sending to AI."),
    card(field("Tell us about your day", text),
      SR && !s.manualVoice ? btn("🎙 Speak (30 sec)", () => {
        const rec = new SR();
        rec.lang = { en: "en-IN", hi: "hi-IN", ta: "ta-IN", pa: "pa-IN" }[s.lang];
        rec.onresult = (e) => { text.value = Array.from(e.results).map((r) => r[0].transcript).join(" "); };
        rec.onerror = () => toast("Voice not available. Please type instead.");
        rec.start();
        setTimeout(() => rec.stop(), 30000);
      }, "btn--ghost") : h("p", { class: "small muted" }, "Typing mode is on."),
      btn("Understand my day", async () => {
        if (!text.value.trim()) return;
        try {
          const r = await api("/api/ai/daygist", { transcript: redact(text.value), lang: s.lang, today: todayISO() });
          const g = r.data;
          const hours = input({ type: "number", value: g.hours ?? "" });
          const earn = input({ type: "number", value: g.earnings_inr ?? "" });
          out.replaceChildren(h("h2", {}, "Please check"), field("Hours", hours), field("Earned (₹)", earn),
            g.accident ? h("p", { class: "notice" }, "You mentioned an accident. See the accident claim help.") : null,
            g.payment_delay ? h("a", { class: "btn btn--ghost", href: "#/payments" }, "Track late payment") : null,
            btn("Save to tracker", () => {
              saveList("entries", [...list("entries"), { id: uid(), day: todayISO(), hours: Number(hours.value) || 0, base_pay: Number(earn.value) || 0, incentive: 0, start_hour: null, platform: g.platform || "" }]);
              toast("Saved ✓");
              location.hash = "#/home";
            }, "btn--wide"));
        } catch (err) { toast(err.message); }
      }, "btn--wide")),
    out);
};

views.checkin = (root) => {
  const q = (label, opts) => field(label, select(opts, opts[0][0]));
  const accident = q("Any accident or safety problem today?", [["no", "No"], ["yes", "Yes"]]);
  const paid = q("Were you paid on time?", [["yes", "Yes"], ["no", "No"]]);
  const stress = q("How stressed do you feel?", [["low", "Okay"], ["mid", "A bit"], ["high", "Very stressed"]]);
  root.append(h("h1", {}, "Shift-end check-in"), h("p", { class: "muted" }, "Step 1 of 1 · 3 quick questions"),
    card(accident, paid, stress, btn("Done", () => {
      const v = (f) => f.querySelector("select").value;
      if (v(accident) === "yes") location.hash = "#/emergency";
      else if (v(paid) === "no") location.hash = "#/payments";
      else if (v(stress) === "high") {
        root.append(card(h("h2", {}, "Take care of yourself"), h("p", {}, "Rest, drink water, and talk to someone you trust. Free support: Tele-MANAS 14416."), h("a", { class: "btn", href: "tel:14416" }, "📞 Call 14416")));
      } else toast("Thanks! Rest well 🌙");
    }, "btn--wide")));
};

views.rights = async (root) => {
  const s = settings();
  root.append(h("h1", {}, "Rights & help"),
    h("nav", { class: "tiles" }, h("a", { href: "#/grievance" }, "📝 Write a complaint"), h("a", { href: "#/eligibility" }, "📅 Eligibility days"), h("a", { href: "#/transparency" }, "❓ Ask why (ratings/ID)")));
  const schemes = await api(`/api/content/welfare-schemes?lang=${s.lang}`);
  for (const e of schemes.entries.filter((x) => x.kind !== "rule")) {
    const body = h("div", { "aria-live": "polite" });
    root.append(card(h("h2", {}, e.title), h("p", {}, e.summary), e.eligibility ? h("p", { class: "small" }, e.eligibility) : null,
      h("ol", {}, ...e.steps.map((st) => h("li", {}, st))), verifyNote(e),
      h("a", { href: e.official_url, target: "_blank", rel: "noopener" }, `Official site: ${e.official_url}`),
      btn("Explain simply (AI)", async () => {
        try {
          const r = await api("/api/ai/welfare/summary", { scheme_id: e.id, lang: s.lang, level: "simple" });
          body.replaceChildren(h("p", {}, r.data.summary), h("ol", {}, ...r.data.steps.map((st) => h("li", {}, st))),
            r.meta.engine === "gemini" ? h("p", { class: "small muted" }, "AI-assisted text: please check") : null, speakBtn(() => r.data.summary + " " + r.data.steps.join(" ")));
        } catch (err) { toast(err.message); }
      }, "btn--ghost"), body));
  }
  const age = input({ type: "number", min: 0, max: 120 });
  const member = select([["no", "No"], ["yes", "Yes"], ["unsure", "Not sure"]], "no");
  const out = h("div", { "aria-live": "polite" });
  const reasons = { age_out_of_range: "e-Shram is for ages 16 to 59.", member_epfo_esic_nps: "Members of EPFO, ESIC or NPS cannot register.", confirm_membership: "Check your payslip or call 14434.", basic_rules_met: "You meet the basic rules. Follow the steps above." };
  root.append(card(h("h2", {}, "Can I get an e-Shram card?"), field("Your age", age), field("Are you in EPFO, ESIC or NPS?", member),
    btn("Check", async () => {
      try {
        const r = await api("/api/domain/eligibility/eshram", { age: Number(age.value), member: member.value });
        out.replaceChildren(h("p", {}, h("strong", {}, r.status.replace("_", " "))), ...r.reasons.map((x) => h("p", {}, reasons[x] || x)));
      } catch (err) { toast(err.message); }
    }, "btn--ghost"), out));
  const boards = await api(`/api/content/state-boards?lang=${s.lang}`);
  const refs = await api(`/api/content/legal-refs?lang=${s.lang}`);
  root.append(card(h("h2", {}, "Get human help"), ...boards.entries.map((b) => h("p", {}, h("a", { href: b.official_url, target: "_blank", rel: "noopener" }, b.title))), h("p", {}, "e-Shram helpline: ", h("a", { href: "tel:14434" }, "14434"))),
    card(h("h2", {}, "Laws and official services"), ...refs.entries.map((r) => h("p", {}, `${r.title} `, h("span", { class: "tag tag--warn" }, r.kind === "international_standard" ? "International standard (ILO), not automatically Indian law" : "Indian law/service (verify)")))));
};

views.eligibility = async (root) => {
  root.append(h("h1", {}, "Eligibility days this year"));
  const workDays = list("entries").filter((e) => e.platform).map((e) => ({ day: e.day, platform: e.platform }));
  const r = await api("/api/domain/eligibility/engagement", { work_days: workDays, today: todayISO() });
  const bar = (pct) => h("div", { class: "progress" }, h("span", { "data-w": pct }));
  root.append(card(h("p", {}, `Financial year ${r.fy_start} to ${r.fy_end}`),
    h("p", {}, `Best single platform: ${r.best_single} of ${r.single_threshold} days`), bar(r.single_pct),
    h("p", {}, `All platforms: ${r.total_days} of ${r.multi_threshold} days`), bar(r.multi_pct),
    ...r.platforms.map((p) => kv(p.platform, `${p.days} days`)),
    h("p", { class: "notice" }, r.verified ? "Check the latest rules on the official portal." : "Draft rule, not yet verified. Check the latest rules on the official portal.")));
  root.querySelectorAll("[data-w]").forEach((el) => { el.style.width = `${el.dataset.w}%`; });
};

views.transparency = (root) => {
  root.append(h("h1", {}, "Ask the platform why"),
    card(h("p", {}, "Apps use automatic systems to decide ratings, tasks and deactivation. You can ask for a written explanation and a review by a person."),
      h("p", { class: "notice" }, "This is a request, not a guaranteed right. Some state laws may give more protection: check with your labour department."),
      h("a", { class: "btn", href: "#/grievance?type=explanation_request" }, "Write the request")));
};

views.grievance = (root, params) => {
  const s = settings();
  const text = h("textarea", { maxlength: 1500, placeholder: "What happened? e.g. My payment of ₹2,450 due on 8th is not paid by Platform A." });
  const out = h("div", { "aria-live": "polite" });
  root.append(h("h1", {}, "Write a complaint"),
    h("ol", { class: "small muted" }, h("li", {}, "Describe"), h("li", {}, "Check details"), h("li", {}, "Get letter")),
    h("p", { class: "notice" }, "Before AI reads your text, phone, Aadhaar and bank numbers are removed."),
    card(field("Describe the problem", text), btn("Next", async () => {
      if (!text.value.trim()) return toast("Please describe the problem.");
      try {
        const r = await api("/api/ai/grievance/extract", { text: redact(text.value), lang: s.lang, today: todayISO() });
        confirmFacts(out, r.data, params.get("type"));
      } catch (err) { toast(err.message); }
    }, "btn--wide")), out);
  if (params.get("type")) confirmFacts(out, { facts: { issue_type: params.get("type"), remedy_sought: "written_explanation" }, summary: "" }, params.get("type"));
};

function confirmFacts(out, draft, forcedType) {
  const s = settings();
  const f = draft.facts;
  const date = input({ type: "date", value: f.date || "" });
  const platform = input({ type: "text", maxlength: 40, value: f.platform || "" });
  const issue = select([["payment_delay", "Payment delay"], ["unfair_deactivation", "Unfair deactivation"], ["bonus_denial", "Bonus denied"], ["wage_theft", "Unpaid wages"], ["explanation_request", "Ask for explanation"], ["other", "Other"]], forcedType || f.issue_type);
  const amount = input({ type: "number", min: 0, value: f.amount_lost ?? "" });
  const remedy = select([["pay_dues", "Pay my dues"], ["reactivate", "Reactivate my ID"], ["pay_bonus", "Pay my bonus"], ["written_explanation", "Explain in writing"], ["human_review", "Human review"], ["other", "Resolve it"]], f.remedy_sought);
  const name = input({ type: "text", maxlength: 60, value: s.name });
  const wid = input({ type: "text", maxlength: 40 });
  const letterLang = select([["en", "English"], ["hi", "हिन्दी"], ["ta", "தமிழ்"], ["pa", "ਪੰਜਾਬੀ"]], "en");
  const result = h("div", { "aria-live": "polite" });
  out.replaceChildren(card(h("h2", {}, "Check the details"), field("Date", date), field("Platform / employer", platform), field("Problem", issue), field("Amount lost (₹)", amount), field("What you want", remedy), field("Your name", name), field("Partner ID", wid), field("Letter language", letterLang),
    btn("Make my letter", async () => {
      try {
        const letter = await api("/api/domain/grievance/letter", {
          facts: { date: date.value || null, platform: platform.value || null, issue_type: issue.value, amount_lost: amount.value === "" ? null : Number(amount.value), remedy_sought: remedy.value },
          lang: letterLang.value, today: todayISO(), worker_name: name.value, worker_id: wid.value, summary: draft.summary || "",
        });
        showLetter(result, letter);
      } catch (err) { toast(err.message); }
    }, "btn--wide")), result);
}

function showLetter(root, letter) {
  const pre = h("pre", { class: "letter" }, letter.body);
  const subject = h("h3", {}, letter.subject);
  const wa = () => `https://wa.me/?text=${encodeURIComponent(subject.textContent + "\n\n" + pre.textContent)}`;
  const saved = [...list("grievances"), { id: uid(), at: todayISO(), subject: letter.subject }];
  saveList("grievances", saved);
  root.replaceChildren(card(subject, pre, h("p", { class: "notice" }, letter.review_note),
    h("div", { class: "row no-print" },
      btn("✨ Improve wording (AI)", async () => {
        try {
          const r = await api("/api/ai/grievance/polish", { subject: subject.textContent, body: pre.textContent, lang: letter.lang });
          subject.textContent = r.data.subject;
          pre.textContent = r.data.body;
          toast(r.meta.degraded ? "AI unavailable: kept your template letter." : "Wording improved. Please check it.");
        } catch (err) { toast(err.message); }
      }, "btn--ghost"),
      btn("🌐 Translate to my language", async () => {
        try {
          const r = await api("/api/ai/translate", { text: pre.textContent, target: settings().lang, source: letter.lang });
          root.append(card(h("h3", {}, "For you to read (AI-assisted translation: please check)"), h("pre", { class: "letter" }, r.data.text)));
        } catch (err) { toast(err.message); }
      }, "btn--ghost"),
      btn("🖨 Print / PDF", () => print(), "btn--ghost"),
      h("a", { class: "btn btn--ghost", href: wa(), target: "_blank", rel: "noopener" }, "Share on WhatsApp"),
      speakBtn(() => pre.textContent))));
}

views.payments = async (root) => {
  const platform = input({ type: "text", maxlength: 40 });
  const due = input({ type: "date" });
  const amount = input({ type: "number", min: 0 });
  root.append(h("h1", {}, "Late payments & pending wages"),
    card(h("h2", {}, "Add a payment you expect"), field("From (platform / employer)", platform), field("Due date", due), field("Amount (₹)", amount),
      btn("Save", () => {
        if (!due.value) return toast("Please add the due date.");
        saveList("payments", [...list("payments"), { id: uid(), platform: platform.value, due_date: due.value, amount: Number(amount.value) || 0, paid: false }]);
        render();
      }, "btn--wide")));
  for (const p of list("payments").filter((x) => !x.paid)) {
    const r = await api("/api/domain/payments/delay", { due_date: p.due_date, today: todayISO(), amount: p.amount, platform: p.platform });
    const labels = { remind_support: "Remind in-app support", written_complaint: "Written complaint to grievance officer", labour_department: "State labour department", cpgrams: "CPGRAMS (pgportal.gov.in)" };
    root.append(card(h("h2", {}, `${p.platform || "Payment"}: ${inr(r.amount)}`), h("p", {}, r.status === "late" ? `${r.days_late} days late` : r.status.replace("_", " ")),
      h("ol", {}, ...r.steps.map((st) => h("li", {}, `${st.reached ? "✅" : "⬜"} ${labels[st.key]}: ${st.on_date}`))),
      h("p", { class: "small muted" }, "Suggested follow-up plan, not legal deadlines."),
      h("div", { class: "row" }, h("a", { class: "btn", href: "#/grievance?type=payment_delay" }, "Draft message"),
        btn("Mark paid", () => { saveList("payments", list("payments").map((x) => (x.id === p.id ? { ...x, paid: true } : x))); render(); }, "btn--ghost"))));
  }
  const contractor = input({ type: "text", maxlength: 60 });
  const wDay = input({ type: "date", value: todayISO() });
  const wAmt = input({ type: "number", min: 0 });
  const wages = list("wages");
  const wCard = card(h("h2", {}, "Pending wages (daily work)"), field("Contractor", contractor), field("Day", wDay), field("Amount (₹)", wAmt),
    btn("Add", () => {
      if (!contractor.value || !wAmt.value) return toast("Please fill contractor and amount.");
      saveList("wages", [...wages, { id: uid(), contractor: contractor.value, day: wDay.value, amount: Number(wAmt.value), paid: false }]);
      render();
    }, "btn--ghost"));
  root.append(wCard);
  if (wages.length) {
    const r = await api("/api/domain/wages/pending", { entries: wages.map(({ contractor: c, day, amount: a, paid }) => ({ contractor: c, day, amount: a, paid })), today: todayISO() });
    wCard.append(kv("Total owed", inr(r.total_owed)), ...r.contractors.map((c) => kv(c.contractor, `${inr(c.owed)} · ${c.days_pending} days`)));
  }
};

views.documents = async (root) => {
  const s = settings();
  const kind = select([["licence", "Driving licence"], ["vehicle_rc", "Vehicle RC"], ["insurance", "Vehicle insurance"], ["puc", "PUC"], ["id", "ID card"], ["permit", "Permit"], ["other", "Other"]], "licence");
  const exp = input({ type: "date" });
  const docs = list("docs");
  const titles = { licence: "Driving licence", vehicle_rc: "Vehicle RC", insurance: "Vehicle insurance", puc: "PUC", id: "ID card", permit: "Permit", other: "Document" };
  root.append(h("h1", {}, "Documents"),
    card(h("h2", {}, "Expiry reminders"), field("Document", kind), field("Expires on", exp),
      btn("Add", () => {
        if (!exp.value) return toast("Please add the expiry date.");
        saveList("docs", [...docs, { id: uid().replace(/[^A-Za-z0-9_-]/g, "").slice(0, 20), kind: kind.value, label: "", expires_on: exp.value }]);
        render();
      }, "btn--ghost")));
  if (docs.length) {
    const r = await api("/api/domain/documents/expiry", { docs, today: todayISO() });
    root.append(card(...r.map((d) => kv(titles[d.kind], d.days_left < 0 ? "Expired" : `${d.days_left} days left`)),
      btn("📅 Add reminders to calendar (.ics)", async () => {
        const res = await api("/api/domain/documents/ics", { docs, today: todayISO(), titles }, { raw: true });
        const url = URL.createObjectURL(await res.blob());
        const a = h("a", { href: url, download: "document-reminders.ics" });
        a.click();
        URL.revokeObjectURL(url);
      }, "btn--ghost")));
  }
  const file = input({ type: "file", accept: "image/png,image/jpeg,image/webp" });
  const consent = input({ type: "checkbox" });
  const out = h("div", { "aria-live": "polite" });
  root.append(card(h("h2", {}, "Explain my contract (photo)"),
    h("p", { class: "small" }, "The image is sent to AI, used in memory only and not saved. Crop out ID numbers first. Not legal advice."),
    field("Screenshot (max 5 MB)", file), h("label", {}, consent, " I agree to send this image to the AI"),
    btn("Explain the 3 key clauses", async () => {
      const f = file.files[0];
      if (!f || !consent.checked) return toast("Choose an image and tick the consent box.");
      if (f.size > 5 * 1024 * 1024) return toast("Image is too large (max 5 MB).");
      const fd = new FormData();
      fd.append("file", f);
      fd.append("lang", s.lang);
      fd.append("consent", "true");
      try {
        const r = await api("/api/ai/contract", fd);
        out.replaceChildren(...(r.data.clauses.length ? r.data.clauses.map((c) => h("div", { class: c.caution ? "notice" : "" }, h("strong", {}, c.title), h("p", {}, c.explanation))) : [h("p", {}, "Could not read this image right now. Please ask a trusted person or call 14434.")]));
      } catch (err) { toast(err.message); }
    }, "btn--wide"), out));
  const pasted = h("textarea", { maxlength: 2000, placeholder: "Paste a confusing message or notice here" });
  const simple = h("div", { "aria-live": "polite" });
  root.append(card(h("h2", {}, "Make a message simple"), field("Message", pasted), btn("Simplify (AI)", async () => {
    if (!pasted.value.trim()) return;
    try {
      const r = await api("/api/ai/simplify", { text: redact(pasted.value), lang: s.lang });
      simple.replaceChildren(h("p", {}, r.data.text), speakBtn(() => r.data.text));
    } catch (err) { toast(err.message); }
  }, "btn--ghost"), simple));
};

views.emergency = async (root) => {
  const s = settings();
  root.append(h("h1", {}, "Emergency"));
  try {
    const r = await api(`/api/content/helplines?lang=${s.lang}`);
    root.append(card(...r.entries.map((e) => h("a", { class: "btn btn--wide " + (e.group === "emergency" ? "btn--danger" : "btn--ghost"), href: `tel:${e.number}` }, `📞 ${e.number} · ${e.title}`)), h("p", { class: "small muted" }, "Please verify numbers on official websites.")));
    const claim = (await api(`/api/content/welfare-schemes?lang=${s.lang}`)).entries.find((e) => e.id === "pmsby_claim");
    if (claim) root.append(card(h("h2", {}, claim.title), h("ol", {}, ...claim.steps.map((x) => h("li", {}, x))), verifyNote(claim)));
  } catch {
    root.append(card(h("a", { class: "btn btn--danger btn--wide", href: "tel:112" }, "📞 112 Emergency"), h("a", { class: "btn btn--ghost btn--wide", href: "tel:108" }, "📞 108 Ambulance"), h("a", { class: "btn btn--ghost btn--wide", href: "tel:181" }, "📞 181 Women helpline")));
  }
  if (navigator.share && navigator.geolocation) {
    root.append(btn("📍 Share my location", () => navigator.geolocation.getCurrentPosition((p) => navigator.share({ text: `I need help. My location: https://maps.google.com/?q=${p.coords.latitude},${p.coords.longitude}` }), () => toast("Location not available.")), "btn--wide"));
  }
};

views.safety = async (root) => {
  const s = settings();
  const out = h("div", { "aria-live": "polite" });
  root.append(h("h1", {}, "Weather & heat safety"), card(h("p", {}, "Your location is rounded to about 1 km and not saved."),
    btn("Check weather near me", () => navigator.geolocation.getCurrentPosition(async (p) => {
      try {
        const r = await api("/api/weather", { lat: p.coords.latitude, lon: p.coords.longitude });
        store.set("weather", r.data);
        out.replaceChildren(r.data.available ? h("div", {}, kv("Highest rain chance", `${r.data.rain_probability_max}% around ${r.data.rain_time || "-"}`), kv("Feels like (max)", `${r.data.apparent_max_c ?? "-"}°C`)) : h("p", {}, "Weather not available right now."));
      } catch (err) { toast(err.message); }
    }, () => toast("Location permission is needed.")), "btn--wide"), out));
  const heat = await api(`/api/content/heat-thresholds?lang=${s.lang}`);
  for (const e of heat.entries) root.append(card(h("h2", {}, e.title), h("ul", {}, ...e.steps.map((x) => h("li", {}, x))), verifyNote(e)));
};

views.more = (root) => {
  root.append(h("h1", {}, "More"), h("nav", { class: "tiles" },
    ...[["#/settings", "⚙️ Settings"], ["#/payments", "⏰ Late payments"], ["#/checkin", "✅ Check-in"], ["#/safety", "🌦 Weather"], ["#/fixit", "🛠 Fix-It"], ["#/health", "🩺 App health"], ["#/gist", "🎙 Voice note"], ["#/eligibility", "📅 Eligibility"], ["#/emergency", "🆘 Emergency"]]
      .map(([href, label]) => h("a", { href }, label))));
};

views.settings = (root) => {
  const s = settings();
  const name = input({ type: "text", maxlength: 30, value: s.name });
  const persona = select([["delivery", "Delivery partner"], ["driver", "Driver"], ["daily_wage", "Daily-wage worker"]], s.persona);
  const goal = input({ type: "number", min: 0, value: s.goal });
  const minWage = input({ type: "number", min: 0, value: s.minWage, placeholder: "From your state labour department" });
  const font = input({ type: "range", min: 1, max: 1.6, step: 0.1, value: s.fontScale });
  const contrast = input({ type: "checkbox", checked: s.contrast });
  const optIn = input({ type: "checkbox", checked: s.reportOptIn });
  root.append(h("h1", {}, "Settings"),
    card(field("First name", name), field("I work as", persona), field("Daily goal (₹)", goal), field("Daily minimum wage (₹, your state)", minWage), field("Text size", font),
      h("label", {}, contrast, " High contrast"), h("label", {}, optIn, " Allow sending anonymous problem reports (off by default)"),
      btn("Save", () => { saveSettings({ name: name.value, persona: persona.value, goal: Number(goal.value), minWage: minWage.value, fontScale: Number(font.value), contrast: contrast.checked, reportOptIn: optIn.checked }); toast("Saved ✓"); }, "btn--wide")),
    card(h("p", { class: "small" }, "Your data is stored only on your device. Numbers are sent to our server only to calculate, and are not saved."),
      btn("Load demo data", () => { seedDemo(); render(); }, "btn--ghost"),
      btn("⬇ Export my data", () => {
        const data = {};
        for (const k of ["settings", "entries", "expenses", "payments", "wages", "docs", "grievances", "changes"]) data[k] = store.get(k, null);
        const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
        h("a", { href: url, download: "rozi-data.json" }).click();
        URL.revokeObjectURL(url);
      }, "btn--ghost"),
      btn("🗑 Delete all my data", () => {
        if (!confirm("Delete all data on this phone? This cannot be undone.")) return;
        Object.keys(localStorage).filter((k) => k.startsWith(LS)).forEach((k) => localStorage.removeItem(k));
        location.hash = "#/onboarding";
        render();
      }, "btn--danger")),
    card(h("h2", {}, "What changed for you"), ...list("changes").slice(-10).reverse().map((c) => kv(c.label, c.at))));
};

views.health = async (root) => {
  root.append(h("h1", {}, "App health"));
  const out = card();
  root.append(out);
  const show = (r) => out.replaceChildren(kv("Mode", r.models.mode), kv("Active model", r.models.active || "none (built-in content)"), kv("Last check", r.models.last_check || "-"), kv("Last problem", r.models.last_failure_reason || "none"),
    btn("Re-check AI", async () => { try { show(await api("/api/health/models/recheck", {})); } catch (err) { toast(err.message); } }, "btn--ghost"));
  show(await api("/api/health/models"));
  root.append(card(h("h2", {}, "Recent problems on this phone"), h("p", {}, recentErrors.slice(-5).join(", ") || "None")));
};

// ---------- Fix-It (Tier A) ----------
const ACTIONS = {
  set_font_scale: { label: (p) => `Text size ${p.scale}x`, apply: (p) => saveSettings({ fontScale: p.scale }) },
  set_high_contrast: { label: () => "High contrast on", apply: (p) => saveSettings({ contrast: p.enabled }) },
  set_language: { label: (p) => `Language: ${p.lang}`, apply: (p) => saveSettings({ lang: p.lang }) },
  set_reading_level: { label: () => "Simple words", apply: (p) => saveSettings({ readingLevel: p.level }) },
  set_read_aloud_default: { label: () => "Read-aloud on", apply: (p) => saveSettings({ readAloud: p.enabled }) },
  reduce_alert_frequency: { label: (p) => `Max ${p.max_per_day} nudges a day`, apply: (p) => saveSettings({ alertCap: p.max_per_day }) },
  enable_quiet_mode: { label: () => "Quiet hours on", apply: (p) => saveSettings({ quiet: p.enabled }) },
  enable_lite_mode: { label: () => "Lite mode on", apply: (p) => saveSettings({ lite: p.enabled }) },
  switch_to_manual_entry: { label: () => "Typing instead of voice", apply: () => saveSettings({ manualVoice: true }) },
  mute_alert_type: { label: (p) => `Muted ${p.alert_type} alerts`, apply: (p) => saveSettings({ muted: [...(settings().muted || []), p.alert_type] }) },
  recalc_and_explain: { label: () => "Recalculated today", apply: () => { location.hash = "#/earnings"; } },
  clear_ui_cache_and_reload: { label: () => "Refreshed app screens", apply: async () => { if (window.caches) for (const k of await caches.keys()) await caches.delete(k); location.reload(); } },
  reset_view_state: { label: () => "Reset this screen", apply: () => store.set("pendingShift", null) },
  refresh_data_files: { label: () => "Refreshed scheme info", apply: async () => { if (window.caches) for (const k of await caches.keys()) await caches.delete(k); } },
  recheck_ai_models: { label: () => "Re-checked AI", apply: () => api("/api/health/models/recheck", {}) },
  repair_storage: { label: () => "Checked saved data", apply: () => { for (const k of ["entries", "expenses", "payments", "wages", "docs"]) saveList(k, list(k).filter((x) => x && typeof x === "object")); } },
  open_human_help: { label: () => "Opened human help", apply: () => { location.hash = "#/rights"; } },
  submit_report: { label: () => "Report sent", apply: () => {} },
};

views.fixit = (root) => {
  const s = settings();
  const text = h("textarea", { maxlength: 500, placeholder: "Tell us in your words, e.g. text is too small" });
  const out = h("div", { "aria-live": "polite" });
  const chips = [["TEXT_READABILITY", "Text too small"], ["ALERTS_NOISY", "Too many alerts"], ["LANGUAGE", "Can't understand language"], ["VOICE_INPUT", "Voice not working"], ["WRONG_NUMBER", "Number looks wrong"], ["PERFORMANCE", "App is slow"], ["FEATURE_BROKEN", "Something is broken"]];
  const run = async (chosen) => {
    try {
      const r = await api("/api/selfheal/triage", { text: redact(text.value), chosen_category: chosen || null, context: { lang: s.lang, route: "fixit", font_scale: s.fontScale, alert_cap: s.alertCap, today: todayISO(), recent_error_codes: recentErrors.slice(-5).filter((c) => /^[A-Z0-9_]{1,30}$/.test(c)) } });
      showDiagnosis(out, r.data, text.value);
    } catch (err) { toast(err.message); }
  };
  root.append(h("h1", {}, "Something not working?"), h("p", { class: "small muted" }, "Your words are checked for phone and ID numbers, then used only to fix the app. Not saved."),
    card(field("What is wrong?", text), btn("Fix it", () => run(null), "btn--wide"), h("div", { class: "row" }, ...chips.map(([c, l]) => btn(l, () => run(c), "btn--ghost")))), out);
};

function showDiagnosis(out, d, reportText) {
  const before = settings();
  const done = [];
  const applyAll = async (actions) => {
    for (const a of actions) {
      const spec = ACTIONS[a.action_id];
      if (!spec) continue; // whitelist only
      if (a.action_id === "submit_report") { await sendReport(d.category, reportText); continue; }
      await spec.apply(a.params);
      done.push(spec.label(a.params));
    }
    saveList("changes", [...list("changes"), ...done.map((label) => ({ label, at: new Date().toLocaleString() }))]);
    const counts = store.get("fixCounts", {});
    counts[d.category] = (counts[d.category] || 0) + 1;
    store.set("fixCounts", counts);
    out.replaceChildren(card(h("h2", {}, "Here's what I did"), h("p", {}, d.user_message), h("ul", {}, ...done.map((x) => h("li", {}, x))),
      counts[d.category] >= 2 ? h("p", { class: "small" }, "You reported this before, so I'll keep this as your default.") : null,
      btn("↩ Undo", () => { store.set("settings", before); applySettings(); toast("Undone"); render(); }, "btn--ghost"),
      h("p", {}, "Did this help?"), h("div", { class: "row" }, btn("Yes", () => toast("Great!"), "btn--ghost"), btn("No", () => sendReport(d.category, reportText), "btn--ghost"))));
  };
  const safe = d.actions.filter((a) => a.risk === "safe");
  const confirmNeeded = d.actions.filter((a) => a.risk === "confirm");
  if (d.clarify) {
    out.replaceChildren(card(h("p", {}, d.clarify.question)));
    return;
  }
  out.replaceChildren(card(h("p", {}, d.user_message), confirmNeeded.length ? btn(`Yes, do it (${confirmNeeded.map((a) => ACTIONS[a.action_id] ? ACTIONS[a.action_id].label(a.params) : a.action_id).join(", ")})`, () => applyAll(d.actions), "btn--wide") : null));
  if (safe.length && !confirmNeeded.length) applyAll(safe);
}

async function sendReport(category, text) {
  const s = settings();
  if (!s.reportOptIn) return toast("Turn on 'Allow sending anonymous problem reports' in Settings first.");
  let install = store.get("installId", null);
  if (!install) { install = uid(); store.set("installId", install); }
  try {
    await api("/api/report", { consent: true, category, route: "fixit", app_version: "1.0.0", error_codes: recentErrors.slice(-5).filter((c) => /^[A-Z0-9_]{1,30}$/.test(c)), description: redact(text || "").slice(0, 300), device_class: innerWidth < 700 ? "phone" : "desktop", install_id: install.toLowerCase() });
    toast("Thank you. Report sent.");
  } catch (err) { toast(err.message); }
}

// ---------- shell ----------
function applySettings() {
  const s = settings();
  const root = document.documentElement;
  root.lang = s.lang;
  root.style.setProperty("--font-scale", String(s.fontScale));
  if (s.contrast) root.dataset.contrast = "high";
  else delete root.dataset.contrast;
  root.dataset.lite = s.lite ? "on" : "off";
  const lang = document.getElementById("lang");
  if (lang) lang.value = s.lang;
  const demo = document.getElementById("demo-tag");
  if (demo) demo.hidden = !s.demo;
}

async function render() {
  const main = document.getElementById("main");
  const [path, query] = (location.hash.slice(2) || "home").split("?");
  const name = !settings().onboarded && path !== "onboarding" ? "onboarding" : path;
  const view = views[name] || views.home;
  document.querySelectorAll(".bottomnav a").forEach((a) => a.toggleAttribute("aria-current", a.getAttribute("href") === `#/${name}`));
  document.querySelectorAll(".bottomnav a[aria-current]").forEach((a) => a.setAttribute("aria-current", "page"));
  main.replaceChildren();
  const root = h("div", { class: "view" });
  main.append(root);
  try {
    await view(root, new URLSearchParams(query || ""));
  } catch (err) {
    recentErrors.push(`VIEW_${name.toUpperCase()}`.slice(0, 30));
    root.append(card(h("h2", {}, "This screen had a problem"), h("p", {}, err.message || "Please try again."), h("a", { class: "btn", href: "#/fixit" }, "Something not working?")));
  }
  main.focus({ preventScroll: true });
  scrollTo(0, 0);
}

document.addEventListener("DOMContentLoaded", () => {
  applySettings();
  document.getElementById("lang").addEventListener("change", (e) => { saveSettings({ lang: e.target.value }); render(); });
  document.getElementById("fixit-btn").addEventListener("click", () => { location.hash = "#/fixit"; });
  addEventListener("hashchange", render);
  addEventListener("offline", () => toast("You are offline. Entries are saved on this phone."));
  render();
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
});
