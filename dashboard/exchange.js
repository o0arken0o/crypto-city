// Shared "exchange" look of the 3D rooms (office.html = trading, sales.html = rendite): a dark corner room with a
// glowing floor grid, chart screens, agent desks along the walls, a glass cabinet of coins and glass HUD panels.
// Each page adds its own centre piece and maps its api/live data onto the panels. No data is ever invented here:
// the numbers come from api/live (or ?demo=1 sample data, marked "demo").
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { postfx, firstSaleParty } from "./scene3d.js";
import { drawRealCandles } from "./charts.js";

export { THREE };
export const BLUE = 0x3aa0ff, CYAN = 0x4fd2ff, GREEN = 0x2fd59b, RED = 0xff4d6a, GOLD = 0xffc35a;
export const $ = s => document.querySelector(s);
export const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const eur = v => v == null ? "—" : Number(v).toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
export const DEMO = new URLSearchParams(location.search).has("demo");
export const seeded = s => () => (s = s * 16807 % 2147483647) / 2147483647;
export const glow = c => new THREE.MeshBasicMaterial({ color: new THREE.Color(c).multiplyScalar(1.9), toneMapped: false });  // HDR: only these bloom
export function canvasTex(w, h, draw) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4; t.userData.canvas = c; return t;
}
export function label(text, cls = "lbl") { const el = document.createElement("div"); el.className = cls; el.textContent = text; return new CSS2DObject(el); }
const hex = c => "#" + c.toString(16).padStart(6, "0");

// a person built from simple shapes: face (eyes that blink, brows, nose, mouth, ears), one of six hair styles,
// jacket in the agent's colour, shirt collar, arms with hands, legs with shoes. Faces -z; joints are groups so
// the room can pose it (sitting, typing, walking, talking, cheering).
const SKINS = [0xf1c9a5, 0xe0ac85, 0xc68b62, 0x8d5a3b, 0xf3d2b8, 0xb47a55];
const HAIRS = [0x1b1410, 0x3b2616, 0x6b4423, 0xb58b52, 0x2a2a2e, 0x9a9a9a, 0x7a2e1a];
const IRIS = [0x3b2a1a, 0x2d5a8c, 0x3c6b3a, 0x5a3b22, 0x4a5a6a];
const PANTS = [0x1a2233, 0x2b2f38, 0x23324d, 0x3a3328, 0x202020];
function person(color, seed) {
  const r = seeded(seed * 9973 + 17); r(); r();
  const pick = a => a[Math.floor(r() * a.length)];
  const std = (c, ro = .6, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: ro, ...o });
  const skinC = new THREE.Color(pick(SKINS));
  const skin = std(skinC, .55), hairM = std(pick(HAIRS), .75), suit = std(color, .5, { metalness: .15, emissive: color, emissiveIntensity: .06 });
  const shirt = std(0xeef2f8), pants = std(pick(PANTS), .7), shoeM = std(0x0e1014, .35, { metalness: .3 });
  const white = std(0xffffff, .25), iris = std(pick(IRIS), .3), black = std(0x050505, .2);
  const lip = std(skinC.clone().lerp(new THREE.Color(0xa0384a), .45), .5), frameM = std(0x15181f, .3, { metalness: .6 });
  const M = (geo, mat, parent, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(geo, mat); m.position.set(x, y, z); parent.add(m); return m; };
  const G = (parent, x = 0, y = 0, z = 0) => { const o = new THREE.Group(); o.position.set(x, y, z); parent.add(o); return o; };
  const female = r() < .45, slim = female ? .88 : 1;
  const root = new THREE.Group(), suitMeshes = [];
  const pelvis = G(root, 0, .915, 0);
  M(new THREE.SphereGeometry(.15, 18, 12), pants, pelvis).scale.set(1.05 * slim, .62, .78);
  const spine = G(pelvis, 0, .05, 0);
  const torso = M(new THREE.CapsuleGeometry(.15, .26, 6, 18), suit, spine, 0, .25, 0); torso.scale.set(1.18 * slim, 1, .74); suitMeshes.push(torso);
  M(new THREE.CylinderGeometry(.075, .02, .16, 3), shirt, spine, 0, .46, -.09).rotation.set(-.25, Math.PI, 0);   // shirt V
  M(new THREE.SphereGeometry(.045, 10, 8), suit, spine, .045, .42, -.1).scale.set(.6, 1.4, .3); M(new THREE.SphereGeometry(.045, 10, 8), suit, spine, -.045, .42, -.1).scale.set(.6, 1.4, .3); // lapels
  if (!female && r() < .6) M(new THREE.BoxGeometry(.035, .16, .012), std(new THREE.Color(color).multiplyScalar(.45), .5), spine, 0, .35, -.115);  // tie
  M(new THREE.CylinderGeometry(.048, .055, .1, 14), skin, spine, 0, .56, 0);
  const head = G(spine, 0, .6, 0), face = G(head, 0, .12, 0);
  M(new THREE.SphereGeometry(.12, 28, 20), skin, face).scale.set(.94 * (female ? .96 : 1), 1.12, 1.02);
  M(new THREE.SphereGeometry(.07, 16, 10), skin, face, 0, -.075, -.03).scale.set(1.15, .8, 1.15);                // jaw/chin
  const eyes = [];
  for (const s of [-1, 1]) {
    const e = G(face, s * .043, .018, -.098); eyes.push(e);
    M(new THREE.SphereGeometry(.021, 14, 10), white, e).scale.set(1.1, .85, .55);
    M(new THREE.SphereGeometry(.012, 12, 8), iris, e, 0, 0, -.009).scale.set(1, 1, .5);
    M(new THREE.SphereGeometry(.006, 8, 6), black, e, 0, 0, -.0145);
    M(new THREE.SphereGeometry(.0025, 6, 4), white, e, .004 * s, .004, -.0175);                                   // glint
    const brow = M(new THREE.BoxGeometry(.046, .009, .012), hairM, face, s * .045, .052, -.105); brow.rotation.z = -s * .12;
    M(new THREE.SphereGeometry(.028, 10, 8), skin, face, s * .114, .005, .005).scale.set(.45, 1, .75);              // ear
  }
  const nose = M(new THREE.ConeGeometry(.017, .055, 10), skin, face, 0, -.005, -.118); nose.rotation.x = -Math.PI / 2 - .35;
  M(new THREE.SphereGeometry(.016, 10, 8), skin, face, 0, -.022, -.131);
  const mouth = M(new THREE.TorusGeometry(.024, .0065, 6, 14, Math.PI), lip, face, 0, -.055, -.108); mouth.rotation.z = Math.PI;
  if (r() < .3) {                                                                                                    // glasses
    for (const s of [-1, 1]) M(new THREE.TorusGeometry(.026, .0035, 6, 18), frameM, face, s * .044, .018, -.122);
    M(new THREE.BoxGeometry(.03, .004, .004), frameM, face, 0, .022, -.124);
  }
  const cap = (tl, sc = 1.04) => { const h = M(new THREE.SphereGeometry(.12, 26, 16, 0, Math.PI * 2, 0, Math.PI * tl), hairM, face, 0, .006, .006); h.scale.set(.96 * sc, 1.12 * sc, 1.04 * sc); return h; };
  const backHair = tl => { const h = M(new THREE.SphereGeometry(.122, 22, 14, 0, Math.PI, 0, Math.PI * tl), hairM, face, 0, .004, .01); h.scale.set(1.0, 1.13, 1.06); return h; };
  const style = female ? pick([1, 1, 2, 4, 5]) : pick([0, 0, 3, 4, 5]);
  if (style === 0) { cap(.42); backHair(.62); }                                                                    // short
  if (style === 1) {                                                                                                // long
    cap(.45, 1.06); backHair(.8).scale.set(1.08, 1.2, 1.12);
    const fall = M(new THREE.CapsuleGeometry(.1, .2, 4, 14), hairM, face, 0, -.14, .06); fall.scale.set(1.25, 1, .5);
    for (const s of [-1, 1]) M(new THREE.CapsuleGeometry(.03, .16, 4, 8), hairM, face, s * .108, -.08, -.02);
  }
  if (style === 2) { cap(.45, 1.05); backHair(.66); M(new THREE.SphereGeometry(.06, 14, 10), hairM, face, 0, .1, .1); }    // bun
  if (style === 3) {                                                                                                // buzz + beard
    cap(.36, 1.02); backHair(.55);
    const beard = M(new THREE.SphereGeometry(.124, 22, 14, Math.PI, Math.PI, Math.PI * .56, Math.PI * .34), hairM, face, 0, -.006, -.002); beard.scale.set(.98, 1.12, 1.05);
    M(new THREE.BoxGeometry(.06, .012, .015), hairM, face, 0, -.04, -.118);                                          // moustache
  }
  if (style === 4) { cap(.4); backHair(.6); for (let k = 0; k < 11; k++) { const a = k / 11 * Math.PI * 2;                // curly
    M(new THREE.SphereGeometry(.045, 10, 8), hairM, face, Math.cos(a) * .09, .085 + Math.sin(k * 2.3) * .02, Math.sin(a) * .085 + .01); } M(new THREE.SphereGeometry(.07, 12, 10), hairM, face, 0, .13, .01); }
  if (style === 5) { cap(.42); backHair(.64); const q = M(new THREE.CapsuleGeometry(.04, .1, 4, 10), hairM, face, .02, .115, -.07); q.rotation.set(.9, 0, Math.PI / 2 + .3); } // quiff
  const limb = (side, x, y, upper, lower, end, matU, matL) => {
    const a = G(side === "arm" ? spine : pelvis, x, y, 0);
    const u = M(new THREE.CapsuleGeometry(upper[0], upper[1], 4, 12), matU, a, 0, -upper[1] / 2 - .02, 0);
    const j = G(a, 0, -upper[1] - upper[0] * 1.2, 0);
    const l = M(new THREE.CapsuleGeometry(lower[0], lower[1], 4, 12), matL, j, 0, -lower[1] / 2 - .02, 0);
    end(j, -lower[1] - lower[0] * 1.6); return { a, j, u, l };
  };
  const arms = [-1, 1].map(s => { const L = limb("arm", s * .2 * slim, .43, [.052, .24], [.045, .2], (j, y) => {
    M(new THREE.CylinderGeometry(.048, .048, .03, 12), shirt, j, 0, y + .055, 0);                                    // cuff
    const h = M(new THREE.SphereGeometry(.05, 12, 10), skin, j, 0, y + .01, -.005); h.scale.set(.75, 1.15, .55);
    M(new THREE.CapsuleGeometry(.014, .03, 3, 6), skin, j, -s * .03, y + .02, -.02).rotation.z = s * .5;               // thumb
  }, suit, suit); suitMeshes.push(L.u, L.l); L.s = s; return L; });
  const legs = [-1, 1].map(s => { const L = limb("leg", s * .085, -.02, [.07, .36], [.058, .36], (j, y) => {
    M(new THREE.BoxGeometry(.1, .07, .24), shoeM, j, 0, y + .035, -.045);
    M(new THREE.SphereGeometry(.05, 10, 8), shoeM, j, 0, y + .035, -.16).scale.set(1, .7, .8);
  }, pants, pants); L.s = s; return L; });
  return { root, pelvis, spine, head, face, eyes, mouth, arms, legs, suit, suitMeshes };
}

