import { Film } from "./film.js";
import { SessionPlayer } from "./synth.js";
import { FaceReader, VoiceReader, speechRecognizer } from "./mood.js";
import { GestureReader, HAND_LINKS } from "./gestures.js";
import { Guide } from "./guide.js";
import { initAfter } from "./after.js";
import { STRINGS, RTL, LANGS, TITLES, needsMore, loadMore, t as tr } from "./i18n.js";
import { initUniverse } from "./universe.js";
import { createInstrument } from "./instrument.js";

const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
const API = "";
const CITY = { "San Jose": [37.3382, -121.8863], "New York City": [40.7128, -74.006], "Los Angeles": [34.0522, -118.2437], "Chicago": [41.8781, -87.6298] };
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const BANDS = [["delta", 0.5, 4, 2], ["theta", 4, 8, 6], ["alpha", 8, 12, 10], ["beta", 12, 30, 16], ["gamma", 30, 50, 40]];
const BAND_COLOR = { delta: "#7b86ff", theta: "#b483ff", alpha: "#3fd1c0", beta: "#e8b63e", gamma: "#ff6f91" };
const ACCENT = { focus: "#e3b23c", sleep: "#7c8cff", calm: "#3fd1c0", autism_calm: "#8fd68a", mood: "#ff9a6b", memory: "#d7a6ff", energy: "#ff5f8f", visual: "#6ad0ff" };
const wait = (ms) => new Promise(r => setTimeout(r, ms));
const state = { lang: "en", personas: [], protocols: null, health: null, slide: "human", result: null, goal: null, mood: null, override: null, face: null, voice: null, faceSince: 0,
  consent: { face: false, voice: false, hands: false }, tracks: [], memory: { liked: [], disliked: [] }, you: { name: "", age: 30, city: "", hearing: "full", favorites: [] }, members: [], source: null,
  src: "artists", scape: "ocean", sessions: [], art: null, lastMood: null, moodStreak: 0, snooze: 0, tour: { stops: [], i: -1, on: false, auto: false, audio: null } };
const L = () => state.lang;
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const load = (k, d) => { try { const v = JSON.parse(localStorage.getItem(k) || "null"); return v ?? d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
state.memory = load("reach.memory", state.memory); state.sessions = load("reach.sessions", []); state.members = load("reach.members", []);
{ const y = load("reach.you", null); if (y && Array.isArray(y.favorites)) state.you = { hearing: "full", ...y }; state.source = load("reach.source", null); }

// ------------------------------------------------------------------ i18n
function applyLang(lang) {
  state.lang = lang; document.documentElement.lang = lang; document.documentElement.dir = RTL.has(lang) ? "rtl" : "ltr";
  $$("[data-i18n]").forEach(el => { el.textContent = tr(lang, el.dataset.i18n); });
  $$("[data-i18n-ph]").forEach(el => { el.placeholder = tr(lang, el.dataset.i18nPh); });
  $$("[data-i18n-list]").forEach(el => { const v = tr(lang, el.dataset.i18nList); el.innerHTML = Array.isArray(v) ? v.map(x => `<li>${esc(x)}</li>`).join("") : ""; });
  $$(".lang button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lang === lang)));
  $$(".langsel").forEach(sel => { sel.value = lang; });
  save("reach.lang", lang);
  renderStatus(); drawDial(); renderMoodWords(); renderBands(); renderYou(); renderMembers(); renderInfoCards(); renderScapeKinds(); renderPatients(); if (state.result) renderResult(state.result, { quiet: true }); if (afterView) { afterView.relang(); afterView.scene.resize(); }
}
$$(".lang button").forEach(b => b.addEventListener("click", () => setLang(b.dataset.lang)));

// ------------------------------------------------------------------ film + deck
const film = new Film($("#film"));
const deck = $("#deck"), slides = $$(".slide"), rail = $("#rail");
slides.forEach((s) => { const b = document.createElement("button"); b.setAttribute("aria-label", s.dataset.slide); b.addEventListener("click", () => { stopAutopilot(); s.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" }); }); rail.appendChild(b); });
const touchfilm = $("#touchfilm"), touchvideo = $("#touchvideo");
let lastSlide = -1;
function onScroll() {
  const h = deck.clientHeight, y = deck.scrollTop, idx = Math.min(slides.length - 1, Math.max(0, Math.round(y / h)));
  const name = slides[idx].dataset.slide; film.setShot(name === "app" && document.body.classList.contains("platemode") ? "plate" : name, 0);
  if (idx !== lastSlide) {
    lastSlide = idx; state.slide = name; slides.forEach((s, i) => s.classList.toggle("active", i === idx));
    $$("button", rail).forEach((b, i) => b.setAttribute("aria-current", String(i === idx)));
    film.shotStart = performance.now(); const fl = $("#flash"); fl.classList.remove("go"); void fl.offsetWidth; if (!reduceMotion) fl.classList.add("go");
    touchfilm.classList.toggle("on", name === "touch"); if (name === "touch") { if (!touchvideo.poster) touchvideo.poster = touchvideo.dataset.poster; touchvideo.currentTime = 0; touchvideo.play().catch(() => {}); } else touchvideo.pause();
    chapterPhoto(name);
    if (name === "galaxy") touchvideo.preload = "auto";                                   // the next chapter's film, fetched one chapter ahead
    if (name === "earth" || name === "world") { const ov = $("#oraclevideo"); if (ov.preload !== "auto") ov.preload = "auto"; }
    if (name === "earth") { const c = cityCoords(); if (c) film.sets.earth.face(c[0], c[1]); }
    if (name === "world") renderTour(); else if (state.tour.on) stopTour();
    if (name !== "app" && document.body.classList.contains("platemode")) plateMode(false);
    if (afterView) { if (name === "app" && state.tab === "after") afterView.open(); else afterView.close(); }
    if (name === "app") { let seen = false; try { seen = sessionStorage.getItem("reach.ob") === "1"; } catch {} if (!profileReady() || !seen) openOnboard(); else if (!state.result && Date.now() - (state.starting || 0) > 3000) compose({ auto: true }); }
    $("#backdrop").classList.toggle("on", (name === "app" && !!state.art) || (name === "earth" && state.tour.on));
  }
}
function cityCoords() { const p = currentProfile(); return p.city_coords || CITY[p.city] || null; }
deck.addEventListener("scroll", onScroll, { passive: true });
function loop() {
  if (document.body.classList.contains("welcoming")) { requestAnimationFrame(loop); return; }   // hidden behind the start page: no need to draw it
  film.progress = Math.min(1, (performance.now() - (film.shotStart || 0)) / 9000);
  film.audioLevel += (Math.min(1, player.level() * 3) - film.audioLevel) * 0.2;
  film.sets.studio.spectrum = player.spectrum();
  film.render(); drawCamOverlay(); requestAnimationFrame(loop);
}
film.shotStart = performance.now(); requestAnimationFrame(loop);
let auto = null;
const APP_I = () => Math.max(0, slides.findIndex(x => x.dataset.slide === "app"));
function startAutopilot() { if (reduceMotion) return; let i = 0; $("#skip").hidden = false; const step = () => { i++; if (i > APP_I()) { stopAutopilot(); return; } slides[i].scrollIntoView({ behavior: "smooth" }); auto = setTimeout(step, slides[i].dataset.slide === "touch" ? 9000 : 7000); }; auto = setTimeout(step, 6500); }
function stopAutopilot() { if (auto) { clearTimeout(auto); auto = null; } $("#skip").hidden = true; }
["wheel", "touchstart", "keydown", "pointerdown"].forEach(ev => window.addEventListener(ev, (e) => { if (auto && !(e.target && e.target.closest && e.target.closest("#skip"))) stopAutopilot(); }, { passive: true }));
$("#skip").addEventListener("click", () => { stopAutopilot(); goSlide("app"); });
$("#intro-skip").addEventListener("click", () => { stopAutopilot(); goSlide("app"); });
function goSlide(name) { stopAutopilot(); const sl = slides.find(x => x.dataset.slide === name); if (sl) sl.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" }); }

// the story's chapters over real medical renders: a person listening, then the neurons that keep time
const CHAPTER_PHOTO = { human: "./assets/portrait_close.jpg", neurons: "./assets/neurons_wide.jpg" };
let chapterSide = 0;
function chapterPhoto(name) {
  const box = $("#chapterphoto"); if (!box) return; const imgs = $$("img", box), src = CHAPTER_PHOTO[name];
  const cur = imgs[chapterSide]; if (src && cur.getAttribute("src") === src && cur.classList.contains("on")) return;
  imgs.forEach(i => i.classList.remove("on")); if (!src) return;
  chapterSide = 1 - chapterSide; const next = imgs[chapterSide]; if (next.getAttribute("src") !== src) next.src = src; next.classList.add("on");
}
// ------------------------------------------------------------------ Studio tabs
state.tab = "talk"; document.body.dataset.tab = "talk"; state.autoAdapt = load("reach.autoAdapt", false);
function openTab(name) {
  state.tab = name; $$("#apptabs button").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name))); document.body.dataset.tab = name;
  $$(".app-slide .tabpanel").forEach(p => { p.hidden = p.dataset.panel !== name; });
  if (name === "watch") { loadWatch(); }
  if (name !== "watch" && visual.on && state.src !== "visual") stopVisual();
  if (name === "after") { afterView = afterView || makeAfter(); afterView.open(); } else if (afterView) afterView.close();
  if (name === "freq") openFreq(); else closeFreq();
}
// After the music (web/after.js): made the first time the tab opens, so its 3D city costs nothing until then
let afterView = null;
function sessionGoal() { const g = (state.result && !state.result.error && state.result.session && state.result.session.goal) || state.goal || document.body.dataset.goal || "calm"; return ACCENT[g] && g !== "visual" ? g : "calm"; }
function makeAfter() {
  return initAfter({ $, tr, L, esc, API, openTab, goal: sessionGoal,
    accent: () => ACCENT[sessionGoal()] || "#3fd1c0",
    profileQS: () => { const prof = currentProfile(); if (!prof.favorites || !prof.favorites.length) return ""; return prof.id === "you" || prof.id !== state.source ? `profile=${encodeURIComponent(JSON.stringify(prof))}` : `persona=${encodeURIComponent(prof.id)}`; } });
}
$("#autoadapt").checked = state.autoAdapt; $("#autoadapt").addEventListener("change", (e) => { state.autoAdapt = e.target.checked; save("reach.autoAdapt", state.autoAdapt); });
$("#apptabs").addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) openTab(b.dataset.tab); });

// ------------------------------------------------------------------ film info cards
const INFO = {
  neurons: [["0.5–4 Hz", "delta: deep sleep", ""], ["4–8 Hz", "theta: drowsiness, memory consolidation", ""], ["8–12 Hz", "alpha: relaxed wakefulness", ""], ["12–30 Hz", "beta: alert focus", ""], ["40 Hz", "gamma: under trial in Alzheimer's (Cognito HOPE, n≈530)", "https://bcs.mit.edu/news/study-suggests-40hz-sensory-stimulation-may-benefit-some-alzheimers-patients-years"]],
  genome: [["45–97 genes", "changed activity in blood after 20 min of music, in musically experienced listeners", "https://peerj.com/articles/830"], ["SNCA ↑", "a dopamine-pathway gene among those upregulated (Kanduri 2015)", "https://peerj.com/articles/830"], ["Not supported", "any 'DNA modification', durable change, or clinical outcome", ""]],
  galaxy: [["220 km/s", "the Sun's speed around the galactic centre", ""], ["230 million years", "one galactic year", ""], ["≈100,000", "heartbeats a day; a 60 bpm session meets your resting rate", ""]],
  touch: [["Qloo", "cross-domain taste: your own artists first, then the ones Qloo links to them in your culture, plus podcasts and shows. Sent: entity ids, genre tags, a city. Never: your words, face, voice or mood", "https://docs.qloo.com"], ["Council", "Listener · Taste · Clinician · Composer · Guardian · Gate, every step hash-chained", ""], ["Evidence", "A: stress/anxiety, subjective sleep, music therapy in autism and cancer care, paced breathing. Experimental: entrainment, 40 Hz for wellness", ""]],
};
function renderInfoCards() {
  for (const [slide, cards] of Object.entries(INFO)) {
    const sec = slides.find(s => s.dataset.slide === slide); if (!sec) continue;
    let box = sec.querySelector(".infocards"); if (!box) { box = document.createElement("div"); box.className = "infocards"; sec.appendChild(box); }
    box.innerHTML = cards.map(([b, t, u]) => `<div class="infocard"><b>${esc(b)}</b>${esc(t)}${u ? ` <a href="${esc(u)}" target="_blank" rel="noopener">source</a>` : ""}</div>`).join("");
  }
}

// ------------------------------------------------------------------ profile (you, or a clinic patient loaded into the editor)
function currentProfile() {
  const y = state.you; const favs = y.favorites.filter(f => f.name);
  const base = state.source ? state.personas.find(p => p.id === state.source) : null;
  const unchanged = base && base.name === y.name && base.age === +y.age && base.city === y.city && favs.length === base.favorites.length && favs.every((f, i) => f.entity_id === base.favorites[i].entity_id) && (base.capacities?.hearing || "full") === y.hearing;
  if (unchanged) return base;
  return { id: "you", name: y.name || tr(L(), "you"), age: +y.age || 30, city: y.city || "", language: L(), targets: [], favorites: favs,
    capacities: { hearing: y.hearing || "full", vision: "full", reading: "yes", mobility: "ambulatory", verbal: "yes" }, sensory: {}, flags: [], consent: { taste: true }, city_coords: y.here || CITY[y.city] || null, here: y.here || null };
}
function profileReady() { return state.you.favorites.filter(f => f.entity_id || f.name).length >= 1; }
function saveYou() { save("reach.you", state.you); save("reach.source", state.source); }
function favChip(f, i, scope) { return `<span class="fav" title="${esc(f.entity_id ? "Qloo entity " + f.entity_id : "not in Qloo yet; used for tracks")}">${esc(f.name)} <small>${esc((f.type || "").replace("_", " "))}${f.entity_id ? "" : " ·♪"}</small><button data-i="${i}" data-scope="${scope}" aria-label="remove">×</button></span>`; }
function renderYou() {
  $("#youname").textContent = state.you.name || tr(L(), "you"); $("#mename").value = state.you.name || ""; $("#youage").value = state.you.age; $("#youcity").value = state.you.city || ""; $("#youhearing").value = state.you.hearing || "full";
  $("#mesummary").textContent = [state.you.age, state.you.city, tr(L(), "h_" + (state.you.hearing || "full")), state.you.favorites.slice(0, 3).map(f => f.name).join(", ")].filter(Boolean).join(" · ");
  $("#favs").innerHTML = state.you.favorites.map((f, i) => favChip(f, i, "you")).join("");
  $("#ob-favs").innerHTML = state.you.favorites.map((f, i) => favChip(f, i, "you")).join("");
  const wf = $("#wl-favs"); if (wf) { wf.innerHTML = state.you.favorites.map((f, i) => favChip(f, i, "you")).join(""); const ex = $("#wl-examples"); if (ex) ex.innerHTML = state.you.favorites.length ? "" : WL_EXAMPLES.map(n => `<button type="button" data-ex="${esc(n)}">+ ${esc(n)}</button>`).join(""); }
}
document.addEventListener("click", (e) => { const b = e.target.closest(".fav button[data-scope]"); if (!b) return; const i = +b.dataset.i; if (b.dataset.scope === "you") { state.you.favorites.splice(i, 1); state.source = null; saveYou(); renderYou(); } else { const m = state.members[+b.dataset.scope.split(":")[1]]; if (m) { m.favorites.splice(i, 1); save("reach.members", state.members); renderMembers(); renderPeople(); } } });
$("#youname").addEventListener("input", () => { state.you.name = $("#youname").textContent.trim().slice(0, 40); state.source = null; saveYou(); $("#mename").value = state.you.name; });
$("#mename").addEventListener("input", () => { state.you.name = $("#mename").value.trim().slice(0, 40); state.source = null; saveYou(); $("#youname").textContent = state.you.name || tr(L(), "you"); });
$("#youage").addEventListener("change", () => { state.you.age = Math.min(100, Math.max(3, +$("#youage").value || 30)); state.source = null; saveYou(); });
$("#youcity").addEventListener("change", () => { state.you.city = $("#youcity").value.trim().slice(0, 40); state.source = null; saveYou(); });
$("#youhearing").addEventListener("change", () => { state.you.hearing = $("#youhearing").value; state.source = null; saveYou(); renderYou(); if (state.you.hearing === "none") setSrc("visual"); });
$("#youage").addEventListener("change", renderYou); $("#youcity").addEventListener("change", renderYou);

// autocomplete (Qloo entities + Deezer/iTunes artists worldwide)
function bindSuggest(input, box, onPick) {
  let timer = null;
  input.addEventListener("input", () => { clearTimeout(timer); const q = input.value.trim(); if (q.length < 2) { box.hidden = true; return; } timer = setTimeout(async () => {
    try { const j = await (await fetch(`${API}/api/suggest?q=${encodeURIComponent(q)}`)).json(); const res = j.results || [];
      box.innerHTML = res.length ? res.map(r => `<button data-name="${esc(r.name)}" data-type="${esc(r.type)}" data-id="${esc(r.entity_id || "")}">${r.image ? `<img src="${esc(r.image)}" alt="" referrerpolicy="no-referrer" style="width:22px;height:22px;border-radius:6px;object-fit:cover;margin-inline-end:8px">` : ""}${esc(r.name)}<small>${esc(tr(L(), "kind." + r.type) || r.type.replace("_", " "))}${r.fans ? ` · ${r.fans >= 1e6 ? (r.fans / 1e6).toFixed(1) + "M" : r.fans >= 1e3 ? Math.round(r.fans / 1e3) + "k" : r.fans} fans` : ""} · ${r.source.includes("qloo") ? "Qloo" : r.source}</small></button>`).join("") : `<button data-name="${esc(q)}" data-type="artist" data-id="">${esc(q)}<small>${j.mode === "fixture" ? "offline" : "use as typed"}</small></button>`;
      box.hidden = false; $$("button", box).forEach(b => b.addEventListener("click", () => { onPick({ name: b.dataset.name, type: b.dataset.type, entity_id: b.dataset.id || null }); input.value = ""; box.hidden = true; }));
    } catch { box.hidden = true; } }, 220); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); const first = $("button", box); if (first && !box.hidden) first.click(); else if (input.value.trim()) { onPick({ name: input.value.trim(), type: "artist", entity_id: null }); input.value = ""; box.hidden = true; } } if (e.key === "Escape") box.hidden = true; });
}
let warmTimer = null;
function warmCulture() { clearTimeout(warmTimer); warmTimer = setTimeout(() => { const prof = currentProfile(); if (!prof.favorites.length) return; fetch(`${API}/api/culture?profile=${encodeURIComponent(JSON.stringify(prof))}`).catch(() => {}); }, 900); }
function addFav(f) { if (!f.name) return; warmCulture(); setTimeout(renderYou, 0); if (!state.you.favorites.find(x => x.name.toLowerCase() === f.name.toLowerCase())) state.you.favorites.push(f); state.you.favorites = state.you.favorites.slice(0, 10); state.source = null; saveYou(); renderYou(); }
bindSuggest($("#favinput"), $("#favsuggest"), addFav); bindSuggest($("#ob-favinput"), $("#ob-suggest"), addFav);
document.addEventListener("click", (e) => { if (!e.target.closest(".favadd")) $$(".suggest").forEach(b => b.hidden = true); });

