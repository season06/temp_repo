/* ============================================================
   Tweaks panel — theme / accent / density
   ============================================================ */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "lime",
  "density": "compact"
}/*EDITMODE-END*/;

const tweaks = { ...TWEAK_DEFAULTS };

const accentMap = {
  lime:    { c: '#1f6f3c', dim: '#2a8b4d', ink: '#f3fff7' },
  amber:   { c: '#b6701f', dim: '#d18b32', ink: '#fff7eb' },
  cyan:    { c: '#0c7a8f', dim: '#1aa0b8', ink: '#ecfbff' },
  magenta: { c: '#a02266', dim: '#c83a85', ink: '#fff0f7' },
};

function applyTheme() {
  document.body.classList.add('theme-light');
}
function applyAccent() {
  const a = accentMap[tweaks.accent] || accentMap.lime;
  const root = document.documentElement;
  root.style.setProperty('--accent', a.c);
  root.style.setProperty('--accent-dim', a.dim);
  root.style.setProperty('--accent-ink', a.ink);
}
function applyDensity() {
  document.body.dataset.density = tweaks.density;
  // simple density swap
  if (tweaks.density === 'cozy') {
    document.documentElement.style.setProperty('--pad', '20px');
  } else {
    document.documentElement.style.setProperty('--pad', '16px');
  }
  // Adjust table cell padding via class
  document.body.classList.toggle('density-cozy', tweaks.density === 'cozy');
}

function syncUI() {
  document.querySelectorAll('#tw-accent .tweak-swatch').forEach(el => {
    el.classList.toggle('on', el.dataset.v === tweaks.accent);
  });
  document.querySelectorAll('#tw-density .opt').forEach(el => {
    el.classList.toggle('on', el.dataset.v === tweaks.density);
  });
}

function setTweak(patch) {
  Object.assign(tweaks, patch);
  applyTheme();
  applyAccent();
  applyDensity();
  syncUI();
  try {
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits: patch }, '*');
  } catch(_) {}
}

// Wire controls
document.querySelectorAll('#tw-accent .tweak-swatch').forEach(el => {
  el.addEventListener('click', () => setTweak({ accent: el.dataset.v }));
});
document.querySelectorAll('#tw-density .opt').forEach(el => {
  el.addEventListener('click', () => setTweak({ density: el.dataset.v }));
});
document.querySelectorAll('#tw-stream .opt').forEach(el => {
  el.addEventListener('click', () => {
    if (el.dataset.v === 'run') {
      if (typeof window.startStream === 'function') window.startStream();
    } else {
      if (typeof window.setChipsComplete === 'function') {
        window.setChipsComplete();
        if (typeof window.renderResults === 'function') window.renderResults();
      }
    }
  });
});

// initial apply
applyTheme();
applyAccent();
applyDensity();
syncUI();

/* ---------------- Host edit mode protocol ---------------- */
const tweaksEl = document.getElementById('tweaks');
const tweaksFab = document.getElementById('tweaksFab');
const tweaksCloseBtn = document.getElementById('tweaksClose');

function showTweaks() {
  tweaksEl.classList.add('show');
  tweaksFab.classList.remove('show');
}
function hideTweaks() {
  tweaksEl.classList.remove('show');
  tweaksFab.classList.add('show');
  try { window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*'); } catch(_) {}
}

window.addEventListener('message', (e) => {
  const t = e.data && e.data.type;
  if (t === '__activate_edit_mode')   showTweaks();
  if (t === '__deactivate_edit_mode') {
    tweaksEl.classList.remove('show');
    tweaksFab.classList.remove('show');
  }
});

tweaksCloseBtn.addEventListener('click', hideTweaks);
tweaksFab.addEventListener('click', showTweaks);

// announce availability
try { window.parent.postMessage({ type: '__edit_mode_available' }, '*'); } catch(_) {}
