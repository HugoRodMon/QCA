/* Remarks: paste an inspection report, pick the client, copy the remark (and one line per box). */
dqs.addView('remarks', { code: 'RM', icon: dqs.icons.draft, title: 'Draft', sub: 'Report → remark text' }, (el, hooks) => {
  const { esc, call, on } = dqs;
  const S = { report: null, reading: false, client: '', product: '', remark: '', box: '', own: false, chosen: null,
              out: null, state: null, saving: false, note: '' };

  el.innerHTML = `<div class="page">
    <header class="page-head"><div class="page-head-text">
      <div class="page-title">Draft</div>
      <div class="muted">Paste an inspection report: the remark comes out of the client's template, ready to copy.</div></div>
      <div class="muted small" id="rm-source"></div></header>
    <section class="card">
      <div class="card-head"><div class="card-title">Report</div>
        <div style="display:flex;gap:6px"><button class="btn btn-small" data-a="clear" hidden>Clear</button></div></div>
      <div class="rm-paste" id="rm-paste" tabindex="0"></div>
    </section>
    <section class="card" id="rm-work" hidden></section>
  </div>`;
  const pasteEl = el.querySelector('#rm-paste'), workEl = el.querySelector('#rm-work'), sourceEl = el.querySelector('#rm-source');

  // ---------------------------------------------------------------- pasting
  function gridFrom(html, text) {
    if (html) {
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const rows = [];
      doc.querySelectorAll('tr').forEach(tr => {
        const cells = [];
        tr.querySelectorAll(':scope > td, :scope > th').forEach(td => {
          const nested = td.querySelector('table');                     // its rows come on their own
          const img = nested ? [] : [...td.querySelectorAll('img')].map(i => ({
            src: i.getAttribute('src') || '', alt: i.getAttribute('alt') || '', title: i.getAttribute('title') || '' }));
          const t = nested ? '' : (td.textContent || '').replace(/\s+/g, ' ').trim();
          cells.push({ t, img });
          const span = Math.min(parseInt(td.getAttribute('colspan') || '1', 10) || 1, 60);
          for (let k = 1; k < span; k++) cells.push({ t: '' });
        });
        if (cells.length) rows.push(cells);
      });
      if (rows.length) return rows;
    }
    return String(text || '').split(/\r?\n/).filter(l => l.trim()).map(l => l.split('\t').map(t => ({ t: t.trim() })));
  }

  async function paste(e) {
    if (e.target.closest('textarea, input')) return;                  // typing in the template: a normal paste
    const data = e.clipboardData;
    if (!data) return;
    e.preventDefault();
    const grid = gridFrom(data.getData('text/html'), data.getData('text/plain'));
    if (!grid.length) return;
    S.reading = true;
    drawPaste();
    try {
      S.report = await call('remarks', 'read', grid);
    } catch (err) {
      S.report = { problems: ['The report couldn\'t be read: ' + err], columns: [], boxes: [], summary: {}, defects: [] };
    }
    S.reading = false;
    S.chosen = new Set(S.report.defects.filter(d => d.boxes).map(d => d.name));
    S.client = S.report.client || '';
    S.product = S.report.product || '';
    await loadTemplate();
    drawPaste();
    drawWork();
    refresh();
  }
  el.addEventListener('paste', paste);
  hooks.onShow = () => { if (!el.contains(document.activeElement)) pasteEl.focus(); };

  // ---------------------------------------------------------------- the report
  const SUMMARY = ['Business partner', 'Inspection Date', 'Inspection Place', 'Origin', 'Template name', 'Temptale', 'Container Nr', 'Receiver'];

  function drawPaste(keepScroll) {
    el.querySelector('[data-a=clear]').hidden = !S.report;
    if (S.reading) { pasteEl.innerHTML = '<div class="rm-empty"><div class="rm-hint">Reading the report…</div></div>'; return; }
    const r = S.report;
    if (!r) {
      const cell = '<td></td>';
      pasteEl.innerHTML = `<div class="rm-empty"><table class="rm-grid rm-blank">${('<tr>' + cell.repeat(3) + '</tr>').repeat(3)}</table>
        <div class="rm-hint">Click here and press <b>Ctrl+V</b> to paste the report: the summary on top and the boxes table,
        copied from the website (or from Excel).</div></div>`;
      return;
    }
    const chips = SUMMARY.filter(k => k in r.summary).map(k =>
      `<div class="rm-fact"><div class="label-up">${esc(k)}</div><div class="ellipsis">${esc(r.summary[k] || '—')}</div></div>`).join('');
    // every name can be corrected (the website cuts long ones short); a missing one is yellow
    const head = r.columns.map((c, i) => c
      ? `<th><input class="rm-head" data-col="${i}" value="${esc(c)}" title="Click to correct the name (it's remembered for this website template)"></th>`
      : `<th class="rm-unknown"><input class="field" data-col="${i}" placeholder="name?" title="This column's name was a picture that couldn't be read: type it"></th>`).join('');
    const body = r.boxes.map((row, b) => `<tr><td class="rm-n">${b + 1}</td>${row.map(v => `<td>${esc(v)}</td>`).join('')}</tr>`).join('');
    const old = pasteEl.querySelector('.rm-scroll');
    const keep = old && keepScroll ? [old.scrollLeft, old.scrollTop] : null;
    pasteEl.innerHTML = `${r.problems.length ? `<div class="banner warn" style="margin:12px 16px 0">${r.problems.map(esc).join('<br>')}</div>` : ''}
      <div class="rm-facts">${chips}</div>
      <div class="rm-scroll"><table class="rm-grid"><tr><th class="rm-n">#</th>${head}</tr>${body}</table></div>`;
    if (keep) { const s = pasteEl.querySelector('.rm-scroll'); s.scrollLeft = keep[0]; s.scrollTop = keep[1]; }
  }

  pasteEl.addEventListener('change', async e => {
    const input = e.target.closest('[data-col]');
    if (!input) return;
    const old = S.report.columns[+input.dataset.col];
    const unticked = S.report.defects.filter(d => d.boxes && !S.chosen.has(d.name)).map(d => d.name);
    S.report = await call('remarks', 'name_column', +input.dataset.col, input.value);
    const renamed = S.report.columns[+input.dataset.col];
    // keep the defects the person unticked unticked (also the one just renamed)
    S.chosen = new Set(S.report.defects.filter(d => d.boxes && !unticked.includes(d.name === renamed ? old : d.name)).map(d => d.name));
    drawPaste(true); drawWork(); refresh();
  });

  // ---------------------------------------------------------------- the remark
  async function loadTemplate() {
    const t = await call('remarks', 'template', S.client, S.product);
    S.remark = t.remark; S.box = t.box; S.own = t.own; S.edited = false;
    S.from = t.own ? `${t.client === '*' ? 'any client' : t.client} · ${t.product === '*' ? 'any product' : t.product}` : 'default';
  }

  function drawWork() {
    const r = S.report;
    workEl.hidden = !r;
    if (!r) return;
    const clients = (S.state && S.state.clients) || [];
    const defects = r.defects.map(d => `<label class="rm-defect${d.boxes ? '' : ' rm-none'}" title="${d.boxes ? `Found in ${d.boxes} of ${r.boxes.length} boxes; ${d.all}% over all boxes` : 'Not found in any box'}">
      <input type="checkbox" data-defect="${esc(d.name)}"${S.chosen.has(d.name) ? ' checked' : ''}${d.boxes ? '' : ' disabled'}>
      <span>${esc(d.name)}</span><span class="mono rm-pct">${d.boxes ? d.avg + '%' : '—'}</span><span class="muted small">${d.boxes}/${r.boxes.length}</span>
      ${groupTag(d.name)}</label>`).join('');
    const holders = Object.entries((S.state && S.state.placeholders) || {}).map(([k, v]) => `<span class="rm-ph" data-ph="[${esc(k)}]" title="${esc(v)}">[${esc(k)}]</span>`).join('');
    const phrases = ((S.state && S.state.phrases) || []).map((p, i) => `<div class="rm-phrase" data-phrase="${i}" title="Add at the cursor">${esc(p)}</div>`).join('');
    const boxHolders = Object.entries((S.state && S.state.box_placeholders) || {}).map(([k, v]) => `<span class="rm-ph" data-bph="[${esc(k)}]" title="${esc(v)}">[${esc(k)}]</span>`).join('');
    workEl.innerHTML = `<div class="card-head"><div class="card-title">Remark</div>
        <div class="rm-who">
          <label class="muted small">Client</label><input class="field" id="rm-client" list="rm-clients" value="${esc(S.client)}" style="width:190px">
          <datalist id="rm-clients">${clients.map(c => `<option value="${esc(c)}">`).join('')}</datalist>
          <label class="muted small">Product</label><input class="field" id="rm-product" value="${esc(S.product)}" style="width:120px">
          <span class="tag ${S.own ? 'tone-new' : ''}" id="rm-from" style="${S.own ? '' : 'background:var(--raised);color:var(--muted)'}">Template: ${esc(S.from)}</span>
        </div></div>
      <div class="rm-body">
        <div><div class="rm-col-head" style="margin-bottom:6px"><div class="label-up">Defects to name — average incidence where found, boxes with it
            · <span title="Click the tag on a defect: – no group, Q quality, C condition">Q/C groups</span>: <span class="mono" id="rm-groups"></span></div>
            <button class="btn btn-small ghost" data-a="save-groups" title="This PC's Quality / Condition groups become everyone's (needs the templates key)">Save groups for everyone…</button></div>
          <div class="rm-defects">${defects || '<span class="muted">No defect columns in this report.</span>'}</div></div>
        <div class="rm-two">
          <div class="rm-col"><div class="rm-col-head"><div class="label-up">Template (editable)</div></div>
            <textarea class="field rm-text" id="rm-remark" spellcheck="false">${esc(S.remark)}</textarea>
            <div class="rm-phs">${holders}</div></div>
          <div class="rm-col"><div class="rm-col-head"><div class="label-up">Remark</div><button class="btn btn-small primary" data-a="copy">Copy</button></div>
            <div class="rm-out selectable" id="rm-out"></div>
            <div class="small" id="rm-unknown" style="color:var(--warn-text)"></div></div>
        </div>
        <div class="rm-phrases-box">
          <div class="rm-col-head"><div class="label-up">Phrases — click to add where the cursor is</div>
            <button class="btn btn-small ghost" data-a="phrases" title="Change the list for everyone (needs the templates key)">Edit phrases…</button></div>
          <div class="rm-phrases">${phrases || '<span class="muted small">No phrases yet: add them with Edit phrases (templates key).</span>'}</div>
        </div>
        <div class="rm-two">
          <div class="rm-col"><div class="rm-col-head"><div class="label-up">One line per box (template, empty = none)</div></div>
            <textarea class="field rm-text rm-short" id="rm-box" spellcheck="false">${esc(S.box)}</textarea>
            <div class="rm-phs">${boxHolders}</div></div>
          <div class="rm-col"><div class="rm-col-head"><div class="label-up">Box remarks</div><button class="btn btn-small" data-a="copy-boxes" hidden>Copy all</button></div>
            <div class="rm-lines" id="rm-lines"></div></div>
        </div>
      </div>
      <div class="card-footer rm-foot"><span id="rm-note"></span><span class="spacer"></span>
        <button class="btn btn-small ghost" data-a="placeholders" title="What the placeholders mean, and your own (changing them needs the templates key)">Placeholders…</button>
        <button class="btn btn-small ghost" data-a="reset">Back to the saved template</button>
        <button class="btn btn-small" data-a="save" title="Changes the template for everyone (needs the templates key)">Save as everyone's template…</button></div>`;
    drawOut();
  }

  // the Quality / Condition group of a defect (Camposol's remark): '–', 'Q' or 'C' on its chip
  const GROUP_TAG = { quality: 'Q', condition: 'C', '': '–' };
  const groupOf = name => ((S.state && S.state.groups) || {})[name.toLowerCase()] || '';
  const groupTag = name => `<span class="rm-group rm-group-${groupOf(name) || 'none'}" data-group="${esc(name)}"
      title="Group: ${groupOf(name) || 'none'} (click to change)">${GROUP_TAG[groupOf(name)]}</span>`;

  function drawOut() {
    const out = S.out;
    const outEl = el.querySelector('#rm-out');
    if (!outEl) return;
    outEl.textContent = out ? out.text : '';
    el.querySelector('#rm-unknown').textContent = out && out.unknown.length ? `Not filled (unknown placeholder): ${out.unknown.join(', ')}` : '';
    const lines = out ? out.boxes : [];
    el.querySelector('#rm-lines').innerHTML = lines.length ? lines.map((l, i) => `<div class="rm-line"><span class="rm-n mono">${i + 1}</span>
      <span class="selectable rm-line-text">${esc(l)}</span><button class="btn btn-small" data-a="copy-line" data-i="${i}">Copy</button></div>`).join('')
      : '<div class="muted small" style="padding:8px 0">No box lines for this template.</div>';
    el.querySelector('[data-a=copy-boxes]').hidden = !lines.length;
    el.querySelector('#rm-note').textContent = S.note;
    const g = el.querySelector('#rm-groups');
    if (g) g.textContent = out ? `Q ${out.values['quality defects %']}% · C ${out.values['condition defects %']}%` : '';
  }

  let timer = null;
  function refresh() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      if (!S.report) return;
      S.out = await call('remarks', 'render', S.client, S.product, S.remark, S.box, [...S.chosen]);
      drawOut();
    }, 120);
  }

  // the phrases go into the template last clicked in (the remark's or the box lines')
  for (const kind of ['focusin', 'mousedown', 'keyup']) {
    workEl.addEventListener(kind, e => { if (e.target.id === 'rm-remark' || e.target.id === 'rm-box') S.target = e.target.id; });
  }
  workEl.addEventListener('input', e => {
    if (e.target.id === 'rm-remark') { S.remark = e.target.value; S.edited = true; refresh(); }
    else if (e.target.id === 'rm-box') { S.box = e.target.value; S.edited = true; refresh(); }
  });
  workEl.addEventListener('change', async e => {
    if (e.target.dataset.defect) {
      if (e.target.checked) S.chosen.add(e.target.dataset.defect); else S.chosen.delete(e.target.dataset.defect);
      refresh();
    } else if (e.target.id === 'rm-client' || e.target.id === 'rm-product') {
      S.client = el.querySelector('#rm-client').value.trim();
      S.product = el.querySelector('#rm-product').value.trim();
      await loadTemplate();
      S.note = '';
      drawWork(); refresh();
    }
  });

  // inserted like typing, so Ctrl+Z takes a clicked placeholder or phrase back out (and Ctrl+Y puts it back)
  function insert(textarea, text) {
    const start = textarea.selectionStart, end = textarea.selectionEnd;
    textarea.focus();
    textarea.setSelectionRange(start, end);
    if (!document.execCommand('insertText', false, text)) {       // (fires 'input' itself)
      textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
      textarea.selectionStart = textarea.selectionEnd = start + text.length;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  async function copy(text, button) {
    try { await navigator.clipboard.writeText(text); } catch (err) {
      const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select();
      document.execCommand('copy'); t.remove();
    }
    if (button) { const old = button.textContent; button.textContent = 'Copied'; setTimeout(() => { button.textContent = old; }, 1200); }
  }

  el.addEventListener('click', async e => {
    const tag = e.target.closest('[data-group]');
    if (tag) {                                            // – -> Q -> C -> –
      e.preventDefault();                                 // (it's inside the defect's label: don't tick it)
      const next = { '': 'quality', quality: 'condition', condition: '' }[groupOf(tag.dataset.group)];
      S.state.groups = await call('remarks', 'set_group', tag.dataset.group, next);
      tag.outerHTML = groupTag(tag.dataset.group);
      refresh();
      return;
    }
    const ph = e.target.closest('[data-ph]');
    if (ph) return insert(el.querySelector('#rm-remark'), ph.dataset.ph);
    const bph = e.target.closest('[data-bph]');
    if (bph) return insert(el.querySelector('#rm-box'), bph.dataset.bph);
    const phrase = e.target.closest('[data-phrase]');
    if (phrase) {
      const area = el.querySelector('#' + (S.target || 'rm-remark'));
      const text = S.state.phrases[+phrase.dataset.phrase];
      const before = area.value.slice(0, area.selectionStart), after = area.value.slice(area.selectionEnd);
      // a space before and after it when needed
      return insert(area, (before && !/\s$/.test(before) ? ' ' : '') + text + (after && !/^\s/.test(after) ? ' ' : ''));
    }
    const a = e.target.closest('[data-a]');
    if (!a) { if (e.target.closest('#rm-paste') && !e.target.closest('input')) pasteEl.focus(); return; }
    const act = a.dataset.a;
    if (act === 'clear') { S.report = null; S.out = null; call('remarks', 'clear'); drawPaste(); drawWork(); pasteEl.focus(); }
    else if (act === 'copy') copy(S.out ? S.out.text : '', a);
    else if (act === 'copy-line') copy(S.out.boxes[+a.dataset.i], a);
    else if (act === 'copy-boxes') copy(S.out.boxes.join('\n'), a);
    else if (act === 'reset') { await loadTemplate(); S.note = ''; drawWork(); refresh(); }
    else if (act === 'save') save();
    else if (act === 'placeholders') openPlaceholders();
    else if (act === 'phrases') openPhrases();
    else if (act === 'save-groups') {
      if (!(await needKey())) return;
      S.note = 'Saving the groups…'; drawOut();
      const result = await call('remarks', 'save_groups');
      S.note = result.ok ? 'Quality / Condition groups saved for everyone.' : result.error;
      if (result.ok) S.state = result.state;
      drawOut(); drawSource();
    }
  });

  // ---------------------------------------------------------------- placeholders (admin)
  async function needKey() {
    if (S.state && S.state.editor) return true;
    const state = await dqs.askKey('Templates key', 'Changing this for everyone needs the templates key. It\'s asked once on this PC.',
      'Templates key', 'Continue', key => call('remarks', 'editor_key', key));
    if (state) S.state = state;
    return !!state;
  }

  function openPhrases() {
    const s = S.state;
    if (!s) return;
    const box = document.createElement('div');
    box.className = 'scrim';
    box.innerHTML = `<div class="modal rm-holders">
      <div class="modal-title">Phrases</div>
      <div class="modal-text">One phrase per line. They show under the template and are added where the cursor is with a click.
        They can use placeholders ([date], [varieties]...). Saved for everyone; needs the templates key.</div>
      <textarea class="field rm-text" id="rm-phrase-list" spellcheck="false" style="min-height:300px">${esc((s.phrases || []).join('\n'))}</textarea>
      <div class="modal-error" hidden></div>
      <div class="modal-buttons"><button class="btn ghost" data-h="cancel">Cancel</button><button class="btn primary" data-h="save">Save for everyone</button></div></div>`;
    el.appendChild(box);
    box.querySelector('textarea').focus();
    box.addEventListener('click', async e => {
      if (e.target === box || e.target.dataset.h === 'cancel') return box.remove();
      if (e.target.dataset.h !== 'save') return;
      const list = box.querySelector('textarea').value.split('\n').map(l => l.trim()).filter(Boolean);
      if (!(await needKey())) return;
      e.target.textContent = 'Saving…';
      const result = await call('remarks', 'save_phrases', list);
      if (!result.ok) {
        e.target.textContent = 'Save for everyone';
        const err = box.querySelector('.modal-error'); err.textContent = result.error; err.hidden = false;
        return;
      }
      S.state = result.state;
      box.remove();
      drawSource();
      if (S.report) { S.note = 'Phrases saved for everyone.'; drawWork(); refresh(); }
    });
  }

  function openPlaceholders() {
    const s = S.state;
    if (!s) return;
    const box = document.createElement('div');
    box.className = 'scrim';
    const builtIn = { ...s.built_in, ...s.built_in_box };
    const row = (name, text, help) => `<div class="rm-custom">
        <input class="field" data-f="name" value="${esc(name)}" placeholder="name">
        <input class="field" data-f="text" value="${esc(text)}" placeholder="text, can use others: [package] [box type] boxes">
        <input class="field" data-f="help" value="${esc(help)}" placeholder="what it is (shown as help)">
        <span class="x" data-x="1" title="Remove">×</span></div>`;
    box.innerHTML = `<div class="modal rm-holders">
      <div class="modal-title">Placeholders</div>
      <div class="modal-text">What each placeholder means (shown when pointing at it) and your own placeholders, made of text and
        other placeholders. Saved for everyone; needs the templates key.</div>
      <div class="label-up">Built in</div>
      <div class="rm-builtin">${Object.entries(builtIn).map(([k, v]) => `<div class="rm-bi"><span class="rm-ph">[${esc(k)}]</span>
        <input class="field" data-k="${esc(k)}" value="${esc((s.meaning || {})[k] || v)}" placeholder="${esc(v)}"></div>`).join('')}</div>
      <div class="label-up" style="margin-top:12px">Your own</div>
      <div class="rm-customs">${Object.entries(s.custom || {}).map(([k, c]) => row(k, c.text, c.help)).join('')}</div>
      <div><button class="btn btn-small" data-h="add">+ Add a placeholder</button></div>
      <div class="modal-error" hidden></div>
      <div class="modal-buttons"><button class="btn ghost" data-h="cancel">Cancel</button><button class="btn primary" data-h="save">Save for everyone</button></div></div>`;
    el.appendChild(box);
    const close = () => box.remove();
    box.addEventListener('click', async e => {
      if (e.target === box || e.target.dataset.h === 'cancel') return close();
      if (e.target.dataset.x) return e.target.closest('.rm-custom').remove();
      if (e.target.dataset.h === 'add') {
        box.querySelector('.rm-customs').insertAdjacentHTML('beforeend', row('', '', ''));
        box.querySelector('.rm-custom:last-child [data-f=name]').focus();
        return;
      }
      if (e.target.dataset.h !== 'save') return;
      const meaning = {};
      box.querySelectorAll('[data-k]').forEach(i => { meaning[i.dataset.k] = i.value.trim(); });
      const custom = {};
      box.querySelectorAll('.rm-custom').forEach(r => {
        const name = r.querySelector('[data-f=name]').value.replace(/[[\]]/g, '').trim();
        const text = r.querySelector('[data-f=text]').value.trim();
        if (name && text) custom[name] = { text, help: r.querySelector('[data-f=help]').value.trim() };
      });
      if (!(await needKey())) return;
      e.target.textContent = 'Saving…';
      const result = await call('remarks', 'save_placeholders', meaning, custom);
      if (!result.ok) {
        e.target.textContent = 'Save for everyone';
        const err = box.querySelector('.modal-error'); err.textContent = result.error; err.hidden = false;
        return;
      }
      S.state = result.state;
      close();
      drawSource();
      if (S.report) { S.note = 'Placeholders saved for everyone.'; drawWork(); refresh(); }
    });
  }

  async function save() {
    if (!S.state || !S.state.editor) {
      const state = await dqs.askKey('Templates key', 'Changing the template for everyone needs the templates key. It\'s asked once on this PC.',
        'Templates key', 'Continue', key => call('remarks', 'editor_key', key));
      if (!state) return;
      S.state = state;
    }
    const client = S.client || '*', product = S.product || '*';
    const scope = await chooseScope(client, product);
    if (!scope) return;
    S.note = 'Saving…'; drawOut();
    const result = await call('remarks', 'save_default', scope[0], scope[1], S.remark, S.box);
    S.note = result.ok ? `Saved: everyone now gets this template for ${scope[0] === '*' ? 'any client' : scope[0]} · ${scope[1] === '*' ? 'any product' : scope[1]}.` : result.error;
    if (result.ok) { S.state = result.state; await loadTemplate(); drawWork(); refresh(); } else drawOut();
    drawSource();
  }

  function chooseScope(client, product) {
    return new Promise(resolve => {
      const opts = [[client, product, `${client} · ${product}`], [client, '*', `${client} · any product`], ['*', '*', 'The default (any client, any product)']]
        .filter(([c, p], i, all) => (i === 0 || c !== all[0][0] || p !== all[0][1]) && !(i < 2 && c === '*'));
      const choice = opts.map((o, i) => `<label class="rm-scope"><input type="radio" name="rm-scope" value="${i}"${i === 0 ? ' checked' : ''}> ${esc(o[2])}</label>`).join('');
      let picked = 0;
      dqs.confirm('Save as everyone\'s template', '', 'Save').then(ok => resolve(ok ? opts[picked] : null));
      const text = document.querySelector('#modal-root .modal-text');
      if (text) {
        text.innerHTML = `Everyone using DQS Apps will get this template (and its box line) for:<div style="display:flex;flex-direction:column;gap:6px;margin-top:10px">${choice}</div>`;
        text.addEventListener('change', e => { if (e.target.name === 'rm-scope') picked = +e.target.value; });
      }
    });
  }

  // ---------------------------------------------------------------- templates
  function drawSource() {
    const s = S.state;
    if (!s) return;
    sourceEl.textContent = `Templates: ${s.source}${s.saved ? ` (saved ${s.saved})` : ''}${s.editor ? ' · templates key on this PC' : ''}`;
  }
  // the shared templates arrived: show them, unless the person is already editing the one on screen
  on('remarks.templates', state => { S.state = state; drawSource(); if (S.report && !S.edited) { loadTemplate().then(() => { drawWork(); refresh(); }); } });
  call('remarks', 'state').then(state => { S.state = state; drawSource(); if (S.report) drawWork(); });

  drawPaste();
});
