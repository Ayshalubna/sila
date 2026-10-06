/* Sila web app: hash-routed single page, no build step, no third-party code. */
(function () {
  "use strict";
  const I = window.SILA_I18N;
  const $ = (s, el = document) => el.querySelector(s);
  const main = $("#main");
  const tip = $("#tip");
  const NS = "http://www.w3.org/2000/svg";

  // ---------------------------------------------------------------- state
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode: keep in memory */ } },
  };
  let lang = store.get("sila.lang") === "ar" ? "ar" : "en";
  let session = store.get("sila.session");
  if (!session || !/^[A-Za-z0-9]{8,40}$/.test(session)) {
    const a = new Uint8Array(12);
    (window.crypto || window.msCrypto).getRandomValues(a);
    session = Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
    store.set("sila.session", session);
  }
  let introPlayed = false;
  const T = () => I[lang];
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---------------------------------------------------------------- formatting
  const nf = () => new Intl.NumberFormat(lang === "ar" ? "ar-AE-u-nu-latn" : "en-AE", { maximumFractionDigits: 0 });
  function aed(v, opts = {}) {
    const n = Math.round(v || 0);
    const s = nf().format(Math.abs(n));
    const neg = n < 0 ? "−" : (opts.sign && n > 0 ? "+" : "");
    return lang === "ar" ? `${neg}${s} درهم` : `${neg}AED ${s}`;
  }
  function aedShort(v) {
    const a = Math.abs(v), neg = v < 0 ? "−" : "";
    const s = a >= 1e6 ? (a / 1e6).toFixed(a >= 1e7 ? 0 : 1) + "M" : a >= 1e3 ? Math.round(a / 1e3) + "k" : String(Math.round(a));
    return lang === "ar" ? `${neg}${s}` : `${neg}${s}`;
  }
  const pct = (x) => `${Math.round((x || 0) * 100)}%`;
  function dfmt(iso, withYear = false) {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    return new Intl.DateTimeFormat(lang === "ar" ? "ar-AE-u-nu-latn" : "en-GB",
      withYear ? { day: "numeric", month: "long", year: "numeric" } : { day: "numeric", month: "short" }).format(d);
  }
  const nm = (o) => (lang === "ar" && o && o.name_ar ? o.name_ar : (o ? o.name : ""));
  const sector = (o) => (lang === "ar" ? o.sector_label_ar : o.sector_label);
  const statusPill = (s) => `<span class="st ${s}">${esc(T().status[s])}</span>`;
  const statusColor = { safe: "var(--teal)", watch: "var(--saffron)", at_risk: "var(--madder)", short: "var(--oxblood)" };
  const pColor = (p) => (p >= 0.3 ? "var(--madder)" : p >= 0.1 ? "var(--saffron)" : "var(--teal)");

  // ---------------------------------------------------------------- api
  async function api(path, opts = {}) {
    const res = await fetch(path, { ...opts, headers: { "Content-Type": "application/json", "X-Sila-Session": session, ...(opts.headers || {}) } });
    if (res.status === 429) { toast(T().rate); throw new Error("rate"); }
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.remove("show"), 3200);
  }
  function showTip(html, x, y) {
    tip.innerHTML = html;
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.max(8, top) + "px";
  }
  const hideTip = () => { tip.hidden = true; };

  // ---------------------------------------------------------------- language
  function applyLang() {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const v = T()[el.dataset.i18n];
      if (typeof v === "string") el.textContent = v;
    });
    $("#lang").textContent = T().lang_other;
    $("#lang").setAttribute("aria-label", lang === "ar" ? "Switch to English" : "التبديل إلى العربية");
  }
  $("#lang").addEventListener("click", () => {
    lang = lang === "ar" ? "en" : "ar";
    store.set("sila.lang", lang);
    applyLang();
    route();
  });
  $("#menuBtn").addEventListener("click", () => {
    const m = $("#mobileNav");
    m.hidden = !m.hidden;
    $("#menuBtn").setAttribute("aria-expanded", String(!m.hidden));
  });

  // ---------------------------------------------------------------- svg helpers
  function el(tag, attrs = {}, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function curve(a, b) {
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
    const cx = mx + (500 - mx) * 0.38, cy = my + (500 - my) * 0.38;
    return `M${a.x},${a.y} Q${cx},${cy} ${b.x},${b.y}`;
  }

  // ---------------------------------------------------------------- the mesh
  function drawMesh(box, net, { labels = true, intro = false, highlight = null } = {}) {
    const svg = el("svg", { viewBox: "0 0 1000 1000", class: "mesh" + (intro ? " intro" : ""), role: "img",
      "aria-label": lang === "ar" ? "خريطة شبكة الشركات وعمليات النقل المقترحة اليوم" : "Map of the business network and today's suggested cash moves" });
    const pos = {};
    net.nodes.forEach((n) => (pos[n.id] = n));
    const gE = el("g", {}, svg);
    net.edges.forEach((e, k) => {
      const a = pos[e.s], b = pos[e.c];
      if (!a || !b) return;
      const p = el("path", { d: curve(a, b), class: "edge" }, gE);
      if (intro) p.style.animationDelay = `${(k % 40) * 18}ms`;
      if (highlight && a.sector !== highlight && b.sector !== highlight) p.classList.add("dim");
    });
    const gF = el("g", {}, svg);
    net.flows.forEach((f) => {
      const a = pos[f.from], b = pos[f.to];
      if (!a || !b) return;
      el("path", { d: curve(a, b), class: `flow ${f.kind} ${f.status}` }, gF);
    });
    const gN = el("g", {}, svg);
    net.nodes.forEach((n, k) => {
      if (n.status === "at_risk" || n.status === "short") el("circle", { cx: n.x, cy: n.y, r: n.r + 1, class: "halo" }, gN);
      const c = el("circle", { cx: n.x, cy: n.y, r: n.r, class: `node ${n.status}`, tabindex: "0", role: "link",
        "aria-label": `${nm(n)}: ${T().status[n.status]}` }, gN);
      if (intro) c.style.animationDelay = `${400 + (k % 60) * 12}ms`;
      if (highlight && n.sector !== highlight) c.classList.add("dim");
      const tipHtml = () => `<b>${esc(nm(n))}</b><br>${esc(T().status[n.status])} · <span class="k">${pct(n.p)}</span>`;
      c.addEventListener("mouseenter", (ev) => showTip(tipHtml(), ev.clientX, ev.clientY));
      c.addEventListener("mousemove", (ev) => showTip(tipHtml(), ev.clientX, ev.clientY));
      c.addEventListener("mouseleave", hideTip);
      c.addEventListener("click", () => { hideTip(); location.hash = `#/b/${n.id}`; });
      c.addEventListener("keydown", (ev) => { if (ev.key === "Enter") location.hash = `#/b/${n.id}`; });
    });
    if (labels) {
      const gL = el("g", {}, svg);
      net.sectors.forEach((s) => {
        const dx = s.x - 500, dy = s.y - 500, d = Math.hypot(dx, dy) || 1;
        const t = el("text", { x: s.x + (dx / d) * 108, y: s.y + (dy / d) * 108 + 5, class: "sector-label" }, gL);
        t.textContent = lang === "ar" ? s.label_ar : s.label;
      });
    }
    box.appendChild(svg);
    return svg;
  }
  function meshLegend() {
    return `<div class="mesh-legend" aria-hidden="true">
      <span><i style="background:#8FA59D"></i>${esc(T().legend_safe)}</span>
      <span><i style="background:var(--saffron)"></i>${esc(T().legend_watch)}</span>
      <span><i style="background:var(--madder)"></i>${esc(T().legend_risk)}</span>
      <span><i style="background:var(--oxblood)"></i>${esc(T().legend_short)}</span>
      <span><i class="line"></i>${esc(T().legend_flow)}</span></div>`;
  }

  // ---------------------------------------------------------------- charts
  function scale(d0, d1, r0, r1) { const k = (r1 - r0) / ((d1 - d0) || 1); return (v) => r0 + (v - d0) * k; }
  function niceTicks(lo, hi, n = 4) {
    const span = hi - lo || 1, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n + 0.5) || mag * 10;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return out;
  }

  /* history (solid) + forecast fan (P10-P90 band, median), optional scenario fan */
  function fanChart(box, { history, fan, scenario = null, shortDate = null }) {
    box.innerHTML = "";
    const W = 760, H = 320, m = { l: 58, r: 18, t: 18, b: 30 };
    const pts = [...history.map((h) => h.v), ...fan.flatMap((f) => [f.q10, f.q90]), ...(scenario ? scenario.flatMap((f) => [f.q10, f.q90]) : []), 0];
    let lo = Math.min(...pts), hi = Math.max(...pts);
    const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
    const n = history.length + fan.length;
    const rtl = lang === "ar";
    const x = rtl ? scale(0, n - 1, W - m.r, m.l) : scale(0, n - 1, m.l, W - m.r);
    const y = scale(lo, hi, H - m.b, m.t);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": T().chart_title });
    const g = el("g", { class: "grid" }, svg);
    const ax = el("g", { class: "axis" }, svg);
    niceTicks(lo, hi, 4).forEach((v) => {
      el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, g);
      const t = el("text", { x: rtl ? W - m.r + 4 : m.l - 8, y: y(v) + 4, "text-anchor": rtl ? "start" : "end" }, ax);
      t.textContent = aedShort(v);
    });
    const all = [...history.map((h) => h.d), ...fan.map((f) => f.d)];
    [0, 30, 60, history.length - 1, n - 1].forEach((i) => {
      const t = el("text", { x: x(i), y: H - 8, "text-anchor": "middle" }, ax);
      t.textContent = dfmt(all[i]);
    });
    el("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: "zero" }, svg);
    const t0 = history.length - 1;
    el("line", { x1: x(t0), x2: x(t0), y1: m.t, y2: H - m.b, class: "today-mark" }, svg);
    const tl = el("text", { x: x(t0), y: m.t - 4, "text-anchor": "middle", class: "label" }, svg);
    tl.textContent = T().today_lbl;
    const band = (f, cls) => {
      const up = f.map((p, k) => `${x(t0 + 1 + k)},${y(p.q90)}`), dn = f.map((p, k) => `${x(t0 + 1 + k)},${y(p.q10)}`).reverse();
      el("path", { d: `M${x(t0)},${y(history[t0].v)} L${up.join(" L")} L${dn.join(" L")} Z`, class: `band ${cls}` }, svg);
      el("path", { d: `M${x(t0)},${y(history[t0].v)} L` + f.map((p, k) => `${x(t0 + 1 + k)},${y(p.q50)}`).join(" L"), class: `med ${cls}` }, svg);
    };
    band(fan, "");
    if (scenario) band(scenario, "scn");
    el("path", { d: "M" + history.map((h, k) => `${x(k)},${y(h.v)}`).join(" L"), class: "hist" }, svg);
    if (shortDate) {
      const k = fan.findIndex((f) => f.d === shortDate);
      if (k >= 0) {
        el("circle", { cx: x(t0 + 1 + k), cy: y(0), r: 5, fill: "var(--madder)", class: "dot" }, svg);
        const lab = el("text", { x: x(t0 + 1 + k), y: y(0) + 18, "text-anchor": "middle", class: "label red" }, svg);
        lab.textContent = dfmt(shortDate);
      }
    }
    // crosshair + tooltip
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
    const dot = el("circle", { r: 4.5, fill: "var(--basalt)", class: "dot", visibility: "hidden" }, svg);
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, class: "hit" }, svg);
    hit.addEventListener("mousemove", (ev) => {
      const r = svg.getBoundingClientRect();
      const px = (ev.clientX - r.left) * (W / r.width);
      let k = Math.round(rtl ? (W - m.r - px) / (W - m.l - m.r) * (n - 1) : (px - m.l) / (W - m.l - m.r) * (n - 1));
      k = Math.max(0, Math.min(n - 1, k));
      cross.setAttribute("x1", x(k)); cross.setAttribute("x2", x(k)); cross.setAttribute("visibility", "visible");
      let html;
      if (k <= t0) {
        const h = history[k];
        dot.setAttribute("cx", x(k)); dot.setAttribute("cy", y(h.v)); dot.setAttribute("visibility", "visible");
        html = `<b>${dfmt(h.d, true)}</b><br><span class="k">${esc(T().chart_hist)}</span> ${aed(h.v)}`;
      } else {
        const f = fan[k - t0 - 1];
        dot.setAttribute("cx", x(k)); dot.setAttribute("cy", y(f.q50)); dot.setAttribute("visibility", "visible");
        html = `<b>${dfmt(f.d, true)}</b><br><span class="k">${esc(T().chart_med)}</span> ${aed(f.q50)}<br><span class="k">${esc(T().chart_band)}</span> ${aed(f.q10)} – ${aed(f.q90)}`;
        if (scenario) { const s = scenario[k - t0 - 1]; html += `<br><span class="k">${esc(T().whatif_title)}</span> ${aed(s.q50)}`; }
      }
      showTip(html, ev.clientX, ev.clientY);
    });
    hit.addEventListener("mouseleave", () => { hideTip(); cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); });
    box.appendChild(svg);
    const leg = document.createElement("div");
    leg.className = "legend";
    leg.innerHTML = `<span><i style="background:var(--basalt)"></i>${esc(T().chart_hist)}</span>
      <span><i style="background:var(--teal-deep)"></i>${esc(T().chart_med)}</span>
      <span><i class="band"></i>${esc(T().chart_band)}</span>
      ${scenario ? `<span><i style="background:var(--saffron)"></i>${esc(T().whatif_title)}</span>` : ""}
      <span><i style="background:var(--madder);height:0;border-top:2px dashed var(--madder)"></i>${esc(T().chart_zero)}</span>`;
    box.appendChild(leg);
  }

  /* two series over weeks: without vs with Sila */
  function twoLines(box, rows, { a, b, labelA, labelB, h = 260, fmt = (v) => nf().format(v), xfmt = (r) => dfmt(r.week) }) {
    box.innerHTML = "";
    const W = 760, H = h, m = { l: 44, r: 96, t: 14, b: 28 };
    const rtl = lang === "ar";
    const hi = Math.max(...rows.flatMap((r) => [r[a], r[b]])) * 1.1 || 1;
    const x = rtl ? scale(0, rows.length - 1, W - m.l, m.r) : scale(0, rows.length - 1, m.l, W - m.r);
    const y = scale(0, hi, H - m.b, m.t);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${labelA} / ${labelB}` });
    const g = el("g", { class: "grid" }, svg), ax = el("g", { class: "axis" }, svg);
    niceTicks(0, hi, 4).forEach((v) => {
      el("line", { x1: rtl ? m.r : m.l, x2: rtl ? W - m.l : W - m.r, y1: y(v), y2: y(v) }, g);
      const t = el("text", { x: rtl ? W - m.l + 6 : m.l - 8, y: y(v) + 4, "text-anchor": rtl ? "start" : "end" }, ax);
      t.textContent = fmt(v);
    });
    rows.forEach((r, k) => { if (k % 4 === 0) { const t = el("text", { x: x(k), y: H - 8, "text-anchor": "middle" }, ax); t.textContent = xfmt(r); } });
    const line = (key, cls) => el("path", { d: "M" + rows.map((r, k) => `${x(k)},${y(r[key])}`).join(" L"), class: cls }, svg);
    line(a, "line-without");
    line(b, "line-with");
    const last = rows.length - 1;
    const la = el("text", { x: x(last) + (rtl ? -8 : 8), y: y(rows[last][a]) + 4, class: "label", "text-anchor": rtl ? "end" : "start" }, svg); la.textContent = labelA;
    const lb = el("text", { x: x(last) + (rtl ? -8 : 8), y: y(rows[last][b]) + 4 + (Math.abs(y(rows[last][a]) - y(rows[last][b])) < 16 ? 14 : 0), class: "label strong", "text-anchor": rtl ? "end" : "start" }, svg); lb.textContent = labelB;
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
    const hit = el("rect", { x: 0, y: m.t, width: W, height: H - m.t - m.b, class: "hit" }, svg);
    hit.addEventListener("mousemove", (ev) => {
      const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * (W / r.width);
      let k = Math.round(rtl ? (W - m.l - px) / (W - m.l - m.r) * (rows.length - 1) : (px - m.l) / (W - m.l - m.r) * (rows.length - 1));
      k = Math.max(0, Math.min(rows.length - 1, k));
      cross.setAttribute("x1", x(k)); cross.setAttribute("x2", x(k)); cross.setAttribute("visibility", "visible");
      showTip(`<b>${esc(xfmt(rows[k]))}</b><br><span class="k">${esc(labelA)}</span> ${fmt(rows[k][a])}<br><span class="k">${esc(labelB)}</span> ${fmt(rows[k][b])}`, ev.clientX, ev.clientY);
    });
    hit.addEventListener("mouseleave", () => { hideTip(); cross.setAttribute("visibility", "hidden"); });
    box.appendChild(svg);
    const leg = document.createElement("div");
    leg.className = "legend";
    leg.innerHTML = `<span><i style="background:var(--madder)"></i>${esc(labelA)}</span><span><i style="background:var(--teal)"></i>${esc(labelB)}</span>`;
    box.appendChild(leg);
  }

  function spark(vals) {
    const W = 120, H = 30, lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const rtl = lang === "ar";
    const x = rtl ? scale(0, vals.length - 1, W - 2, 2) : scale(0, vals.length - 1, 2, W - 2), y = scale(lo, hi, H - 3, 3);
    return `<svg class="spark" viewBox="0 0 ${W} ${H}" aria-hidden="true"><line class="z" x1="0" x2="${W}" y1="${y(0)}" y2="${y(0)}"/><path class="l" d="M${vals.map((v, k) => `${x(k)},${y(v)}`).join(" L")}"/></svg>`;
  }

  // ---------------------------------------------------------------- move cards
  function legText(m, lg) {
    return { invoice: esc(lg.invoice), amount: aed(lg.amount), to: dfmt(lg.to_date), from: dfmt(lg.from_date), payer: esc(nm(lg.payer)) };
  }
  function moveHtml(m) {
    const t = T();
    const helper = esc(nm(m.helper)), helps = esc(nm(m.helps));
    const helperRaw = nm(m.helper), helpsRaw = nm(m.helps);
    let what;
    if (m.kind === "chain") {
      what = t.move_chain({ helper }, legText(m, m.legs[0]), legText(m, m.legs[1]));
    } else {
      const f = m.kind === "grace" ? t.move_grace : t.move_early;
      what = f({ helper }, legText(m, m.legs[0]));
      if (m.legs.length > 1) what += ` <span class="muted small">${esc(t.more_invoices(m.legs.length - 1))}</span>`;
    }
    const st = m.status;
    const dec = m.decisions || {};
    const chip = (party, who) => {
      const d = dec[party];
      if (d === "accept") return `<span class="chip yes" aria-label="${esc(t.agrees(who))}">✓ ${esc(t.agrees(who))}</span>`;
      if (st === "declined" || st === "agreed") return "";
      return `<button class="chip" type="button" data-move="${m.id}" data-party="${party}" data-decision="accept">${esc(t.agrees(who))}</button>`;
    };
    const decline = st === "proposed" || st === "waiting" ? `<button class="chip no" type="button" data-move="${m.id}" data-party="${dec.helped === "accept" ? "helper" : "helped"}" data-decision="decline">${esc(t.declines)}</button>` : "";
    return `<article class="move ${st}" id="mv-${m.id}">
      <p class="what"><span class="st safe" style="margin-inline-end:8px">${esc(t.kind[m.kind])}</span>${what}</p>
      <div class="facts">
        <span>${esc(t.f_amount)} <b class="num">${aed(m.amount)}</b></span>
        <span>${esc(t.f_fee)} <b class="num">${m.fee ? aed(m.fee) : esc(t.free)}</b></span>
        <span>${esc(t.f_loan)} <b class="num">${aed(m.loan_cost)}</b></span>
        <span>${esc(t.f_buffer)} <b>${esc(t.days_cover(Math.round(m.helper_buffer_days)))}</b></span>
      </div>
      <div class="consent">
        ${st === "agreed" ? `<span class="agreed-note">✓ ${esc(t.agreed)}</span>` : st === "declined" ? `<span class="muted small">${esc(t.declined)}</span>` : `${chip("helped", helpsRaw)}${chip("helper", helperRaw)}${decline}`}
      </div>
      <div class="impact" data-impact="${m.id}"></div>
    </article>`;
  }
  function bindMoves(scope, after) {
    scope.querySelectorAll("button[data-move]").forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const r = await api(`/api/moves/${b.dataset.move}/decision`, { method: "POST", body: JSON.stringify({ party: b.dataset.party, decision: b.dataset.decision }) });
        const card = scope.querySelector(`#mv-${CSS.escape(r.move.id)}`);
        if (card) {
          const wrap = document.createElement("div");
          wrap.innerHTML = moveHtml(r.move);
          card.replaceWith(wrap.firstElementChild);
          if (r.impact) {
            const imp = scope.querySelector(`[data-impact="${CSS.escape(r.move.id)}"]`);
            if (imp) imp.textContent = T().impact(pct(r.impact.helps.before), pct(r.impact.helps.after), pct(r.impact.helper.after));
            toast(T().toast_agreed);
          }
          bindMoves(scope, after);
        }
        if (r.impact && after) after(r);
      } catch (e) { if (e.message !== "rate") toast(T().err); b.disabled = false; }
    }));
  }

  // ---------------------------------------------------------------- pages
  async function pageHome() {
    const [o, net, mv, proof] = await Promise.all([api("/api/overview"), api("/api/network"), api("/api/moves"), api("/api/proof")]);
    const t = T();
    const top = mv.moves.find((m) => m.kind === "early_payment" && m.verified && m.verified.p_short_after < 0.3) || mv.moves[0];
    const atRisk = o.status_counts.at_risk + o.status_counts.short;
    const gapTotal = mv.plans.reduce((s, p) => s + (p.gap_before || 0), 0);
    main.innerHTML = `<div class="wrap">
      <section class="hero">
        <div class="hero-copy">
          <h1 class="display">${esc(t.hero_title)}</h1>
          <p class="lede">${esc(t.hero_lede)}</p>
          ${top ? `<p class="hero-live">${t.hero_live(esc(nm(top.helps)), dfmt(top.shortfall_date, true), esc(nm(top.helper)), aed(top.amount))}</p>` : ""}
          <div class="row">
            <a class="btn" href="#/today">${esc(t.cta_today(mv.moves.length))}</a>
            <a class="btn ghost" href="#/how">${esc(t.cta_how)}</a>
          </div>
        </div>
        <div><div class="mesh-box" id="mesh"></div>${meshLegend()}</div>
      </section>
      <p class="today-line">${t.today_line({ date: dfmt(o.today, true), atRisk, total: o.businesses, gap: aed(gapTotal), cover: aed(o.cover_today), helped: o.businesses_helped_today })}</p>
      <section class="section">
        <h2>${esc(t.steps_title)}</h2>
        <div class="steps">
          <div class="step"><div class="n">1</div><h3>${esc(t.s1_t)}</h3><p>${esc(t.s1_p)}</p>${stepArt(1)}</div>
          <div class="step"><div class="n">2</div><h3>${esc(t.s2_t)}</h3><p>${esc(t.s2_p)}</p>${stepArt(2)}</div>
          <div class="step"><div class="n">3</div><h3>${esc(t.s3_t)}</h3><p>${esc(t.s3_p)}</p>${stepArt(3)}</div>
        </div>
      </section>
      <section class="section">
        <div class="section-head"><div><h2>${esc(t.proof_title)}</h2><p>${esc(t.proof_p(proof.replay))}</p></div>
          <a class="btn ghost small" href="#/proof">${esc(t.proof_link)}</a></div>
        <div class="panel"><h3>${esc(t.chart_weekly)}</h3><div class="chart" id="weekly"></div></div>
      </section></div>`;
    drawMesh($("#mesh"), net, { intro: !introPlayed });
    introPlayed = true;
    twoLines($("#weekly"), proof.weeks, { a: "short_without", b: "short_with", labelA: t.without, labelB: t.with });
  }
  function stepArt(k) {
    if (k === 1) return `<svg viewBox="0 0 300 90" aria-hidden="true"><path d="M0 40 C40 30 60 52 100 46" fill="none" stroke="var(--basalt)" stroke-width="2"/><path d="M100 46 L300 18 L300 88 Z" fill="var(--teal)" fill-opacity=".18"/><path d="M100 46 C160 50 220 60 300 54" fill="none" stroke="var(--teal-deep)" stroke-width="2"/><line x1="0" x2="300" y1="70" y2="70" stroke="var(--madder)" stroke-dasharray="4 4"/></svg>`;
    if (k === 2) return `<svg viewBox="0 0 300 90" aria-hidden="true"><path d="M40 60 Q150 0 260 50" fill="none" stroke="var(--teal)" stroke-width="2.6" stroke-dasharray="3 9" class="flowart"/><circle cx="40" cy="60" r="11" fill="#8FA59D"/><circle cx="260" cy="50" r="11" fill="var(--madder)"/></svg>`;
    return `<svg viewBox="0 0 300 90" aria-hidden="true"><rect x="20" y="28" width="118" height="36" rx="18" fill="var(--teal)"/><path d="M42 46 l8 8 l16 -16" stroke="#fff" stroke-width="3" fill="none"/><text x="74" y="51" fill="#fff" font-size="13" font-weight="650">${lang === "ar" ? "المالك 1" : "Owner 1"}</text><rect x="162" y="28" width="118" height="36" rx="18" fill="var(--teal)"/><path d="M184 46 l8 8 l16 -16" stroke="#fff" stroke-width="3" fill="none"/><text x="216" y="51" fill="#fff" font-size="13" font-weight="650">${lang === "ar" ? "المالك 2" : "Owner 2"}</text></svg>`;
  }

  async function pageToday() {
    const [mv, o] = await Promise.all([api("/api/moves"), api("/api/overview")]);
    const t = T();
    const byId = Object.fromEntries(mv.moves.map((m) => [m.id, m]));
    const plans = mv.plans.map((p) => {
      const done = p.moves.every((id) => byId[id].status === "agreed");
      return `<section class="plan${done ? " done" : ""}">
        <div>
          <h3><a href="#/b/${p.business.id}">${esc(nm(p.business))}</a></h3>
          <div class="sub">${esc(sector(p))} · ${esc(t.plan_short_on(dfmt(p.shortfall_date, true)))}</div>
          ${statusPill(p.status_now)}
          <div class="risk-change"><span class="v before">${pct(p.p_before)}</span><span class="arrow">→</span><span class="v after">${pct(p.p_after)}</span></div>
          <p class="risk-cap">${esc(t.risk_caption)}</p>
          <p class="risk-cap muted">${esc(t.gap_caption(aed(p.gap_before), aed(p.gap_after)))}</p>
        </div>
        <div class="moves">${p.moves.map((id) => moveHtml(byId[id])).join("")}</div>
      </section>`;
    }).join("");
    const adv = mv.advisories.map((a) => `<div class="advice-item"><h3><a href="#/b/${a.business.id}">${esc(nm(a.business))}</a></h3>
      <p>${esc(t.adv_reason[a.reason] || a.reason)} ${esc(t.adv_line(dfmt(a.date, true), aed(a.gap)))}</p></div>`).join("");
    main.innerHTML = `<div class="wrap">
      <div class="section-head" style="margin-top:36px"><div><h1 class="page">${esc(t.today_title)}</h1>
        <p class="lede">${esc(t.today_lede(mv.plans.length, mv.moves.length, dfmt(o.today, true)))}</p></div>
        <button class="btn ghost small" id="reset" type="button">${esc(t.reset)}</button></div>
      <div class="plans" id="plans">${plans || `<p class="empty">—</p>`}</div>
      ${adv ? `<section class="advice"><h2>${esc(t.advice_title)}</h2><p class="muted">${esc(t.advice_p)}</p>${adv}</section>` : ""}
    </div>`;
    bindMoves($("#plans"), () => setTimeout(() => { if (location.hash.startsWith("#/today")) refreshPlans(); }, 2600));
    $("#reset").addEventListener("click", async () => { await api("/api/session/reset", { method: "POST" }); toast(t.reset_done); pageToday(); });
  }
  async function refreshPlans() {
    const y = window.scrollY;
    await pageToday();
    window.scrollTo(0, y);
  }

  const bizQuery = { q: "", sector: "", emirate: "", status: "", page: 1 };
  async function pageBusinesses() {
    const t = T();
    const qs = new URLSearchParams({ ...bizQuery, size: 25 }).toString();
    const d = await api(`/api/businesses?${qs}`);
    const segs = ["", "at_risk", "watch", "safe", "short"].map((s) => `<button type="button" data-status="${s}" aria-pressed="${bizQuery.status === s}">${esc(s ? t.status[s] : t.all)}</button>`).join("");
    const rows = d.rows.map((r) => `<tr data-id="${r.id}" tabindex="0">
      <td><span class="nm">${esc(r.name)}</span><span class="nm-ar" lang="ar">${esc(r.name_ar)}</span></td>
      <td>${esc(sector(r))}</td><td>${esc(lang === "ar" ? r.emirate_ar : r.emirate)}</td>
      <td class="num">${aed(r.balance)}</td><td>${spark(r.spark)}</td>
      <td><div class="pbar"><div class="track"><div class="fill" style="width:${Math.max(2, r.p_short * 100)}%;background:${pColor(r.p_short)}"></div></div><span class="num small">${pct(r.p_short)}</span></div></td>
      <td>${statusPill(r.status)}</td></tr>`).join("");
    const from = (d.page - 1) * d.size + 1, to = Math.min(d.total, d.page * d.size);
    main.innerHTML = `<div class="wrap">
      <h1 class="page" style="margin-top:36px">${esc(t.biz_title)}</h1><p class="lede">${esc(t.biz_lede(240))}</p>
      <div class="filters">
        <input class="search" id="q" type="search" placeholder="${esc(t.search_ph)}" value="${esc(bizQuery.q)}" aria-label="${esc(t.search_ph)}">
        <select class="select" id="sector" aria-label="${esc(t.th_sector)}"><option value="">${esc(t.all_sectors)}</option>${d.sectors.map((s) => `<option value="${s.id}" ${bizQuery.sector === s.id ? "selected" : ""}>${esc(lang === "ar" ? s.label_ar : s.label)}</option>`).join("")}</select>
        <select class="select" id="emirate" aria-label="${esc(t.th_emirate)}"><option value="">${esc(t.all_emirates)}</option>${d.emirates.map((e) => `<option value="${esc(e[0])}" ${bizQuery.emirate === e[0] ? "selected" : ""}>${esc(lang === "ar" ? e[1] : e[0])}</option>`).join("")}</select>
        <div class="seg" role="group" aria-label="${esc(t.th_status)}">${segs}</div>
      </div>
      <div class="table-wrap"><table class="biz"><thead><tr><th>${esc(t.th_business)}</th><th>${esc(t.th_sector)}</th><th>${esc(t.th_emirate)}</th><th>${esc(t.th_cash)}</th><th>${esc(t.th_outlook)}</th><th>${esc(t.th_risk)}</th><th>${esc(t.th_status)}</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="7" class="empty">${esc(t.none)}</td></tr>`}</tbody></table></div>
      <div class="pager"><span>${d.total ? esc(t.page_of(from, to, d.total)) : ""}</span>
        <button class="btn ghost small" id="prev" type="button" ${d.page <= 1 ? "disabled" : ""}>${esc(t.prev)}</button>
        <button class="btn ghost small" id="next" type="button" ${to >= d.total ? "disabled" : ""}>${esc(t.next)}</button></div></div>`;
    let timer;
    $("#q").addEventListener("input", (e) => { clearTimeout(timer); timer = setTimeout(() => { bizQuery.q = e.target.value.slice(0, 60); bizQuery.page = 1; pageBusinesses().then(() => { const q = $("#q"); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }); }, 250); });
    $("#sector").addEventListener("change", (e) => { bizQuery.sector = e.target.value; bizQuery.page = 1; pageBusinesses(); });
    $("#emirate").addEventListener("change", (e) => { bizQuery.emirate = e.target.value; bizQuery.page = 1; pageBusinesses(); });
    main.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => { bizQuery.status = b.dataset.status; bizQuery.page = 1; pageBusinesses(); }));
    $("#prev").addEventListener("click", () => { bizQuery.page--; pageBusinesses(); });
    $("#next").addEventListener("click", () => { bizQuery.page++; pageBusinesses(); });
    main.querySelectorAll("tbody tr[data-id]").forEach((tr) => {
      tr.addEventListener("click", () => (location.hash = `#/b/${tr.dataset.id}`));
      tr.addEventListener("keydown", (e) => { if (e.key === "Enter") location.hash = `#/b/${tr.dataset.id}`; });
    });
  }

  async function pageBusiness(id) {
    const t = T();
    const b = await api(`/api/businesses/${encodeURIComponent(id)}`);
    const low = Math.min(...b.fan.map((f) => f.q50));
    const summary = b.status === "short" ? t.sum_short(aed(b.balance), pct(b.p_short))
      : b.p_short >= 0.1 ? t.sum_risk(aed(b.balance), pct(b.p_short), dfmt(b.first_date, true)) : t.sum_safe(aed(b.balance), aed(low));
    const w = b.why;
    const whys = [];
    if (b.p_short >= 0.1 || b.status === "short") {
      w.big_outflows.forEach((o) => whys.push(`<li>${esc(t.why_outflow(t.item[o.kind] || o.label, aed(o.amount), dfmt(o.date)))}</li>`));
      w.late_receipts.forEach((r) => whys.push(`<li>${esc(t.why_late(nm(r.counterparty), aed(r.amount), dfmt(r.due), dfmt(r.expected)))}</li>`));
      if (w.sales_change != null && Math.abs(w.sales_change) >= 0.05) whys.push(`<li class="${w.sales_change > 0 ? "good" : ""}">${esc(t.why_sales(w.sales_change))}</li>`);
      if (!whys.length) whys.push(`<li>${esc(t.why_none)}</li>`);
    } else whys.push(`<li class="good">${esc(t.why_safe)}</li>`);
    const items = b.items.map((x) => {
      const who = x.counterparty ? esc(nm(x.counterparty)) : "";
      const label = esc(t.item[x.kind] || x.label);
      let note = x.dir === "in" && x.range ? esc(t.exp_range(dfmt(x.range[0]), dfmt(x.range[1]))) : "";
      if (x.agreed) note = esc(t.agreed_date);
      const why = x.dir === "in" && !x.agreed ? ` <button class="linkbtn" type="button" data-why="${esc(x.invoice)}">${esc(t.why_date)}</button>` : "";
      return `<li><span class="d">${dfmt(x.date)}</span><span>${label}${who ? ` · ${who}` : ""}<span class="n">${note ? `<br>${note}` : ""}${why}</span><div class="explain-slot" data-slot="${esc(x.invoice || "")}"></div></span>
        <span class="a ${x.dir}">${aed(x.dir === "in" ? x.amount : -x.amount, { sign: true })}</span></li>`;
    }).join("");
    const partners = b.partners.map((p) => `<a class="partner" href="#/b/${p.id}"><span>${esc(nm(p))}<small>${esc(p.relation === "supplier" ? t.supplier : t.customer)} · ${esc(sector(p))}</small></span>${statusPill(p.status)}</a>`).join("");
    const sh = b.sila_history;
    main.innerHTML = `<div class="wrap">
      <a class="back" href="#/businesses">← ${esc(t.back_all)}</a>
      <div class="biz-head"><div><h1 class="page">${esc(lang === "ar" ? b.name_ar : b.name)}</h1>
        <div class="ar-name" ${lang === "ar" ? "" : 'lang="ar"'}>${esc(lang === "ar" ? b.name : b.name_ar)}</div>
        <div class="tags"><span class="tag">${esc(sector(b))}</span><span class="tag">${esc(lang === "ar" ? b.emirate_ar : b.emirate)}</span>
          <span class="tag">${esc(t.tag_staff(b.staff))}</span><span class="tag">${esc(t.tag_rev(aed(b.monthly_revenue)))}</span><span class="tag">${esc(t.tag_partners(b.partners.length))}</span></div></div>
        ${statusPill(b.status)}</div>
      <div class="cols">
        <div>
          <div class="panel"><p class="summary-big">${summary}</p><h3 class="muted small" style="font-weight:560">${esc(t.chart_title)}</h3><div class="chart" id="fan"></div></div>
          <div class="panel"><h2>${esc(t.moves_title)}</h2><div class="moves" id="bmoves" style="margin-top:12px">${b.moves.length ? b.moves.map(moveHtml).join("") : `<p class="muted">${esc(t.moves_none)}</p>`}</div></div>
          <div class="panel"><h2>${esc(t.money_title)}</h2><ul class="money" id="money">${items || `<li class="muted">${esc(t.money_none)}</li>`}</ul></div>
        </div>
        <div>
          <div class="panel"><h2>${esc(t.why_title)}</h2><ul class="why-list">${whys.join("")}</ul></div>
          <div class="panel"><h2>${esc(t.whatif_title)}</h2>
            <form class="whatif" id="wi">
              <label>${esc(t.wi_sales)} <output id="o_s">0%</output><input type="range" id="wi_s" min="-60" max="40" step="5" value="0"></label>
              <label>${esc(t.wi_late)} <output id="o_l">${esc(t.days(0))}</output><input type="range" id="wi_l" min="0" max="60" step="5" value="0"></label>
              <label>${esc(t.wi_exp)} <output id="o_e">${aed(0)}</output><input type="range" id="wi_e" min="0" max="${Math.max(50000, Math.round(b.monthly_revenue / 10000) * 10000)}" step="5000" value="0"></label>
              <label>${esc(t.wi_day)} <output id="o_d">7</output><input type="range" id="wi_d" min="1" max="28" step="1" value="7"></label>
            </form>
            <p class="wi-result" id="wi_r">${esc(t.wi_hint)}</p></div>
          ${partners ? `<div class="panel"><h2>${esc(t.partners_title)}</h2><div class="partners">${partners}</div></div>` : ""}
          ${(sh.helped || sh.helper) ? `<div class="panel"><h2>${esc(t.history_title)}</h2><p>${esc(t.history_p(sh.helped, aed(sh.helped_aed), sh.helper, aed(sh.helper_aed)))}</p></div>` : ""}
        </div>
      </div></div>`;
    fanChart($("#fan"), { history: b.history, fan: b.fan, shortDate: b.p_short >= 0.3 ? b.first_date : null });
    bindMoves($("#bmoves"), () => setTimeout(() => pageBusiness(id), 2600));
    main.querySelectorAll("button[data-why]").forEach((btn) => btn.addEventListener("click", async () => {
      const slot = main.querySelector(`[data-slot="${CSS.escape(btn.dataset.why)}"]`);
      if (slot.innerHTML) { slot.innerHTML = ""; return; }
      try {
        const e = await api(`/api/invoices/${encodeURIComponent(btn.dataset.why)}/why`);
        const mx = Math.max(1, ...e.drivers.map((d) => Math.abs(d.days)));
        slot.innerHTML = `<div class="explain"><p style="margin:0 0 6px">${esc(t.explain_head(t.days(Math.round(e.baseline_days)), (e.adjustment > 0 ? "+" : "") + e.adjustment))}</p>
          ${e.drivers.map((d) => `<div class="bar"><span>${esc(d.feature)}</span><span class="b"><i style="${d.days >= 0 ? "inset-inline-start:50%" : "inset-inline-end:50%"};width:${Math.abs(d.days) / mx * 50}%;background:${d.days > 0 ? "var(--madder)" : "var(--teal)"}"></i></span><span class="num">${d.days > 0 ? "+" : ""}${d.days}</span></div>`).join("")}</div>`;
      } catch (err) { toast(T().err); }
    }));
    // what-if
    const ids = ["s", "l", "e", "d"];
    let wt;
    const upd = () => {
      const s = +$("#wi_s").value, l = +$("#wi_l").value, ex = +$("#wi_e").value, dd = +$("#wi_d").value;
      $("#o_s").textContent = `${s > 0 ? "+" : ""}${s}%`;
      $("#o_l").textContent = t.days(l);
      $("#o_e").textContent = aed(ex);
      $("#o_d").textContent = dd;
      clearTimeout(wt);
      wt = setTimeout(async () => {
        if (!s && !l && !ex) { $("#wi_r").textContent = t.wi_hint; fanChart($("#fan"), { history: b.history, fan: b.fan, shortDate: b.p_short >= 0.3 ? b.first_date : null }); return; }
        try {
          const r = await api("/api/whatif", { method: "POST", body: JSON.stringify({ business: id, sales_change: s / 100, late_days: l, expense: ex, expense_day: dd }) });
          $("#wi_r").innerHTML = t.wi_result(pct(r.base.p_short), pct(r.scenario.p_short));
          fanChart($("#fan"), { history: b.history, fan: r.base.fan, scenario: r.scenario.fan });
        } catch (e) { /* toast shown for rate limit */ }
      }, 350);
    };
    ids.forEach((k) => $("#wi_" + k).addEventListener("input", upd));
  }

  async function pageNetwork() {
    const t = T();
    const net = await api("/api/network");
    main.innerHTML = `<div class="wrap"><h1 class="page" style="margin-top:36px">${esc(t.net_title)}</h1><p class="lede">${esc(t.net_lede)}</p>
      <div class="filters"><select class="select" id="hl" aria-label="${esc(t.th_sector)}"><option value="">${esc(t.all_sectors)}</option>${net.sectors.map((s) => `<option value="${s.id}">${esc(lang === "ar" ? s.label_ar : s.label)}</option>`).join("")}</select></div>
      <div class="mesh-box" id="mesh" style="max-width:900px;margin:0 auto"></div>${meshLegend()}</div>`;
    drawMesh($("#mesh"), net);
    $("#hl").addEventListener("change", (e) => { $("#mesh").innerHTML = ""; drawMesh($("#mesh"), net, { highlight: e.target.value || null }); });
  }

  async function pageProof() {
    const t = T();
    const p = await api("/api/proof");
    const r = p.replay, ev = p.eval || {}, a = ev.alerts || {}, tm = ev.timing || {}, sl = ev.sales || {}, cal = ev.calibration || {};
    const stories = p.stories.map((s, k) => `<div class="panel story"><h3><a href="#/b/${s.business.id}">${esc(nm(s.business))}</a></h3>
      <p>${esc(t.story_p({ date: dfmt(s.would_be_short, true), days: s.days, depth: aed(s.depth), lead: s.lead_days, n: s.moves.length }))}</p><div class="chart" id="story${k}"></div></div>`).join("");
    main.innerHTML = `<div class="wrap">
      <h1 class="page" style="margin-top:36px">${esc(t.pf_title)}</h1><p class="lede">${esc(t.pf_lede)}</p>
      <div class="facts-row">
        <div class="fact"><div class="v">${pct(r.episodes_prevented_share)}</div><p>${esc(t.pf_f1)} (${r.episodes_prevented}/${r.episodes_baseline})</p></div>
        <div class="fact"><div class="v">${pct(r.episode_days_avoided_share)}</div><p>${esc(t.pf_f2)}</p></div>
        <div class="fact"><div class="v">${r.helpers_pushed_into_shortfall}</div><p>${esc(t.pf_f3)}</p></div>
        <div class="fact"><div class="v">${pct(r.saving_vs_loan)}</div><p>${esc(t.pf_f4)}</p></div>
      </div>
      <section class="section"><div class="panel"><h3>${esc(t.pf_weekly)}</h3><div class="chart" id="weekly"></div></div></section>
      <section class="section"><h2>${esc(t.pf_alerts)}</h2><p class="muted">${esc(t.pf_alerts_p(a))}</p>
        <table class="cmp"><thead><tr><th>${esc(t.th_measure)}</th><th>${esc(t.th_sila)}</th><th>${esc(t.th_rule)}</th></tr></thead><tbody>
          <tr><td>${esc(t.m_precision)}</td><td class="win num">${pct(a.precision)}</td><td class="num">${pct(a.naive_precision)}</td></tr>
          <tr><td>${esc(t.m_recall)}</td><td class="win num">${pct(a.recall)}</td><td class="num">${pct(a.naive_recall)}</td></tr>
          <tr><td>${esc(t.m_auc)}</td><td class="win num">${a.auc}</td><td class="num">${a.naive_auc}</td></tr>
        </tbody></table><p class="small muted">${esc(t.rule_note)}</p></section>
      <section class="section"><h2>${esc(t.pf_parts)}</h2>
        <table class="cmp"><thead><tr><th>${esc(t.th_measure)}</th><th>${esc(t.th_sila)}</th><th>${esc(t.th_rule)}</th></tr></thead><tbody>
          <tr><td>${esc(t.m_timing)}</td><td class="win num">${tm.mae_days}</td><td class="num">${tm.baseline_mae_days} <span class="muted">(${esc(t.rule_timing)})</span></td></tr>
          <tr><td>${esc(t.m_sales)}</td><td class="win num">${pct(sl.wape)}</td><td class="num">${pct(sl.baseline_wape)} <span class="muted">(${esc(t.rule_sales)})</span></td></tr>
          <tr><td>${esc(t.m_cov)}</td><td class="win num">${pct(cal.coverage_p10_p90)}</td><td class="muted">${esc(t.target80)}</td></tr>
        </tbody></table></section>
      <section class="section"><h2>${esc(t.pf_stories)}</h2><div class="stories">${stories}</div></section>
      <section class="section prose"><h2>${esc(t.pf_limits)}</h2><p>${esc(t.pf_limits_p)}</p><p class="small"><a href="https://github.com/Ayshalubna/sila/blob/main/eval/RESULTS.md" rel="noopener">${esc(t.pf_more)}</a></p></section></div>`;
    twoLines($("#weekly"), p.weeks, { a: "short_without", b: "short_with", labelA: t.without, labelB: t.with });
    p.stories.forEach((s, k) => {
      const start = new Date(s.start + "T00:00:00");
      const rows = s.balance_without.map((v, i) => ({ week: new Date(start.getTime() + i * 864e5).toISOString().slice(0, 10), without: v, with: s.balance_with[i] }));
      storyChart($(`#story${k}`), rows, t);
    });
  }
  function storyChart(box, rows, t) {
    box.innerHTML = "";
    const W = 380, H = 170, m = { l: 46, r: 12, t: 10, b: 24 }, rtl = lang === "ar";
    const vals = rows.flatMap((r) => [r.without, r.with, 0]);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    const x = rtl ? scale(0, rows.length - 1, W - m.r, m.l) : scale(0, rows.length - 1, m.l, W - m.r), y = scale(lo, hi, H - m.b, m.t);
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${t.without} / ${t.with}` });
    const ax = el("g", { class: "axis" }, svg), g = el("g", { class: "grid" }, svg);
    niceTicks(lo, hi, 3).forEach((v) => { el("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v) }, g); const tx = el("text", { x: rtl ? W - m.r + 4 : m.l - 6, y: y(v) + 4, "text-anchor": rtl ? "start" : "end" }, ax); tx.textContent = aedShort(v); });
    el("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: "zero" }, svg);
    el("path", { d: "M" + rows.map((r, k) => `${x(k)},${y(r.without)}`).join(" L"), class: "line-without" }, svg);
    el("path", { d: "M" + rows.map((r, k) => `${x(k)},${y(r.with)}`).join(" L"), class: "line-with" }, svg);
    [0, rows.length - 1].forEach((k) => { const tx = el("text", { x: x(k), y: H - 6, "text-anchor": k ? (rtl ? "start" : "end") : (rtl ? "end" : "start") }, ax); tx.textContent = dfmt(rows[k].week); });
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, class: "hit" }, svg);
    hit.addEventListener("mousemove", (ev) => {
      const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * (W / r.width);
      let k = Math.round(rtl ? (W - m.r - px) / (W - m.l - m.r) * (rows.length - 1) : (px - m.l) / (W - m.l - m.r) * (rows.length - 1));
      k = Math.max(0, Math.min(rows.length - 1, k));
      cross.setAttribute("x1", x(k)); cross.setAttribute("x2", x(k)); cross.setAttribute("visibility", "visible");
      showTip(`<b>${dfmt(rows[k].week, true)}</b><br><span class="k">${esc(t.without)}</span> ${aed(rows[k].without)}<br><span class="k">${esc(t.with)}</span> ${aed(rows[k].with)}`, ev.clientX, ev.clientY);
    });
    hit.addEventListener("mouseleave", () => { hideTip(); cross.setAttribute("visibility", "hidden"); });
    box.appendChild(svg);
    const leg = document.createElement("div");
    leg.className = "legend";
    leg.innerHTML = `<span><i style="background:var(--madder)"></i>${esc(t.without)}</span><span><i style="background:var(--teal)"></i>${esc(t.with)}</span>`;
    box.appendChild(leg);
  }

  function pageHow() {
    const t = T();
    main.innerHTML = `<div class="wrap"><article class="prose"><h1 class="page" style="margin-top:36px">${esc(t.how_title)}</h1>${t.how_html()}</article></div>`;
  }

  // ---------------------------------------------------------------- router
  const routes = [
    [/^#?\/?$/, pageHome, "#/"], [/^#\/today$/, pageToday, "#/today"], [/^#\/businesses$/, pageBusinesses, "#/businesses"],
    [/^#\/b\/(S\d{4})$/, pageBusiness, "#/businesses"], [/^#\/network$/, pageNetwork, "#/network"], [/^#\/proof$/, pageProof, "#/proof"],
    [/^#\/how$/, pageHow, "#/how"],
  ];
  let seq = 0;
  async function route() {
    hideTip();
    const h = location.hash || "#/";
    const r = routes.find(([re]) => re.test(h)) || routes[0];
    const m = h.match(r[0]);
    document.querySelectorAll(".nav a, .mobile-nav a").forEach((a) => {
      if (a.getAttribute("href") === r[2]) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    $("#mobileNav").hidden = true;
    $("#menuBtn").setAttribute("aria-expanded", "false");
    const my = ++seq;
    try {
      await r[1](m && m[1]);
      if (my === seq) window.scrollTo(0, 0);
    } catch (e) {
      if (my === seq && e.message !== "rate") main.innerHTML = `<div class="wrap"><p class="empty">${esc(T().err)}</p></div>`;
    }
    if (my === seq) main.focus({ preventScroll: true });
  }
  window.addEventListener("hashchange", route);
  applyLang();
  route();
})();