// decorative candlestick chart (seeded, never presented as real prices)
export function candles(g, w, h, seed, title, accent = "#3aa0ff") {
  const r = seeded(seed);
  g.fillStyle = "#030918"; g.fillRect(0, 0, w, h);
  g.strokeStyle = "rgba(80,150,255,.12)"; g.lineWidth = 1;
  for (let y = 60; y < h; y += 50) { g.beginPath(); g.moveTo(0, y); g.lineTo(w, y); g.stroke(); }
  for (let x = 0; x < w; x += 70) { g.beginPath(); g.moveTo(x, 50); g.lineTo(x, h); g.stroke(); }
  let p = h * .65; const pts = [];
  for (let x = 24; x < w - 24; x += 13) {
    const o = p, c = Math.max(90, Math.min(h - 50, p + (r() - .56) * 40)), hi = Math.min(o, c) - r() * 16, lo = Math.max(o, c) + r() * 16;
    g.strokeStyle = g.fillStyle = c < o ? "#2fd59b" : "#ff4d6a";
    g.beginPath(); g.moveTo(x + 4, hi); g.lineTo(x + 4, lo); g.stroke(); g.fillRect(x, Math.min(o, c), 8, Math.max(2, Math.abs(c - o)));
    pts.push([x + 4, c]); p = c;
  }
  g.strokeStyle = accent; g.lineWidth = 3; g.shadowColor = accent; g.shadowBlur = 14; g.beginPath();
  pts.forEach(([x], i) => { const a = pts.slice(Math.max(0, i - 8), i + 1), m = a.reduce((t, q) => t + q[1], 0) / a.length; i ? g.lineTo(x, m) : g.moveTo(x, m); });
  g.stroke(); g.shadowBlur = 0;
  g.fillStyle = "#cfe3ff"; g.font = "600 28px Chakra Petch, sans-serif"; g.fillText(title, 22, 38);
}

