// Reads analysis.json (built by scripts/process_outliers.py from Neo4j or the parsed resume).
// Sliders re-sift outliers client-side: ATS score >= min, 1..max missing skills, none critical.
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const chip = (t, c) => `<span class="chip ${c}">${esc(t)}</span>`;
let data = null;

function classify(j, min, maxm) {
  const critical = j.missing.some(m => m.critical);
  if (!j.missing.length) return ["Strict match", true];
  if (j.ats_score >= min && j.missing.length <= maxm && !critical) return ["Outlier", true];
  return [critical ? "Critical gap" : "Below threshold", false];
}

function render() {
  const min = +$("ratio").value, maxm = +$("maxm").value;
  $("rv").textContent = min; $("mv").textContent = maxm;
  const q = $("q").value.toLowerCase(), co = $("company").value, all = $("all").checked;
  const rows = data.jobs.map(j => ({j, cls: classify(j, min, maxm)}));
  $("sOut").textContent = rows.filter(r => r.cls[0] === "Outlier").length;
  $("sBest").textContent = Math.max(...data.jobs.map(j => j.ats_score)).toFixed(0);
  const shown = rows.filter(({j, cls}) => (cls[1] || all) && (!co || j.company === co) &&
    `${j.title} ${j.company}`.toLowerCase().includes(q)).sort((a, b) => b.j.ats_score - a.j.ats_score);
  $("jobs").innerHTML = shown.length ? shown.map(({j, cls}) => `<article class="card">
    <span class="tag">${cls[0]} · ${esc(j.location || "n/a")}</span>
    <h3>${esc(j.title)}</h3><div class="co">${esc(j.company)}</div>
    <div>ATS score <b>${j.ats_score}</b>/100</div><div class="bar"><i style="width:${j.ats_score}%"></i></div>
    <div class="chips">${j.matched.map(m => chip(m.skill, m.weight < 1 ? "soft" : "ok")).join("")}${j.missing.map(m => chip("missing: " + m.skill, m.critical ? "bad" : "warn")).join("")}</div>
  </article>`).join("") : `<p class="empty">No jobs match. Lower the minimum ATS score or raise max missing.</p>`;
}

function renderTree() {
  const groups = {};
  data.skills.forEach(s => (groups[s.category] ||= []).push(s));
  $("tree").innerHTML = Object.entries(groups).map(([cat, list]) =>
    `<details><summary>${esc(cat)} (${list.length})</summary><div class="chips">${list.map(s =>
      chip(s.name + (s.evidence ? ` ·${s.evidence}` : ""), s.source === "text" || s.source === "implied" ? "soft" : "")).join("")}</div></details>`).join("");
}

async function init() {
  try {
    data = await fetch("analysis.json").then(r => { if (!r.ok) throw 0; return r.json(); });
    $("who").textContent = `${data.candidate} · scored via ${data.source} · ${data.generated.slice(0, 10)}`;
    $("sSkills").textContent = data.skills.length; $("sCreds").textContent = data.credentials.length;
    $("ratio").value = data.thresholds.min_score; $("maxm").value = data.thresholds.max_missing;
    [...new Set(data.jobs.map(j => j.company))].sort().forEach(c => $("company").add(new Option(c, c)));
    ["q", "company", "ratio", "maxm", "all"].forEach(id => $(id).addEventListener("input", render));
    renderTree(); render();
  } catch (e) {
    $("who").textContent = "Could not load analysis.json. Run scripts/process_outliers.py, serve the repo root (python -m http.server) and open /web/.";
  }
}
init();
