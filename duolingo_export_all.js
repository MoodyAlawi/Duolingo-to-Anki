/* ============================================================================
 * Duolingo — export the COMPLETE vocabulary list (all lexemes, not just the
 * few pages your browser happened to load).
 *
 * HOW TO USE
 *   1. Open https://www.duolingo.com and make sure you are logged in.
 *   2. Open the Words page once: /practice-hub/words
 *      (this is what lets the script learn your exact request credentials).
 *   3. Press F12 -> Console tab.
 *   4. Paste this entire file into the Console and press Enter.
 *   5. A banner appears in the top-right corner showing live progress.
 *      Wait ~30-90 seconds.
 *   6. Two files download:
 *          duolingo_words_full.csv   (German, English, Notes, Source_URL)
 *          duolingo_words_full.json
 *
 * PRIVACY
 *   - Everything runs locally in your own browser tab.
 *   - Your session token is read locally and used only in request headers.
 *     It is NEVER printed to the console, never written to the output files,
 *     and never sent anywhere except Duolingo itself (the same endpoint the
 *     website already calls).
 *   - Requests are rate-limited to be gentle on the server.
 *   - Close the tab or press Ctrl+C to abort at any time.
 * ==========================================================================*/

(async () => {
  'use strict';

  const DELAY_MS  = 250;    // pause between requests
  const PAGE_SIZE = 50;     // the API caps page size at 50; ask for exactly that
  const OUT_CSV   = 'duolingo_words_full.csv';
  const OUT_JSON  = 'duolingo_words_full.json';
  const SAFE_BASE_PLACEHOLDER = '{user_id}';

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  if (location.hostname !== 'www.duolingo.com') {
    console.warn('[duo] Run this on https://www.duolingo.com while logged in.');
    return;
  }

  // ------------------------------------------------------------- on-page UI
  const banner = document.createElement('div');
  banner.style.cssText = [
    'position:fixed', 'top:12px', 'right:12px', 'z-index:2147483647',
    'background:#111', 'color:#fff', 'font:12px/1.5 monospace',
    'padding:10px 14px', 'border-radius:8px', 'max-width:420px',
    'white-space:pre-wrap', 'box-shadow:0 4px 16px rgba(0,0,0,.4)',
  ].join(';');
  banner.textContent = '[duo] starting...';
  document.body.appendChild(banner);

  const setBanner = (text, bg) => {
    banner.textContent = '[duo] ' + text;
    if (bg) banner.style.background = bg;
  };
  const log = (...args) => {
    console.log('[duo]', ...args);
    setBanner(args.map((a) => (typeof a === 'string' ? a : JSON.stringify(a))).join(' '));
  };

  // ------------------------------------------------------- context discovery
  function detectContext() {
    const urls = performance.getEntriesByType('resource').map((e) => e.name);
    let uid = null, learning = null, from = null;
    for (const u of urls) {
      const m = u.match(/\/users\/(\d+)\/courses\/([^/]+)\/([^/]+)\/learned-lexemes/);
      if (m) { uid = m[1]; learning = m[2]; from = m[3]; break; }
    }
    if (!uid) {
      for (const u of urls) { const m = u.match(/\/users\/(\d+)\//); if (m) { uid = m[1]; break; } }
    }
    return { uid, learning, from };
  }

  const ctx = detectContext();
  if (!ctx.uid) {
    ctx.uid = window.prompt(
      'Duolingo user id (the number in DevTools > Network > any /users/<number>/ request):');
  }
  if (!ctx.learning) ctx.learning = window.prompt('Learning language code (e.g. de):', 'de');
  if (!ctx.from) ctx.from = window.prompt('From language code (e.g. en):', 'en');
  if (!ctx.uid || !ctx.learning || !ctx.from) {
    log('missing user id / language codes. Aborting.');
    return;
  }

  const BASE = `https://www.duolingo.com/2017-06-30/users/${ctx.uid}/courses/${ctx.learning}/${ctx.from}`;
  const SAFE_BASE = `https://www.duolingo.com/2017-06-30/users/${SAFE_BASE_PLACEHOLDER}/courses/${ctx.learning}/${ctx.from}`;
  log(`user=${ctx.uid} course=${ctx.learning}/${ctx.from}`);

  // ---------------------------------------------------------- token discovery
  const JWT_RE = /^eyJ[\w-]+\.[\w-]+\.[\w-]+$/;

  function tokenFromCookie() {
    const m = document.cookie.match(/(?:^|;\s*)jwt_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }

  function tokenFromStorage() {
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        const val = localStorage.getItem(key);
        if (typeof val !== 'string') continue;
        if (JWT_RE.test(val)) return val;
        if (val.startsWith('{') || val.startsWith('"')) {
          try {
            const parsed = JSON.parse(val);
            const found = deepFindJwt(parsed, 0);
            if (found) return found;
          } catch (_) { /* not JSON */ }
        }
      }
    } catch (_) { /* storage blocked */ }
    return null;
  }

  function deepFindJwt(node, depth) {
    if (depth > 4 || node == null) return null;
    if (typeof node === 'string') return JWT_RE.test(node) ? node : null;
    if (typeof node === 'object') {
      for (const k of Object.keys(node)) {
        const r = deepFindJwt(node[k], depth + 1);
        if (r) return r;
      }
    }
    return null;
  }

  const cookieToken = tokenFromCookie();
  const storageToken = cookieToken ? null : tokenFromStorage();
  const localToken = cookieToken || storageToken;
  console.log(`[duo] token found in cookie: ${!!cookieToken}, in localStorage: ${!!storageToken}`);

  // -------------------------------------------------- capture site's own call
  // The website already issues this exact request successfully. Rather than
  // guess the credential format, we wait for the site to make one and copy
  // its headers and body verbatim.
  const captured = { auth: null, body: null, method: null };

  function startInterceptors() {
    const origFetch = window.fetch;
    window.fetch = function (input, init) {
      try {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (url.includes('/learned-lexemes')) {
          let auth = null;
          const h = (init && init.headers) || (input instanceof Request ? input.headers : null);
          if (h) auth = typeof h.get === 'function' ? h.get('Authorization') : (h.Authorization || h.authorization);
          if (auth) {
            captured.auth = auth;
            if (init && typeof init.body === 'string') captured.body = init.body;
            captured.method = (init && init.method) || 'POST';
          }
        }
      } catch (_) { /* never break the page */ }
      return origFetch.apply(this, arguments);
    };

    const origOpen = XMLHttpRequest.prototype.open;
    const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
    const origSend = XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function (method, url) {
      try {
        this.__duoUrl = String(url || '');
        this.__duoMethod = method;
        this.__duoAuth = null;
      } catch (_) {}
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
      try {
        if (String(name).toLowerCase() === 'authorization') this.__duoAuth = value;
      } catch (_) {}
      return origSetHeader.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (body) {
      try {
        if (this.__duoUrl && this.__duoUrl.includes('/learned-lexemes') && this.__duoAuth) {
          captured.auth = this.__duoAuth;
          if (typeof body === 'string') captured.body = body;
          captured.method = this.__duoMethod || 'POST';
        }
      } catch (_) {}
      return origSend.apply(this, arguments);
    };

    return () => {
      window.fetch = origFetch;
      XMLHttpRequest.prototype.open = origOpen;
      XMLHttpRequest.prototype.setRequestHeader = origSetHeader;
      XMLHttpRequest.prototype.send = origSend;
    };
  }

  // ------------------------------------------------------------ HTTP helper
  const DEFAULT_BODY = JSON.stringify({ lastTotalLexemeCount: 0, progressedSkills: [] });

  function buildInit(auth, body, method) {
    const headers = {
      'Accept': 'application/json; charset=UTF-8',
      'X-Requested-With': 'XMLHttpRequest',
    };
    const init = { method, headers, credentials: 'include' };
    if (method === 'POST') {
      headers['Content-Type'] = 'application/json; charset=UTF-8';
      if (body != null) init.body = body;
    }
    if (auth) headers['Authorization'] = auth;
    return init;
  }

  function lexemeUrl(startIndex, limit, kind) {
    const query = kind === 'practice'
      ? '' : `?limit=${limit}&sortBy=LEARNED_DATE&startIndex=${startIndex}`;
    return `${BASE}/${kind}-lexemes${query}`;
  }

  async function callLexemes(auth, body, method, startIndex, limit, kind) {
    return fetch(lexemeUrl(startIndex, limit, kind), buildInit(auth, body, method));
  }

  async function probe(auth, body, label) {
    let res;
    try {
      res = await callLexemes(auth, body, 'POST', 0, 50, 'learned');
    } catch (err) {
      console.log(`[duo] ${label} -> network error: ${err.message}`);
      return null;
    }
    if (!res.ok) {
      console.log(`[duo] ${label} -> HTTP ${res.status}`);
      return null;
    }
    let payload;
    try { payload = await res.json(); } catch (_) {
      console.log(`[duo] ${label} -> HTTP ${res.status} but body was not JSON`);
      return null;
    }
    const usable = Array.isArray(payload.learnedLexemes) && payload.learnedLexemes.length > 0;
    console.log(`[duo] ${label} -> HTTP ${res.status} ${usable ? 'OK' : 'no lexemes'}`);
    return usable ? payload : null;
  }

  // -------------------------------------------------------- resolve auth path
  let auth = null, bodyTemplate = DEFAULT_BODY, firstPage = null;

  // 1) plain cookie auth (the browser attaches the session automatically)
  firstPage = await probe(null, DEFAULT_BODY, 'POST + cookies');
  if (firstPage) {
    log('authenticated with cookies');
  }

  // 2) explicit token from cookie / localStorage
  if (!firstPage && localToken) {
    auth = 'Bearer ' + localToken;
    firstPage = await probe(auth, DEFAULT_BODY, 'POST + local token');
    if (firstPage) log('authenticated with local token');
  }

  // 3) copy the website's own request verbatim
  if (!firstPage) {
    log('direct auth failed - capturing the site\'s own request.\n' +
        'ACTION: open /practice-hub/words (or scroll it) so the site calls\n' +
        'the learned-lexemes endpoint once.');
    const stop = startInterceptors();
    const deadline = Date.now() + 90000;
    while (Date.now() < deadline && !captured.auth) await sleep(200);
    stop();

    if (captured.auth) {
      console.log('[duo] captured site Authorization header (value withheld)');
      auth = captured.auth;
      if (captured.body) bodyTemplate = captured.body;
      firstPage = await probe(auth, bodyTemplate, 'POST + captured site request');
      if (firstPage) log('authenticated using captured site request');
    } else {
      console.warn('[duo] no site request captured within 90s');
    }
  }

  if (!firstPage) {
    setBanner('FAILED: could not authenticate.\nSee console for details.', '#7f1d1d');
    console.error(
      '[duo] Could not authenticate to the lexemes endpoint.\n' +
      'Everything was tried: cookies, bearer token, and replaying the site\'s own\n' +
      'request. Please send the "[duo] ..." lines from the console to diagnose.');
    return;
  }

  // ------------------------------------------------------------------ paging
  async function collect(kind, seed) {
    const records = [];
    let total = null;
    let limit = PAGE_SIZE;
    let start = 0;
    let pageSizeSeen = null;
    const paginated = kind !== 'practice';

    const seedBucket = seed && seed[`${kind}Lexemes`];
    if (Array.isArray(seedBucket) && seedBucket.length) {
      const pag = seed.pagination || {};
      if (typeof pag.totalLexemes === 'number') total = pag.totalLexemes;
      if (pag.pageSize) { pageSizeSeen = pag.pageSize; limit = pag.pageSize; }
      for (const r of seedBucket) records.push({ ...r, __kind: kind, __url: `${SAFE_BASE}/${kind}-lexemes` });
      start = pageSizeSeen || seedBucket.length;
      if (!paginated || (typeof total === 'number' && start >= total)) {
        log(`${kind}: ${records.length}${total ? ' of ' + total : ''} records`);
        return { records, total };
      }
    }

    while (true) {
      let res;
      try {
        res = await callLexemes(auth, bodyTemplate, 'POST', start, limit, kind);
      } catch (err) {
        console.warn(`[duo] ${kind} network error: ${err.message}`);
        break;
      }
      if (!res.ok) {
        console.warn(`[duo] ${kind} HTTP ${res.status} at startIndex=${start} - stopping.`);
        break;
      }
      let payload;
      try { payload = await res.json(); } catch (_) { break; }

      const bucket = payload[`${kind}Lexemes`] || [];
      const pag = payload.pagination || {};
      if (typeof pag.totalLexemes === 'number') total = pag.totalLexemes;
      if (pag.pageSize) { pageSizeSeen = pag.pageSize; limit = pag.pageSize; }
      if (!bucket.length) break;

      for (const r of bucket) records.push({ ...r, __kind: kind, __url: `${SAFE_BASE}/${kind}-lexemes` });

      if (!paginated) break;
      start += (pageSizeSeen || bucket.length);
      if (typeof total === 'number' && start >= total) break;
      if (start > 200000) break;

      setBanner(`fetching ${kind}: ${records.length}${total ? ' / ' + total : ''} words...`);
      await sleep(DELAY_MS);
    }
    log(`${kind}: ${records.length}${total ? ' of ' + total : ''} records`);
    return { records, total };
  }

  setBanner('fetching vocabulary...');
  const learned = await collect('learned', firstPage);
  await sleep(DELAY_MS);
  const practice = await collect('practice', null);

  // --------------------------------------------------------------- normalise
  const merged = new Map();
  let rawCount = 0;

  for (const r of [...learned.records, ...practice.records]) {
    const german = (r.text || r.word || '').trim();
    if (!german) continue;
    rawCount++;
    let trans = r.translations || (r.translation ? [r.translation] : []);
    if (!Array.isArray(trans)) trans = [trans];
    trans = trans.map((t) =>
      typeof t === 'string' ? t.trim()
        : String((t && (t.translation || t.text || t.meaning)) || '').trim()
    ).filter(Boolean);

    const key = german.toLocaleLowerCase('de');
    if (merged.has(key)) {
      const cur = merged.get(key);
      for (const t of trans) if (!cur.english.includes(t)) cur.english.push(t);
    } else {
      merged.set(key, { german, english: trans, notes: '', url: r.__url || SAFE_BASE });
    }
  }

  const rows = [...merged.values()].sort((a, b) =>
    a.german.localeCompare(b.german, 'de', { sensitivity: 'base' }));

  // ----------------------------------------------------------------- outputs
  const csvCell = (v) => {
    const s = String(v == null ? '' : v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const download = (name, text, mime) => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: mime }));
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  };

  const csv = '\uFEFF' + 'German,English,Notes,Source_URL\r\n' +
    rows.map((r) => [r.german, r.english.join(', '), r.notes, r.url].map(csvCell).join(',')).join('\r\n') + '\r\n';
  const json = JSON.stringify(
    rows.map((r) => ({ german: r.german, english: r.english, notes: r.notes, source_url: r.url })), null, 2) + '\n';

  download(OUT_CSV, csv, 'text/csv;charset=utf-8');
  download(OUT_JSON, json, 'application/json;charset=utf-8');

  const duplicates = rawCount - rows.length;
  const declared = learned.total;
  const shortfall = declared && learned.records.length < declared
    ? `\nWARNING: got ${learned.records.length} of ${declared} lexemes`
    : '';
  log(
    `DONE\nraw records      : ${rawCount}\nduplicates merged: ${duplicates}\n` +
    `unique words     : ${rows.length}\nAPI total        : ${declared}${shortfall}\n` +
    `wrote ${OUT_CSV} + ${OUT_JSON}`,
    shortfall ? '#7c2d12' : '#14532d'
  );

  window.__duoExport = { rows, rawCount, duplicates, declared };
  return window.__duoExport;
})();
