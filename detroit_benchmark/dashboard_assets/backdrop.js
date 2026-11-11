/* Background layer: a slow node network whose movement fits the current Character.
 *
 * Connor is an exact grid swept by a scan line, Kara soft clusters of protective pairs,
 * Markus a scattered crowd gathering toward a centre, and no Character a calm drift.
 * Styles crossfade on the `characterchange` event that app.js fires on document.
 * Self-contained: it only reads the colour tokens and listens for events.
 */
'use strict';
(() => {
  const host = document.getElementById('backdropNetwork');
  if (!host) return;
  const canvas = document.createElement('canvas');
  canvas.className = 'backdrop-canvas';
  host.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const MAX_NODES = 150, FADE_MS = 1800, TAU = Math.PI * 2;
  const VISIBILITY = 3; // the network reads clearly behind the Story and Flowchart, not as a faint texture

  let width = 0, height = 0, dpr = 1;
  let colors = null;
  let current = null, previous = null, fadeStart = 0;
  let frame = 0, lastTime = 0, clock = 0;

  /* ── Colours: the Character's shades for structure and highlights, from the live tokens ── */
  function readColors() {
    const style = getComputedStyle(document.body);
    const token = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
    // Lines and dots carry the Character's colour, so the network reads against the light theme.
    return {node: token('--shade-4', '#1567b6'), line: token('--shade-2', '#52a9f2'), accent: token('--accent', '#2087e0')};
  }

  /* ── Small helpers ── */
  const rand = (min, max) => min + Math.random() * (max - min);
  // Deterministic randomness, so a reduced-motion static frame looks the same every time.
  function seeded(seed) {
    let s = seed >>> 0;
    return () => {s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296;};
  }
  function linkByDistance(nodes, maxDist, draw) {
    const max2 = maxDist * maxDist;
    for (let i = 0; i < nodes.length; i++) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j++) {
        const b = nodes[j], dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy;
        if (d2 < max2) draw(a, b, 1 - Math.sqrt(d2) / maxDist);
      }
    }
  }
  /* Lines are batched into a few opacity buckets: one stroke call per bucket. */
  function strokeBuckets(alpha, color, segments, lineWidth = 0.7) {
    ctx.lineWidth = lineWidth * 1.4;
    ctx.strokeStyle = color;
    for (let bucket = 0; bucket < segments.length; bucket++) {
      const list = segments[bucket];
      if (!list.length) continue;
      ctx.globalAlpha = Math.min(1, alpha * (bucket + 1) / segments.length);
      ctx.beginPath();
      for (let k = 0; k < list.length; k += 4) {ctx.moveTo(list[k], list[k + 1]); ctx.lineTo(list[k + 2], list[k + 3]);}
      ctx.stroke();
    }
  }
  function proximitySegments(nodes, maxDist, buckets = 3) {
    const segments = Array.from({length: buckets}, () => []);
    linkByDistance(nodes, maxDist, (a, b, strength) => {
      const bucket = Math.min(buckets - 1, Math.floor(strength * buckets));
      segments[bucket].push(a.x, a.y, b.x, b.y);
    });
    return segments;
  }
  function dots(alpha, color, nodes, radius, filter = null) {
    ctx.fillStyle = color;
    ctx.globalAlpha = Math.min(1, alpha);
    ctx.beginPath();
    for (const n of nodes) {
      if (filter && !filter(n)) continue;
      const r = n.r || radius;
      ctx.moveTo(n.x + r, n.y);
      ctx.arc(n.x, n.y, r, 0, TAU);
    }
    ctx.fill();
  }
  function glow(alpha, color, x, y, r) {
    ctx.globalAlpha = Math.min(1, alpha);
    ctx.fillStyle = color;
    ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill();
  }

  /* ── Connor: an exact grid; a scan line sweeps across it in straight lines ── */
  function connorStyle(w, h) {
    const spacing = Math.max(64, Math.sqrt(w * h / 130));
    const cols = Math.ceil(w / spacing) + 1, rows = Math.ceil(h / spacing) + 1;
    const ox = (w - (cols - 1) * spacing) / 2, oy = (h - (rows - 1) * spacing) / 2;
    const nodes = [];
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) nodes.push({x: ox + c * spacing, y: oy + r * spacing, col: c, row: r, heat: 0});
    const SWEEP = 9;  // seconds per pass
    return {
      update() {},
      draw(alpha, t) {
        // Alternate horizontal and vertical passes, like a methodical scan of a room.
        const pass = Math.floor(t / SWEEP), progress = (t % SWEEP) / SWEEP;
        const vertical = pass % 2 === 1;
        const ease = progress < .5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
        const scan = vertical ? ease * (w + 80) - 40 : ease * (h + 80) - 40;
        const segments = [[], []];
        for (const n of nodes) {
          const distance = Math.abs((vertical ? n.x : n.y) - scan);
          n.heat = Math.max(0, 1 - distance / (spacing * 1.4));
          if (n.col < cols - 1) segments[0].push(n.x, n.y, n.x + spacing, n.y);
          if (n.row < rows - 1) segments[0].push(n.x, n.y, n.x, n.y + spacing);
        }
        strokeBuckets(alpha * .32, colors.line, segments, .6);
        // Grid cells under the scan line light up along their edges.
        const lit = [[], [], []];
        for (const n of nodes) {
          if (n.heat <= 0) continue;
          const bucket = Math.min(2, Math.floor(n.heat * 3));
          if (vertical && n.row < rows - 1) lit[bucket].push(n.x, n.y, n.x, n.y + spacing);
          if (!vertical && n.col < cols - 1) lit[bucket].push(n.x, n.y, n.x + spacing, n.y);
        }
        strokeBuckets(alpha * .35, colors.accent, lit, .8);
        dots(alpha * .45, colors.node, nodes, 1.4);
        dots(alpha * .85, colors.accent, nodes, 2, n => n.heat > .45);
        // The scan line itself: a thin accent rule with a soft trailing band.
        ctx.globalAlpha = Math.min(1, alpha * .4);
        ctx.strokeStyle = colors.accent;
        ctx.lineWidth = 1;
        ctx.beginPath();
        if (vertical) {ctx.moveTo(scan, 0); ctx.lineTo(scan, h);} else {ctx.moveTo(0, scan); ctx.lineTo(w, scan);}
        ctx.stroke();
        const band = vertical ? ctx.createLinearGradient(scan - 90, 0, scan, 0) : ctx.createLinearGradient(0, scan - 90, 0, scan);
        band.addColorStop(0, 'rgba(0,0,0,0)');
        band.addColorStop(1, colors.accent);
        ctx.globalAlpha = Math.min(1, alpha * .07);
        ctx.fillStyle = band;
        if (vertical) ctx.fillRect(scan - 90, 0, 90, h); else ctx.fillRect(0, scan - 90, w, 90);
      },
    };
  }

  /* ── Kara: soft clusters of pairs, each pair orbiting close together ── */
  function karaStyle(w, h) {
    const random = seeded(7);
    const clusterCount = Math.max(5, Math.min(9, Math.round(w * h / 200000)));
    const clusters = [], nodes = [], pairs = [];
    for (let i = 0; i < clusterCount; i++) {
      const cluster = {
        ax: random() * w, ay: random() * h, rx: w * (.04 + random() * .06), ry: h * (.04 + random() * .06),
        sx: .02 + random() * .03, sy: .02 + random() * .03, phase: random() * TAU, x: 0, y: 0,
      };
      clusters.push(cluster);
      const pairCount = 3 + Math.floor(random() * 4);
      for (let p = 0; p < pairCount && nodes.length < MAX_NODES - 2; p++) {
        const pair = {
          cluster, orbit: 34 + random() * 70, angle: random() * TAU, speed: (.05 + random() * .08) * (random() < .5 ? -1 : 1),
          spin: random() * TAU, spinSpeed: .25 + random() * .35, gap: 7 + random() * 6, x: 0, y: 0,
        };
        pair.a = {x: 0, y: 0, r: 1.9};
        pair.b = {x: 0, y: 0, r: 1.3};
        pairs.push(pair); nodes.push(pair.a, pair.b);
      }
    }
    return {
      update(t) {
        for (const c of clusters) {
          c.x = c.ax + Math.sin(t * c.sx + c.phase) * c.rx;
          c.y = c.ay + Math.cos(t * c.sy + c.phase * 1.3) * c.ry;
        }
        for (const p of pairs) {
          const angle = p.angle + t * p.speed, breathe = 1 + .08 * Math.sin(t * .3 + p.spin);
          p.x = p.cluster.x + Math.cos(angle) * p.orbit * breathe;
          p.y = p.cluster.y + Math.sin(angle) * p.orbit * .8 * breathe;
          // The smaller node stays close and circles the larger one: a guardian and a child.
          const spin = p.spin + t * p.spinSpeed;
          p.a.x = p.x; p.a.y = p.y;
          p.b.x = p.x + Math.cos(spin) * p.gap; p.b.y = p.y + Math.sin(spin) * p.gap;
        }
      },
      draw(alpha) {
        // A faint halo marks each cluster's shelter.
        for (const c of clusters) glow(alpha * .035, colors.accent, c.x, c.y, 120);
        const anchors = pairs.map(p => p.a);
        strokeBuckets(alpha * .3, colors.line, proximitySegments(anchors, 150));
        const bonds = [[]];
        for (const p of pairs) bonds[0].push(p.a.x, p.a.y, p.b.x, p.b.y);
        strokeBuckets(alpha * .55, colors.accent, bonds, .9);
        for (const p of pairs) glow(alpha * .07, colors.accent, p.x, p.y, p.gap + 6);
        dots(alpha * .55, colors.node, anchors, 1.9);
        dots(alpha * .8, colors.accent, pairs.map(p => p.b), 1.3);
      },
    };
  }

  /* ── Markus: scattered nodes slowly walk in and gather, like a crowd forming ── */
  function markusStyle(w, h) {
    const random = seeded(31);
    const cx = w * .6, cy = h * .52, crowd = Math.min(w, h) * .2;
    const nodes = [];
    const spawn = (n, anywhere) => {
      if (anywhere) {n.x = random() * w; n.y = random() * h;}
      else {
        // Newcomers walk in from just beyond an edge of the screen.
        const edge = Math.floor(random() * 4), along = random();
        n.x = edge === 0 ? -10 : edge === 1 ? w + 10 : along * w;
        n.y = edge === 2 ? -10 : edge === 3 ? h + 10 : along * h;
      }
      const spot = Math.sqrt(random()) * crowd, spotAngle = random() * TAU;
      n.tx = cx + Math.cos(spotAngle) * spot * 1.3; n.ty = cy + Math.sin(spotAngle) * spot;
      n.speed = 3 + random() * 5;  // px per second: a slow walk
      n.life = 0; n.linger = 20 + random() * 30; n.arrived = 0;
    };
    const count = Math.min(MAX_NODES - 10, Math.round(w * h / 11000));
    for (let i = 0; i < count; i++) {const n = {}; spawn(n, true); n.life = random() * 8; nodes.push(n);}
    return {
      update(t, dt) {
        for (const n of nodes) {
          n.life += dt;
          const dx = n.tx - n.x, dy = n.ty - n.y, d = Math.hypot(dx, dy);
          if (d > 1) {
            const step = Math.min(d, n.speed * dt * (0.4 + Math.min(1, d / 200)));
            n.x += dx / d * step + Math.sin(t * .4 + n.tx) * .05;
            n.y += dy / d * step + Math.cos(t * .4 + n.ty) * .05;
          } else n.arrived += dt;
          // Once settled for a while a node leaves quietly and another walks in from afar.
          if (n.arrived > n.linger) spawn(n, false);
          n.fade = Math.min(1, n.life / 4) * Math.min(1, (n.linger - n.arrived) / 4);
          n.heat = Math.max(0, 1 - Math.hypot(n.x - cx, n.y - cy) / (crowd * 1.6));
        }
      },
      draw(alpha) {
        glow(alpha * .04, colors.accent, cx, cy, crowd * 1.4);
        strokeBuckets(alpha * .32, colors.line, proximitySegments(nodes, 95));
        ctx.fillStyle = colors.node;
        for (const n of nodes) {
          ctx.globalAlpha = Math.min(1, alpha * .55 * n.fade);
          ctx.beginPath(); ctx.arc(n.x, n.y, 1.6, 0, TAU); ctx.fill();
        }
        ctx.fillStyle = colors.accent;
        for (const n of nodes) {
          if (n.heat < .3) continue;
          ctx.globalAlpha = Math.min(1, alpha * .8 * n.heat * n.fade);
          ctx.beginPath(); ctx.arc(n.x, n.y, 1.9, 0, TAU); ctx.fill();
        }
      },
    };
  }

  /* ── No Character: a calm neutral drift ── */
  function neutralStyle(w, h) {
    const random = seeded(3);
    const count = Math.min(MAX_NODES - 40, Math.round(w * h / 14000));
    const nodes = Array.from({length: count}, () => ({
      x: random() * w, y: random() * h, vx: (random() - .5) * 7, vy: (random() - .5) * 7, r: 1.1 + random() * .8,
    }));
    return {
      update(t, dt) {
        for (const n of nodes) {
          n.x += n.vx * dt; n.y += n.vy * dt;
          if (n.x < -20) n.x = w + 20; else if (n.x > w + 20) n.x = -20;
          if (n.y < -20) n.y = h + 20; else if (n.y > h + 20) n.y = -20;
        }
      },
      draw(alpha) {
        strokeBuckets(alpha * .3, colors.line, proximitySegments(nodes, 120));
        dots(alpha * .5, colors.node, nodes, 1.4);
      },
    };
  }

  const STYLES = {connor: connorStyle, kara: karaStyle, markus: markusStyle, none: neutralStyle};
  const characterKey = () => (STYLES[document.body.dataset.character] ? document.body.dataset.character : 'none');
  function makeStyle(key) {
    const style = STYLES[key](width, height);
    style.key = key;
    style.colors = readColors();
    return style;
  }

  /* ── Canvas and loop ── */
  function resize() {
    dpr = Math.min(2, window.devicePixelRatio || 1);
    width = window.innerWidth; height = window.innerHeight;
    canvas.width = Math.round(width * dpr); canvas.height = Math.round(height * dpr);
    canvas.style.width = width + 'px'; canvas.style.height = height + 'px';
    current = makeStyle(current?.key || characterKey());
    previous = null;
    if (reducedMotion.matches) drawStatic();
  }
  function render(t, dt) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const mix = previous ? Math.min(1, (performance.now() - fadeStart) / FADE_MS) : 1;
    if (previous && mix >= 1) previous = null;
    // Each style keeps the colours it was born with, so a fade also crossfades the accent.
    if (previous) {colors = previous.colors; previous.update(t, dt); previous.draw((1 - mix) * VISIBILITY, t);}
    colors = current.colors; current.update(t, dt); current.draw((previous ? mix : 1) * VISIBILITY, t);
    ctx.globalAlpha = 1;
  }
  /* Reduced motion: one settled, still frame. */
  function drawStatic() {
    previous = null;
    for (let i = 0; i < 40; i++) current.update(4 + i * .25, .25);
    render(14, 0);
  }
  function tick(now) {
    frame = 0;
    const dt = Math.min(.1, lastTime ? (now - lastTime) / 1000 : 0);
    lastTime = now; clock += dt;
    render(clock, dt);
    schedule();
  }
  function schedule() {
    if (frame || document.hidden || reducedMotion.matches) return;
    frame = requestAnimationFrame(tick);
  }
  function stop() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0; lastTime = 0;
  }
  function setCharacter(key) {
    if (current?.key === key) {current.colors = readColors(); return;}
    if (reducedMotion.matches || !current) {current = makeStyle(key); drawStatic(); return;}
    previous = current; fadeStart = performance.now();
    current = makeStyle(key);
  }

  document.addEventListener('characterchange', event => setCharacter(STYLES[event.detail?.character] ? event.detail.character : 'none'));
  document.addEventListener('visibilitychange', () => (document.hidden ? stop() : schedule()));
  reducedMotion.addEventListener?.('change', () => {stop(); if (reducedMotion.matches) drawStatic(); else schedule();});
  let resizeTimer;
  window.addEventListener('resize', () => {clearTimeout(resizeTimer); resizeTimer = setTimeout(resize, 150);});

  /* The network lives only behind the Story and the Flowchart: the layer is clipped to
   * whichever of the two is showing, and hidden when neither is. */
  const views = ['storyView', 'viewport'].map(id => document.getElementById(id)).filter(Boolean);
  function clipToView() {
    const view = views.find(el => el.offsetWidth && el.offsetHeight);
    if (!view) {host.style.clipPath = 'inset(50%)'; return;}
    const r = view.getBoundingClientRect();
    host.style.clipPath = `inset(${Math.max(0, r.top)}px ${Math.max(0, window.innerWidth - r.right)}px ${Math.max(0, window.innerHeight - r.bottom)}px ${Math.max(0, r.left)}px)`;
  }
  if (window.ResizeObserver) {const watch = new ResizeObserver(clipToView); views.forEach(el => watch.observe(el));}
  window.addEventListener('resize', clipToView);
  window.addEventListener('scroll', clipToView, {passive: true, capture: true});

  resize();
  clipToView();
  schedule();
})();

