// Realistic look shared by the 3D rooms (office.html, sales.html): lighting, room, furniture, people,
// wall screen with the real numbers, AI budget tank, windows that follow the time of day, cash sound.
// Everything is procedural (canvas textures, primitives, Web Audio): no external assets to download.
import * as THREE from "three";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const SMALL = Math.min(innerWidth, innerHeight) < 760;
let THEME = null;  // set by room(): "neon" turns wooden desks into dark glass with a blue edge

// ---------------------------------------------------------------- renderer: tone mapping, soft shadows, reflections
export function realism(renderer, scene, { bg = 0x070b14, envIntensity = .45 } = {}) {
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), .04).texture;
  scene.environmentIntensity = envIntensity;
  pmrem.dispose();
  scene.fog = new THREE.Fog(bg, 38, 80);
  const sun = new THREE.DirectionalLight(0xfff1dc, 1.1);
  sun.position.set(-9, 16, 11);
  sun.castShadow = true;
  sun.shadow.mapSize.setScalar(SMALL ? 1024 : 2048);
  Object.assign(sun.shadow.camera, { left: -17, right: 17, top: 13, bottom: -13, near: 1, far: 50 });
  sun.shadow.bias = -.0004; sun.shadow.normalBias = .02; sun.shadow.radius = 3;
  scene.add(sun, sun.target);
  return sun;
}

// glow on neon, screens and lamps (bloom). Off on small screens to save battery and GPU.
export function postfx(renderer, scene, camera) {
  if (SMALL) return { render: () => renderer.render(scene, camera), setSize() {} };
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), .5, .45, .9);  // only very bright pixels glow
  composer.addPass(bloom); composer.addPass(new OutputPass());
  return { render: () => composer.render(), setSize: (w, h) => { composer.setPixelRatio(renderer.getPixelRatio()); composer.setSize(w, h); }, bloom };
}

// cast/receive shadows on every solid mesh under obj (transparent/glowing ones excluded)
export function shade(obj) {
  obj.traverse(o => {
    if (!o.isMesh || o.material.transparent || o.material.isMeshBasicMaterial) return;
    o.castShadow = true; o.receiveShadow = true;
  });
  return obj;
}

// ---------------------------------------------------------------- procedural textures
function canvasTex(w, h, draw, repeat) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 4;
  if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); }
  return t;
}
const rnd = (a, b) => a + Math.random() * (b - a);
const seeded = seed => () => (seed = seed * 16807 % 2147483647) / 2147483647;
const shadeHex = (hex, f) => { const c = new THREE.Color(hex).multiplyScalar(f); return "#" + c.getHexString(); };
const hexStr = hex => "#" + new THREE.Color(hex).getHexString();

function woodPlanks(base, rows = 8, repeat) {
  return canvasTex(512, 512, (g, w, h) => {
    const ph = h / rows;
    for (let r = 0; r < rows; r++) {
      let x = -rnd(0, 200);
      while (x < w) {
        const len = rnd(160, 320);
        g.fillStyle = shadeHex(base, rnd(.78, 1.15)); g.fillRect(x, r * ph, len, ph);
        g.strokeStyle = "rgba(0,0,0,.18)"; g.lineWidth = 1;
        for (let k = 0; k < 7; k++) {  // grain
          const y = r * ph + rnd(2, ph - 2); g.beginPath(); g.moveTo(x, y);
          g.bezierCurveTo(x + len * .3, y + rnd(-3, 3), x + len * .7, y + rnd(-3, 3), x + len, y + rnd(-2, 2)); g.stroke();
        }
        g.fillStyle = "rgba(0,0,0,.45)"; g.fillRect(x, r * ph, 2, ph);
        x += len;
      }
      g.fillStyle = "rgba(0,0,0,.5)"; g.fillRect(0, r * ph, w, 2);
    }
  }, repeat);
}

// floors of the styled rooms: lab tiles, shop checkerboard, studio concrete (1 texture = 4 m)
function floorTex(style, repeat) {
  return canvasTex(512, 512, (g, w, h) => {
    const r = seeded(5);
    if (style === "neon") {  // exchange look: deep navy glass tiles with a thin glowing blue grid
      const bg = g.createLinearGradient(0, 0, w, h); bg.addColorStop(0, "#081226"); bg.addColorStop(1, "#050b1a");
      g.fillStyle = bg; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 900; i++) { g.fillStyle = `rgba(90,150,255,${r() * .05})`; g.fillRect(r() * w, r() * h, 1 + r() * 3, 1 + r() * 3); }
      g.strokeStyle = "rgba(70,150,255,.55)"; g.lineWidth = 2;
      for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * w / 4, 0); g.lineTo(i * w / 4, h); g.stroke(); g.beginPath(); g.moveTo(0, i * h / 4); g.lineTo(w, i * h / 4); g.stroke(); }
      g.strokeStyle = "rgba(70,150,255,.14)"; g.lineWidth = 1;
      for (let i = 0; i < 16; i++) { g.beginPath(); g.moveTo(i * w / 16, 0); g.lineTo(i * w / 16, h); g.stroke(); g.beginPath(); g.moveTo(0, i * h / 16); g.lineTo(w, i * h / 16); g.stroke(); }
    } else if (style === "lab") {
      g.fillStyle = "#4b5563"; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 6; i++) for (let j = 0; j < 6; j++) {
        const v = Math.round(r() * 8 - 4); g.fillStyle = `rgb(${92 + v},${101 + v},${114 + v})`; g.fillRect(i * w / 6 + 2, j * h / 6 + 2, w / 6 - 4, h / 6 - 4);
      }
    } else if (style === "shop") {
      for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
        const v = Math.round(r() * 6); g.fillStyle = (i + j) % 2 ? `rgb(${50 + v},${42 + v},${64 + v})` : `rgb(${132 - v},${124 - v},${113 - v})`;
        g.fillRect(i * w / 4, j * h / 4, w / 4, h / 4);
      }
    } else {
      g.fillStyle = "#4b4d55"; g.fillRect(0, 0, w, h);
      for (let i = 0; i < 2600; i++) { g.fillStyle = `rgba(${r() < .5 ? "255,255,255" : "0,0,0"},${r() * .08})`; g.fillRect(r() * w, r() * h, 2 + r() * 5, 2 + r() * 5); }
      g.fillStyle = "rgba(0,0,0,.35)"; g.fillRect(0, h / 2 - 1, w, 2); g.fillRect(w / 2 - 1, 0, 2, h);
    }
  }, repeat);
}

// wall monitor with a candlestick chart (decoration for the neon theme; the real numbers stay on the big screen)
function chartPanel(accent, seed, w = 3.6, h = 2.1) {
  const g = new THREE.Group(), r = seeded(seed), acc = "#" + accent.toString(16).padStart(6, "0");
  const tex = canvasTex(768, 448, (c, W, H) => {
    c.fillStyle = "#040a18"; c.fillRect(0, 0, W, H);
    c.strokeStyle = "rgba(80,150,255,.12)"; c.lineWidth = 1;
    for (let y = 40; y < H; y += 48) { c.beginPath(); c.moveTo(0, y); c.lineTo(W, y); c.stroke(); }
    for (let x = 0; x < W; x += 64) { c.beginPath(); c.moveTo(x, 30); c.lineTo(x, H); c.stroke(); }
    let p = H * .6; const pts = [];
    for (let x = 20; x < W - 20; x += 14) {
      const o = p, cl = Math.max(70, Math.min(H - 70, p + (r() - .52) * 46)), hi = Math.min(o, cl) - r() * 18, lo = Math.max(o, cl) + r() * 18;
      const up = cl < o; c.strokeStyle = c.fillStyle = up ? "#2fd59b" : "#ff4d6a";
      c.beginPath(); c.moveTo(x + 4, hi); c.lineTo(x + 4, lo); c.stroke(); c.fillRect(x, Math.min(o, cl), 9, Math.max(2, Math.abs(cl - o)));
      pts.push([x + 4, cl]); p = cl;
    }
    c.strokeStyle = acc; c.lineWidth = 3; c.shadowColor = acc; c.shadowBlur = 12; c.beginPath();
    pts.forEach(([x, y], i) => { const a = pts.slice(Math.max(0, i - 6), i + 1); const m = a.reduce((t, q) => t + q[1], 0) / a.length; i ? c.lineTo(x, m) : c.moveTo(x, m); }); c.stroke();
    c.shadowBlur = 0; c.fillStyle = "#cfe3ff"; c.font = "600 22px sans-serif"; c.fillText(["BTC · 1D", "ETH · 4H", "SOL · 1H", "MARKET"][seed % 4], 18, 26);
  }, [1, 1]);
  const frame = new THREE.Mesh(new THREE.BoxGeometry(w + .14, h + .14, .06), new THREE.MeshStandardMaterial({ color: 0x0a1428, roughness: .3, metalness: .8 }));
  g.add(frame);
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ map: tex, fog: false, toneMapped: false })); scr.position.z = .035; g.add(scr);
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(w + .5, h + .5), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: .12, depthWrite: false })); glow.position.z = .01; g.add(glow);
  return g;
}

// the same city (fixed seed) at three times of day
const SKY = {
  day: { top: "#5d9be0", mid: "#a9cdf0", low: "#dde9f2", far: "#7f93ab", near: "#5b6b80", lit: .04, stars: 0 },
  dusk: { top: "#2a2350", mid: "#c9607a", low: "#f3a45c", far: "#3e3656", near: "#241f36", lit: .2, stars: 20 },
  night: { top: "#060914", mid: null, low: "#1a1426", far: "#0d1220", near: "#070a12", lit: .3, stars: 90 },
};
function skyline(accent, mode) {
  const k = SKY[mode], r = seeded(7), wins = [];
  let ctx = null;
  const tex = canvasTex(1024, 512, (g, w, h) => {
    ctx = g;
    const sky = g.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, k.top); sky.addColorStop(.65, k.mid || shadeHex(accent, .18)); sky.addColorStop(1, k.low);
    g.fillStyle = sky; g.fillRect(0, 0, w, h);
    for (let i = 0; i < k.stars; i++) { g.fillStyle = `rgba(255,255,255,${rnd(.2, .8)})`; g.fillRect(rnd(0, w), rnd(0, h * .45), 1.5, 1.5); }
    // the windows show the texture stretched ~1.45x horizontally: draw round things as ellipses so they look round
    if (mode === "day") { g.fillStyle = "rgba(255,250,225,.9)"; g.beginPath(); g.ellipse(w * .78, h * .2, 18, 26, 0, 0, 7); g.fill(); }
    if (mode === "night") { g.fillStyle = "rgba(235,240,255,.85)"; g.beginPath(); g.ellipse(w * .2, h * .16, 11, 16, 0, 0, 7); g.fill(); }
    for (const [far, tone] of [[1, k.far], [0, k.near]]) {
      let x = 0;
      while (x < w) {
        const bw = 40 + r() * 70, bh = far ? 120 + r() * 180 : 60 + r() * 160;
        g.fillStyle = tone; g.fillRect(x, h - bh, bw, bh);
        for (let wy = h - bh + 8; wy < h - 6; wy += 11) for (let wx = x + 6; wx < x + bw - 6; wx += 9) {
          const on = r() < (far ? k.lit * .75 : k.lit), cool = r() < .2;
          if (on) { g.fillStyle = cool ? "rgba(140,220,255,.8)" : "rgba(255,214,140,.85)"; g.fillRect(wx, wy, 4, 5); }
          else if (mode === "day") { g.fillStyle = "rgba(210,230,250,.35)"; g.fillRect(wx, wy, 4, 5); }
          if (!far) wins.push([wx, wy, on, tone, cool]);
        }
        x += bw + 2 + r() * 12;
      }
    }
  });
  // a few office lights switch on/off now and then (evening and night only)
  tex.userData.flicker = (n = 6) => {
    if (mode === "day" || !wins.length) return;
    for (let i = 0; i < n; i++) {
      const wv = wins[Math.floor(Math.random() * wins.length)]; wv[2] = !wv[2];
      ctx.fillStyle = wv[3]; ctx.fillRect(wv[0] - 1, wv[1] - 1, 6, 7);
      if (wv[2]) { ctx.fillStyle = wv[4] ? "rgba(140,220,255,.8)" : "rgba(255,214,140,.85)"; ctx.fillRect(wv[0], wv[1], 4, 5); }
    }
    tex.needsUpdate = true;
  };
  return tex;
}
function cloudTex() {
  return canvasTex(512, 256, (g, w, h) => {
    const r = seeded(11);
    for (let i = 0; i < 9; i++) {
      const cx = r() * w, cy = 30 + r() * h * .45, s = 26 + r() * 46;
      for (let k = 0; k < 5; k++) {
        const x = cx + (k - 2) * s * .55, y = cy + Math.sin(k * 1.7) * s * .18, rad = s * (.55 + r() * .35);
        const gr = g.createRadialGradient(x, y, 0, x, y, rad);
        gr.addColorStop(0, "rgba(255,255,255,.55)"); gr.addColorStop(1, "rgba(255,255,255,0)");
        g.fillStyle = gr; g.beginPath(); g.arc(x, y, rad, 0, 7); g.fill();
      }
    }
  }, [1, 1]);
}
// the street seen from the shop window (sales room): the facades across the road, at three times of day
function streetTex(accent, mode) {
  return canvasTex(1024, 440, (g, w, h) => {
    const r = seeded(21), dark = { day: 1, dusk: .62, night: .3 }[mode];
    const sky = g.createLinearGradient(0, 0, 0, h * .3);
    sky.addColorStop(0, SKY[mode].top); sky.addColorStop(1, SKY[mode].low);
    g.fillStyle = sky; g.fillRect(0, 0, w, h * .3);
    // the buildings across the road: a shop on the ground floor, flats above
    let x = -20;
    const tones = ["#c9a27e", "#d8c7a8", "#9fb3c0", "#b98b7a", "#cfc29a"];
    while (x < w) {
      const bw = 190 + r() * 90, top = h * (.04 + r() * .1), base = h * .68;
      g.fillStyle = shadeHex(tones[Math.floor(r() * tones.length)], dark); g.fillRect(x, top, bw, base - top);
      for (let wy = top + 22; wy < base - 140; wy += 58) for (let wx = x + 22; wx < x + bw - 40; wx += 52) {
        const lit = mode !== "day" && r() < (mode === "night" ? .45 : .25);
        g.fillStyle = lit ? "rgba(255,206,130,.95)" : mode === "day" ? "#7f9cb5" : "#1b2230"; g.fillRect(wx, wy, 26, 36);
      }
      // shop front with its own awning
      const sx = x + 18, sw = bw - 36, sy = base - 112;
      const shopLit = mode !== "day";
      const sg = g.createLinearGradient(0, sy, 0, base);
      sg.addColorStop(0, shopLit ? "#ffd99a" : "#9cc0d8"); sg.addColorStop(1, shopLit ? "#e7a650" : "#6d8fa8");
      g.fillStyle = sg; g.fillRect(sx, sy, sw, 100);
      g.fillStyle = shadeHex("#20242c", dark + .3); g.fillRect(sx + sw * .62, sy + 10, sw * .2, 90);  // door
      const aw = ["#c0392b", "#2e86de", "#27ae60", "#8e44ad", "#d35400"][Math.floor(r() * 5)];
      for (let i = 0; i < sw; i += 22) { g.fillStyle = (i / 22) % 2 ? "#f4efe6" : aw; g.fillRect(sx + i, sy - 26, Math.min(22, sw - i), 22); }
      g.fillStyle = shadeHex("#ffffff", dark * .6); g.fillRect(sx, sy - 32, sw, 6);
      x += bw + 6;
    }
    // far sidewalk, road with the dashed line, near sidewalk
    g.fillStyle = shadeHex("#a49d90", dark); g.fillRect(0, h * .68, w, h * .07);
    g.fillStyle = shadeHex("#4a4d55", dark); g.fillRect(0, h * .75, w, h * .17);
    g.fillStyle = shadeHex("#e8e4d8", dark); for (let i = 0; i < w; i += 90) g.fillRect(i, h * .83, 46, 5);
    g.fillStyle = shadeHex("#b3ab9c", dark); g.fillRect(0, h * .92, w, h * .08);
    // a parked car and two street lamps (lit after sunset)
    g.fillStyle = shadeHex("#2f6fb0", dark); g.beginPath(); g.roundRect(620, h * .77, 150, 30, 8); g.fill();
    g.beginPath(); g.roundRect(650, h * .77 - 22, 85, 26, 8); g.fill();
    g.fillStyle = "#15161a"; for (const cx of [648, 742]) { g.beginPath(); g.arc(cx, h * .77 + 30, 11, 0, 7); g.fill(); }
    for (const lx of [180, 860]) {
      g.fillStyle = "#23262e"; g.fillRect(lx, h * .32, 7, h * .4); g.fillRect(lx - 16, h * .32, 30, 7);
      if (mode !== "day") {
        const gl = g.createRadialGradient(lx - 4, h * .34, 2, lx - 4, h * .34, 70);
        gl.addColorStop(0, "rgba(255,226,160,.95)"); gl.addColorStop(1, "rgba(255,226,160,0)"); g.fillStyle = gl; g.fillRect(lx - 80, h * .34 - 70, 160, 140);
      }
    }
    // our own awning, seen from below at the top of the glass
    for (let i = 0; i < w; i += 64) {
      g.fillStyle = (i / 64) % 2 ? "#f4efe6" : hexStr(accent);
      g.beginPath(); g.moveTo(i, 0); g.lineTo(i + 64, 0); g.lineTo(i + 64, 30); g.arc(i + 32, 30, 32, 0, Math.PI); g.closePath(); g.fill();
    }
  });
}
// a passer-by on the pavement outside the shop window (dark silhouette)
function walkerTex(seed) {
  return canvasTex(64, 200, (g, w, h) => {
    g.fillStyle = "#fff";
    g.beginPath(); g.arc(32, 22, 15, 0, 7); g.fill();
    g.beginPath(); g.roundRect(14, 40, 36, 80, 12); g.fill();
    g.fillRect(17, 112, 12, 84); g.fillRect(35, 112, 12, 84);
    if (seed % 2) { g.fillRect(48, 70, 12, 26); }  // a shopping bag
  });
}
// light coming in through a window: two sheets (from the top and bottom of the glass) and the patch on the floor
function sunShaft(ww, top, bottom, k = .95, skew = .7) {
  const grad = canvasTex(4, 128, (g, w, h) => {
    const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, "rgba(255,255,255,.9)"); gr.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = gr; g.fillRect(0, 0, w, h);
  });
  const patch = canvasTex(128, 96, (g, w, h) => {
    g.fillStyle = "rgba(255,255,255,.75)"; g.fillRect(0, 0, w, h);
    g.clearRect(w / 2 - 3, 0, 6, h);  // the mullion's shadow
  });
  const mat = new THREE.MeshBasicMaterial({ map: grad, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false });
  const pmat = new THREE.MeshBasicMaterial({ map: patch, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, fog: false });
  const g = new THREE.Group(), hw = ww / 2;
  const sheet = (y) => {
    const z = y * k, geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.Float32BufferAttribute([-hw, y, .15, hw, y, .15, hw + skew * y / top, .03, z, -hw + skew * y / top, .03, z], 3));
    geo.setAttribute("uv", new THREE.Float32BufferAttribute([0, 1, 1, 1, 1, 0, 0, 0], 2)); geo.setIndex([0, 2, 1, 0, 3, 2]);
    return new THREE.Mesh(geo, mat);
  };
  g.add(sheet(top), sheet(bottom));
  const pgeo = new THREE.BufferGeometry(), zn = bottom * k, zf = top * k, sn = skew * bottom / top;
  pgeo.setAttribute("position", new THREE.Float32BufferAttribute([-hw + sn, .025, zn, hw + sn, .025, zn, hw + skew, .025, zf, -hw + skew, .025, zf], 3));
  pgeo.setAttribute("uv", new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2)); pgeo.setIndex([0, 1, 2, 0, 2, 3]);
  g.add(new THREE.Mesh(pgeo, pmat));
  g.renderOrder = 2;
  return { group: g, set(color, a) { mat.color.setHex(color); pmat.color.setHex(color); mat.opacity = a; pmat.opacity = a * .55; g.visible = a > 0; } };
}

// lamps of the room (desk pendants, floor lamps): on in the evening, almost off in daylight
const LAMPS = [];
let lampLevel = 1;
function lampMats() {
  const on = lampLevel > .5;
  if (shared.pbM) shared.pbM.color.setHex(on ? 0xfff0d0 : 0x77736a);
  if (shared.bulbM) shared.bulbM.color.setHex(on ? 0xffe2b0 : 0x8a8478);
}
function addLamp(l) { LAMPS.push(l); l(lampLevel); lampMats(); }
function setLamps(v) { lampLevel = v; for (const l of LAMPS) l(v); lampMats(); }

// ?ora=giorno|sera|notte in the address forces the light, for previews
const ORA = typeof location !== "undefined" ? { giorno: "day", sera: "dusk", notte: "night" }[new URLSearchParams(location.search).get("ora")] : null;
export function dayPart(d = new Date()) {
  if (ORA) return ORA;
  const h = d.getHours() + d.getMinutes() / 60;
  return h >= 7.5 && h < 18.5 ? "day" : (h >= 6 && h < 7.5) || (h >= 18.5 && h < 20.5) ? "dusk" : "night";
}