const CSS = `
:root{color-scheme:dark;--night:#040915;--glass:rgba(8,20,46,.62);--edge:rgba(86,160,255,.35);--glow:#3aa0ff;--text:#e6efff;--muted:#8ea3c8;--good:#2fd59b;--bad:#ff4d6a;--amber:#ffb020;
  --hud:"Chakra Petch","Trebuchet MS",system-ui,sans-serif;--body:"Nunito Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}[hidden]{display:none!important}
html,body{margin:0;height:100%;overflow:hidden;background:var(--night);color:var(--text);font:14px/1.4 var(--body)}
#gl{position:fixed;inset:0}#gl canvas{display:block}
.glass{position:fixed;z-index:5;background:var(--glass);border:1px solid var(--edge);border-radius:14px;box-shadow:0 0 0 1px rgba(58,160,255,.06),0 10px 34px rgba(0,25,80,.5),inset 0 1px 0 rgba(150,200,255,.15);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
.glass h2{font:600 12px var(--hud);letter-spacing:.12em;text-transform:uppercase;color:var(--glow);margin:0 0 8px;text-shadow:0 0 10px rgba(58,160,255,.6)}
#nav{top:calc(10px + env(safe-area-inset-top,0px));right:12px;display:flex;gap:14px;align-items:center;padding:7px 14px;font:600 13px var(--hud)}
#nav a{color:var(--muted);text-decoration:none}#nav a:hover{color:var(--text)}
#side{top:calc(10px + env(safe-area-inset-top,0px));left:12px;width:250px;padding:14px 16px}
#side h1{font:700 17px var(--hud);letter-spacing:.08em;margin:0 0 2px;color:var(--glow);text-shadow:0 0 12px rgba(58,160,255,.7)}
#side .sub{font:600 11px var(--hud);letter-spacing:.1em;color:var(--muted);text-transform:uppercase;margin-bottom:12px}
.kv{border-top:1px solid rgba(86,160,255,.18);padding:9px 0}
.kv span{display:block;font:600 11px var(--hud);letter-spacing:.06em;color:var(--muted);text-transform:uppercase}
.kv b{font:700 19px var(--hud);font-variant-numeric:tabular-nums}
.bar{height:5px;border-radius:9px;background:rgba(86,160,255,.15);margin-top:6px;overflow:hidden}
.bar i{display:block;height:100%;width:0;background:linear-gradient(90deg,#1f6fff,#4fc3ff);box-shadow:0 0 10px #3aa0ff;transition:width .6s}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:99px;font:600 11px var(--hud);letter-spacing:.05em;background:rgba(86,160,255,.12);color:var(--muted)}
.pill i{width:7px;height:7px;border-radius:50%;background:currentColor}
.pill.working{color:var(--good)}.pill.working i{animation:blink 1s infinite}.pill.starting{color:var(--amber)}.pill.paused{color:var(--bad)}
@keyframes blink{50%{opacity:.25}}
button.go{width:100%;margin-top:10px;font:700 13px var(--hud);letter-spacing:.08em;text-transform:uppercase;color:#031022;border:0;border-radius:10px;padding:10px;cursor:pointer;background:linear-gradient(180deg,#5cc2ff,#1f7bff);box-shadow:0 0 18px rgba(58,160,255,.55)}
button.go:hover{filter:brightness(1.1)}button.go:disabled{opacity:.5;cursor:default}
#feed{right:12px;top:calc(58px + env(safe-area-inset-top,0px));width:min(330px,calc(100vw - 24px));max-height:34vh;overflow:auto;padding:12px 14px}
#feed div.e{padding:4px 0;border-bottom:1px dashed rgba(86,160,255,.18);font-size:12px}
#report{right:12px;bottom:calc(12px + env(safe-area-inset-bottom,0px));width:min(330px,calc(100vw - 24px));padding:12px 14px}
#report .h{font-weight:700}
#card{left:12px;bottom:calc(12px + env(safe-area-inset-bottom,0px));width:min(300px,calc(100vw - 24px));max-height:46vh;overflow:auto;padding:12px 14px}
#card h3{font:700 15px var(--hud);color:var(--glow);margin:0 0 6px}
#card dl{display:grid;grid-template-columns:auto 1fr;gap:3px 10px;margin:6px 0 0;font-size:13px}
#card dt{color:var(--muted)}#card dd{margin:0}
.muted{color:var(--muted)}.small{font-size:12px}
.lbl{font:600 11px var(--hud);letter-spacing:.04em;color:#dfeaff;background:rgba(4,12,30,.82);border:1px solid rgba(86,160,255,.4);padding:2px 8px;border-radius:99px;white-space:nowrap}
.lbl.off{opacity:.55}
.say{max-width:180px;font-size:11.5px;line-height:1.3;color:#e8f2ff;background:rgba(20,70,160,.85);border:1px solid #4fb3ff;border-radius:9px;padding:4px 8px;box-shadow:0 0 14px rgba(58,160,255,.5)}
.say.chat{background:rgba(240,246,255,.95);color:#0a1830;border-color:#cfe3ff;box-shadow:0 0 12px rgba(200,225,255,.35)}
.say.done{background:rgba(10,90,70,.85);border-color:#2fd59b;box-shadow:0 0 14px rgba(47,213,155,.4)}
@media (max-width:760px){#side{width:auto;right:12px;padding:10px 12px}#side .kv{display:inline-block;width:48%;border:0;padding:4px 0}#side .kv b{font-size:15px}
  #feed{display:none}#nav{top:auto;bottom:calc(12px + env(safe-area-inset-bottom,0px));right:12px}#report{display:none}.say{max-width:120px;font-size:10.5px}.lbl{font-size:10px}}`;

