/* The window: sidebar, moving between apps, messages from Python, update card and unlock modal. */
const dqs = (() => {
  const handlers = {};
  const views = {};           // id -> {el, onDrop, onShow, onKey}
  let current = null;
  const main = document.getElementById('main');

  const ready = new Promise(resolve => {
    if (window.pywebview && window.pywebview.api) resolve();
    else window.addEventListener('pywebviewready', () => resolve());
  });

  const esc = text => String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // what Python says, from any of its threads (see Host.emit)
  const on = (event, fn) => { handlers[event] = fn; };
  const emit = (event, payload) => { if (handlers[event]) handlers[event](payload); };

  // call Python: await dqs.call('price', 'add', paths, known)
  const call = async (part, method, ...args) => {
    await ready;
    return window.pywebview.api[part][method](...args);
  };

  // ---------------------------------------------------------------- moving between apps
  function addView(id, nav, build) {
    const el = document.createElement('div');
    el.className = 'view';
    el.id = 'view-' + id;
    el.hidden = true;
    main.appendChild(el);
    views[id] = { el, nav };
    build(el, views[id]);
    drawNav();
    return views[id];
  }

  function show(id) {
    if (current === id) return;
    current = id;
    for (const [key, view] of Object.entries(views)) view.el.hidden = key !== id;
    main.scrollTop = main.scrollLeft = 0;
    drawNav();
    if (views[id].onShow) views[id].onShow();
  }

  // the app DQS Apps opens on: the filled star (one at a time), kept in the settings file
  const STAR = '<svg viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 3.5l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.8l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z"/></svg>';
  let startApp = '';
  call('shell', 'start').then(id => { startApp = id || ''; if (startApp && views[startApp]) show(startApp); drawNav(); });

  function drawNav() {
    const item = (id, v) => `<div class="nav-item${id === current ? ' on' : ''}" data-go="${esc(id)}">
      <div class="chip">${v.nav.icon || esc(v.nav.code)}</div>
      <div class="nav-text"><div class="nav-title ellipsis">${esc(v.nav.title)}</div><div class="nav-sub ellipsis">${esc(v.nav.sub)}</div></div>
      <div class="nav-star${id === startApp ? ' on' : ''}" data-star="${esc(id)}" title="${id === startApp ? 'DQS Apps opens on this app (click to undo)' : 'Open DQS Apps on this app'}">${STAR}</div></div>`;
    const entries = Object.entries(views);
    document.getElementById('nav').innerHTML = entries.filter(([, v]) => !v.nav.private).map(([id, v]) => item(id, v)).join('');
    document.getElementById('nav-private').innerHTML = entries.filter(([, v]) => v.nav.private).map(([id, v]) => item(id, v)).join('');
  }

  // ---------------------------------------------------------------- modals
  const modalRoot = document.getElementById('modal-root');
  let modal = null;         // {close}

  function openModal(html, close) {
    modalRoot.innerHTML = `<div class="scrim">${html}</div>`;
    modal = { close };
    return modalRoot.firstElementChild;
  }

  function closeModal() {
    modalRoot.innerHTML = '';
    modal = null;
  }

  // an in-window yes/no: if (await dqs.confirm('Text', 'Count again')) ...
  function confirm(title, text, okLabel) {
    return new Promise(resolve => {
      const finish = value => { closeModal(); resolve(value); };
      const scrim = openModal(`<div class="modal"><div class="modal-title">${esc(title)}</div><div class="modal-text">${esc(text)}</div>
        <div class="modal-buttons"><button class="btn ghost" data-act="no">Cancel</button><button class="btn primary" data-act="yes">${esc(okLabel)}</button></div></div>`, () => finish(false));
      scrim.addEventListener('click', e => {
        if (e.target === scrim || e.target.dataset.act === 'no') finish(false);
        else if (e.target.dataset.act === 'yes') finish(true);
      });
      modal.submit = () => finish(true);
      scrim.querySelector('[data-act=yes]').focus();
    });
  }

  // asks for a key; check(key) resolves to something truthy when it's right. Resolves to that, or null if cancelled.
  function askKey(title, text, placeholder, okLabel, check) {
    return new Promise(resolve => {
      let done = false;
      const finish = result => { if (!done) { done = true; resolve(result); } };
      const scrim = openModal(`<div class="modal"><div class="modal-title">${esc(title)}</div>
        <div class="modal-text">${esc(text)}</div>
        <input type="password" placeholder="${esc(placeholder)}" autocomplete="off">
        <div class="modal-error" hidden>That key isn't correct.</div>
        <div class="modal-buttons"><button class="btn ghost" data-act="cancel">Cancel</button><button class="btn primary" data-act="ok">${esc(okLabel)}</button></div></div>`,
        () => { closeModal(); finish(null); });
      const input = scrim.querySelector('input');
      const error = scrim.querySelector('.modal-error');
      const button = scrim.querySelector('[data-act=ok]');
      let checking = false;

      const submit = async () => {
        if (checking || !input.value.trim()) return;
        checking = true;
        error.hidden = true;
        button.textContent = 'Checking…';
        const result = await check(input.value);
        checking = false;
        if (!modalRoot.contains(button)) { finish(result || null); return; }   // closed while checking
        button.textContent = okLabel;
        if (!result) {
          error.hidden = false;
          input.value = '';
          input.focus();
          return;
        }
        closeModal();
        finish(result);
      };
      modal.submit = submit;
      input.addEventListener('input', () => { error.hidden = true; });
      scrim.addEventListener('click', e => {
        if (e.target === scrim || e.target.dataset.act === 'cancel') { closeModal(); finish(null); }
        else if (e.target.dataset.act === 'ok') submit();
      });
      input.focus();
    });
  }

  async function openUnlock() {
    const screens = await askKey('Unlock more apps', "Private apps open with the team's secret key. Ask the maintainer if you need it.",
      'Secret key', 'Unlock', key => call('private', 'unlock', key));
    if (screens) showPrivate(screens);
  }

  // a PC that unlocked them before opens them straight away (the key is kept in its settings)
  call('private', 'remembered').then(screens => { if (screens) showPrivate(screens, true); });

  function showPrivate(screens, remembered) {
    document.getElementById('unlock-item').hidden = true;
    for (const screen of screens) {
      addView(screen.id, { code: screen.code, icon: dqs.icons[screen.icon] || '', title: screen.title, sub: screen.sub, private: true }, (el, view) => {
        el.innerHTML = screen.html;
        if (screen.js) {
          const app = { call: (method, ...args) => call('private', 'call', screen.id, method, args) };
          new Function('view', 'app', 'dqs', 'hooks', screen.js)(el, app, api, view);
        }
      });
    }
    // typed the key: open the first one; remembered at start-up: only if it's the starred app
    if (remembered) { if (screens.some(s => s.id === startApp)) show(startApp); }
    else if (screens.length) show(screens[0].id);
  }

  // ---------------------------------------------------------------- update card
  const card = document.getElementById('update-card');
  let update = null;

  function drawUpdate() {
    if (!update || update.hidden) { card.hidden = true; return; }
    card.hidden = false;
    let bottom;
    if (update.downloading) {
      bottom = `<div class="update-bar"><div style="width:${update.pct}%"></div></div><div class="small muted">Downloading… ${update.pct}%</div>`;
    } else {
      bottom = `${update.error ? `<div class="small" style="color:var(--bad)">${esc(update.error)}</div>` : ''}
        <div class="update-buttons"><button class="btn primary" data-act="update-now">Update now</button><button class="btn ghost" data-act="update-later">Later</button></div>`;
    }
    card.innerHTML = `<div class="update-head"><div class="update-dot"></div><div>Version ${esc(update.version)} is ready</div></div>
      <div class="update-notes">${esc(update.notes)} The app restarts after updating.</div>${bottom}`;
  }

  on('update.available', info => { update = { ...info, pct: 0 }; drawUpdate(); });
  on('update.progress', pct => { if (update) { update.pct = pct; drawUpdate(); } });
  on('update.error', message => { update.downloading = false; update.error = message; drawUpdate(); });

  // ---------------------------------------------------------------- clicks, keys, dragging
  document.addEventListener('click', e => {
    const star = e.target.closest('[data-star]');
    if (star) {
      startApp = startApp === star.dataset.star ? '' : star.dataset.star;
      call('shell', 'set_start', startApp);
      drawNav();
      return;
    }
    const go = e.target.closest('[data-go]');
    if (go) return show(go.dataset.go);
    const act = e.target.closest('[data-act]');
    if (!act) return;
    if (act.dataset.act === 'open-unlock') openUnlock();
    else if (act.dataset.act === 'update-now') { update.downloading = true; update.error = ''; update.pct = 0; drawUpdate(); call('updates', 'install'); }
    else if (act.dataset.act === 'update-later') { update.hidden = true; drawUpdate(); }
  });

  document.addEventListener('keydown', e => {
    // this is an app, not a web page: a reload would lose everything on screen
    if (e.key === 'F5' || e.key === 'F3' || e.key === 'F7' || (e.ctrlKey && 'rpfgjsuon'.includes(e.key.toLowerCase()))) {
      e.preventDefault();
      return;
    }
    if (modal) {
      if (e.key === 'Escape') { e.preventDefault(); modal.close(); }
      else if (e.key === 'Enter' && modal.submit) { e.preventDefault(); modal.submit(); }
      return;
    }
    const view = views[current];
    if (view && view.onKey) view.onKey(e);
  });

  document.addEventListener('contextmenu', e => {
    if (!e.target.closest('input, textarea, .selectable')) e.preventDefault();
  });

  // without these Windows would open the dropped file inside the window, instead of giving it to the app
  let depth = 0;
  const isFiles = e => e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files');
  document.addEventListener('dragenter', e => {
    e.preventDefault();
    if (isFiles(e) && ++depth === 1) document.body.classList.add('dragging');
  });
  document.addEventListener('dragleave', e => {
    e.preventDefault();
    if (isFiles(e) && --depth <= 0) { depth = 0; document.body.classList.remove('dragging'); }
  });
  document.addEventListener('dragover', e => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
  });
  document.addEventListener('drop', e => {
    e.preventDefault();
    depth = 0;
    document.body.classList.remove('dragging');
  });
  on('drop', paths => {
    const view = views[current];
    if (!modal && view && view.onDrop && paths.length) view.onDrop(paths);
  });

  const api = { esc, on, emit, call, addView, show, confirm, askKey, views, get current() { return current; } };
  return api;
})();