// onboarding (every visit to the Studio, prefilled with what Reach remembers)
function openOnboard() {
  if (guide && guide.open) return;
  $("#ob-name").value = state.you.name || ""; $("#ob-age").value = state.you.age || 30; $("#ob-city").value = state.you.city || ""; $("#ob-hearing").value = state.you.hearing || "full";
  $("#ob-start").textContent = state.you.name && profileReady() ? `${tr(L(), "ob_continue")} ${state.you.name}` : tr(L(), "ob_start"); renderYou(); $("#onboard").hidden = false;
}
const obSeen = () => { try { sessionStorage.setItem("reach.ob", "1"); } catch {} };
$("#editme").addEventListener("click", openOnboard);
$("#ob-name").addEventListener("input", () => { $("#ob-start").textContent = tr(L(), "ob_start"); });
$("#ob-start").addEventListener("click", () => { obSeen(); prevSession = null; state.pin = null; state.avoid = []; state.you.name = $("#ob-name").value.trim().slice(0, 40); state.you.age = Math.min(100, Math.max(3, +$("#ob-age").value || 30)); state.you.city = $("#ob-city").value.trim().slice(0, 40); state.you.hearing = $("#ob-hearing").value; state.source = null; saveYou(); renderYou(); if (!profileReady()) { $("#ob-favinput").focus(); return; } $("#onboard").hidden = true; if (state.you.hearing === "none") setSrc("visual"); compose({ play: true }); });
$("#ob-demo").addEventListener("click", () => { obSeen(); const first = state.personas.find(p => (p.capacities?.hearing || "full") !== "none"); if (first) loadPersona(first); $("#onboard").hidden = true; compose({ play: true }); });