// The whole room. opts: { team, title, sub, agents: [[key, name, colour]], spots: [[x, z, yaw]], cron: [min, [hours UTC]],
// kv: [[id, label, withBar]], nav: [[href, text]], reportTitle, cabinet: true }
export function createRoom(opts) {
  const { team, sub, agents, spots, cron, kv, nav, reportTitle } = opts;
  document.head.insertAdjacentHTML("beforeend", `<style>${CSS}</style>`);
  document.body.insertAdjacentHTML("beforeend", `
<div id="gl"></div>
<div id="side" class="glass"><h1>CRYPTO MACHINE</h1><div class="sub">${esc(sub)} · <span id="phase" class="pill"><i></i><span>…</span></span></div>
  ${kv.map(([id, t, bar]) => `<div class="kv"><span>${esc(t)}</span><b id="${id}">—</b>${bar ? `<div class="bar"><i id="${id}Bar"></i></div>` : ""}</div>`).join("")}
  <button class="go" id="runBtn">▶ Avvia ciclo</button><div class="small muted" id="next" style="margin-top:8px"></div></div>
<div id="nav" class="glass"><span id="demoTag" class="pill" hidden>demo</span>${nav.map(([h, t]) => `<a href="${h}">${esc(t)}</a>`).join("")}</div>
<div id="feed" class="glass"><h2>Cosa succede</h2><div id="events"></div></div>
<div id="report" class="glass"><h2>${esc(reportTitle)}</h2><div class="h" id="repH">—</div><div class="small muted" id="repM"></div></div>
<div id="card" class="glass" hidden></div>`);

  // renderer, camera, light
  const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.5));
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.35;
  $("#gl").appendChild(renderer.domElement);
  const labels = new CSS2DRenderer();
  Object.assign(labels.domElement.style, { position: "absolute", inset: "0", pointerEvents: "none" });
  $("#gl").appendChild(labels.domElement);
  const scene = new THREE.Scene(); scene.background = new THREE.Color(0x040915); scene.fog = new THREE.Fog(0x040915, 45, 90);
  const camera = new THREE.PerspectiveCamera(38, 1, .1, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(.6, 1.2, -.6); controls.enableDamping = true; controls.enablePan = false;
  controls.minDistance = 10; controls.maxDistance = 48; controls.maxPolarAngle = Math.PI * .45;
  camera.position.set(17, 16, 19);
  {  // ?cam=x,y,z,tx,ty,tz: open the room on a given view (handy to share a wall)
    const c = (new URLSearchParams(location.search).get("cam") || "").split(",").map(Number);
    if (c.length === 6 && c.every(Number.isFinite)) { camera.position.set(c[0], c[1], c[2]); controls.target.set(c[3], c[4], c[5]); controls.minDistance = 1; }
  }
  scene.add(new THREE.HemisphereLight(0x8fbcff, 0x0a1430, 1.1), new THREE.AmbientLight(0x6f8fd0, .35));
  const key = new THREE.DirectionalLight(0xd6e6ff, .9); key.position.set(8, 18, 10); scene.add(key);

  // live charts: every chart screen and desk monitor draws real candles from api/candles, refreshed every minute
  const tokenHdr = () => { try { const t = localStorage.getItem("mm-token"); return t ? { "X-MM-Token": t } : {}; } catch (e) { return {}; } };
  const charts = [], chartData = {}, extraPairs = [];  // extraPairs: "XRP-EUR|1h" fetched even without a chart on screen
  function liveChart(cw, ch, pair, tf, title, accent = "#3aa0ff") {
    const tex = canvasTex(cw, ch, () => {}), c = { tex, pair, tf, title, accent };
    c.draw = () => {
      const g = tex.userData.canvas.getContext("2d");
      if (DEMO) candles(g, cw, ch, (pair + tf).length * 7 + cw, title + " · esempio", accent);
      else drawRealCandles(g, cw, ch, chartData[pair + tf] || { loading: true, pair }, title, accent);
      tex.needsUpdate = true;
    };
    c.draw(); charts.push(c); return tex;
  }
  async function refreshCharts() {
    if (DEMO || document.hidden) return;
    for (const key of new Set(charts.map(c => c.pair + "|" + c.tf).concat(extraPairs))) {
      const [pair, tf] = key.split("|");
      try {
        const r = await fetch(`api/candles?pair=${pair}&tf=${tf}`, { cache: "no-store", headers: tokenHdr() });
        if (r.ok) chartData[pair + tf] = await r.json();
      } catch (e) { /* keep the last data */ }
    }
    for (const c of charts) c.draw();
  }

  // shell: floor with a grid and four walls; the walls between the camera and the room hide themselves
  const XW = -14, ZW = -12, X1 = 16, Z1 = 13, H = 7, walls = {};
  {
    const tex = canvasTex(512, 512, (g, w, h) => {
      g.fillStyle = "#0e2250"; g.fillRect(0, 0, w, h);
      g.strokeStyle = "rgba(58,140,255,.55)"; g.lineWidth = 2; g.strokeRect(1, 1, w - 2, h - 2);
      g.strokeStyle = "rgba(58,140,255,.16)"; g.lineWidth = 1;
      for (let i = 1; i < 4; i++) { g.beginPath(); g.moveTo(i * w / 4, 0); g.lineTo(i * w / 4, h); g.moveTo(0, i * h / 4); g.lineTo(w, i * h / 4); g.stroke(); }
    });
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping; tex.repeat.set((X1 - XW) / 2, (Z1 - ZW) / 2);
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(X1 - XW, Z1 - ZW), new THREE.MeshStandardMaterial({ map: tex, roughness: .5, metalness: .3 }));
    floor.rotation.x = -Math.PI / 2; floor.position.set((XW + X1) / 2, 0, (ZW + Z1) / 2); scene.add(floor);
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x16285a, roughness: .6, metalness: .25, emissive: 0x081638 });
    const led = glow(BLUE);
    const mk = (side, len, x, z, rotY) => {  // a wall with its LED lines; side: back/left/right/front
      const g = new THREE.Group(); scene.add(g); walls[side] = g;
      const wall = new THREE.Mesh(new THREE.BoxGeometry(len, H, .3), wallMat); wall.position.set(x, H / 2, z); wall.rotation.y = rotY; g.add(wall);
      for (const y of [.12, H - .3]) { const b = new THREE.Mesh(new THREE.BoxGeometry(len, .04, .04), led); b.position.set(x, y, z); b.rotation.y = rotY; g.add(b); }
      for (let k = 1; k < 4; k++) {  // vertical light blades
        const b = new THREE.Mesh(new THREE.BoxGeometry(.035, H - 1, .035), led), f = k / 4 - .5;
        b.position.set(x + (rotY ? 0 : f * len), H / 2, z + (rotY ? f * len : 0)); g.add(b);
      }
    };
    mk("back", X1 - XW, (XW + X1) / 2, ZW - .15, 0); mk("front", X1 - XW, (XW + X1) / 2, Z1 + .15, 0);
    mk("left", Z1 - ZW, XW - .15, (ZW + Z1) / 2, Math.PI / 2); mk("right", Z1 - ZW, X1 + .15, (ZW + Z1) / 2, Math.PI / 2);
    for (const [x, z, side] of [[XW, ZW, null], [X1, ZW, "right"], [XW, Z1, "front"], [X1, Z1, "front"]]) {
      const c = new THREE.Mesh(new THREE.BoxGeometry(.08, H, .08), led); c.position.set(x, H / 2, z); (side ? walls[side] : scene).add(c);
    }
  }
  function screen(w, h, tex, x, y, z, rotY) {
    const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.y = rotY;
    const wall = Math.abs(x - XW) < .6 ? "left" : Math.abs(x - X1) < .6 ? "right" : Math.abs(z - ZW) < .6 ? "back" : Math.abs(z - Z1) < .6 ? "front" : null;
    (wall ? walls[wall] : scene).add(g);
    g.add(new THREE.Mesh(new THREE.BoxGeometry(w + .16, h + .16, .08), new THREE.MeshStandardMaterial({ color: 0x0b1733, metalness: .8, roughness: .3 })));
    // slightly below white so the bloom never smears the charts
    const s = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, color: 0xd8d8d8, toneMapped: false })); s.position.z = .045; g.add(s);
    const halo = new THREE.Mesh(new THREE.PlaneGeometry(w + .7, h + .7), new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: .12, depthWrite: false })); halo.position.z = .01; g.add(halo);
    return g;
  }
  // the big screen on the back wall: real numbers (page decides which), or the first-gain celebration
  const kpiTex = canvasTex(1400, 560, () => {});
  let partyUntil = 0, partyText = null;
  function drawCells(cells) {
    if (Date.now() < partyUntil) return;
    const c = kpiTex.userData.canvas, g = c.getContext("2d"), w = c.width;
    g.fillStyle = "#030918"; g.fillRect(0, 0, w, c.height);
    g.fillStyle = "#3aa0ff"; g.shadowColor = "#3aa0ff"; g.shadowBlur = 18; g.font = "700 52px Chakra Petch, sans-serif"; g.textAlign = "center"; g.fillText("CRYPTO MACHINE", w / 2, 84); g.shadowBlur = 0;
    cells.forEach(([t, v, col], i) => {
      const x = 40 + (i % 2) * (w / 2), y = 140 + Math.floor(i / 2) * 200;
      g.strokeStyle = "rgba(86,160,255,.35)"; g.lineWidth = 2; g.strokeRect(x, y, w / 2 - 80, 170);
      g.textAlign = "left"; g.fillStyle = "#8ea3c8"; g.font = "600 30px Chakra Petch, sans-serif"; g.fillText(t, x + 26, y + 50);
      g.fillStyle = col || "#e6efff"; g.font = "700 52px Chakra Petch, sans-serif"; g.fillText(String(v).slice(0, 24), x + 26, y + 128);
    });
    kpiTex.needsUpdate = true;
  }
  screen(7.2, 2.9, kpiTex, 1.5, 4.1, ZW + .05, 0);

  // agent desks along the walls
  const stations = {};
  const deskMat = new THREE.MeshStandardMaterial({ color: 0x0c1a38, metalness: .75, roughness: .15, emissive: 0x041030 });
  const darkMat = new THREE.MeshStandardMaterial({ color: 0x0a1226, metalness: .6, roughness: .4 });
  const greyMat = new THREE.MeshStandardMaterial({ color: 0x3a4256, roughness: .7 });
  agents.forEach(([keyName, name, color], i) => {
    const [x, z, yaw] = spots[i];
    const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = yaw; scene.add(g);
    const top = new THREE.Mesh(new THREE.BoxGeometry(2.6, .07, 1.1), deskMat); top.position.set(0, .78, -.15); g.add(top);
    const edge = new THREE.Mesh(new THREE.BoxGeometry(2.6, .015, .015), glow(BLUE)); edge.position.set(0, .8, .4); g.add(edge);
    for (const sx of [-1.2, 1.2]) { const leg = new THREE.Mesh(new THREE.BoxGeometry(.06, .78, 1), darkMat); leg.position.set(sx, .39, -.15); g.add(leg); }
    const scrMats = [];
    [[-.62, .25], [0, 0], [.62, -.25]].forEach(([mx, ry], j) => {
      const tex = liveChart(512, 320, ["BTC-EUR", "ETH-EUR", "SOL-EUR"][j], "15m", ["BTC 15m", "ETH 15m", "SOL 15m"][j], hex(color));
      const mm = new THREE.MeshBasicMaterial({ map: tex, toneMapped: false, transparent: true, opacity: .35 }); scrMats.push(mm);
      const mon = new THREE.Group(); mon.position.set(mx, 1.1, -.5); mon.rotation.y = ry; g.add(mon);
      mon.add(new THREE.Mesh(new THREE.BoxGeometry(.62, .4, .03), darkMat));
      const s = new THREE.Mesh(new THREE.PlaneGeometry(.58, .36), mm); s.position.z = .02; mon.add(s);
      const st = new THREE.Mesh(new THREE.BoxGeometry(.04, .14, .04), darkMat); st.position.set(0, -.25, -.02); mon.add(st);
    });
    const chair = new THREE.Mesh(new THREE.CylinderGeometry(.3, .3, .07, 20), darkMat); chair.position.set(0, .41, .7); g.add(chair);
    const back = new THREE.Mesh(new THREE.BoxGeometry(.56, .62, .06), darkMat); back.position.set(0, .8, 1.02); g.add(back);
    const post = new THREE.Mesh(new THREE.CylinderGeometry(.03, .03, .38), darkMat); post.position.set(0, .19, .7); g.add(post);
    const kb = new THREE.Mesh(new THREE.BoxGeometry(.5, .02, .16), new THREE.MeshStandardMaterial({ color: 0x1a2440, metalness: .5, roughness: .4 })); kb.position.set(0, .825, .18); g.add(kb);
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(.045, .04, .1, 16), new THREE.MeshStandardMaterial({ color, roughness: .4 })); mug.position.set(.85, .865, .12); g.add(mug);
    // the agent: a person sitting at the desk (see person()); lives in world space so it can get up and walk
    g.updateMatrixWorld(true);
    const p = person(color, i * 31 + keyName.length * 7 + 3); scene.add(p.root);
    const seat = g.localToWorld(new THREE.Vector3(0, 0, .66)).setY(0);
    p.root.position.copy(seat); p.root.rotation.y = yaw;
    const ring = new THREE.Mesh(new THREE.RingGeometry(.55, .62, 40), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0, toneMapped: false, side: THREE.DoubleSide }));
    ring.rotation.x = -Math.PI / 2; ring.position.set(0, .02, .6); g.add(ring);
    // a pendant lamp over the desk with a real light on the agent
    const cord = new THREE.Mesh(new THREE.CylinderGeometry(.01, .01, H - 3.6), darkMat); cord.position.set(0, 3.6 + (H - 3.6) / 2, .2); g.add(cord);
    const shadeM = new THREE.Mesh(new THREE.CylinderGeometry(.18, .55, .3, 32, 1, true), new THREE.MeshStandardMaterial({ color: 0x0b1733, metalness: .8, roughness: .3, side: THREE.DoubleSide }));
    shadeM.position.set(0, 3.5, .2); g.add(shadeM);
    const bulb = new THREE.Mesh(new THREE.CircleGeometry(.5, 32), glow(0xcfe6ff)); bulb.rotation.x = Math.PI / 2; bulb.position.set(0, 3.36, .2); g.add(bulb);
    const lamp = new THREE.SpotLight(0xdcebff, 26, 7, .75, .55, 1.4); lamp.position.set(0, 3.3, .2); lamp.target.position.set(0, 0, .2); g.add(lamp, lamp.target);
    const lab = label(name); p.root.add(lab);
    const bub = label("", "say"); bub.visible = false; p.root.add(bub);
    const st = stations[keyName] = { key: keyName, name, g, p, seat, yaw, suit: p.suit, ring, scrMats, lab, bub, state: "idle", desc: "", runs: 0, task: "", last: "",
      mode: "sit", path: [], face: yaw, stride: 0, J: null, blinkAt: 2 + i * .7, look: 0, text: "", shown: null };
    g.userData.onClick = () => showCard(name, [["Stato", st.paused ? "in pausa" : st.state === "working" ? "al lavoro" : "a riposo"], ["Compito", st.task || "—"], ["Ultimo lavoro", st.last || "—"], ["Esecuzioni", String(st.runs || 0)]],
      st.desc ? `<div class="small muted">${esc(st.desc)}</div>` : "");
    p.root.userData.onClick = g.userData.onClick;
  });

  // glass cabinet of coins (back-right corner)
  const coins = [];
  if (opts.cabinet !== false) {
    const cab = new THREE.Group(); cab.position.set(13.2, 0, -9.6); cab.rotation.y = -Math.PI / 6; scene.add(cab);
    const frameM = new THREE.MeshStandardMaterial({ color: 0x0b1733, metalness: .85, roughness: .25 });
    const glassM = new THREE.MeshStandardMaterial({ color: 0x8fc2ff, transparent: true, opacity: .1, roughness: .05, metalness: .1, depthWrite: false });
    const box = (sx, sy, sz, m, x, y, z) => { const o = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), m); o.position.set(x, y, z); cab.add(o); return o; };
    box(2.6, .15, 1.2, frameM, 0, .075, 0); box(2.6, .1, 1.2, frameM, 0, 4.3, 0);
    for (const [x, z] of [[-1.28, -.58], [1.28, -.58], [-1.28, .58], [1.28, .58]]) box(.06, 4.2, .06, frameM, x, 2.2, z);
    box(2.56, 4.15, .02, glassM, 0, 2.2, .6); box(.02, 4.15, 1.16, glassM, -1.29, 2.2, 0); box(.02, 4.15, 1.16, glassM, 1.29, 2.2, 0);
    const SYM = [["₿", "#f7931a"], ["Ξ", "#8c9eff"], ["◎", "#14f195"], ["$", "#2775ca"], ["Ł", "#bfbbbb"], ["◈", "#4fd2ff"]];
    [1.1, 2.3, 3.5].forEach((y, row) => {
      box(2.5, .03, 1.1, new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: .35, toneMapped: false }), 0, y - .35, 0);
      [-.7, .7].forEach((x, k) => {
        const [ch, col] = SYM[row * 2 + k];
        const face = canvasTex(256, 256, (g, w, h) => { g.fillStyle = "#0a1a3a"; g.beginPath(); g.arc(w / 2, h / 2, 124, 0, 7); g.fill(); g.strokeStyle = col; g.lineWidth = 10; g.stroke();
          g.font = "700 140px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillStyle = col; g.shadowColor = col; g.shadowBlur = 20; g.fillText(ch, w / 2, h / 2 + 8); });
        const fm = new THREE.MeshBasicMaterial({ map: face, toneMapped: false }), side = new THREE.MeshStandardMaterial({ color: 0x1b2b50, metalness: .9, roughness: .2 });
        const coin = new THREE.Mesh(new THREE.CylinderGeometry(.36, .36, .06, 40), [side, fm, fm]); coin.rotation.x = Math.PI / 2; coin.position.set(x, y, 0); cab.add(coin); coins.push(coin);
        const spot = new THREE.Mesh(new THREE.CircleGeometry(.4, 30), new THREE.MeshBasicMaterial({ color: new THREE.Color(col), transparent: true, opacity: .25, toneMapped: false })); spot.rotation.x = -Math.PI / 2; spot.position.set(x, y - .33, 0); cab.add(spot);
      });
    });
  }

  // picking and the info card
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function pick(ev) {
    const r = renderer.domElement.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1); ray.setFromCamera(ndc, camera);
    for (const h of ray.intersectObjects(scene.children, true)) { let o = h.object; while (o && !o.userData.onClick) o = o.parent; if (o) return o; }
    return null;
  }
  let downAt = null, lastHover = 0;
  renderer.domElement.addEventListener("pointerdown", e => { downAt = [e.clientX, e.clientY]; });
  renderer.domElement.addEventListener("pointerup", e => {
    if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 6) return;
    const o = pick(e); if (o) o.userData.onClick(o); else $("#card").hidden = true;
  });
  renderer.domElement.addEventListener("pointermove", e => { const n = performance.now(); if (n - lastHover < 120) return; lastHover = n; renderer.domElement.style.cursor = pick(e) ? "pointer" : "grab"; });
  addEventListener("keydown", e => { if (e.key === "Escape") $("#card").hidden = true; });
  function showCard(title, rows, extra = "") {
    $("#card").innerHTML = `<h3>${esc(title)}</h3>${extra}<dl>${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>`;
    $("#card").hidden = false;
  }

  // live state shared by every room: phase pill, agents, events, report, run button, next cycle
  // a wall screen drawn by the page: panel(w, h, x, y, z, rotY, draw(g, W, H)) → { draw() } (redraws with the same function)
  function panel(w, h, x, y, z, rotY, draw, px = 1100) {
    const W = px, Hh = Math.round(px * h / w), tex = canvasTex(W, Hh, () => {});
    const p = { draw(...a) { const g = tex.userData.canvas.getContext("2d"); g.setTransform(1, 0, 0, 1, 0, 0); g.textAlign = "left"; g.fillStyle = "#030918"; g.fillRect(0, 0, W, Hh); draw(g, W, Hh, ...a); tex.needsUpdate = true; } };
    p.draw(); screen(w, h, tex, x, y, z, rotY); return p;
  }

  // LED band running round the room, high on the four walls: real prices (api/prices) and the latest news of the machine
  const bandTex = canvasTex(4096, 128, () => {}); bandTex.wrapS = THREE.RepeatWrapping;
  let bandPrices = [], bandNews = [];
  function drawBand() {
    const g = bandTex.userData.canvas.getContext("2d"); g.fillStyle = "#020610"; g.fillRect(0, 0, 4096, 128);
    const items = bandPrices.map(p => [`${p.asset} ${Number(p.eur).toLocaleString("it-IT", { maximumFractionDigits: p.eur >= 1000 ? 0 : 2 })} € ${p.move > 0 ? "▲" : p.move < 0 ? "▼" : "•"}`, p.move > 0 ? "#2fd59b" : p.move < 0 ? "#ff4d6a" : "#cfe3ff"])
      .concat(bandNews.map(t => ["◆ " + t.toUpperCase(), "#4fd2ff"]));
    if (!items.length) items.push(["◆ CRYPTO MACHINE", "#4fd2ff"]);
    g.font = "700 62px Chakra Petch, sans-serif"; g.textBaseline = "middle";
    let x = 30; while (x < 4096) for (const [t, c] of items) { g.fillStyle = c; g.fillText(t, x, 66); x += g.measureText(t).width + 110; if (x >= 4096) break; }
    bandTex.needsUpdate = true;
  }
  drawBand();
  for (const [len, x, z, ry, side] of [[X1 - XW - .4, (XW + X1) / 2, ZW + .17, 0, "back"], [Z1 - ZW - .4, XW + .17, (ZW + Z1) / 2, Math.PI / 2, "left"],
    [Z1 - ZW - .4, X1 - .17, (ZW + Z1) / 2, -Math.PI / 2, "right"], [X1 - XW - .4, (XW + X1) / 2, Z1 - .17, Math.PI, "front"]]) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(len, .5), new THREE.MeshBasicMaterial({ map: bandTex, color: 0xdddddd, toneMapped: false }));
    m.position.set(x, H - .75, z); m.rotation.y = ry; walls[side].add(m);
  }
  async function refreshBand() {
    if (DEMO) { bandPrices = [{ asset: "BTC", eur: 52587, move: 1 }, { asset: "ETH", eur: 2282, move: -1 }, { asset: "SOL", eur: 141.67, move: 1 }]; drawBand(); return; }
    try { const r = await fetch("api/prices", { cache: "no-store", headers: tokenHdr() }); if (r.ok) { bandPrices = (await r.json()).prices || []; drawBand(); } } catch (e) {}
  }

  const room = { THREE, scene, camera, controls, renderer, screen, panel, stations, showCard, drawCells, kpiTex, liveChart, chartData, extraPairs, tokenHdr, XW, ZW, X1, Z1, H, phase: "idle", tickers: [] };
  function setPhase(p, paused, other) {
    room.phase = p;
    const shown = paused && p === "idle" ? "paused" : p;
    $("#phase").className = "pill " + shown;
    $("#phase").querySelector("span").textContent = other && p === "idle" ? `lavora il team ${other}` : ({ working: "al lavoro", starting: "sta partendo", idle: "chiusa", paused: "in pausa" })[shown];
  }
  function applyAgents(a0) {
    for (const st of Object.values(stations)) {
      const a = a0[st.key] || {};
      st.paused = !!a.paused; st.desc = a.desc || st.desc; st.runs = a.runs ?? st.runs;
      const prev = st.state;
      st.state = st.paused ? "paused" : a.status && a.status !== "idle" ? "working" : (st.key === opts.lead && room.phase === "working" ? "working" : "idle");
      if (prev === "working" && st.state !== "working") st.doneUntil = Date.now() + 9000;
      st.task = a.task || (st.key === opts.lead && st.state === "working" ? "coordina il ciclo" : "");
      if (a.last) st.last = a.last;
      st.lab.element.className = "lbl" + (st.paused ? " off" : "");
      for (const m of st.p.suitMeshes) m.material = st.paused ? greyMat : st.suit;
      st.text = st.state === "working" ? "⚙️ " + (st.task || "al lavoro") : st.doneUntil > Date.now() ? "✅ " + String(st.last || "fatto").slice(0, 90) : "";
    }
  }
  const NAME = Object.fromEntries(agents.map(a => [a[0], a[1]]));
  function render(d) {
    setPhase(d.phase, d.system === "paused", d.other_team);
    applyAgents(d.agents || {});
    room.headline = d.report ? d.report.headline : "";
    if (d.world) { party.check(d.world, DEMO); opts.world(d.world, d); }
    const r = d.report;
    const news = [r && `ciclo #${r.cycle}: ${r.headline}`, ...(d.events || []).slice(-3).reverse().map(e => `${NAME[e.agent] || e.agent} ${e.msg}`)].filter(Boolean).map(t => String(t).slice(0, 90));
    if (news.join() !== bandNews.join()) { bandNews = news; drawBand(); }
    $("#repH").textContent = r ? r.headline : "Nessun resoconto ancora.";
    $("#repM").textContent = r ? `Ciclo #${r.cycle}` + (r.needs_you && r.needs_you.length ? ` · serve da te: ${r.needs_you[0]}` : "") : "";
    $("#events").innerHTML = (d.events || []).slice().reverse().slice(0, 12).map(e =>
      `<div class="e"><span class="muted">${esc((e.ts || "").slice(11, 16))}</span> <b>${esc(NAME[e.agent] || e.agent)}</b> ${esc(e.msg)}</div>`).join("")
      || `<div class="muted small">Nessuna attività registrata finora.</div>`;
  }
  let demoT0 = Date.now();
  async function poll() {
    if (DEMO) { $("#demoTag").hidden = false; return render(opts.demo((Date.now() - demoT0) / 1000)); }
    try {
      const r = await fetch("api/live?team=" + team, { cache: "no-store", headers: tokenHdr() });
      if (r.status === 401) { const t = prompt("Password della plancia (MM_TOKEN):"); if (t) { try { localStorage.setItem("mm-token", t); } catch (e) {} poll(); } return; }
      if (r.ok) render(await r.json());
    } catch (e) { /* offline: keep the last view */ }
  }
  $("#runBtn").onclick = async () => {
    if (DEMO) { demoT0 = Date.now(); return; }
    $("#runBtn").disabled = true;
    try {
      const r = await fetch("api/cycle", { method: "POST", headers: { "Content-Type": "application/json", ...tokenHdr() }, body: JSON.stringify({ team }) });
      const j = await r.json(); showCard("Avvia ciclo", [["Esito", (j.result || [j.error || "—"]).join(" ")]]);
    } catch (e) { showCard("Avvia ciclo", [["Esito", "il server della plancia non risponde"]]); }
    setTimeout(() => { $("#runBtn").disabled = false; }, 8000);
  };
  const [cMin, cHours] = cron;
  setInterval(() => {
    const now = new Date(); let n = null;
    for (let d = 0; d < 2; d++) for (const h of cHours) { const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + d, h, cMin)); if (t > now && (!n || t < n)) n = t; }
    const m = Math.round((n - now) / 60000);
    $("#next").textContent = `prossimo ciclo alle ${n.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })} (tra ${m >= 60 ? Math.floor(m / 60) + " h " : ""}${m % 60} min)`;
  }, 1000);

  // first real gain: confetti, the big screen celebrates, the agents cheer (once per gain)
  const party = firstSaleParty({ scene, key: team === "trading" ? "office" : "sales",
    office: { celebrate(text, line, secs) {
      partyText = [text, line]; partyUntil = Date.now() + secs * 1000;
      const c = kpiTex.userData.canvas, g = c.getContext("2d"), w = c.width, h = c.height;
      g.fillStyle = "#030918"; g.fillRect(0, 0, w, h); g.textAlign = "center"; g.shadowColor = "#2fd59b"; g.shadowBlur = 30;
      g.fillStyle = "#2fd59b"; g.font = "700 110px Chakra Petch, sans-serif"; g.fillText(partyText[0], w / 2, h / 2);
      g.shadowBlur = 0; g.fillStyle = "#e6efff"; g.font = "600 46px Chakra Petch, sans-serif"; g.fillText(partyText[1] || "", w / 2, h / 2 + 90); kpiTex.needsUpdate = true;
    } },
    desks: () => Object.values(stations).map(st => ({ cheer: secs => { st.cheerUntil = Date.now() + secs * 1000; } })) });

  // office life: agents at work sit and type; idle agents now and then get up, walk along the aisles to a colleague's
  // desk, chat for a few seconds (real prices, the real report, the colleague's real last job, or office small talk)
  // and go back to their chair. A task, a pause or the party always calls them back.
  const life = (() => {
    const V = (x, z) => new THREE.Vector3(x, 0, z);
    const loc = (st, x, z) => st.g.localToWorld(new THREE.Vector3(x, 0, z)).setY(0);
    const exitOf = (st, toward) => { const sx = st.g.worldToLocal(toward.clone()).x >= 0 ? 1.65 : -1.65; return [loc(st, sx, .66), loc(st, sx, -1.45)]; };
    const corridor = (a, b) => {
      if (Math.abs(a.x - b.x) < .4 || Math.abs(a.z - b.z) < .4) return [b];
      const c1 = V(a.x, b.z), c2 = V(b.x, a.z); return [c1.length() > c2.length() ? c1 : c2, b];
    };
    const pick = a => a[Math.floor(Math.random() * a.length)];
    const free = st => st.state === "idle" && !st.paused && st.mode === "sit" && !(st.cheerUntil > Date.now());
    let meeting = null, nextMeet = Date.now() + 5000 + Math.random() * 4000;
    function lines(a, b) {
      const facts = [], pr = bandPrices.filter(p => p.eur != null);
      if (pr.length) { const p = pick(pr), v = Number(p.eur).toLocaleString("it-IT", { maximumFractionDigits: p.eur >= 1000 ? 0 : 3 });
        facts.push([`Hai visto ${p.asset}? ${v} €`, p.move > 0 ? "Sì, oggi sale 📈" : p.move < 0 ? "Sì, oggi scende 📉 occhio" : "Sì, è fermo per ora"]); }
      if (room.headline) facts.push(["Hai letto l'ultimo resoconto?", "«" + String(room.headline).slice(0, 70) + "»"]);
      if (b.last) facts.push(["Com'è andato il tuo ultimo lavoro?", String(b.last).slice(0, 80)]);
      const nx = ($("#next") || {}).textContent || "";
      if (nx) facts.push(["Quando riparte il ciclo?", nx.replace(/^prossimo ciclo /, "")]);
      const talk = [["Pausa caffè? ☕", "Volentieri, cinque minuti"], ["Niente leva, mai 😉", "Lo dice la POLICY: mai"], ["Prima il backtest, poi si parla", "Esatto, contano i numeri veri"],
        ["Tutto tranquillo?", "Sì, aspetto il prossimo ciclo"], ["Mi passi i dati di ieri?", "Te li ho messi nel registro"]];
      const [q, r] = facts.length && Math.random() < .75 ? pick(facts) : pick(talk);
      return [[a, q], [b, r], [a, pick(["Ok, torno alla scrivania", "Perfetto, a dopo 👋", "Teniamolo d'occhio", "Grazie, ci aggiorniamo"])]];
    }
    function start(a, b) {
      const bx = exitOf(b, a.seat), ax = exitOf(a, b.seat);
      const route = [...ax, ...corridor(ax[1], bx[1])]; route.pop();
      const prev = route[route.length - 1], dir = prev.clone().sub(bx[1]).setY(0).normalize();
      route.push(bx[1].clone().addScaledVector(dir, .95));
      a.path = route.slice(); a.home = route.slice(0, -1).reverse().concat([a.seat]);
      b.path = bx.slice(); b.home = [bx[0], b.seat];
      for (const s of [a, b]) s.mode = "walk";
      a.mate = b; b.mate = a; meeting = { a, b, talk: null, i: 0, next: 0 };
    }
    function goHome(s) { s.mode = "walk"; s.path = s.home || [s.seat]; s.home = null; s.mate = null; s.talking = false; }
    function end() { if (!meeting) return; goHome(meeting.a); goHome(meeting.b); meeting = null; nextMeet = Date.now() + 12000 + Math.random() * 20000; }
    function schedule() {
      const now = Date.now();
      if (meeting) {
        const { a, b } = meeting;
        if ([a, b].some(s => s.state !== "idle" || s.paused || s.cheerUntil > now)) return end();
        if (a.mode === "stand" && b.mode === "stand") {
          meeting.talk = meeting.talk || lines(a, b);
          if (now >= meeting.next) {
            if (meeting.i >= meeting.talk.length) return end();
            const [who, text] = meeting.talk[meeting.i++];
            for (const s of [a, b]) s.talking = s === who;
            who.chatText = text; who.chatUntil = now + 3300; meeting.next = now + 3500;
          }
        }
        return;
      }
      if (now < nextMeet) return;
      const ok = Object.values(stations).filter(free);
      if (ok.length < 2) { nextMeet = now + 4000; return; }
      const a = pick(ok), near = ok.filter(s => s !== a).sort((x, y) => x.seat.distanceTo(a.seat) - y.seat.distanceTo(a.seat));
      start(a, pick(near.slice(0, 3)));   // usually a colleague nearby
    }
    // pose: target joint angles per activity, smoothed every frame
    function pose(st, dt, t) {
      const P = st.p, now = Date.now(), on = st.state === "working", cheer = st.cheerUntil > now, seed = st.blinkAt;
      const T = { pel: .917, lean: 0, hip: [0, 0], knee: [0, 0], sh: [.06, .06], shz: [.08, .08], el: [.15, .15], hy: 0, hx: 0 };
      if (st.mode === "sit") {
        Object.assign(T, { pel: .52, hip: [Math.PI / 2, Math.PI / 2], knee: [-Math.PI / 2 + .08, -Math.PI / 2 - .04], shz: [.05, .05] });
        if (st.paused) Object.assign(T, { lean: .12, hx: -.38, sh: [.2, .2], el: [1, 1] });
        else if (on) { const k = Math.sin(t * 17), k2 = Math.sin(t * 15 + 1.7);
          Object.assign(T, { lean: -.08, sh: [.5, .5], el: [1.42 + k * .07, 1.42 + k2 * .07], hx: -.1, hy: Math.round(Math.sin(t * .45 + seed) * 1.2) * .28 }); }
        else Object.assign(T, { lean: .05, sh: [.45, .4], el: [1.35, 1.3], hx: .04 + Math.sin(t * .5 + seed) * .05, hy: Math.sin(t * .23 + seed) * .55 });
      } else if (st.mode === "walk") {
        const f = st.stride;
        T.pel = .9 + Math.abs(Math.cos(f)) * .025; T.lean = -.04;
        for (const k of [0, 1]) { const ph = f + k * Math.PI;
          T.hip[k] = Math.sin(ph) * .45; T.knee[k] = -.1 - Math.max(0, Math.sin(ph - 1.3)) * .7; T.sh[1 - k] = Math.sin(ph) * .4; T.el[1 - k] = .3; }
      } else if (st.talking) { T.sh[1] = .45 + Math.sin(t * 3) * .15; T.el[1] = 1.2 + Math.sin(t * 5) * .3; T.hx = Math.sin(t * 2.5) * .05; T.hy = Math.sin(t * 1.3) * .12; }
      else { T.hx = Math.sin(t * 1.6) * .06; }
      if (cheer) { T.sh = [2.75, 2.75]; T.shz = [.35, .35]; T.el = [.3, .3]; }
      const J = st.J || (st.J = JSON.parse(JSON.stringify(T))), d = Math.min(1, dt * 9);
      for (const k in T) if (Array.isArray(T[k])) for (const n of [0, 1]) J[k][n] += (T[k][n] - J[k][n]) * d; else J[k] += (T[k] - J[k]) * d;
      P.pelvis.position.y = J.pel; P.spine.rotation.x = J.lean;
      P.legs.forEach((L, n) => { L.a.rotation.x = J.hip[n]; L.j.rotation.x = J.knee[n]; });
      P.arms.forEach((A, n) => { A.a.rotation.x = J.sh[n]; A.a.rotation.z = A.s * J.shz[n]; A.j.rotation.x = J.el[n]; });
      P.head.rotation.set(J.hx, J.hy, 0);
      // eyes blink, the mouth moves while talking
      const bl = (t + seed * 1.7) % 4.2 < .13 ? .12 : 1; for (const e of P.eyes) e.scale.y = bl;
      const speaking = st.chatUntil > now; P.mouth.scale.set(1, speaking ? .5 + Math.abs(Math.sin(t * 13)) * 1.6 : 1, 1);
      P.root.position.y = cheer ? Math.abs(Math.sin(t * 9)) * .3 : 0;
      st.lab.position.y = J.pel + 1.1; st.bub.position.y = J.pel + 1.52;
    }
    function move(st, dt) {
      const R = st.p.root;
      if (st.mode === "walk") {
        const tgt = st.path[0];
        if (!tgt) {
          if (st.mate) { st.mode = "stand"; } else { st.mode = "sit"; st.face = st.yaw; R.position.x = st.seat.x; R.position.z = st.seat.z; }
        } else {
          const dx = tgt.x - R.position.x, dz = tgt.z - R.position.z, dist = Math.hypot(dx, dz), sp = (st.state === "idle" ? 1.35 : 2.4) * dt;
          if (dist <= sp) { R.position.x = tgt.x; R.position.z = tgt.z; st.path.shift(); } else { R.position.x += dx / dist * sp; R.position.z += dz / dist * sp; }
          if (dist > .05) st.face = Math.atan2(-dx, -dz);
          st.stride += sp / .55 * Math.PI;
        }
      }
      if (st.mode === "stand" && st.mate) { const o = st.mate.p.root.position; st.face = Math.atan2(-(o.x - R.position.x), -(o.z - R.position.z)); }
      let dy = st.face - R.rotation.y; dy = Math.atan2(Math.sin(dy), Math.cos(dy)); R.rotation.y += dy * Math.min(1, dt * 7);
    }
    function bubble(st) {
      const chat = st.chatUntil > Date.now() && st.state !== "working";
      const text = chat ? st.chatText : st.text, cls = "say" + (chat ? " chat" : st.state === "working" ? "" : " done");
      if (text + cls === st.shown) return; st.shown = text + cls;
      st.bub.visible = !!text; st.bub.element.textContent = text; st.bub.element.className = cls;
    }
    let acc = 0;
    return { tick(dt, t) {
      if ((acc += dt) > .25) { acc = 0; schedule(); }
      for (const st of Object.values(stations)) {
        // a task or a pause calls a wandering agent straight back to the desk
        if (st.mode !== "sit" && !st.mate && st.path.length === 0 && st.mode !== "walk") goHome(st);
        move(st, dt); pose(st, dt, t); bubble(st);
      }
    } };
  })();

  // loop
  const fx = postfx(renderer, scene, camera);
  if (fx.bloom) { fx.bloom.strength = .5; fx.bloom.threshold = .9; fx.bloom.radius = .4; }
  function resize() {
    const w = innerWidth, h = innerHeight; renderer.setSize(w, h); labels.setSize(w, h); fx.setSize(w, h);
    camera.aspect = w / h; camera.fov = w / h < 1 ? 55 : 38; camera.updateProjectionMatrix();
  }
  addEventListener("resize", resize); resize();
  const clock = new THREE.Clock();
  room.start = () => {
    renderer.setAnimationLoop(() => {
      const dt = Math.min(.1, clock.getDelta()), t = clock.elapsedTime;
      for (const c of coins) c.rotation.z += dt * .8;
      for (const st of Object.values(stations)) {
        const on = st.state === "working";
        st.suit.emissiveIntensity = on ? .3 + Math.sin(t * 4) * .12 : .06;
        st.ring.material.opacity = on && st.mode === "sit" ? .7 : 0;
        for (const m of st.scrMats) m.opacity = on ? 1 : st.paused ? .1 : .4;
      }
      life.tick(dt, t);
      const cp = camera.position;
      walls.front.visible = cp.z < Z1; walls.right.visible = cp.x < X1; walls.back.visible = cp.z > ZW; walls.left.visible = cp.x > XW;
      bandTex.offset.x = (bandTex.offset.x + dt * .025) % 1;
      for (const f of room.tickers) f(dt, t);
      party.tick(dt);
      controls.update(); fx.render(); labels.render(scene, camera);
    });
    poll(); setInterval(() => { if (!document.hidden) poll(); }, DEMO ? 1000 : 5000);
    refreshCharts(); setInterval(refreshCharts, 60000);
    refreshBand(); setInterval(refreshBand, 60000);
  };
  return room;
}