// ---------------------------------------------------------------- wall screen with the real numbers
const eur = v => v == null ? "—" : Number(v).toLocaleString("it-IT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });
const usd = v => v == null ? "—" : "$" + Number(v).toFixed(2);
function drawScreen(g, w, h, { title, sub, accent, kpi }) {
  const bg = g.createLinearGradient(0, 0, w, h); bg.addColorStop(0, "#0a0f1c"); bg.addColorStop(1, shadeHex(accent, .25));
  g.fillStyle = bg; g.fillRect(0, 0, w, h);
  g.strokeStyle = shadeHex(accent, .45); g.lineWidth = 2;
  for (let i = 0; i < 5; i++) { g.beginPath(); for (let x = 0; x <= w; x += 16) g.lineTo(x, h * .9 - Math.sin(x / 110 + i) * 14 - i * 12); g.stroke(); }
  g.textBaseline = "middle"; g.textAlign = "center";
  g.fillStyle = "#fff"; g.font = "700 64px 'Chakra Petch',sans-serif"; g.fillText(title, w / 2, h * .42);
  g.fillStyle = hexStr(accent); g.font = "600 32px 'Chakra Petch',sans-serif"; g.fillText(sub, w / 2, h * .6);
  if (!kpi) return;
  const day = kpi.ai_day_usd || 0, used = day ? kpi.ai_today_usd / day : 0;
  const tiles = [
    ["RISULTATI REALI", eur(kpi.revenue_eur), "#7dffb0"],
    ["ULTIMI 30 GIORNI", `${eur(kpi.revenue_30d)} · ${kpi.sales_30d} voci`, "#7dffb0"],
    ["COSTO AI OGGI", `${usd(kpi.ai_today_usd)} / ${usd(day)}`, used > .85 ? "#ff5d73" : used > .6 ? "#ffb020" : "#3ecfb2"],
    ["STRATEGIE LIVE", `${kpi.live_products} ${kpi.live_products === 1 ? "strategia" : "strategie"}`, "#f5b83d"],
  ];
  const tw = w * .29, th = h * .38;
  tiles.forEach(([lab, val, col], i) => {
    const x = i < 2 ? w * .015 : w - w * .015 - tw, y = h * .07 + (i % 2) * (th + h * .08);
    g.fillStyle = "rgba(0,0,0,.45)"; g.fillRect(x, y, tw, th);
    g.fillStyle = col; g.fillRect(x, y, 6, th);
    g.textAlign = "left";
    g.fillStyle = "#a9b4c8"; g.font = "600 30px 'Chakra Petch',sans-serif"; g.fillText(lab, x + 24, y + th * .28);
    g.fillStyle = col; g.font = `700 ${val.length > 18 ? 40 : val.length > 13 ? 48 : 58}px 'Chakra Petch',sans-serif`; g.fillText(val, x + 24, y + th * .68, tw - 36);
  });
}

// the wall screen during a celebration: rotating golden rays, sparkles, a big message
function drawParty(g, w, h, { text, line, accent }, now) {
  const t = now / 1000;
  g.fillStyle = "#0a0716"; g.fillRect(0, 0, w, h);
  g.save(); g.translate(w / 2, h / 2); g.rotate(t * .4);
  for (let i = 0; i < 18; i++) {
    g.rotate(Math.PI / 9); g.fillStyle = i % 2 ? "rgba(245,184,61,.22)" : shadeHex(accent, .5) + "55";
    g.beginPath(); g.moveTo(0, 0); g.lineTo(w, -90); g.lineTo(w, 90); g.closePath(); g.fill();
  }
  g.restore();
  const r = seeded(Math.floor(t * 5) + 1);
  for (let i = 0; i < 70; i++) { g.fillStyle = ["#f5b83d", "#ffffff", "#ff5d73", "#3ecfb2", "#b48cff"][i % 5]; const s = 3 + r() * 7; g.fillRect(r() * w, r() * h, s, s); }
  g.textAlign = "center"; g.textBaseline = "middle";
  const pulse = 1 + Math.sin(t * 6) * .03;
  g.save(); g.translate(w / 2, h * .42); g.scale(pulse, pulse);
  g.font = "700 150px 'Chakra Petch',sans-serif"; g.lineWidth = 14; g.strokeStyle = "#2a1600"; g.strokeText(text, 0, 0, w * .94);
  g.fillStyle = "#ffd36b"; g.fillText(text, 0, 0, w * .94);
  g.restore();
  if (line) { g.font = "600 56px 'Chakra Petch',sans-serif"; g.fillStyle = "#ffffff"; g.fillText(line, w / 2, h * .8, w * .9); }
}

// shop sign on the back wall of the sales room: a lightbox with the shop's name and a clock-and-coin mark
function lightbox(accent) {
  const c = document.createElement("canvas"); c.width = 1024; c.height = 256;
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const draw = (name = "IL NEGOZIO") => {
    const g = c.getContext("2d"), w = c.width, h = c.height;
    const bg = g.createLinearGradient(0, 0, w, 0); bg.addColorStop(0, shadeHex(accent, .35)); bg.addColorStop(1, shadeHex(accent, .7));
    g.fillStyle = bg; g.fillRect(0, 0, w, h);
    g.strokeStyle = "rgba(255,255,255,.5)"; g.lineWidth = 6; g.strokeRect(14, 14, w - 28, h - 28);
    g.fillStyle = "#fff"; g.beginPath(); g.arc(140, h / 2, 70, 0, 7); g.fill();
    g.strokeStyle = shadeHex(accent, .4); g.lineWidth = 14; g.lineCap = "round"; g.beginPath(); g.moveTo(140, h / 2 - 42); g.lineTo(140, h / 2 + 4); g.lineTo(172, h / 2 + 22); g.stroke();
    g.fillStyle = "#f5b83d"; g.beginPath(); g.arc(196, h / 2 - 54, 32, 0, 7); g.fill();
    g.fillStyle = "#1f2937"; g.font = "900 40px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText("€", 196, h / 2 - 52);
    g.fillStyle = "#fff"; g.textAlign = "left"; g.font = "700 108px 'Chakra Petch','Trebuchet MS',sans-serif";
    g.fillText(String(name).slice(0, 22), 260, h / 2 + 6, w - 290);
    tex.needsUpdate = true;
  };
  draw();
  const group = new THREE.Group();
  const box = new THREE.Mesh(new THREE.BoxGeometry(3.3, .86, .2), new THREE.MeshStandardMaterial({ color: 0x15161c, metalness: .6, roughness: .35 })); group.add(box);
  const face = new THREE.Mesh(new THREE.PlaneGeometry(3.2, .8), new THREE.MeshBasicMaterial({ map: tex, color: 0xb0b0b0, toneMapped: false, fog: false }));
  face.position.z = .105; group.add(face);
  return { group, draw };
}

// ---------------------------------------------------------------- room: floor, walls with windows, decor
// Dollhouse cut-away: a wall hides itself when the camera is outside it, so the view is never blocked.
// weather inside the rooms: how much sun, shafts, clouds and grey the outside gets
const WEATHER = {
  clear: { sun: 1, shaft: 1, cloud: 0, tint: 0, label: "sereno" },
  clouds: { sun: .65, shaft: .3, cloud: .85, tint: .25, label: "nuvoloso" },
  fog: { sun: .5, shaft: 0, cloud: .6, tint: .55, fog: true, label: "nebbia" },
  rain: { sun: .45, shaft: 0, cloud: .9, tint: .4, rain: true, label: "pioggia" },
  storm: { sun: .3, shaft: 0, cloud: 1, tint: .6, rain: true, storm: true, label: "temporale" },
  snow: { sun: .6, shaft: .15, cloud: .8, tint: .15, snow: true, label: "neve" },
};

// back-right corner: the plant grows with the visits, a glass jar fills with coins as real money comes in,
// and a board on the right wall ticks off the milestones. Only real numbers: with nothing, they stay small.
function growthCorner(scene, { x1, z0, plantObj, accent }) {
  const jar = new THREE.Group(); jar.position.set(3.1, 0, z0 + .9); scene.add(jar);
  const wood = new THREE.MeshStandardMaterial({ color: 0x6b4a33, roughness: .6 });
  const base = new THREE.Mesh(new THREE.CylinderGeometry(.42, .46, .12, 32), wood); base.position.y = .06; jar.add(base);
  const glass = new THREE.Mesh(new THREE.CylinderGeometry(.36, .36, 1.1, 32, 1, true), new THREE.MeshPhysicalMaterial({ color: 0xdff4ff, roughness: .05, transparent: true, opacity: .25, clearcoat: 1, depthWrite: false, side: THREE.DoubleSide }));
  glass.position.y = .67; jar.add(glass);
  const lid = new THREE.Mesh(new THREE.CylinderGeometry(.38, .38, .06, 32), new THREE.MeshStandardMaterial({ color: 0xc8a046, metalness: .9, roughness: .25 })); lid.position.y = 1.25; jar.add(lid);
  const coinM = new THREE.MeshStandardMaterial({ color: 0xe8b04a, metalness: 1, roughness: .25 }), coinG = new THREE.CylinderGeometry(.13, .13, .03, 18);
  const coins = [];
  for (let i = 0; i < 34; i++) {
    const c = new THREE.Mesh(coinG, coinM); const a = i * 2.4, r = (i % 3) * .1;
    c.position.set(Math.cos(a) * r, .14 + Math.floor(i / 3) * .085, Math.sin(a) * r); c.rotation.set((i % 5 - 2) * .12, a, (i % 3 - 1) * .1); c.visible = false; jar.add(c); coins.push(c);
  }
  const cv = document.createElement("canvas"); cv.width = 680; cv.height = 440;
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
  const board = new THREE.Group(); board.position.set(6.5, 3.62, z0 + .16); scene.add(board);  // above the bookcase
  board.add(new THREE.Mesh(new THREE.BoxGeometry(2.3, 1.42, .06), new THREE.MeshStandardMaterial({ color: 0x15171c, metalness: .5, roughness: .4 })));
  const face = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 1.33), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false, color: 0xd0d0d0 })); face.position.z = .035; board.add(face);
  const draw = items => {
    const g = cv.getContext("2d"), w = cv.width;
    g.fillStyle = "#0f172a"; g.fillRect(0, 0, w, cv.height);
    g.fillStyle = "#f5b83d"; g.font = "700 38px 'Chakra Petch',sans-serif"; g.fillText("TRAGUARDI", 30, 56);
    items.slice(0, 6).forEach(([l, ok], i) => {
      const y = 80 + i * 58;
      g.fillStyle = ok ? "#14532d" : "#1e293b"; g.fillRect(30, y, w - 60, 48);
      g.fillStyle = ok ? "#7dffb0" : "#64748b"; g.font = "600 28px sans-serif"; g.fillText((ok ? "✓  " : "○  ") + l, 46, y + 34);
    });
    tex.needsUpdate = true;
  };
  draw([]);
  let sig = "", plantK = 1, plantGoal = 1;
  return {
    set({ visits = 0, revenue = 0, items = [] } = {}) {
      if (!items.length) items = ["Prima strategia in paper trading", "Prima strategia live", "Primo segnale", "Primo guadagno reale", "10 risultati registrati", "100 € di guadagni"].map(l => [l, false]);
      plantGoal = .75 + Math.min(1.5, Math.log10(1 + visits) * .75);  // 0 visits: small; ~100: big; 1000+: huge
      const n = revenue > 0 ? Math.min(coins.length, Math.ceil(Math.log2(1 + revenue) * 4)) : 0;
      coins.forEach((c, i) => c.visible = i < n);
      const s = JSON.stringify(items); if (s !== sig) { sig = s; draw(items); }
    },
    tick(dt) { plantK += (plantGoal - plantK) * Math.min(1, dt * .8); if (plantObj) plantObj.scale.setScalar(plantK); },
  };
}

// season decor, from the date: Christmas, Halloween, Carnival, summer. Garland along the back wall plus a corner piece.
export function seasonOf(d = new Date()) {
  const md = (d.getMonth() + 1) * 100 + d.getDate();
  const q = typeof location !== "undefined" ? new URLSearchParams(location.search).get("stagione") : null;
  if (q) return q;
  if (md >= 1201 || md <= 106) return "natale";
  if (md >= 1020 && md <= 1102) return "halloween";
  if (md >= 201 && md <= 304) return "carnevale";
  if (md >= 701 && md <= 831) return "estate";
  return null;
}
function seasonDecor(scene, { x0, x1, z0, z1, frontPlant }) {
  const name = seasonOf();
  const g = new THREE.Group(); scene.add(g);
  const bulbs = [];
  if (!name) return { name, tick() {} };
  const M = (geo, m, x, y, z, p = g) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); o.castShadow = true; p.add(o); return o; };
  const std = (c, o = {}) => new THREE.MeshStandardMaterial({ color: c, roughness: .7, ...o });
  const COLS = { natale: [0xff5d73, 0xffd36b, 0x4da3ff, 0x7dffb0, 0xffffff], halloween: [0xff8a1f, 0xb06bff, 0xff8a1f, 0x7dff5a],
                 carnevale: [0xff5d73, 0xffd36b, 0x4da3ff, 0x7dffb0, 0xb48cff], estate: [0xffd36b, 0x4de3ff] }[name] || [0xffffff];
  if (name !== "estate") for (let x = x0 + .4, i = 0; x <= x1 - .4; x += .45, i++) {  // garland under the ceiling of the back wall
    bulbs.push(M(new THREE.SphereGeometry(.06, 8, 6), new THREE.MeshBasicMaterial({ color: COLS[i % COLS.length], toneMapped: false }), x, 4.72 - Math.abs(Math.sin(x * 1.1)) * .25, z0 + .3));
  }
  const at = new THREE.Group(); at.position.set(x1 - 1.4, 0, z0 + 1.3); at.scale.setScalar(.8); g.add(at);  // back-right corner
  if (frontPlant) frontPlant.visible = false;
  if (name === "natale") {
    M(new THREE.CylinderGeometry(.12, .15, .5, 12), std(0x6b4423), 0, .25, 0, at);
    [[1.1, 1.3, 1], [.9, 1.1, 1.75], [.65, .9, 2.4]].forEach(([r, h, y]) => M(new THREE.ConeGeometry(r, h, 24), std(0x1f6b3a, { roughness: .9 }), 0, y, 0, at));
    M(new THREE.OctahedronGeometry(.16), new THREE.MeshBasicMaterial({ color: 0xffd36b, toneMapped: false }), 0, 3, 0, at);
    for (let k = 0; k < 34; k++) { const y = .7 + Math.random() * 2, r = (2.85 - y) * .45 + .05, a = Math.random() * 7; bulbs.push(M(new THREE.SphereGeometry(.045, 8, 6), new THREE.MeshBasicMaterial({ color: COLS[k % 5], toneMapped: false }), Math.cos(a) * r, y, Math.sin(a) * r, at)); }
    for (let k = 0; k < 4; k++) M(new THREE.BoxGeometry(.38, .3, .38), std([0xd84a4a, 0x2e86de, 0xf5b83d, 0x16a34a][k]), Math.cos(k * 1.6) * .9, .15, Math.sin(k * 1.6) * .9, at);
    const l = new THREE.PointLight(0xffd29a, 5, 5); l.position.set(0, 2, .8); at.add(l);
  } else if (name === "halloween") {
    const face = canvasTex(256, 128, (c, w, h) => { c.fillStyle = "#e8771c"; c.fillRect(0, 0, w, h); c.fillStyle = "#2a1300"; for (const x of [80, 176]) { c.beginPath(); c.moveTo(x - 18, 56); c.lineTo(x + 18, 56); c.lineTo(x, 30); c.fill(); } c.beginPath(); c.moveTo(70, 80); for (let x = 70; x <= 186; x += 16) c.lineTo(x, x % 32 ? 96 : 84); c.lineTo(186, 80); c.fill(); });
    [[0, 0, .5], [.75, .4, .35], [-.55, .55, .3]].forEach(([x, z, r]) => {
      const p = M(new THREE.SphereGeometry(r, 24, 16), new THREE.MeshStandardMaterial({ map: face, roughness: .6, emissive: 0x401800, emissiveIntensity: .4 }), x, r * .85, z, at); p.scale.y = .85; p.rotation.y = -.6;
      M(new THREE.CylinderGeometry(.04, .05, .14, 8), std(0x3f6b2a), x, r * 1.6, z, at);
    });
    const l = new THREE.PointLight(0xff8a1f, 4, 4); l.position.set(0, .8, .8); at.add(l);
  } else if (name === "carnevale") {
    for (let k = 0; k < 14; k++) { const s = M(new THREE.PlaneGeometry(.12, 1.6 + Math.random()), new THREE.MeshBasicMaterial({ color: COLS[k % 5], side: THREE.DoubleSide }), x0 + 2 + k * 1.9, 4.1, z0 + .35); s.rotation.z = (Math.random() - .5) * .3; }
    M(new THREE.SphereGeometry(.45, 24, 16), std(0xff5d73), 0, .45, 0, at); M(new THREE.SphereGeometry(.3, 24, 16), std(0x4da3ff), .7, .3, .3, at);
  } else if (name === "estate") {  // a standing fan that turns
    M(new THREE.CylinderGeometry(.25, .3, .06, 20), std(0xf2f2f2), 0, .03, 0, at); M(new THREE.CylinderGeometry(.03, .03, 1.3, 8), std(0xd8dde6, { metalness: .8 }), 0, .7, 0, at);
    const hub = new THREE.Group(); hub.position.set(0, 1.4, .1); at.add(hub);
    M(new THREE.TorusGeometry(.42, .015, 6, 40), std(0xd8dde6, { metalness: .8 }), 0, 0, 0, hub);
    for (let k = 0; k < 3; k++) { const b = M(new THREE.BoxGeometry(.12, .36, .01), new THREE.MeshStandardMaterial({ color: 0x4de3ff, transparent: true, opacity: .8 }), 0, .18, .02, hub); b.geometry.translate(0, 0, 0); const r = new THREE.Group(); r.rotation.z = k * 2.094; hub.add(r); r.add(b); }
    bulbs.push(hub); hub.userData.fan = true;
    M(new THREE.SphereGeometry(.3, 24, 16), std(0xffd36b), .8, .3, .4, at);
  }
  shade(g);
  return {
    name,
    tick(dt, t) { bulbs.forEach((b, i) => { if (b.userData.fan) b.rotation.z += dt * 9; else b.visible = Math.sin(t * 2.5 + i * 1.7) > -.35; }); },
  };
}

// style: "lab" (product room: glass boards, blueprints, flasks), "shop" (sales room: shop window on the street, sign,
// display shelves), "studio" (social room: wall of sticky notes, ring light, coloured lights). Without it: plain office.
export function room(scene, { w = 30, d = 20, z0 = -8.5, h = 5.2, wall = 0x1a2130, floor = 0x6b4a33, accent = 0x3ecfb2, title = "CRYPTO MACHINE", sub = "", sun = null, fill = null, sign = "", style = null, theme = null } = {}) {
  const x0 = -w / 2, x1 = w / 2, z1 = z0 + d;
  const neon = theme === "neon"; THEME = theme;  // dark exchange look: navy glass floor with a blue grid, LED strips, chart monitors, always night
  const floorMat = neon
    ? new THREE.MeshStandardMaterial({ map: floorTex("neon", [w / 4, d / 4]), roughness: .16, metalness: .55 })
    : style
    ? new THREE.MeshStandardMaterial({ map: floorTex(style, [w / 4, d / 4]), roughness: style === "studio" ? .55 : .3, metalness: .08 })
    : new THREE.MeshStandardMaterial({ map: woodPlanks(floor, 8, [w / 4, d / 4]), roughness: .28, metalness: .12 });  // lacquered parquet
  const fl = new THREE.Mesh(new THREE.PlaneGeometry(w, d), floorMat);
  fl.rotation.x = -Math.PI / 2; fl.position.set(0, 0, (z0 + z1) / 2); fl.receiveShadow = true; scene.add(fl);
  // round rug under the central piece, with a glowing ring in the accent colour
  const rug = new THREE.Mesh(new THREE.CircleGeometry(5.2, 64), new THREE.MeshStandardMaterial({ color: neon ? 0x060d20 : 0x151b28, roughness: neon ? .25 : 1, metalness: neon ? .5 : 0 }));
  rug.rotation.x = -Math.PI / 2; rug.position.set(0, .012, 1); rug.receiveShadow = true; scene.add(rug);
  const ring = new THREE.Mesh(new THREE.RingGeometry(5, neon ? 5.18 : 5.12, 96), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: neon ? .95 : .55, toneMapped: !neon }));
  ring.rotation.x = -Math.PI / 2; ring.position.set(0, .016, 1); scene.add(ring);
  if (neon) for (const [r0, r1, op] of [[5.35, 5.4, .45], [4.3, 4.33, .3]]) {
    const rr = new THREE.Mesh(new THREE.RingGeometry(r0, r1, 96), new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: op, toneMapped: false }));
    rr.rotation.x = -Math.PI / 2; rr.position.set(0, .017, 1); scene.add(rr);
  }

  const wallMat = neon ? new THREE.MeshStandardMaterial({ color: 0x0a1226, roughness: .5, metalness: .4, emissive: 0x040a1c })
    : new THREE.MeshStandardMaterial({ color: wall, roughness: .92 });
  const trimMat = new THREE.MeshStandardMaterial({ color: 0x0c0f16, roughness: .6, metalness: .3 });
  const ledMat = new THREE.MeshBasicMaterial({ color: accent, toneMapped: !neon });
  const skies = {};
  const skyTex = mode => { if (!skies[mode]) { skies[mode] = skyline(accent, mode); skies[mode].repeat.set(.45, 1); } return skies[mode]; };
  const glassMat = new THREE.MeshBasicMaterial({ map: skyTex("night"), fog: false });
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x2b3140, roughness: .4, metalness: .7 });
  const walls = [], clouds = [], planes = [], shafts = [], walkers = [];
  // weather on the glass: rain streaks or snowflakes (hidden until the real weather says so)
  const rainTex = canvasTex(256, 256, (g, w, h) => {
    for (let i = 0; i < 220; i++) { const x = Math.random() * w, y = Math.random() * h, l = 14 + Math.random() * 40; g.strokeStyle = `rgba(210,228,255,${.45 + Math.random() * .5})`; g.lineWidth = 2.2; g.beginPath(); g.moveTo(x, y); g.lineTo(x - 2, y + l); g.stroke(); }
    for (let i = 0; i < 70; i++) { g.fillStyle = "rgba(225,238,255,.8)"; g.beginPath(); g.arc(Math.random() * w, Math.random() * h, 1 + Math.random() * 2.5, 0, 7); g.fill(); }
  }, [1, 1]);
  const snowTex = canvasTex(256, 256, (g, w, h) => {
    for (let i = 0; i < 160; i++) { g.fillStyle = `rgba(255,255,255,${.6 + Math.random() * .4})`; g.beginPath(); g.arc(Math.random() * w, Math.random() * h, 1.5 + Math.random() * 3, 0, 7); g.fill(); }
  }, [1, 1]);
  const rainMat = new THREE.MeshBasicMaterial({ map: rainTex, transparent: true, depthWrite: false, fog: false, opacity: .9 });
  const snowMat = new THREE.MeshBasicMaterial({ map: snowTex, transparent: true, depthWrite: false, fog: false });
  const wxPanes = [];
  const addWx = (g, x, y, w, hh) => {
    for (const mat of [rainMat, snowMat]) {
      const m = new THREE.Mesh(new THREE.PlaneGeometry(w, hh), mat); m.position.set(x, y, .136); m.renderOrder = 3; m.visible = false; g.add(m); wxPanes.push(m);
    }
  };
  const streets = {};
  const streetMat = new THREE.MeshBasicMaterial({ fog: false });
  const streetTx = mode => streets[mode] || (streets[mode] = streetTex(accent, mode));
  const walkerMat = [0, 1].map(i => new THREE.MeshBasicMaterial({ map: walkerTex(i), color: 0x1a1d24, transparent: true, depthWrite: false, fog: false }));
  const cloudBase = cloudTex();
  const planeBody = new THREE.MeshBasicMaterial({ color: 0x0b0d14, fog: false });
  // axis/limit/sign: the camera beyond this plane (on the outside) hides the wall
  const mk = (len, pos, rotY, axis, limit, sign, windows, front = null) => {
    const g = new THREE.Group(); g.position.copy(pos); g.rotation.y = rotY; scene.add(g);
    const body = new THREE.Mesh(new THREE.BoxGeometry(len, h, .25), wallMat); body.position.y = h / 2; body.receiveShadow = true; g.add(body);
    const base = new THREE.Mesh(new THREE.BoxGeometry(len, .18, .06), trimMat); base.position.set(0, .09, .15); g.add(base);
    const led = new THREE.Mesh(new THREE.BoxGeometry(len, .04, .03), ledMat); led.position.set(0, h - .25, .15); g.add(led);
    if (neon) {  // glowing skirting and vertical light blades
      const low = new THREE.Mesh(new THREE.BoxGeometry(len, .03, .03), ledMat); low.position.set(0, .2, .19); g.add(low);
      for (let x = -len / 2 + 1; x < len / 2 - .5; x += len / Math.max(2, Math.round(len / 5))) {
        if (windows.some(wx => Math.abs(wx - x) < 2.2) || (front && Math.abs((front.x || 0) - x) < front.w / 2 + .3)) continue;
        const bl = new THREE.Mesh(new THREE.BoxGeometry(.035, h - .7, .03), ledMat); bl.position.set(x, h / 2 - .05, .15); g.add(bl);
      }
    }
    for (const wx of windows) {
      const win = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 2.6), glassMat); win.position.set(wx, 2.75, .131); g.add(win);
      const ct = cloudBase.clone(); ct.needsUpdate = true; ct.repeat.set(.45, 1); ct.offset.x = Math.random();
      const cm = new THREE.MeshBasicMaterial({ map: ct, transparent: true, depthWrite: false, fog: false, opacity: .5 });
      const cl = new THREE.Mesh(new THREE.PlaneGeometry(3.4, 2.6), cm); cl.position.set(wx, 2.75, .133); g.add(cl);
      clouds.push({ tex: ct, mat: cm, speed: .004 + Math.random() * .004 });
      const ap = new THREE.Group(); ap.position.set(wx, 3.7, .135); ap.visible = false; g.add(ap);  // airplane crossing the window
      const fus = new THREE.Mesh(new THREE.PlaneGeometry(.16, .025), planeBody); ap.add(fus);
      const wing = new THREE.Mesh(new THREE.PlaneGeometry(.05, .07), planeBody); wing.position.x = .01; ap.add(wing);
      const blink = new THREE.Mesh(new THREE.CircleGeometry(.014, 8), new THREE.MeshBasicMaterial({ color: 0xff3b3b, fog: false, toneMapped: false })); blink.position.set(.02, .035, .001); ap.add(blink);
      planes.push({ g: ap, blink, x0: wx, t: Math.random() * 60, dir: Math.random() < .5 ? -1 : 1, period: 40 + Math.random() * 40 });
      for (const [sx, sy, px, py] of [[3.6, .12, 0, 1.36], [3.6, .12, 0, -1.36], [.12, 2.8, 1.74, 0], [.12, 2.8, -1.74, 0], [.07, 2.6, 0, 0]]) {
        const f = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, .1), frameMat); f.position.set(wx + px, 2.75 + py, .16); g.add(f);
      }
      const sill = new THREE.Mesh(new THREE.BoxGeometry(3.8, .08, .35), trimMat); sill.position.set(wx, 1.4, .25); g.add(sill);
      const sh = sunShaft(3.4, 4.05, 1.45); sh.group.position.x = wx; g.add(sh.group); shafts.push(sh);
      addWx(g, wx, 2.75, 3.4, 2.6);
    }
    if (front) {  // shop window on the street: almost floor to ceiling, people walking by outside
      const fw = front.w, fy = front.y, fh = front.h;
      const fx = front.x || 0;
      const glass = new THREE.Mesh(new THREE.PlaneGeometry(fw, fh), streetMat); glass.position.set(fx, fy, .131); g.add(glass);
      for (let i = 0; i < 3; i++) {
        const m = new THREE.Mesh(new THREE.PlaneGeometry(.55, 1.72), walkerMat[i % 2]); m.position.set(fx, .9, .134); g.add(m);
        walkers.push({ m, x: (i / 3 - .5) * fw, cx: fx, v: (i % 2 ? -1 : 1) * (.55 + i * .12), half: fw / 2 - .3 });
      }
      const pane = new THREE.Mesh(new THREE.PlaneGeometry(fw, fh), new THREE.MeshStandardMaterial({ color: 0xbfd9ff, transparent: true, opacity: .07, roughness: .05, metalness: .2, depthWrite: false }));
      pane.position.set(fx, fy, .137); g.add(pane);
      const fb = (sx, sy, px, py) => { const f = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, .12), frameMat); f.position.set(fx + px, fy + py, .17); g.add(f); };
      fb(fw + .2, .14, 0, fh / 2); fb(fw + .2, .14, 0, -fh / 2); fb(.14, fh, fw / 2, 0); fb(.14, fh, -fw / 2, 0); fb(.09, fh, fw / 6, 0); fb(.09, fh, -fw / 6, 0);
      const plinth = new THREE.Mesh(new THREE.BoxGeometry(fw + .2, fy - fh / 2, .3), trimMat); plinth.position.set(fx, (fy - fh / 2) / 2, .2); g.add(plinth);
      if (front.sign) { const ns = neonSign(front.sign, accent); ns.scale.setScalar(.62); ns.position.set(fx + fw / 4, fy + fh * .25, .3); g.add(ns); }
      const sh = sunShaft(fw, fy + fh / 2, fy - fh / 2 + .4, .55, .5); sh.group.position.x = fx; g.add(sh.group); shafts.push(sh);
      addWx(g, fx, fy, fw, fh);
    }
    walls.push({ g, axis, limit, sign });
    return g;
  };
  if (style === "shop") mk(w, new THREE.Vector3(0, 0, z0), 0, "z", z0, -1, [w * .34], { x: -w * .375, w: 5.6, h: 3.75, y: 2.2, sign });
  else mk(w, new THREE.Vector3(0, 0, z0), 0, "z", z0, -1, [-w * .34, w * .34]);
  mk(d, new THREE.Vector3(x0, 0, (z0 + z1) / 2), Math.PI / 2, "x", x0, -1, [-d * .22, d * .22]);
  mk(d, new THREE.Vector3(x1, 0, (z0 + z1) / 2), -Math.PI / 2, "x", x1, 1, [-d * .22, d * .22]);
  mk(w, new THREE.Vector3(0, 0, z1), Math.PI, "z", z1, 1, [-w * .3, 0, w * .3]);
  if (neon) [walls[1], walls[2]].forEach((wl, i) => { const cp = chartPanel(accent, 3 + i, 3.4, 2); cp.position.set(0, 2.9, .2); wl.g.add(cp); });

  // big screen on the back wall: logo in the middle, real numbers on the sides
  const tv = new THREE.Group(); tv.position.set(0, 3.2, z0 + .16); scene.add(tv);
  const bezel = new THREE.Mesh(new THREE.BoxGeometry(8.9, 2.5, .12), trimMat); tv.add(bezel);
  const sc = document.createElement("canvas"); sc.width = 1792; sc.height = 480;
  const screenTex = new THREE.CanvasTexture(sc); screenTex.colorSpace = THREE.SRGBColorSpace; screenTex.anisotropy = 4;
  let subLine = sub;
  const paint = kpi => { drawScreen(sc.getContext("2d"), sc.width, sc.height, { title, sub: subLine, accent, kpi }); screenTex.needsUpdate = true; };
  paint(null);
  if (document.fonts) document.fonts.ready.then(() => paint(lastKpi));
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(8.7, 2.33), new THREE.MeshBasicMaterial({ map: screenTex, fog: false, toneMapped: false }));
  scr.position.z = .065; tv.add(scr);
  walls[0].extra = tv;
  // LED ticker above the big screen: real crypto prices (see priceTicker below)
  const ticker = priceTicker(tv, { x: 0, y: 1.6, z: 0, width: 8.7, demo: new URLSearchParams(location.search).has("demo") });
  let shopSign = null;
  if (style === "shop") { shopSign = lightbox(accent); shopSign.group.position.set(-6.5, 3.6, z0 + .2); scene.add(shopSign.group); walls[0].extra2 = shopSign.group; }
  else if (sign) { const ns = neonSign(sign, accent); ns.position.set(-6.5, 3.55, z0 + .17); tv.parent.add(ns); walls[0].extra2 = ns; }
  let lastKpi = null, lastSig = "", party = null, partyT = 0;

  // plants in the corners and along the walls
  const corner = [];
  for (const [px, pz, s] of [[x0 + 1.1, z0 + 1.1, 1.2], [x1 - 1.1, z0 + 1.1, 1.2], [x0 + 1.1, z1 - 1.3, 1], [x1 - 1.1, z1 - 1.3, 1]]) {
    const p = plant(s); p.position.set(px, 0, pz); scene.add(p); corner.push(p);
  }
  const growthPlant = plant(1); growthPlant.position.set(-9, 0, z0 + .8); scene.add(growthPlant);  // by the left window
  const growth = growthCorner(scene, { x1, z0, plantObj: growthPlant, accent });
  const season = seasonDecor(scene, { x0, x1, z0, z1, frontPlant: corner[1] });
  const deco = furnish(scene, { x0, x1, z0, z1, accent, style, ledMat });
  shade(scene);

  // light of the time of day: by day the sun comes in through the windows and the lamps are off,
  // in the evening the lamps switch on and the light inside turns warm
  const LIGHT = { day: [0xfff1dc, 1.45, .6], dusk: [0xffb27a, .9, .4], night: [0xb9c8ff, .45, .24] };
  const FILL = { day: [null, 1], dusk: [0xffc99a, .7], night: [0xffc58a, .42] };
  const SHAFT = { day: [0xfff0d2, .14], dusk: [0xff9a55, .12], night: [0x9fb4ff, 0] };
  const HEMI = { day: [0xeaf3ff, .4, 1.3], dusk: [0xffb98a, .35, .9], night: [0xffc58a, .35, .6] };
  let part = null, wx = WEATHER.clear, flashT = 0, wxNow = null;
  const flash = new THREE.PointLight(0xcfe0ff, 0, 45); flash.position.set(0, 6, z0 - 3); scene.add(flash);
  const setTime = (d = new Date(), force = false) => {
    const p = neon ? "night" : dayPart(d); if (p === part && !force) return; part = p;
    glassMat.map = skyTex(p); glassMat.needsUpdate = true;
    streetMat.map = streetTx(p); streetMat.needsUpdate = true;
    for (const wm of walkerMat) wm.color.setHex(p === "day" ? 0x2a2f3a : 0x0b0d12);
    for (const c of clouds) c.mat.opacity = Math.max({ day: .6, dusk: .4, night: .16 }[p], wx.cloud * (p === "night" ? .4 : .9));
    for (const s of shafts) s.set(SHAFT[p][0], SHAFT[p][1] * wx.shaft);
    if (sun) { sun.color.setHex(LIGHT[p][0]); sun.intensity = LIGHT[p][1] * wx.sun; }
    const tint = new THREE.Color(0xffffff).lerp(new THREE.Color(wx.fog ? 0xd5dbe3 : 0x7c8698), wx.tint);
    glassMat.color.copy(tint); streetMat.color.copy(tint);
    for (const m of wxPanes) m.visible = (m.material === rainMat && wx.rain) || (m.material === snowMat && wx.snow);
    scene.environmentIntensity = LIGHT[p][2];
    setLamps({ day: .1, dusk: .8, night: 1 }[p]);
    if (fill) {
      const b = fill.userData.base || (fill.userData.base = { i: fill.intensity, c: fill.color.getHex() });
      fill.color.setHex(FILL[p][0] ?? b.c); fill.intensity = b.i * FILL[p][1];
    }
    const hemi = scene.children.find(o => o.isHemisphereLight);
    if (hemi) {
      const b = hemi.userData.base || (hemi.userData.base = { c: hemi.color.clone(), i: hemi.intensity });
      hemi.color.copy(b.c).lerp(new THREE.Color(HEMI[p][0]), HEMI[p][1]); hemi.intensity = b.i * HEMI[p][2];
    }
  };
  setTime();
  const v = new THREE.Vector3();
  let last = performance.now(), flickT = 0;
  function animate() {  // clouds drift, lights flicker, airplanes cross the windows at dusk and night
    const now = performance.now(), dt = Math.min(.1, (now - last) / 1000); last = now;
    for (const wk of walkers) {
      wk.x += wk.v * dt; if (Math.abs(wk.x) > wk.half) wk.x = -Math.sign(wk.v) * wk.half;
      wk.m.position.x = wk.cx + wk.x; wk.m.position.y = .9 + Math.abs(Math.sin(now / 160 + wk.v * 9)) * .03; wk.m.scale.x = Math.sign(wk.v);
      wk.m.material.opacity = Math.min(1, (wk.half - Math.abs(wk.x)) / .6) * .92;
    }
    if (deco.tick) deco.tick(dt, now / 1000);
    season.tick(dt, now / 1000); growth.tick(dt, now / 1000);
    if (wx.rain) rainTex.offset.y = (rainTex.offset.y - dt * .6) % 1;
    if (wx.snow) { snowTex.offset.y = (snowTex.offset.y - dt * .08) % 1; snowTex.offset.x = Math.sin(now / 1500) * .03; }
    if (wx.storm && (flashT -= dt) <= 0) { flashT = 5 + Math.random() * 9; flash.userData.until = now + 160; }
    flash.intensity = flash.userData.until > now ? 140 : 0;
    if (party) {
      if (now > party.until) { party = null; paint(lastKpi); ledMat.color.setHex(accent); }
      else {
        ledMat.color.setHSL((now / 1500) % 1, .9, .55);
        if ((partyT -= dt) <= 0) { partyT = .2; drawParty(sc.getContext("2d"), sc.width, sc.height, party, now); screenTex.needsUpdate = true; }
      }
    }
    for (const c of clouds) c.tex.offset.x = (c.tex.offset.x + dt * c.speed) % 1;
    if ((flickT -= dt) <= 0) { flickT = 1.5 + Math.random() * 2; const tx = skyTex(part); tx.userData.flicker && tx.userData.flicker(); }
    for (const pl of planes) {
      pl.t += dt; const k = (pl.t % pl.period) / 6;  // 6 s to cross, then a pause
      pl.g.visible = part !== "day" && k < 1;
      if (pl.g.visible) { pl.g.position.x = pl.x0 + (k - .5) * 3.2 * pl.dir; pl.g.scale.x = -pl.dir; pl.blink.visible = Math.sin(pl.t * 9) > .3; }
    }
  }
  return {
    setTime,
    screen(kpi) {
      const sig = JSON.stringify(kpi); if (sig === lastSig) return; lastSig = sig; lastKpi = kpi; if (!party) paint(kpi);
    },
    // the big screen shows a celebration for `secs` seconds, then goes back to the numbers
    celebrate(text, line = "", secs = 60) { party = { text, line, accent, until: performance.now() + secs * 1000 }; partyT = 0; },
    get partying() { return !!party; },
    shopName(name) { if (shopSign) shopSign.draw(name); },
    // real weather of the owner's city: {kind: clear|clouds|fog|rain|storm|snow, city, temp}
    weather(w) {
      wx = WEATHER[w && w.kind] || WEATHER.clear;
      subLine = w && w.city ? `${sub} · ${w.city} ${Math.round(w.temp)}° ${wx.label}` : sub;
      wxNow = w && w.city ? { city: w.city, temp: Math.round(w.temp), label: wx.label, kind: w.kind } : null;
      setTime(new Date(), true); if (!party) paint(lastKpi);
    },
    // things that grow with the real numbers: {visits, revenue, items: [[label, done], ...]}
    growth(g) { growth.set(g); },
    season: season.name,
    get weatherNow() { return wxNow; },
    update(camera) {
      animate();
      ticker.tick();
      v.copy(camera.position);
      for (const wl of walls) {
        const vis = wl.sign < 0 ? v[wl.axis] > wl.limit : v[wl.axis] < wl.limit;
        wl.g.visible = vis; if (wl.extra) wl.extra.visible = vis; if (wl.extra2) wl.extra2.visible = vis;
      }
    },
  };
}