// group members
function renderMembers() {
  const box = $("#members"); box.innerHTML = state.members.map((m, i) => `<div class="member"><b>${esc(m.name)}</b>${(m.favorites || []).map((f, j) => favChip(f, j, "m:" + i)).join("")}<input data-m="${i}" class="mfav" type="text" placeholder="${esc(tr(L(), "fav_ph"))}"><label><input type="checkbox" data-nv="${i}" ${m.needs?.vocals === false ? "checked" : ""}> ${esc(tr(L(), "src_bed")) === "" ? "" : "no vocals"}</label><button class="rm" data-rm="${i}">×</button></div>`).join("");
  $$(".mfav", box).forEach(inp => { const sug = document.createElement("div"); sug.className = "suggest"; sug.hidden = true; inp.insertAdjacentElement("afterend", sug); inp.parentElement.style.position = "relative"; bindSuggest(inp, sug, (f) => { state.members[+inp.dataset.m].favorites.push(f); save("reach.members", state.members); renderMembers(); }); });
  $$("input[data-nv]", box).forEach(c => c.addEventListener("change", () => { state.members[+c.dataset.nv].needs = c.checked ? { vocals: false } : {}; save("reach.members", state.members); }));
  $$("button[data-rm]", box).forEach(b => b.addEventListener("click", () => { state.members.splice(+b.dataset.rm, 1); save("reach.members", state.members); renderMembers(); }));
  if (state.members.length) $("#groupbox").open = true;
}
$("#memberinput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); const name = $("#memberinput").value.trim().slice(0, 30); if (!name) return; state.members.push({ name, favorites: [], needs: {} }); save("reach.members", state.members); $("#memberinput").value = ""; renderMembers(); } });

function loadPersona(p) {
  prevSession = null; state.pin = null; state.avoid = [];
  state.source = p.id; state.you = { name: p.name, age: p.age, city: p.city, hearing: p.capacities?.hearing || "full", favorites: p.favorites.map(f => ({ ...f })) }; state.goal = null; state.goal2 = null; state.override = null; state.members = []; save("reach.members", []);
  saveYou(); renderYou(); renderMembers(); $("#request").value = p.sample_request || ""; syncGoals();
  if (state.you.hearing === "none") setSrc("visual"); else if (state.src === "visual") setSrc("artists");
  if (state.slide === "earth") { const c = p.city_coords || CITY[p.city]; if (c) film.sets.earth.face(c[0], c[1]); }
}
$("#goals").addEventListener("click", (e) => { const b = e.target.closest("button[data-goal]"); if (!b) return; pickGoal(b.dataset.goal); if (state.goal) compose({ play: true }); });
function clearGoal() { state.goal = null; state.goal2 = null; syncGoals(); }
function setAccent(goal) { document.body.dataset.goal = goal || ""; film.setAccent(ACCENT[goal] || "#c9a24a"); }
function setBackdrop(url) { const b = $("#backdrop"); state.art = url || null; if (url) { b.style.setProperty("--art", `url("${url.replace(/"/g, "%22")}")`); } b.classList.toggle("on", !!url && (state.slide === "app" || state.tour.on)); }

// ------------------------------------------------------------------ sensors: face, voice, hands, speech, dial
const face = new FaceReader($("#camvideo")), voice = new VoiceReader(); let recog = null, faceBox = null;
function camLive() { $(".camwrap").classList.toggle("live", !!face.stream); }
// (the old "How I feel" drawer is the Feel tab now)
setInterval(camLive, 700);
face.onRead = (expr, box) => { faceBox = box; if (!state.consent.face) { state.face = null; return; } if (expr && !state.face) state.faceSince = performance.now(); if (!expr) state.faceSince = 0; state.face = expr; if (!hands.on) $("#camhint").textContent = expr ? tr(L(), "face_on") : tr(L(), "face_none"); updateMoodEstimate(); };
voice.onRead = (f) => { if (!talk.on) return; state.voice = f; updateMoodEstimate(); };    // the voice is read only while the person talks
$("#cam").addEventListener("click", async (e) => { const b = e.currentTarget; const on = b.getAttribute("aria-pressed") !== "true"; try { if (on) { await face.start(); state.consent.face = true; $("#camhint").textContent = tr(L(), "face_on"); } else { if (!hands.on) face.stop(); state.consent.face = false; state.face = null; $("#camhint").textContent = ""; } b.setAttribute("aria-pressed", String(on)); } catch (err) { console.warn(err); b.setAttribute("aria-pressed", "false"); } updateMoodEstimate(); });
// voice: push to talk. Reach never listens on its own, so it can't hear its own songs or podcasts as requests.
// While you talk the music steps back (ducked), and only then is the tone of your voice read (if you allowed it).
const talk = { on: false, r: null, n: 0 };
$("#mic").addEventListener("click", (e) => { const b = e.currentTarget; const on = b.getAttribute("aria-pressed") !== "true"; state.consent.voice = on; if (!on) state.voice = null; b.setAttribute("aria-pressed", String(on)); if (on) toast("🎙 " + tr(L(), "mic_ptt"), 5200); updateMoodEstimate(); });
function startTalk() {
  if (talk.on) { endTalk(); return; }
  player.warm().catch(() => {});
  const r = speechRecognizer(L(), (text, final) => { $("#request").value = text; if (final) { endTalk(); if (text.trim()) send(); } });
  if (!r) { addMsg("sys", tr(L(), "no_speech")); return; }
  talk.on = true; talk.r = r; $("#speak").setAttribute("aria-pressed", "true"); $("#speak").classList.add("live");
  player.duck(true); if (yt.player) { try { yt.player.setVolume(12); } catch {} } if (state.tour.audio) state.tour.audio.volume = 0.15;
  const my = ++talk.n; if (state.consent.voice) voice.start().then(() => { if (!talk.on || talk.n !== my) voice.stop(); }).catch(() => {});
  r.onend = () => endTalk(); r.onerror = () => endTalk();
  try { r.start(); toast("🎙 " + tr(L(), "listening")); } catch { endTalk(); }
}
function endTalk() {
  if (!talk.on) return; talk.on = false; const r = talk.r; talk.r = null; try { r && r.stop(); } catch {}
  $("#speak").setAttribute("aria-pressed", "false"); $("#speak").classList.remove("live");
  player.duck(false); if (yt.player) { try { yt.player.setVolume(85); } catch {} } if (state.tour.audio) state.tour.audio.volume = 0.9; voice.stop();
}
// hands: MediaPipe's hand model when it can load, otherwise the author's own skin-colour tracker
// (web/vendor/tracker.js) told where the face is. Gestures drive the player; a head turn never does.
const hands = { on: false, reader: new GestureReader(), timer: null, last: null, since: 0, cool: 0, trail: [], moved: 0 };
const GEST = { palm: ["✋", "play / pause"], fist: ["✊", "pause"], victory: ["✌", "next"], thumb_up: ["👍", "more like this"], thumb_down: ["👎", "not this"], pinch: ["🤏", "—"], point: ["☝", "—"] };
const HOLD = { palm: 800, fist: 900, victory: 700, thumb_up: 700, thumb_down: 700 };
// a small live camera window that stays on screen while hands are on: you see your hand, its landmarks, and the gesture read
function pip(on) {
  const box = $("#handpip"), v = $("#pipvideo"); box.hidden = !on;
  if (on && face.stream) { v.srcObject = face.stream; v.play().catch(() => {}); } else { v.srcObject = null; }
}
function pipSay(text) { const el = $("#piplabel"); if (el) el.textContent = text; }
const PIP_STATUS = { loading: "loading the hand model…", ready: "hand model ready · show a palm", fallback: "hand model unavailable · simple tracker" };
$("#hands").addEventListener("click", async (e) => { const b = e.currentTarget; const on = b.getAttribute("aria-pressed") !== "true";
  try {
    if (on) { if (!face.stream) await face.start(); hands.on = true; b.setAttribute("aria-pressed", "true"); pip(true); $("#camhint").textContent = tr(L(), "hands_cal");
      const mode = await hands.reader.start((st) => pipSay(PIP_STATUS[st] || st)); if (!hands.on) return;
      $("#camhint").textContent = tr(L(), mode === "mediapipe" ? "gest_mp" : "gest_skin") + (mode === "skin" && hands.reader.error ? ` (${hands.reader.error.slice(0, 80)})` : ""); handsLoop(); }
    else { hands.on = false; clearTimeout(hands.timer); hands.reader.stop(); pip(false); if (!state.consent.face) face.stop(); $("#camhint").textContent = state.consent.face ? tr(L(), "face_on") : ""; b.setAttribute("aria-pressed", "false"); }
  } catch (err) { console.warn(err); hands.on = false; pip(false); b.setAttribute("aria-pressed", "false"); toast("camera: " + (err && err.message || err)); } });
function drawHand(r) {
  const v = $("#pipvideo"), cv = $("#pipcanvas"); if (!cv || !v.videoWidth) return; const W = cv.clientWidth || 200, H = cv.clientHeight || 150;
  if (cv.width !== W) { cv.width = W; cv.height = H; } const g = cv.getContext("2d"); g.clearRect(0, 0, W, H);
  if (!r || !r.landmarks) return; const lm = r.landmarks, P = (p) => [p.x * W, p.y * H];
  g.lineWidth = 2.5; g.strokeStyle = "rgba(63,209,192,0.95)"; g.beginPath(); for (const [i, j] of HAND_LINKS) { const [x1, y1] = P(lm[i]), [x2, y2] = P(lm[j]); g.moveTo(x1, y1); g.lineTo(x2, y2); } g.stroke();
  g.fillStyle = "#c9a24a"; for (const p of lm) { const [x, y] = P(p); g.beginPath(); g.arc(x, y, 3.2, 0, 6.283); g.fill(); }
}
function handsLoop() {
  if (!hands.on) return; const v = $("#pipvideo").videoWidth ? $("#pipvideo") : $("#camvideo");
  if (v.videoWidth && v.readyState >= 2) {
    const r = hands.reader.read(v, faceBox); const now = performance.now();
    const g = r.present ? r.gesture : null; drawHand(r);
    if (g !== hands.last) { hands.last = g; hands.since = now; hands.fired = null; }
    // motion history: a gesture only counts while the hand is held still (a moving open hand is not a "pause")
    if (r.present && r.x != null) hands.trail.push([now, r.x]); else hands.trail = []; hands.trail = hands.trail.filter(p => now - p[0] < 800);
    const xs = hands.trail.map(p => p[1]), travel = xs.length > 3 ? Math.max(...xs) - Math.min(...xs) : 0;
    if (travel > 0.08) hands.moved = now;
    const held = now - hands.since, still = now - (hands.moved || 0) > 500;
    const need = g && HOLD[g], k = need ? Math.min(1, held / need) : 0; $("#pipmeter").style.width = `${Math.round((still ? k : 0) * 100)}%`;
    if (r.calibrating) pipSay(tr(L(), "hands_cal"));
    else if (r.present) pipSay(g && GEST[g] ? `${GEST[g][0]} ${g.replace("_", " ")} → ${GEST[g][1]}` : `hand · ${r.source}`);
    else if (hands.reader.status === "ready" || hands.reader.mode) pipSay(PIP_STATUS.ready);
    if (now > hands.cool && r.present && !(g && hands.fired === g)) {
      const fire = (ms, text) => { hands.cool = now + ms; hands.trail = []; hands.since = now; hands.fired = g; toast(text); };
      if (g === "victory" && held > HOLD.victory && still) { nextTrack(); fire(2200, "✌ " + tr(L(), "next_up")); }
      else if (g === "palm" && held > HOLD.palm && still) { togglePlay(); fire(2200, "✋ " + (player.playing || visual.on ? "❚❚" : "▶")); }
      else if (g === "fist" && held > HOLD.fist && player.playing) { player.pause(); setPlayUI(false); fire(2500, "✊ ❚❚"); }
      else if (g === "thumb_up" && held > HOLD.thumb_up) { feedback("up"); fire(3500, "👍 " + tr(L(), "remembered")); }
      else if (g === "thumb_down" && held > HOLD.thumb_down) { const t = currentTrack(); fire(3500, "👎 " + tr(L(), "not_this")); if (t && t.artist && state.result && !state.result.error) avoidArtists([t.artist]); else nextTrack(); }
    }
  }
  hands.timer = setTimeout(handsLoop, 70);
}
$("#speak").addEventListener("click", startTalk);
const ANCH = { neutral: [0, 0.35], happy: [0.7, 0.55], sad: [-0.6, 0.25], angry: [-0.6, 0.8], fearful: [-0.5, 0.85], disgusted: [-0.5, 0.6], surprised: [0.1, 0.8] };
function updateMoodEstimate() {
  const parts = [];
  if (state.face) { let v = 0, a = 0, tot = 0; for (const k in ANCH) { const p = state.face[k] || 0; v += ANCH[k][0] * p; a += ANCH[k][1] * p; tot += p; } if (tot > 0) parts.push([v / tot, a / tot, 0.5]); }
  if (state.voice) { const f = state.voice; parts.push([0.2 * f.pitch_var - 0.1 * (1 - f.energy), Math.min(1, 0.15 + 0.45 * f.energy + 0.25 * f.pitch_var + 0.15 * f.rate), 0.3]); }
  if (parts.length) { const w = parts.reduce((s, p) => s + p[2], 0); const raw = { valence: parts.reduce((s, p) => s + p[0] * p[2], 0) / w, arousal: parts.reduce((s, p) => s + p[1] * p[2], 0) / w };
    // smoothed over ~10 s: one frown is not a mood
    const m = state.mood; state.mood = m ? { valence: m.valence * 0.92 + raw.valence * 0.08, arousal: m.arousal * 0.92 + raw.arousal * 0.08 } : raw; } else state.mood = null;
  drawDial(); renderMoodWords();
}
function moodWords(m) { return m ? tr(L(), moodKey(m)) : null; }
function renderMoodWords() {
  const m = state.override || state.mood; const el = $("#moodwords"); if (!el) return;
  if (!m) { el.innerHTML = `<small>${tr(L(), "dial_none")}</small>`; return; }
  const top = state.face ? Object.entries(state.face).sort((a, b) => b[1] - a[1])[0] : null;
  el.innerHTML = `${tr(L(), "reads")}: <b>${esc(moodWords(m))}</b><small>arousal ${m.arousal.toFixed(2)} · valence ${m.valence.toFixed(2)}${top ? ` · ${top[0]} ${Math.round(top[1] * 100)}%` : ""}${state.voice ? ` · voice ${state.voice.energy > 0.3 ? "strong" : "quiet"}${state.voice.pitch_var < 0.2 ? ", flat" : ", lively"}` : ""}${state.override ? " · corrected" : ""}</small>`;
}
const dial = $("#dial"), dctx = dial.getContext("2d");
function drawDial() {
  const W = dial.width, c = W / 2, r = W / 2 - 14; dctx.clearRect(0, 0, W, W);
  const grad = dctx.createRadialGradient(c, c, 10, c, c, r); grad.addColorStop(0, "rgba(201,162,74,0.14)"); grad.addColorStop(1, "rgba(63,209,192,0.05)");
  dctx.fillStyle = grad; dctx.beginPath(); dctx.arc(c, c, r, 0, 6.283); dctx.fill(); dctx.strokeStyle = "rgba(237,231,218,0.2)"; dctx.lineWidth = 1.5; dctx.stroke();
  dctx.beginPath(); dctx.moveTo(c - r, c); dctx.lineTo(c + r, c); dctx.moveTo(c, c - r); dctx.lineTo(c, c + r); dctx.stroke();
  dctx.fillStyle = "rgba(237,231,218,0.72)"; dctx.font = `${Math.round(W * 0.075)}px IBM Plex Sans, sans-serif`; dctx.textAlign = "center"; dctx.textBaseline = "middle";
  dctx.fillText(tr(L(), "dial_bright"), c, c - r + W * 0.08); dctx.fillText(tr(L(), "dial_low"), c, c + r - W * 0.08);
  dctx.textAlign = "left"; dctx.fillText(tr(L(), "dial_calm"), c - r + W * 0.05, c - W * 0.06); dctx.textAlign = "right"; dctx.fillText(tr(L(), "dial_wired"), c + r - W * 0.05, c - W * 0.06);
  const m = state.override || state.mood; const note = $("#dialnote"); if (note) note.textContent = m ? tr(L(), "dial_note") : tr(L(), "dial_none");
  if (!m) return;
  const x = c + (m.arousal * 2 - 1) * r * 0.9, y = c - m.valence * r * 0.9;
  dctx.fillStyle = "rgba(201,162,74,0.25)"; dctx.beginPath(); dctx.arc(x, y, 24, 0, 6.283); dctx.fill();
  dctx.fillStyle = "#c9a24a"; dctx.beginPath(); dctx.arc(x, y, 8, 0, 6.283); dctx.fill();
}
let dragging = false;
const dialSet = (e) => { const rect = dial.getBoundingClientRect(); const x = (e.clientX - rect.left) / rect.width, y = (e.clientY - rect.top) / rect.height; state.override = { arousal: Math.min(1, Math.max(0, (x - 0.05) / 0.9)), valence: Math.min(1, Math.max(-1, (0.5 - y) * 2 / 0.9)) }; drawDial(); renderMoodWords(); };
dial.addEventListener("pointerdown", (e) => { dragging = true; dialSet(e); }); window.addEventListener("pointermove", (e) => { if (dragging) dialSet(e); }); window.addEventListener("pointerup", () => { if (dragging) { dragging = false; if (state.slide === "app") compose({ play: true }); } });
dial.addEventListener("dblclick", () => { state.override = null; drawDial(); renderMoodWords(); });
function drawCamOverlay() {
  const cv = $("#camoverlay"); if (!face.stream) { if (cv.width) cv.width = 0; return; }
  const v = $("#camvideo"); if (cv.width !== v.videoWidth) { cv.width = v.videoWidth || 320; cv.height = v.videoHeight || 240; }
  const g = cv.getContext("2d"); g.clearRect(0, 0, cv.width, cv.height); if (!faceBox) return;
  g.strokeStyle = "rgba(201,162,74,0.9)"; g.lineWidth = 2; g.strokeRect(faceBox.x, faceBox.y, faceBox.width, faceBox.height);
}

// ------------------------------------------------------------------ chat
function addMsg(kind, text, who, url) { const box = $("#chat"); const d = document.createElement("div"); d.className = "msg " + kind; d.innerHTML = (who ? `<span class="who">${esc(who)}</span>` : "") + esc(text) + (url ? ` <a href="${esc(url)}" target="_blank" rel="noopener">source</a>` : ""); box.appendChild(d); box.scrollTop = box.scrollHeight; return d; }
$("#compose").addEventListener("click", () => send());
$("#request").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
let prevSession = null;
// ------------------------------------------------------------------ the conversation agent: every message is read against what is playing
// (server: reach/dialogue.py, rules + an optional LLM). Only a real new need goes back to the council.
function currentTrack() { if (yt.on && yt.list.length && yt.i >= 0) return yt.list[yt.i]; if (!state.tracks.length) return null; return state.tracks[Math.max(0, player.trackIdx)] || state.tracks[0]; }
function favArtists() { return currentProfile().favorites.filter(f => f.type === "artist").map(f => f.name); }
function chatContext() {
  const r = state.result && !state.result.error ? state.result : null, s = r ? r.session : null, t = currentTrack();
  const c = t && s ? s.carrier.find(x => x.name.toLowerCase() === (t.artist || "").toLowerCase()) : null;
  const own = t ? (t.own ?? (!!c && !!c.own)) || favArtists().some(n => n.toLowerCase() === (t.artist || "").toLowerCase()) : false;
  return { lang: L(), favourites: favArtists(), carrier: s ? s.carrier.map(x => x.name) : [], src: state.src, goal: r ? r.listener.goal : null, protocol_id: s ? s.protocol_id : null,
    now: t ? { artist: t.artist, title: t.title, kind: t.kind === "podcast" ? "podcast" : t.scape ? "scape" : "song", own, because: own ? null : (t.because || (c && c.because && c.because[0] && c.because[0].name) || null), culture: own ? null : (t.culture || (c && c.culture) || null) } : null,
    lens: s && s.lens ? s.lens.name : null, set_aside: s ? (s.set_aside || []).map(a => a.name) : [] };
}
async function chat(text) {
  try { const r = await fetch(`${API}/api/chat`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text, context: chatContext() }) }); return r.ok ? await r.json() : null; } catch { return null; }
}
function boldNames(html) {
  const names = [...new Set([...((state.result && state.result.session && state.result.session.carrier) || []).map(c => c.name), ...currentProfile().favorites.map(f => f.name), ...((state.pin && state.pin.names) || [])])].filter(n => n && n.length > 2).sort((a, b) => b.length - a.length);
  if (!names.length) return html; const re = new RegExp(names.map(n => esc(n).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "g");
  return html.replace(re, m => `<b>${m}</b>`);
}
// countries and languages arrive as tokens (⟦cc:IR⟧, ⟦lang:fas⟧) and are named by the browser in the reader's language
function placeName(kind, code) { try { return new Intl.DisplayNames([L()], { type: kind === "cc" ? "region" : "language" }).of(code) || code; } catch { return code; } }
function untoken(text) { return String(text || "").replace(/⟦(cc|lang):([A-Za-z]{2,3})⟧/g, (m, k, c) => placeName(k, c)); }
function reachSay(text, url) { if (!text) return null; text = untoken(text); const d = addMsg("friend", "", "Reach"); d.innerHTML = `<span class="who">Reach</span>${boldNames(esc(text))}${url ? ` <a href="${esc(url)}" target="_blank" rel="noopener">${tr(L(), "source")}</a>` : ""}`; $("#chat").scrollTop = $("#chat").scrollHeight; return d; }
async function send(sayText) {
  const text = String(sayText ?? $("#request").value).trim(); $("#request").value = "";
  if (!text) { compose({ play: true }); return; }
  addMsg("me", text);
  if (!profileReady()) { $("#onboard").hidden = false; return; }
  if (/\b(different|other|new) artists\b|\bsomething (new|different)\b|\bdiscover|\bexplore|otros artistas|algo nuevo|هنرمندان دیگر|چیز جدید|其他艺术家|新的/i.test(text)) { state.pin = null; state.explore = true; }
  const d = await chat(text);
  const has = state.result && !state.result.error;
  if (!d) { clearGoal(); compose({ play: true, say: text }); return; }
  if (!has) {                                       // no session yet: the council builds one, with whatever the message asked for
    if (d.act === "answer") { reachSay(d.reply, d.passages && d.passages[0] && d.passages[0].url); return; }
    if (d.act === "play") state.pin = { names: d.artists, only: !!d.only };
    if (d.act === "source" && d.src) { setSrc(d.src); if (d.src === "scape" && d.topic) state.scape = d.topic; state.podq = d.src === "podcast" ? d.topic : null; }
    clearGoal(); compose({ play: true, say: text, goal: d.goal }); return;
  }
  await act(d, text);
}
async function act(d, text) {
  const s = state.result.session;
  switch (d.act) {
    case "play": reachSay(d.reply); if (d.avoid && d.avoid.length) state.avoid = [...new Set([...(state.avoid || []), ...d.avoid.map(x => x.toLowerCase())])]; await playArtists(d.artists, { only: !!d.only }); break;
    case "avoid": reachSay(d.reply); await avoidArtists(d.artists); break;
    case "next": toast("⏭ " + d.reply); nextTrack(); break;
    case "pause": if (player.playing || visual.on) await togglePlay(); toast("❚❚ " + d.reply); break;
    case "resume": if (!player.playing && !visual.on) await togglePlay(); toast("▶ " + d.reply); break;
    case "source":
      reachSay(d.reply); if (d.src === "scape" && d.topic) { state.scape = d.topic; renderScapeKinds(); } state.podq = d.src === "podcast" ? (d.topic || null) : null; setSrc(d.src);
      if (d.src === "visual") { if (player.playing) player.pause(); stopYT(); startVisual(); break; }
      stopVisual(); await loadTracks(s); if (!player.playing) await startPlayback(); break;
    case "answer": reachSay(d.reply, d.passages && d.passages[0] && d.passages[0].url); break;
    default: clearGoal(); state.pin = null; compose({ play: true, say: text, goal: d.goal });
  }
}
// play these artists now, inside the current session (no new plan needed); only=true plays nothing else
async function playArtists(names, { only = false } = {}) {
  if (!names || !names.length) return; state.pin = { names, only }; stopVisual(); setSrc("artists");
  const asked = names.map(n => n.toLowerCase()); state.avoid = (state.avoid || []).filter(n => !asked.includes(n));
  if (player.playing) { player.pause(); setPlayUI(false); } stopYT();
  await loadTracks(state.result.session);
  if (state.missing && state.missing.length) reachSay(tr(L(), "not_found").replace("{a}", state.missing.join(", ")));
  if (state.tracks.length && !player.playing) await startPlayback();
}
async function avoidArtists(names) {
  const low = (names || []).map(n => n.toLowerCase()); if (!low.length) { nextTrack(); return; }
  state.avoid = [...new Set([...(state.avoid || []), ...low])];
  const favLow = favArtists().map(f => f.toLowerCase());
  const ids = state.result.session.carrier.filter(c => low.includes(c.name.toLowerCase()) && !c.own && !favLow.includes(c.name.toLowerCase())).map(c => c.entity_id).filter(Boolean);
  if (ids.length) { state.memory.disliked = [...new Set([...(state.memory.disliked || []), ...ids])].slice(-16); save("reach.memory", state.memory); }
  if (state.pin) { state.pin.names = state.pin.names.filter(n => !low.includes(n.toLowerCase())); if (!state.pin.names.length) state.pin = null; }
  if (state.src === "podcast") { nextTrack(); return; }
  const wasPlaying = player.playing; await loadTracks(state.result.session); if (!wasPlaying && state.tracks.length) await startPlayback();
}

// ------------------------------------------------------------------ compose (SSE council)
const player = new SessionPlayer();
function requestPayload(say, goal) {
  const req = { text: (say ?? $("#request").value).slice(0, 400), lang: L(), local_hour: new Date().getHours(), consent: { ...state.consent }, memory: { ...state.memory, fb: fbScores(), explore: !!state.explore }, name: state.you.name || "" };
  state.explore = false;
  if (state.goal) req.goal = state.goal; else if (goal) req.goal = goal;
  if (state.goal && state.goal2) req.then_goal = state.goal2;        // a journey: the first need, then the second
  if (state.pin && state.pin.names.length) { req.pin = state.pin.names.slice(0, 4); req.only = !!state.pin.only; }
  if (prevSession) req.prev = prevSession;
  const people = state.members.filter(m => (m.name && m.name !== "?") || (m.favorites || []).length);
  if (people.length) req.group = people.map((m, i) => ({ name: m.name && m.name !== "?" ? m.name : `${tr(L(), "wl_person_name")} ${i + 1}`, favorites: m.favorites || [], needs: m.needs || {} }));
  if (state.consent.face && state.face) { req.face = state.face; req.face_seconds = state.faceSince ? Math.round((performance.now() - state.faceSince) / 1000) : 0; }
  if (state.consent.voice && state.voice) req.voice = { energy: state.voice.energy, pitch_var: state.voice.pitch_var, rate: state.voice.rate };
  if (state.override) req.override = state.override;
  const src = state.source && state.personas.find(p => p.id === state.source);
  if (src && src.sample_hour !== undefined && req.text === src.sample_request && !state.face) req.local_hour = src.sample_hour;
  return req;
}
let es = null;
// while the guided tour speaks, nothing else makes a sound: no session, no song, no start-page music
const quiet = { on: false };
function compose({ play = false, auto = false, say, goal } = {}) {
  if (!profileReady()) { $("#onboard").hidden = false; return; }
  if (es) { es.close(); es = null; }
  if (play) player.warm().catch(() => {});
  const prof = currentProfile(); const btn = $("#compose"); btn.disabled = true;
  const trace = $("#trace"); trace.innerHTML = ""; $("#story").textContent = ""; $("#feedback").hidden = true; $("#nowplaying").hidden = true;
  if (player.playing) player.stop(); stopVisual(); stopYT();
  $("#hz-big").textContent = "—"; $("#hudmeta").innerHTML = `<span>${tr(L(), "composing")}…</span>`; $("#adaptline").textContent = ""; $("#stagecaption").innerHTML = ""; $("#play").disabled = true;
  const req = requestPayload(say, goal);
  const qs = prof.id === "you" || prof.id !== state.source ? `profile=${encodeURIComponent(JSON.stringify(prof))}` : `persona=${encodeURIComponent(prof.id)}`;
  es = new EventSource(`${API}/api/session/stream?${qs}&req=${encodeURIComponent(JSON.stringify(req))}`);
  const add = (kind, html) => { const d = document.createElement("div"); d.className = "ev " + kind; const role = tr(L(), "roles." + kind); d.innerHTML = `<div class="av">${esc(String(role)[0])}</div><div><div class="k">${esc(role)}</div>${html}</div>`; trace.appendChild(d); trace.scrollTop = trace.scrollHeight; };
  const J = (e) => JSON.parse(e.data);
  es.addEventListener("guard", e => { const d = J(e); add("guard", `${d.signals.join(", ") || "text only"} · on device: ${d.on_device.join(", ")} · leaves browser: ${d.leaves_browser.join(", ")}${d.notes.length ? " · " + esc(d.notes.join("; ")) : ""} <code>${d.hash}</code>`); });
  es.addEventListener("listener", e => { const d = J(e); add("listener", `goal <b>${esc(d.goal.replace(/_/g, " "))}</b>${d.inferred ? " (inferred)" : d.goal_words.length ? ` (${esc(d.goal_words.slice(0, 3).join(", "))})` : ""} · arousal ${d.mood.arousal} · valence ${d.mood.valence} · confidence ${d.mood.confidence} · ${tr(L(), "meet")} ${d.arousal_bpm} bpm${d.intents.length ? ` · intents: ${d.intents.join(", ")}` : ""}${d.observations.length ? "<br>" + esc(d.observations.join("; ")) : ""}${d.notes.length ? "<br>" + esc(d.notes.join("; ")) : ""}`); $("#hudmeta").innerHTML = `<span>${esc(d.goal.replace(/_/g, " "))}</span><span>${tr(L(), "meet")} <b>${d.arousal_bpm}</b> bpm</span>`; });
  es.addEventListener("group", e => { const d = J(e); add("group", `${d.members.map(m => `<b>${esc(m.name)}</b> ${esc([...(m.genres || []), m.artist || ""].filter(Boolean).join(", "))}${m.needs && m.needs.vocals === false ? " · no vocals" : ""}${m.favourites ? ` · ${m.favourites} favourites` : ""}`).join(" · ")}${d.stated_count ? ` · ${d.stated_count} people` : ""}`); });
  es.addEventListener("fairness", e => { const d = J(e); add("fairness", `<b>${esc(d.protocol)}</b> · Bayes → ${esc(d.bayes)} · minimax → ${esc(d.minimax)} · LFP → ${esc(d.lfp)} · weights ${Object.entries(d.weights).map(([k, v]) => `${esc(k)} ${v}`).join(", ")}<br>${d.top.map(([n, pm]) => `${esc(n)}: ${Object.entries(pm).map(([k, v]) => `${esc(k)} ${v}`).join(" / ")}`).join("<br>")}${d.instrumental ? "<br>instrumental for the room" : ""}`); });
  es.addEventListener("journey", e => { const d = J(e); add("plan", `<b>${esc(d.start)} → ${esc(d.then)}</b> · ${d.minutes} ${tr(L(), "minutes")} · ${d.segments.map(x => `${esc(x[0])} ${x[1]}→${x[2]} Hz @ ${x[3]} bpm`).join(" · ")}`); });
  es.addEventListener("plan", e => { const d = J(e); add("plan", `candidates: ${d.candidates.map(x => `<b>${esc(x)}</b>`).join(", ")} · ${d.steps.join(" → ")}`); });
  es.addEventListener("taste", e => { const d = J(e); add("taste", d.ok ? `<b>${esc(d.protocol)}</b> · ${d.carrier.map(esc).join(", ")} · palette <b>${esc(d.palette)}</b> · fit ${d.fit_rate} · strength ${d.strength} (data weight ${d.data_weight}) · texture ${esc((d.texture || []).join(", "))}${d.memory && (d.memory.liked || d.memory.disliked) ? ` · memory ${d.memory.liked}↑ ${d.memory.disliked}↓` : ""} · <code>${d.source}</code>` : `<b>${esc(d.protocol)}</b> · ${esc(d.reason)}`); });
  es.addEventListener("rule", e => { const d = J(e); add("rule", `<b>${esc(d.protocol)}</b> · evidence ${d.evidence} · fit ${d.fit} · taste ${d.taste} · ${d.rules.map(r => `<span class="pill ${r.verdict}" title="${esc(r.reason)}">${r.rule}</span>`).join(" ")}`); });
  es.addEventListener("adjudicate", e => { const d = J(e); add("adjudicate", `Bayes → <b>${esc(d.bayes)}</b> · minimax → <b>${esc(d.minimax)}</b> · least-favourable prior → <b>${esc(d.lfp)}</b> · ${Object.entries(d.weights).map(([k, v]) => `${tr(L(), k)} ${v}`).join(" · ")}`); });
  es.addEventListener("compose", e => { const d = J(e); add("compose", `<b>${esc(d.protocol)}</b> · ${d.key} · ${esc(d.palette)} · ${d.entrainment} · depth ${d.pulse_depth} · ${d.gain_dbfs} dBFS · ${d.duration_min} min<br>${d.segments.map(s => `${esc(s[0])} ${s[1]}→${s[2]} Hz @ ${s[3]} bpm (${s[4]})`).join(" · ")}`); });
  es.addEventListener("guardian", e => { const d = J(e); add("guardian", d.checks.map(c => `<code>${c.check}</code> ${esc(c.action)} · ${esc(c.detail)}`).join("<br>")); });
  es.addEventListener("gate", e => { const d = J(e); add("gate", `p=${d.p} · ${d.p}·${d.benefit} ${d.justified ? "≥" : "<"} ${(1 - d.p).toFixed(3)}·${d.cost} → <b>${d.justified ? "recommend" : "hold"}</b>`); });
  es.addEventListener("refuse", e => { const d = J(e); add("refuse", `<b>${esc(d.by)}</b>: ${esc(d.reason)}`); });
  es.addEventListener("seal", e => { const d = J(e); add("seal", `${d.length} entries · head <code>${d.head}</code> · ${d.ok ? "chain intact" : "chain broken"}`); });
  es.addEventListener("result", e => { const d = J(e).result; state.result = d; state.lastMood = null; state.moodStreak = 0; if (!d.error) setAccent(d.listener.goal); const ready = renderResult(d); logSession(d); if (play && !d.error) Promise.resolve(ready).then(() => { if (state.result === d && !player.playing && !yt.on) startPlayback(); }); });
  const done = () => { if (es) es.close(); es = null; btn.disabled = false; };
  es.addEventListener("done", done); es.onerror = () => { add("refuse", "stream interrupted"); addMsg("err", "The council could not be reached. Is the server running?"); done(); };
}
function logSession(d) {
  if (d.error) return; const p = d.profile || {};
  state.sessions.unshift({ ts: Date.now(), pid: p.id, name: p.name, goal: d.listener.goal, protocol: d.session.protocol_name, carrier: d.session.carrier.slice(0, 3).map(c => c.name), key: d.session.key, hz: [d.session.segments[0].hz_from, d.session.segments.at(-1).hz_to], feedback: null, head: d.ledger_head.slice(0, 12) });
  state.sessions = state.sessions.slice(0, 20); save("reach.sessions", state.sessions); renderPatients();
}

// ------------------------------------------------------------------ studio: bands, pulse, carrier source, playback
function bandFor(hz) { return BANDS.find(([n, lo, hi]) => hz >= lo && hz < hi) || BANDS[4]; }
let lastBand = null;
// one row of five bands, each in its own colour; the plate below takes the colour and the figure of the live one
function renderBands(hz) {
  const el = $("#band-strip"); if (!el) return;
  if (el.children.length !== BANDS.length || el.dataset.lang !== L()) { el.dataset.lang = L(); el.innerHTML = BANDS.map(([n, lo, hi, rep]) => `<button data-hz="${rep}" data-lo="${lo}" data-hi="${hi}" style="--bc:${BAND_COLOR[n]}" title="${esc(n + " " + lo + "–" + hi + " Hz · " + tr(L(), "lab_" + n))}"><i></i>${esc(tr(L(), "band_for." + n))}</button>`).join(""); lastBand = null; }
  if (hz == null) return; const b = bandFor(hz)[0];
  [...el.children].forEach(sp => sp.classList.toggle("on", hz >= +sp.dataset.lo && hz < +sp.dataset.hi));
  if (b !== lastBand) { lastBand = b; document.body.style.setProperty("--band", BAND_COLOR[b]); film.sets.studio.setBand(BAND_COLOR[b]); $("#bandnote").textContent = `${b} · ${tr(L(), "band_for." + b)}`; $("#bandnote").title = tr(L(), "lab_" + b); }
  renderPulseState();
}
// says plainly whether a pulse is sounding: songs always play clean, a frequency is its own session
function renderPulseState() { const el = $("#pulsestate"); if (!el) return; const songs = state.src === "artists" || state.src === "podcast" || state.src === "scape"; el.textContent = songs && !player.layer.on ? tr(L(), "pulse_clean") : tr(L(), "pulse_on"); el.classList.toggle("live", !(songs && !player.layer.on)); }
$("#band-strip").addEventListener("click", async (e) => { const sp = e.target.closest("[data-hz]"); if (!sp) return; holdPulse(+sp.dataset.hz);
  // a frequency is its own session: never laid over a song
  if (state.src !== "bed" && state.result && !state.result.error) { setSrc("bed"); stopVisual(); await loadTracks(state.result.session); }
  if (!player.playing && state.result && !state.result.error) await startPlayback();
  toast(`${tr(L(), "src_bed")} · ${sp.textContent.trim()}`); });
function holdPulse(v) { player.holdHz = v; $("#pulse").value = v; $("#pulseout").textContent = `${v.toFixed(1)} Hz · ${tr(L(), "hold_hz")}`; $("#pulsefree").hidden = false; $("#hz-big").textContent = v.toFixed(1); renderBands(v); film.sets.studio.hz = v; film.sets.neurons.hz = v; }
$("#pulse").addEventListener("input", (e) => holdPulse(+e.target.value));
// the plate, full screen: tap a band to hear it and watch its figure form
function plateMode(on) { document.body.classList.toggle("platemode", on); film.setShot(on ? "plate" : "app", 0); film.shotStart = performance.now(); $("#platebtn").setAttribute("aria-pressed", String(on)); $("#platebtn").textContent = on ? "✕ " + tr(L(), "plate_view").replace(/^⤢\s*/, "") : tr(L(), "plate_view"); }
$("#platebtn").addEventListener("click", () => plateMode(!document.body.classList.contains("platemode")));
// Frequencies: speakers (pulsing tone) or headphones (binaural), with or without the soft pad underneath; remembered
{ const fs = load("reach.freqstyle", "iso"), fp = load("reach.freqpad", false); player.setFreqStyle(fs, fp); $("#freqpad").checked = fp;
  $$("#freqopts [data-fs]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.fs === fs))); }
$("#freqopts").addEventListener("click", (e) => { const b = e.target.closest("[data-fs]"); if (!b) return; player.setFreqStyle(b.dataset.fs); save("reach.freqstyle", b.dataset.fs);
  $$("#freqopts [data-fs]").forEach(x => x.setAttribute("aria-pressed", String(x === b))); toast(b.textContent); });
$("#freqpad").addEventListener("change", (e) => { player.setFreqStyle(null, e.target.checked); save("reach.freqpad", e.target.checked); });
window.addEventListener("keydown", (e) => { if (e.key === "Escape" && document.body.classList.contains("platemode")) plateMode(false); });
$("#pulsefree").addEventListener("click", () => { player.holdHz = null; $("#pulsefree").hidden = true; $("#pulseout").textContent = tr(L(), "session_hz"); });
$("#depth").addEventListener("input", (e) => { player.depthOverride = +e.target.value; $("#depthout").textContent = (+e.target.value).toFixed(2); });
$("#demospeed").addEventListener("change", (e) => player.setSpeed(e.target.checked ? 10 : 1));
function renderScapeKinds() { const sel = $("#scapekind"); const kinds = SCAPES; sel.innerHTML = kinds.map(k => `<option value="${k}" ${k === state.scape ? "selected" : ""}>${esc(tr(L(), "scape_kinds." + k))}</option>`).join(""); }
$("#scapekind").addEventListener("change", async (e) => { state.scape = e.target.value; if (state.result && !state.result.error) { await loadTracks(state.result.session); if (!player.playing) startPlayback(); } });
$("#srcsel").addEventListener("click", async (e) => { const b = e.target.closest("button"); if (!b) return; setSrc(b.dataset.src);
  if (!state.result || state.result.error) { compose({ play: true }); return; }
  if (state.src === "visual") { if (player.playing) { player.pause(); } stopYT(); startVisual(); return; }
  stopVisual(); await loadTracks(state.result.session); if (!player.playing) startPlayback(); else if (state.src === "bed") toast("♪ " + tr(L(), "src_bed")); });
const SCAPES = ["fire", "ocean", "rain", "window", "thunder", "forest", "river", "waterfall", "wind", "night", "bowls", "whale"];
function setSrc(src) { state.src = src; document.body.dataset.src = src; player.setFreqMode(src === "bed"); setTimeout(renderPulseState, 0); $$("#srcsel button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.src === src))); $("#scapekind").hidden = src !== "scape"; }
function artistChip(c) {
  return `<span class="artist" tabindex="0">${c.image ? `<img src="${esc(c.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=noimg>♪</span>'">` : `<span class="noimg">♪</span>`}<span>${esc(c.name)}${c.own ? `<span class="tag own">${esc(tr(L(), "own_tag"))}</span>` : `<span class="tag rec" title="${esc(c.because && c.because[0] ? tr(L(), "because") + " " + c.because[0].name : "")}">${esc(tr(L(), "rec_tag"))}${c.culture ? " · " + esc(placeName("cc", c.culture)) : ""}</span>`}${!c.own && c.affinity ? ` <small>${(+c.affinity).toFixed(2)}</small>` : ""}${c.per_member ? ` <small title="${esc(Object.entries(c.per_member).map(([k, v]) => k + " " + v).join(", "))}">⚖</small>` : ""}</span><span class="acts"><button data-act="play" data-id="${esc(c.entity_id || "")}" data-name="${esc(c.name)}">▶ ${tr(L(), "play_now")}</button><button data-act="like" data-id="${esc(c.entity_id || "")}" data-name="${esc(c.name)}">+ ${tr(L(), "more_like")}</button><button data-act="dislike" data-id="${esc(c.entity_id || "")}" data-name="${esc(c.name)}">× ${tr(L(), "not_this")}</button></span></span>`;
}
document.addEventListener("click", (e) => {
  const b = e.target.closest(".artist .acts button"); if (!b) return; const id = b.dataset.id, name = b.dataset.name;
  if (b.dataset.act === "play") { if (state.result && !state.result.error) playArtists([name]); return; }
  if (b.dataset.act === "dislike") { addMsg("me", `${tr(L(), "not_this")}: ${name}`); if (state.result && !state.result.error) avoidArtists([name]); return; }
  const key = b.dataset.act === "like" ? "liked" : "disliked"; if (id) { state.memory[key] = [...new Set([...(state.memory[key] || []), id])].slice(-16); save("reach.memory", state.memory); }
  addMsg("me", `${b.dataset.act === "like" ? tr(L(), "more_like") : tr(L(), "not_this")}: ${name}`); compose({ play: true, say: b.dataset.act === "like" ? `more like ${name}` : `not ${name}` });
});
function friendly(r) {
  const s = r.session, l = r.listener, lang = L(), F = tr(lang, "fr");
  const prev = null;
  if (prev && prev.protocol === s.protocol_id) {
    const ch = [];
    if (s.segments.at(-1).bpm < prev.bpm1 - 2) ch.push(F.c_slower.replace("{b}", s.segments.at(-1).bpm));
    if (s.segments.at(-1).bpm > prev.bpm1 + 2) ch.push(F.c_faster.replace("{b}", s.segments.at(-1).bpm));
    if (s.duration_min < prev.min) ch.push(F.c_shorter.replace("{m}", s.duration_min)); if (s.duration_min > prev.min) ch.push(F.c_longer.replace("{m}", s.duration_min));
    if (s.vocals === false && prev.vocals !== false) ch.push(F.c_novocals);
    const newA = s.carrier.slice(0, 3).map(c => c.name).filter(n => !prev.carrier.includes(n)); if (newA.length) ch.push(F.c_artists.replace("{a}", newA.map(esc).map(x => `<b>${x}</b>`).join(F.and)));
    const intents = (l.intents || []).length;
    return `${ch.length ? F.c_done + " " + ch.join("; ") + "." : intents ? F.c_same : F.c_same}${F.c_next ? " " + F.c_next : ""}`;
  }
  const name = (r.profile && r.profile.name && r.profile.id !== "you") || state.you.name ? esc(state.you.name || r.profile.name) : "";
  const mk = l.mood ? moodKey({ arousal: +l.mood.arousal, valence: +l.mood.valence }) : null;
  const artists = s.carrier.slice(0, 3).map(c => `<b>${esc(c.name)}</b>`).join(F.and);
  const fav = esc((r.profile.favorites || []).slice(0, 2).map(f => f.name).join(F.and));
  const b0 = s.segments[0].bpm, b1 = s.segments.at(-1).bpm;
  const move = b1 < b0 - 3 ? F.down.replace("{b}", b1) : b1 > b0 + 3 ? F.up.replace("{b}", b1) : F.steady;
  const ev = (r.protocol.evidence || [])[0];
  const evline = ev ? (ev.grade === "A" ? F.evA : ev.grade === "B" ? F.evB : F.evC).replace("{c}", esc(ev.claim.charAt(0).toLowerCase() + ev.claim.slice(1))) : "";
  const group = s.group ? F.group.replace("{n}", s.group.members.length) : "";
  if (s.entrainment === "visual") return `${name ? name + ", " : ""}${F.visual.replace("{fav}", fav)} ${F.ask}`;
  const sensed = (state.consent.face && state.face) || state.voice || state.override;
  return `${name ? name + ", " : ""}${mk && sensed ? F.feel.replace("{m}", tr(lang, mk)) + " " : ""}${F.built.replace("{min}", s.duration_min).replace("{p}", esc(s.protocol_name)).replace("{a}", artists).replace("{fav}", fav)}${group} ${F.pace.replace("{b}", b0)} ${move} ${evline} ${F.ask}`;
}
function renderQuick() {
  const q = tr(L(), "quick"); $("#quick").innerHTML = q.map(([label, say]) => `<button data-say="${esc(say)}">${esc(label)}</button>`).join("");
}
$("#quick").addEventListener("click", (e) => { const b = e.target.closest("button[data-say]"); if (!b) return; addMsg("me", b.textContent); clearGoal(); state.pin = null; compose({ play: true, say: b.dataset.say }); });
let toastTimer = null;
function toast(text, ms = 3200) { let t = $("#toast");
  if (!t.closest(".tabpanel") || t.closest(".tabpanel").hidden || state.slide !== "app" || state.tab !== "talk") { t = $("#gtoast") || document.body.appendChild(Object.assign(document.createElement("div"), { id: "gtoast", className: "toast gtoast" })); } t.textContent = text; t.hidden = false; t.style.animation = "none"; void t.offsetWidth; t.style.animation = ""; clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, ms); }
function renderResult(r, { quiet = false, full = false } = {}) {
  const hud = $("#hudmeta"), story = $("#story");
  if (r.error) {
    story.innerHTML = `<div class="refusal"><b>${tr(L(), "refused")}</b> · ${esc(r.detail)}${r.alternative ? `<br>${tr(L(), "alt_vibro")}` : ""}</div>`;
    hud.innerHTML = `<span style="color:var(--red)">${tr(L(), "refused")}</span>`; $("#hz-big").textContent = "—"; $("#play").disabled = true; $("#timeline").innerHTML = ""; $("#ledgerhead").textContent = "";
    if (!quiet) { (r.replies || []).forEach(x => addMsg(x.agent + " err", x.text, tr(L(), "roles." + (x.agent === "clinician" ? "rule" : x.agent)))); if (r.alternative) { setSrc("visual"); addMsg("sys", tr(L(), "visual_on")); startVisual(); } }
    return;
  }
  const s = r.session; player.load(s); $("#play").disabled = false;
  if (!quiet) prevSession = { protocol: s.protocol_id, goal: r.listener.goal, bpm1: s.segments.at(-1).bpm, min: s.duration_min, vocals: s.vocals };
  if (s.entrainment === "visual" && state.src !== "visual") { setSrc("visual"); if (!quiet) addMsg("sys", tr(L(), "visual_on")); }
  if (s.entrainment === "visual" && !quiet) setTimeout(() => openTab("watch"), 400);
  else if (s.entrainment !== "visual" && state.src === "visual" && state.you.hearing !== "none") setSrc("artists");
  { const art = (s.carrier.find(c => c.image) || {}).image; if (art && !quiet) setBackdrop(art); } player.depthOverride = null; $("#depth").value = s.pulse_depth; $("#depthout").textContent = s.pulse_depth.toFixed(2); player.holdHz = null; $("#pulsefree").hidden = true; $("#pulse").value = s.segments[0].hz_from; $("#pulseout").textContent = tr(L(), "session_hz");
  story.textContent = r.story.text;
  if (!quiet) {
    if (r.reply) reachSay(r.reply); else { addMsg("friend", "", "Reach").innerHTML = `<span class="who">Reach</span>${friendly(r)}`; }
    $("#chat").scrollTop = $("#chat").scrollHeight;
    renderQuick();
  }
  $("#hz-big").textContent = s.segments[0].hz_from.toFixed(1); renderBands(s.segments[0].hz_from);
  hud.innerHTML = `<span><b>${esc(s.protocol_name)}</b></span><span><b id="lv-bpm">${s.segments[0].bpm}</b> ${tr(L(), "bpm")}</span><span>${s.duration_min} ${tr(L(), "minutes")}</span>${s.group ? `<span>⚖ ${esc(s.group.members.join(", "))}</span>` : ""}${s.flag ? `<span class="flag">⚑ engaging, weakly proven</span>` : ""}`;
  $("#timeline").innerHTML = s.segments.map((g, i) => `<div class="seg" style="--w:${g.minutes}" data-i="${i}"><i></i><span>${esc(g.name)} · ${g.hz_from}→${g.hz_to} Hz · ${g.bpm}</span></div>`).join("");
  $("#stagecaption").innerHTML = `<div class="carrier" style="justify-content:center">${s.carrier.slice(0, 7).map(artistChip).join("")}</div>`;
  $("#feedback").hidden = false;
  $("#ledgerhead").textContent = `head ${r.ledger_head} · ${r.ledger.length} entries · ${r.elapsed_ms} ms · ${r.qloo_calls.length} Qloo calls`;
  $("#verdict").innerHTML = "";
  $("#qloobox").innerHTML = `${tr(L(), "sent")}<br><br>palette <b>${esc(r.taste.palette)}</b> from tags ${esc((r.taste.texture_tags || []).join(", "))} · carrier strength ${r.taste.strength} · fit ${r.taste.fit_rate} · <code>${esc(r.taste.source)}</code><div class="carrier" style="margin-top:8px">${s.carrier.map(c => `<span class="ent">${c.image ? `<img src="${esc(c.image)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=noimg>♪</span>'">` : `<span class="noimg">♪</span>`}<span>${esc(c.name)}${c.affinity ? ` <small>${(+c.affinity).toFixed(2)}</small>` : ""}${c.because && c.because.length ? ` <small>· ${tr(L(), "because")} ${esc(c.because[0].name)} (${c.because[0].score})</small>` : ""}</span></span>`).join("")}</div>`;
  $("#evidencebox").innerHTML = r.protocol.evidence.map(e => `<div><span class="pill ${e.grade}">${e.grade}</span><div>${esc(e.claim)}<small>${esc(e.note)} <a href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.source)}</a></small></div></div>`).join("") + `<div><span class="pill D">D</span><div>Music and gene activity<small>${esc(state.protocols?.gene_note || "")}</small></div></div>`;
  film.sets.studio.hz = s.segments[0].hz_from; film.sets.studio.bpm = s.segments[0].bpm; film.sets.human.bpm = s.segments[0].bpm; film.sets.galaxy.bpm = s.segments[0].bpm; film.sets.neurons.hz = s.segments[0].hz_from;
  if (!quiet) { player.setTracks([]); state.tracks = []; const ready = loadTracks(s); if (state.src === "visual") startVisual(); return ready; }
}
let loadSeq = 0;
const uniqi = (xs) => { const seen = new Set(); return xs.filter(x => { const k = (x || "").toLowerCase(); if (!k || seen.has(k)) return false; seen.add(k); return true; }); };
async function loadTracks(s) {
  const seq = ++loadSeq; stopYT(); $("#podpick").hidden = true;
  state.tracks = []; state.missing = []; const np = $("#nowplaying"); np.hidden = false; np.classList.remove("yt");
  const label = esc(s.carrier.slice(0, 4).map(c => c.name).join(" · "));
  if (state.src === "bed") { player.setTracks([]); np.innerHTML = `<span class="noimg">♪</span><div><div class="np-title">${tr(L(), "src_bed")}</div><div class="np-sub">${label}</div></div><div></div>`; return; }
  if (state.src === "visual") { player.setTracks([]); np.innerHTML = `<span class="noimg">◎</span><div><div class="np-title">${tr(L(), "src_visual")}</div><div class="np-sub">${tr(L(), "visual_on")}</div></div><div></div>`; loadWatch(); return; }
  np.innerHTML = `<span class="noimg">♪</span><div><div class="np-title">${tr(L(), "loading_tracks")}</div><div class="np-sub">${label}</div></div><div></div>`;
  let order = [];
  try {
    if (state.src === "scape") { order = [{ title: tr(L(), "scape_kinds." + state.scape), artist: tr(L(), "real_rec"), stream: `./assets/scapes/${state.scape}.mp3`, loop: true, source: "recording", duration: null, because: null, scape: true }]; }
    else if (state.src === "podcast") { order = await loadPodcasts(seq); if (order === null) return; }
    else if (s.calm_carrier && !(state.pin && state.pin.names.length)) {
      // lively favourites and a need for sleep or calm: the most watched calm instrumental pieces instead
      let items = []; try { items = (await (await fetch(`${API}/api/calmmusic?goal=${encodeURIComponent(s.calm_carrier.goal)}`)).json()).items || []; } catch {}
      if (seq !== loadSeq) return;
      if (items.length) { order = items.map(v => ({ title: v.title, artist: v.channel || "", ytid: v.id, source: "youtube", because: tr(L(), "calm_pick"), calm: true })); state.tracks = order; player.setTracks([]); startYT(order); return; }
      const kind = s.calm_carrier.goal === "sleep" ? "rain" : "ocean";
      order = [{ title: tr(L(), "scape_kinds." + kind), artist: tr(L(), "real_rec"), stream: `./assets/scapes/${kind}.mp3`, loop: true, source: "recording", scape: true }];
    }
    else {
      // the person's own artists first (the ones they just asked for before all), then Qloo's picks in their culture
      const avoid = new Set(state.avoid || []), favs = favArtists();
      const pin = (state.pin && state.pin.names) || [], only = !!(state.pin && state.pin.only);
      const own = s.carrier.filter(c => c.own).map(c => c.name), recs = s.carrier.filter(c => !c.own && !c.pinned).map(c => c.name);
      const isOwn = (n) => own.includes(n) || favs.some(f => f.toLowerCase() === n.toLowerCase());
      const names = uniqi(only ? pin : [...pin, ...own, ...favs, ...recs]).filter(n => !avoid.has(n.toLowerCase())).slice(0, 12);
      const per = only ? 8 : pin.length ? 3 : 2, got = new Map();
      await Promise.all(names.map(async (n) => { try { const j = await (await fetch(`${API}/api/preview?artist=${encodeURIComponent(n)}&limit=${only ? 8 : 6}`)).json(); const c = s.carrier.find(x => x.name === n); const mine = isOwn(n), asked = pin.includes(n);
        got.set(n, (j.tracks || []).map(t => ({ ...t, own: mine, asked, because: mine || asked ? null : (c && c.because && c.because[0] && c.because[0].name) || null, culture: mine || asked ? null : (c && c.culture) || null }))); } catch { got.set(n, []); } }));
      if (seq !== loadSeq) return;
      state.missing = pin.filter(n => !(got.get(n) || []).length);
      const heard = new Set(load("reach.heard", []));
      const list = (n) => { const l = got.get(n) || []; return [...l.filter(t => !heard.has(`${t.artist}|${t.title}`)), ...l.filter(t => heard.has(`${t.artist}|${t.title}`))].slice(0, per); };
      const rr = (ls) => { const out = []; for (let i = 0; i < Math.max(0, ...ls.map(l => l.length)); i++) for (const l of ls) if (l[i]) out.push(l[i]); return out; };
      const A = names.filter(n => pin.includes(n)).map(list), B = names.filter(n => !pin.includes(n) && isOwn(n)).map(list), C = names.filter(n => !pin.includes(n) && !isOwn(n)).map(list);
      order = rr(A);
      const rot = (load("reach.rot", 0) + 1) % Math.max(1, B.length); save("reach.rot", rot);
      const Br = [...B.slice(rot), ...B.slice(0, rot)];
      const own1 = rr(Br), recs1 = rr(C);
      if (A.length) { for (let i = 0; i < Math.max(own1.length, recs1.length); i++) { if (own1[i]) order.push(own1[i]); if (recs1[i]) order.push(recs1[i]); } }
      else { const first = own1.shift(); if (first) order.push(first); for (let i = 0; i < Math.max(own1.length, recs1.length); i++) { if (recs1[i]) order.push(recs1[i]); if (own1[i]) order.push(own1[i]); } }
      const seen = new Set(); order = order.filter(t => { const k = `${t.artist}|${t.title}`.toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; });
    }
  } catch {}
  if (seq !== loadSeq) return;   // a newer choice replaced this one while it was loading
  if (state.src === "artists" && state.health && state.health.youtube && order.length) { state.tracks = order; player.setTracks([]); startYT(order); return; }
  state.tracks = order; player.setTracks(order);
  if (!order.length) np.innerHTML = `<span class="noimg">♪</span><div><div class="np-title">${tr(L(), "bed_only")}</div><div class="np-sub">${label}</div></div><div></div>`;
  else if (!player.playing) renderTrack({ track: order[0], next: order[1] });
}
// podcasts: a choice of shows, each with the reason it is here; Next moves to the next show
async function loadPodcasts(seq) {
  const prof = currentProfile(); const qs = prof.id === "you" || prof.id !== state.source ? `profile=${encodeURIComponent(JSON.stringify(prof))}` : `persona=${encodeURIComponent(prof.id)}`;
  const heard = load("reach.heard", []).slice(0, 30).join("|"), shows = load("reach.shows", []).slice(0, 12).join("|"), goal = (state.result && state.result.listener && state.result.listener.goal) || "calm";
  const j = await (await fetch(`${API}/api/podcast?${qs}&lang=${L()}&goal=${encodeURIComponent(goal)}&heard=${encodeURIComponent(heard)}&shows=${encodeURIComponent(shows)}${state.podq ? `&q=${encodeURIComponent(state.podq)}` : ""}`)).json();
  if (seq !== loadSeq) return null;
  state.shows = j.shows || []; renderPodPick(0);
  return state.shows.map(sh => ({ ...sh.episodes[0], kind: "podcast", because: podWhy(sh) }));
}
function podWhy(sh) { const k = "pod_" + sh.why; const t = tr(L(), k); const about = sh.why === "goal" ? (tr(L(), "g_" + sh.about) || sh.about) : /^[A-Z]{2}$/.test(sh.about || "") ? placeName("cc", sh.about) : sh.about || ""; return (t && t !== k ? t : tr(L(), "pod_goal")).replace("{x}", about); }
function renderPodPick(active) {
  const box = $("#podpick"); if (!state.shows || !state.shows.length) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = `<div class="pp-head">${esc(tr(L(), "pod_pick"))}</div><div class="pp-row">${state.shows.map((sh, i) => `<button class="pp ${i === active ? "on" : ""}" data-i="${i}">${sh.cover ? `<img src="${esc(sh.cover)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=noimg>◉</span>'">` : `<span class="noimg">◉</span>`}<span><b>${esc(sh.show)}</b><small>${esc(podWhy(sh))}</small></span><i class="pp-state">${i === active ? "❚❚" : "▶"}</i></button>`).join("")}</div>`;
}
$("#podpick").addEventListener("click", async (e) => { const b = e.target.closest(".pp[data-i]"); if (!b) return; const i = +b.dataset.i;
  if (b.classList.contains("on") && player.playing && player.trackIdx === i) { if (player.trackPaused) player.resumeTrack(); else player.pauseTrack(); return; }
  renderPodPick(i); player.trackIdx = i - 1; player.trackPaused = false; if (!player.playing) await startPlayback(); else player._nextTrack(); });
function renderTrack({ track, next }) {
  const np = $("#nowplaying"); if (!track) return; np.hidden = false;
  const dur = track.scape ? ` · ${tr(L(), "looping")}` : track.duration && track.duration > 45 ? ` · ${Math.round(track.duration / 60)} min` : ` · 30 s ${tr(L(), "preview_note")}`;
  if (player.playing) toast(`♪ ${track.artist} · ${track.title}`); warned = false;
  np.innerHTML = `${track.cover ? `<img src="${esc(track.cover)}" alt="" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=noimg>♪</span>'">` : `<span class="noimg">♪</span>`}<div><div class="np-title">${esc(track.title)}</div><div class="np-sub">${esc(track.artist)}${track.because ? ` · ${track.kind === "podcast" ? "" : tr(L(), "because") + " "}${esc(track.because)}` : track.own ? ` · ${esc(tr(L(), "own_tag"))}` : ""}${dur} · ${esc(track.source || "")}${player.playing ? " · " + tr(L(), "now_playing") : ""}${track.link ? ` <a class="np-full" href="${esc(track.link)}" target="_blank" rel="noopener">${tr(L(), "full_track")} ↗</a>` : ""}${!track.scape && track.kind !== "podcast" && track.artist ? ` <a class="np-full" href="https://www.youtube.com/results?search_query=${encodeURIComponent(track.artist + " " + track.title)}" target="_blank" rel="noopener">YouTube ↗</a>` : ""}</div></div><div class="np-next"><button class="np-toggle" aria-label="pause this">❚❚</button>${next ? `<span>${tr(L(), "next_up")}<b>${esc(next.artist)} · ${esc(next.title)}</b></span>` : ""}</div><div class="np-bar"><i></i></div>`;
  if (track.cover_big || track.cover) setBackdrop(track.cover_big || track.cover);
}
// implicit feedback, the way watch time works for video: what you finish counts for an artist, what you skip
// early counts against (sent as memory.fb; the ranking step uses it, and drops an artist skipped again and again)
const heardNow = { cur: null, frac: 0, userSkip: false };
function fbRecord(track, frac, skipped) {
  if (!track || !track.artist || track.kind === "podcast" || track.scape) return; const fb = load("reach.fb", {}); const k = track.artist.toLowerCase();
  const r = fb[k] || { n: 0, done: 0, skip: 0 }; r.n++; if (frac >= 0.8) r.done++; else if (skipped && frac < 0.4) r.skip++; fb[k] = r; save("reach.fb", fb);
}
function fbScores() { const rows = Object.entries(load("reach.fb", {})).map(([k, r]) => [k, (r.done - 1.5 * r.skip) / (r.n + 2)]).filter(([, v]) => Math.abs(v) > 0.05).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1])).slice(0, 30); return Object.fromEntries(rows.map(([k, v]) => [k, +v.toFixed(2)])); }
const markHeard = (t) => { if (t && t.artist && !t.scape) save("reach.heard", [`${t.artist}|${t.title}`, ...load("reach.heard", []).filter(x => x !== `${t.artist}|${t.title}`)].slice(0, 80)); };
player.on("track", ({ track }) => { markHeard(track); if (heardNow.cur && heardNow.cur !== track) fbRecord(heardNow.cur, heardNow.frac, heardNow.userSkip); heardNow.cur = track; heardNow.frac = 0; heardNow.userSkip = false; });
player.on("time", ({ t, d }) => { if (isFinite(d) && d > 0) heardNow.frac = t / d; });
player.on("track", renderTrack);
// each song or episode has its own play/pause; the big button is the session (and its frequency)
document.addEventListener("click", (e) => { const b = e.target.closest(".np-toggle"); if (!b) return; e.stopPropagation();
  if (yt.on && yt.player) { try { const st = yt.player.getPlayerState(); if (st === 1) { yt.player.pauseVideo(); b.textContent = "▶"; } else { yt.player.playVideo(); b.textContent = "❚❚"; } } catch {} return; }
  if (player.trackPaused) player.resumeTrack(); else if (!player.pauseTrack() && !player.playing) startPlayback(); });
player.on("trackstate", (on) => { $$(".np-toggle").forEach(b => b.textContent = on ? "❚❚" : "▶"); const a = $("#podpick .pp.on"); if (a) { a.classList.toggle("paused", !on); const st = a.querySelector(".pp-state"); if (st) st.textContent = on ? "❚❚" : "▶"; } });
player.on("track", ({ track, idx }) => { if (track && track.kind === "podcast") { save("reach.shows", [track.show || track.artist, ...load("reach.shows", []).filter(x => x !== (track.show || track.artist))].slice(0, 16)); if (state.src === "podcast") renderPodPick(idx); } });
let warned = false;
player.on("time", ({ t, d }) => { if (!warned && isFinite(d) && d < 45 && d - t < 6 && state.tracks.length > 1) { warned = true; const nx = state.tracks[(player.trackIdx + 1) % state.tracks.length]; toast(`${tr(L(), "preview_ends")} ${nx.artist} · ${nx.title}`, 5200); } const bar = $("#nowplaying .np-bar i"); if (bar && isFinite(d) && d > 0) bar.style.setProperty("--p", `${(t / d * 100).toFixed(1)}%`); });
$("#genon").addEventListener("change", (e) => { player.setLayer(e.target.checked); $("#genlayer").classList.toggle("off", !e.target.checked); renderPulseState(); });
$("#genlevel").addEventListener("input", (e) => { player.setLayer(undefined, +e.target.value); $("#genout").textContent = `${Math.round(e.target.value * 100)}%`; });
function nextTrack() { heardNow.userSkip = true; if (yt.on) { ytNext(); return; } if (state.tracks.length > 1) player._nextTrack(); }
function setPlayUI(on) { $("#play").textContent = on ? "❚❚" : "▶"; $("#play").classList.toggle("on", on); if (!on) stopAdaptLoop(); }
async function startPlayback() { if (quiet.on || player.playing) return; if (yt.pending) { const l = yt.pending; yt.pending = null; startYT(l); return; } if (state.src === "visual") { startVisual(); return; } await player.play(); setPlayUI(true); startAdaptLoop(); }
async function togglePlay() { if (player.playing) { player.pause(); if (yt.player) { try { yt.player.pauseVideo(); } catch {} } setPlayUI(false); return; } if (visual.on) { stopVisual(); return; } await startPlayback(); if (yt.player) { try { yt.player.playVideo(); } catch {} } }
$("#play").addEventListener("click", togglePlay);
player.on("state", (st) => {
  $("#hz-big").textContent = st.hz.toFixed(1); renderBands(st.hz);
  const b = $("#lv-bpm"), d = $("#lv-depth"), m = $("#lv-mode"); if (b) b.textContent = st.bpm; if (d) d.textContent = st.depth.toFixed(2); if (m) m.textContent = st.seg.mode;
  $$("#timeline .seg").forEach((el, i) => { const g = state.result.session.segments[i]; const k = Math.min(1, Math.max(0, (st.elapsed - g.start_s) / (g.minutes * 60))); el.style.setProperty("--p", (k * 100) + "%"); el.classList.toggle("now", i === st.idx); });
  film.sets.studio.hz = st.hz; film.sets.studio.bpm = st.bpm; film.sets.human.bpm = st.bpm; film.sets.galaxy.bpm = st.bpm; film.sets.neurons.hz = st.hz;
});
player.on("end", () => setPlayUI(false));
// when a session runs to its end, offer one gentle next step (the After the music tab)
player.on("end", () => { const d = reachSay(tr(L(), "af_chip")); if (!d) return; const b = document.createElement("button"); b.className = "ghost small afchip"; b.textContent = "✦ " + tr(L(), "af_show"); b.addEventListener("click", () => openTab("after")); d.appendChild(document.createTextNode(" ")); d.appendChild(b); });
let adaptTimer = null, adaptCount = 0;
function startAdaptLoop() { stopAdaptLoop(); adaptCount = 0; adaptTimer = setInterval(adaptOnce, 20000); }
function stopAdaptLoop() { if (adaptTimer) clearInterval(adaptTimer); adaptTimer = null; }
async function adaptOnce() {
  if (!player.playing || !state.result || state.result.error) return; const m = state.override || state.mood; if (!m) return;
  if (state.autoAdapt) try { const d = await (await fetch(`${API}/api/adapt`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ session: state.result.session, mood: m, elapsed_s: player.elapsed }) })).json(); player.adapt(d); adaptCount++;
    const line = `${tr(L(), "adapted")} ×${adaptCount} · ${moodWords(m)} · ${d.reason}${d.bpm_delta ? ` · bpm ${d.bpm_delta > 0 ? "+" : ""}${d.bpm_delta}` : ""}${d.hz_delta ? ` · Hz ${d.hz_delta > 0 ? "+" : ""}${d.hz_delta}` : ""}`;
    $("#adaptline").textContent = line; if (d.bpm_delta || d.hz_delta || d.depth_delta) addMsg("compose", line, tr(L(), "roles.compose")); } catch {}
  // a changed mood that holds for two readings (40 s) earns a question before anything is switched
  const key = moodKey(m); if (key !== state.lastMood) { state.lastMood = key; state.moodStreak = 1; } else state.moodStreak++;
  const goal = state.result.listener.goal;
  const wants = (["m_sad", "m_tired", "m_low"].includes(key) && !["mood", "energy", "sleep"].includes(goal)) || (["m_tense", "m_wired"].includes(key) && !["calm", "sleep", "autism_calm"].includes(goal));
  if (wants && state.moodStreak === 3 && Date.now() > state.snooze) askChange(key);     // a change held for a minute: ask, never switch on its own
}
function moodKey(m) {
  const { arousal: a, valence: v } = m;
  if (v < -0.3 && a < 0.5) return "m_sad"; if (v < -0.2 && a >= 0.6) return "m_tense"; if (a >= 0.65) return "m_wired";
  if (a < 0.25 && v < 0) return "m_tired"; if (a < 0.3) return "m_low"; if (v > 0.3) return "m_bright"; if (Math.abs(v) < 0.1 && a < 0.45) return "m_calm"; return "m_flat";
}
function askChange(key) {
  $$("#chat .msg.ask").forEach(x => x.remove());
  const d = addMsg("ask", `${tr(L(), "change_q")} ${tr(L(), key)} ${tr(L(), "change_q2")}`, tr(L(), "roles.listener"));
  d.insertAdjacentHTML("beforeend", `<div class="choices"><button data-choice="keep">${tr(L(), "keep")}</button><button data-choice="smoother">${tr(L(), "smoother")}</button><button data-choice="energetic">${tr(L(), "energetic")}</button></div>`);
  d.querySelector(".choices").addEventListener("click", (e) => { const b = e.target.closest("button[data-choice]"); if (!b) return; d.querySelector(".choices").remove(); state.snooze = Date.now() + 5 * 60 * 1000;
    if (b.dataset.choice === "keep") { addMsg("me", tr(L(), "keep")); return; }
    if (b.dataset.choice === "smoother") { state.goal = "calm"; state.goal2 = null; addMsg("me", tr(L(), "smoother")); compose({ play: true, say: "softer and slower, calm me" }); }
    else { state.goal = "energy"; state.goal2 = null; addMsg("me", tr(L(), "energetic")); compose({ play: true, say: "I need a boost, more energy" }); }
    syncGoals(); });
}

