/* Sila UI text in English and Arabic. Sentences that contain live numbers are functions. */
(function () {
  const EN = {
    skip: "Skip to content", menu: "Menu", loading: "Loading the network…",
    nav_today: "Today", nav_businesses: "Businesses", nav_network: "Network", nav_proof: "Proof", nav_how: "How it works",
    foot_data: "All businesses, people and transactions here are synthetic. No real company or bank data is used.",
    foot_by: "Built by Ayesha Lubna for the du × Ignyte SME Resilience & Innovation Challenge.",
    foot_code: "Source code on GitHub",
    lang_other: "عربي",
    status: { safe: "Safe", watch: "Watch", at_risk: "At risk", short: "Short today" },
    kind: { early_payment: "Early payment", grace: "Grace period", chain: "Chain payment" },
    item: { payroll: "WPS payroll", rent_cheque: "Rent cheque", vat: "VAT return", utilities: "Utilities", owner_drawings: "Owner drawings", supplier: "Supplier invoice", receipt: "Customer payment" },
    hero_title: "Cash runs short. The network doesn’t have to.",
    hero_lede: "Sila sees a small business’s cash gap weeks before it happens, then closes it with money the network already has: a customer pays an invoice early, or a supplier waits. No loans, no interest, and nothing moves unless both owners agree.",
    hero_live: (b, date, helper, amt) => `<b>${b}</b> is likely to run short on <span class="when">${date}</span>. <b>${helper}</b> owes it ${amt} and has the spare cash to pay early. Sila has asked both owners.`,
    cta_today: (n) => `See today’s ${n} suggestions`, cta_how: "How Sila works",
    legend_safe: "Safe", legend_watch: "Watch", legend_risk: "At risk", legend_short: "Short today", legend_flow: "Suggested cash move",
    today_line: (o) => `On ${o.date}, <strong class="r">${o.atRisk} of ${o.total}</strong> businesses are heading for a cash gap within four weeks, ${o.gap} in total. Sila found <strong class="g">${o.cover}</strong> inside the network to protect <strong>${o.helped}</strong> of them, from partners that stay safe after helping.`,
    steps_title: "Three steps, every morning",
    s1_t: "Predict", s1_p: "A forecast of each business’s balance for the next 28 days, from its bank history, its customers’ payment habits, seasonality, Ramadan and fixed bills like payroll and post-dated rent cheques.",
    s2_t: "Find", s2_p: "For a business heading for a gap, Sila looks for open invoices with partners who have spare cash: a customer who can pay early, or a supplier who can wait.",
    s3_t: "Agree", s3_p: "Both owners see the same suggestion, the cost and the safety check. Only when both agree does the payment date change. Every decision is recorded.",
    proof_title: "Tested on six months it had never seen",
    proof_p: (r) => `Run every morning from April to September 2026: ${pct(r.episodes_prevented_share)} of cash shortfalls never happened, ${pct(r.episode_days_avoided_share)} of the days short were avoided, and not one helper was pushed into trouble.`,
    proof_link: "See the full evidence",
    chart_weekly: "Business-days short each week", without: "Without Sila", with: "With Sila",
    // today page
    today_title: "Today’s suggestions",
    today_lede: (n, m, d) => `${n} businesses are heading for a cash gap. Sila has ${m} suggestions to prevent it, each checked against both sides’ forecasts on ${d}. You can act as either owner below; your choices only change your own copy of the demo.`,
    plan_short_on: (d) => `First short day: ${d}`,
    risk_caption: "Chance of running out of cash in the next four weeks, now and if every suggestion below is agreed",
    gap_caption: (a, b) => `Cash gap ${a} → ${b}`,
    move_early: (m, leg) => `<b>${m.helper}</b> pays invoice ${leg.invoice} (${leg.amount}) on <b>${leg.to}</b> instead of around ${leg.from}.`,
    move_grace: (m, leg) => `<b>${m.helper}</b> agrees to receive invoice ${leg.invoice} (${leg.amount}) on <b>${leg.to}</b> instead of around ${leg.from}, at no charge.`,
    move_chain: (m, l1, l2) => `<b>${l1.payer}</b> pays <b>${l2.payer}</b> early (${l1.amount}), so ${l2.payer} can pay this business early too (${l2.amount}).`,
    more_invoices: (n) => `+ ${n} more invoice${n > 1 ? "s" : ""} between the same two businesses`,
    f_amount: "Cash moved", f_fee: "Discount paid", f_loan: "Same cover as a loan", f_buffer: "Helper still holds",
    days_cover: (d) => `${d} days of its own bills`, free: "Free",
    agrees: (n) => `${n} agrees`, declines: "Decline", waiting_for: (n) => `Waiting for ${n}`,
    agreed: "Both owners agreed. The new payment date is fixed.", declined: "Declined. Nothing changes.",
    impact: (b, a, h) => `Re-forecast: chance of running short now ${a} (was ${b}). The helper stays at ${h}.`,
    advice_title: "What the network can’t cover yet",
    advice_p: "For these businesses Sila gives the early warning and recommends talking to the bank now, weeks before the gap, while there is still time to arrange Sharia-compliant working capital.",
    adv_reason: { "no open invoices with network partners": "No open invoices with partners in the network.", "network partners do not have enough spare cash": "Its network partners don’t have enough spare cash right now.", "the gap is larger than the network can safely cover": "The gap is bigger than partners can safely cover." },
    adv_line: (d, g) => `Likely short from ${d}; about ${g} still needed.`,
    reset: "Reset my choices", reset_done: "Your choices were cleared.",
    // businesses
    biz_title: "Businesses", biz_lede: (n) => `${n} small businesses across the UAE trade with each other in this network. Sorted by risk.`,
    search_ph: "Search by name, owner or ID", all_sectors: "All sectors", all_emirates: "All emirates", all: "All",
    th_business: "Business", th_sector: "Sector", th_emirate: "Emirate", th_cash: "Cash today", th_outlook: "Next 4 weeks", th_risk: "Chance of running short", th_status: "Status",
    page_of: (a, b, n) => `${a}–${b} of ${n}`, prev: "Previous", next: "Next", none: "No businesses match these filters.",
    // business
    back_all: "All businesses",
    tag_staff: (n) => `${n} staff`, tag_rev: (v) => `${v} a month`, tag_partners: (n) => `${n} network partners`,
    sum_safe: (bal, low) => `Cash today <b>${bal}</b>. Over the next four weeks the expected low point is <b>${low}</b>, and the forecast stays above zero.`,
    sum_risk: (bal, p, d) => `Cash today <b>${bal}</b>. There is a <b>${p}</b> chance it runs out, first around <b>${d}</b>.`,
    sum_short: (bal, p) => `The account is already below zero (<b>${bal}</b>). Chance it is still short at some point in the next four weeks: <b>${p}</b>.`,
    chart_title: "Balance: last 90 days and the next 28", chart_hist: "Actual balance", chart_med: "Expected", chart_band: "8 in 10 outcomes", chart_zero: "Zero",
    today_lbl: "Today",
    why_title: "Why", why_outflow: (label, amt, d) => `${label} of ${amt} due ${d}.`,
    why_late: (who, amt, due, exp) => `${amt} from ${who} was due ${due}, but is expected around ${exp}.`,
    why_sales: (p) => p < 0 ? `Sales over the next four weeks expected ${pct(-p)} lower than the last four.` : `Sales over the next four weeks expected ${pct(p)} higher than the last four.`,
    why_none: "No single bill stands out: the balance is simply thin for the bills coming up.",
    why_safe: "Expected payments arrive before the big bills, so the balance stays positive.",
    moves_title: "Suggestions involving this business", moves_none: "No suggestions involve this business today.",
    money_title: "Money expected in and out, next 28 days", money_none: "Nothing scheduled.",
    exp_range: (a, b) => `likely between ${a} and ${b}`, why_date: "Why this date?", agreed_date: "Agreed through Sila",
    explain_head: (base, adj) => `Starting point: due date plus this customer’s usual delay = about ${base} from today. The model adjusts by ${adj} days:`,
    whatif_title: "What if…", wi_sales: "Sales change", wi_late: "Customers pay later by", wi_exp: "One-off extra payment", wi_day: "Paid on day",
    wi_result: (a, b) => `Chance of running short: <b>${a}</b> → <b>${b}</b>`, wi_hint: "Move a slider to see the forecast change.",
    partners_title: "Trading partners in the network", supplier: "Supplier", customer: "Customer",
    history_title: "In the six-month test", history_p: (a, b, c, d) => `Sila helped this business ${a} times (${b}) and it helped others ${c} times (${d}).`,
    days: (n) => (n === 1 ? "1 day" : `${n} days`),
    // network
    net_title: "The network", net_lede: "Each dot is a business, grouped by sector and sized by revenue. Faint threads are regular trade between them. Animated threads are today’s suggested cash moves.",
    // proof
    pf_title: "The evidence", pf_lede: "Models were trained on data up to 31 March 2026. Everything here is measured on April to September 2026, which they never saw. All data is synthetic.",
    pf_f1: "of cash shortfalls never happened", pf_f2: "of days short avoided", pf_f3: "helpers pushed into trouble", pf_f4: "cheaper than the same cover as a loan",
    pf_weekly: "Business-days below zero each week, Apr–Sep 2026",
    pf_alerts: "Warnings: will this business run out of cash within four weeks?",
    pf_alerts_p: (a) => `Sila warned before ${pct(a.warned_share)} of the shortfalls, ${pct(a.warned_7d_share)} at least a week ahead, with a median of ${a.median_lead_days} days’ notice.`,
    th_measure: "Measure", th_sila: "Sila", th_rule: "Simple rule",
    m_precision: "Warnings that were right", m_recall: "Shortfalls caught", m_auc: "Ranking quality (ROC-AUC)",
    rule_note: "The simple rule warns the businesses with the fewest days of cash left, with the same number of warnings.",
    pf_parts: "The parts of the forecast",
    m_timing: "When will an invoice be paid? (average error, days)", m_sales: "Daily sales four weeks ahead (error)", m_cov: "Real balance inside the 8-in-10 range",
    rule_timing: "Due date + usual delay", rule_sales: "Same weekday, last 4 weeks", target80: "Target 80%",
    pf_stories: "Shortfalls that didn’t happen",
    story_p: (s) => `Would have run short on ${s.date} for ${s.days} days, down to ${s.depth}. Sila warned ${s.lead} days ahead and arranged ${s.n} move${s.n > 1 ? "s" : ""}.`,
    pf_limits: "What Sila can’t fix",
    pf_limits_p: "Businesses with no trading partners inside the network, and gaps bigger than partners can safely cover. In the test these were mostly contractors paid by large outside clients, and salons that buy outside the network. For them Sila still gives the warning, a median of three weeks ahead, so the owner can talk to the bank in time.",
    pf_more: "Full method and numbers are in the repository’s evaluation report.",
    // how
    how_title: "How Sila works",
    how_html: () => `
<p class="lede">Most small businesses that run out of cash are not losing money. They are waiting to be paid. Sila uses that.</p>
<h2>The problem</h2>
<p>In the UAE, customers often pay 30, 60 or 90 days after the invoice, and later still in summer and Ramadan. Meanwhile payroll goes out through WPS on a fixed day, rent is paid by post-dated cheques that must not bounce, and VAT is due every quarter. A profitable business can be short for a few weeks, then fine again.</p>
<p>Inside any trading network, at the same moment, other businesses are holding more cash than they need, often money they owe to the very business that is short.</p>
<h2>What Sila does</h2>
<p>Every morning Sila forecasts each member’s balance for the next 28 days, as a range rather than a single number, and estimates the chance it goes below zero. When that chance is high, it looks at the invoices that already exist between that business and its partners and suggests one of two changes:</p>
<div class="rules">
  <div class="rule"><h3>Early payment</h3><p>A customer with spare cash pays an invoice it already owes before the due date. The business receiving the money gives a small early-payment discount of 0.6% per 30 days.</p></div>
  <div class="rule"><h3>Grace period</h3><p>A supplier with spare cash agrees to be paid later for an invoice it is already owed. There is no fee for waiting.</p></div>
</div>
<p>When the customer who owes money is itself short of spare cash, Sila can chain two early payments through it. No new money is created and no new debt: only the date of an existing payment changes.</p>
<h2>Safety rules</h2>
<div class="rules">
  <div class="rule"><h3>Helpers stay safe</h3><p>After helping, a partner must still hold at least 10 days of its own bills, even in its pessimistic (1 in 10) forecast.</p></div>
  <div class="rule"><h3>Never more than 60%</h3><p>One suggestion can use at most 60% of a helper’s spare cash.</p></div>
  <div class="rule"><h3>Re-checked before it is shown</h3><p>Every suggestion is re-forecast with the change in place. If any helper would become at risk, it is dropped.</p></div>
  <div class="rule"><h3>Both owners decide</h3><p>Nothing moves without both owners agreeing, and every decision is recorded with a timestamp.</p></div>
</div>
<h2>Why it is Sharia-friendly by design</h2>
<p>Sila never lends and never charges for time. An early-payment discount on an existing debt is a practice that many scholars permit (known as <span lang="ar" class="ar">ضع وتعجل</span>, “reduce and hasten”), and a grace period without charge follows the principle of giving time to someone in difficulty (Qur’an 2:280). A real deployment would still be reviewed and approved by a Sharia supervisory board.</p>
<h2>What it needs to run for real</h2>
<ul>
<li>Bank transaction feeds, with the owner’s consent, through the UAE’s Open Finance framework.</li>
<li>Invoice data, for example from e-invoicing, so payment dates can be changed in an agreed and auditable way.</li>
<li>A bank or payments partner to run the network, holding no balance of its own.</li>
</ul>
<h2>The models</h2>
<p>Payment timing and daily sales are predicted with LightGBM quantile models; known bills such as payroll, rent cheques and VAT come from the categorised bank history. A Monte Carlo simulation combines them into 120 possible paths per business, and the range is calibrated so that 8 in 10 real outcomes fall inside it.</p>`,
    toast_agreed: "Agreed by both owners. Forecast updated.", toast_saved: "Saved.", err: "Something went wrong. Try again in a moment.",
    rate: "Too many requests. Wait a minute and try again.",
  };

  const AR = {
    skip: "انتقل إلى المحتوى", menu: "القائمة", loading: "جارٍ تحميل الشبكة…",
    nav_today: "اليوم", nav_businesses: "الشركات", nav_network: "الشبكة", nav_proof: "الدليل", nav_how: "كيف يعمل",
    foot_data: "جميع الشركات والأشخاص والمعاملات هنا افتراضية. لا تُستخدم أي بيانات حقيقية لشركات أو بنوك.",
    foot_by: "من إعداد عائشة لبنى لتحدي du × Ignyte لمرونة الشركات الصغيرة والمتوسطة والابتكار.",
    foot_code: "الشيفرة المصدرية على GitHub",
    lang_other: "English",
    status: { safe: "آمنة", watch: "تحت المراقبة", at_risk: "معرّضة للخطر", short: "رصيدها سالب اليوم" },
    kind: { early_payment: "دفع مبكر", grace: "مهلة سداد", chain: "دفع متسلسل" },
    item: { payroll: "رواتب نظام حماية الأجور", rent_cheque: "شيك إيجار", vat: "إقرار ضريبة القيمة المضافة", utilities: "فواتير الخدمات", owner_drawings: "مسحوبات المالك", supplier: "فاتورة مورّد", receipt: "دفعة من عميل" },
    hero_title: "قد ينفد النقد لدى شركة، لكن الشبكة لا تنفد.",
    hero_lede: "ترى «صلة» العجز النقدي لدى الشركة الصغيرة قبل حدوثه بأسابيع، ثم تسدّه بمال موجود أصلًا في الشبكة: عميل يدفع فاتورته مبكرًا، أو مورّد ينتظر. لا قروض، ولا فوائد، ولا يتحرك شيء إلا بموافقة المالكين معًا.",
    hero_live: (b, date, helper, amt) => `من المرجّح أن ينفد النقد لدى <b>${b}</b> في <span class="when">${date}</span>. وشركة <b>${helper}</b> مدينة لها بمبلغ ${amt} ولديها فائض يكفي للدفع مبكرًا. وقد أرسلت «صلة» الاقتراح إلى المالكين.`,
    cta_today: (n) => `راجع اقتراحات اليوم (${n})`, cta_how: "كيف تعمل «صلة»",
    legend_safe: "آمنة", legend_watch: "تحت المراقبة", legend_risk: "معرّضة للخطر", legend_short: "رصيد سالب اليوم", legend_flow: "نقل نقد مقترح",
    today_line: (o) => `في ${o.date}، تتجه <strong class="r">${o.atRisk} من ${o.total}</strong> شركة نحو عجز نقدي خلال أربعة أسابيع، بإجمالي ${o.gap}. ووجدت «صلة» <strong class="g">${o.cover}</strong> داخل الشبكة لحماية <strong>${o.helped}</strong> منها، من شركاء يبقون في أمان بعد المساعدة.`,
    steps_title: "ثلاث خطوات كل صباح",
    s1_t: "التوقّع", s1_p: "توقع لرصيد كل شركة خلال الأيام الثمانية والعشرين القادمة، من سجلها البنكي وعادات عملائها في السداد والمواسم ورمضان والالتزامات الثابتة مثل الرواتب وشيكات الإيجار المؤجلة.",
    s2_t: "البحث", s2_p: "للشركة المتجهة نحو عجز، تبحث «صلة» عن فواتير قائمة مع شركاء لديهم فائض: عميل يستطيع الدفع مبكرًا، أو مورّد يستطيع الانتظار.",
    s3_t: "الموافقة", s3_p: "يرى المالكان الاقتراح نفسه والتكلفة وفحص الأمان. ولا يتغير موعد الدفع إلا بموافقتهما معًا، ويُسجَّل كل قرار.",
    proof_title: "اختُبرت على ستة أشهر لم ترها من قبل",
    proof_p: (r) => `عند تشغيلها كل صباح من أبريل إلى سبتمبر 2026: لم يحدث ${pct(r.episodes_prevented_share)} من حالات العجز النقدي، وتم تجنب ${pct(r.episode_days_avoided_share)} من أيام العجز، ولم يتضرر أي شريك ساعد غيره.`,
    proof_link: "اطّلع على الدليل الكامل",
    chart_weekly: "أيام العجز لكل الشركات أسبوعيًا", without: "بدون «صلة»", with: "مع «صلة»",
    today_title: "اقتراحات اليوم",
    today_lede: (n, m, d) => `تتجه ${n} شركات نحو عجز نقدي. ولدى «صلة» ${m} اقتراحًا لمنعه، وكلٌّ منها مُتحقَّق منه على توقعات الطرفين في ${d}. يمكنك التصرف بصفة أيٍّ من المالكين أدناه، وقراراتك لا تغيّر إلا نسختك من العرض.`,
    plan_short_on: (d) => `أول يوم عجز: ${d}`,
    risk_caption: "احتمال نفاد النقد خلال الأسابيع الأربعة القادمة، الآن وفي حال الموافقة على كل الاقتراحات أدناه",
    gap_caption: (a, b) => `العجز النقدي ${a} ← ${b}`,
    move_early: (m, leg) => `تدفع <b>${m.helper}</b> الفاتورة ${leg.invoice} (${leg.amount}) في <b>${leg.to}</b> بدلًا من نحو ${leg.from}.`,
    move_grace: (m, leg) => `توافق <b>${m.helper}</b> على استلام الفاتورة ${leg.invoice} (${leg.amount}) في <b>${leg.to}</b> بدلًا من نحو ${leg.from}، دون أي رسوم.`,
    move_chain: (m, l1, l2) => `تدفع <b>${l1.payer}</b> إلى <b>${l2.payer}</b> مبكرًا (${l1.amount})، لتتمكن ${l2.payer} بدورها من الدفع لهذه الشركة مبكرًا (${l2.amount}).`,
    more_invoices: (n) => `+ ${n} فواتير أخرى بين الشركتين نفسيهما`,
    f_amount: "النقد المنقول", f_fee: "الخصم المدفوع", f_loan: "التكلفة نفسها كقرض", f_buffer: "يبقى لدى الشريك",
    days_cover: (d) => `${d} يومًا من التزاماته`, free: "مجانًا",
    agrees: (n) => `توافق ${n}`, declines: "رفض", waiting_for: (n) => `بانتظار ${n}`,
    agreed: "وافق المالكان. تم تثبيت موعد الدفع الجديد.", declined: "تم الرفض. لن يتغير شيء.",
    impact: (b, a, h) => `التوقع الجديد: احتمال العجز الآن ${a} (كان ${b}). ويبقى الشريك عند ${h}.`,
    advice_title: "ما لا تستطيع الشبكة تغطيته بعد",
    advice_p: "لهذه الشركات تقدّم «صلة» الإنذار المبكر وتنصح بالتحدث إلى البنك الآن، قبل العجز بأسابيع، ما دام هناك وقت لترتيب تمويل رأس مال عامل متوافق مع الشريعة.",
    adv_reason: { "no open invoices with network partners": "لا توجد فواتير قائمة مع شركاء داخل الشبكة.", "network partners do not have enough spare cash": "لا يملك شركاؤها في الشبكة فائضًا كافيًا حاليًا.", "the gap is larger than the network can safely cover": "العجز أكبر مما يستطيع الشركاء تغطيته بأمان." },
    adv_line: (d, g) => `عجز مرجّح ابتداءً من ${d}؛ ولا يزال مطلوبًا نحو ${g}.`,
    reset: "إعادة ضبط قراراتي", reset_done: "تم مسح قراراتك.",
    biz_title: "الشركات", biz_lede: (n) => `${n} شركة صغيرة في أنحاء الإمارات تتعامل فيما بينها ضمن هذه الشبكة. مرتبة حسب الخطر.`,
    search_ph: "ابحث بالاسم أو المالك أو الرقم", all_sectors: "كل القطاعات", all_emirates: "كل الإمارات", all: "الكل",
    th_business: "الشركة", th_sector: "القطاع", th_emirate: "الإمارة", th_cash: "النقد اليوم", th_outlook: "الأسابيع الأربعة القادمة", th_risk: "احتمال العجز", th_status: "الحالة",
    page_of: (a, b, n) => `${a}–${b} من ${n}`, prev: "السابق", next: "التالي", none: "لا توجد شركات تطابق هذه المرشحات.",
    back_all: "كل الشركات",
    tag_staff: (n) => `${n} موظفين`, tag_rev: (v) => `${v} شهريًا`, tag_partners: (n) => `${n} شركاء في الشبكة`,
    sum_safe: (bal, low) => `النقد اليوم <b>${bal}</b>. أدنى رصيد متوقع خلال الأسابيع الأربعة القادمة <b>${low}</b>، ويبقى التوقع فوق الصفر.`,
    sum_risk: (bal, p, d) => `النقد اليوم <b>${bal}</b>. هناك احتمال <b>${p}</b> أن ينفد، أولًا في حدود <b>${d}</b>.`,
    sum_short: (bal, p) => `الحساب دون الصفر بالفعل (<b>${bal}</b>). احتمال بقائه في عجز في وقت ما خلال الأسابيع الأربعة القادمة: <b>${p}</b>.`,
    chart_title: "الرصيد: آخر 90 يومًا و28 يومًا قادمة", chart_hist: "الرصيد الفعلي", chart_med: "المتوقع", chart_band: "8 من كل 10 نتائج", chart_zero: "صفر",
    today_lbl: "اليوم",
    why_title: "السبب", why_outflow: (label, amt, d) => `${label} بقيمة ${amt} مستحقة في ${d}.`,
    why_late: (who, amt, due, exp) => `مبلغ ${amt} من ${who} كان مستحقًا في ${due}، لكن يُتوقع وصوله في حدود ${exp}.`,
    why_sales: (p) => p < 0 ? `يُتوقع أن تنخفض المبيعات في الأسابيع الأربعة القادمة بنسبة ${pct(-p)} عن الأربعة الماضية.` : `يُتوقع أن ترتفع المبيعات في الأسابيع الأربعة القادمة بنسبة ${pct(p)} عن الأربعة الماضية.`,
    why_none: "لا توجد فاتورة واحدة بارزة: الرصيد ببساطة ضعيف أمام الالتزامات القادمة.",
    why_safe: "الدفعات المتوقعة تصل قبل الالتزامات الكبيرة، فيبقى الرصيد موجبًا.",
    moves_title: "اقتراحات تخص هذه الشركة", moves_none: "لا توجد اقتراحات تخص هذه الشركة اليوم.",
    money_title: "الأموال المتوقعة دخولًا وخروجًا خلال 28 يومًا", money_none: "لا شيء مجدول.",
    exp_range: (a, b) => `على الأرجح بين ${a} و${b}`, why_date: "لماذا هذا الموعد؟", agreed_date: "متفق عليه عبر «صلة»",
    explain_head: (base, adj) => `نقطة البداية: تاريخ الاستحقاق مع التأخير المعتاد لهذا العميل = نحو ${base} من اليوم. ويعدّل النموذج ذلك بمقدار ${adj} يومًا:`,
    whatif_title: "ماذا لو…", wi_sales: "تغير المبيعات", wi_late: "تأخر العملاء في السداد بمقدار", wi_exp: "دفعة إضافية لمرة واحدة", wi_day: "تُدفع في اليوم",
    wi_result: (a, b) => `احتمال العجز: <b>${a}</b> ← <b>${b}</b>`, wi_hint: "حرّك أي مؤشر لترى تغيّر التوقع.",
    partners_title: "الشركاء التجاريون في الشبكة", supplier: "مورّد", customer: "عميل",
    history_title: "خلال اختبار الأشهر الستة", history_p: (a, b, c, d) => `ساعدت «صلة» هذه الشركة ${a} مرات (${b})، وساعدت هي غيرها ${c} مرات (${d}).`,
    days: (n) => `${n} يومًا`,
    net_title: "الشبكة", net_lede: "كل نقطة شركة، مجمّعة حسب القطاع وبحجم يعكس إيراداتها. الخيوط الباهتة هي التعاملات التجارية المنتظمة بينها، والخيوط المتحركة هي عمليات نقل النقد المقترحة اليوم.",
    pf_title: "الدليل", pf_lede: "دُرّبت النماذج على بيانات حتى 31 مارس 2026. وكل ما هنا مقيس على الفترة من أبريل إلى سبتمبر 2026 التي لم ترها النماذج قط. جميع البيانات افتراضية.",
    pf_f1: "من حالات العجز النقدي لم تحدث", pf_f2: "من أيام العجز تم تجنبها", pf_f3: "شركاء تضرروا بسبب المساعدة", pf_f4: "أرخص من التغطية نفسها بقرض",
    pf_weekly: "أيام العجز لكل الشركات أسبوعيًا، أبريل – سبتمبر 2026",
    pf_alerts: "الإنذارات: هل سينفد النقد لدى هذه الشركة خلال أربعة أسابيع؟",
    pf_alerts_p: (a) => `أنذرت «صلة» قبل ${pct(a.warned_share)} من حالات العجز، منها ${pct(a.warned_7d_share)} قبل أسبوع على الأقل، وبمتوسط إنذار مسبق ${a.median_lead_days} يومًا.`,
    th_measure: "المقياس", th_sila: "«صلة»", th_rule: "قاعدة بسيطة",
    m_precision: "إنذارات صحيحة", m_recall: "حالات عجز تم رصدها", m_auc: "جودة الترتيب (ROC-AUC)",
    rule_note: "القاعدة البسيطة تنذر الشركات التي لديها أقل عدد من أيام النقد المتبقية، بالعدد نفسه من الإنذارات.",
    pf_parts: "مكوّنات التوقع",
    m_timing: "متى ستُدفع الفاتورة؟ (متوسط الخطأ بالأيام)", m_sales: "المبيعات اليومية بعد أربعة أسابيع (الخطأ)", m_cov: "الرصيد الفعلي داخل نطاق 8 من 10",
    rule_timing: "تاريخ الاستحقاق + التأخير المعتاد", rule_sales: "اليوم نفسه من الأسابيع الأربعة الماضية", target80: "الهدف 80%",
    pf_stories: "حالات عجز لم تحدث",
    story_p: (s) => `كانت ستعاني عجزًا في ${s.date} لمدة ${s.days} يومًا وبعمق ${s.depth}. أنذرت «صلة» قبل ${s.lead} يومًا ورتبت ${s.n} عملية.`,
    pf_limits: "ما لا تستطيع «صلة» إصلاحه",
    pf_limits_p: "الشركات التي ليس لها شركاء تجاريون داخل الشبكة، وحالات العجز الأكبر مما يستطيع الشركاء تغطيته بأمان. في الاختبار كانت في الغالب شركات مقاولات يدفع لها عملاء كبار من خارج الشبكة، وصالونات تشتري من خارجها. ومع ذلك تمنحها «صلة» الإنذار، بمتوسط ثلاثة أسابيع مسبقًا، ليتحدث المالك إلى البنك في الوقت المناسب.",
    pf_more: "المنهجية والأرقام الكاملة في تقرير التقييم داخل المستودع.",
    how_title: "كيف تعمل «صلة»",
    how_html: () => `
<p class="lede">معظم الشركات الصغيرة التي ينفد لديها النقد لا تخسر المال، بل تنتظر أن يُدفع لها. و«صلة» تستفيد من ذلك.</p>
<h2>المشكلة</h2>
<p>في الإمارات كثيرًا ما يدفع العملاء بعد 30 أو 60 أو 90 يومًا من الفاتورة، ويتأخرون أكثر في الصيف ورمضان. وفي المقابل تُصرف الرواتب عبر نظام حماية الأجور في يوم ثابت، ويُدفع الإيجار بشيكات مؤجلة لا يجوز أن ترتد، وتستحق ضريبة القيمة المضافة كل ربع سنة. فقد تعاني شركة رابحة من عجز لبضعة أسابيع ثم تعود إلى وضعها الطبيعي.</p>
<p>وفي أي شبكة تجارية، وفي اللحظة نفسها، تحتفظ شركات أخرى بنقد يفوق حاجتها، وكثيرًا ما يكون مالًا تدين به للشركة نفسها التي تعاني العجز.</p>
<h2>ما تفعله «صلة»</h2>
<p>كل صباح تتوقع «صلة» رصيد كل عضو للأيام الثمانية والعشرين القادمة، على شكل نطاق لا رقم واحد، وتقدّر احتمال نزوله دون الصفر. وعندما يكون الاحتمال مرتفعًا، تنظر في الفواتير القائمة بين تلك الشركة وشركائها وتقترح أحد تغييرين:</p>
<div class="rules">
  <div class="rule"><h3>الدفع المبكر</h3><p>يدفع عميل لديه فائض فاتورة مستحقة عليه قبل موعدها، وتمنحه الشركة المستفيدة خصمًا صغيرًا للدفع المبكر قدره 0.6% عن كل 30 يومًا.</p></div>
  <div class="rule"><h3>مهلة السداد</h3><p>يوافق مورّد لديه فائض على تأجيل استلام فاتورة مستحقة له، دون أي رسوم مقابل الانتظار.</p></div>
</div>
<p>وعندما يكون العميل المدين نفسه بلا فائض كافٍ، يمكن لـ«صلة» ربط دفعتين مبكرتين عبره. لا يُخلق مال جديد ولا دين جديد، بل يتغير موعد دفعة قائمة فقط.</p>
<h2>قواعد الأمان</h2>
<div class="rules">
  <div class="rule"><h3>الشريك يبقى في أمان</h3><p>بعد المساعدة، يجب أن يبقى لدى الشريك ما يغطي 10 أيام على الأقل من التزاماته، حتى في توقعه المتشائم (1 من 10).</p></div>
  <div class="rule"><h3>لا أكثر من 60%</h3><p>لا يستخدم الاقتراح الواحد أكثر من 60% من فائض الشريك.</p></div>
  <div class="rule"><h3>يُعاد التحقق قبل العرض</h3><p>يُعاد حساب التوقع لكل اقتراح مع تطبيق التغيير. وإذا أصبح أي شريك معرّضًا للخطر، يُستبعد الاقتراح.</p></div>
  <div class="rule"><h3>القرار للمالكين</h3><p>لا يتحرك شيء دون موافقة المالكين معًا، ويُسجَّل كل قرار مع وقته.</p></div>
</div>
<h2>لماذا هي متوافقة مع الشريعة بطبيعة تصميمها</h2>
<p>لا تُقرض «صلة» ولا تتقاضى مقابلًا للزمن. والخصم مقابل تعجيل سداد دين قائم أجازه كثير من العلماء (ويُعرف بـ«ضع وتعجّل»)، ومنح المهلة دون مقابل يقوم على مبدأ إنظار المعسر (البقرة: 280). ومع ذلك فإن أي تطبيق فعلي سيُعرض على هيئة رقابة شرعية لمراجعته واعتماده.</p>
<h2>ما تحتاجه للتشغيل الفعلي</h2>
<ul>
<li>بيانات المعاملات البنكية بموافقة المالك، عبر إطار التمويل المفتوح في دولة الإمارات.</li>
<li>بيانات الفواتير، مثلًا من الفوترة الإلكترونية، ليتم تغيير مواعيد الدفع بطريقة متفق عليها وقابلة للتدقيق.</li>
<li>شريك بنكي أو شريك مدفوعات لتشغيل الشبكة، دون أن يحتفظ برصيد خاص به.</li>
</ul>
<h2>النماذج</h2>
<p>يُتوقع توقيت السداد والمبيعات اليومية بنماذج LightGBM الكمية، وتؤخذ الالتزامات المعروفة مثل الرواتب وشيكات الإيجار وضريبة القيمة المضافة من السجل البنكي المصنّف. ثم تجمعها محاكاة مونت كارلو في 120 مسارًا محتملًا لكل شركة، ويُعايَر النطاق بحيث تقع 8 من كل 10 نتائج فعلية داخله.</p>`,
    toast_agreed: "وافق المالكان. تم تحديث التوقع.", toast_saved: "تم الحفظ.", err: "حدث خطأ. حاول مرة أخرى بعد قليل.",
    rate: "طلبات كثيرة. انتظر دقيقة ثم حاول مجددًا.",
  };

  function pct(x) { return `${Math.round((x || 0) * 100)}%`; }
  window.SILA_I18N = { en: EN, ar: AR, pct };
})();