// ---------------------------------------------------------------- furniture: relax corner, bookcase, whiteboard, paintings
function furnish(scene, { x0, x1, z0, z1, accent, style, ledMat }) {
  const g = new THREE.Group(); scene.add(g);
  const M = (geo, m, x, y, z, parent = g) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); parent.add(o); return o; };
  const B = (sx, sy, sz, m, x, y, z, parent = g) => M(new THREE.BoxGeometry(sx, sy, sz), m, x, y, z, parent);
  const std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: .8, ...o });
  const wood = new THREE.MeshStandardMaterial({ map: woodPlanks(0x6e4b2e, 4), roughness: .55 });
  const metal = std(0x9aa3b2, { roughness: .3, metalness: .85 }), dark = std(0x16181d, { roughness: .4, metalness: .3 });

  // relax corner (back right): rug, sofa against the wall, armchair, coffee table, floor lamp
  const rc = new THREE.Group(); rc.position.set(x1 - 3, 0, z0 + 3.9); g.add(rc);
  M(new THREE.PlaneGeometry(4.2, 3.4), std(0x3b2f4a, { roughness: 1 }), 0, .014, 0, rc).rotation.x = -Math.PI / 2;
  const sofaM = std(0x34507a, { roughness: .95 }), cushM = std(0x41618f, { roughness: .95 });
  const sofa = new THREE.Group(); sofa.position.set(1.85, 0, 0); sofa.rotation.y = -Math.PI / 2; rc.add(sofa);  // faces the room
  B(2.4, .38, .9, sofaM, 0, .3, 0, sofa); B(2.4, .6, .22, sofaM, 0, .7, .36, sofa);
  for (const sx of [-1.28, 1.28]) B(.18, .55, .9, sofaM, sx, .45, 0, sofa);
  for (const sx of [-.58, .58]) B(1.12, .14, .7, cushM, sx, .55, -.05, sofa);
  B(.36, .32, .12, std(0xe8b04a, { roughness: .9 }), -.75, .76, .18, sofa).rotation.z = .2;  // throw pillow
  for (const [lx, lz] of [[-1.1, -.35], [1.1, -.35], [-1.1, .35], [1.1, .35]]) M(new THREE.CylinderGeometry(.03, .02, .12, 8), dark, lx, .06, lz, sofa);
  const arm = new THREE.Group(); arm.position.set(-1.5, 0, 0); arm.rotation.y = Math.PI / 2; rc.add(arm);  // armchair facing the sofa
  B(.85, .36, .8, cushM, 0, .3, 0, arm); B(.85, .6, .18, cushM, 0, .65, .32, arm);
  for (const sx of [-.4, .4]) B(.12, .5, .8, cushM, sx, .42, 0, arm);
  B(1.1, .05, .6, wood, .2, .42, 0, rc); for (const [lx, lz] of [[-.3, -.25], [.7, -.25], [-.3, .25], [.7, .25]]) B(.04, .4, .04, metal, lx, .2, lz, rc);
  M(new THREE.CylinderGeometry(.05, .04, .1, 12), std(0xf4efe6, { roughness: .4 }), .4, .5, .1, rc);  // mug on the table
  B(.3, .03, .22, std(0xd84a4a), -.05, .46, -.08, rc).rotation.y = .3;  // magazine
  const lamp = new THREE.Group(); lamp.position.set(1.9, 0, -1.45); rc.add(lamp);
  M(new THREE.CylinderGeometry(.16, .18, .04, 18), dark, 0, .02, 0, lamp); M(new THREE.CylinderGeometry(.015, .015, 1.6, 8), metal, 0, .82, 0, lamp);
  M(new THREE.CylinderGeometry(.14, .24, .3, 18, 1, true), new THREE.MeshStandardMaterial({ color: 0xfff1d6, emissive: 0xffd9a0, emissiveIntensity: .8, side: THREE.DoubleSide, roughness: .9 }), 0, 1.7, 0, lamp);
  const glow = new THREE.PointLight(0xffd29a, 2.2, 4.5); glow.position.set(0, 1.55, 0); lamp.add(glow);
  const shadeM = lamp.children[2].material;
  addLamp(v => { glow.intensity = 2.6 * v; shadeM.emissiveIntensity = .05 + .85 * v; });

  // coffee counter and water cooler against the back wall
  const cc = new THREE.Group(); cc.position.set(x1 - 3.4, 0, z0 + .45); g.add(cc);
  B(1.7, .9, .6, std(0x2a2f3a, { roughness: .6 }), 0, .45, 0, cc); B(1.76, .05, .64, std(0xd9d4c7, { roughness: .3 }), 0, .925, 0, cc);
  const mach = new THREE.Group(); mach.position.set(-.35, .95, 0); cc.add(mach);
  B(.36, .46, .34, std(0x1b1d22, { roughness: .3, metalness: .5 }), 0, .23, 0, mach); B(.36, .08, .34, metal, 0, .5, 0, mach);
  M(new THREE.CircleGeometry(.05, 14), new THREE.MeshBasicMaterial({ color: 0x3ecfb2, toneMapped: false }), .1, .38, .171, mach);
  M(new THREE.CylinderGeometry(.04, .035, .08, 12), std(0xf4efe6, { roughness: .4 }), 0, .04, .1, mach);
  for (let i = 0; i < 4; i++) M(new THREE.CylinderGeometry(.04, .035, .08, 12), std([0xf4efe6, 0xd84a4a, 0x2e86de, 0xe8b04a][i], { roughness: .4 }), .25 + (i % 2) * .1, .99, -.1 + Math.floor(i / 2) * .12, cc);
  M(new THREE.CylinderGeometry(.13, .13, .12, 16), std(0xc8ccd4, { roughness: .2, metalness: .9 }), .62, 1.01, 0, cc);  // sugar/coffee tin
  const wc = new THREE.Group(); wc.position.set(-1.3, 0, 0); cc.add(wc);  // water cooler
  B(.36, 1, .36, std(0xe9ecf1, { roughness: .4 }), 0, .5, 0, wc);
  M(new THREE.CylinderGeometry(.15, .15, .42, 18), new THREE.MeshPhysicalMaterial({ color: 0x8fc7ff, roughness: .05, transparent: true, opacity: .45, clearcoat: 1 }), 0, 1.22, 0, wc);

  // bookcase on the back wall (right of the screen) full of books
  const bc = new THREE.Group(); bc.position.set(6.5, 0, z0 + .3); g.add(bc);
  for (const sx of [-1.18, 1.18]) B(.05, 2.3, .38, wood, sx, 1.15, 0, bc);  // open front: sides, top, back
  B(2.4, .05, .38, wood, 0, 2.28, 0, bc); B(2.4, 2.3, .02, wood, 0, 1.15, -.18, bc);
  const inner = std(0x1f1712, { roughness: .9 });
  for (let r = 0; r < 4; r++) {
    B(2.24, .5, .03, inner, 0, .32 + r * .54, -.16, bc);  // dark back of the shelf
    B(2.3, .04, .36, wood, 0, .06 + r * .54, .01, bc);    // shelf board
    if (style === "lab") { shelfLab(bc, r, std); continue; }
    if (style === "shop") { shelfShop(bc, r, std, accent); continue; }
    let x = -1.05;
    while (x < 1.0) {
      const bw = .05 + Math.random() * .06, bh = .3 + Math.random() * .14;
      if (Math.random() < .12) { x += .12; continue; }
      const book = B(bw, bh, .22, std([0x8e1b2c, 0x2e5c8a, 0xd9a441, 0x2f6b3a, 0x5b3a7a, 0xe8e2d6, 0x1d2230][Math.floor(Math.random() * 7)], { roughness: .7 }), x + bw / 2, .1 + r * .54 + bh / 2, .08, bc);
      if (Math.random() < .07) book.rotation.z = .25;
      x += bw + .006;
    }
  }
  const pl = plant(.5); pl.position.set(.75, 2.3, 0); bc.add(pl);

  // whiteboard with sticky notes and marker lines (back wall, left of the screen); each styled room has its own
  let tick = null;
  if (style === "lab") {
    const gb = glassBoard(accent, 1, 2.8, 1.6); gb.position.set(-6.5, 1.95, z0 + .2); g.add(gb);
    const gb2 = glassBoard(accent, 2, 2.6, 1.5); gb2.position.set(x0 + .2, 2.6, (z0 + z1) / 2); gb2.rotation.y = Math.PI / 2; g.add(gb2);
  } else if (style === "shop") {
    const cb = chalkboard(); cb.position.set(-6.5, 1.85, z0 + .16); g.add(cb);
  } else if (style === "studio") {
    const pw = postItWall(); pw.position.set(-6.45, 1.85, z0 + .15); g.add(pw);
    tick = studioLights(g, { x0, x1, z0, z1, accent, ledMat });
  }
  const wb = new THREE.Group(); wb.position.set(-6.5, 1.9, z0 + .16); if (!style) g.add(wb);
  B(2.8, 1.5, .05, metal, 0, 0, 0, wb); B(2.7, 1.4, .02, std(0xd3d8df, { roughness: .45 }), 0, 0, .03, wb);
  const ink = [0x2e86de, 0xd84a4a, 0x1d2230];
  for (let i = 0; i < 5; i++) B(.6 + Math.random() * .5, .02, .005, std(ink[i % 3], { roughness: .5 }), -.75 + Math.random() * .2, .45 - i * .17, .045, wb);
  const notes = [0xfff176, 0xffab91, 0x80deea, 0xc5e1a5, 0xf8bbd0];
  for (let i = 0; i < 9; i++) {
    const n = B(.2, .2, .008, std(notes[i % 5], { roughness: .9 }), .35 + (i % 3) * .28, .4 - Math.floor(i / 3) * .3, .045, wb);
    n.rotation.z = (Math.random() - .5) * .25;
  }
  B(2.6, .05, .1, metal, 0, -.75, .06, wb);  // marker tray
  for (let i = 0; i < 3; i++) M(new THREE.CylinderGeometry(.012, .012, .13, 8), std(ink[i]), -.3 + i * .18, -.71, .06, wb).rotation.z = Math.PI / 2;

  // two paintings: one on the left wall, one above the sofa side (right wall)
  const art = (seed) => canvasTex(256, 192, (c, w, h) => {
    const r = seeded(seed); c.fillStyle = ["#1d2a44", "#2b1d33", "#14302c"][seed % 3]; c.fillRect(0, 0, w, h);
    for (let i = 0; i < 7; i++) {
      c.globalAlpha = .55 + r() * .4; c.fillStyle = ["#f5b83d", "#3ecfb2", "#ff5d73", "#4da3ff", "#e8e2d6", hexStr(accent)][Math.floor(r() * 6)];
      if (r() < .5) { c.beginPath(); c.arc(r() * w, r() * h, 12 + r() * 50, 0, 7); c.fill(); } else c.fillRect(r() * w, r() * h, 20 + r() * 90, 10 + r() * 60);
    }
    c.globalAlpha = 1;
  });
  for (const [px, py, pz, ry, sd] of [[x0 + .16, 3.3, z0 + 2, Math.PI / 2, 3], [x1 - .16, 3.4, z0 + 2.2, -Math.PI / 2, 8]]) {
    const pf = new THREE.Group(); pf.position.set(px, py, pz); pf.rotation.y = ry; g.add(pf);
    if (style === "studio") { const ic = neonIcon(sd === 3 ? "♥" : "▶", sd === 3 ? 0xff5fa2 : 0x4de3ff); pf.add(ic); continue; }
    B(1.5, 1.15, .05, std(style === "lab" ? 0x9aa3b2 : 0xc9a46a, { roughness: .4, metalness: .4 }), 0, 0, 0, pf);
    M(new THREE.PlaneGeometry(1.36, 1.01), new THREE.MeshStandardMaterial({ map: style === "lab" ? blueprint(sd) : art(sd), roughness: .8 }), 0, 0, .03, pf);
  }
  if (style === "studio") { const rl = ringLight(); rl.position.set(-3.7, 0, z0 + 1.1); g.add(rl); }
  return { tick };
}