// ------------------------------------------------------------------ visual + haptic session (deaf, or by choice)
const visual = { on: false, raf: null, vib: null, t0: 0, calm: null };
function startVisual() {
  const s = state.result && !state.result.error ? state.result.session : null;
  openTab("watch");
  if (!s) { setSrc("visual"); compose({ play: true }); return; }        // compose first, then come back here
  if (player.playing) player.pause(); stopYT(); if (visual.on) return;
  visual.on = true; visual.t0 = performance.now(); $("#breathlight").classList.add("on"); setPlayUI(true); document.body.classList.add("visualmode");
  $("#vsnote").textContent = tr(L(), "visual_note") + (navigator.vibrate ? " " + tr(L(), "visual_vibe") : "");
  const rate = (s.breathing && s.breathing.rate_per_min) || 6, bpm = s.segments[0].bpm;
  const tick = () => { if (!visual.on) return; const t = (performance.now() - visual.t0) / 1000; const ph = (t * rate / 60) % 1, inhale = ph < 0.5;
    const b = 0.55 + 0.45 * (0.5 - 0.5 * Math.cos(ph * 2 * Math.PI)); $("#orb").style.setProperty("--b", b.toFixed(3)); $("#breathlight").style.setProperty("--b", (0.12 + 0.28 * b).toFixed(3));
    $("#orbword").textContent = tr(L(), inhale ? "breathe_in" : "breathe_out"); $("#orbcount").textContent = String(1 + Math.floor((inhale ? ph : ph - 0.5) * 2 * (60 / rate / 2)));
    const beat = (t * bpm / 60) % 1; $("#orbring").style.setProperty("--r", Math.exp(-beat * 4).toFixed(3)); film.audioLevel = 0.25 + 0.5 * b; visual.raf = requestAnimationFrame(tick); }; tick();
  if (navigator.vibrate) { const period = Math.round(60000 / bpm); visual.vib = setInterval(() => navigator.vibrate(40), period); }
  loadWatch(); calmFilm(true);
}
function stopVisual() { document.body.classList.remove("visualmode"); calmFilm(false); if (!visual.on) return; visual.on = false; cancelAnimationFrame(visual.raf); if (visual.vib) clearInterval(visual.vib); $("#breathlight").classList.remove("on"); if (navigator.vibrate) navigator.vibrate(0); setPlayUI(false); $("#orbword").textContent = ""; $("#orbcount").textContent = ""; }
// a slow 4K nature film behind the breathing light (muted); needs the server's YouTube key
async function calmFilm(on) {
  const bg = $("#watchbg");
  if (!on) { bg.classList.remove("on"); if (visual.calm) { try { visual.calm.destroy(); } catch {} visual.calm = null; } $("#watchbg").innerHTML = `<div id="calmbox"></div>`; return; }
  if (!(state.health && state.health.youtube) || visual.calm) return;
  let v = null; try { v = await (await fetch(`${API}/api/calmvideo`)).json(); } catch {}
  if (!v || !v.id || !visual.on) return;
  try { const YT = await loadYTApi(); visual.calm = new YT.Player("calmbox", { videoId: v.id, playerVars: { autoplay: 1, mute: 1, controls: 0, loop: 1, playlist: v.id, start: v.start || 0, modestbranding: 1, rel: 0, playsinline: 1, iv_load_policy: 3, disablekb: 1 },
    events: { onReady: (e) => { e.target.mute(); e.target.playVideo(); bg.classList.add("on"); } } }); } catch {}
}
async function loadWatch() {
  const prof = currentProfile(); if (!prof.favorites || !prof.favorites.length) return;
  const qs = prof.id === "you" || prof.id !== state.source ? `profile=${encodeURIComponent(JSON.stringify(prof))}` : `persona=${encodeURIComponent(prof.id)}`;
  let items = []; try { const j = await (await fetch(`${API}/api/watch?${qs}`)).json(); items = j.items || []; } catch {}
  if (!items.length && state.result && !state.result.error) items = state.result.session.carrier.map(c => ({ name: c.name, image: c.image, affinity: c.affinity, kind: "artist" }));
  $("#posters").innerHTML = items.slice(0, 8).map(x => `<div class="poster" data-name="${esc(x.name)}" data-kind="${esc(x.kind || "")}" data-year="${esc(x.year || "")}" title="${esc(tr(L(), "watch_trailer"))}">${x.image ? `<img src="${esc(x.image)}" alt="" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=noimg>▣</span>'">` : `<span class="noimg">▣</span>`}<b>${esc(x.name)}</b>${x.affinity ? `Qloo ${(+x.affinity).toFixed(2)} · ` : ""}${esc(tr(L(), "kind." + (x.kind || "")) || "")}</div>`).join("");
}
// a poster opens its trailer, captions on (cc_load_policy), in the interface language
$("#posters").addEventListener("click", async (e) => {
  const p = e.target.closest(".poster"); if (!p || p.dataset.kind === "artist") return;
  const ytSearch = () => window.open(`https://www.youtube.com/results?search_query=${encodeURIComponent(p.dataset.name + " " + (p.dataset.year || "") + " trailer")}`, "_blank", "noopener");
  if (!(state.health && state.health.youtube)) { ytSearch(); return; }      // no key on this server: YouTube's own search, in a new tab
  p.classList.add("busy"); let v = null; try { v = await (await fetch(`${API}/api/trailer?name=${encodeURIComponent(p.dataset.name)}&year=${encodeURIComponent(p.dataset.year || "")}&kind=${encodeURIComponent(p.dataset.kind || "")}`)).json(); } catch {}
  p.classList.remove("busy");
  if (!v || !v.id) { toast(tr(L(), "no_trailer") + " · " + p.dataset.name, 4200); return; }
  $("#trailer").hidden = false; $("#trailerbox").outerHTML = `<div id="trailerbox"></div>`;
  try { const YT = await loadYTApi(); visual.trailer = new YT.Player("trailerbox", { videoId: v.id, playerVars: { autoplay: 1, cc_load_policy: 1, cc_lang_pref: L(), hl: L(), modestbranding: 1, rel: 0, playsinline: 1 } }); } catch {}
});
$("#trailerclose").addEventListener("click", () => { $("#trailer").hidden = true; if (visual.trailer) { try { visual.trailer.destroy(); } catch {} visual.trailer = null; } });
$("#vsstart").addEventListener("click", () => { player.warm().catch(() => {}); setSrc("visual"); startVisual(); });

// ------------------------------------------------------------------ full songs through YouTube (when the server has a YouTube Data API key)
const yt = { on: false, player: null, list: [], i: 0, api: null };
function loadYTApi() { if (yt.api) return yt.api; yt.api = new Promise((res, rej) => { if (window.YT && window.YT.Player) return res(window.YT); window.onYouTubeIframeAPIReady = () => res(window.YT); const sc = document.createElement("script"); sc.src = "https://www.youtube.com/iframe_api"; sc.onerror = rej; document.head.appendChild(sc); setTimeout(() => rej(new Error("youtube timeout")), 6000); }); return yt.api; }
async function startYT(list) { if (quiet.on) { ytHeld(list); return; } yt.on = true; yt.list = list; yt.i = -1; player.setExternal(true); if (!player.playing) await startPlayback(); ytNext(); }
async function ytNext(step = 1) {
  if (!yt.on || !yt.list.length) return;
  { const was = yt.list[yt.i]; let frac = 0; try { frac = yt.player ? yt.player.getCurrentTime() / (yt.player.getDuration() || 1) : 0; } catch {} if (was) fbRecord(was, frac, heardNow.userSkip); heardNow.userSkip = false; }
  yt.i = (yt.i + step + yt.list.length) % yt.list.length; const t = yt.list[yt.i]; markHeard(t);
  let id = t.ytid || null; if (!id) try { id = (await (await fetch(`${API}/api/fullsong?artist=${encodeURIComponent(t.artist)}&title=${encodeURIComponent(t.title)}`)).json()).id; } catch {}
  if (!yt.on) return;
  if (!id) { yt.on = false; player.setExternal(false); state.tracks = yt.list; player.setTracks(yt.list); return; }   // no full song: back to previews
  const np = $("#nowplaying"); np.hidden = false; np.classList.add("yt");
  np.innerHTML = `<div class="np-yt"><div id="npyt"></div></div><div><div class="np-title">${esc(t.title)}</div><div class="np-sub">${esc(t.artist)}${t.because ? ` · ${tr(L(), "because")} ${esc(t.because)}` : ""} · ${tr(L(), "full_track")} · YouTube</div></div><div class="np-next">${yt.list.length > 1 ? `${tr(L(), "next_up")}<b>${esc(yt.list[(yt.i + 1) % yt.list.length].artist)}</b>` : ""}</div>`;
  toast(`♪ ${t.artist} · ${t.title}`);
  try { const YT = await loadYTApi(); if (yt.player) { try { yt.player.destroy(); } catch {} }
    clearTimeout(yt.watch);
    yt.player = new YT.Player("npyt", { videoId: id, playerVars: { autoplay: 1, controls: 0, modestbranding: 1, rel: 0, playsinline: 1, origin: location.origin },
      events: { onReady: (e) => { e.target.setVolume(85); e.target.playVideo(); },
                onStateChange: (e) => { if (e.data === 1) clearTimeout(yt.watch); if (e.data === 0) ytNext(); },
                onError: () => ytFailed(id, false) } });
    // a video that never starts (blocked on this site, or the browser held back sound) is treated as a failure too
    yt.watch = setTimeout(() => { let st = -1; try { st = yt.player ? yt.player.getPlayerState() : -1; } catch {} if (yt.on && st !== 1 && st !== 2 && st !== 3) ytFailed(id, true); }, 7000);
  } catch { yt.on = false; player.setExternal(false); state.tracks = yt.list; player.setTracks(yt.list); }
}
// the full video would not play: this same song's preview now, and previews from here on. Never a skip loop.
function ytFailed(id, stalled) {
  clearTimeout(yt.watch); if (!yt.on) return;
  if (!stalled && id) fetch(`${API}/api/fullsong/bad?id=${encodeURIComponent(id)}`, { method: "POST" }).catch(() => {});
  const rest = yt.list.slice(Math.max(0, yt.i)).concat(yt.list.slice(0, Math.max(0, yt.i)));
  stopYT(); $("#nowplaying").classList.remove("yt"); state.tracks = rest; player.setTracks(rest);
  toast(tr(L(), "yt_fallback"), 4200);
}
// the songs are ready but wait, silent, for the end of the guided tour: shown, not played
function ytHeld(list) {
  yt.pending = list; const t = list[0]; if (!t) return; const np = $("#nowplaying"); np.hidden = false; np.classList.remove("yt");
  np.innerHTML = `<span class="noimg">♪</span><div><div class="np-title">${esc(t.title)}</div><div class="np-sub">${esc(t.artist)}${t.because ? ` · ${tr(L(), "because")} ${esc(t.because)}` : ""} · ${tr(L(), "full_track")} · YouTube</div></div><div class="np-next">${list.length > 1 ? `${tr(L(), "next_up")}<b>${esc(list[1].artist)}</b>` : ""}</div>`;
}
function stopYT() { yt.pending = null; clearTimeout(yt.watch); if (yt.player) { try { yt.player.destroy(); } catch {} yt.player = null; } yt.on = false; player.setExternal(false); }

// ------------------------------------------------------------------ why drawer, feedback, clinic
$("#vsstop").addEventListener("click", () => { stopVisual(); if (state.src === "visual") setSrc(state.you.hearing === "none" ? "visual" : "artists"); });
$("#whybtn").addEventListener("click", () => $("#why").classList.toggle("open")); $("#whyclose").addEventListener("click", () => $("#why").classList.remove("open"));
function feedback(kind) {
  if (!state.result || state.result.error) return; const ids = state.result.session.carrier.map(c => c.entity_id).filter(Boolean).slice(0, 4); const key = kind === "up" ? "liked" : "disliked";
  state.memory[key] = [...new Set([...(state.memory[key] || []), ...ids])].slice(-16); save("reach.memory", state.memory);
  if (state.sessions[0] && state.sessions[0].head === state.result.ledger_head.slice(0, 12)) { state.sessions[0].feedback = kind; save("reach.sessions", state.sessions); renderPatients(); }
  addMsg("sys", tr(L(), "remembered"));
}
$("#feedback").addEventListener("click", (e) => { const b = e.target.closest("button[data-fb]"); if (!b) return; feedback(b.dataset.fb); });
function renderPatients() {
  const box = $("#patients"); if (!box) return;
  const rows = [...(state.source ? [] : [{ id: "you", name: state.you.name || tr(L(), "you"), age: state.you.age, words: null, hearing: state.you.hearing, p: null }]), ...state.personas.map(p => ({ id: p.id, name: p.name, age: p.age, words: p.sample_request, hearing: p.capacities?.hearing || "full", p }))];
  box.innerHTML = rows.map(r => { const last = state.sessions.find(s => s.pid === r.id || (r.id !== "you" && s.name === r.name)); const n = state.sessions.filter(s => s.pid === r.id).length;
    return `<div class="prow"><div><b>${esc(r.name)}</b>, ${r.age}<small>${esc(tr(L(), "h_" + (r.hearing || "full")))}</small></div><div>${r.words ? `“${esc(r.words)}”` : "—"}</div>
      <div>${last ? `${esc(last.protocol)}<small>${esc(last.carrier.join(", "))}${n > 1 ? ` · ${n}×` : ""}</small>` : `<small>${tr(L(), "no_session")}</small>`}</div>
      <div class="fb ${last && last.feedback ? last.feedback : ""}">${last && last.feedback ? tr(L(), last.feedback === "up" ? "fb_up" : "fb_down") : "—"}</div>
      <div>${r.p ? `<button class="ghost small" data-open="${esc(r.id)}">${tr(L(), "open_studio")}</button>` : ""}</div></div>`; }).join("");
  $$("button[data-open]", box).forEach(b => b.addEventListener("click", () => { const p = state.personas.find(x => x.id === b.dataset.open); if (!p) return; loadPersona(p); try { sessionStorage.setItem("reach.ob", "1"); } catch {} slides.find(s => s.dataset.slide === "app").scrollIntoView({ behavior: "smooth" }); setTimeout(() => compose({ play: true, say: p.sample_request || "" }), 700); }));
}
$("#runcompare").addEventListener("click", async () => {
  const r = state.result; if (!r || r.error) { $("#comparebox").textContent = tr(L(), "compare_hint"); return; }
  const prof = currentProfile(); $("#comparebox").innerHTML = "…";
  try { const c = await (await fetch(`${API}/api/compare`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ profile: prof, goal: r.listener.goal, carrier: r.session.carrier }) })).json();
    if (!c.ok) { $("#comparebox").textContent = c.reason + (c.generic ? ": " + c.generic.join(", ") : ""); return; }
    $("#comparebox").innerHTML = `<div class="cmp"><div><div class="hd">${tr(L(), "without_qloo")} · generic ${esc(c.goal)}</div>${c.generic.map(g => `<div><span>${esc(g.name)}</span><b class="${g.in_top50 ? "" : "no"}">${g.affinity != null ? g.affinity.toFixed(2) : "< " + c.floor_top50.toFixed(2)}</b></div>`).join("")}</div><div><div class="hd">Qloo carrier</div>${c.carrier.map(g => `<div><span>${esc(g.name)}</span><b>${(g.affinity || 0).toFixed(2)}</b></div>`).join("")}</div></div><div class="liftcard"><b>+${c.lift.toFixed(2)}</b> ${tr(L(), "lift")} · ${tr(L(), "mean_aff")} ${c.mean_carrier} vs ${c.mean_generic} · ${c.generic_missing}/${c.generic.length} ${tr(L(), "generic_missing")}</div>`; } catch { $("#comparebox").textContent = "comparison failed"; }
});
$("#verify").addEventListener("click", async () => { const r = state.result; if (!r || !r.ledger) return; const v = await (await fetch(`${API}/api/verify`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ ledger: r.ledger }) })).json(); $("#verdict").innerHTML = `<div class="verdict ${v.ok ? "" : "bad"}">${v.ok ? tr(L(), "verified") + ` · ${v.length}` : tr(L(), "broken") + ` ${v.at}: ${v.reason}`}</div>`; });
$("#tamper").addEventListener("click", () => { const r = state.result; if (!r || !r.ledger || r.ledger.length < 4) return; r.ledger = JSON.parse(JSON.stringify(r.ledger)); const e = r.ledger[3]; e.payload = { ...e.payload, tampered: true }; $("#verdict").innerHTML = `<div class="verdict">step 3 edited locally. Verify.</div>`; });