/* Scene art: the current scene's concept art, if installed locally, under the network.
 *
 * Listens for `scenechange` ({chapter, heading, headings, art}) from the Story and Flowchart.
 * An `art` key named by the Story wins, then a heading listed for that chapter in the
 * manifest, then the chapter's main image,
 * else no art. Images crossfade between two layers once loaded.
 */
(() => {
  const host = document.getElementById('backdropArt'), backdrop = document.getElementById('backdrop');
  if (!host || !backdrop) return;
  const SETTLE_MS = 180;  // hovering across nodes or scrolling quickly should not flicker
  const layers = [0, 1].map(() => {
    const layer = document.createElement('div');
    layer.className = 'backdrop-art-layer';
    host.appendChild(layer);
    return layer;
  });
  const byChapter = new Map();
  const byKey = new Map();
  let wanted = {chapter: null, headings: [], art: null}, shownKey = null, front = 0, timer = 0, request = 0;

  function sceneFor({chapter, headings, art}) {
    if (art && byKey.has(art)) return byKey.get(art);
    const entry = byChapter.get(String(chapter ?? ''));
    if (!entry) return null;
    for (const heading of headings) if (entry.byHeading.has(heading)) return entry.byHeading.get(heading);
    return entry.main;
  }
  function show(scene) {
    const key = scene?.key || null;
    if (key === shownKey) return;
    shownKey = key;
    const ticket = ++request;
    if (!scene) {
      layers.forEach(layer => layer.classList.remove('is-shown'));
      backdrop.classList.remove('has-art');
      return;
    }
    const image = new Image();
    image.onload = () => {
      if (ticket !== request) return;
      const next = layers[1 - front];
      next.style.backgroundImage = `url("${scene.url}")`;
      next.dataset.key = scene.key;
      next.classList.add('is-shown');
      layers[front].classList.remove('is-shown');
      front = 1 - front;
      backdrop.classList.add('has-art');
    };
    image.onerror = () => { if (ticket === request) shownKey = null; };
    image.src = scene.url;
  }
  const update = () => { clearTimeout(timer); timer = setTimeout(() => show(sceneFor(wanted)), SETTLE_MS); };

  document.addEventListener('scenechange', event => {
    const detail = event.detail || {};
    const headings = detail.headings?.length ? detail.headings : detail.heading ? [detail.heading] : [];
    wanted = {chapter: detail.chapter ?? null, headings, art: detail.art ?? null};
    update();
  });

  fetch('/api/art/manifest')
    .then(response => (response.ok ? response.json() : {scenes: []}))
    .then(manifest => {
      for (const scene of manifest.scenes || []) {
        byKey.set(scene.key, scene);
        const chapter = String(scene.chapter);
        if (!byChapter.has(chapter)) byChapter.set(chapter, {main: null, byHeading: new Map()});
        const entry = byChapter.get(chapter);
        if (scene.chapter_main && !entry.main) entry.main = scene;
        for (const heading of scene.headings || []) if (!entry.byHeading.has(heading)) entry.byHeading.set(heading, scene);
      }
      update();
    })
    .catch(() => {});  // no art: the network alone is the background
})();