// ---- pieces of the styled rooms
const _M = (geo, m, x, y, z, parent) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); parent.add(o); return o; };
// lab: flasks with glowing liquid, jars and labelled boxes on the shelves
function shelfLab(bc, r, std) {
  const y = .08 + r * .54, glassM = new THREE.MeshPhysicalMaterial({ color: 0xdff4ff, roughness: .05, transparent: true, opacity: .35, clearcoat: 1, depthWrite: false });
  const liq = [0x3ecfb2, 0x4da3ff, 0xb48cff, 0xf5b83d];
  for (let i = 0; i < 5; i++) {
    const x = -.9 + i * .44, kind = (i + r) % 3, col = liq[(i + r) % 4];
    const lm = new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: .55, roughness: .3 });
    if (kind === 0) {  // round flask
      _M(new THREE.SphereGeometry(.11, 16, 12), glassM, x, y + .12, 0, bc); _M(new THREE.SphereGeometry(.09, 14, 10, 0, Math.PI * 2, Math.PI * .45, Math.PI * .55), lm, x, y + .12, 0, bc);
      _M(new THREE.CylinderGeometry(.03, .03, .14, 10), glassM, x, y + .29, 0, bc);
    } else if (kind === 1) {  // beaker
      _M(new THREE.CylinderGeometry(.08, .08, .24, 16, 1, true), glassM, x, y + .12, 0, bc); _M(new THREE.CylinderGeometry(.075, .075, .13, 16), lm, x, y + .07, 0, bc);
    } else {  // labelled box
      _M(new THREE.BoxGeometry(.3, .22, .22), std([0xe8e2d6, 0x2e5c8a, 0x2f6b3a][r % 3], { roughness: .8 }), x, y + .11, 0, bc);
      _M(new THREE.PlaneGeometry(.16, .07), std(0xffffff), x, y + .13, .111, bc);
    }
  }
}
// shop: product boxes on display, facing out, with a shelf-edge strip in the shop colour
function shelfShop(bc, r, std, accent) {
  const y = .08 + r * .54, cols = [0x0f766e, 0xf5b83d, 0xb48cff, 0xe8e2d6, 0x2e86de];
  for (let i = 0; i < 4; i++) {
    const c = cols[(i + r * 2) % cols.length];
    _M(new THREE.BoxGeometry(.34, .36 - (i % 2) * .06, .2), std(c, { roughness: .5 }), -.78 + i * .52, y + .18 - (i % 2) * .03, 0, bc);
    _M(new THREE.PlaneGeometry(.22, .05), std(0xffffff), -.78 + i * .52, y + .2, .101, bc);
  }
  _M(new THREE.BoxGeometry(2.3, .035, .02), new THREE.MeshBasicMaterial({ color: accent }), 0, y + .02, .2, bc);
}
// lab: a glass board on standoffs with diagrams drawn in light
function glassBoard(accent, seed, w, h) {
  const g = new THREE.Group(), col = hexStr(accent);
  const draw = canvasTex(512, Math.round(512 * h / w), (c, cw, ch) => {
    const r = seeded(seed * 13);
    c.strokeStyle = col; c.fillStyle = col; c.lineWidth = 3; c.font = "600 20px 'Chakra Petch',sans-serif";
    const labels = seed === 1 ? ["IDEA", "TEST", "VENDITA"] : ["DATI", "PROTOTIPO", "OK"];
    labels.forEach((l, i) => {
      const x = 30 + i * 160, y = 40 + (i % 2) * 30;
      c.strokeRect(x, y, 120, 50); c.fillText(l, x + 14, y + 32);
      if (i < 2) { c.beginPath(); c.moveTo(x + 122, y + 25); c.lineTo(x + 158, y + 25 + ((i + 1) % 2 - i % 2) * 30); c.stroke(); }
    });
    c.beginPath(); for (let x = 30; x < cw - 30; x += 12) c.lineTo(x, ch * .72 - Math.sin(x / 40 + seed) * 22 - (x / cw) * 40 * r()); c.stroke();
    c.beginPath(); c.moveTo(30, ch * .9); c.lineTo(cw - 30, ch * .9); c.moveTo(30, ch * .9); c.lineTo(30, ch * .5); c.stroke();
    c.beginPath(); c.arc(cw * .78, ch * .3, 42, 0, 7); c.stroke(); c.beginPath(); c.arc(cw * .78, ch * .3, 18, 0, 7); c.stroke();
  });
  const pane = new THREE.Mesh(new THREE.BoxGeometry(w, h, .03), new THREE.MeshPhysicalMaterial({ color: 0xcfefff, roughness: .05, transparent: true, opacity: .16, clearcoat: 1, depthWrite: false }));
  g.add(pane);
  const ink = new THREE.Mesh(new THREE.PlaneGeometry(w * .96, h * .94), new THREE.MeshBasicMaterial({ map: draw, transparent: true, color: 0x9a9a9a, toneMapped: false, depthWrite: false, fog: false }));
  ink.position.z = .02; g.add(ink);
  const steel = new THREE.MeshStandardMaterial({ color: 0xc8ccd4, metalness: .9, roughness: .2 });
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) { const s = _M(new THREE.CylinderGeometry(.03, .03, .1, 10), steel, sx * (w / 2 - .12), sy * (h / 2 - .12), -.03, g); s.rotation.x = Math.PI / 2; }
  return g;
}
// lab: framed blueprints instead of paintings
function blueprint(seed) {
  return canvasTex(256, 192, (c, w, h) => {
    const r = seeded(seed);
    c.fillStyle = "#123a6b"; c.fillRect(0, 0, w, h);
    c.strokeStyle = "rgba(255,255,255,.12)"; c.lineWidth = 1;
    for (let x = 0; x < w; x += 16) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, h); c.stroke(); }
    for (let y = 0; y < h; y += 16) { c.beginPath(); c.moveTo(0, y); c.lineTo(w, y); c.stroke(); }
    c.strokeStyle = "#e6f1ff"; c.lineWidth = 2;
    c.strokeRect(40, 40, 110, 80); c.beginPath(); c.moveTo(40, 40); c.lineTo(70, 20); c.lineTo(180, 20); c.lineTo(150, 40); c.moveTo(180, 20); c.lineTo(180, 100); c.lineTo(150, 120); c.stroke();
    c.beginPath(); c.arc(205, 140, 24 + r() * 6, 0, 7); c.stroke();
    for (let i = 0; i < 8; i++) { const a = i / 8 * Math.PI * 2; c.beginPath(); c.moveTo(205 + Math.cos(a) * 24, 140 + Math.sin(a) * 24); c.lineTo(205 + Math.cos(a) * 33, 140 + Math.sin(a) * 33); c.stroke(); }
    c.setLineDash([4, 4]); c.beginPath(); c.moveTo(40, 150); c.lineTo(150, 150); c.stroke(); c.setLineDash([]);
    c.fillStyle = "#e6f1ff"; c.font = "10px monospace"; c.fillText("REV. " + (1 + seed % 4), 20, h - 12);
  });
}
// shop: chalkboard with chalk scribbles in a wooden frame
function chalkboard() {
  const g = new THREE.Group();
  const tex = canvasTex(512, 300, (c, w, h) => {
    c.fillStyle = "#1f2a24"; c.fillRect(0, 0, w, h);
    for (let i = 0; i < 400; i++) { c.fillStyle = `rgba(255,255,255,${Math.random() * .04})`; c.fillRect(Math.random() * w, Math.random() * h, 8, 3); }
    c.fillStyle = "rgba(245,240,230,.9)"; c.font = "700 46px 'Trebuchet MS',sans-serif"; c.fillText("Benvenuti!", 40, 70);
    c.strokeStyle = "rgba(245,240,230,.75)"; c.lineWidth = 4;
    for (let i = 0; i < 4; i++) { c.beginPath(); c.moveTo(48, 120 + i * 42); c.lineTo(70, 120 + i * 42); c.stroke(); c.beginPath(); c.moveTo(90, 120 + i * 42); for (let x = 90; x < 300 + Math.random() * 140; x += 14) c.lineTo(x, 120 + i * 42 + Math.sin(x) * 2); c.stroke(); }
    c.strokeStyle = "rgba(245,184,61,.85)"; c.beginPath(); c.arc(420, 200, 50, 0, 7); c.stroke();
  });
  const wood = new THREE.MeshStandardMaterial({ map: woodPlanks(0x7a5230, 3), roughness: .6 });
  const frame = new THREE.Mesh(new THREE.BoxGeometry(2.8, 1.65, .06), wood); g.add(frame);
  const face = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 1.47), new THREE.MeshStandardMaterial({ map: tex, roughness: .95 })); face.position.z = .035; g.add(face);
  return g;
}
// studio: a big wall of sticky notes, with lines of string between some of them
function postItWall() {
  const g = new THREE.Group(), r = seeded(17), W = 3.7, H = 2.3;
  const cork = new THREE.Mesh(new THREE.BoxGeometry(W, H, .04), new THREE.MeshStandardMaterial({ color: 0x8f877a, roughness: .95 })); g.add(cork);
  const cols = [0xfff176, 0xffab91, 0x80deea, 0xc5e1a5, 0xf8bbd0, 0xffcc80, 0xb39ddb];
  const mats = cols.map(c => new THREE.MeshStandardMaterial({ color: c, roughness: .9 })), geo = new THREE.BoxGeometry(.22, .22, .008);
  const pos = [];
  for (let i = 0; i < 12; i++) for (let j = 0; j < 7; j++) {
    if (r() < .18) continue;
    const n = new THREE.Mesh(geo, mats[Math.floor(r() * mats.length)]);
    n.position.set(-W / 2 + .25 + i * .29 + (r() - .5) * .06, H / 2 - .24 - j * .3 + (r() - .5) * .06, .026); n.rotation.z = (r() - .5) * .3; g.add(n); pos.push(n.position);
  }
  const line = new THREE.LineBasicMaterial({ color: 0xd84a4a });
  for (let k = 0; k < 5; k++) {
    const a = pos[Math.floor(r() * pos.length)], b = pos[Math.floor(r() * pos.length)];
    g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([a.clone().setZ(.04), b.clone().setZ(.04)]), line));
  }
  return g;
}
// studio: ring light on a tripod with a phone in the middle
function ringLight() {
  const g = new THREE.Group(), dark = new THREE.MeshStandardMaterial({ color: 0x16181d, roughness: .4, metalness: .5 });
  for (let i = 0; i < 3; i++) { const a = i / 3 * Math.PI * 2, leg = _M(new THREE.CylinderGeometry(.015, .015, .9, 6), dark, Math.cos(a) * .2, .42, Math.sin(a) * .2, g); leg.rotation.set(Math.sin(a) * .45, 0, -Math.cos(a) * .45); }
  _M(new THREE.CylinderGeometry(.018, .018, 1.1, 8), dark, 0, 1.3, 0, g);
  const ring = _M(new THREE.TorusGeometry(.34, .035, 12, 48), new THREE.MeshBasicMaterial({ color: 0xfff4e0, toneMapped: false }), 0, 2.05, 0, g);
  _M(new THREE.BoxGeometry(.09, .17, .012), dark, 0, 2.05, .01, g);
  const l = new THREE.PointLight(0xfff0dc, 1.4, 2.6); l.position.set(0, 2.05, .5); g.add(l);
  ring.userData.glow = true;
  return g;
}
// studio: neon icons on the side walls instead of paintings
function neonIcon(ch, color) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 256; const g = c.getContext("2d"), col = hexStr(color);
  g.font = "700 190px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.shadowColor = col; g.shadowBlur = 26; g.strokeStyle = col; g.lineWidth = 10; g.strokeText(ch, 128, 136);
  g.shadowBlur = 0; g.fillStyle = "#fff0f8"; g.globalAlpha = .55; g.fillText(ch, 128, 136);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 1.2), new THREE.MeshBasicMaterial({ map: t, transparent: true, toneMapped: false, fog: false, depthWrite: false }));
  m.position.z = .03; return m;
}
// studio: coloured wash lights on the walls that slowly change colour, and the LED strip following them
function studioLights(g, { x0, x1, z0, z1, accent, ledMat }) {
  const spots = [[x0 + 1, 3.6, z0 + 1, 0], [x1 - 1, 3.6, z0 + 1, .33], [x0 + 1, 3.6, (z0 + z1) / 2 + 3, .66]].map(([x, y, z, h]) => {
    const l = new THREE.PointLight(0xffffff, 6, 9, 1.6); l.position.set(x, y, z); g.add(l); return { l, h };
  });
  const base = new THREE.Color(accent).getHSL({});
  return (dt, t) => {
    for (const s of spots) s.l.color.setHSL((s.h + t * .02) % 1, .85, .55);
    ledMat.color.setHSL((base.h + Math.sin(t * .15) * .08 + 1) % 1, .85, .6);
  };
}

// neon sign: glowing tube letters on a dark backing (glows with the bloom)
function neonSign(text, color) {
  const c = document.createElement("canvas"); c.width = 512; c.height = 160; const g = c.getContext("2d");
  const col = hexStr(color);
  g.font = "700 104px 'Chakra Petch','Trebuchet MS',sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.shadowColor = col; g.shadowBlur = 24; g.strokeStyle = col; g.lineWidth = 9; g.strokeText(text, 256, 84);
  g.shadowBlur = 0; g.fillStyle = "#f3ecff"; g.fillText(text, 256, 84);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace;
  const grp = new THREE.Group();
  const back = new THREE.Mesh(new THREE.BoxGeometry(2.7, .9, .03), new THREE.MeshStandardMaterial({ color: 0x0b0d14, roughness: .4, metalness: .3, transparent: true, opacity: .6 }));
  grp.add(back);
  const glow = new THREE.Mesh(new THREE.PlaneGeometry(2.6, .81), new THREE.MeshBasicMaterial({ map: t, color: 0xa8a8a8, transparent: true, toneMapped: false, fog: false }));  // soft: under the bloom threshold
  glow.position.z = .02; grp.add(glow);
  return grp;
}

export function plant(s = 1) {
  const g = new THREE.Group();
  const pot = new THREE.Mesh(new THREE.CylinderGeometry(.32, .24, .6, 20), new THREE.MeshStandardMaterial({ color: 0xd9d4c7, roughness: .5 }));
  pot.position.y = .3; g.add(pot);
  const soil = new THREE.Mesh(new THREE.CylinderGeometry(.29, .29, .04, 20), new THREE.MeshStandardMaterial({ color: 0x2b1d12, roughness: 1 }));
  soil.position.y = .58; g.add(soil);
  const leafMat = new THREE.MeshStandardMaterial({ color: 0x2f6b3a, roughness: .7, flatShading: true });
  const leafMat2 = new THREE.MeshStandardMaterial({ color: 0x3f8a48, roughness: .7, flatShading: true });
  const leaf = new THREE.IcosahedronGeometry(1, 0);
  for (let i = 0; i < 9; i++) {
    const a = i / 9 * Math.PI * 2, r = .12 + (i % 3) * .08;
    const l = new THREE.Mesh(leaf, i % 2 ? leafMat : leafMat2);
    l.scale.set(.16, .38, .08); l.position.set(Math.cos(a) * r, .9 + (i % 3) * .28, Math.sin(a) * r);
    l.rotation.set(Math.sin(a) * .5, a, Math.cos(a) * .5); g.add(l);
  }
  g.scale.setScalar(s);
  return shade(g);
}

// ---------------------------------------------------------------- workstation + person (sits, types, sleeps, walks)
// Local frame: +z points to the room centre. The person sits on the inner side, facing the monitor (-z).
const SKINS = [0xf1c9a5, 0xd9a47e, 0xa8714f, 0x7a4b31, 0xe8b894];
const HAIRS = [0x1b1410, 0x3b2616, 0x6b4423, 0xb58b52, 0x2a2a2e, 0x8c8c8c];
const shared = {};
const once = (k, f) => shared[k] || (shared[k] = f());
const SEAT = new THREE.Vector3(0, 0, .55), FRONT = new THREE.Vector3(0, 0, 1.55);
const lerp = (a, b, t) => a + (b - a) * t;

// what each role has on its monitor (drawn live, it moves while the agent works)
const SCREEN_KIND = { ceo: "chart", "yield-lead": "chart", "social-lead": "chart", "quant-analyst": "chart", growth: "chart",
  "portfolio-analyst": "bars", "onchain-analyst": "bars", "market-scanner": "map", "airdrop-scout": "map",
  "quant-dev": "code", "yield-scout": "doc", "social-writer": "doc", "ethics-guard": "check", "visual-designer": "art" };
function monitorScreen(kind, color) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 140; const g = c.getContext("2d");
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const col = hexStr(color);
  const draw = time => {
    g.fillStyle = "#0b1626"; g.fillRect(0, 0, 256, 140);
    g.fillStyle = col; g.fillRect(0, 0, 256, 12);
    for (let i = 0; i < 3; i++) { g.fillStyle = "rgba(255,255,255,.55)"; g.beginPath(); g.arc(240 - i * 10, 6, 2.5, 0, 7); g.fill(); }
    const T = Math.floor(time * 4);
    if (kind === "code") {
      for (let i = 0; i < 11; i++) {
        const k = i + T, ind = (k * 7) % 4;
        g.fillStyle = ["#7dd3fc", "#f5b83d", "#c4b5fd", "#86efac", "#94a3b8"][(k * 3) % 5];
        g.fillRect(10 + ind * 12, 20 + i * 11, 30 + (k * 53) % 140, 5);
      }
      if (T % 2) { g.fillStyle = "#fff"; g.fillRect(12 + (T * 13) % 150, 20 + 10 * 11, 3, 7); }
    } else if (kind === "chart") {
      for (let i = 0; i < 6; i++) { g.fillStyle = "rgba(255,255,255,.14)"; const hh = 18 + ((i * 23) % 46); g.fillRect(14 + i * 40, 132 - hh, 24, hh); }
      g.strokeStyle = col; g.lineWidth = 3; g.beginPath();
      for (let x = 0; x <= 236; x += 8) g.lineTo(10 + x, 112 - x * .25 - Math.sin(x / 26 + time * 1.5) * 12);
      g.stroke();
    } else if (kind === "bars") {
      for (let i = 0; i < 7; i++) { const v = .35 + .55 * Math.abs(Math.sin(i * 1.3 + time * .8)); g.fillStyle = i % 2 ? col : "rgba(255,255,255,.3)"; g.fillRect(16, 22 + i * 16, 220 * v, 10); }
    } else if (kind === "map") {
      g.fillStyle = "#16324a";
      for (let i = 0; i < 42; i++) { g.beginPath(); g.arc(24 + (i * 53) % 210, 26 + (i * 37) % 104, 5 + i % 7, 0, 7); g.fill(); }
      for (let i = 0; i < 6; i++) { g.fillStyle = "#f5b83d"; g.beginPath(); g.arc(36 + i * 34, 40 + (i * 29) % 76, 3.5 + Math.sin(time * 3 + i) * 1.5, 0, 7); g.fill(); }
    } else if (kind === "doc" || kind === "check") {
      g.fillStyle = "#e8ecf4"; g.fillRect(44, 18, 168, 120);
      const lines = kind === "doc" ? 1 + (T % 9) : 9;
      for (let i = 0; i < lines; i++) { g.fillStyle = i ? "#94a3b8" : "#1d2230"; g.fillRect(56, 28 + i * 11, i ? 100 + (i * 31) % 44 : 80, i ? 4 : 6); }
      if (kind === "check") { g.fillStyle = "#16a34a"; g.font = "700 20px sans-serif"; g.fillText("✓ PASS", 140, 130); }
    } else if (kind === "art") {
      const r = seeded(3 + (T >> 3));
      for (let i = 0; i < 6; i++) { g.fillStyle = ["#f5b83d", "#ff5fa2", "#3ecfb2", "#4da3ff", "#e8e2d6"][Math.floor(r() * 5)]; g.beginPath(); g.arc(30 + r() * 200, 30 + r() * 100, 10 + r() * 26, 0, 7); g.fill(); }
      g.strokeStyle = "#fff"; g.lineWidth = 2; g.strokeRect(60, 24, 136, 108);
    }
    tex.needsUpdate = true;
  };
  draw(0);
  return { tex, draw };
}