// ------------------------------------------------------------------ world tour (Earth chapter)
// globe -> the country outlined in red -> dive -> a map with the country filled by the city's
// streets (like Dunyo) -> the city: the author's video vibe for that place, or its street photos
// with a classic of the country -> back up to orbit, find the next country.
let WORLD = null;
async function world() { if (!WORLD) WORLD = fetch("./assets/world.json").then(r => r.json()).catch(() => null); return WORLD; }
function personaMarkers() { return state.personas.map(p => { const c = p.city_coords || CITY[p.city] || [0, 0]; return { lat: c[0], lon: c[1] }; }); }
async function renderTour() {
  if (state.tour.stops.length) return;
  try { const j = await (await fetch(`${API}/api/tour`)).json(); state.tour.stops = j.stops || []; } catch {}
  $("#cities").innerHTML = state.tour.stops.map((c, i) => `<button data-i="${i}">${esc(c.city)}<small>${esc(c.local)}</small></button>`).join("");
}
$("#cities").addEventListener("click", (e) => { const b = e.target.closest("button[data-i]"); if (!b) return; state.tour.auto = false; visitCity(+b.dataset.i); });
$("#tourstart").addEventListener("click", () => { if (state.tour.on && state.tour.auto) stopTour(); else { state.tour.auto = true; visitCity(state.tour.i + 1); } });
$("#addvid").addEventListener("submit", async (e) => { e.preventDefault(); const url = $("#addvidurl").value.trim(); const c = state.tour.stops[state.tour.i]; if (!url || !c) return;
  try { const j = await (await fetch(`${API}/api/tour/media`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ url, city: c.city }) })).json(); toast(j.ok ? `+ ${j.title || url} → ${c.city}` : j.reason); if (j.ok) { $("#addvidurl").value = ""; visitCity(state.tour.i); } } catch {} });
