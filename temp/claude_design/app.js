/* ============================================================
   SQL Console — interactivity
   ============================================================ */

const $  = (s, r=document) => r.querySelector(s);
const $$ = (s, r=document) => [...r.querySelectorAll(s)];

const state = {
  selectedFabs: new Set(window.FABS),
  rownum: 100,
  scenario: 'cpnt_by_name',
  params: { cpnt_name: 'PCM_QUERY_V2' },
  view: 'flat',           // flat | pivot
  diffOn: true,
  diffPanelOpen: false,
  bannerOpen: true,
  search: '',
  // chip state per fab: { status: 'pend'|'run'|'ok'|'err', rows: number, ms: number }
  chipState: {},
  streaming: false,
  // column filters: { colKey: Set(values) }  — empty Set means "all"
  colFilters: {},
  openFilterCol: null,
};

// initialize chip state from RESULTS as "complete"
function setChipsComplete() {
  state.chipState = {};
  window.RESULTS.forEach(r => {
    state.chipState[r.fab] = {
      status: r.status,
      rows: r.status === 'ok' ? 1 : 0,
      ms: 180 + Math.floor(Math.random() * 1400),
      error: r.error,
    };
  });
}
function setChipsPending() {
  state.chipState = {};
  window.FABS.forEach(f => {
    state.chipState[f] = { status: 'pend', rows: 0, ms: 0 };
  });
}

/* ---------------- helpers ---------------- */
const okRows  = () => window.RESULTS.filter(r => state.selectedFabs.has(r.fab) && r.status === 'ok'
  && state.chipState[r.fab] && state.chipState[r.fab].status === 'ok');
const errRows = () => window.RESULTS.filter(r => state.selectedFabs.has(r.fab) && r.status === 'err'
  && state.chipState[r.fab] && state.chipState[r.fab].status === 'err');
const allRows = () => window.RESULTS.filter(r => state.selectedFabs.has(r.fab)
  && state.chipState[r.fab] && (state.chipState[r.fab].status === 'ok' || state.chipState[r.fab].status === 'err'));

function diffColumns() {
  const rows = okRows();
  const diff = new Set();
  window.COLUMNS.forEach(col => {
    const s = new Set(rows.map(r => String(r.data[col.k])));
    if (s.size > 1) diff.add(col.k);
  });
  return diff;
}

function fmtVal(v) {
  if (v === null || v === undefined || v === '') return '<span class="null">∅ null</span>';
  return String(v);
}

function pillFor(col, v) {
  if (col === 'enabled') {
    if (v === 'Y') return `<span class="pill ok">Y · enabled</span>`;
    if (v === 'N') return `<span class="pill bad">N · disabled</span>`;
  }
  if (col === 'auth_mode') {
    if (v === 'OAUTH2') return `<span class="pill ok">${v}</span>`;
    if (v === 'BASIC')  return `<span class="pill warn">${v}</span>`;
  }
  return null;
}

/* ---------------- per-fab SSE indicator (rendered inside FAB cells) ---------------- */
function fabCellHtml(fab) {
  const cs = state.chipState[fab] || { status: 'pend', ms: 0 };
  let dotCls = cs.status;
  let timeTxt = '';
  if (cs.status === 'ok' || cs.status === 'err') {
    timeTxt = `<span class="fab-cell-ms">${cs.ms}ms</span>`;
  } else if (cs.status === 'run') {
    timeTxt = `<span class="fab-cell-ms run">streaming…</span>`;
  } else {
    timeTxt = `<span class="fab-cell-ms pend">queued</span>`;
  }
  return `
    <span class="fab-cell-inner">
      <span class="fab-cell-dot ${dotCls}"></span>
      <span class="fab-cell-name">${fab}</span>
      ${timeTxt}
    </span>`;
}

function renderChips() {
  // Chip strip removed — SSE info is now embedded inside FAB cells.
  // Still update the summary numbers in the unified results bar.
  const done = window.FABS.filter(f => {
    const cs = state.chipState[f];
    return cs && (cs.status === 'ok' || cs.status === 'err');
  });
  const maxMs = done.length ? Math.max(...done.map(f => state.chipState[f].ms)) : 0;
  const elEl = $('#chipElapsed'); if (elEl) elEl.textContent = (maxMs/1000).toFixed(2) + 's';
}