export function workstation(color, seed = 0, key = "") {
  const root = new THREE.Group();
  const wood = THEME === "neon"
    ? once("deskNeon", () => new THREE.MeshStandardMaterial({ color: 0x0c1830, roughness: .12, metalness: .7, emissive: 0x061533 }))
    : once("deskWood", () => new THREE.MeshStandardMaterial({ map: woodPlanks(0x8a6242, 4), roughness: .45 }));
  const metal = once("metal", () => new THREE.MeshStandardMaterial({ color: 0x9aa3b2, roughness: .3, metalness: .85 }));
  const black = once("black", () => new THREE.MeshStandardMaterial({ color: 0x14161b, roughness: .35, metalness: .4 }));
  const fabric = once("fabric", () => new THREE.MeshStandardMaterial({ color: 0x2a2f3a, roughness: .95 }));
  const B = (sx, sy, sz, m, x, y, z, parent = root) => { const o = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), m); o.position.set(x, y, z); parent.add(o); return o; };

  // desk
  B(1.9, .05, .85, wood, 0, .76, -.4);
  if (THEME === "neon") B(1.9, .012, .012, once("deskEdge", () => new THREE.MeshBasicMaterial({ color: 0x3aa0ff, toneMapped: false })), 0, .785, .03);  // glowing front edge
  for (const x of [-.88, .88]) { B(.05, .74, .7, metal, x, .37, -.4); B(.05, .03, .75, metal, x, .015, -.4); }
  B(1.76, .3, .02, black, 0, .56, -.8);  // modesty panel
  // monitor (bezel, stand) + glowing screen driven by the page (opacity = activity)
  const mon = new THREE.Group(); mon.position.set(0, 1.2, -.62); root.add(mon);
  B(1.14, .66, .04, black, 0, 0, 0, mon);
  B(.08, .36, .04, black, 0, -.42, -.03, mon);
  B(.34, .02, .22, black, 0, -.43, -.02, mon);
  const off = new THREE.Mesh(new THREE.PlaneGeometry(1.06, .58), new THREE.MeshStandardMaterial({ color: 0x05070b, roughness: .15, metalness: .2 }));
  off.position.z = .021; mon.add(off);
  const screen = monitorScreen(SCREEN_KIND[key] || "chart", color);
  const scrMat = new THREE.MeshBasicMaterial({ map: screen.tex, transparent: true, opacity: .1, toneMapped: false });  // opacity = activity (set by the page)
  const scr = new THREE.Mesh(new THREE.PlaneGeometry(1.06, .58), scrMat); scr.position.z = .023; mon.add(scr);
  const radar = new THREE.Mesh(new THREE.CircleGeometry(.2, 24, 0, .9), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0, toneMapped: false }));
  radar.position.z = .025; mon.add(radar);
  // keyboard, mouse, mug
  B(.5, .02, .16, black, 0, .79, -.2);
  B(.07, .02, .1, black, .38, .79, -.2);
  const mug = new THREE.Mesh(new THREE.CylinderGeometry(.045, .04, .1, 14), new THREE.MeshStandardMaterial({ color: [0xeeeeee, 0xd84a4a, 0x2e86de][seed % 3], roughness: .4 }));
  mug.position.set(-.62, .835, -.32); root.add(mug);
  // desk lamp (warm bulb, glows with the bloom) and a pendant lamp lighting the desk
  const lampM = once("lampM", () => new THREE.MeshStandardMaterial({ color: 0x23262e, roughness: .35, metalness: .6 }));
  const bulbM = once("bulbM", () => new THREE.MeshBasicMaterial({ color: 0xffe2b0 }));
  const dl = new THREE.Group(); dl.position.set(.72, .79, -.55); root.add(dl);
  dl.add(new THREE.Mesh(new THREE.CylinderGeometry(.07, .08, .03, 14), lampM));
  const dla = new THREE.Mesh(new THREE.CylinderGeometry(.012, .012, .42, 6), lampM); dla.position.set(-.04, .2, 0); dla.rotation.z = .35; dl.add(dla);
  const dls = new THREE.Mesh(new THREE.ConeGeometry(.08, .12, 14, 1, true), lampM); dls.position.set(-.1, .42, 0); dls.rotation.z = -.3; dl.add(dls);
  const dlb = new THREE.Mesh(new THREE.SphereGeometry(.028, 8, 6), bulbM); dlb.position.set(-.11, .38, 0); dl.add(dlb);
  const pend = new THREE.Group(); pend.position.set(0, 4.25, -.25); root.add(pend);
  const cord = new THREE.Mesh(new THREE.CylinderGeometry(.006, .006, .95, 4), once("cordM", () => new THREE.MeshBasicMaterial({ color: 0x111111 }))); cord.position.y = .48; pend.add(cord);
  pend.add(new THREE.Mesh(new THREE.SphereGeometry(.2, 18, 8, 0, Math.PI * 2, 0, Math.PI / 2), once("domeM", () => new THREE.MeshStandardMaterial({ color: 0x1d2230, metalness: .6, roughness: .3, side: THREE.DoubleSide }))));
  const pb = new THREE.Mesh(new THREE.CircleGeometry(.17, 18), once("pbM", () => new THREE.MeshBasicMaterial({ color: 0xfff0d0 }))); pb.rotation.x = Math.PI / 2; pb.position.y = .01; pend.add(pb);
  const spot = new THREE.SpotLight(0xffe0b0, 7, 6.5, .75, .6, 1.6); spot.position.y = -.05; spot.target.position.set(0, -4, -.2); pend.add(spot, spot.target);
  addLamp(v => { spot.intensity = 9 * (.12 + .88 * v); });

  // office chair
  const chair = new THREE.Group(); chair.position.copy(SEAT); root.add(chair);
  B(.52, .08, .5, fabric, 0, .5, 0, chair);
  B(.48, .58, .07, fabric, 0, .9, .27, chair).rotation.x = -.12;
  B(.05, .4, .05, metal, 0, .27, 0, chair);
  for (let i = 0; i < 5; i++) {
    const a = i / 5 * Math.PI * 2, leg = B(.3, .03, .04, metal, Math.cos(a) * .15, .06, Math.sin(a) * .15, chair); leg.rotation.y = -a;
    const wheel = new THREE.Mesh(new THREE.SphereGeometry(.035, 8, 6), black); wheel.position.set(Math.cos(a) * .29, .035, Math.sin(a) * .29); chair.add(wheel);
  }

  // person
  const skin = new THREE.MeshStandardMaterial({ color: SKINS[seed % SKINS.length], roughness: .6 });
  const hair = new THREE.MeshStandardMaterial({ color: HAIRS[(seed * 7 + 3) % HAIRS.length], roughness: .8 });
  const suit = new THREE.MeshStandardMaterial({ color, roughness: .6 });
  const PANTS = [0x23262e, 0x2f4466, 0x5a4a38, 0x3a3d45, 0x1e2a3f];  // charcoal, denim, khaki, grey, navy
  const pants = once("pants" + (seed % PANTS.length), () => new THREE.MeshStandardMaterial({ color: PANTS[seed % PANTS.length], roughness: .85 }));
  const shoes = once("shoes", () => new THREE.MeshStandardMaterial({ color: 0x0e0e10, roughness: .4 }));
  const eyeM = once("eye", () => new THREE.MeshStandardMaterial({ color: 0x111111, roughness: .2 }));
  const cyl = (r1, r2, len, m) => new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, len, 14), m);

  const body = new THREE.Group(); body.position.copy(SEAT); root.add(body);
  const pelvis = new THREE.Group(); body.add(pelvis);  // lifted when standing
  // legs: hip pivot -> thigh hanging down, knee pivot -> shin + shoe (seated: hip +90°, knee -90°)
  const legs = [-.11, .11].map(x => {
    const hip = new THREE.Group(); hip.position.set(x, .6, 0); pelvis.add(hip);
    const thigh = new THREE.Mesh(new THREE.CapsuleGeometry(.082, .32, 4, 12), pants); thigh.position.y = -.23; hip.add(thigh);
    const knee = new THREE.Group(); knee.position.y = -.46; hip.add(knee);
    const shin = new THREE.Mesh(new THREE.CapsuleGeometry(.066, .38, 4, 12), pants); shin.position.y = -.25; knee.add(shin);
    B(.11, .07, .24, shoes, 0, -.52, -.06, knee);
    B(.115, .025, .25, once("sole", () => new THREE.MeshStandardMaterial({ color: 0xd8d4cc, roughness: .8 })), 0, -.565, -.06, knee);  // light sole
    return { hip, knee };
  });
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(1, 1.6, 6, 16), suit);
  torso.scale.set(.19, .145, .125); torso.position.set(0, .95, .03); torso.rotation.x = -.08; pelvis.add(torso);
  // shoulders: one rounded piece across the top of the chest, so the arms are attached to the body
  const yoke = new THREE.Mesh(new THREE.CapsuleGeometry(.078, .3, 6, 14), suit); yoke.rotation.z = Math.PI / 2; yoke.position.set(0, 1.16, .03); yoke.scale.z = .95; pelvis.add(yoke);
  const suitParts = [];
  const hips = new THREE.Mesh(new THREE.SphereGeometry(1, 18, 12), pants); hips.scale.set(.185, .09, .15); hips.position.set(0, .64, .02); pelvis.add(hips);
  const collar = cyl(.062, .072, .05, once("collar", () => new THREE.MeshStandardMaterial({ color: 0xf2f2f2, roughness: .7 }))); collar.position.set(0, 1.24, .02); pelvis.add(collar);
  const neck = cyl(.048, .054, .09, skin); neck.position.set(0, 1.29, .02); pelvis.add(neck);
  const belt = new THREE.Mesh(new THREE.TorusGeometry(.162, .012, 6, 28), once("belt", () => new THREE.MeshStandardMaterial({ color: 0x17181c, roughness: .45 })));
  belt.rotation.x = Math.PI / 2; belt.scale.set(1, .8, 1); belt.position.set(0, .715, .02); pelvis.add(belt);
  const buckle = B(.045, .03, .012, once("buckle", () => new THREE.MeshStandardMaterial({ color: 0xc9a227, metalness: .9, roughness: .25 })), 0, .715, -.122, pelvis);
  // company badge on a lanyard, in the agent's colour
  const strap = once("strap", () => new THREE.MeshStandardMaterial({ color: 0x2b3140, roughness: .6 }));
  for (const sd of [-1, 1]) { const st = B(.012, .2, .008, strap, sd * .045, 1.12, -.122, pelvis); st.rotation.z = -sd * .22; }
  B(.075, .1, .008, once("card", () => new THREE.MeshStandardMaterial({ color: 0xf7f7f2, roughness: .5 })), 0, .99, -.128, pelvis);
  B(.075, .028, .009, suit, 0, 1.025, -.129, pelvis);  // stripe in the agent's colour

  const head = new THREE.Group(); head.position.set(0, 1.43, 0); pelvis.add(head);
  const skull = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 18), skin); skull.scale.set(.115, .14, .125); head.add(skull);
  const hairCap = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 12, 0, Math.PI * 2, 0, Math.PI * .55), hair);
  hairCap.scale.set(.125, .15, .135); hairCap.position.set(0, .012, .01); hairCap.rotation.x = .25; head.add(hairCap);
  // face: eyes that blink and look around, eyebrows and a mouth for the expressions (see mood below)
  const EYES = [0x5b3a1e, 0x2e6fa8, 0x3f7a4a, 0x3b2a20];
  const iris = once("iris" + (seed % EYES.length), () => new THREE.MeshStandardMaterial({ color: EYES[seed % EYES.length], roughness: .25 }));
  const white = once("eyeW", () => new THREE.MeshStandardMaterial({ color: 0xf8f6f2, roughness: .3 }));
  const glint = once("glint", () => new THREE.MeshBasicMaterial({ color: 0xffffff }));
  const eyes = [-.042, .042].map(x => {
    const g = new THREE.Group(); g.position.set(x, .022, -.104); head.add(g);
    const w = new THREE.Mesh(new THREE.SphereGeometry(.024, 14, 10), white); w.scale.set(1, 1.05, .55); g.add(w);
    const look = new THREE.Group(); g.add(look);
    const ir = new THREE.Mesh(new THREE.SphereGeometry(.0135, 12, 8), iris); ir.position.z = -.011; ir.scale.z = .5; look.add(ir);
    const pu = new THREE.Mesh(new THREE.SphereGeometry(.007, 8, 6), eyeM); pu.position.z = -.0165; pu.scale.z = .5; look.add(pu);
    const gl = new THREE.Mesh(new THREE.SphereGeometry(.0035, 6, 4), glint); gl.position.set(.005, .006, -.019); look.add(gl);
    const lid = new THREE.Mesh(new THREE.SphereGeometry(.026, 14, 8, 0, Math.PI * 2, 0, Math.PI / 2), skin); lid.scale.set(1, .25, .62); lid.position.z = -.001; g.add(lid);
    return { g, look, lid };
  });
  const brows = [-1, 1].map(sd => { const b = B(.042, .009, .01, hair, sd * .043, .062, -.118, head); b.rotation.z = -sd * .06; return b; });
  const nose = new THREE.Mesh(new THREE.SphereGeometry(.021, 10, 8), skin); nose.position.set(0, -.012, -.124); nose.scale.set(.85, 1, 1.25); head.add(nose);
  const lipM = once("lip", () => new THREE.MeshStandardMaterial({ color: 0x8a3b3b, roughness: .5 }));
  const smile = new THREE.Mesh(new THREE.TorusGeometry(.026, .0055, 6, 16, Math.PI), lipM); smile.rotation.z = Math.PI; smile.position.set(0, -.048, -.112); head.add(smile);
  const mouthO = new THREE.Mesh(new THREE.SphereGeometry(.018, 12, 8), once("mouthIn", () => new THREE.MeshStandardMaterial({ color: 0x3a1414, roughness: .8 })));
  mouthO.scale.set(1.2, .8, .4); mouthO.position.set(0, -.058, -.112); mouthO.visible = false; head.add(mouthO);
  for (const sd of [-1, 1]) {  // a bit of colour on the cheeks
    const ch = new THREE.Mesh(new THREE.SphereGeometry(.018, 8, 6), once("cheek", () => new THREE.MeshStandardMaterial({ color: 0xe0786a, roughness: .7, transparent: true, opacity: .28, depthWrite: false })));
    ch.position.set(sd * .07, -.025, -.098); ch.scale.z = .3; head.add(ch);
  }
  // mood: "calm" | "focus" (brows down, at work) | "happy" (big smile) | "talk" (mouth moves) | "sleep" (eyes closed)
  let mood = "calm", forced = null, blinkT = 2 + Math.random() * 3, blink = 0, gazeT = 0;
  const gaze = new THREE.Vector2();
  const face = (t, dt) => {
    if ((blinkT -= dt) <= 0) { blink = .14; blinkT = 2.2 + Math.random() * 4; }
    blink = Math.max(0, blink - dt);
    if ((gazeT -= dt) <= 0) { gazeT = 1.2 + Math.random() * 2.5; gaze.set((Math.random() - .5) * .006, (Math.random() - .5) * .004); }
    const shut = mood === "sleep" ? 1 : blink > 0 ? 1 : mood === "focus" ? .35 : mood === "happy" ? .3 : 0;
    for (const e of eyes) {
      e.lid.scale.y = .25 + shut * .8; e.lid.rotation.x = -.15 - shut * .9;  // the lid closes over the eye
      e.look.position.set(gaze.x, mood === "focus" ? -.004 : gaze.y, 0);
    }
    const bY = mood === "focus" ? .056 : mood === "happy" ? .07 : mood === "talk" ? .064 + Math.sin(t * 4) * .004 : .062;
    brows.forEach((b, k) => { b.position.y = bY; b.rotation.z = (k ? 1 : -1) * (mood === "focus" ? .22 : mood === "happy" ? -.12 : -.06); });
    const open = mood === "talk" ? Math.abs(Math.sin(t * 9)) : mood === "happy" ? .55 : 0;
    mouthO.visible = open > .2; mouthO.scale.y = .4 + open * .8;
    smile.visible = !mouthO.visible || mood === "happy";
    smile.scale.set(mood === "happy" ? 1.25 : mood === "focus" ? .7 : 1, mood === "happy" ? 1.3 : mood === "focus" ? .25 : .6, 1);
    smile.position.y = mood === "happy" && mouthO.visible ? -.04 : -.048;
  };
  for (const x of [-.115, .115]) { const ear = new THREE.Mesh(new THREE.SphereGeometry(.028, 8, 6), skin); ear.position.set(x, 0, 0); ear.scale.x = .5; head.add(ear); }
  // hairstyle (0 short, 1 long, 2 bun, 3 balding, 4 curly) and glasses: a different look for each person
  const style = (seed * 3 + 1) % 5;
  if (style === 1) { const back = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 12), hair); back.scale.set(.12, .17, .07); back.position.set(0, -.07, .07); head.add(back); }
  if (style === 2) { const bun = new THREE.Mesh(new THREE.SphereGeometry(.055, 12, 10), hair); bun.position.set(0, .12, .09); head.add(bun); }
  if (style === 4) for (let i = 0; i < 12; i++) {
    const a = i / 12 * Math.PI * 2, c = new THREE.Mesh(new THREE.SphereGeometry(.042, 8, 6), hair);
    c.position.set(Math.cos(a) * .1, .08 + Math.sin(i * 1.7) * .02, Math.sin(a) * .1 + .015); head.add(c);
  }
  if (style === 0 || style === 1) {  // fringe over the forehead, swept to one side
    const fr = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 8, 0, Math.PI * 2, 0, Math.PI * .5), hair);
    fr.scale.set(.1, .05, .05); fr.position.set(seed % 2 ? .02 : -.02, .1, -.085); fr.rotation.set(-.5, 0, seed % 2 ? -.25 : .25); head.add(fr);
  }
  if (style === 1) for (const sd of [-1, 1]) {  // long hair: locks down the sides of the face
    const lock = new THREE.Mesh(new THREE.CapsuleGeometry(.03, .14, 4, 8), hair); lock.position.set(sd * .108, -.06, .0); lock.rotation.z = sd * .08; head.add(lock);
  }
  if (style === 2) {  // ponytail under the bun
    const tail = new THREE.Mesh(new THREE.CapsuleGeometry(.03, .14, 4, 8), hair); tail.position.set(0, .02, .16); tail.rotation.x = .5; head.add(tail);
  }
  if (style === 3) {  // bald on top: the hair stays on the back of the head; a moustache
    hairCap.rotation.x = 1.15; hairCap.scale.set(.126, .13, .136); hairCap.position.set(0, -.01, .012);
    const mo = new THREE.Mesh(new THREE.CapsuleGeometry(.009, .045, 3, 6), hair); mo.rotation.z = Math.PI / 2; mo.position.set(0, -.031, -.121); head.add(mo);
  }
  if (seed % 3 === 1) {  // glasses
    const frame = once("frame", () => new THREE.MeshStandardMaterial({ color: 0x15161a, roughness: .3, metalness: .6 }));
    for (const x of [-.045, .045]) { const r = new THREE.Mesh(new THREE.TorusGeometry(.028, .005, 6, 18), frame); r.position.set(x, .02, -.122); head.add(r); }
    const br = new THREE.Mesh(new THREE.BoxGeometry(.035, .006, .006), frame); br.position.set(0, .025, -.124); head.add(br);
  }
  // outfit details on the shirt front (the torso keeps the agent's colour): 0 jacket + tie, 1 hoodie, 2 shirt with buttons
  const outfit = seed % 3, front = (m, sx, sy, sz, x, y, z, rz = 0) => { const o = B(sx, sy, sz, m, x, y, z, pelvis); o.rotation.z = rz; return o; };
  if (outfit === 0) {
    const jacket = once("jacket", () => new THREE.MeshStandardMaterial({ color: 0x1d2230, roughness: .75 }));
    for (const sd of [-1, 1]) front(jacket, .1, .4, .03, sd * .11, .98, -.09, sd * .18);
    front(once("shirtW", () => new THREE.MeshStandardMaterial({ color: 0xf2f2f2, roughness: .7 })), .1, .2, .02, 0, 1.1, -.1);
    front(once("tie", () => new THREE.MeshStandardMaterial({ color: 0x8e1b2c, roughness: .5 })), .035, .22, .02, 0, 1.03, -.112);
  } else if (outfit === 1) {
    belt.visible = buckle.visible = false;  // the hoodie covers the belt
    // hood: a soft collar around the neck and the hood lying flat on the upper back
    const cowl = new THREE.Mesh(new THREE.TorusGeometry(.078, .026, 8, 20), suit); cowl.rotation.x = Math.PI / 2; cowl.scale.set(1.05, 1.15, 1); cowl.position.set(0, 1.235, .03); pelvis.add(cowl);
    const hood = new THREE.Mesh(new THREE.SphereGeometry(1, 16, 10), suit); hood.scale.set(.12, .1, .045); hood.position.set(0, 1.16, .145); hood.rotation.x = .25; pelvis.add(hood);
    suitParts.push(cowl, hood);
    const cord = once("cord", () => new THREE.MeshStandardMaterial({ color: 0xf2f2f2, roughness: .6 }));
    for (const x of [-.04, .04]) front(cord, .008, .14, .008, x, 1.12, -.105);
    front(once("pocket", () => new THREE.MeshStandardMaterial({ color: 0x000000, transparent: true, opacity: .18 })), .22, .08, .01, 0, .78, -.1);
  } else {
    const btn = once("btn", () => new THREE.MeshStandardMaterial({ color: 0xf5f5f5, roughness: .4 }));
    for (let i = 0; i < 4; i++) { const b = new THREE.Mesh(new THREE.SphereGeometry(.009, 6, 5), btn); b.position.set(0, 1.12 - i * .09, -.105); pelvis.add(b); }
  }

  const cup = new THREE.Mesh(new THREE.CylinderGeometry(.035, .03, .08, 12), once("cupM", () => new THREE.MeshStandardMaterial({ color: 0xf4efe6, roughness: .4 })));
  cup.visible = false;
  // arms: shoulder pivot -> upper arm, elbow pivot -> forearm reaching the keyboard (hangs down when standing)
  // arm: shoulder joint -> upper arm (a bit forward) -> elbow joint -> forearm towards the keyboard -> hand.
  // Capsules and ball joints: no gaps or flat ends. `fore` is the elbow pivot animated by tick() and the pages.
  suitParts.push(yoke);
  const shoulders = [], arms = [-1, 1].map(sd => {
    const sh = new THREE.Group(); sh.position.set(sd * .2, 1.16, .03); pelvis.add(sh); shoulders.push(sh);
    const ball = new THREE.Mesh(new THREE.SphereGeometry(.064, 14, 10), suit); sh.add(ball);
    const upper = new THREE.Group(); upper.rotation.set(.32, 0, sd * .07); sh.add(upper);  // upper arm slightly forward and out
    const up = new THREE.Mesh(new THREE.CapsuleGeometry(.056, .2, 4, 12), suit); up.position.y = -.14; upper.add(up);
    const fore = new THREE.Group(); fore.position.set(0, -.28, 0); upper.add(fore);
    const elbow = new THREE.Mesh(new THREE.SphereGeometry(.05, 12, 8), suit); fore.add(elbow);
    const lower = new THREE.Group(); lower.rotation.set(-.42, -sd * .12, 0); fore.add(lower);  // forearm level with the desk, hands towards the middle
    const lo = new THREE.Mesh(new THREE.CapsuleGeometry(.046, .19, 4, 12), suit); lo.rotation.x = Math.PI / 2; lo.position.z = -.13; lower.add(lo);
    const cuff = new THREE.Mesh(new THREE.CylinderGeometry(.04, .04, .025, 12), skin); cuff.rotation.x = Math.PI / 2; cuff.position.z = -.255; lower.add(cuff);
    const hand = new THREE.Mesh(new THREE.SphereGeometry(.045, 12, 10), skin); hand.scale.set(.95, .55, 1.35); hand.position.set(0, -.005, -.31); lower.add(hand);
    const thumb = new THREE.Mesh(new THREE.CapsuleGeometry(.011, .03, 3, 6), skin); thumb.position.set(-sd * .042, .004, -.3); thumb.rotation.set(Math.PI / 2, 0, sd * .5); lower.add(thumb);
    for (let f = 0; f < 4; f++) {  // fingers
      const fg = new THREE.Mesh(new THREE.CapsuleGeometry(.0085, .03, 3, 6), skin); fg.rotation.x = Math.PI / 2 + .25; fg.position.set((f - 1.5) * .019, -.01, -.355); lower.add(fg);
    }
    if (sd === 1) { cup.position.set(0, .05, -.31); lower.add(cup); }
    suitParts.push(ball, up, elbow, lo);
    return fore;
  });
  // the pages grey out `torso` for a paused agent: do the same for every piece of clothing in the agent's colour
  let torsoMat = torso.material;
  Object.defineProperty(torso, "material", { get: () => torsoMat, set: m => { torsoMat = m; for (const x of suitParts) x.material = m; }, configurable: true });
  shade(root);

  // ---- motion: seated (typing / idle / asleep) or a walk along a route of waypoints (root-local)
  let trip = null, away = false, stand = 0, walkPh = 0, act = null, nextAct = 3 + Math.random() * 8, scrT = Math.random(), cheerT = 0;
  // a yellow folder held to the chest, for the walk that brings finished work to a colleague
  const folder = new THREE.Group(); folder.position.set(0, 1.0, -.2); folder.visible = false; body.add(folder);
  const fm = new THREE.Mesh(new THREE.BoxGeometry(.32, .42, .04), once("folderM", () => new THREE.MeshStandardMaterial({ color: 0xf5b83d, roughness: .7 }))); folder.add(fm);
  const fp = new THREE.Mesh(new THREE.BoxGeometry(.27, .36, .02), once("paperM", () => new THREE.MeshStandardMaterial({ color: 0xfaf7f0, roughness: .9 }))); fp.position.set(0, .03, -.025); folder.add(fp);
  // small things a person does when free: coffee, stretch, a turn on the chair, a chat with the neighbour
  const ACTS = ["coffee", "stretch", "turn", "talk"];
  const env = p => p < .2 ? p / .2 : p > .8 ? (1 - p) / .2 : 1;
  const pose = (s, walking) => {
    legs.forEach(({ hip, knee }, k) => {
      const sw = walking ? Math.sin(walkPh + k * Math.PI) : 0;
      hip.rotation.x = lerp(Math.PI / 2, 0, s) + sw * .45;
      knee.rotation.x = lerp(-Math.PI / 2, 0, s) - (walking ? Math.max(0, -sw) * .7 : 0);
    });
    pelvis.position.y = s * .38;
    shoulders.forEach((sh, k) => { sh.rotation.x = walking ? Math.sin(walkPh + (k + 1) * Math.PI) * .4 : 0; });
    arms.forEach(a => { a.rotation.x = lerp(0, -1.15, s); });  // standing: forearms hang down
    torso.rotation.x = lerp(-.08, 0, s);
  };
  return {
    root, scrMat, radar, body, head, arms, torso, suit,
    get walking() { return !!trip; },
    // celebrate for `secs` seconds: arms up, bouncing on the chair
    cheer(secs = 8) { if (!trip) cheerT = secs; },
    get away() { return away; },
    set mood(m) { forced = m || null; },  // force an expression (previews); null = follow the state
    // walk: stand up, go to `to` (root-local) through the `via` points, look at `look`, wait, come back and sit down.
    // onWait/onDone: called when the person arrives and when they are back at the desk; doing: coffee|talk|pet|read|stretch.
    visit(to, look, wait = 1.4, carry = false, { via = [], onWait = null, onDone = null, doing = null } = {}) {
      if (trip || away) return false;
      const v = via.map(p => p.clone());
      const pts = [SEAT.clone(), FRONT.clone(), ...v, to.clone(), ...v.slice().reverse(), FRONT.clone(), SEAT.clone()];
      trip = { pts, seg: 0, t: 0, phase: "up", wait, waitSeg: 2 + v.length, look, carry, onWait, onDone, doing };
      return true;
    },
    // end of the day: walk along `route` (root-local, e.g. to the lift) and disappear; arrive() is the way back
    leave(route) {
      if (trip || away) return false;
      trip = { pts: [SEAT.clone(), FRONT.clone(), ...route.map(p => p.clone())], seg: 0, t: 0, phase: "up", end: "hide" };
      return true;
    },
    arrive(route) {
      if (!away) return false;
      away = false; body.visible = true; stand = 1; body.position.copy(route[0]);
      trip = { pts: [...route.map(p => p.clone()), FRONT.clone(), SEAT.clone()], seg: 0, t: 0, phase: "walk" };
      return true;
    },
    // put the person away (or back at the desk) instantly, e.g. when the page opens at night
    setAway(v) { if (trip) return; away = !!v; body.visible = !away; stand = 0; pose(0, false); body.position.copy(SEAT); },
    tick(dt, t, { working = false, sleeping = false, mo = 1 } = {}) {
      if ((scrT -= dt) <= 0) { scrT = working ? .25 : 2.5; screen.draw(t); }
      if (away) return;
      mood = cheerT > 0 ? "happy" : trip ? (trip.phase === "wait" && trip.doing === "talk" ? "talk" : trip.phase === "wait" && trip.doing ? "happy" : "calm")
        : working ? "focus" : sleeping && !act ? "sleep" : act && act.type === "talk" ? "talk" : act ? "happy" : "calm";
      if (forced) mood = forced;
      if (mo) face(t, dt);
      folder.visible = !!(trip && trip.carry && trip.seg < 2);
      if (trip) {
        const T = trip;
        if (T.phase === "up") { stand = Math.min(1, stand + dt / .45); pose(stand, false); if (stand >= 1) T.phase = "walk"; }
        else if (T.phase === "walk") {
          const a = T.pts[T.seg], b = T.pts[T.seg + 1], len = Math.max(a.distanceTo(b), .01);
          T.t += dt * 1.5 / len; walkPh += dt * 9 * mo;
          body.position.lerpVectors(a, b, Math.min(T.t, 1));
          body.rotation.y = Math.atan2(-(b.x - a.x), -(b.z - a.z));
          pose(1, true);
          if (T.t >= 1) {
            T.t = 0; T.seg++;
            if (T.seg >= T.pts.length - 1 && T.end === "hide") { trip = null; away = true; body.visible = false; body.position.copy(SEAT); stand = 0; pose(0, false); return; }
            if (T.seg === (T.waitSeg ?? 2) && T.wait) { T.phase = "wait"; T.left = T.wait; T.onWait && T.onWait(); }
            else if (T.seg >= T.pts.length - 1) T.phase = "down";
          }
        } else if (T.phase === "wait") {
          body.rotation.y = Math.atan2(-(T.look.x - body.position.x), -(T.look.z - body.position.z));
          pose(1, false); T.left -= dt; if (T.left <= 0) T.phase = "walk";
        } else if (T.phase === "down") {
          body.rotation.y = 0; stand = Math.max(0, stand - dt / .45); pose(stand, false);
          if (stand <= 0) { const done = T.onDone; trip = null; body.position.copy(SEAT); done && done(); }
        }
        head.rotation.x = 0; head.rotation.y = 0; chair.rotation.y = 0; act = null; cup.visible = false;
        if (trip && trip.phase === "wait" && trip.doing && mo) {  // what they do once there
          const D = trip.doing;
          if (D === "coffee") { cup.visible = true; shoulders[1].rotation.x = .9; arms[1].rotation.x = 1.25; head.rotation.x = -.12 * Math.max(0, Math.sin(t * 1.3)); }
          else if (D === "talk") { shoulders[Math.sin(t * .7) > 0 ? 0 : 1].rotation.x = .55 + Math.sin(t * 5) * .3; head.rotation.x = Math.sin(t * 6) * .07; }
          else if (D === "pet") { shoulders.forEach(sh => sh.rotation.x = .6); arms.forEach(a => a.rotation.x = .9 + Math.sin(t * 4) * .2); head.rotation.x = .45; torso.rotation.x = .35; }
          else if (D === "read") { shoulders.forEach(sh => sh.rotation.x = 1); arms.forEach(a => a.rotation.x = 1.1); head.rotation.x = .35; }
          else if (D === "stretch") { shoulders.forEach(sh => sh.rotation.x = 2.7 * Math.max(0, Math.sin(t * .8))); }
        }
        return;
      }
      if (cheerT > 0) {
        cheerT -= dt; pose(0, false); act = null; cup.visible = false;
        const e = Math.min(1, cheerT * 2);
        shoulders.forEach((s, k) => s.rotation.x = (2.7 + Math.sin(t * 13 + k * Math.PI) * .3) * e);
        arms.forEach(a => a.rotation.x = -.25 * e);
        pelvis.position.y = Math.abs(Math.sin(t * 9)) * .1 * e; head.rotation.x = -.25 * e; head.rotation.y = 0;
        body.rotation.y = chair.rotation.y = Math.sin(t * 3) * .25 * e;
        if (cheerT <= 0) { pelvis.position.y = 0; body.rotation.y = chair.rotation.y = 0; }
        return;
      }
      pose(0, false);
      arms.forEach((a, k) => a.rotation.x = working ? Math.sin(t * 16 + k * Math.PI) * .14 * mo : 0);
      head.rotation.x = sleeping ? .45 : working ? Math.sin(t * 3) * .05 * mo : 0;
      head.rotation.y = 0; body.rotation.y = 0; chair.rotation.y = 0;
      if (working || !mo) { act = null; cup.visible = false; return; }
      if (!act) {
        nextAct -= dt;
        if (nextAct <= 0) {
          const type = sleeping ? (Math.random() < .5 ? "stretch" : "coffee") : ACTS[Math.floor(Math.random() * ACTS.length)];
          act = { type, p: 0, dur: type === "talk" ? 5 : type === "turn" ? 3.2 : 3.6, side: Math.random() < .5 ? -1 : 1 };
        }
        return;
      }
      act.p += dt / act.dur; const e = env(Math.min(act.p, 1));
      head.rotation.x *= 1 - e;  // awake while doing it
      if (act.type === "coffee") {
        cup.visible = true; shoulders[1].rotation.x = .9 * e; arms[1].rotation.x = 1.25 * e;
        head.rotation.x = -.15 * e * Math.max(0, Math.sin(act.p * Math.PI * 3));
      } else if (act.type === "stretch") {
        shoulders.forEach(s => s.rotation.x = 2.7 * e); arms.forEach(a => a.rotation.x = -.3 * e); head.rotation.x = -.25 * e;
      } else if (act.type === "turn") {
        body.rotation.y = chair.rotation.y = Math.sin(act.p * Math.PI * 2) * .7 * act.side;
      } else if (act.type === "talk") {
        head.rotation.y = .9 * e * act.side; head.rotation.x = Math.sin(t * 7) * .06 * e;
        shoulders[act.side > 0 ? 0 : 1].rotation.x = (.5 + Math.sin(t * 5) * .25) * e;
      }
      if (act.p >= 1) { act = null; cup.visible = false; nextAct = sleeping ? 25 + Math.random() * 25 : 5 + Math.random() * 8; }
    },
  };
}

// ---------------------------------------------------------------- AI budget tank: liquid = what is left today
export function budgetTank() {
  const g = new THREE.Group();
  const metal = new THREE.MeshStandardMaterial({ color: 0x8d96a6, roughness: .3, metalness: .9 });
  const base = new THREE.Mesh(new THREE.CylinderGeometry(.5, .56, .18, 28), metal); base.position.y = .09; g.add(base);
  const top = new THREE.Mesh(new THREE.CylinderGeometry(.5, .5, .1, 28), metal); top.position.y = 1.93; g.add(top);
  const liqMat = new THREE.MeshStandardMaterial({ color: 0x3ecfb2, emissive: 0x3ecfb2, emissiveIntensity: .45, roughness: .2, transparent: true, opacity: .85 });
  const liq = new THREE.Mesh(new THREE.CylinderGeometry(.38, .38, 1, 28), liqMat); g.add(liq);
  const glass = new THREE.Mesh(new THREE.CylinderGeometry(.44, .44, 1.72, 28, 1, true),
    new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: .05, transparent: true, opacity: .16, clearcoat: 1, side: THREE.DoubleSide, depthWrite: false }));
  glass.position.y = 1.04; g.add(glass);
  for (let i = 1; i < 4; i++) {  // level marks
    const m = new THREE.Mesh(new THREE.TorusGeometry(.445, .008, 4, 40), metal); m.rotation.x = Math.PI / 2; m.position.y = .18 + i * .43; g.add(m);
  }
  shade(g);
  const H = 1.66, cold = new THREE.Color(0x3ecfb2), warm = new THREE.Color(0xffb020), hot = new THREE.Color(0xff5d73), c = new THREE.Color();
  let target = 1, level = 1;
  const draw = () => {
    liq.scale.y = Math.max(level, .02) * H; liq.position.y = .18 + liq.scale.y / 2;
    if (level > .4) c.copy(warm).lerp(cold, (level - .4) / .6); else c.copy(hot).lerp(warm, level / .4);
    liqMat.color.copy(c); liqMat.emissive.copy(c);
  };
  draw();
  return {
    group: g,
    set(today, perDay) { target = perDay ? Math.max(0, 1 - (today || 0) / perDay) : 1; },
    get left() { return target; },
    tick(dt) { if (Math.abs(level - target) < .001) return false; level += (target - level) * Math.min(1, dt * 2.5); draw(); return true; },
  };
}