let tourRun = 0;
// the oracle: loading screen. The figure in the film points (his hand is at 64% x 48% of the frame);
// the card sits where he points and a beam runs from his fingertip to it.
const oracle = { on: false, t0: 0 };
function placeOracle() {
  const v = $("#oraclevideo"), r = v.getBoundingClientRect(), card = $("#oraclecard");
  const fx = r.left + 0.64 * r.width * (1 + 0.045 * 0), fy = r.top + 0.48 * r.height, W = window.innerWidth, H = window.innerHeight;
  const cw = card.offsetWidth || 440, ch = card.offsetHeight || 150;
  let x = fx + Math.max(110, W * 0.085), y = fy - ch / 2;
  const beam = fx > 20 && fx < W - 40 && x + cw <= W - 20; $("#oraclebeam").style.display = beam ? "" : "none";
  if (!beam) { x = Math.max(20, (W - cw) / 2); y = H - ch - 40; }
  card.style.left = `${x}px`; card.style.top = `${Math.max(80, Math.min(H - ch - 20, y))}px`;
  const ln = $("#beamline"), tip = $("#beamtip"); const cy = parseFloat(card.style.top) + ch / 2;
  ln.setAttribute("x1", fx + 6); ln.setAttribute("y1", fy); ln.setAttribute("x2", x - 8); ln.setAttribute("y2", cy); tip.setAttribute("cx", fx + 6); tip.setAttribute("cy", fy);
}
function showOracle(c) {
  const o = $("#oracle"); o.hidden = false; oracle.on = true; oracle.t0 = performance.now();
  $("#oraclekicker").textContent = tr(L(), "or_kicker"); $("#oracletitle").textContent = c.local || c.city; $("#oracleline").textContent = `${tr(L(), "tour_loading")} ${c.city} ${tr(L(), "tour_loves")}…`;
  $("#oraclesrc").innerHTML = tr(L(), "or_sources").map((x, i) => `<li data-i="${i}">${esc(x)}</li>`).join("");
  const v = $("#oraclevideo"); if (!v.poster) v.poster = v.dataset.poster; try { v.currentTime = 0; v.play().catch(() => {}); } catch {}
  requestAnimationFrame(() => { placeOracle(); o.classList.add("on"); });
}
async function hideOracle() {
  if (!oracle.on) return; oracle.on = false;
  $$("#oraclesrc li").forEach((li, i) => setTimeout(() => li.classList.add("done"), i * 120));
  const shown = performance.now() - oracle.t0; await wait(Math.max(500, 1100 - shown));       // never a flash
  $("#oracle").classList.remove("on"); setTimeout(() => { if (!oracle.on) { $("#oracle").hidden = true; try { $("#oraclevideo").pause(); } catch {} } }, 650);
}
window.addEventListener("resize", () => { if (oracle.on) placeOracle(); });
// tour data: fetched once per city, the next city prefetched while this one plays
const tourData = new Map();
function fetchCity(c) { if (!tourData.has(c.city)) tourData.set(c.city, fetch(`${API}/api/tour?city=${encodeURIComponent(c.city)}`).then(r => r.json()).catch(() => { tourData.delete(c.city); return null; })); return tourData.get(c.city); }
function tourMap(feature, c, photo) {
  const cv = $("#tourmap"), dpr = Math.min(2, window.devicePixelRatio || 1), W = window.innerWidth, H = window.innerHeight; cv.width = W * dpr; cv.height = H * dpr; const x = cv.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0);
  if (!window.d3 || !feature) return () => {};
  const feats = WORLD_DATA.features; let [[x0, y0], [x1, y1]] = d3.geoBounds(feature); if (x1 < x0 || x1 - x0 > 70) { x0 = c.lon - 12; x1 = c.lon + 12; }
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, sx = Math.max(12, (x1 - x0) * 2.0), sy = Math.max(8, (y1 - y0) * 2.0);
  const box = { type: "MultiPoint", coordinates: [[cx - sx / 2, cy - sy / 2], [cx + sx / 2, cy + sy / 2], [cx - sx / 2, cy + sy / 2], [cx + sx / 2, cy - sy / 2]] };
  const proj = d3.geoMercator().fitExtent([[W * 0.08, H * 0.1], [W * 0.92, H * 0.78]], box), path = d3.geoPath(proj, x);
  const t0 = performance.now(); let raf = 0, alive = true;
  const draw = (now) => { if (!alive) return; const t = (now - t0) / 1000;
    const g = x.createRadialGradient(W / 2, H * 0.45, 40, W / 2, H * 0.45, Math.max(W, H) * 0.7); g.addColorStop(0, "#14223a"); g.addColorStop(1, "#05070d"); x.fillStyle = g; x.fillRect(0, 0, W, H);
    x.beginPath(); feats.forEach(f => { if (f !== feature) path(f); }); x.fillStyle = "#1d2636"; x.fill(); x.strokeStyle = "rgba(237,231,218,.16)"; x.lineWidth = 0.8; x.stroke();
    x.save(); x.beginPath(); path(feature); x.clip(); const b = path.bounds(feature), bw = b[1][0] - b[0][0], bh = b[1][1] - b[0][1];
    if (photo && photo.complete && photo.naturalWidth) { const z = 1.12 + 0.05 * Math.sin(t * 0.25), sc = Math.max(bw / photo.naturalWidth, bh / photo.naturalHeight) * z, dw = photo.naturalWidth * sc, dh = photo.naturalHeight * sc; x.drawImage(photo, b[0][0] - (dw - bw) * (0.5 + 0.3 * Math.sin(t * 0.2)), b[0][1] - (dh - bh) / 2, dw, dh); x.fillStyle = "rgba(255,59,59,.12)"; x.fillRect(b[0][0], b[0][1], bw, bh); }
    else { const gg = x.createLinearGradient(0, b[0][1], 0, b[1][1]); gg.addColorStop(0, "#ff6b6b"); gg.addColorStop(1, "#7a1f2b"); x.fillStyle = gg; x.fillRect(b[0][0], b[0][1], bw, bh); }
    x.restore();
    x.beginPath(); path(feature); x.shadowColor = "rgba(255,59,59,.9)"; x.shadowBlur = 18; x.strokeStyle = "#ff3b3b"; x.lineWidth = 2.4; x.stroke(); x.shadowBlur = 0;
    const [px, py] = proj([c.lon, c.lat]); const ph = (t * 0.9) % 1;
    x.beginPath(); x.arc(px, py, 8 + 22 * ph, 0, 6.283); x.fillStyle = `rgba(255,59,59,${0.45 * (1 - ph)})`; x.fill();
    x.beginPath(); x.arc(px, py, 7, 0, 6.283); x.fillStyle = "#ff3b3b"; x.fill(); x.lineWidth = 2.5; x.strokeStyle = "#fff"; x.stroke();
    x.font = "600 15px IBM Plex Sans, sans-serif"; const label = `${c.local} · ${c.country}`, tw = x.measureText(label).width + 22; let lx = px + 14, ly = py - 40; if (lx + tw > W - 10) lx = px - tw - 14;
    x.fillStyle = "rgba(8,9,16,.88)"; x.beginPath(); x.roundRect(lx, ly, tw, 30, 15); x.fill(); x.fillStyle = "#fff"; x.fillText(label, lx + 11, ly + 20);
    raf = requestAnimationFrame(draw); };
  raf = requestAnimationFrame(draw);
  return () => { alive = false; cancelAnimationFrame(raf); };
}
let WORLD_DATA = null, stopMap = () => {};
function scenePhotos(photos) {
  const box = $("#tourphotos"); box.innerHTML = photos.map((p, i) => `<img src="${esc(p.src)}" alt="${esc(p.title || "")}" referrerpolicy="no-referrer" class="${i === 0 ? "on" : ""}">`).join(""); let i = 0;
  clearInterval(state.tour.photoTimer); if (photos.length > 1) state.tour.photoTimer = setInterval(() => { const imgs = $$("img", box); if (!imgs.length) return; imgs[i].classList.remove("on"); i = (i + 1) % imgs.length; imgs[i].classList.add("on"); }, 7000);
}
function playTourVideo(v, done, song) {
  const sc = $("#tourscene"); sc.classList.add("withvideo"); sc.classList.toggle("vertical", !!v.vertical); $("#ytframe").innerHTML = `<div id="ytbox"></div>`;
  let finished = false; const finish = () => { if (!finished) { finished = true; clearTimeout(state.tour.vtimer); done(); } };
  const mute = !!song;     // the country's song plays over the film; the film's own sound only when there is no song
  if (song) { showSongCard(song); playTour(song, finish); } else state.tour.vtimer = setTimeout(finish, (v.seconds + 6) * 1000);
  loadYTApi().then(YT => { if (!state.tour.on) return; state.tour.ytp = new YT.Player("ytbox", { videoId: v.id, playerVars: { autoplay: 1, controls: 0, modestbranding: 1, rel: 0, playsinline: 1, start: v.start || 0, end: (v.start || 0) + v.seconds, iv_load_policy: 3, disablekb: 1, fs: 0 },
    events: { onReady: (e) => { if (mute) e.target.mute(); else e.target.setVolume(90); e.target.playVideo(); if (!mute) setTimeout(() => { try { if (e.target.getPlayerState() !== 1) { e.target.mute(); e.target.playVideo(); $("#soundbtn").hidden = false; } } catch {} }, 1500); },
      onStateChange: (e) => { if (e.data === 0) { if (mute) { try { e.target.seekTo(v.start || 0); e.target.playVideo(); } catch {} } else finish(); } }, onError: () => fallback() } }); }).catch(() => fallback());
  // the video can't play here (offline, blocked, not embeddable): the city's photos with its classic song instead
  function fallback() { if (finished) return; sc.classList.remove("withvideo", "vertical"); if (!song) { clearTimeout(state.tour.vtimer); state.tour.vtimer = setTimeout(finish, 9000); } }
}
$("#soundbtn").addEventListener("click", () => { const p = state.tour.ytp; if (p) { try { p.unMute(); p.setVolume(90); } catch {} } $("#soundbtn").hidden = true; });
async function visitCity(i) {
  const stops = state.tour.stops; if (!stops.length) return; i = (i + stops.length) % stops.length; const c = stops[i]; const run = ++tourRun;
  const alive = () => run === tourRun && state.tour.on;
  const wasOn = state.tour.on; state.tour.i = i; state.tour.on = true; document.body.classList.add("touring"); $("#tourstart").textContent = tr(L(), state.tour.auto ? "tour_stop" : "tour_start");
  if (player.playing) { player.pause(); setPlayUI(false); } stopYT();
  $$("#cities button").forEach(b => b.setAttribute("aria-current", String(+b.dataset.i === i))); $("#addvid").hidden = false;
  // 1. leave the last city: scene and map fade, camera rises to orbit
  endScene(); if (wasOn) { film.zoomTo(0); await wait(1000); if (!alive()) return; }
  // 2. find the country: turn the globe, red border, pin
  WORLD_DATA = WORLD_DATA || await world(); const feature = WORLD_DATA && WORLD_DATA.features.find(f => f.id === c.iso3);
  film.sets.earth.setMarkers([]); film.sets.earth.face(c.lat, c.lon, true); film.sets.earth.highlight(feature, { lat: c.lat, lon: c.lon });
  const jp = fetchCity(c); let ready = false; jp.then(() => { ready = true; });
  $("#tourcard").hidden = false; $("#tourcard").innerHTML = `<span class="noimg">◎</span><div><div class="city">${esc(c.city)}<small>${esc(c.local)}</small></div><div class="line">${esc(c.country)} · ${tr(L(), "tour_loading")} ${esc(c.city)} ${tr(L(), "tour_loves")}…</div></div>`;
  await wait(1300); if (!alive()) return;
  // 3. dive toward the country
  film.zoomTo(1); await wait(1400); if (!alive()) return;
  if (!ready) showOracle(c);
  const j = await jp; await hideOracle(); if (!alive()) return;
  const photos = (j && j.photos) || [], vid = j && j.videos && j.videos[0], song = j && j.classic, artists = (j && j.artists) || [];
  // 4. the map: the country filled with its own streets, the city pinned
  const img = new Image(); img.referrerPolicy = "no-referrer"; if (photos[0]) img.src = photos[0].src;
  stopMap(); stopMap = tourMap(feature, c, img); $("#tourmap").classList.add("on");
  renderTourCard(c, j, song, vid, artists);
  await wait(2000); if (!alive()) return;
  // 5. into the city
  scenePhotos(photos); $("#scenecity").textContent = c.local; $("#sceneline").textContent = `${c.country} · ${c.line}`;
  $("#scenesong").innerHTML = vid ? `▶ ${esc(vid.title || "")}${vid.author ? ` · ${esc(vid.author)}` : ""}` : "";
  $("#tourscene").classList.add("on"); $("#tourmap").classList.remove("on"); setTimeout(() => { if (run === tourRun) stopMap(); }, 1000);
  const next = () => { if (!alive()) return; if (state.tour.auto) visitCity(i + 1); };
  fetchCity(stops[(i + 1) % stops.length]);           // the next city is ready before it is needed
  if (vid) playTourVideo(vid, next, song);
  else if (song) { showSongCard(song); playTour(song, next); }
  else setTimeout(next, 9000);
}
function showSongCard(song) {
  const sc = $("#songcard"); sc.hidden = false;
  sc.innerHTML = `${song.cover ? `<img src="${esc(song.cover)}" alt="" referrerpolicy="no-referrer">` : `<span class="noimg">♪</span>`}<div><small>${esc(song.because || "")}</small><b>${esc(song.title)}</b><small>${esc(song.artist)}${song.link ? ` · <a href="${esc(song.link)}" target="_blank" rel="noopener">${tr(L(), "full_track")} ↗</a>` : ""}</small></div>`;
}
function renderTourCard(c, j, song, vid, artists) {
  $("#tourcard").innerHTML = `${song && song.cover ? `<img src="${esc(song.cover)}" alt="" referrerpolicy="no-referrer" onerror="this.outerHTML='<span class=noimg>◎</span>'">` : `<span class="noimg">◎</span>`}<div><div class="city">${esc(c.city)}<small>${esc(c.local)} · ${esc(c.country)}</small></div>
    <div class="np">${song ? `♪ ${tr(L(), "tour_classic")} ${esc(c.country)}: <b>${esc(song.artist)}</b> · ${esc(song.title)}` : vid ? `▶ ${tr(L(), "tour_video")}` : tr(L(), "tour_none")}</div>
    ${artists.length ? `<div class="line">${esc(c.city)} ${tr(L(), "tour_now")}:</div><div class="who">${artists.slice(0, 6).map(a => `<span>${a.image ? `<img src="${esc(a.image)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}${esc(a.name)}${a.affinity ? ` <small>${(+a.affinity).toFixed(2)}</small>` : ""}</span>`).join("")}</div>` : ""}</div>`;
}
function playTour(t, done) { stopTourAudio(); if (quiet.on) { setTimeout(done, 9000); return; } const a = new Audio(t.stream || t.preview); a.volume = 0.9; state.tour.audio = a; let fired = false; const once = () => { if (!fired) { fired = true; done(); } }; a.addEventListener("ended", once); a.addEventListener("error", () => setTimeout(once, 1500)); a.play().catch(() => setTimeout(once, 2000)); }
function stopTourAudio() { const a = state.tour.audio; if (a) { try { a.pause(); a.src = ""; } catch {} state.tour.audio = null; } }
function endScene() {
  stopTourAudio(); clearTimeout(state.tour.vtimer); clearInterval(state.tour.photoTimer); if (state.tour.ytp) { try { state.tour.ytp.destroy(); } catch {} state.tour.ytp = null; }
  $("#tourscene").classList.remove("on", "withvideo", "vertical"); $("#ytframe").innerHTML = `<div id="ytbox"></div>`; $("#songcard").hidden = true; $("#soundbtn").hidden = true; $("#tourmap").classList.remove("on"); stopMap(); stopMap = () => {};
}
function stopTour() {
  tourRun++; if (oracle.on) { oracle.on = false; $("#oracle").classList.remove("on"); $("#oracle").hidden = true; } state.tour.on = false; state.tour.auto = false; endScene(); film.zoomTo(0); film.sets.earth.clearHighlight(); film.sets.earth.precise = false; document.body.classList.remove("touring"); $("#tourstart").textContent = tr(L(), "tour_start");
  $$("#cities button").forEach(b => b.removeAttribute("aria-current")); $("#tourcard").hidden = true; $("#addvid").hidden = true; film.sets.earth.setMarkers(personaMarkers());
}

// ------------------------------------------------------------------ guided tour (spoken walkthrough)
// every chapter of the guide opens its own screen, so the timeline can jump anywhere
async function inApp(tab) {
  $("#onboard").hidden = true; if (!profileReady()) demoPersona();
  if (state.slide !== "app") { goSlide("app"); await wait(1100); $("#onboard").hidden = true; }
  if (!state.result) compose({ auto: true });
  if (state.tab !== tab) { openTab(tab); await wait(250); }
}
function demoPersona() { const first = state.personas.find(p => (p.capacities?.hearing || "full") !== "none"); if (first) loadPersona(first); }
const guide = new Guide($("#guide"), {
  lang: L, steps: (l) => tr(l, "guide_steps"),
  // the order chapters are shown in (each keeps its own narration): the opening, then the film of one hand and a face
  order: [0, 2, 3, 1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
  // the film of one hand and a face (the face drawn over): sensors and the mood dial, then likes and dislikes from the thumbs
  media: { 2: "./assets/guide/hands_demo.mp4?v=2", 3: "./assets/guide/hands_demo.mp4?v=2", 11: { src: "./assets/guide/hands_demo.mp4?v=2", at: 10.4 } },
  // her voice alone: every other sound in the app stops while the tour plays, and none can start
  onOpen: () => {
    quiet.on = true; stopAutopilot(); wlMusicStop(true);
    if (player.playing) { player.pause(); setPlayUI(false); }
    if (yt.player) { try { yt.player.pauseVideo(); } catch {} }
    if (visual.on) stopVisual(); if (visual.trailer) { try { visual.trailer.destroy(); } catch {} visual.trailer = null; $("#trailer").hidden = true; }
    closeFreq(); if (state.tour.on) stopTour(); stopTourAudio();
  },
  onClose: () => { quiet.on = false; },
  targets: [
    async () => { goSlide("human"); await wait(700); return { el: null }; },
    async () => { await inApp("me"); return { el: $(".pagepanel[data-panel=me] .page") }; },
    async () => { await inApp("feel"); return { el: $(".camwrap") }; },
    async () => { await inApp("feel"); return { el: $(".dialwrap") }; },
    async () => { await inApp("talk"); return { el: $(".composer") }; },
    async () => { await inApp("talk"); $("#why").classList.add("open"); await wait(450); return { el: $("#trace .ev.taste") || $("#trace") }; },
    async () => { await inApp("talk"); $("#why").classList.add("open"); await wait(300); return { el: $("#trace .ev.compose") || $("#story") }; },
    async () => { await inApp("talk"); $("#why").classList.add("open"); await wait(300); return { el: $("#trace .ev.adjudicate") || $("#trace") }; },
    async () => { await inApp("talk"); $("#why").classList.remove("open"); await wait(450); return { el: $("#hud") }; },
    async () => { await inApp("talk"); $("#why").classList.remove("open"); return { el: $("#srcsel").parentElement }; },
    async () => { await inApp("talk"); $(".finetune").open = true; await wait(200); return { el: $("#genlayer") }; },
    async () => { await inApp("talk"); $(".finetune").open = false; return { el: $("#nowplaying").hidden ? $("#stagecaption") : $("#nowplaying") }; },
    async () => { await inApp("me"); return { el: $("#groupbox") }; },
    async () => { await inApp("watch"); return { el: $(".orbwrap") }; },
    async () => { goSlide("world"); await wait(1200); await renderTour(); return { el: $("#tour") }; },
    async () => { goSlide("clinic"); await wait(1200); return { el: $(".clinic .story3") }; },
  ],
});
$("#guidebtn").addEventListener("click", () => guide.start());
$("#groupgo").addEventListener("click", () => { openTab("talk"); compose({ play: true, say: state.members.length ? "a session for all of us" : "" }); });
$("#intro-guide").addEventListener("click", () => guide.start());

// ------------------------------------------------------------------ status, boot
function renderStatus() { const h = state.health; const el = $("#status"); if (!h) return; el.classList.toggle("fixture", h.mode !== "live"); $("span", el).textContent = h.mode === "live" ? tr(L(), "live_note") + (h.qloo ? ` · ${h.qloo.ms} ms` : "") : tr(L(), "offline_note") + ` · ${h.fixtures}`; }
(async function boot() {
  const q = new URLSearchParams(location.search);
  let lang = q.get("lang") || load("reach.lang", null) || (navigator.language || "en").slice(0, 2); if (!LANGS.some(([l]) => l === lang)) lang = "en";
  if (needsMore(lang)) await loadMore();
  const [pp, pr, health] = await Promise.all([
    fetch(`${API}/api/personas`).then(r => r.json()).catch(() => ({ personas: [] })),
    fetch(`${API}/api/protocols`).then(r => r.json()).catch(() => null),
    fetch(`${API}/api/health`).then(r => r.json()).catch(() => null),
  ]);
  state.personas = pp.personas; state.protocols = pr; state.health = health;
  if (state.source) { state.you = { name: "", age: 30, city: "", hearing: "full", favorites: [] }; state.source = null; saveYou(); }
  film.sets.earth.setMarkers(state.personas.map(p => { const c = p.city_coords || CITY[p.city] || [0, 0]; return { lat: c[0], lon: c[1] }; }));
  applyLang(lang); setSrc(state.you.hearing === "none" ? "visual" : "artists"); if (profileReady()) warmCulture();
  slides[0].classList.add("active"); onScroll();
  // installed as an app: straight into the Studio (or the screen a home-screen shortcut asked for)
  if (q.get("app")) { stopAutopilot(); const go = q.get("go"), tab = q.get("tab"); setTimeout(() => { goSlide(go === "world" ? "world" : go === "clinic" ? "clinic" : "app"); if (tab) openTab(tab); if (go === "sleep" && profileReady()) { openTab("talk"); compose({ play: true, say: "help me sleep" }); } }, 400); }
  if ("serviceWorker" in navigator && location.protocol !== "file:" && !location.hostname.endsWith("claudeusercontent.com")) setTimeout(() => navigator.serviceWorker.register("./sw.js").catch(() => {}), 15000);   // the offline copy downloads after the first screen, never during it
  if (q.get("tour")) { setTimeout(() => guide.start({ render: q.get("render") === "1", at: +(q.get("at") || 0) }), 600); } else if (!q.get("app") && !q.get("film")) { if (q.get("love")) prefillFromLink(q); showWelcome(); } else if (!q.get("app")) startAutopilot();
  renderWelcomeLive();
})();
// ------------------------------------------------------------------ the start page: Reach in one 3D picture
// Eight worlds around a person of light (web/universe.js). Click one to step inside; "Start my session" opens the
// drawer with four choices: what you love, what you need (one, or two for a journey), who is listening, where.
const WL_EXAMPLES = ["Hayedeh", "Shakira", "Jay Chou", "Taylor Swift", "BTS", "Bad Bunny"];
const welcome = $("#welcome");
let uni = null;
const trL = (k) => tr(L(), k);
function showWelcome() {
  if (!welcome) return; welcome.hidden = false; document.body.classList.add("welcoming"); $("#wl-city").value = state.you.city || "";
  renderYou(); renderTries(); cycleAlso(); renderProof(); setWho(state.members.length ? "group" : "me"); renderPeople(); syncGoals(); fillLangSelects();
  if (!uni) uni = initUniverse({ root: welcome, tr: trL, onOpen: openWorld });
  syncMusicBtn(); wlMusicStart();                                   // a browser lets sound start only after a first touch: tried now, then on the first one
  window.__uni = uni;
  uni.start();
}
function hideWelcome() { wlMusicStop(); if (!welcome || welcome.hidden) return; welcome.classList.add("leaving"); document.body.classList.remove("welcoming"); if (uni) { uni.back(); uni.stop(); } clearInterval(alsoTimer); closeDrawer(); setTimeout(() => { welcome.hidden = true; welcome.classList.remove("leaving"); }, 600); }
function openDrawer() { if (uni) uni.back(); $("#wl-drawer").hidden = false; welcome.classList.add("drawer"); setTimeout(() => $("#wl-favinput").focus({ preventScroll: true }), 60); }
function closeDrawer() { const d = $("#wl-drawer"); if (d) d.hidden = true; if (welcome) welcome.classList.remove("drawer"); }
// a world's "Open": that part of the app, with a sample listener if nobody has said what they love yet
function openWorld(go) {
  if (go.judge) { location.href = "./judge"; return; }
  if (go.tab === "talk" && !profileReady()) { openDrawer(); return; }
  obSeen(); state.starting = Date.now(); hideWelcome(); stopAutopilot();
  if (go.slide) { setTimeout(() => goSlide(go.slide), 50); return; }
  const sl = slides.find(x => x.dataset.slide === "app"); if (sl) deck.scrollTop = sl.offsetTop;
  if (!profileReady() && go.tab !== "freq") { const first = state.personas.find(p => (p.capacities?.hearing || "full") !== "none"); if (first) loadPersona(first); }
  setTimeout(() => { openTab(go.tab); if (go.tab === "talk" && !state.result) compose({ play: false }); }, 250);
}
function renderWelcomeLive() {
  const el = $("#wl-live"); if (!el) return; const h = state.health; const live = h && h.mode === "live" && (!h.qloo || h.qloo.status === 200);
  el.className = "wl-live " + (h ? (live ? "on" : "off") : ""); el.querySelector("span").textContent = tr(L(), h ? (live ? "wl_live" : "wl_recorded") : "wl_checking");
}
// one need, or two: the second makes a journey (calm, then sleep; energy, then focus). Shared by the start page and the Studio.
function pickGoal(g) {
  const cur = [state.goal, state.goal2].filter(Boolean); const i = cur.indexOf(g);
  if (i >= 0) cur.splice(i, 1); else if (cur.length >= 2) cur.splice(0, 2, g); else cur.push(g);   // a third pick starts over
  state.goal = cur[0] || null; state.goal2 = cur[1] || null; state.pin = null; syncGoals();
}
function syncGoals() {
  const order = [state.goal, state.goal2];
  for (const sel of ["#wl-goals", "#goals"]) $$(sel + " button[data-goal]").forEach(x => { const k = order.indexOf(x.dataset.goal); x.setAttribute("aria-pressed", String(k >= 0)); if (k >= 0 && state.goal2) x.dataset.order = String(k + 1); else delete x.dataset.order; });
  const txt = state.goal && state.goal2 ? tr(L(), "wl_journey").replace("{a}", tr(L(), "g_" + state.goal)).replace("{b}", tr(L(), "g_" + state.goal2)) : "";
  for (const id of ["#wl-journey", "#journeynote"]) { const el = $(id); if (el) { el.textContent = txt; el.hidden = !txt; } }
}
// "with others": a row per person, a name and who they love (looked up in Qloo on the server); fills state.members
function renderPeople() {
  const box = $("#wl-people"); if (!box) return;
  box.innerHTML = state.members.map((m, i) => `<div class="wl-person"><input class="wl-pname" type="text" data-i="${i}" maxlength="30" value="${esc(m.name === "?" ? "" : m.name)}" placeholder="${esc(tr(L(), "wl_person_name"))}">
    <div class="wl-pfav favadd"><div class="favs">${(m.favorites || []).map((f, j) => favChip(f, j, "m:" + i)).join("")}</div><input class="wl-pfavin" data-i="${i}" type="text" placeholder="${esc(tr(L(), "wl_person_love"))}"><div class="suggest" hidden></div></div>
    <button type="button" class="wl-prm" data-rm="${i}" aria-label="remove">×</button></div>`).join("") + (state.members.length ? `<p class="wl-note">${esc(tr(L(), "wl_people_note"))}</p>` : "");
  $$(".wl-pname", box).forEach(inp => inp.addEventListener("change", () => { const m = state.members[+inp.dataset.i]; if (m) { m.name = inp.value.trim().slice(0, 30) || "?"; save("reach.members", state.members); renderMembers(); } }));
  $$(".wl-pfavin", box).forEach(inp => bindSuggest(inp, inp.nextElementSibling, (f) => { const m = state.members[+inp.dataset.i]; if (!m) return; m.favorites = (m.favorites || []).concat([f]).slice(0, 4); save("reach.members", state.members); renderPeople(); renderMembers(); }));
  $$(".wl-prm", box).forEach(b => b.addEventListener("click", () => { state.members.splice(+b.dataset.rm, 1); save("reach.members", state.members); renderPeople(); renderMembers(); if (!state.members.length) setWho("me"); }));
}
function setWho(who) {
  $$("[data-who]").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.who === who)));
  const group = who === "group"; $("#wl-people").hidden = !group; $("#wl-addperson").hidden = !group;
  if (group && !state.members.length) addPerson(); if (!group && state.members.length) { state.members = []; save("reach.members", []); renderMembers(); renderPeople(); }
}
function addPerson() { if (state.members.length >= 7) return; state.members.push({ name: "?", favorites: [], needs: {} }); save("reach.members", state.members); renderPeople(); renderMembers(); const ins = $$("#wl-people .wl-pname"); if (ins.length) ins[ins.length - 1].focus(); }
// the language picker: every language Reach speaks, in its own name
function fillLangSelects() { $$(".langsel").forEach(sel => { if (!sel.options.length) sel.innerHTML = LANGS.map(([l, n]) => `<option value="${l}">${esc(n)}</option>`).join(""); sel.value = L(); }); }
$$(".langsel").forEach(sel => sel.addEventListener("change", () => setLang(sel.value)));
async function setLang(l) { if (needsMore(l)) await loadMore(); applyLang(l); fillLangSelects(); renderWelcomeLive(); renderTries(); cycleAlso(); renderProof(); renderPeople(); syncGoals(); if (uni) uni.relang(); if (freqInst) freqInst.relang(); }
if (welcome) {
  bindSuggest($("#wl-favinput"), $("#wl-suggest"), addFav);
  $("#wl-examples").addEventListener("click", (e) => { const b = e.target.closest("[data-ex]"); if (b) addFav({ name: b.dataset.ex, type: "artist", entity_id: null }); });
  $("#wl-open-start").addEventListener("click", openDrawer);
  $("#wl-open-freq").addEventListener("click", () => { closeDrawer(); if (uni) uni.open(1); });
  $("#wl-close").addEventListener("click", closeDrawer);
  addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#wl-drawer").hidden) closeDrawer(); });
  $("#wl-goals").addEventListener("click", (e) => { const b = e.target.closest("button[data-goal]"); if (b) pickGoal(b.dataset.goal); });
  $$("[data-who]").forEach(b => b.addEventListener("click", () => setWho(b.dataset.who)));
  $("#wl-addperson").addEventListener("click", addPerson);
  $("#wl-locate").addEventListener("click", () => {
    const btn = $("#wl-locate"), note = $("#wl-locnote");
    if (!navigator.geolocation) { note.textContent = tr(L(), "wl_loc_denied"); note.classList.add("warn"); return; }
    btn.classList.add("busy"); note.classList.remove("warn"); note.textContent = tr(L(), "wl_locating");
    navigator.geolocation.getCurrentPosition(async (pos) => {
      // about 1 km: enough for "a park near you", never enough to find a door (Qloo's safe-use rules: no location data)
      const lat = Math.round(pos.coords.latitude * 100) / 100, lon = Math.round(pos.coords.longitude * 100) / 100;
      state.you.here = [lat, lon]; state.source = null;
      let city = "";
      try { // the city's name, asked with the rounded position
        const j = await (await fetch(`https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${lat.toFixed(2)}&longitude=${lon.toFixed(2)}&localityLanguage=en`)).json();
        city = j.city || j.locality || j.principalSubdivision || "";
      } catch {}
      if (city) { $("#wl-city").value = city; state.you.city = city; }
      saveYou(); btn.classList.remove("busy"); btn.classList.add("done"); note.textContent = tr(L(), "wl_loc_note");
    }, () => { btn.classList.remove("busy"); note.textContent = tr(L(), "wl_loc_denied"); note.classList.add("warn"); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 });
  });
  $("#wl-city").addEventListener("change", () => { const c = $("#wl-city").value.trim().slice(0, 40); if (c !== state.you.city) { state.you.city = c; state.you.here = null; $("#wl-locate").classList.remove("done"); state.source = null; saveYou(); } });
  $("#wl-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const typed = $("#wl-favinput").value.trim(); if (typed) { addFav({ name: typed, type: "artist", entity_id: null }); $("#wl-favinput").value = ""; }
    if (!profileReady()) { openDrawer(); $("#wl-favinput").focus(); $("#wl-favinput").placeholder = tr(L(), "wl_need_fav"); return; }
    state.you.city = $("#wl-city").value.trim().slice(0, 40); state.source = null; saveYou(); obSeen();
    player.warm().catch(() => {});                       // inside the click: browsers allow sound to start
    // people with a name or a favourite count; empty rows are dropped
    state.members = state.members.filter(m => (m.name && m.name !== "?") || (m.favorites || []).length).map((m, i) => ({ ...m, name: m.name && m.name !== "?" ? m.name : `${tr(L(), "wl_person_name")} ${i + 1}` }));
    save("reach.members", state.members); renderMembers();
    const group = state.members.length > 0;
    state.starting = Date.now(); hideWelcome(); stopAutopilot();
    const sl = slides.find(x => x.dataset.slide === "app"); if (sl) deck.scrollTop = sl.offsetTop;
    openTab("talk");
    setTimeout(() => { if (group) { addMsg("me", state.members.map(m => m.name).join(", ")); compose({ play: true, say: "a session for all of us" }); } else compose({ play: true }); }, 250);
  });
  $("#wl-demo").addEventListener("click", () => { obSeen(); state.starting = Date.now(); hideWelcome(); stopAutopilot(); const sl = slides.find(x => x.dataset.slide === "app"); if (sl) deck.scrollTop = sl.offsetTop; openTab("talk");
    const first = state.personas.find(p => (p.capacities?.hearing || "full") !== "none"); if (first) loadPersona(first); setTimeout(() => compose({ play: true }), 250); });
  $("#wl-film").addEventListener("click", () => { hideWelcome(); deck.scrollTop = 0; startAutopilot(); });
  $("#wl-tour").addEventListener("click", (e) => { e.stopPropagation(); quiet.on = true; wlMusicStop(true); obSeen(); state.starting = Date.now(); hideWelcome(); stopAutopilot(); guide.start(); });
  fillLangSelects();
}
// a link from an assistant (MCP "open_in_app") or a shared link: /?love=Hayedeh|Googoosh&need=sleep&then=calm&city=Los Angeles&lang=fa
function prefillFromLink(q) {
  const names = String(q.get("love") || "").split("|").map(x => x.trim().slice(0, 80)).filter(Boolean).slice(0, 8);
  if (names.length) { state.you.favorites = names.map(n => ({ name: n, type: "artist", entity_id: null })); state.source = null; }
  const G = ["sleep", "calm", "focus", "mood", "memory", "energy"], need = q.get("need"), then = q.get("then");
  if (G.includes(need)) { state.goal = need; state.goal2 = G.includes(then) && then !== need ? then : null; setTimeout(syncGoals, 0); }
  const city = q.get("city"); if (city) { state.you.city = city.slice(0, 40); state.you.here = null; }
  const lg = q.get("lang"); if (LANGS.some(([l]) => l === lg)) setTimeout(() => setLang(lg), 0);
  saveYou(); renderYou();
}
// one-tap tries: a favourite and a need, straight into a session
const WL_TRIES = [["Hayedeh", "sleep", "wl_try_sleep"], ["Jay Chou", "calm", "wl_try_calm"], ["Shakira", "mood", "wl_try_mood"], ["Vicente Fernández", "memory", "wl_try_memory"]];
function renderTries() {
  const box = $("#wl-tries"); if (!box) return;
  box.innerHTML = WL_TRIES.map(([n, g, k], i) => `<button type="button" data-try="${i}"><b>${esc(n)}</b><span>${esc(tr(L(), k))}</span></button>`).join("");
}
if (welcome) $("#wl-tries").addEventListener("click", (e) => { const b = e.target.closest("[data-try]"); if (!b) return; const [n, g] = WL_TRIES[+b.dataset.try];
  state.you.favorites = [{ name: n, type: "artist", entity_id: null }]; state.source = null; state.goal = g; state.goal2 = null; saveYou(); renderYou(); syncGoals();
  if (state.members.length) { state.members = []; save("reach.members", []); renderMembers(); }
  $("#wl-form").requestSubmit(); });
