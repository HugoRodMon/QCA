/* Image Editor: list of pictures, live preview, and the same edits for all of them. */
dqs.addView('image', { code: 'IE', title: 'Image Editor', sub: 'Batch edit pictures' }, (el, hooks) => {
  const { esc, call, on, plural, shortPath } = dqs;
  const DEFAULTS = { angle: 0, flip_h: false, flip_v: false, ratio: 'Keep', anchor: 'Center', resolution: 'Keep', custom_w: '', custom_h: '', fit: null, brightness: 100, contrast: 100, saturation: 100, sharpness: 100 };
  const S = {
    files: [], selected: null, original: false, recipe: { ...DEFAULTS }, format: 'Same as original', quality: 92, suffix: '_edited', out: '',
    options: null, saving: false, progress: { i: 0, n: 0, name: '' }, message: null, sizes: '',
  };

  el.innerHTML = `<div class="tool">
    <div class="panel-list ie-list">
      <div class="panel-head"><div class="panel-title">Image Editor</div><div class="muted small">Originals are never changed</div></div>
      <div class="dz dz-small" data-a="add">Drop pictures or folders</div>
      <div class="list" id="ie-list"></div>
      <div class="panel-footer" id="ie-footer"></div>
    </div>
    <div class="ie-center">
      <div class="ie-top">
        <div class="segment"><div class="on" data-a="edited">Edited</div><div data-a="original">Original</div></div>
        <div class="muted small mono" id="ie-sizes" style="white-space:nowrap"></div>
      </div>
      <div class="ie-preview" id="ie-preview"><div class="dim" id="ie-empty">Add pictures to see the preview here.</div><img alt="" hidden></div>
      <div class="ie-bottom" id="ie-bottom"></div>
    </div>
    <div class="inspector" id="ie-inspector"></div>
  </div>`;
  const listEl = el.querySelector('#ie-list'), footerEl = el.querySelector('#ie-footer'), bottomEl = el.querySelector('#ie-bottom');
  const sizesEl = el.querySelector('#ie-sizes'), previewEl = el.querySelector('#ie-preview'), imgEl = previewEl.querySelector('img'), emptyEl = el.querySelector('#ie-empty');
  const inspector = el.querySelector('#ie-inspector');

  // ---------------------------------------------------------------- inspector (built once, so sliders keep working while being dragged)
  const option = (value, on) => `<option value="${esc(value)}"${on ? ' selected' : ''}>${esc(value)}</option>`;
  const select = (id, values, value) => `<select class="field prop-value" data-input="${id}">${values.map(v => option(v, v === value)).join('')}</select>`;
  const slider = (id, label) => `<div class="slider"><div class="slider-top"><div>${label}</div><div class="mono" data-value="${id}">100%</div></div><input type="range" min="0" max="200" value="100" data-input="${id}"></div>`;

  function buildInspector() {
    const o = S.options;
    inspector.innerHTML = `
      <div class="section"><div class="section-title">Rotate</div>
        <div class="row"><button class="btn" data-a="turn" data-d="-90">⟲ 90°</button><button class="btn" data-a="turn" data-d="90">⟳ 90°</button><button class="btn" data-a="turn" data-d="180">180°</button>
          <div class="angle"><input value="0" data-input="angle" spellcheck="false"><span>°</span></div></div>
        <div class="row"><button class="btn" data-a="flip" data-k="flip_h">Mirror</button><button class="btn" data-a="flip" data-k="flip_v">Upside down</button></div></div>
      <div class="section"><div class="section-title">Cut to a shape</div>
        <div class="chips" id="ie-ratios"></div>
        <div class="prop"><div class="muted">Keep</div>${select('anchor', o.anchors, 'Center')}</div></div>
      <div class="section"><div class="section-title">Resolution</div>
        <div class="prop"><div class="muted">Size</div>${select('resolution', o.resolutions, 'Keep')}</div>
        <div class="prop" id="ie-custom" hidden><div class="muted">W × H</div><div class="custom-size"><input class="field" data-input="custom_w" inputmode="numeric" spellcheck="false"><span class="muted">×</span><input class="field" data-input="custom_h" inputmode="numeric" spellcheck="false"></div></div>
        <div class="prop"><div class="muted">How</div>${select('fit', o.fits, o.fits[0])}</div></div>
      <div class="section" style="gap:12px"><div style="display:flex;justify-content:space-between"><div class="section-title">Adjust</div><div class="link small" data-a="reset">Reset all edits</div></div>
        ${slider('brightness', 'Brightness')}${slider('contrast', 'Contrast')}${slider('saturation', 'Colour')}${slider('sharpness', 'Sharpness')}</div>
      <div class="section"><div class="section-title">Save as</div>
        <div class="prop"><div class="muted">Format</div>${select('format', o.formats, S.format)}</div>
        <div class="prop"><div class="muted">Quality</div><div class="prop-value" style="display:flex;gap:8px;align-items:center"><input type="range" min="40" max="100" value="92" data-input="quality"><div class="mono muted small" data-value="quality" style="min-width:22px;text-align:right">92</div></div></div>
        <div class="prop"><div class="muted">Add to name</div><input class="field prop-value mono small" value="_edited" data-input="suffix" spellcheck="false"></div>
        <div class="prop"><div class="muted">Save to</div><div class="prop-value" style="display:flex;flex-direction:column;gap:4px"><div class="mono small ellipsis" id="ie-out"></div><div class="small"><span class="link" data-a="change">Change</span> · <span class="link" data-a="open">Open</span></div></div></div></div>`;
    drawRatios();
    drawOut();
  }

  function drawRatios() {
    inspector.querySelector('#ie-ratios').innerHTML = S.options.ratios.map(r => `<div class="ratio-chip${S.recipe.ratio === r ? ' on' : ''}" data-a="ratio" data-r="${esc(r)}">${esc(r)}</div>`).join('');
  }

  function drawOut() {
    const out = inspector.querySelector('#ie-out');
    if (out) { out.textContent = S.out; out.title = S.out; }
  }

  function syncInspector() {
    const r = S.recipe;
    for (const input of inspector.querySelectorAll('[data-input]')) {
      const key = input.dataset.input;
      if (key in r && document.activeElement !== input) input.value = r[key];
    }
    for (const key of ['brightness', 'contrast', 'saturation', 'sharpness']) inspector.querySelector(`[data-value=${key}]`).textContent = `${r[key]}%`;
    inspector.querySelector('[data-value=quality]').textContent = S.quality;
    for (const button of inspector.querySelectorAll('[data-a=flip]')) button.classList.toggle('on', !!r[button.dataset.k]);
    inspector.querySelector('#ie-custom').hidden = r.resolution !== 'Custom';
    drawRatios();
  }

  // ---------------------------------------------------------------- list and bottom bar
  function drawList() {
    const top = listEl.scrollTop;
    listEl.innerHTML = S.files.map((f, i) => `<div class="list-row${f.path === S.selected ? ' on' : ''}" data-pick="${i}" title="${esc(f.path)}">
      ${f.thumb ? `<img class="thumb" width="44" height="33" src="${f.thumb}" alt="">` : '<div class="thumb" style="width:44px;height:33px"></div>'}
      <div class="list-text"><div class="small ellipsis">${esc(f.name)}</div><div class="mono muted" style="font-size:11px">${f.error ? 'can\'t open' : f.w ? `${f.w} × ${f.h}` : ''}</div></div>
      <div class="x" data-a="remove" data-i="${i}">×</div></div>`).join('');
    listEl.scrollTop = top;
    const n = S.files.length;
    footerEl.innerHTML = n ? `<div>${plural(n, 'picture')} · same edits for all</div><div class="link" data-a="clear">Clear</div>` : '<div>No pictures yet</div>';
  }

  function drawBottom() {
    const n = S.files.length;
    if (S.saving) {
      const { i, n: total, name } = S.progress;
      if (!bottomEl.querySelector('.bar')) bottomEl.innerHTML = `<div class="ie-progress"><div class="progress-text"><div class="ellipsis" data-status></div><div class="muted mono" data-count></div></div><div class="bar"><div style="width:0"></div></div></div>`;
      bottomEl.querySelector('[data-status]').textContent = name ? `Saving ${name}` : 'Finishing…';
      bottomEl.querySelector('[data-count]').textContent = `${i} / ${total}`;
      bottomEl.querySelector('.bar > div').style.width = `${total ? i / total * 100 : 0}%`;
      return;
    }
    const m = S.message;
    const message = m ? `<div class="banner ${m.kind} selectable" style="flex-basis:100%">${esc(m.text)}${m.folder ? ` <span class="link" data-a="open">Open folder</span>` : ''}</div>` : '';
    bottomEl.innerHTML = `${message}<button class="btn primary btn-save" data-a="save"${n ? '' : ' disabled'}>${n ? (n === 1 ? 'Save 1 picture' : `Save all ${n} pictures`) : 'Add pictures first'}</button>
      <div class="muted small">to ${esc(shortPath(S.out))} · name + “${esc(S.suffix)}”</div>`;
  }

  // ---------------------------------------------------------------- preview: one request at a time, always the latest edits
  let timer = null, busy = false, again = false;

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(refresh, 80);            // wait for the slider to pause
  }

  async function refresh() {
    if (busy) { again = true; return; }
    if (!S.selected) {
      imgEl.hidden = true;
      emptyEl.hidden = false;
      emptyEl.textContent = 'Add pictures to see the preview here.';
      sizesEl.textContent = '';
      return;
    }
    busy = true;
    const scale = window.devicePixelRatio || 1;
    const result = await call('image', 'preview', S.selected, S.recipe, S.original,
      Math.round((previewEl.clientWidth - 48) * scale), Math.round((previewEl.clientHeight - 48) * scale));
    busy = false;
    if (result.error) {
      imgEl.hidden = true;
      emptyEl.hidden = false;
      emptyEl.textContent = result.error;
    } else {
      imgEl.style.maxWidth = `${previewEl.clientWidth - 48}px`;
      imgEl.style.maxHeight = `${previewEl.clientHeight - 48}px`;
      imgEl.src = result.url;
      imgEl.hidden = false;
      emptyEl.hidden = true;
      const [ow, oh] = result.original, [rw, rh] = result.result;
      sizesEl.textContent = `${ow} × ${oh}  →  ${rw} × ${rh}`;
    }
    if (again) { again = false; refresh(); }
  }

  new ResizeObserver(() => { if (S.selected) schedule(); }).observe(previewEl);

  // ---------------------------------------------------------------- files
  async function add(paths) {
    if (!paths.length) return;
    const files = await call('image', 'add', paths, S.files.map(f => f.path));
    S.files.push(...files);
    S.message = null;
    if (!S.selected && S.files.length) { S.selected = S.files[0].path; schedule(); }
    drawList();
    drawBottom();
  }

  function remove(i) {
    const [gone] = S.files.splice(i, 1);
    if (gone.path === S.selected) {
      S.selected = S.files.length ? S.files[Math.min(i, S.files.length - 1)].path : null;
      schedule();
    }
    drawList();
    drawBottom();
  }

  on('image.thumb', t => {
    const f = S.files.find(x => x.path === t.path);
    if (f) { Object.assign(f, t); drawList(); }
  });
  on('image.progress', p => { S.progress = p; drawBottom(); });
  on('image.done', d => {
    S.saving = false;
    const failed = d.failed.length ? ` Could not edit: ${d.failed.map(f => `${f.name} (${f.error})`).join(', ')}.` : '';
    S.message = { kind: d.failed.length ? 'warn' : 'good', text: `${plural(d.saved, 'picture')} saved. The originals weren't changed.${failed}`, folder: true };
    drawBottom();
  });
  on('image.error', message => { S.saving = false; S.message = { kind: 'bad', text: message }; drawBottom(); });

  // ---------------------------------------------------------------- input
  el.addEventListener('input', e => {
    const key = e.target.dataset.input;
    if (!key) return;
    const value = e.target.value;
    if (key === 'format') S.format = value;
    else if (key === 'quality') S.quality = +value;
    else if (key === 'suffix') { S.suffix = value; drawBottom(); }
    else {
      S.recipe[key] = ['brightness', 'contrast', 'saturation', 'sharpness'].includes(key) ? +value : value;
      schedule();
    }
    syncInspector();
  });

  el.addEventListener('focusout', e => {
    if (e.target.dataset.input === 'angle') {       // tidy up what was typed
      const angle = parseFloat(S.recipe.angle);
      S.recipe.angle = Number.isFinite(angle) ? angle : 0;
      syncInspector();
    }
  });

  el.addEventListener('click', async e => {
    const target = e.target.closest('[data-a]');
    if (!target) {
      const row = e.target.closest('[data-pick]');
      if (row) { S.selected = S.files[+row.dataset.pick].path; drawList(); schedule(); }
      return;
    }
    const act = target.dataset.a;
    if (act === 'add') add(await call('image', 'choose'));
    else if (act === 'remove') remove(+target.dataset.i);
    else if (act === 'clear') { S.files = []; S.selected = null; S.message = null; drawList(); drawBottom(); schedule(); }
    else if (act === 'edited' || act === 'original') {
      S.original = act === 'original';
      el.querySelector('[data-a=edited]').classList.toggle('on', !S.original);
      el.querySelector('[data-a=original]').classList.toggle('on', S.original);
      schedule();
    } else if (act === 'turn') {
      const angle = parseFloat(S.recipe.angle) || 0;
      S.recipe.angle = ((angle + +target.dataset.d) % 360 + 360) % 360;
      syncInspector();
      schedule();
    } else if (act === 'flip') {
      S.recipe[target.dataset.k] = !S.recipe[target.dataset.k];
      syncInspector();
      schedule();
    } else if (act === 'ratio') {
      S.recipe.ratio = target.dataset.r;
      syncInspector();
      schedule();
    } else if (act === 'reset') {
      S.recipe = { ...DEFAULTS, fit: S.options.fits[0] };
      syncInspector();
      schedule();
    } else if (act === 'change') {
      const folder = await call('image', 'choose_out', S.out);
      if (folder) { S.out = folder; drawOut(); drawBottom(); }
    } else if (act === 'open') {
      const problem = await call('image', 'open_out', S.out);
      if (problem) { S.message = { kind: 'bad', text: problem }; drawBottom(); }
    } else if (act === 'save') {
      if (!S.files.length || S.saving) return;
      S.saving = true;
      S.message = null;
      S.progress = { i: 0, n: S.files.length, name: S.files[0].name };
      drawBottom();
      call('image', 'save', S.files.map(f => f.path), S.out, S.recipe, S.suffix, S.format, S.quality);
    }
  });

  hooks.onDrop = add;
  hooks.onShow = () => { if (S.selected) schedule(); };
  hooks.onKey = e => {
    if (e.key === 'Delete' && S.selected && !e.target.matches('input, select, textarea')) {
      remove(S.files.findIndex(f => f.path === S.selected));
    }
  };

  drawList();
  call('image', 'state').then(state => {
    S.options = state;
    S.out = state.out;
    S.recipe.fit = state.fits[0];
    DEFAULTS.fit = state.fits[0];
    buildInspector();
    syncInspector();
    drawBottom();
  });
});