// the shared parts of the public apps
// sidebar icons (line drawings in the text colour): Loot, Pixie, Harvest, Draft, and the private Vault and Stack
dqs.icons = (() => {
  const svg = body => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
  return {
    loot: svg('<path d="M9 3h6l-1.6 3.2h-2.8z"/><path d="M10.6 6.2C6.3 8.2 4 12 4 15.4 4 19 6.6 21 12 21s8-2 8-5.6c0-3.4-2.3-7.2-6.6-9.2"/><path d="M12 10.2v7.2M14.2 11.6h-3a1.3 1.3 0 0 0 0 2.6h1.6a1.3 1.3 0 0 1 0 2.6H9.8"/>'),
    pixie: svg('<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="9.5" r="1.7"/><path d="M21 15.5l-5-5L7 20"/>'),
    harvest: svg('<path d="M12 7.2c-1.5-1.2-3.6-1.6-5.3-.8C4.4 7.5 3.6 10.2 4.1 13c.7 4 3.3 8 5.9 8 .8 0 1.3-.4 2-.4s1.2.4 2 .4c2.6 0 5.2-4 5.9-8 .5-2.8-.3-5.5-2.6-6.6-1.7-.8-3.8-.4-5.3.8z"/><path d="M12 7.2c0-2 .9-3.6 3-4.4"/><path d="M12.8 5.2c1.2-1.6 3-1.9 4.4-1.2-.6 1.6-2.2 2.4-4.4 1.2z"/>'),
    vault: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6M9 9h2"/>'),
    stack: svg('<path d="M10 6h10M10 12h10M10 18h10"/><path d="M4 4.5l1.5-1V9"/><path d="M4 14a1.5 1.5 0 0 1 3 .2c0 1.3-3 2.3-3 3.8h3"/>'),
    draft: svg('<path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6"/><path d="M8 9h4M8 13h3M8 17h7"/><path d="M18.4 2.6a2 2 0 0 1 2.9 2.9L14 12.8l-3.6.9.9-3.6z"/>'),
  };
})();
dqs.plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
dqs.shortPath = path => {
  const parts = String(path).split(/[\\/]/).filter(Boolean);
  return parts.length > 2 ? parts.slice(-2).join('\\') : String(path);
};