// the headline in the other languages, one at a time, under the one you read
let alsoTimer = null;
function cycleAlso() {
  const el = $("#wl-also"); if (!el) return; clearInterval(alsoTimer);
  const head = (l) => (STRINGS[l] && STRINGS[l].wl_title) || TITLES[l] || tr(l, "wl_title");
  const others = LANGS.map(([l]) => l).filter(l => l !== L()); let i = 0;
  if (!others.length) { el.textContent = ""; return; }
  const show = () => { const l = others[i++ % others.length]; el.classList.remove("in"); setTimeout(() => { el.textContent = head(l); el.lang = l; el.dir = RTL.has(l) ? "rtl" : "ltr"; el.classList.add("in"); }, reduceMotion ? 0 : 380); };
  show(); if (!reduceMotion) alsoTimer = setInterval(show, 2600);
}
// the proof, from the comparison this server last ran (scripts/bench.py); hidden until there is one
async function renderProof() {
  const el = $("#wl-proof"); if (!el) return;
  try { const b = await (await fetch(`${API}/api/bench`)).json(); const S = b.systems || {};
    if (!b.ran || !S.llm || !S.reach || S.llm.exists == null || S.reach.culture == null) { el.hidden = true; return; }
    el.textContent = tr(L(), "wl_proof").replace("{m}", String(b.llm || "LLM").replace(/^ollama:/, "")).replace("{x}", Math.round(S.llm.exists * 100)).replace("{c}", Math.round(S.reach.culture * 100));
    el.hidden = false; } catch { el.hidden = true; }
}
// the start page's music: Bach, Prelude in C (public domain, recorded for Reach), soft and looping without a gap.
// It starts with the first touch on the page (browsers allow no sound before one), stops when the person leaves
// the start page or plays a frequency, and the Music switch turns it off (remembered).
const wlMusic = { ctx: null, buf: null, src: null, gain: null, on: load("reach.wlmusic", true), playing: false, loading: false };
async function wlMusicStart() {
  if (quiet.on || !wlMusic.on || wlMusic.playing || wlMusic.loading || !welcome || welcome.hidden) return;
  wlMusic.loading = true; wlMusic.cancel = false;
  try {
    wlMusic.ctx = wlMusic.ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (wlMusic.ctx.state === "suspended") await wlMusic.ctx.resume().catch(() => {});
    if (wlMusic.ctx.state !== "running") return;
    if (!wlMusic.buf) wlMusic.buf = await wlMusic.ctx.decodeAudioData(await (await fetch("./assets/music/prelude_loop.mp3")).arrayBuffer());
    if (!wlMusic.on || welcome.hidden || wlMusic.playing || wlMusic.cancel) return;
    const g = wlMusic.ctx.createGain(); g.gain.value = 0; g.connect(wlMusic.ctx.destination);
    const s = wlMusic.ctx.createBufferSource(); s.buffer = wlMusic.buf; s.loop = true; s.connect(g); s.start();
    g.gain.setTargetAtTime(0.3, wlMusic.ctx.currentTime, 1.0);
    Object.assign(wlMusic, { src: s, gain: g, playing: true }); syncMusicBtn();
  } catch {} finally { wlMusic.loading = false; }
}
function wlMusicStop(fast) {
  if (wlMusic.loading) wlMusic.cancel = true;
  if (!wlMusic.playing) return; const { ctx, gain, src } = wlMusic; wlMusic.playing = false;
  try { gain.gain.setTargetAtTime(0, ctx.currentTime, fast ? 0.08 : 0.45); src.stop(ctx.currentTime + (fast ? 0.5 : 2.4)); } catch {}
  syncMusicBtn();
}
function syncMusicBtn() { const b = $("#wl-sound"); if (b) { b.setAttribute("aria-pressed", String(wlMusic.on)); b.classList.toggle("live", wlMusic.playing); } }
if (welcome) {
  $("#wl-sound").addEventListener("click", (e) => { e.stopPropagation(); wlMusic.on = !(wlMusic.on && (wlMusic.playing || wlMusic.loading)); if (!wlMusic.on) wlMusicStop(true); save("reach.wlmusic", wlMusic.on); syncMusicBtn(); if (wlMusic.on) wlMusicStart(); });
  const first = (e) => { if (e.target.closest && e.target.closest("#wl-sound, #wl-tour, #wl-open-freq, .fq, .ul[data-w='1']")) return; wlMusicStart(); };
  welcome.addEventListener("pointerdown", first, true); welcome.addEventListener("keydown", first, true);
  // a frequency is its own sound: the music makes way for it
  welcome.addEventListener("click", (e) => { if (e.target.closest(".fq-play, .fq-bands [data-band], #wl-open-freq")) wlMusicStop(true); }, true);
}
// the Reach logo: back to the start page from anywhere
function goHome(e) {
  if (e) e.preventDefault();
  stopAutopilot(); if (player.playing) { player.pause(); setPlayUI(false); } stopYT(); if (visual.on) stopVisual(); if (state.tour.on) stopTour();
  closeFreq(); if (afterView) afterView.close(); if (document.body.classList.contains("platemode")) plateMode(false);
  try { history.replaceState(null, "", location.pathname); } catch {}
  if (welcome.hidden) showWelcome(); else { if (uni) uni.back(); closeDrawer(); wlMusicStart(); }
  welcome.scrollTop = 0; deck.scrollTop = 0;
}
$$(".homelink").forEach(a => a.addEventListener("click", goHome));

