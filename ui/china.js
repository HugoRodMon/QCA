/* Price Extractor, China: the cleaned WeChat reports (Word) split into the China sheets' columns.
   Shown inside the Price Extractor page when its Europe | China switch is on China. */
dqs.chinaPage = root => {
  const { esc, call, on, plural } = dqs;
  const S = { files: [], out: '', phase: 'ready', report: null, error: '' };

  root.innerHTML = `<div class="columns">
      <section class="card files-card" id="cn-files"></section>
      <section class="output-col">
        <div class="card output-card">
          <div style="display:flex;flex-direction:column;gap:6px"><div class="label-up">Save to</div>
            <div style="display:flex;gap:6px;align-items:center"><div class="path" id="cn-out"></div>
              <button class="btn" data-c="change" style="padding:7px 10px">Change</button><button class="btn" data-c="open" style="padding:7px 10px">Open</button></div></div>
          <div id="cn-run"></div>
        </div>
        <div id="cn-results" style="display:flex;flex-direction:column;gap:14px;flex:1"></div>
      </section>
    </div>`;
  const filesEl = root.querySelector('#cn-files'), runEl = root.querySelector('#cn-run');
  const resultsEl = root.querySelector('#cn-results'), outEl = root.querySelector('#cn-out');

  function drawFiles() {
    const n = S.files.length;
    const head = `<div class="card-head"><div style="display:flex;align-items:baseline;gap:8px"><div class="card-title">WeChat reports</div><div class="muted small">${n ? plural(n, 'file') : 'none yet'}</div></div>
      <div style="display:flex;gap:6px"><button class="btn" data-c="add">Add files</button><button class="btn ghost" data-c="clear">Clear</button></div></div>`;
    const foot = '<div class="card-footer">The Word file with the cleaned WeChat lines: headings (market, date, product) and one line per offer.</div>';
    if (!n) {
      filesEl.innerHTML = `${head}<div class="dz dz-big" data-c="add"><div class="dz-head">Drop the cleaned WeChat reports</div><div class="muted">or click to choose</div>
        <div class="dz-chips"><div class="dz-chip">Word (DOCX)</div></div></div>${foot}`;
      return;
    }
    const status = f => f.error ? `<div style="color:var(--bad);font-weight:600" title="${esc(f.error)}">Not read</div>`
      : f.rows !== undefined ? `<div class="mono">${esc(plural(f.rows, 'line'))}</div>`
      : S.phase === 'running' ? '<div style="color:var(--accent-text);font-weight:600">Reading…</div>' : '<div class="muted">Ready</div>';
    filesEl.innerHTML = `${head}<div class="table-grid table-head cn-grid"><div>Type</div><div>File</div><div style="text-align:right">Status</div><div></div></div>
      <div class="table-body">${S.files.map((f, i) => `<div class="table-grid table-row cn-grid" title="${esc(f.path)}">
        <div class="badge">DOCX</div><div class="ellipsis">${esc(f.name)}</div><div class="status">${status(f)}</div>
        <div class="x" data-c="remove" data-i="${i}">×</div></div>`).join('')}</div>${foot}`;
  }

  function drawRun() {
    outEl.textContent = S.out;
    outEl.title = S.out;
    const n = S.files.length;
    const banner = S.error ? `<div class="banner bad selectable" style="margin-bottom:14px">${esc(S.error)}</div>` : '';
    const label = S.phase === 'running' ? 'Splitting into columns…' : S.phase === 'done' ? 'Split again'
      : n ? `Split ${plural(n, 'report')} into columns` : 'Add a WeChat report first';
    runEl.innerHTML = `${banner}<button class="btn primary btn-big" data-c="start"${n && S.phase !== 'running' ? '' : ' disabled'}>${esc(label)}</button>`;
  }

  function drawResults() {
    const r = S.report;
    if (S.phase !== 'done' || !r) {
      resultsEl.innerHTML = '<div class="placeholder">The Excel with a tab per product (CHERRIES, BLUEBERRY, CITRUS...), in the same columns as the China file, will show here.</div>';
      return;
    }
    const tile = (number, label, color) => `<div class="tile"><div class="tile-number" style="${color ? `color:${color}` : ''}">${number}</div><div class="muted small">${label}</div></div>`;
    const output = r.workbook ? `<div class="out-row"><div class="xls">XLS</div><div class="out-text"><div class="out-name ellipsis">${esc(r.name)}</div>
        <div class="muted small ellipsis">${esc(r.sheets.map(s => `${s.name} ${s.rows}`).join(' · '))}</div></div>
        <button class="btn btn-small" data-c="open-file" data-path="${esc(r.workbook)}">Open</button></div>`
      : '<div class="empty-note">No Excel was written: no line could be read.</div>';
    const checks = r.check.length ? r.check.map(c => `<div class="issue tone-${c.kind}"><div class="issue-dot"></div><div class="issue-text">
        <div class="issue-title selectable">${esc(c.why.charAt(0).toUpperCase() + c.why.slice(1))}</div><div class="issue-detail selectable">${esc(c.line)}</div></div></div>`).join('')
      : '<div class="empty-note">Nothing to check.</div>';
    resultsEl.innerHTML = `<div class="tiles">${tile(r.rows, 'rows')}${tile(r.red, 'red cells to fill in', 'var(--warn)')}${tile(r.check.length, 'lines to check', r.check.some(c => c.kind === 'bad') ? 'var(--bad)' : 'var(--warn)')}</div>
      <div class="card"><div class="results-head"><div>Excel file</div><div class="link" data-c="open">Open folder</div></div>${output}
        <div class="tab-note">Copy each tab's rows (without the heading row) into the same tab of the China file. Red cells: the WeChat line doesn't say it (e.g. the box weight).</div></div>
      <div class="card" style="overflow:hidden"><div class="results-head"><div>To check</div></div><div style="padding:4px 0">${checks}</div></div>`;
  }

  function drawAll() { drawFiles(); drawRun(); drawResults(); }

  function reset() {
    if (S.phase !== 'running') { S.phase = 'ready'; S.report = null; S.error = ''; S.files.forEach(f => { delete f.rows; delete f.error; }); }
  }

  async function add(paths) {
    if (S.phase === 'running' || !paths || !paths.length) return;
    const files = await call('china', 'add', paths, S.files.map(f => f.path));
    reset();
    S.files.push(...files);
    if (!files.length) S.error = 'Only Word files (.docx) are read here.';
    drawAll();
  }

  on('china.done', report => {
    S.phase = 'done';
    S.report = report;
    for (const r of report.files) {
      const f = S.files.find(x => x.path === r.path);
      if (f) Object.assign(f, r.error ? { error: r.error } : { rows: r.rows });
    }
    drawAll();
  });
  on('china.error', message => { S.phase = 'error'; S.error = message; drawAll(); });

  root.addEventListener('click', async e => {
    const target = e.target.closest('[data-c]');
    if (!target) return;
    const act = target.dataset.c;
    if (act === 'add') add(await call('china', 'choose'));
    else if (act === 'clear') { if (S.phase !== 'running') { S.files = []; reset(); drawAll(); } }
    else if (act === 'remove') { if (S.phase !== 'running') { S.files.splice(+target.dataset.i, 1); reset(); drawAll(); } }
    else if (act === 'start') {
      if (!S.files.length || S.phase === 'running') return;
      S.phase = 'running'; S.error = ''; S.report = null;
      S.files.forEach(f => { delete f.rows; delete f.error; });
      drawAll();
      call('china', 'start', S.files.map(f => f.path), S.out);
    } else if (act === 'change') {
      const folder = await call('china', 'choose_out', S.out);
      if (folder) { S.out = folder; drawRun(); }
    } else if (act === 'open') {
      const problem = await call('china', 'open_out', S.out);
      if (problem) { S.error = problem; drawRun(); }
    } else if (act === 'open-file') {
      const problem = await call('china', 'open_file', target.dataset.path);
      if (problem) { S.error = problem; drawRun(); }
    }
  });

  drawAll();
  call('china', 'state').then(state => { S.out = state.out; drawRun(); });
  return { onDrop: add };
};