// ---------------------------------------------------------------- printer: a finished product comes out
export function printer() {
  const g = new THREE.Group();
  const white = new THREE.MeshStandardMaterial({ color: 0xe8e8ea, roughness: .45 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x2a2d34, roughness: .5 });
  const cab = new THREE.Mesh(new THREE.BoxGeometry(.56, .62, .46), dark); cab.position.y = .31; g.add(cab);
  const body = new THREE.Mesh(new THREE.BoxGeometry(.5, .24, .4), white); body.position.y = .74; g.add(body);
  const lid = new THREE.Mesh(new THREE.BoxGeometry(.5, .04, .4), white); lid.position.y = .88; g.add(lid);
  const slot = new THREE.Mesh(new THREE.BoxGeometry(.38, .02, .06), dark); slot.position.set(0, .7, .2); g.add(slot);
  const ledMat = new THREE.MeshBasicMaterial({ color: 0x224433, toneMapped: false });
  const led = new THREE.Mesh(new THREE.SphereGeometry(.018, 8, 6), ledMat); led.position.set(.19, .8, .205); g.add(led);
  const paper = new THREE.Mesh(new THREE.PlaneGeometry(.3, .4), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: .9, side: THREE.DoubleSide }));
  paper.rotation.x = -Math.PI / 2 + .25; paper.position.set(0, .7, .2); paper.visible = false; g.add(paper);
  const box = new THREE.Mesh(new THREE.BoxGeometry(.22, .16, .22), new THREE.MeshStandardMaterial({ color: 0xe8b04a, roughness: .25, metalness: 1, emissive: 0x4a3000 }));
  box.visible = false; g.add(box);
  shade(g);
  let job = 0;
  return {
    group: g,
    print() { job = 2.6; },
    get busy() { return job > 0; },
    tick(dt) {
      if (job <= 0) return;
      job = Math.max(0, job - dt); const p = 1 - job / 2.6;
      ledMat.color.setHex(job > 0 && Math.sin(p * 40) > 0 ? 0x3ecfb2 : 0x224433);
      paper.visible = p > .1 && p < .95; paper.position.z = .2 + Math.min(1, (p - .1) / .4) * .22;
      box.visible = p > .45 && job > 0; box.position.set(0, .98 + Math.sin(Math.min(1, (p - .45) / .55) * Math.PI) * .35, 0); box.rotation.y = p * 6;
    },
  };
}

// ---------------------------------------------------------------- cash sound (Web Audio, no files) + mute button
let actx = null, muted = false;
try { muted = localStorage.getItem("mm-sound") === "0"; } catch (e) {}
addEventListener("pointerdown", () => { try { actx = actx || new (window.AudioContext || window.webkitAudioContext)(); actx.resume(); } catch (e) {} }, { once: false });
export const sound = {
  get muted() { return muted; },
  button(el) {
    const show = () => { el.textContent = muted ? "🔕" : "🔔"; el.title = muted ? "Suono della cassa: spento" : "Suono della cassa: acceso"; el.setAttribute("aria-pressed", String(!muted)); };
    el.onclick = () => { muted = !muted; try { localStorage.setItem("mm-sound", muted ? "0" : "1"); } catch (e) {} show(); if (!muted) sound.cash(); };
    show();
  },
  meow() {  // a soft "mi-a-o": a voice-like buzz through two moving vowel filters (i → a → o), short and quiet
    if (muted || !actx) return;
    const t0 = actx.currentTime, d = .62, o = actx.createOscillator(), vib = actx.createOscillator(), vg = actx.createGain();
    o.type = "sawtooth"; o.frequency.setValueAtTime(560, t0); o.frequency.linearRampToValueAtTime(700, t0 + .2); o.frequency.exponentialRampToValueAtTime(430, t0 + d);
    vib.frequency.value = 6; vg.gain.value = 9; vib.connect(vg); vg.connect(o.frequency);
    const out = actx.createGain(); out.gain.setValueAtTime(0, t0); out.gain.linearRampToValueAtTime(.09, t0 + .06);
    out.gain.setValueAtTime(.09, t0 + d * .65); out.gain.exponentialRampToValueAtTime(.001, t0 + d);
    for (const [f1, f2, f3, q, v] of [[350, 820, 520, 7, 1], [2200, 1250, 880, 9, .6]]) {  // F1 and F2 of i, a, o
      const f = actx.createBiquadFilter(), g = actx.createGain(); f.type = "bandpass"; f.Q.value = q; g.gain.value = v;
      f.frequency.setValueAtTime(f1, t0); f.frequency.linearRampToValueAtTime(f2, t0 + .22); f.frequency.linearRampToValueAtTime(f3, t0 + d);
      o.connect(f); f.connect(g); g.connect(out);
    }
    const lp = actx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 3200; out.connect(lp); lp.connect(actx.destination);
    o.start(t0); vib.start(t0); o.stop(t0 + d + .05); vib.stop(t0 + d + .05);
  },
  purr() {  // the purr: low rumble pulsing about 25 times a second, for two seconds
    if (muted || !actx) return;
    const t0 = actx.currentTime, d = 2.2, len = Math.floor(actx.sampleRate * d);
    const buf = actx.createBuffer(1, len, actx.sampleRate), x = buf.getChannelData(0);
    for (let i = 0, b = 0; i < len; i++) {
      b = b * .97 + (Math.random() * 2 - 1) * .03;  // brown-ish noise
      const ti = i / actx.sampleRate, breath = .55 + .45 * Math.sin(ti * Math.PI * 2 / 1.1);  // in and out
      x[i] = b * 6 * Math.pow(Math.max(0, Math.sin(ti * Math.PI * 2 * 26)), 3) * breath;
    }
    const src = actx.createBufferSource(); src.buffer = buf;
    const lp = actx.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 380;
    const g = actx.createGain(); g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(.35, t0 + .25); g.gain.setValueAtTime(.35, t0 + d - .5); g.gain.linearRampToValueAtTime(0, t0 + d);
    src.connect(lp); lp.connect(g); g.connect(actx.destination); src.start(t0);
  },
  ding() {  // shop counter bell
    if (muted || !actx) return;
    const t0 = actx.currentTime;
    for (const [f, v] of [[1568, .35], [3136, .12], [4700, .05]]) {
      const o = actx.createOscillator(), g = actx.createGain(); o.type = "sine"; o.frequency.value = f;
      g.gain.setValueAtTime(0, t0); g.gain.linearRampToValueAtTime(v, t0 + .005); g.gain.exponentialRampToValueAtTime(.001, t0 + 1.4);
      o.connect(g); g.connect(actx.destination); o.start(t0); o.stop(t0 + 1.5);
    }
  },
  slot() {  // the reels' ratchet: a run of short clicks that slows down
    if (muted || !actx) return;
    const t0 = actx.currentTime, out = actx.createGain(); out.gain.value = .18; out.connect(actx.destination);
    const n = actx.createBuffer(1, actx.sampleRate * .015, actx.sampleRate), d = n.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    for (let k = 0, at = 0; k < 22; k++, at += .035 + k * .004) { const ns = actx.createBufferSource(); ns.buffer = n; ns.playbackRate.value = .8 + Math.random() * .4; ns.connect(out); ns.start(t0 + at); }
  },
  fanfare() {  // short rising arpeggio and a final chord
    if (muted || !actx) return;
    const t0 = actx.currentTime, out = actx.createGain(); out.gain.value = .16; out.connect(actx.destination);
    for (const [f, at, len] of [[523, 0, .16], [659, .14, .16], [784, .28, .16], [1047, .42, .9], [784, .42, .9], [659, .42, .9]]) {
      const o = actx.createOscillator(), gg = actx.createGain(); o.type = "square"; o.frequency.value = f;
      gg.gain.setValueAtTime(0, t0 + at); gg.gain.linearRampToValueAtTime(.4, t0 + at + .02); gg.gain.exponentialRampToValueAtTime(.001, t0 + at + len);
      o.connect(gg); gg.connect(out); o.start(t0 + at); o.stop(t0 + at + len + .05);
    }
  },
  cash() {
    if (muted || !actx) return;
    const t0 = actx.currentTime, out = actx.createGain(); out.gain.value = .25; out.connect(actx.destination);
    // "ka": short noise click of the drawer
    const n = actx.createBuffer(1, actx.sampleRate * .06, actx.sampleRate), d = n.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
    const ns = actx.createBufferSource(); ns.buffer = n; ns.connect(out); ns.start(t0);
    // "ching": two bright bell tones
    for (const [f, at] of [[2093, .07], [2637, .13], [3136, .13]]) {
      const o = actx.createOscillator(), gg = actx.createGain(); o.type = "triangle"; o.frequency.value = f;
      gg.gain.setValueAtTime(0, t0 + at); gg.gain.linearRampToValueAtTime(.5, t0 + at + .01); gg.gain.exponentialRampToValueAtTime(.001, t0 + at + .9);
      o.connect(gg); gg.connect(out); o.start(t0 + at); o.stop(t0 + at + 1);
    }
  },
};

// ---------------------------------------------------------------- the office cat, with its climbing trees and toys
// Lives in the left part of the room (x0..x1, z0..z1): walks, eats, plays with the yarn, climbs, sleeps.
function sisal() {
  return canvasTex(64, 256, (g, w, h) => {
    g.fillStyle = "#c9a66b"; g.fillRect(0, 0, w, h);
    for (let y = 0; y < h; y += 5) { g.fillStyle = `rgba(90,60,20,${rnd(.25, .45)})`; g.fillRect(0, y, w, 2); }
  }, [1, 4]);
}

export function catCorner(scene, { x0 = -13.8, x1 = -9.2, z0 = -7, z1 = 2.8, name = "Micio", coat = "tuxedo" } = {}) {
  const corner = new THREE.Group(); scene.add(corner);
  const carpet = new THREE.MeshStandardMaterial({ color: 0x8c8c94, roughness: 1 });
  const rope = new THREE.MeshStandardMaterial({ map: sisal(), roughness: .95 });
  const wood = new THREE.MeshStandardMaterial({ color: 0xb08a5a, roughness: .7 });
  const M = (geo, m, x, y, z, parent = corner) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); parent.add(o); return o; };
  const spots = [];  // perches: {local, tree, where}

  // tall tree: base, two sisal posts, three platforms, cubby on the top, pompom on a string
  const t1 = new THREE.Group(); t1.position.set(x0 + .5, 0, z0 + 1.2); corner.add(t1);
  M(new THREE.BoxGeometry(1.1, .1, 1.1), carpet, 0, .05, 0, t1);
  M(new THREE.CylinderGeometry(.09, .09, 1.9, 16), rope, -.25, 1.05, -.2, t1);
  M(new THREE.CylinderGeometry(.08, .08, 1.2, 16), rope, .3, .7, .25, t1);
  for (const [px, py, pz, r, where] of [[.3, 1.3, .25, .36, null], [-.25, 2.0, -.2, .42, "in cima all'albero alto"], [-.1, .75, -.3, .3, "sul ripiano basso dell'albero"]]) {
    M(new THREE.CylinderGeometry(r, r, .07, 24), carpet, px, py, pz, t1);
    if (where) spots.push({ local: new THREE.Vector3(px, py + .035, pz), tree: t1, where });
  }
  M(new THREE.BoxGeometry(.5, .38, .46), carpet, .3, 1.53, .25, t1);  // cubby on the middle platform: the cat sits on its roof
  M(new THREE.CircleGeometry(.13, 20), new THREE.MeshStandardMaterial({ color: 0x2a2a30, roughness: 1 }), .3, 1.53, .481, t1);
  spots.push({ local: new THREE.Vector3(.3, 1.72, .25), tree: t1, where: "sul tetto della cuccetta" });
  const string = M(new THREE.CylinderGeometry(.004, .004, .45, 4), new THREE.MeshBasicMaterial({ color: 0x222222 }), -.55, 1.73, -.2, t1);
  const pom = M(new THREE.SphereGeometry(.06, 12, 10), new THREE.MeshStandardMaterial({ color: 0xff5fa2, roughness: 1 }), -.55, 1.48, -.2, t1);
  M(new THREE.BoxGeometry(.4, .03, .03), wood, -.4, 1.96, -.2, t1);

  // short tree with a hammock
  const t2 = new THREE.Group(); t2.position.set(x0 + .4, 0, z1 - 1.4); corner.add(t2);
  M(new THREE.BoxGeometry(.9, .1, .9), carpet, 0, .05, 0, t2);
  for (const [px, pz] of [[-.3, -.3], [.3, -.3], [-.3, .3], [.3, .3]]) M(new THREE.CylinderGeometry(.05, .05, .9, 12), rope, px, .5, pz, t2);
  M(new THREE.BoxGeometry(.8, .06, .8), carpet, 0, .95, 0, t2);
  const hammock = M(new THREE.SphereGeometry(.34, 20, 8, 0, Math.PI * 2, Math.PI * .62, Math.PI * .38), new THREE.MeshStandardMaterial({ color: 0x3e6ea8, roughness: .95, side: THREE.DoubleSide }), 0, .72, 0, t2);
  hammock.scale.y = .6;
  spots.push({ local: new THREE.Vector3(0, .98, 0), tree: t2, where: "sull'albero con l'amaca" });

  // bed, bowls, toys
  const bed = new THREE.Group(); bed.position.set(x0 + 2.2, 0, z0 + .6); corner.add(bed);
  M(new THREE.TorusGeometry(.3, .1, 12, 28), new THREE.MeshStandardMaterial({ color: 0x6a4c93, roughness: 1 }), 0, .1, 0, bed).rotation.x = Math.PI / 2;
  M(new THREE.CylinderGeometry(.28, .28, .07, 24), new THREE.MeshStandardMaterial({ color: 0xe8dcc8, roughness: 1 }), 0, .05, 0, bed);
  const bowls = new THREE.Group(); bowls.position.set(x1 - .6, 0, z0 + 1.6); corner.add(bowls);
  const steel = new THREE.MeshStandardMaterial({ color: 0xc8ccd4, roughness: .25, metalness: .9 });
  for (const [bx, top] of [[-.16, 0x7a4a26], [.16, 0x7fb6e6]]) {
    M(new THREE.CylinderGeometry(.12, .09, .07, 20), steel, bx, .035, 0, bowls);
    M(new THREE.CylinderGeometry(.1, .1, .01, 20), new THREE.MeshStandardMaterial({ color: top, roughness: top === 0x7fb6e6 ? .05 : .9 }), bx, .066, 0, bowls);
  }
  const yarnHome = new THREE.Vector3(x1 - 1, .09, (z0 + z1) / 2 + .8);
  const yarn = new THREE.Group(); yarn.position.copy(yarnHome); corner.add(yarn);
  const yarnMat = new THREE.MeshStandardMaterial({ color: 0xd63a4a, roughness: 1 });
  M(new THREE.SphereGeometry(.09, 14, 12), yarnMat, 0, 0, 0, yarn);
  for (let i = 0; i < 4; i++) { const r = M(new THREE.TorusGeometry(.09, .008, 4, 24), yarnMat, 0, 0, 0, yarn); r.rotation.set(i * .8, i * 1.3, 0); }
  const mouse = new THREE.Group(); mouse.position.set(x1 - .3, 0, z1 - .6); mouse.rotation.y = 2.2; corner.add(mouse);
  const grey = new THREE.MeshStandardMaterial({ color: 0x9a9aa2, roughness: 1 });
  M(new THREE.SphereGeometry(.05, 10, 8), grey, 0, .04, 0, mouse).scale.set(.8, .7, 1.4);
  for (const ex of [-.025, .025]) M(new THREE.SphereGeometry(.018, 8, 6), grey, ex, .075, .05, mouse);
  M(new THREE.CylinderGeometry(.004, .004, .12, 4), grey, 0, .02, -.1, mouse).rotation.x = Math.PI / 2;
  const scratch = M(new THREE.BoxGeometry(.5, .06, .25), rope, x1 - .5, .03, z0 + .4); scratch.rotation.y = .3;  // flat scratcher
  shade(corner);

  // ---- the cat (faces +z): body, head, jointed legs and tail; the coat is painted per vertex
  const m = catModel(coat);
  m.hat.visible = seasonOf() === "natale";
  const cat = new THREE.Group(); corner.add(cat); cat.add(m.root);

  // ---- behaviour: a queue of steps; each step moves the cat or holds a pose (poses blend smoothly)
  const lo = new THREE.Vector3(x0 + .6, 0, z0 + .3), hi = new THREE.Vector3(x1 - .2, 0, z1 - .3);
  const floorPt = () => new THREE.Vector3(lo.x + Math.random() * (hi.x - lo.x), 0, lo.z + Math.random() * (hi.z - lo.z));
  const world = (s) => s.tree.localToWorld(s.local.clone()).sub(corner.position);
  cat.position.copy(bed.position);
  let queue = [], cur = null, pose = "sleep", doing = "dorme nella cuccia", walkPh = 0, perch = null, jump = null;
  let lastPoke = 0, heart = null, zoom = 0;
  const plan = () => {
    corner.updateMatrixWorld(true);
    const night = dayPart() === "night", r = Math.random() * (night ? .75 : 1) + (night ? .25 : 0);  // at night it naps more
    const down = perch ? [{ type: "jump", to: perch.foot.clone(), then: () => { perch = null; } }] : [];
    const idle = [["sit", "si guarda intorno"], ["loaf", "è accucciato a pagnotta"], ["lick", "si lecca la zampa"], ["stretch", "si stiracchia"]][Math.floor(Math.random() * 4)];
    if (r < .22) queue = [...down, { type: "walk", to: floorPt() }, { type: "stay", pose: idle[0], dur: idle[0] === "stretch" ? 3 : 4 + Math.random() * 4, what: idle[1] }];
    else if (r < .34) queue = [...down, { type: "walk", to: bowls.position.clone().add(new THREE.Vector3(-.16, 0, -.34)) }, { type: "stay", pose: "eat", dur: 4 + Math.random() * 3, what: "mangia" }];
    else if (r < .5) queue = [...down, { type: "walk", to: yarn.position.clone().setY(0).add(new THREE.Vector3(0, 0, -.36)) }, { type: "play", dur: 5, what: "gioca col gomitolo" }];
    else if (r < .75) {
      const s = spots[Math.floor(Math.random() * spots.length)], top = world(s);
      const foot = top.clone().setY(0).add(new THREE.Vector3(.55, 0, .4));
      queue = [...down, { type: "walk", to: foot }, { type: "jump", to: top, then: () => { perch = { foot }; } }];
      const nap = Math.random() < .6;
      queue.push({ type: "stay", pose: nap ? "sleep" : "loaf", dur: 8 + Math.random() * 10, what: `${nap ? "dorme" : "si gode la vista"} ${s.where}` });
    } else queue = [...down, { type: "walk", to: bed.position.clone() }, { type: "stay", pose: "sleep", dur: 12 + Math.random() * 10, what: "dorme nella cuccia" }];
  };
  const face = (from, to) => { const d = to.clone().sub(from); if (d.lengthSq() > 1e-4) cat.rotation.y = Math.atan2(d.x, d.z); };
  const showHeart = () => {
    if (!heart) {
      const c = document.createElement("canvas"); c.width = c.height = 64; const g = c.getContext("2d");
      g.fillStyle = "#ff4d6d"; g.beginPath(); g.moveTo(32, 56); g.bezierCurveTo(2, 35, 7, 5, 32, 20); g.bezierCurveTo(57, 5, 62, 35, 32, 56); g.fill();
      const tx = new THREE.CanvasTexture(c); tx.colorSpace = THREE.SRGBColorSpace;
      heart = new THREE.Sprite(new THREE.SpriteMaterial({ map: tx, transparent: true, depthWrite: false })); heart.scale.setScalar(.14); cat.add(heart);
    }
    heart.userData.t = 0; heart.visible = true;
  };
  return {
    group: cat, corner, name,
    get doing() { return doing; },
    get busy() { return !!(heart && heart.visible) || zoom > 0; },
    // a tap: it turns to you, tail up, a heart and a purr; a second tap soon after: belly up for scratches
    poke() {
      const now = performance.now(), twice = now - lastPoke < 900; lastPoke = now;
      if (jump || (cur && cur.type === "jump")) return;
      queue = perch ? [] : queue;
      cur = twice && !perch ? { type: "stay", pose: "belly", dur: 3.5, what: "si fa grattare la pancia" } : { type: "stay", pose: "happy", dur: 2.6, what: "fa le fusa" };
      cur.left = cur.dur; doing = cur.what; showHeart();
      if (twice) sound.purr(); else { sound.meow(); setTimeout(() => sound.purr(), 650); }
    },
    // first real sale: a few seconds of happy running around (zoomies) and jumps
    party() { if (!perch) { queue = []; cur = null; zoom = 6; } },
    tick(dt, t) {
      if (heart && heart.visible) {
        heart.userData.t += dt; const k = heart.userData.t / 1.4;
        heart.position.set(0, .62 + k * .35, .2); heart.material.opacity = 1 - k * k; if (k >= 1) heart.visible = false;
      }
      if (zoom > 0) {  // zoomies: quick dashes to random points with little hops
        zoom -= dt;
        if (!cur || cur.type !== "dash") cur = { type: "dash", to: floorPt() };
        const d = cur.to.clone().sub(cat.position); d.y = 0; const dist = d.length();
        if (dist < .05) cur = null;
        else { face(cat.position, cur.to); cat.position.addScaledVector(d.normalize(), Math.min(dist, dt * 2.2)); }
        walkPh += dt * 22; cat.position.y = Math.abs(Math.sin(walkPh * .5)) * .08;
        doing = "festeggia correndo"; m.blend("walk", dt, t, walkPh, 10);
        if (zoom <= 0) { cur = null; cat.position.y = 0; }
        return;
      }
      if (!cur) { if (!queue.length) plan(); cur = queue.shift(); if (!cur) return; cur.left = cur.dur; cur.from = cat.position.clone(); cur.p = 0; }
      if (cur.type === "walk") {
        const d = cur.to.clone().sub(cat.position); d.y = 0; const dist = d.length();
        doing = "passeggia";
        if (dist < .03) { cur = null; m.blend("stand", dt, t); return; }
        face(cat.position, cur.to); const step = Math.min(dist, dt * .7);
        cat.position.addScaledVector(d.normalize(), step); cat.position.y = 0;
        walkPh += dt * 9; m.blend("walk", dt, t, walkPh, 12);
      } else if (cur.type === "jump") {
        doing = "salta"; cur.p = Math.min(1, cur.p + dt / .55);
        face(cur.from, cur.to);
        cat.position.lerpVectors(cur.from, cur.to, cur.p); cat.position.y += Math.sin(cur.p * Math.PI) * .6;
        m.blend(cur.p < .5 ? "leap" : "land", dt, t, 0, 18);
        if (cur.p >= 1) { cur.then && cur.then(); cur = null; }
      } else if (cur.type === "play") {
        doing = cur.what; cur.left -= dt;
        m.blend("play", dt, t);
        yarn.position.x = yarnHome.x + Math.sin(t * 2.3) * .12; yarn.rotation.z = -Math.sin(t * 2.3) * 1.3;
        if (cur.left <= 0) { cur = null; yarn.position.copy(yarnHome); }
      } else {
        doing = cur.what; pose = cur.pose; cur.left -= dt; if (cur.left <= 0) cur = null;
        m.blend(pose, dt, t);
      }
      pom.position.x = -.55 + Math.sin(t * 1.3) * .03; string.rotation.z = Math.sin(t * 1.3) * .05;
    },
  };
}