// the Frequencies tab: the instrument, full size (web/instrument.js). Playing it pauses the session, never both at once.
let freqInst = null;
function openFreq() {
  if (!freqInst) { const box = $("#freqinst"); freqInst = createInstrument(box, { tr: trL });
    box.addEventListener("click", (e) => { if (e.target.closest(".fq-play, [data-band]") && (player.playing || yt.on)) { if (player.playing) player.pause(); stopYT(); setPlayUI(false); } }, true); }
  freqInst.start();
}
function closeFreq() { if (freqInst) { freqInst.stop(); freqInst.pause(); } }

// Forget me (About me): everything Reach saved in this browser, gone
$("#forgetme").addEventListener("click", () => { if (!confirmForget()) return; try { Object.keys(localStorage).filter(k => k.startsWith("reach.")).forEach(k => localStorage.removeItem(k)); Object.keys(sessionStorage).filter(k => k.startsWith("reach.")).forEach(k => sessionStorage.removeItem(k)); } catch {} location.href = "./"; });
function confirmForget() { const b = $("#forgetme"); if (b.dataset.armed) return true; b.dataset.armed = "1"; b.textContent = tr(L(), "forget_sure"); setTimeout(() => { delete b.dataset.armed; b.textContent = tr(L(), "forget_me"); }, 4000); return false; }

window.__reach = { wlMusic, state, film, player, stopAutopilot, compose, loadPersona, guide, visitCity, stopTour, showOracle, hideOracle };
