/* Fruit Counter: a first count on the picture, which the person corrects with the mouse. */
dqs.addView('fruit', { code: 'FC', title: 'Fruit Counter', sub: 'Count & correct' }, (el, hooks) => {
  const { esc, call, on, plural, shortPath, confirm } = dqs;
  const CLICK_MOVE = 4;       // moving less than this many pixels is a click, more is a drag
  const KEEP_LOADED = 6;      // pictures kept ready, for going back and forth without waiting
  const S = {
    pictures: [], current: null, image: null, width: 0, height: 0, zoom: 1, ox: 0, oy: 0, fitted: true,
    history: [], measuring: false, sensitivity: 70, out: '', busy: '', problem: '', saving: false, message: null,
    modes: [], mode: 'pieces',
    lessons: { on: false, share: true, pending: 0 },   // sending checked counts to the team's Drive, to tune on     // what counts as one: a piece, a grape berry or a whole bunch...
  };
  const loaded = new Map();   // path -> {image, width, height}

  el.innerHTML = `<div class="tool">
    <div class="panel-list fc-list">
      <div class="panel-head"><div class="panel-title">Fruit Counter</div><div class="muted small">A first count for you to correct</div></div>
      <div class="dz dz-small" data-a="add">Drop pictures or folders</div>
      <div class="list" id="fc-list"></div>
      <div class="fc-total">
        <div class="fc-total-row"><div class="muted">Total, all pictures</div><div class="fc-total-number" id="fc-total">0</div></div>
        <div class="fc-share" id="fc-share"></div>
        <button class="btn primary fc-save" data-a="save" id="fc-save">Save results</button>
        <div class="fc-caption" id="fc-caption"></div>
      </div>
    </div>
    <div class="fc-main">
      <div class="fc-top">
        <div class="fc-count" id="fc-count">—</div>
        <div class="fc-stats" id="fc-stats"></div>
        <div class="spacer"></div>
        <div style="display:flex;gap:6px"><button class="btn" data-a="undo">Undo <span class="muted" style="font-size:11px">Ctrl+Z</span></button><button class="btn" data-a="fit">Fit</button></div>
      </div>
      <div class="fc-canvas" id="fc-area"><canvas></canvas><div class="fc-label" id="fc-label" hidden></div><div class="fc-empty" id="fc-empty">Add pictures to count the fruit on them.</div></div>
      <div class="fc-controls">
        <div class="muted small">Count</div>
        <select class="field fc-mode" id="fc-mode" title="What counts as one"></select>
        <div class="fc-divider"></div>
        <button class="btn" data-a="measure" id="fc-measure">Measure one</button>
        <div class="muted small">Size <span class="mono" style="color:var(--text)" id="fc-size">—</span></div>
        <div class="fc-divider"></div>
        <div class="fc-slider"><div class="muted small">Finds fewer</div><input type="range" min="0" max="100" value="70" id="fc-sens" style="flex:1"><div class="muted small">more</div></div>
        <button class="btn" data-a="again">Count again</button>
      </div>
      <div class="fc-hints" id="fc-hints"></div>
    </div>
  </div>`;
  const $ = id => el.querySelector(id);
  const area = $('#fc-area'), canvas = area.querySelector('canvas'), ctx = canvas.getContext('2d');
  const HINTS = '<div><span>Left click</span> adds</div><div><span>Right click</span> removes</div><div><span>Wheel</span> zooms</div><div><span>Drag</span> moves around</div>';

  // ---------------------------------------------------------------- drawing
  let measureLine = null, drawPending = false;

  function draw() {
    if (drawPending) return;
    drawPending = true;
    requestAnimationFrame(() => { drawPending = false; paint(); });
  }

  function paint() {
    const scale = window.devicePixelRatio || 1;
    const w = area.clientWidth, h = area.clientHeight;
    if (canvas.width !== Math.round(w * scale) || canvas.height !== Math.round(h * scale)) {
      canvas.width = Math.round(w * scale);
      canvas.height = Math.round(h * scale);
    }
    ctx.setTransform(scale, 0, 0, scale, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const p = S.current;
    if (!S.image || !p) return;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(S.image, S.ox, S.oy, S.width * S.zoom, S.height * S.zoom);
    const r = Math.max(3, Math.min(12, (p.diameter || 30) * S.zoom * 0.14));
    ctx.fillStyle = '#ff4b4b';
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.5;
    for (const [x, y] of p.points) {
      const sx = x * S.zoom + S.ox, sy = y * S.zoom + S.oy;
      if (sx < -r || sy < -r || sx > w + r || sy > h + r) continue;
      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }
    if (measureLine) {
      ctx.strokeStyle = '#ffd54a';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(measureLine[0], measureLine[1]);
      ctx.lineTo(measureLine[2], measureLine[3]);
      ctx.stroke();
    }
  }

  function drawList() {
    const list = $('#fc-list');
    const top = list.scrollTop;
    list.innerHTML = S.pictures.map((p, i) => `<div class="list-row${p === S.current ? ' on' : ''}" data-pick="${i}" title="${esc(p.path)}">
      ${p.thumb ? `<img class="thumb" width="40" height="30" src="${p.thumb}" alt="">` : '<div class="thumb" style="width:40px;height:30px"></div>'}
      <div class="small ellipsis" style="flex:1">${esc(p.name)}</div>
      <div class="mono small" ${p.done ? '' : 'style="color:var(--dim)"'}>${p.done ? p.points.length : '—'}</div>
      <div class="x" data-a="remove" data-i="${i}">×</div></div>`).join('');
    list.scrollTop = top;
    $('#fc-total').textContent = S.pictures.reduce((sum, p) => sum + (p.done ? p.points.length : 0), 0);
  }

  const modeOf = picture => S.modes.find(m => m.id === (picture ? picture.mode : S.mode)) || { one: 'piece', many: 'pieces' };

  function drawModes() {
    const groups = [];
    S.modes.forEach(m => {
      const last = groups[groups.length - 1];
      if (last && last.product === m.product) last.modes.push(m); else groups.push({ product: m.product, modes: [m] });
    });
    $('#fc-mode').innerHTML = groups.map(g => g.modes.length === 1
      ? `<option value="${g.modes[0].id}">${esc(g.product)}</option>`
      : `<optgroup label="${esc(g.product)}">${g.modes.map(m => `<option value="${m.id}">${esc(g.product)}: ${esc(m.many)}</option>`).join('')}</optgroup>`).join('');
    $('#fc-mode').value = S.current ? S.current.mode : S.mode;
  }

  function drawInfo() {
    const p = S.current;
    const unit = modeOf(p);
    $('#fc-count').textContent = p && p.done ? p.points.length : '—';
    $('#fc-stats').innerHTML = p && p.done ? `<div><span>${esc(unit.many)}</span></div><div>found <span>${p.detected}</span></div><div>you added <span>${p.added}</span></div><div>removed <span>${p.removed}</span></div>` : '';
    $('#fc-size').textContent = p && p.diameter ? `${Math.round(p.diameter)} px` : '—';
    $('#fc-hints').innerHTML = S.measuring
      ? `<div>Drag across <span>ONE</span> ${esc(unit.one)}, from edge to edge${unit.measure ? `, to count the ${esc(unit.many)}` : ''}.</div>`
      : HINTS;
    $('#fc-measure').textContent = `Measure one ${unit.one}`;
    if (S.modes.length) $('#fc-mode').value = p ? p.mode : S.mode;
    $('#fc-measure').classList.toggle('on', S.measuring);
    const label = $('#fc-label');
    label.hidden = !S.busy;
    label.textContent = S.busy;
    const empty = $('#fc-empty');
    empty.hidden = !!S.image && !S.problem;
    empty.textContent = S.problem || (S.pictures.length ? '' : 'Add pictures to count the fruit on them.');
    area.style.cursor = S.image ? 'crosshair' : 'default';
  }

  function drawSave() {
    const m = S.message, l = S.lessons;
    $('#fc-share').innerHTML = l.on
      ? `<label class="fc-share-row" title="The pictures and your corrections go to the team's Google Drive, to make the counter better. Only tick it when every mark is right.">
          <input type="checkbox" id="fc-share-box" ${l.share ? 'checked' : ''}><span>Every mark checked: share to improve counting</span></label>
         ${l.pending ? `<div class="fc-share-note">${plural(l.pending, 'picture')} waiting to be sent</div>` : ''}`
      : '<span class="link" data-a="team">Help improve counting: enter the team key</span>';
    $('#fc-save').disabled = S.saving || !S.pictures.some(p => p.done);
    $('#fc-save').textContent = S.saving ? 'Saving…' : 'Save results';
    $('#fc-caption').innerHTML = `Fruit counts.xlsx + marked pictures<br>to <span title="${esc(S.out)}">${esc(shortPath(S.out))}</span> · <span class="link" data-a="change">Change</span> · <span class="link" data-a="open">Open</span>
      ${m ? `<div class="banner ${m.kind} selectable" style="margin-top:8px;text-align:left">${esc(m.text)}</div>` : ''}`;
  }

  function refresh() { drawList(); drawInfo(); drawSave(); draw(); }

  // ---------------------------------------------------------------- view
  function fitZoom() {
    return Math.min((area.clientWidth - 4) / S.width, (area.clientHeight - 4) / S.height, 4);
  }

  function fit() {
    if (!S.image) return;
    S.zoom = Math.max(0.01, fitZoom());
    S.ox = (area.clientWidth - S.width * S.zoom) / 2;
    S.oy = (area.clientHeight - S.height * S.zoom) / 2;
    S.fitted = true;
    draw();
  }

  new ResizeObserver(() => { if (S.fitted) fit(); else draw(); }).observe(area);

  // ---------------------------------------------------------------- pictures
  async function add(paths) {
    if (!paths.length) return;
    const files = await call('fruit', 'add', paths, S.pictures.map(p => p.path));
    const fresh = files.map(f => ({ ...f, points: [], detected: 0, added: 0, removed: 0, diameter: null, done: false, mode: S.mode }));
    S.pictures.push(...fresh);
    S.message = null;
    refresh();
    if (!S.current && fresh.length) select(fresh[0]);
  }

  function showImage(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error('The picture could not be shown.'));
      image.src = url;
    });
  }

  async function select(picture) {
    if (picture === S.current) return;
    S.current = picture;
    S.history = [];
    S.measuring = false;
    S.problem = '';
    S.busy = 'Opening…';
    S.image = null;
    refresh();
    let entry = loaded.get(picture.path);
    if (!entry) {
      const result = await call('fruit', 'load', picture.path);
      if (S.current !== picture) return;
      if (result.error) { S.busy = ''; S.problem = result.error; refresh(); return; }
      try {
        entry = { image: await showImage(result.url), width: result.width, height: result.height };
      } catch (e) {
        if (S.current === picture) { S.busy = ''; S.problem = e.message; refresh(); }
        return;
      }
      loaded.set(picture.path, entry);
      if (loaded.size > KEEP_LOADED) loaded.delete(loaded.keys().next().value);
      if (S.current !== picture) return;
    }
    S.image = entry.image;
    S.width = entry.width;
    S.height = entry.height;
    S.busy = '';
    fit();
    if (picture.done) refresh();
    else await detect(picture);
  }

  async function detect(picture) {
    S.busy = 'Counting…';
    refresh();
    // big piles (hundreds of grapes) take a while: show it's still going
    const started = Date.now();
    const ticking = setInterval(() => {
      const seconds = Math.round((Date.now() - started) / 1000);
      if (picture === S.current && S.busy.startsWith('Counting') && seconds >= 3) { S.busy = `Counting… ${seconds} s`; drawInfo(); }
    }, 1000);
    const asked = picture.mode;
    let result;
    try {
      result = await call('fruit', 'detect', picture.path, picture.diameter, S.sensitivity, picture.example || null, asked);
    } finally {
      clearInterval(ticking);
    }
    if (picture.mode !== asked) return detect(picture);      // the mode was changed while counting
    if (result.error) {
      S.message = { kind: 'bad', text: result.error };
    } else if (result.measure) {
      // groups (bunches, punnets...) are counted from one measured: ask for it straight away
      Object.assign(picture, { points: [], detected: 0, added: 0, removed: 0, done: false });
      if (picture === S.current) S.measuring = true;
    } else {
      Object.assign(picture, { points: result.points, diameter: result.diameter, detected: result.points.length, added: 0, removed: 0, done: true,
        found: result.points.slice(), sensitivity: S.sensitivity });      // what it found, kept for the lessons
      if (picture === S.current) S.history = [];
    }
    if (picture === S.current) S.busy = '';
    refresh();
  }

  function remove(i) {
    const [gone] = S.pictures.splice(i, 1);
    loaded.delete(gone.path);
    if (gone === S.current) {
      S.current = null;
      S.image = null;
      S.problem = '';
      S.history = [];
      if (S.pictures.length) select(S.pictures[Math.min(i, S.pictures.length - 1)]);
    }
    refresh();
  }

  // ---------------------------------------------------------------- mouse
  let press = null;
  const where = e => {
    const box = area.getBoundingClientRect();
    return [e.clientX - box.left, e.clientY - box.top];
  };
  const toPicture = (x, y) => [(x - S.ox) / S.zoom, (y - S.oy) / S.zoom];

  area.addEventListener('wheel', e => {
    e.preventDefault();
    if (!S.image) return;
    const factor = e.deltaY < 0 ? 1.25 : 0.8;
    const zoom = Math.min(12, Math.max(fitZoom() * 0.5, S.zoom * factor));
    const [x, y] = where(e);
    const [px, py] = toPicture(x, y);
    S.ox = x - px * zoom;                  // zoom around the mouse
    S.oy = y - py * zoom;
    S.zoom = zoom;
    S.fitted = false;
    draw();
  }, { passive: false });

  area.addEventListener('pointerdown', e => {
    if (e.button !== 0 || !S.image) return;
    area.setPointerCapture(e.pointerId);
    const [x, y] = where(e);
    press = { x, y, ox: S.ox, oy: S.oy };
  });

  area.addEventListener('pointermove', e => {
    if (!press) return;
    const [x, y] = where(e);
    if (S.measuring) {
      measureLine = [press.x, press.y, x, y];
      draw();
    } else if (Math.abs(x - press.x) + Math.abs(y - press.y) > CLICK_MOVE) {
      S.ox = press.ox + x - press.x;
      S.oy = press.oy + y - press.y;
      S.fitted = false;
      draw();
    }
  });

  area.addEventListener('pointerup', e => {
    if (!press) return;
    const start = press;
    press = null;
    const [x, y] = where(e);
    const moved = Math.abs(x - start.x) + Math.abs(y - start.y);
    const picture = S.current;
    if (!picture) return;
    if (S.measuring) {
      measureLine = null;
      draw();
      if (moved > CLICK_MOVE && !S.busy) {
        S.measuring = false;
        // the measured fruit is the example: its size and its colour (kept for Count again)
        picture.example = [...toPicture(start.x, start.y), ...toPicture(x, y)];
        picture.diameter = Math.hypot(x - start.x, y - start.y) / S.zoom;
        detect(picture);
      }
      return;
    }
    if (moved <= CLICK_MOVE && !S.busy && picture.done) {
      const [px, py] = toPicture(x, y);
      if (px >= 0 && py >= 0 && px < S.width && py < S.height) {
        const point = [px, py];
        S.history.push(['add', point]);
        picture.points.push(point);
        picture.added += 1;
        refresh();
      }
    }
  });

  area.addEventListener('contextmenu', e => {
    e.preventDefault();
    const picture = S.current;
    if (!picture || !picture.points.length || S.busy) return;
    const [x, y] = where(e);
    const [px, py] = toPicture(x, y);
    let best = -1, bestDistance = Infinity;
    picture.points.forEach(([mx, my], i) => {
      const distance = (mx - px) ** 2 + (my - py) ** 2;
      if (distance < bestDistance) { best = i; bestDistance = distance; }
    });
    const reach = Math.max((picture.diameter || 40) * 0.6, 12 / S.zoom);
    if (bestDistance <= reach ** 2) {
      S.history.push(['remove', picture.points.splice(best, 1)[0]]);
      picture.removed += 1;
      refresh();
    }
  });

  function undo() {
    const picture = S.current;
    if (!picture || !S.history.length) return;
    const [action, point] = S.history.pop();
    if (action === 'add') {
      picture.points.splice(picture.points.indexOf(point), 1);
      picture.added -= 1;
    } else {
      picture.points.push(point);
      picture.removed -= 1;
    }
    refresh();
  }

  // ---------------------------------------------------------------- buttons
  async function countAgain() {
    const picture = S.current;
    if (!picture || S.busy || !S.image) return;
    if ((picture.added || picture.removed) &&
        !await confirm('Count again?', 'Counting again replaces your corrections on this picture.', 'Count again')) return;
    detect(picture);
  }

  on('fruit.thumb', t => {
    const picture = S.pictures.find(p => p.path === t.path);
    if (picture) { picture.thumb = t.thumb; drawList(); }
  });
  on('fruit.saved', d => {
    S.saving = false;
    setTimeout(async () => { S.lessons = await call('fruit', 'lessons'); drawSave(); }, 1500);
    S.message = { kind: 'good', text: `Saved ${d.workbook} and ${plural(d.n, 'marked picture')}.` };
    drawSave();
  });
  on('fruit.error', message => { S.saving = false; S.message = { kind: 'bad', text: message }; drawSave(); });

  $('#fc-sens').addEventListener('input', e => { S.sensitivity = +e.target.value; });
  el.addEventListener('change', e => {
    if (e.target.id === 'fc-share-box') { S.lessons.share = e.target.checked; call('fruit', 'share', e.target.checked); }
  });

  // a different count mode counts the picture again: a measured berry says nothing about a bunch
  $('#fc-mode').addEventListener('change', async e => {
    const mode = e.target.value, picture = S.current;
    S.mode = mode;
    if (!picture || picture.mode === mode) return;
    if (S.busy && !S.busy.startsWith('Counting')) { e.target.value = picture.mode; return; }
    if (((picture.added || picture.removed) &&
        !await confirm('Count again?', 'Counting something else replaces your corrections on this picture.', 'Count again'))) {
      e.target.value = picture.mode;
      return;
    }
    const counting = S.busy.startsWith('Counting');
    Object.assign(picture, { mode, example: null, diameter: null });
    S.measuring = false;
    if (counting) return;                    // the count under way starts again with the new mode
    if (S.image) detect(picture); else refresh();
  });

  el.addEventListener('click', async e => {
    const target = e.target.closest('[data-a]');
    if (!target) {
      const row = e.target.closest('[data-pick]');
      if (row) select(S.pictures[+row.dataset.pick]);
      return;
    }
    const act = target.dataset.a;
    if (act === 'add') add(await call('fruit', 'choose'));
    else if (act === 'remove') remove(+target.dataset.i);
    else if (act === 'undo') undo();
    else if (act === 'fit') fit();
    else if (act === 'again') countAgain();
    else if (act === 'measure') { if (S.image) { S.measuring = !S.measuring; drawInfo(); } }
    else if (act === 'change') {
      const folder = await call('fruit', 'choose_out', S.out);
      if (folder) { S.out = folder; drawSave(); }
    } else if (act === 'open') {
      const problem = await call('fruit', 'open_out', S.out);
      if (problem) { S.message = { kind: 'bad', text: problem }; drawSave(); }
    } else if (act === 'save') {
      const counted = S.pictures.filter(p => p.done);
      if (!counted.length || S.saving) return;
      S.saving = true;
      S.message = null;
      drawSave();
      call('fruit', 'save', counted.map(({ path, points, detected, added, removed, diameter, mode, found, example, sensitivity }) =>
        ({ path, points, detected, added, removed, diameter, mode, found, example: example || null, sensitivity })), S.out, S.lessons.on && S.lessons.share);
    } else if (act === 'team') {
      const lessons = await dqs.askKey('Help improve counting', "With the team key, the counts you check and save are shared with the team's Google Drive, to make the counter better. Ask the maintainer for it.",
        'Team key', 'Save key', key => call('fruit', 'team_key', key));
      if (lessons) { S.lessons = lessons; drawSave(); }
    }
  });

  hooks.onDrop = add;
  hooks.onShow = () => { if (S.fitted) fit(); else draw(); };
  hooks.onKey = e => {
    if (e.ctrlKey && e.key.toLowerCase() === 'z') { e.preventDefault(); undo(); }
    else if (e.key === 'Escape' && S.measuring) { S.measuring = false; measureLine = null; drawInfo(); draw(); }
  };

  refresh();
  call('fruit', 'state').then(state => {
    S.out = state.out;
    S.modes = state.modes;
    S.lessons = state.lessons;
    S.mode = state.mode;
    S.pictures.forEach(p => { if (!p.done) p.mode = S.mode; });
    drawModes();
    drawSave();
    drawInfo();
  });
});