/* ---------------- stream simulation ---------------- */
let streamTimer = null;
function startStream() {
  if (streamTimer) clearTimeout(streamTimer);
  setChipsPending();
  state.streaming = true;
  renderChips();
  renderResults();

  const order = [...window.FABS].sort(() => Math.random() - 0.5);
  let idx = 0;

  function step() {
    if (idx >= order.length) {
      state.streaming = false;
      renderChips();
      renderResults();
      return;
    }
    const fab = order[idx];
    // mark running
    state.chipState[fab] = { ...state.chipState[fab], status: 'run' };
    renderChips();

    // resolve after a short delay
    const ms = 200 + Math.floor(Math.random() * 900);
    setTimeout(() => {
      const result = window.RESULTS.find(r => r.fab === fab);
      state.chipState[fab] = {
        status: result.status,
        rows: result.status === 'ok' ? 1 : 0,
        ms,
        error: result.error,
      };
      renderChips();
      renderResults();
    }, ms);

    idx++;
    streamTimer = setTimeout(step, 80 + Math.floor(Math.random() * 220));
  }
  step();
}
window.startStream = startStream;
$('#collapseBtn').addEventListener('click', () => {
  $('#sidebar').classList.toggle('collapsed');
});

/* ---------------- fab dropdown ---------------- */
function fabSummaryText() {
  const sel = [...state.selectedFabs];
  if (sel.length === 0) return 'no fabs selected';
  if (sel.length === window.FABS.length) return 'all fabs';
  const sorted = window.FABS.filter(f => state.selectedFabs.has(f));
  const visible = sorted.slice(0, 4).join(', ');
  return sorted.length > 4 ? `${visible} +${sorted.length - 4}` : visible;
}
function renderFabs() {
  const list = $('#fabList');
  list.innerHTML = window.FABS.map(f => {
    const on = state.selectedFabs.has(f);
    return `<div class="dropdown-item ${on?'on':''}" data-fab="${f}">
      <span class="cb">
        <svg width="9" height="9" viewBox="0 0 9 9" fill="none"><path d="M1.5 4.5 L3.5 6.5 L7.5 2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </span>
      <span class="name">${f}</span>
    </div>`;
  }).join('');
  $('#fabCountSel').textContent = state.selectedFabs.size;
  $('#fabCountTot').textContent = window.FABS.length;
  $('#fabCountPill').textContent = state.selectedFabs.size;
  $('#fabSummary').textContent = fabSummaryText();
  const runMeta = $('#runMetaFabs');
  if (runMeta) runMeta.textContent = `${state.selectedFabs.size} fab${state.selectedFabs.size===1?'':'s'}`;

  list.querySelectorAll('.dropdown-item').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const f = el.dataset.fab;
      if (state.selectedFabs.has(f)) state.selectedFabs.delete(f);
      else state.selectedFabs.add(f);
      renderFabs();
      renderResults();
    });
  });
}

// open / close dropdown
const fabDropdownEl = $('#fabDropdown');
$('#fabTrigger').addEventListener('click', (e) => {
  e.stopPropagation();
  fabDropdownEl.classList.toggle('open');
});
document.addEventListener('click', (e) => {
  if (!fabDropdownEl.contains(e.target)) fabDropdownEl.classList.remove('open');
});
$('#fabAll').addEventListener('click', () => {
  state.selectedFabs = new Set(window.FABS);
  renderFabs(); renderResults();
});
$('#fabNone').addEventListener('click', () => {
  state.selectedFabs = new Set();
  renderFabs(); renderResults();
});
$('#fabInvert').addEventListener('click', () => {
  const next = new Set();
  window.FABS.forEach(f => { if (!state.selectedFabs.has(f)) next.add(f); });
  state.selectedFabs = next;
  renderFabs(); renderResults();
});

