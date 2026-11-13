/* Price Extractor: the files on the left, where they go and what came out on the right. */
dqs.addView('price', { code: 'PX', title: 'Price Extractor', sub: 'Supplier lists → Excel' }, (el, hooks) => {
  const { esc, call, on, plural } = dqs;
  const S = {
    files: [], leftOut: [], out: '', phase: 'ready', progress: { i: 0, n: 0, name: '' },
    report: null, tab: 'checks', error: '', selected: new Set(), anchor: null,
  };
  const TABS = [['checks', 'Price checks'], ['unknown', 'Not extracted'], ['failed', 'Not processed'], ['newcols', 'New columns'], ['log', 'Full log']];
  const now = new Date();
  const two = n => String(n).padStart(2, '0');
  const today = `${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][now.getDay()]} ${two(now.getDate())}-${two(now.getMonth() + 1)}-${now.getFullYear()}`;

  el.innerHTML = `<div class="page">
    <header class="page-head"><div class="page-head-text">
      <div class="page-title-row"><div class="page-title">Price Extractor</div>
        <div class="segment segment-small" id="px-region"><div data-region="europe" class="on">Europe</div><div data-region="china">China</div></div></div>
      <div class="muted" id="px-sub">Daily supplier price lists to Excel, in the final files' columns.</div></div>
      <div class="muted small mono">${today}</div></header>
    <div id="px-china" hidden></div>
    <div class="columns" id="px-europe">
      <section class="card files-card" id="px-files"></section>
      <section class="output-col">
        <div class="card output-card">
          <div style="display:flex;flex-direction:column;gap:6px"><div class="label-up">Save to</div>
            <div style="display:flex;gap:6px;align-items:center"><div class="path" id="px-out"></div>
              <button class="btn" data-a="change" style="padding:7px 10px">Change</button><button class="btn" data-a="open" style="padding:7px 10px">Open</button></div></div>
          <div id="px-run"></div>
        </div>
        <div id="px-results" style="display:flex;flex-direction:column;gap:14px;flex:1"></div>
      </section>
    </div></div>`;
  // Europe | China: two ways in, one page. China is in china.js.
  const SUBS = { europe: "Daily supplier price lists to Excel, in the final files' columns.",
                 china: 'The cleaned WeChat market reports, split into the columns of the China file.' };
  const chinaEl = el.querySelector('#px-china'), europeEl = el.querySelector('#px-europe');
  const china = dqs.chinaPage(chinaEl);
  let region = 'europe';
  function showRegion(r) {
    region = r;
    europeEl.hidden = r !== 'europe';
    chinaEl.hidden = r !== 'china';
    el.querySelector('#px-sub').textContent = SUBS[r];
    el.querySelectorAll('#px-region [data-region]').forEach(d => d.classList.toggle('on', d.dataset.region === r));
    try { localStorage.setItem('px-region', r); } catch (e) { /* private window: just not remembered */ }
  }
  el.querySelector('#px-region').addEventListener('click', e => {
    const d = e.target.closest('[data-region]');
    if (d) showRegion(d.dataset.region);
  });
  try { if (localStorage.getItem('px-region') === 'china') showRegion('china'); } catch (e) { /* see above */ }

  const filesEl = el.querySelector('#px-files'), runEl = el.querySelector('#px-run'), resultsEl = el.querySelector('#px-results'), outEl = el.querySelector('#px-out');

  // ---------------------------------------------------------------- drawing
  function fileRow(f, i) {
    let supplier = f.guess || '—', how = f.guess ? 'guessed from file name' : 'identified when extracting', color = f.guess ? '' : 'color:var(--muted)';
    if (f.status === 'done') { supplier = f.supplier; how = f.how; color = ''; }
    if (f.status === 'failed') {
      if (f.unrecognised) { supplier = 'Not recognised'; how = 'no identifier found'; color = 'color:var(--bad)'; }
      else { how = f.reason || 'could not be read'; }
    }
    const status = { ready: '<div class="muted">Ready</div>', reading: '<div style="color:var(--accent-text);font-weight:600">Reading…</div>',
      done: `<div class="mono">${esc(plural(f.rows, 'price'))}</div>`, failed: '<div style="color:var(--bad);font-weight:600">Not processed</div>' }[f.status];
    return `<div class="table-grid table-row${S.selected.has(f.path) ? ' selected' : ''}" data-row="${i}" title="${esc(f.path)}">
      <div class="badge">${esc(f.kind)}</div><div class="ellipsis">${esc(f.name)}</div>
      <div class="sup"><div class="sup-name ellipsis" style="${color}">${esc(supplier)}</div><div class="sup-how" title="${esc(how)}">${esc(how)}</div></div>
      <div class="status">${status}</div><div class="x" data-a="remove" data-i="${i}">×</div></div>`;
  }

  function footer() {
    const left = S.leftOut;
    const out = left.length === 1 ? `1 final Excel (${left[0]}) was left out — it's not a price list. `
      : left.length > 3 ? `${left.length} final Excels were left out — they're not price lists. `
      : left.length ? `${left.length} final Excels (${left.join(', ')}) were left out — they're not price lists. ` : '';
    return out + (S.files.length ? 'Files are recognised by their content when extracting.' : '');
  }

  function drawFiles() {
    const n = S.files.length;
    const scroll = filesEl.querySelector('.table-body');
    const top = scroll ? scroll.scrollTop : 0;
    const head = `<div class="card-head"><div style="display:flex;align-items:baseline;gap:8px"><div class="card-title">Price files</div><div class="muted small">${n ? plural(n, 'file') : 'none yet'}</div></div>
      <div style="display:flex;gap:6px"><button class="btn" data-a="add">Add files</button><button class="btn ghost" data-a="clear">Clear</button></div></div>`;
    const note = footer();
    const foot = note ? `<div class="card-footer" title="${esc(S.leftOut.join(', '))}">${esc(note)}</div>` : '';
    if (!n) {
      filesEl.innerHTML = `${head}<div class="dz dz-big" data-a="add"><div class="dz-head">Drop today's price files or a folder</div><div class="muted">or click to choose</div>
        <div class="dz-chips">${['PDF', 'WhatsApp TXT', 'MHTML', 'XLSX', 'Pictures'].map(c => `<div class="dz-chip">${c}</div>`).join('')}</div></div>${foot}`;
      return;
    }
    filesEl.innerHTML = `${head}<div class="table-grid table-head"><div>Type</div><div>File</div><div>Supplier</div><div style="text-align:right">Status</div><div></div></div>
      <div class="table-body">${S.files.map(fileRow).join('')}</div>${foot}`;
    filesEl.querySelector('.table-body').scrollTop = top;
  }

  function drawRun() {
    const n = S.files.length;
    outEl.textContent = S.out;
    outEl.title = S.out;
    const banner = S.error ? `<div class="banner bad selectable" style="margin-bottom:14px">${esc(S.error)}</div>` : '';
    if (S.phase === 'running') {
      if (!runEl.querySelector('.bar')) {
        runEl.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px"><div class="progress-text"><div class="ellipsis" data-status></div><div class="muted mono" style="flex-shrink:0" data-count></div></div><div class="bar"><div style="width:0"></div></div></div>`;
      }
      const { i, n: total, name } = S.progress;
      runEl.querySelector('[data-status]').textContent = name ? `Reading ${name}` : 'Writing Excel files…';
      runEl.querySelector('[data-count]').textContent = `${Math.min(i, total)} / ${total}`;
      runEl.querySelector('.bar > div').style.width = `${total ? Math.min(i, total) / total * 100 : 0}%`;
      return;
    }
    const label = S.phase === 'done' ? 'Extract again' : n ? `Extract prices from ${plural(n, 'file')}` : 'Add price files first';
    runEl.innerHTML = `${banner}<button class="btn primary btn-big" data-a="start"${n ? '' : ' disabled'}>${esc(label)}</button>`;
  }

  function issueRow(i) {
    return `<div class="issue tone-${esc(i.kind)}"><div class="issue-dot"></div><div class="issue-text">
      <div class="issue-title-row"><div class="issue-title selectable">${esc(i.title)}</div><div class="muted small">${esc(i.supplier)}</div></div>
      ${i.detail ? `<div class="issue-detail selectable">${esc(i.detail)}</div>` : ''}</div><div class="tag">${esc(i.tag)}</div></div>`;
  }

  function drawTab(r) {
    if (S.tab === 'log') return `<div class="log selectable">${esc(r.log)}</div>`;
    const items = r.issues[S.tab];
    return `<div style="padding:4px 0"><div class="tab-note">${esc(r.notes[S.tab])}</div>${items.length ? items.map(issueRow).join('') : '<div class="empty-note">Nothing here.</div>'}</div>`;
  }

  function drawResults() {
    const r = S.report;
    if (S.phase !== 'done' || !r) {
      resultsEl.innerHTML = `<div class="placeholder">The Excel files, price checks and anything that couldn't be read will show here.</div>`;
      return;
    }
    const tile = (number, label, color) => `<div class="tile"><div class="tile-number" style="${color ? `color:${color}` : ''}">${number}</div><div class="muted small">${label}</div></div>`;
    const renamed = r.renamed.length ? `<div class="banner warn" style="margin:10px 16px">The usual file is open, probably in Excel, so the new prices were saved under another name: ${esc(r.renamed.map(x => `${x.used} (instead of ${x.wanted})`).join(', '))}.</div>` : '';
    const outputs = r.outputs.length ? r.outputs.map(o => `<div class="out-row"><div class="xls">XLS</div><div class="out-text"><div class="out-name ellipsis" title="${esc(o.name)}">${esc(o.name)}</div>
      <div class="muted small ellipsis" title="${esc(o.detail)}">${esc(o.detail)}</div></div><button class="btn btn-small" data-a="open-file" data-path="${esc(o.path)}">Open</button></div>`).join('')
      : '<div class="empty-note">No Excel file was written: nothing could be extracted.</div>';
    const tabs = TABS.map(([id, label]) => {
      const count = id === 'log' ? '…' : r.issues[id].length;
      const color = id === 'failed' ? 'var(--bad-text)' : id === 'log' ? 'var(--muted)' : id === 'newcols' ? 'var(--new-text)' : 'var(--warn-text)';
      return `<div class="tab${S.tab === id ? ' on' : ''}" data-a="tab" data-tab="${id}">${label}<div class="tab-count" style="color:${color}">${count}</div></div>`;
    }).join('');
    resultsEl.innerHTML = `<div class="tiles">${tile(r.rows, 'prices extracted')}${tile(r.to_look_at, 'to look at', 'var(--warn)')}${tile(r.not_processed, r.not_processed === 1 ? 'file not processed' : 'files not processed', 'var(--bad)')}</div>
      <div class="card"><div class="results-head"><div>Excel files</div><div class="link" data-a="open">Open folder</div></div>${renamed}${outputs}</div>
      <div class="card" style="overflow:hidden"><div class="tabs">${tabs}</div><div data-tabbody>${drawTab(r)}</div></div>`;
  }

  function drawAll() { drawFiles(); drawRun(); drawResults(); }

  // ---------------------------------------------------------------- files
  function backToReady() {
    if (S.phase === 'done' || S.phase === 'error') S.phase = 'ready';
    S.report = null;
    S.error = '';
    for (const f of S.files) f.status = 'ready';
  }

  async function add(paths) {
    if (S.phase === 'running' || !paths.length) return;
    try {
      const { files, left_out } = await call('price', 'add', paths, S.files.map(f => f.path));
      backToReady();
      S.files.push(...files.map(f => ({ ...f, status: 'ready' })));
      S.leftOut = [...new Set([...S.leftOut, ...left_out])];
    } catch (e) { S.error = String(e.message || e); }
    drawAll();
  }

  function remove(paths) {
    if (S.phase === 'running' || !paths.length) return;
    S.files = S.files.filter(f => !paths.includes(f.path));
    paths.forEach(p => S.selected.delete(p));
    backToReady();
    drawAll();
  }

  function selectRow(i, e) {
    const path = S.files[i].path;
    if (e.shiftKey && S.anchor !== null) {
      const [a, b] = [Math.min(S.anchor, i), Math.max(S.anchor, i)];
      S.selected = new Set(S.files.slice(a, b + 1).map(f => f.path));
    } else if (e.ctrlKey) {
      S.selected.has(path) ? S.selected.delete(path) : S.selected.add(path);
      S.anchor = i;
    } else {
      S.selected = S.selected.size === 1 && S.selected.has(path) ? new Set() : new Set([path]);
      S.anchor = i;
    }
    drawFiles();
  }

  // ---------------------------------------------------------------- running
  function start() {
    if (!S.files.length || S.phase === 'running') return;
    for (const f of S.files) f.status = 'ready';
    S.phase = 'running';
    S.report = null;
    S.error = '';
    S.progress = { i: 0, n: S.files.length, name: S.files[0].name };
    drawAll();
    call('price', 'start', S.files.map(f => f.path), S.out);
  }

  on('price.progress', p => {
    S.progress = p;
    const f = S.files.find(x => x.name === p.name && x.status === 'ready');
    if (f) f.status = 'reading';
    drawFiles();
    drawRun();
  });
  on('price.file', r => {
    const f = S.files.find(x => x.path === r.path);
    if (!f) return;
    if (r.failed) Object.assign(f, { status: 'failed', unrecognised: r.unrecognised, reason: r.reason });
    else Object.assign(f, { status: 'done', supplier: r.supplier, how: r.how, rows: r.rows });
    drawFiles();
  });
  on('price.done', report => {
    S.phase = 'done';
    S.report = report;
    S.tab = 'checks';
    drawAll();
  });
  on('price.error', message => {
    S.phase = 'error';
    S.error = message;
    for (const f of S.files) if (f.status === 'reading') f.status = 'ready';
    drawAll();
  });

  // ---------------------------------------------------------------- clicks
  el.addEventListener('click', async e => {
    const target = e.target.closest('[data-a]');
    if (!target) {
      const row = e.target.closest('[data-row]');
      if (row) selectRow(+row.dataset.row, e);
      return;
    }
    const act = target.dataset.a;
    if (act === 'add') add(await call('price', 'choose'));
    else if (act === 'clear') { if (S.phase !== 'running') { S.files = []; S.leftOut = []; S.selected.clear(); backToReady(); drawAll(); } }
    else if (act === 'remove') remove([S.files[+target.dataset.i].path]);
    else if (act === 'start') start();
    else if (act === 'change') {
      const folder = await call('price', 'choose_out', S.out);
      if (folder) { S.out = folder; S.error = ''; drawRun(); }
    } else if (act === 'open') {
      const problem = await call('price', 'open_out', S.out);
      if (problem) { S.error = problem; drawRun(); }
    } else if (act === 'open-file') {
      const problem = await call('price', 'open_file', target.dataset.path);
      if (problem) { S.error = problem; drawRun(); }
    } else if (act === 'tab') { S.tab = target.dataset.tab; drawResults(); }
  });

  hooks.onDrop = paths => (region === 'china' ? china.onDrop(paths) : add(paths));
  hooks.onKey = e => {
    if (region === 'china') return;
    if (e.key === 'Delete' && !e.target.matches('input, select, textarea')) remove([...S.selected]);
  };

  drawAll();
  call('price', 'state').then(state => { S.out = state.out; drawRun(); });
});
dqs.show('price');