// ---------------------------------------------------------------- the cat's body (tuxedo by default)
// Every joint has a target per pose; blend() moves the joints towards it, so poses change smoothly.
const CAT_COATS = {
  tuxedo: { base: "#222226", dark: "#222226", white: "#f5f3ee", eye: 0xf4c430, kind: "solid" },
  rosso: { base: "#e2934a", dark: "#a8561f", white: "#f7efe4", eye: 0x9ad44f, kind: "tabby" },
  grigio: { base: "#a2a7ae", dark: "#4a4f57", white: "#f2f2ef", eye: 0xf2b33d, kind: "tabby" },
  calico: { base: "#f5f0e6", dark: "#2b2625", orange: "#e0883a", white: "#f5f0e6", eye: 0x6fbf4a, kind: "calico" },
};
function catCoatColor(c, p, part) {
  const C = h => new THREE.Color(h);
  const n = Math.sin(p.x * 31 + 1.3) * Math.sin(p.y * 27 + .7) * Math.sin(p.z * 23 + 2.1);
  let white = part === "muzzle" || part === "paw";
  if (part === "body" && p.y < .205) white = true;  // belly
  if ((part === "body" || part === "neck") && p.z > .06 && p.y < .36 && Math.abs(p.x) < .06 + (.36 - p.y) * .3) white = true;  // bib
  if (c.kind === "calico") { if (white) return C(c.white); const k = n + Math.sin(p.z * 9 + p.x * 4) * .45; return C(k > .2 ? c.orange : k < -.35 ? c.dark : c.white); }
  if (white) return C(c.white);
  if (c.kind === "solid") return C(c.base);
  let s = -1;
  if (part === "body" || part === "neck") s = Math.sin(p.z * 62 + n * 2 + Math.abs(p.x) * 18 - p.y * 8);
  else if (part === "head") s = p.y > .475 && p.z < .3 ? Math.sin(p.x * 120 + n) : Math.sin((p.y - Math.abs(p.x) * .6) * 90);
  else if (part === "leg") s = p.y > .12 ? Math.sin(p.y * 60 + n) - .3 : -1;
  else if (part === "tail") s = Math.sin(p.z * 60);
  return C(c.base).lerp(C(c.dark), s > .35 ? 1 : s > .1 ? .5 : 0);
}
function catModel(coatName = "tuxedo") {
  const coat = CAT_COATS[coatName] || CAT_COATS.tuxedo;
  const fur = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .85 });
  const root = new THREE.Group(), painted = [];
  const blob = (parent, part, pos, scale, rot = [0, 0, 0], geo = null) => {
    const mm = new THREE.Mesh(geo || new THREE.SphereGeometry(1, 22, 16), fur); mm.position.set(...pos); mm.scale.set(...scale); mm.rotation.set(...rot);
    mm.castShadow = true; mm.userData.part = part; parent.add(mm); painted.push(mm); return mm;
  };
  const cap = (r, len) => new THREE.CapsuleGeometry(r, len, 5, 12);
  const grp = (parent, pos, rot = [0, 0, 0]) => { const g = new THREE.Group(); g.position.set(...pos); g.rotation.set(...rot); parent.add(g); return g; };
  const body = grp(root, [0, .27, -.1]);  // pivot at the hips
  blob(body, "body", [0, .005, -.01], [.125, .12, .13]); blob(body, "body", [0, -.005, .1], [.112, .108, .15]); blob(body, "body", [0, .012, .2], [.108, .118, .11]);
  const neck = grp(body, [0, .07, .27], [-.55, 0, 0]); blob(neck, "neck", [0, 0, 0], [.072, .085, .07]);
  const head = grp(body, [0, .16, .33]);
  blob(head, "head", [0, 0, 0], [.112, .096, .098]);
  for (const sx of [-1, 1]) blob(head, "head", [sx * .045, -.03, .035], [.06, .048, .056]);
  for (const sx of [-1, 1]) blob(head, "muzzle", [sx * .021, -.036, .083], [.028, .022, .022]);
  blob(head, "muzzle", [0, -.058, .066], [.026, .016, .022]);
  const pink = new THREE.MeshStandardMaterial({ color: 0xee8f9e, roughness: .6 });
  const nose = new THREE.Mesh(new THREE.ConeGeometry(.014, .016, 3), pink); nose.rotation.set(Math.PI / 2 + .3, 0, Math.PI); nose.position.set(0, -.016, .1); head.add(nose);
  const iris = new THREE.MeshStandardMaterial({ color: coat.eye, roughness: .15, emissive: coat.eye, emissiveIntensity: .15 });
  const black = new THREE.MeshStandardMaterial({ color: 0x050505, roughness: .1 }), glintM = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const eyes = [-1, 1].map(sx => {
    const e = grp(head, [sx * .041, .008, .078], [0, sx * .32, 0]);
    const ball = new THREE.Mesh(new THREE.SphereGeometry(.025, 16, 12), iris); ball.scale.set(1, .9, .55); e.add(ball);
    const pup = new THREE.Mesh(new THREE.SphereGeometry(.025, 12, 8), black); pup.scale.set(.32, .82, .3); pup.position.z = .009; e.add(pup);
    const gl = new THREE.Mesh(new THREE.SphereGeometry(.005, 6, 4), glintM); gl.position.set(.007, .009, .015); e.add(gl);
    return { ball, pup, gl };
  });
  for (const sx of [-1, 1]) {
    const g = grp(head, [sx * .056, .07, -.008], [-.12, sx * .25, -sx * .32]);
    blob(g, "head", [0, .042, 0], [1, 1, .45], [0, 0, 0], new THREE.ConeGeometry(.046, .09, 16));
    const inner = new THREE.Mesh(new THREE.ConeGeometry(.03, .065, 12), pink); inner.scale.z = .35; inner.position.set(0, .035, .012); g.add(inner);
  }
  const wh = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: .8 });
  for (const sx of [-1, 1]) for (const dy of [-.012, 0, .012])
    head.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(sx * .035, -.035, .09), new THREE.Vector3(sx * .16, -.03 + dy * 2.2, .07)]), wh));
  const front = [-1, 1].map(sx => {
    const sh = grp(body, [sx * .062, -.01, .2]);
    blob(sh, "leg", [0, .01, 0], [.05, .07, .055]); blob(sh, "leg", [0, -.06, 0], [1, 1, 1], [0, 0, 0], cap(.032, .08));
    const el = grp(sh, [0, -.12, 0]);
    blob(el, "leg", [0, 0, 0], [.03, .03, .03]); blob(el, "leg", [0, -.05, 0], [1, 1, 1], [0, 0, 0], cap(.027, .075));
    blob(el, "paw", [0, -.112, .012], [.034, .022, .042]);
    return { sh, el };
  });
  const back = [-1, 1].map(sx => {
    const hip = grp(body, [sx * .07, -.01, -.03]);
    blob(hip, "leg", [0, -.04, .01], [.066, .1, .08]);
    const kn = grp(hip, [0, -.11, .035], [.55, 0, 0]);
    blob(kn, "leg", [0, 0, 0], [.03, .03, .03]); blob(kn, "leg", [0, -.045, 0], [1, 1, 1], [0, 0, 0], cap(.026, .07));
    const ho = grp(kn, [0, -.1, 0], [-.55, 0, 0]);
    blob(ho, "leg", [0, 0, 0], [.024, .024, .024]); blob(ho, "leg", [0, -.025, 0], [1, 1, 1], [0, 0, 0], cap(.021, .03));
    blob(ho, "paw", [0, -.052, .014], [.032, .02, .044]);
    return { hip, kn, ho };
  });
  const tail = []; let par = grp(body, [0, .045, -.13]);
  for (let i = 0; i < 11; i++) {
    const s = grp(par, i ? [0, 0, -.042] : [0, 0, 0]);
    blob(s, "tail", [0, 0, -.021], [1, 1, 1], [Math.PI / 2, 0, 0], cap(.024 - i * .0011, .03));
    tail.push(s); par = s;
  }
  root.updateMatrixWorld(true);  // paint the coat in the rest pose
  const v = new THREE.Vector3();
  for (const mm of painted) {
    const pos = mm.geometry.attributes.position, cols = new Float32Array(pos.count * 3);
    for (let i = 0; i < pos.count; i++) {
      v.fromBufferAttribute(pos, i).applyMatrix4(mm.matrixWorld);
      const c = catCoatColor(coat, v, mm.userData.part); cols[i * 3] = c.r; cols[i * 3 + 1] = c.g; cols[i * 3 + 2] = c.b;
    }
    mm.geometry.setAttribute("color", new THREE.BufferAttribute(cols, 3));
  }
  const hat = new THREE.Group(); hat.position.set(0, .085, -.005); hat.rotation.set(-.35, 0, .25); hat.visible = false; head.add(hat);
  const hatR = new THREE.MeshStandardMaterial({ color: 0xd62839, roughness: .8 }), hatW = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 1 });
  const cone = new THREE.Mesh(new THREE.ConeGeometry(.085, .2, 20), hatR); cone.position.y = .1; hat.add(cone);
  const rim = new THREE.Mesh(new THREE.TorusGeometry(.085, .022, 10, 24), hatW); rim.rotation.x = Math.PI / 2; hat.add(rim);
  const pom = new THREE.Mesh(new THREE.SphereGeometry(.03, 12, 10), hatW); pom.position.y = .21; hat.add(pom);
  shade(root);

  // joints moved by the poses, with their rest values
  const J = [root, body, neck, head, ...front.flatMap(f => [f.sh, f.el]), ...back.flatMap(b => [b.hip, b.kn, b.ho]), ...tail];
  const restRot = J.map(o => o.rotation.clone()), restPos = J.map(o => o.position.clone());
  const tailShape = (shape, t) => tail.forEach((s, i) => {
    const w = Math.sin(t * 1.6 - i * .5) * .08;
    if (shape === "up") s.rotation.set(i === 0 ? 1.25 : i < 6 ? .05 : -.32, w, 0);
    else if (shape === "wrap") s.rotation.set(i === 0 ? -1.1 : 0, i === 0 ? 0 : .32, 0);
    else if (shape === "curl") s.rotation.set(i === 0 ? -.5 : 0, i === 0 ? .9 : .38, 0);
    else s.rotation.set(i === 0 ? -.35 : i < 5 ? .06 : .14, w, 0);
  });
  const sit = () => {
    body.rotation.x = -.62; body.position.y = .2; for (const f of front) f.sh.rotation.x = .62;
    for (const b of back) { b.hip.rotation.x = -.9; b.kn.rotation.x = 2.1; b.ho.rotation.x = -1.6; }
    head.rotation.x = .5; neck.rotation.x = -.2;
  };
  const loaf = () => {
    body.position.y = .15; for (const f of front) { f.sh.rotation.x = -1.45; f.el.rotation.x = 2.6; }
    for (const b of back) { b.hip.rotation.x = -1.1; b.kn.rotation.x = 2.2; b.ho.rotation.x = -1.3; }
  };
  const POSES = {
    stand: (t) => tailShape("relax", t),
    walk: (t, ph) => {
      const a = Math.sin(ph);
      front[0].sh.rotation.x = a * .45; front[1].sh.rotation.x = -a * .45;
      front[0].el.rotation.x = Math.min(0, a) * .7; front[1].el.rotation.x = Math.min(0, -a) * .7;
      back[0].hip.rotation.x = -a * .4; back[1].hip.rotation.x = a * .4;
      body.position.y += Math.abs(Math.sin(ph)) * .008; head.rotation.x = .1; tailShape("relax", t);
    },
    sit: (t) => { sit(); tailShape("wrap", t); head.rotation.y = Math.sin(t * .4) * .5; },
    loaf: (t) => { loaf(); head.rotation.y = Math.sin(t * .3) * .35; tailShape("curl", t); },
    sleep: (t) => { loaf(); body.position.y = .13; head.rotation.set(.55, .5, .35); tailShape("curl", t); },
    eat: (t) => { for (const f of front) f.sh.rotation.x = -.15; body.rotation.x = .18; head.rotation.x = .9 + Math.sin(t * 9) * .1; tailShape("relax", t); },
    play: (t) => { sit(); const k = Math.sin(t * 6) > .5; front[0].sh.rotation.x = k ? -.9 : .62; front[0].el.rotation.x = k ? -.3 : 0; head.rotation.x = .75; tailShape("relax", t); },
    stretch: (t) => { body.rotation.x = .3; for (const f of front) { f.sh.rotation.x = -1.25; f.el.rotation.x = .2; } for (const b of back) b.hip.rotation.x = -.25; head.rotation.x = -.35; tailShape("up", t); },
    lick: (t) => { sit(); front[1].sh.rotation.x = -2.05; front[1].el.rotation.x = 1.9; head.rotation.set(.75 + Math.sin(t * 7) * .08, -.3, .15); tailShape("wrap", t); },
    happy: (t) => { tailShape("up", t); head.rotation.set(-.15, 0, Math.sin(t * 2) * .12); },
    belly: (t) => {
      root.rotation.z = Math.PI * .82; root.position.set(.15, .42, 0);  // rolled around the body, not the feet
      for (const f of front) { f.sh.rotation.x = -.9 + Math.sin(t * 5) * .15; f.el.rotation.x = 1.6; }
      for (const b of back) { b.hip.rotation.x = -.5; b.kn.rotation.x = 1.2; }
      head.rotation.set(-.2, 0, -.5); tailShape("relax", t);
    },
    leap: () => { for (const f of front) f.sh.rotation.x = -1.1; for (const b of back) b.hip.rotation.x = .8; body.rotation.x = -.2; tailShape("relax", 0); },
    land: () => { for (const f of front) f.sh.rotation.x = -.4; for (const b of back) b.hip.rotation.x = .3; tailShape("relax", 0); },
  };
  const tgtRot = J.map(() => new THREE.Euler()), tgtPos = J.map(() => new THREE.Vector3()), curRot = J.map(o => o.rotation.clone()), curPos = J.map(o => o.position.clone());
  let blink = 3;
  return {
    root, hat,
    blend(name, dt, t, ph = 0, speed = 6) {
      J.forEach((o, i) => { o.rotation.copy(restRot[i]); o.position.copy(restPos[i]); });
      (POSES[name] || POSES.stand)(t, ph);
      const k = Math.min(1, dt * speed);
      J.forEach((o, i) => {
        tgtRot[i].copy(o.rotation); tgtPos[i].copy(o.position);
        curRot[i].x += (tgtRot[i].x - curRot[i].x) * k; curRot[i].y += (tgtRot[i].y - curRot[i].y) * k; curRot[i].z += (tgtRot[i].z - curRot[i].z) * k;
        curPos[i].lerp(tgtPos[i], k); o.rotation.copy(curRot[i]); o.position.copy(curPos[i]);
      });
      const closed = name === "sleep" || name === "lick" || name === "stretch";
      blink -= dt; const blinking = blink < .12; if (blink < 0) blink = 2.5 + Math.random() * 4;
      for (const e of eyes) {
        const shut = closed || blinking;
        e.ball.scale.y = shut ? .12 : (name === "happy" ? .6 : .9); e.pup.visible = e.gl.visible = !shut;
        e.pup.scale.x = name === "happy" || name === "play" ? .55 : .32;
      }
    },
  };
}

// ---------------------------------------------------------------- camera tour: a slow flight around the room
// Start/stop with toggle(); any drag or pinch on the view stops it. Remembered per browser, so a room left on
// the tour starts touring again next time (an animated background).
export function cameraTour(camera, controls, { center = new THREE.Vector3(0, 1.4, .5), storeKey = "mm-tour", onChange = () => {} } = {}) {
  let on = false, t = 0, a0 = 0;
  const from = { p: new THREE.Vector3(), q: new THREE.Vector3() }, p = new THREE.Vector3(), q = new THREE.Vector3();
  const save = v => { try { localStorage.setItem(storeKey, v ? "1" : "0"); } catch (e) {} };
  const api = {
    get active() { return on; },
    start() {
      if (on) return; on = true; t = 0;
      from.p.copy(camera.position); from.q.copy(controls.target);
      a0 = Math.atan2(camera.position.x - center.x, camera.position.z - center.z);  // start where the camera already is
      save(true); onChange(true);
    },
    stop() { if (!on) return; on = false; save(false); onChange(false); },
    toggle() { on ? api.stop() : api.start(); },
    tick(dt) {
      if (!on) return;
      t += dt;
      const a = a0 + t * .055, r = 15.5 + 4 * Math.sin(t * .09), y = 4.5 + 4.5 * (.5 + .5 * Math.sin(t * .05 + 1.3));
      p.set(center.x + Math.sin(a) * r, y, center.z + Math.cos(a) * r * .8);
      q.set(center.x + Math.sin(t * .13) * 3, center.y + Math.sin(t * .07) * .4, center.z + Math.cos(t * .11) * 2);
      const k = Math.min(1, t / 4), e = k * k * (3 - 2 * k);  // ease in from where the camera was
      camera.position.lerpVectors(from.p, p, e); controls.target.lerpVectors(from.q, q, e);
    },
  };
  controls.addEventListener("start", () => api.stop());  // the user takes the camera back
  try { if (localStorage.getItem(storeKey) === "1") setTimeout(() => api.start(), 1500); } catch (e) {}
  return api;
}

// ---------------------------------------------------------------- material helpers for props
export const materials = {
  woodCrate: () => new THREE.MeshStandardMaterial({ map: woodPlanks(0x9a7448, 4), roughness: .75 }),
  paintedCrate: color => new THREE.MeshStandardMaterial({ map: woodPlanks(color, 4), roughness: .6 }),
  gold: () => new THREE.MeshStandardMaterial({ color: 0xffc85a, roughness: .22, metalness: 1, emissive: 0x4a3000 }),
  steel: (color = 0x8d96a6) => new THREE.MeshStandardMaterial({ color, roughness: .32, metalness: .9 }),
  rubber: () => new THREE.MeshStandardMaterial({ color: 0x1c1f25, roughness: .95 }),
  cork: () => new THREE.MeshStandardMaterial({ map: canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = "#a47a4c"; g.fillRect(0, 0, w, h);
    for (let i = 0; i < 2600; i++) { g.fillStyle = `rgba(${rnd(60, 120) | 0},${rnd(35, 70) | 0},${rnd(15, 35) | 0},${rnd(.3, .8)})`; g.fillRect(rnd(0, w), rnd(0, h), rnd(1, 3), rnd(1, 3)); }
  }), roughness: .95 }),
  glass: (tint = 0xffffff) => new THREE.MeshPhysicalMaterial({ color: tint, roughness: .05, metalness: 0, transparent: true, opacity: .12, clearcoat: 1, side: THREE.DoubleSide, depthWrite: false }),
};

// ---------------------------------------------------------------- labels: hide the ones behind objects or on top of a more important one
// Call tick(performance.now()) every frame; the real work runs ~3 times a second.
// Priority: speech bubbles and pop-ups first, then names (nearest first), zone writings last.
export function labelTidy(scene, camera) {
  if (!document.getElementById("mm-tidy-css")) {
    const st = document.createElement("style"); st.id = "mm-tidy-css";
    st.textContent = ".lbl,.zone,.say,.sign,.zzz{transition:opacity .25s}.tidy-hid{opacity:0!important}";
    document.head.appendChild(st);
  }
  const ray = new THREE.Raycaster(), cam = new THREE.Vector3(), dir = new THREE.Vector3();
  const occ = [], labs = [];
  let next = 0, occAt = 0;
  const pri = el => /\b(say|pop)\b/.test(el.className) ? 0 : /\bzone\b/.test(el.className) ? 3 : /\bzzz\b/.test(el.className) ? 4 : 1;
  return function tick(now) {
    if (now < next) return; next = now + 320;
    if (now > occAt) {  // solid, visible meshes can hide a label (glass, wireframes and see-through things cannot)
      occAt = now + 2500; occ.length = 0;
      scene.traverseVisible(o => { const m = o.material; if (o.isMesh && m && !Array.isArray(m) && !m.wireframe && !(m.transparent && m.opacity < .7) && !o.userData.noOcclude) occ.push(o); });
    }
    labs.length = 0; scene.traverseVisible(o => { if (o.isCSS2DObject) labs.push(o); });
    camera.getWorldPosition(cam);
    const items = labs.map(o => { const p = o.getWorldPosition(new THREE.Vector3()); return { o, p, d: p.distanceTo(cam), k: pri(o.element) }; })
      .sort((a, b) => a.k - b.k || a.d - b.d);
    const placed = [];
    for (const it of items) {
      const el = it.o.element; let hide = false;
      if (it.k > 0) {
        dir.copy(it.p).sub(cam); const len = dir.length(); ray.set(cam, dir.divideScalar(len)); ray.far = Math.max(.1, len - .35);
        hide = ray.intersectObjects(occ, false).length > 0;
      }
      const r = el.getBoundingClientRect();
      if (!hide && r.width && !/\bpop\b/.test(el.className) && placed.some(q => r.left < q.right - 3 && r.right > q.left + 3 && r.top < q.bottom - 2 && r.bottom > q.top + 2)) hide = true;
      if (!hide && r.width) placed.push(r);
      el.classList.toggle("tidy-hid", hide);
    }
  };
}

// ---------------------------------------------------------------- camera framing: on a phone held upright look from higher up and closer
export function frameCamera(camera, controls, base) {
  const portrait = camera.aspect < .9;
  camera.fov = portrait ? 56 : 42; camera.updateProjectionMatrix();
  const dir = portrait ? new THREE.Vector3(0, 17, 12.5) : base.clone().multiplyScalar(Math.max(1, .95 / camera.aspect));
  camera.position.copy(controls.target).add(dir);
}

// ---------------------------------------------------------------- rotating warning light (approvals / posts waiting for the owner)
export function siren(color = 0xffa020) {
  const group = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CylinderGeometry(.17, .19, .09, 20), new THREE.MeshStandardMaterial({ color: 0x23262e, metalness: .7, roughness: .35 }));
  base.position.y = .045; group.add(base);
  const domeMat = new THREE.MeshStandardMaterial({ color: 0x4a4f5c, transparent: true, opacity: .9, roughness: .2 });
  const dome = new THREE.Mesh(new THREE.SphereGeometry(.16, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2), domeMat); dome.position.y = .09; dome.scale.y = 1.35; group.add(dome);
  const spin = new THREE.Group(); spin.position.y = .17; spin.visible = false; group.add(spin);
  const beamMat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: .12, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide });
  for (const s of [-1, 1]) { const b = new THREE.Mesh(new THREE.ConeGeometry(.28, 1.3, 20, 1, true), beamMat); b.rotation.z = s * Math.PI / 2; b.position.x = s * .65; spin.add(b); }
  const light = new THREE.PointLight(color, 0, 5); light.position.y = .25; group.add(light);
  let was = null;
  return { group, dome, tick(dt, on) {
    if (on !== was) { was = on; spin.visible = on; domeMat.color.setHex(on ? color : 0x4a4f5c); domeMat.emissive.setHex(on ? color : 0); domeMat.emissiveIntensity = on ? .8 : 0; light.intensity = on ? 2.5 : 0; }
    if (on) spin.rotation.y += dt * 5;
  } };
}

// ---------------------------------------------------------------- confetti burst (a product goes on sale); tick(dt) returns false when done
const CONF_MATS = [0xf5b83d, 0x3ecfb2, 0xff5d73, 0xb48cff, 0xffffff].map(c => new THREE.MeshBasicMaterial({ color: c, side: THREE.DoubleSide }));
const CONF_GEO = new THREE.PlaneGeometry(.09, .055);
export function confetti(parent, at, n = 70) {
  const g = new THREE.Group(); g.position.copy(at); parent.add(g);
  for (let i = 0; i < n; i++) {
    const m = new THREE.Mesh(CONF_GEO, CONF_MATS[i % CONF_MATS.length]);
    m.userData.v = new THREE.Vector3((Math.random() - .5) * 3.2, 2.5 + Math.random() * 3.5, (Math.random() - .5) * 3.2);
    m.userData.r = new THREE.Vector3(Math.random() * 9, Math.random() * 9, Math.random() * 4); g.add(m);
  }
  let life = 2.6;
  return { tick(dt) {
    life -= dt;
    for (const m of g.children) {
      const v = m.userData.v; v.y -= 7 * dt; v.multiplyScalar(1 - dt * .9); m.position.addScaledVector(v, dt);
      if (m.position.y < -at.y + .02) { m.position.y = -at.y + .02; v.set(0, 0, 0); } else { m.rotation.x += m.userData.r.x * dt; m.rotation.y += m.userData.r.y * dt; }
    }
    if (life > 0) return true;
    parent.remove(g); return false;
  } };
}

// ---------------------------------------------------------------- "waiting for you" props, one per room: tick(dt, t, count)
const _std = (color, o = {}) => new THREE.MeshStandardMaterial({ color, roughness: .6, ...o });
const _box = (mat, sx, sy, sz, x = 0, y = 0, z = 0) => { const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), mat); m.position.set(x, y, z); m.castShadow = true; return m; };

// product room: a desk with the stack of papers to approve and a rubber stamp that keeps stamping while something waits
export function approvalStamp() {
  const group = new THREE.Group(), wood = _std(0x6b4a33), dark = _std(0x22262e, { metalness: .6, roughness: .35 });
  group.add(_box(wood, .9, .06, .6, 0, .78, 0));
  for (const [x, z] of [[-.4, -.25], [.4, -.25], [-.4, .25], [.4, .25]]) group.add(_box(dark, .05, .75, .05, x, .375, z));
  group.add(_box(dark, .44, .03, .34, -.18, .825, 0));  // in-tray
  const paper = _std(0xf3f1ea, { roughness: .9 }), sheets = new THREE.Group(); sheets.position.set(-.18, .84, 0); group.add(sheets);
  const pad = _box(dark, .2, .03, .14, .26, .825, .16); group.add(pad);
  group.add(_box(_std(0xb3202e, { roughness: .9 }), .17, .005, .11, .26, .842, .16));
  const stamp = new THREE.Group(); group.add(stamp);
  const red = _std(0xc62828, { roughness: .45 });
  stamp.add(_box(red, .17, .05, .12, 0, .025, 0));
  const stem = new THREE.Mesh(new THREE.CylinderGeometry(.025, .03, .15, 12), wood); stem.position.y = .12; stamp.add(stem);
  const knobMat = _std(0x4a2f1f, { emissive: 0x000000 }), knob = new THREE.Mesh(new THREE.SphereGeometry(.06, 16, 10), knobMat); knob.position.y = .22; stamp.add(knob);
  const REST = new THREE.Vector3(.26, .845, -.12);
  stamp.position.copy(REST);
  let shown = -1;
  return { group, tick(dt, t, n) {
    const k = Math.min(n, 12);
    if (k !== shown) {
      shown = k; sheets.clear();
      for (let i = 0; i < k; i++) { const s = _box(paper, .36, .012, .26, (Math.sin(i * 7) * .01), i * .014, (Math.cos(i * 5) * .01)); s.rotation.y = Math.sin(i * 3) * .08; sheets.add(s); }
      knobMat.emissive.setHex(k ? 0xff3b30 : 0); knobMat.emissiveIntensity = k ? .7 : 0;
    }
    if (!k) { stamp.position.copy(REST); return; }
    const top = .84 + k * .014 + .02, c = (t % 2.4) / 2.4;  // move over the stack, press, come back, rest
    let s = 0, dip = 0;
    if (c < .25) s = c / .25; else if (c < .4) { s = 1; dip = Math.sin((c - .25) / .15 * Math.PI); } else if (c < .65) s = 1 - (c - .4) / .25;
    const e = s * s * (3 - 2 * s);
    stamp.position.set(REST.x + (-.18 - REST.x) * e, s === 1 ? top + .06 * (1 - dip) : REST.y + (top + .06 - REST.y) * e + Math.sin(e * Math.PI) * .12, REST.z * (1 - e));
  } };
}