/* ---------------- scenarios + params ---------------- */
function renderScenarios() {
  const sel = $('#scenarioSel');
  sel.innerHTML = window.SCENARIOS.map(s =>
    `<option value="${s.id}" ${state.scenario===s.id?'selected':''}>${s.label}</option>`
  ).join('');
  sel.addEventListener('change', () => {
    state.scenario = sel.value;
    renderParams();
  });
}
function renderParams() {
  const sc = window.SCENARIOS.find(s => s.id === state.scenario);
  const box = $('#paramBox');
  const field = $('#paramBoxField');
  if (!sc || sc.params.length === 0) {
    field.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  field.style.display = '';
  box.innerHTML = sc.params.map(p => `
    <div class="param-row">
      <div class="k">${p.k}</div>
      <input class="input" data-param="${p.k}"
             value="${state.params[p.k] ?? ''}"
             placeholder="${p.placeholder}"/>
    </div>
  `).join('');
  box.querySelectorAll('input[data-param]').forEach(el => {
    el.addEventListener('input', () => {
      state.params[el.dataset.param] = el.value;
    });
  });
}

/* ---------------- SQL syntax highlight ---------------- */
function highlightSql(sql) {
  const esc = sql.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  return esc
    .replace(/(--[^\n]*)/g, '<span class="com">$1</span>')
    .replace(/('[^']*')/g, '<span class="str">$1</span>')
    .replace(/\b(SELECT|FROM|WHERE|AND|OR|ROWNUM|ORDER\s+BY|GROUP\s+BY|JOIN|INNER\s+JOIN|LEFT\s+JOIN|ON|AS|IN|NOT|NULL|IS|LIKE)\b/gi, '<span class="kw">$1</span>')
    .replace(/\b(TO_CHAR|TO_DATE|COUNT|SUM|AVG|MAX|MIN|NVL|TRUNC|UPPER|LOWER)\b/gi, '<span class="fn">$1</span>')
    .replace(/(:[\w_]+)/g, '<span class="par">$1</span>')
    .replace(/\b(\d+)\b/g, '<span class="num">$1</span>');
}
function renderSql() {
  const code = window.SAMPLE_SQL;
  const lines = code.split('\n').length;
  $('#lineNumbers').innerHTML = Array.from({length: lines}, (_,i)=>i+1).join('\n');
  $('#sqlCode').innerHTML = highlightSql(code);
}

/* ---------------- status strip ---------------- */
function renderStatus() {
  const sel = state.selectedFabs.size;
  const ok  = okRows().length;
  const err = errRows().length;
  const pending = 0;
  const safeSet = (id, val) => { const el = $(id); if (el) el.textContent = val; };
  safeSet('#sCountOk', ok);
  safeSet('#sCountErr', err);
  safeSet('#sCountPend', pending);
  const pct = sel === 0 ? 0 : ((ok+err) / sel) * 100;
  const fill = $('#progFill'); if (fill) fill.style.width = pct + '%';
  safeSet('#progLabel', `${ok+err}/${sel} fabs`);

  // banner
  const errs = errRows();
  const banner = $('#banner');
  if (errs.length > 0 && state.bannerOpen) {
    banner.style.display = '';
    $('#bannerCount').textContent = errs.length;
    $('#bannerList').innerHTML = errs.map(e =>
      `<span class="pill" title="${e.error}">${e.fab}</span>`
    ).join('');
  } else {
    banner.style.display = 'none';
  }
}
$('#bannerClose').addEventListener('click', () => {
  state.bannerOpen = false;
  renderStatus();
});

/* ---------------- view tabs ---------------- */
function setActiveTab() {
  $$('.tab[data-view]').forEach(x => x.classList.toggle('active', x.dataset.view === state.view));
  const diffBtn = $('#diffBtn');
  if (diffBtn) diffBtn.classList.toggle('active', state.view === 'diff');
}

$$('.tab[data-view]').forEach(t => t.addEventListener('click', () => {
  state.view = t.dataset.view;
  setActiveTab();
  renderResults();
}));
$('#diffBtn').addEventListener('click', () => {
  state.view = 'diff';
  setActiveTab();
  renderResults();
});

/* ---------------- result counts on tabs ---------------- */
function renderTabCounts() {
  $('#tabFlatCount').textContent  = okRows().length;
  $('#tabPivotCount').textContent = okRows().length;
  $('#tabDiffCount').textContent  = diffColumns().size;
}

/* ---------------- column filter helpers ---------------- */
function uniqueValuesForCol(colKey) {
  const seen = new Map();  // value -> count
  okRows().forEach(r => {
    const v = String(r.data[colKey]);
    seen.set(v, (seen.get(v) || 0) + 1);
  });
  return [...seen.entries()]
    .sort((a,b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}
function rowPassesFilters(row) {
  if (row.status !== 'ok') return true;
  for (const colKey in state.colFilters) {
    const allowed = state.colFilters[colKey];
    if (!allowed || allowed.size === 0) continue;
    const v = String(row.data[colKey]);
    if (!allowed.has(v)) return false;
  }
  return true;
}
function isFilterActive(colKey) {
  const s = state.colFilters[colKey];
  return s && s.size > 0;
}

/* ---------------- flat table ---------------- */
function renderFlat() {
  const cols = window.COLUMNS;
  const diff = state.diffOn ? diffColumns() : new Set();
  const byFab = Object.fromEntries(window.RESULTS.map(r => [r.fab, r]));

  // header
  const headHtml = `
    <tr>
      <th class="fab-col${isFilterActive('__fab')?' filtered':''}" data-col="__fab">
        <span class="h">FAB
          ${isFilterActive('__fab') ? '<span class="filter-on">●</span>' : ''}
          <span class="th-filter-ico">
            <svg width="9" height="9" viewBox="0 0 9 9" fill="none"><path d="M1 2h7M2.2 4.5h4.6M3.3 7h2.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
          </span>
        </span>
      </th>
      ${cols.map(c => `
        <th class="${diff.has(c.k)?'diff-col':''}${isFilterActive(c.k)?' filtered':''}" data-col="${c.k}">
          <span class="h">${c.label}
            ${isFilterActive(c.k) ? '<span class="filter-on">●</span>' : ''}
            <span class="th-filter-ico">
              <svg width="9" height="9" viewBox="0 0 9 9" fill="none"><path d="M1 2h7M2.2 4.5h4.6M3.3 7h2.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
            </span>
          </span>
        </th>
      `).join('')}
      <th><span class="h">SSE</span></th>
    </tr>`;

  // body — iterate ALL selected fabs in fab order (so pending/running rows are visible too)
  const fabsOrdered = window.FABS.filter(f => state.selectedFabs.has(f));
  const bodyHtml = fabsOrdered.map(fab => {
    const cs = state.chipState[fab] || { status: 'pend' };
    const r = byFab[fab];

    // pending / running → skeleton row
    if (cs.status === 'pend' || cs.status === 'run') {
      const isRun = cs.status === 'run';
      return `
        <tr class="placeholder ${cs.status}">
          <td class="fab-cell">${fabCellHtml(fab)}</td>
          <td class="placeholder-cell" colspan="${cols.length}">
            ${isRun
              ? `<span class="skeleton-bar"></span><span class="placeholder-txt">streaming from ${fab}…</span>`
              : `<span class="placeholder-txt pend">queued</span>`}
          </td>
          <td><span class="row-status ${cs.status}"><span class="ind"></span>${isRun?'STREAM':'QUEUED'}</span></td>
        </tr>`;
    }

    // error row
    if (cs.status === 'err') {
      return `
        <tr class="failed">
          <td class="fab-cell">${fabCellHtml(fab)}</td>
          <td class="err-cell" colspan="${cols.length}">${r && r.error ? r.error : 'fab failed'}</td>
          <td><span class="row-status err"><span class="ind"></span>FAILED</span></td>
        </tr>`;
    }

    // ok row — apply column filters
    if (!rowPassesFilters(r)) return '';
    return `
      <tr>
        <td class="fab-cell">${fabCellHtml(fab)}</td>
        ${cols.map(c => {
          const v = r.data[c.k];
          const cls = diff.has(c.k) ? 'diff-cell' : '';
          const rendered = pillFor(c.k, v) ?? fmtVal(v);
          return `<td class="${cls}">${rendered}</td>`;
        }).join('')}
        <td><span class="row-status ok"><span class="ind"></span>OK · 1 row</span></td>
      </tr>`;
  }).join('');

  return `
    <div class="table-wrap">
      <table class="dt">
        <thead>${headHtml}</thead>
        <tbody>${bodyHtml}</tbody>
      </table>
    </div>`;
}

/* ---------------- column filter popover ---------------- */
function showColFilter(colKey, anchorEl) {
  // remove existing
  hideColFilter();

  const isFab = colKey === '__fab';
  let values;
  if (isFab) {
    values = window.FABS.map(f => [f, 1]);
  } else {
    values = uniqueValuesForCol(colKey);
  }

  const selected = isFab
    ? new Set([...state.selectedFabs])
    : new Set([...(state.colFilters[colKey] || new Set())]);
  const allActive = isFab
    ? (selected.size === window.FABS.length)
    : (!selected.size);

  const pop = document.createElement('div');
  pop.className = 'col-filter-pop';
  pop.innerHTML = `
    <div class="col-filter-head">
      <span class="lbl">${isFab ? 'FAB' : colKey.toUpperCase()}</span>
      <div class="links">
        <a data-act="all">all</a>
        <a data-act="none">none</a>
        <a data-act="invert">invert</a>
      </div>
    </div>
    <div class="col-filter-list">
      ${values.map(([v, cnt]) => {
        const on = isFab ? selected.has(v) : (allActive || selected.has(v));
        return `<div class="col-filter-item ${on?'on':''}" data-v="${v}">
          <span class="cb"><svg width="9" height="9" viewBox="0 0 9 9" fill="none"><path d="M1.5 4.5 L3.5 6.5 L7.5 2.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          <span class="v" title="${v}">${v}</span>
          <span class="cnt">${cnt}</span>
        </div>`;
      }).join('')}
    </div>
    <div class="col-filter-foot">
      <span>${values.length} unique value${values.length===1?'':'s'}</span>
      <button class="col-filter-close">close</button>
    </div>`;

  document.body.appendChild(pop);
  // position under anchor
  const rect = anchorEl.getBoundingClientRect();
  pop.style.top = (rect.bottom + 4) + 'px';
  pop.style.left = Math.min(rect.left, window.innerWidth - 280) + 'px';

  state.openFilterCol = colKey;

  // wire
  pop.querySelectorAll('.col-filter-item').forEach(el => {
    el.addEventListener('click', () => {
      const v = el.dataset.v;
      if (isFab) {
        if (state.selectedFabs.has(v)) state.selectedFabs.delete(v);
        else state.selectedFabs.add(v);
        renderFabs();
      } else {
        let s = state.colFilters[colKey];
        if (!s || s.size === 0) {
          // currently "all" — start filtering by deselecting clicked
          s = new Set(values.map(([vv]) => vv));
          state.colFilters[colKey] = s;
        }
        if (s.has(v)) s.delete(v);
        else s.add(v);
        if (s.size === values.length) state.colFilters[colKey] = new Set(); // back to "all"
      }
      renderResults();
      // re-render popover keeping position
      const stillAnchor = document.querySelector(`th[data-col="${colKey}"]`);
      if (stillAnchor) showColFilter(colKey, stillAnchor);
    });
  });
  pop.querySelectorAll('.links a').forEach(el => {
    el.addEventListener('click', () => {
      const act = el.dataset.act;
      if (isFab) {
        if (act === 'all') state.selectedFabs = new Set(window.FABS);
        else if (act === 'none') state.selectedFabs = new Set();
        else if (act === 'invert') {
          const next = new Set();
          window.FABS.forEach(f => { if (!state.selectedFabs.has(f)) next.add(f); });
          state.selectedFabs = next;
        }
        renderFabs();
      } else {
        if (act === 'all') state.colFilters[colKey] = new Set();
        else if (act === 'none') state.colFilters[colKey] = new Set(['__none__']);
        else if (act === 'invert') {
          const cur = state.colFilters[colKey] || new Set();
          const next = new Set();
          values.forEach(([vv]) => { if (!cur.has(vv)) next.add(vv); });
          state.colFilters[colKey] = next;
        }
      }
      renderResults();
      const stillAnchor = document.querySelector(`th[data-col="${colKey}"]`);
      if (stillAnchor) showColFilter(colKey, stillAnchor);
    });
  });
  pop.querySelector('.col-filter-close').addEventListener('click', hideColFilter);
}
function hideColFilter() {
  document.querySelectorAll('.col-filter-pop').forEach(el => el.remove());
  state.openFilterCol = null;
}
document.addEventListener('click', (e) => {
  if (e.target.closest('.col-filter-pop')) return;
  if (e.target.closest('.dt thead th')) return;
  hideColFilter();
});

/* ---------------- pivot ---------------- */
function renderPivot() {
  const cols = window.COLUMNS;
  const diff = state.diffOn ? diffColumns() : new Set();
  const fabs = [...state.selectedFabs].sort((a,b) => window.FABS.indexOf(a) - window.FABS.indexOf(b));
  const byFab = Object.fromEntries(window.RESULTS.map(r => [r.fab, r]));

  const head = `
    <tr>
      <th>FIELD</th>
      ${fabs.map(f => {
        const r = byFab[f];
        const cls = r && r.status === 'err' ? 'fab-h failed' : 'fab-h';
        return `<th class="${cls}">${f}</th>`;
      }).join('')}
    </tr>`;

  const body = cols.map(c => {
    const isDiff = diff.has(c.k);
    return `
      <tr class="${isDiff?'diff':''}">
        <td class="field">${c.label}</td>
        ${fabs.map(f => {
          const r = byFab[f];
          if (!r) return `<td class="val null-val">—</td>`;
          if (r.status === 'err') return `<td class="val err-val">err</td>`;
          const v = r.data[c.k];
          const display = (v===null||v===undefined||v==='') ? '<span class="null">∅</span>' : String(v);
          return `<td class="val ${isDiff?'diff-cell':''}">${display}</td>`;
        }).join('')}
      </tr>`;
  }).join('');

  return `
    <div class="pivot-wrap">
      <table class="pivot">
        <thead>${head}</thead>
        <tbody>${body}</tbody>
      </table>
    </div>`;
}

/* ---------------- diff view (card layout) ---------------- */
function renderDiffView() {
  const rows = okRows();
  if (rows.length === 0) {
    return `
      <div class="diff-view-empty">
        <div class="empty-icon">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="1.5" opacity="0.3"/>
            <path d="M16 24h16M24 16v16" stroke="currentColor" stroke-width="1.5" opacity="0.5" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="empty-title">No data to compare</div>
        <div class="empty-sub">Select fabs and run a query to see column diffs.</div>
      </div>`;
  }

  const diff = diffColumns();
  if (diff.size === 0) {
    return `
      <div class="diff-view-empty">
        <div class="empty-icon ok">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
            <circle cx="24" cy="24" r="20" stroke="currentColor" stroke-width="1.5"/>
            <path d="M16 24l6 6 12-12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
          </svg>
        </div>
        <div class="empty-title">All ${window.COLUMNS.length} columns match across ${rows.length} fabs</div>
        <div class="empty-sub">No divergent values detected. SET(values) = 1 for every column.</div>
      </div>`;
  }

  // header summary
  const summary = `
    <div class="diff-view-head">
      <div class="diff-head-l">
        <div class="diff-head-title">
          <span class="diff-head-marker"></span>
          <h2><b>${diff.size}</b> column${diff.size===1?'':'s'} diverge across <b>${rows.length}</b> fabs</h2>
        </div>
        <div class="diff-head-sub">Each card lists the distinct values for one column. Groups sorted by fab count.</div>
      </div>
      <div class="diff-head-r">
        <div class="diff-head-stat">
          <span class="stat-v">${window.COLUMNS.length - diff.size}</span>
          <span class="stat-l">columns identical</span>
        </div>
        <div class="diff-head-stat warn">
          <span class="stat-v">${diff.size}</span>
          <span class="stat-l">columns differ</span>
        </div>
      </div>
    </div>`;

  // cards
  const cards = [...diff].map(col => {
    const groups = new Map();
    rows.forEach(r => {
      const v = String(r.data[col]);
      if (!groups.has(v)) groups.set(v, []);
      groups.get(v).push(r.fab);
    });
    const grouped = [...groups.entries()].sort((a,b) => b[1].length - a[1].length);
    const totalFabs = rows.length;

    return `
      <div class="diff-vcard">
        <div class="diff-vcard-head">
          <div class="diff-vcard-name">
            <span class="marker"></span>
            <span class="col-name">${col.toUpperCase()}</span>
          </div>
          <div class="diff-vcard-meta">${groups.size} distinct values</div>
        </div>
        <div class="diff-vcard-body">
          ${grouped.map(([v, fabs], idx) => {
            const isMajority = idx === 0;
            const rendered = pillFor(col, v) ?? `<span class="val-text">${v === 'null' || v === 'undefined' ? '<i class="null">∅ null</i>' : v}</span>`;
            return `
              <div class="diff-vrow ${isMajority?'majority':''}">
                <div class="diff-vrow-val">${rendered}</div>
                <div class="diff-vrow-count"><b>${fabs.length}</b><span class="of">/${rows.length}</span></div>
                <div class="diff-vrow-fabs">
                  ${fabs.map(f => `<span class="vfab">${f}</span>`).join('')}
                </div>
              </div>`;
          }).join('')}
        </div>
      </div>`;
  }).join('');

  return `
    <div class="diff-view">
      ${summary}
      <div class="diff-vgrid">${cards}</div>
    </div>`;
}
function renderDiffPanel() {
  if (!state.diffOn) return '';
  const diff = diffColumns();
  if (diff.size === 0) return '';
  const rows = okRows();

  // collapsed mini-bar
  if (!state.diffPanelOpen) {
    return `
      <div class="diff-mini" id="diffMini">
        <span class="diff-mini-mark"></span>
        <span class="diff-mini-title">Diff — <b>${diff.size}</b> column${diff.size===1?'':'s'} with divergent values</span>
        <span class="diff-mini-cols">${[...diff].slice(0,4).map(c => `<span class="diff-mini-col">${c}</span>`).join('')}${diff.size>4?`<span class="diff-mini-more">+${diff.size-4}</span>`:''}</span>
        <span class="diff-mini-toggle">expand ▾</span>
      </div>`;
  }

  // full panel
  const cards = [...diff].map(col => {
    const groups = new Map();
    rows.forEach(r => {
      const v = String(r.data[col]);
      if (!groups.has(v)) groups.set(v, []);
      groups.get(v).push(r.fab);
    });
    const grouped = [...groups.entries()].sort((a,b) => b[1].length - a[1].length);
    return `
      <div class="diff-card">
        <div class="col">
          <span>${col.toUpperCase()}</span>
          <span class="n">${groups.size} distinct</span>
        </div>
        <div class="vals">
          ${grouped.map(([v, fabs]) => `
            <div class="diff-val">
              <span class="v" title="${v}">${v}</span>
              <span class="fabs">${fabs.map(f => `<span class="f">${f}</span>`).join('')}</span>
            </div>
          `).join('')}
        </div>
      </div>`;
  }).join('');

  return `
    <div class="diff-panel show">
      <div class="diff-panel-head">
        <div class="diff-panel-title">
          <h3><span class="marker"></span>Diff — ${diff.size} column${diff.size===1?'':'s'} with divergent values</h3>
          <span class="sub">columns where SET(values) across selected fabs &gt; 1</span>
        </div>
        <button class="diff-panel-collapse" id="diffCollapse">collapse ▴</button>
      </div>
      <div class="diff-grid">${cards}</div>
    </div>`;
}

/* ---------------- main render ---------------- */
function renderResults() {
  renderStatus();
  renderTabCounts();
  renderChips();
  const host = $('#resultsHost');
  const diffHost = $('#diffPanelHost');

  if (state.view === 'flat') {
    host.innerHTML = renderFlat();
    if (diffHost) diffHost.innerHTML = renderDiffPanel();
  } else if (state.view === 'pivot') {
    host.innerHTML = renderPivot();
    if (diffHost) diffHost.innerHTML = renderDiffPanel();
  } else if (state.view === 'diff') {
    host.innerHTML = renderDiffView();
    if (diffHost) diffHost.innerHTML = '';
  }

  // wire diff-panel mini/expand controls (only when flat/pivot rendered the under-table panel)
  if (state.view !== 'diff' && diffHost) {
    const mini = $('#diffMini');
    if (mini) mini.addEventListener('click', () => { state.diffPanelOpen = true; renderResults(); });
    const collapse = $('#diffCollapse');
    if (collapse) collapse.addEventListener('click', () => { state.diffPanelOpen = false; renderResults(); });
  }

  // wire column header click → filter popover (only when table is rendered)
  host.querySelectorAll('.dt thead th[data-col]').forEach(th => {
    th.style.cursor = 'pointer';
    th.addEventListener('click', (e) => {
      e.stopPropagation();
      const colKey = th.dataset.col;
      if (state.openFilterCol === colKey) {
        hideColFilter();
      } else {
        showColFilter(colKey, th);
      }
    });
  });

  // footer
  const ok = okRows().length;
  const tot = ok + errRows().length;
  $('#footRows').textContent = ok;
  $('#footFabs').textContent = tot;
  $('#footDiff').textContent = diffColumns().size;
}

/* ---------------- boot ---------------- */
setChipsComplete();
renderFabs();
renderScenarios();
renderParams();
renderSql();
setActiveTab();
renderResults();

// expose for tweaks.js
window.setChipsComplete = setChipsComplete;
window.renderResults = renderResults;

// Run button replays the stream simulation
$('#runBtn').addEventListener('click', () => {
  startStream();
});

// fake "live" pulse on the prog bar to suggest SSE
let pulseDir = 1;
setInterval(() => {
  const el = $('#progFill');
  if (!el) return;
  const cur = parseFloat(el.style.width) || 0;
  if (cur >= 100) el.style.opacity = (parseFloat(el.style.opacity || 1) === 1 ? 0.55 : 1);
}, 1400);