// sales room: a mailbox; the red flag goes up and letters stick out while something waits
export function mailbox(color = 0xb48cff) {
  const group = new THREE.Group(), steel = _std(0x6f7888, { metalness: .9, roughness: .3 }), body = _std(color, { metalness: .5, roughness: .35 });
  const post = new THREE.Mesh(new THREE.CylinderGeometry(.04, .05, .95, 12), steel); post.position.y = .475; group.add(post);
  group.add(_box(body, .36, .26, .62, 0, 1.06, 0));
  const roof = new THREE.Mesh(new THREE.CylinderGeometry(.18, .18, .62, 24, 1, false, 0, Math.PI), body); roof.rotation.set(Math.PI / 2, 0, Math.PI / 2); roof.position.y = 1.19; roof.castShadow = true; group.add(roof);
  const door = _box(_std(0x1d1626, { roughness: .4 }), .3, .3, .01, 0, 1.12, .313); group.add(door);
  const flag = new THREE.Group(); flag.position.set(.19, 1.02, -.12); group.add(flag);
  const flagRed = _std(0xe53935, { roughness: .4 });
  flag.add(_box(flagRed, .025, .52, .035, 0, .26, 0), _box(flagRed, .025, .16, .22, 0, .44, .1));
  const paper = _std(0xf3f1ea, { roughness: .9 }), letters = new THREE.Group(); letters.position.set(0, 1.12, .33); group.add(letters);
  let shown = -1, up = 0;
  return { group, tick(dt, t, n) {
    const k = Math.min(n, 5);
    if (k !== shown) { shown = k; letters.clear(); for (let i = 0; i < k; i++) { const l = _box(paper, .24, .16, .008, (i - (k - 1) / 2) * .03, (i % 2) * .02, i * .012); l.rotation.set(-.35, 0, (i - 2) * .06); letters.add(l); } }
    up += ((k ? 1 : 0) - up) * Math.min(1, dt * 4);
    flag.rotation.x = (1 - up) * Math.PI / 2 + (k ? Math.sin(t * 6) * .06 : 0);
  } };
}

// social room: a big notification bell with a red badge that rings while posts wait
export function notifyBell(color = 0xff5fa2) {
  const group = new THREE.Group(), steel = _std(0x6f7888, { metalness: .9, roughness: .3 });
  const post = new THREE.Mesh(new THREE.CylinderGeometry(.04, .05, .9, 12), steel); post.position.y = .45; group.add(post);
  const hang = new THREE.Group(); hang.position.y = 1.55; group.add(hang);  // the bell swings from here
  const prof = [[0, 0], [.3, 0], [.29, .04], [.22, .1], [.19, .22], [.17, .36], [.13, .46], [.06, .5], [0, .5]].map(([x, y]) => new THREE.Vector2(x, y));
  const bellMat = _std(color, { metalness: .4, roughness: .3, emissive: color, emissiveIntensity: .12 });
  const bell = new THREE.Mesh(new THREE.LatheGeometry(prof, 32), bellMat); bell.position.y = -.58; bell.castShadow = true; hang.add(bell);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(.045, .015, 8, 16), steel); ring.position.y = -.04; hang.add(ring);
  const clap = new THREE.Mesh(new THREE.SphereGeometry(.06, 14, 10), bellMat); clap.position.y = -.62; hang.add(clap);
  const c = document.createElement("canvas"); c.width = c.height = 128; const g = c.getContext("2d");
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  const badge = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, toneMapped: false, depthWrite: false })); badge.scale.setScalar(.3); badge.position.set(.24, 1.62, .1); group.add(badge);
  let shown = -1;
  return { group, tick(dt, t, n) {
    if (n !== shown) {
      shown = n; badge.visible = n > 0; g.clearRect(0, 0, 128, 128);
      g.fillStyle = "#ff2d55"; g.beginPath(); g.arc(64, 64, 58, 0, 7); g.fill(); g.lineWidth = 8; g.strokeStyle = "#fff"; g.stroke();
      g.fillStyle = "#fff"; g.font = "800 66px sans-serif"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(n > 9 ? "9+" : String(n), 64, 68); tex.needsUpdate = true;
    }
    const c2 = t % 2.6, ringing = n > 0 && c2 < .9;
    hang.rotation.z = ringing ? Math.sin(c2 * 22) * .32 * (1 - c2 / .9) : hang.rotation.z * (1 - Math.min(1, dt * 6));
    clap.position.x = -hang.rotation.z * .15;
    if (n > 0) badge.scale.setScalar(.3 + Math.max(0, Math.sin(t * 4)) * .04);
  } };
}

// ---------------------------------------------------------------- the first real sale: a party in every room, once
// world.first_sale comes from the real ledger (never from the demo). Each room celebrates it once per browser, and only
// if the sale is recent (an old first sale is never celebrated late). ?festa in the address shows a preview.
// true things the agents can chat about: the real numbers of the site, approvals waiting, the weather outside
export function lifeFacts({ kpi = null, pending = 0, weather = null } = {}) {
  const f = [], n = v => Number(v || 0).toLocaleString("it-IT");
  if (kpi) {
    if (kpi.visits_total) f.push(`Il sito è a ${n(kpi.visits_total)} visite in tutto`);
    if (kpi.clicks_total) f.push(`${n(kpi.clicks_total)} clic sul tasto d'acquisto finora`);
    f.push(kpi.revenue_eur > 0 ? `Guadagni reali registrati: ${eur(kpi.revenue_eur)}` : "Prima la prova, poi i soldi veri");
  }
  if (pending) f.push(pending === 1 ? "C'è una cosa che aspetta l'ok del capo" : `${pending} cose aspettano l'ok del capo`);
  if (weather) {
    const how = { clear: "c'è il sole", clouds: "è nuvoloso", fog: "c'è nebbia", rain: "piove", storm: "c'è un temporale", snow: "nevica" }[weather.kind] || weather.label;
    f.push(`A ${weather.city} ${how}, ${weather.temp}°`);
  }
  return f;
}

// ---------------------------------------------------------------- life in the room when the agents are free
// Free agents (not working, not paused) get up now and then: coffee, sofa, books, the plant, the cat, a chat in twos
// in the middle of the room, with a speech bubble. Bubbles say only true things (facts()) or plain small talk, never
// invented numbers. Office hours: in the evening they take the lift home, in the morning they come back; when a cycle
// starts at night, whoever works arrives from the lift. Purely visual: it costs nothing.
// stations(): [{ws, g, body, state, paused}], label(text, cls) → CSS2DObject. Preview: ?vita=giro|chiacchiere|sera|notte|mattina
export function officeLife({ stations, label, cat = null, facts = () => [], lift = [12.4, .5], open = [8, 19.5], left = -8.4, right = 9.6,
  chatSpots = [[[-2.1, 2.7], [-1.05, 3.05]], [[1.2, 2.4], [2.2, 2.75]]] }) {
  const V = (x, z) => new THREE.Vector3(x, 0, z);
  const R = [V(right, 1.6), V(right, -5.6)], L = [V(left, 1.6), V(left, -5.6)];  // around the ends of the desk arc
  const SPOTS = [
    { at: V(11.25, -7.05), look: V(11.25, -8.3), via: R, doing: "coffee", say: ["Caffè?", "Un espresso e riparto", "Il caffè qui è buono"] },
    { at: V(10.1, -7.1), look: V(10.1, -8.3), via: R, doing: "coffee", say: ["Un bicchiere d'acqua", "Bisogna bere, eh"] },
    { at: V(11.4, -4.2), look: V(13.8, -4.6), via: [R[0]], doing: "read", say: ["Cinque minuti di pausa", "Leggo due notizie"] },
    { at: V(6.5, -7.25), look: V(6.5, -8.4), via: R, doing: "read", say: ["Cerco un'idea qui dentro", "Questo lo rileggo"] },
    { at: V(-8.3, -6.9), look: V(-9, -7.7), via: L, doing: "pet", say: ["La pianta cresce con le visite del sito", "Un po' d'acqua alla pianta"] },
    { cat: true, via: [L[0]], doing: "pet", say: ["Ciao Micio!", "Chi è il gatto più bravo?", "Una carezza e torno al lavoro"] },
    { at: V(chatSpots[0][0][0] - .4, chatSpots[0][0][1] + .2), look: V(0, -1), via: [], doing: "stretch", say: ["Sgranchisco le gambe", "Respiro un attimo", "Due passi e riparto"] },
  ];
  const CHAT = chatSpots.map(([a, b]) => [V(a[0], a[1]), V(b[0], b[1])]);  // open floor in front of the desks, free in every room
  const bubs = new Map(), timeline = [];
  const bubble = (st) => {
    if (!bubs.has(st)) { const b = label("", "say life"); b.position.set(0, 2.95, -.25); b.visible = false; st.body.add(b); bubs.set(st, b); }
    return bubs.get(st);
  };
  const say = (st, text, secs = 4) => { const b = bubble(st); b.element.textContent = text; b.visible = true; timeline.push({ t: secs, fn: () => { b.visible = false; } }); };
  const later = (secs, fn) => timeline.push({ t: secs, fn });
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const local = (st, v) => { st.g.updateMatrixWorld(); return st.g.worldToLocal(v.clone()); };
  const all = () => stations().filter(st => st && st.ws);
  const free = () => all().filter(st => !st.paused && st.state !== "working" && !st.ws.walking && !st.ws.away && !st.busyLife);
  const out = () => all().filter(st => st.busyLife).length;
  const qs = new URLSearchParams(location.search).get("vita");
  const hourNow = () => { const d = new Date(); return d.getHours() + d.getMinutes() / 60; };
  const isOpen = () => qs === "sera" || qs === "notte" ? false : qs === "mattina" || qs === "giro" || qs === "chiacchiere" ? true : hourNow() >= open[0] && hourNow() < open[1];
  let next = 4 + Math.random() * 4, door = 0, started = false;

  function walkTo(st, spot, wait, onWait) {
    let at = spot.at, look = spot.look;
    if (spot.cat) {
      if (!cat || cat.busy) return false;
      const p = new THREE.Vector3(); cat.group.getWorldPosition(p);
      if (p.y > .25) return false;  // up on a shelf: not reachable
      at = V(Math.max(p.x + .75, -8.9), p.z + .2); look = V(p.x, p.z);
    }
    st.busyLife = true;
    const ok = st.ws.visit(local(st, at), local(st, look), wait, false, {
      via: spot.via.map(v => local(st, v)), doing: spot.doing, onWait,
      onDone: () => { st.busyLife = false; },
    });
    if (!ok) st.busyLife = false;
    return ok;
  }
  function solo(st, spot = pick(SPOTS)) {
    const wait = 6 + Math.random() * 5;
    return walkTo(st, spot, wait, () => say(st, pick(spot.say), Math.min(wait, 4.5)));
  }
  function chat(a, b) {
    const [pa, pb] = pick(CHAT), lines = conversation(), wait = 3.6 * lines.length + 2;
    let here = 0;
    const start = () => { if (++here < 2) return; lines.forEach(([who, text], i) => later(i * 3.6, () => say(who ? b : a, text, 3.4))); };
    const okA = walkTo(a, { at: pa, look: pb, via: [], doing: "talk", say: [] }, wait, start);
    const okB = okA && walkTo(b, { at: pb, look: pa, via: [], doing: "talk", say: [] }, wait, start);
    return okA && okB;
  }
  // a short exchange: a true fact if there is one, then a plain reply
  function conversation() {
    const f = facts().filter(Boolean);
    const open1 = f.length ? pick(f) : pick(["Come va oggi?", "Pausa di cinque minuti?", "Hai visto il gatto?"]);
    const reply = pick(["Bene, continuiamo così", "Ottimo, ci penso io", "Prima il backtest, poi vediamo", "Vero! Lo dico al CEO", "Ne parliamo al prossimo ciclo"]);
    return [[0, open1], [1, reply], [0, pick(["Caffè dopo?", "Torno alla scrivania", "Perfetto"])]];
  }
  function hours(dt) {
    const opened = isOpen();
    // whoever must work comes back right away, office hours or not
    for (const st of all()) if (st.ws.away && st.state === "working") st.ws.arrive([local(st, V(lift[0], lift[1])), local(st, R[0])]);
    if ((door -= dt) > 0) return;
    if (!opened) {
      const st = all().find(s => !s.ws.away && !s.ws.walking && !s.busyLife && s.state !== "working");
      if (st && st.ws.leave([local(st, R[0]), local(st, V(lift[0], lift[1]))])) door = 2.5;
    } else {
      const st = all().find(s => s.ws.away);
      if (st && st.ws.arrive([local(st, V(lift[0], lift[1])), local(st, R[0])])) door = 2.5;
    }
  }
  return {
    get busy() { return out() > 0 || timeline.length > 0 || all().some(st => st.ws.walking); },
    get open() { return isOpen(); },
    tick(dt) {
      for (let i = timeline.length - 1; i >= 0; i--) if ((timeline[i].t -= dt) <= 0) { const e = timeline.splice(i, 1)[0]; e.fn(); }
      if (!started) {  // first frame: at night the room opens already empty; previews start at once
        started = true;
        if (!isOpen() && qs !== "sera") for (const st of all()) if (st.state !== "working") st.ws.setAway(true);
        if (qs === "mattina") for (const st of all()) st.ws.setAway(true);
        if (qs === "giro") { const f = free(); [2, 3, 5].forEach((k, i) => f[i] && solo(f[i], SPOTS[k])); next = 999; }
        if (qs === "chiacchiere") { const f = free(); if (f.length > 1) chat(f[1], f[2] || f[0]); const g = free(); g[0] && solo(g[0], SPOTS[0]); next = 999; }
      }
      hours(dt);
      if (!isOpen() || (next -= dt) > 0) return;
      next = 7 + Math.random() * 9;
      const f = free(); if (!f.length || out() >= 3) return;
      if (f.length > 1 && Math.random() < .3) { const a = pick(f); chat(a, pick(f.filter(x => x !== a))); }
      else solo(pick(f));
    },
  };
}

export function firstSaleParty({ scene, office, key, desks = () => [], cats = () => [], extra = () => {} }) {
  const bursts = [], storeKey = "mm-festa-" + key;
  let left = 0, next = 0, done = false;
  const preview = /[?&]festa\b/.test(location.search);
  const get = () => { try { return localStorage.getItem(storeKey) || ""; } catch (e) { return ""; } };
  const put = v => { try { localStorage.setItem(storeKey, v); } catch (e) {} };
  const start = fs => {
    left = 16; next = 0;
    const amount = fs.amount_eur != null ? Number(fs.amount_eur).toLocaleString("it-IT", { style: "currency", currency: "EUR" }) : "";
    office.celebrate("PRIMO GUADAGNO! 🎉", fs.preview ? "anteprima della festa" : [amount, fs.name].filter(Boolean).join(" · "), 60);
    sound.cash(); setTimeout(() => sound.fanfare(), 500);
    for (const d of desks()) d.cheer(9 + Math.random() * 3);
    for (const c of cats()) c.party();
    extra(fs);
  };
  return {
    get active() { return left > 0 || bursts.length > 0; },
    check(world, demo = false) {
      if (done) return;
      if (preview) { done = true; start({ preview: true }); return; }
      const fs = !demo && world && world.first_sale;
      if (!fs || !fs.id) return;
      done = true;
      if (get() === String(fs.id)) return;
      put(String(fs.id));
      if (Date.now() - Date.parse(fs.date || "") < 7 * 864e5) start(fs);
    },
    tick(dt) {
      if (left > 0) {
        left -= dt;
        if ((next -= dt) <= 0) { next = .35; for (let k = 0; k < 2; k++) bursts.push(confetti(scene, new THREE.Vector3(rnd(-9, 9), rnd(3.5, 5), rnd(-4, 7)), 110)); }
      }
      for (let i = bursts.length - 1; i >= 0; i--) if (!bursts[i].tick(dt)) bursts.splice(i, 1);
    },
  };
}

// ---------------------------------------------------------------- glass elevator: the three rooms are three floors of one building
const FLOORS = [["office.html", "Sala trading", "📈", "#0f3b36"], ["sales.html", "Sala rendite", "🏦", "#2a1f3d"]];
export function elevator(scene, { floor = 1, accent = 0x3ecfb2, at = [12.4, .5] } = {}) {
  const group = new THREE.Group(); group.position.set(at[0], 0, at[1]); scene.add(group);
  const M = (geo, m, x, y, z, p = group) => { const o = new THREE.Mesh(geo, m); o.position.set(x, y, z); p.add(o); return o; };
  const steel = new THREE.MeshStandardMaterial({ color: 0xc8ccd4, metalness: .9, roughness: .25 });
  M(new THREE.CylinderGeometry(1.15, 1.15, 5.2, 32, 1, true), new THREE.MeshPhysicalMaterial({ color: 0xbfe9ff, transparent: true, opacity: .2, roughness: .05, clearcoat: 1, depthWrite: false, side: THREE.DoubleSide }), 0, 2.6, 0);
  for (const y of [.05, 5.15]) M(new THREE.CylinderGeometry(1.2, 1.2, .1, 32), steel, 0, y, 0);
  for (let k = 0; k < 6; k++) { const a = k / 6 * Math.PI * 2; M(new THREE.CylinderGeometry(.04, .04, 5.2, 8), steel, Math.cos(a) * 1.15, 2.6, Math.sin(a) * 1.15); }
  const cab = new THREE.Group(); group.add(cab);
  const dark = new THREE.MeshStandardMaterial({ color: 0x23262e, metalness: .6, roughness: .35 });
  M(new THREE.CylinderGeometry(1, 1, .08, 32), dark, 0, .1, 0, cab); M(new THREE.CylinderGeometry(1, 1, .08, 32), dark, 0, 2.8, 0, cab);
  M(new THREE.CircleGeometry(.6, 32), new THREE.MeshBasicMaterial({ color: 0xfff1d0, toneMapped: false }), 0, 2.75, 0, cab).rotation.x = Math.PI / 2;
  const light = new THREE.PointLight(0xfff1d0, 3, 4); light.position.set(0, 2.2, 0); cab.add(light);
  const dc = document.createElement("canvas"); dc.width = 240; dc.height = 120; const dtex = new THREE.CanvasTexture(dc); dtex.colorSpace = THREE.SRGBColorSpace;
  const drawD = (txt) => { const g = dc.getContext("2d"); g.fillStyle = "#06140c"; g.fillRect(0, 0, 240, 120); g.fillStyle = "#7dffb0"; g.font = "700 70px sans-serif"; g.textAlign = "center"; g.fillText(txt, 120, 88); dtex.needsUpdate = true; };
  drawD(String(floor));
  const disp = M(new THREE.PlaneGeometry(.8, .4), new THREE.MeshBasicMaterial({ map: dtex, toneMapped: false }), -1.25, 3.4, 0); disp.rotation.y = -Math.PI / 2;
  const ring = M(new THREE.TorusGeometry(1.17, .025, 8, 64), new THREE.MeshBasicMaterial({ color: accent, toneMapped: false }), 0, .12, 0); ring.rotation.x = Math.PI / 2;
  let move = null;
  const fade = document.createElement("div");
  Object.assign(fade.style, { position: "fixed", inset: "0", background: "#05070d", opacity: "0", pointerEvents: "none", transition: "opacity .7s",
    zIndex: "50", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff", font: "700 28px system-ui,sans-serif" });
  document.body.appendChild(fade);
  const api = {
    group,
    get busy() { return !!move; },
    go(href) {
      const to = FLOORS.findIndex(f => f[0] === href) + 1;
      if (!to || to === floor || move) { if (to === floor) return; location.href = href; return; }
      drawD((to > floor ? "▲ " : "▼ ") + to);
      move = { t: 0, dir: to > floor ? 1 : -1, href };
      fade.textContent = `${FLOORS[to - 1][2]} Piano ${to} · ${FLOORS[to - 1][1]}`;
      setTimeout(() => { fade.style.opacity = "1"; }, 450);
      setTimeout(() => { location.href = href; }, 1300);
    },
    menu() {
      let m = document.getElementById("liftMenu");
      if (!m) {
        m = document.createElement("div"); m.id = "liftMenu";
        Object.assign(m.style, { position: "fixed", left: "50%", top: "50%", transform: "translate(-50%,-50%)", zIndex: "40", background: "rgba(15,23,42,.96)",
          border: "1px solid #334155", borderRadius: "16px", padding: "16px", color: "#fff", font: "600 16px system-ui,sans-serif", minWidth: "260px", boxShadow: "0 20px 60px rgba(0,0,0,.5)" });
        document.body.appendChild(m);
      }
      m.innerHTML = `<div style="font:700 13px system-ui;color:#94a3b8;letter-spacing:.08em;margin-bottom:10px">🛗 PALAZZO CRYPTO MACHINE</div>` +
        FLOORS.map((f, i) => i + 1).reverse().map(n => { const f = FLOORS[n - 1], here = n === floor;
          return `<button data-href="${f[0]}" style="display:block;width:100%;text-align:left;margin:6px 0;padding:10px 12px;border-radius:10px;border:${here ? "2px solid #3ecfb2" : "1px solid #334155"};background:${f[3]};color:#fff;font:600 16px system-ui;cursor:pointer">${f[2]} ${n} · ${f[1]}${here ? " · sei qui" : ""}</button>`; }).join("") +
        `<button data-close style="margin-top:6px;background:none;border:0;color:#94a3b8;font:500 14px system-ui;cursor:pointer">Chiudi</button>`;
      m.hidden = false;
      m.onclick = e => { const b = e.target.closest("button"); if (!b) return; m.hidden = true; if (b.dataset.href) api.go(b.dataset.href); };
    },
    tick(dt) {
      if (!move) return;
      move.t += dt; cab.position.y = Math.min(1, move.t / 1.2) * 2.4 * -move.dir;
      light.intensity = 3 + Math.sin(move.t * 20) * .5;
    },
  };
  // the room links in the top bar take the elevator too
  for (const f of FLOORS) document.querySelectorAll(`a[href="${f[0]}"]`).forEach(a => a.addEventListener("click", e => { e.preventDefault(); api.go(f[0]); }));
  return api;
}

// ---------------------------------------------------------------- real weather of the owner's city (server: /api/weather, cached)
// ?meteo=rain|storm|snow|fog|clouds|clear in the address shows a preview.
export function weatherWatch(office) {
  const q = new URLSearchParams(location.search).get("meteo");
  if (q) { office.weather({ kind: q, city: "anteprima", temp: 12 }); return; }
  const load = async () => {
    try {
      const tok = (() => { try { return localStorage.getItem("mm-token"); } catch (e) { return null; } })();
      const r = await fetch("api/weather", { cache: "no-store", headers: tok ? { "X-MM-Token": tok } : {} });
      if (r.ok) { const w = await r.json(); if (w && w.kind) office.weather(w); }
    } catch (e) { /* no weather: the room stays as it is */ }
  };
  load(); setInterval(() => { if (!document.hidden) load(); }, 30 * 60 * 1000);
}


// ---------------------------------------------------------------- crypto price ticker (LED board, real public prices)
// A scrolling LED board high on the back wall: BTC, ETH, SOL… in euro from /api/prices (Coinbase spot, cached 60 s),
// green when the price went up since the last reading, red when it went down. No data → "prezzi non disponibili".
export function priceTicker(parent, { x = 0, y = 4.25, z = -5.9, width = 7.5, demo = false } = {}) {
  const W = 2048, H = 96, c = document.createElement("canvas"); c.width = W; c.height = H;
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.wrapS = THREE.RepeatWrapping;
  const g = new THREE.Group(); g.position.set(x, y, z); parent.add(g);
  const frame = new THREE.Mesh(new THREE.BoxGeometry(width + .2, .52, .08), new THREE.MeshStandardMaterial({ color: 0x0b0d12, roughness: .5, metalness: .6 }));
  frame.position.z = -.05; g.add(frame);
  const board = new THREE.Mesh(new THREE.PlaneGeometry(width, .4), new THREE.MeshBasicMaterial({ map: tex, toneMapped: false }));
  g.add(board);
  let items = [];
  const fmt = v => v >= 1000 ? v.toLocaleString("it-IT", { maximumFractionDigits: 0 }) : v.toLocaleString("it-IT", { maximumFractionDigits: v >= 1 ? 2 : 5 });
  function draw() {
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#020403"; ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "rgba(60,255,140,.05)"; for (let i = 0; i < W; i += 8) ctx.fillRect(i, 0, 1, H);  // LED grid
    ctx.font = "700 54px monospace"; ctx.textBaseline = "middle";
    let px = 30;
    const list = items.length ? items : [{ asset: "PREZZI", eur: null, move: 0 }];
    for (let k = 0; k < 6 && px < W; k++) for (const it of list) {
      const col = it.move > 0 ? "#3cff8c" : it.move < 0 ? "#ff5a5a" : "#ffd25a";
      ctx.fillStyle = col; ctx.shadowColor = col; ctx.shadowBlur = 14;
      const txt = it.eur == null ? "prezzi non disponibili" : `${it.asset} ${fmt(it.eur)} € ${it.move > 0 ? "▲" : it.move < 0 ? "▼" : "•"}`;
      ctx.fillText(txt, px, H / 2 + 2); px += ctx.measureText(txt).width + 70;
    }
    ctx.shadowBlur = 0; tex.needsUpdate = true;
  }
  draw();
  board.userData.onClick = () => {};  // decorative: the numbers are real but this is not trading advice
  const load = async () => {
    if (demo) { items = [{ asset: "BTC", eur: 58123, move: 1 }, { asset: "ETH", eur: 2310.5, move: -1 }, { asset: "SOL", eur: 141.2, move: 1 }]; draw(); return; }
    try {
      const tok = (() => { try { return localStorage.getItem("mm-token"); } catch (e) { return null; } })();
      const r = await fetch("api/prices", { cache: "no-store", headers: tok ? { "X-MM-Token": tok } : {} });
      if (r.ok) { const j = await r.json(); if (Array.isArray(j.prices) && j.prices.length) { items = j.prices; draw(); } }
    } catch (e) { /* no prices: the board says so */ }
  };
  load(); setInterval(() => { if (!document.hidden) load(); }, 60 * 1000);
  return { group: g, tick() { tex.offset.x = (performance.now() / 1000 * .03) % 1; } };
}
