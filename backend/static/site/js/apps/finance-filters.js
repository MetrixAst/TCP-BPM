'use strict';

/* ─── CSRF helper ────────────────────────────────────────── */
function getCsrfToken() {
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  if (el) return el.value;
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : '';
}

/* ─── Load saved filters from session ───────────────────── */
async function loadSavedFilters() {
  try {
    const resp = await fetch('/finances/filters/');
    if (!resp.ok) return;
    const filters = await resp.json();

    Object.entries(filters).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') return;

      /* date inputs */
      const dateEl = document.querySelector(`input[data-filter-key="${key}"]`);
      if (dateEl) {
        dateEl.value = value;
        return;
      }

      /* custom selects */
      const selectWrap = document.querySelector(`.fin-custom-select[data-filter-key="${key}"]`);
      if (selectWrap) {
        const hidden = selectWrap.querySelector('input[type=hidden]');
        if (hidden) hidden.value = value;

        const opt = selectWrap.querySelector(`.fin-custom-select__option[data-value="${value}"]`);
        const label = selectWrap.querySelector('.fin-custom-select__value');
        if (opt && label) label.textContent = opt.textContent.trim();
        return;
      }
    });

    updateActiveHint(filters);
  } catch (e) {
    console.warn('loadSavedFilters failed', e);
  }
}

/* ─── Save filters to session ────────────────────────────── */
async function saveFilters(filters) {
  await fetch('/finances/filters/save/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCsrfToken(),
    },
    body: JSON.stringify(filters),
  });
}

/* ─── Collect current filter values from form ───────────── */
function collectFilters() {
  const filters = {};

  /* date inputs */
  document.querySelectorAll('input[data-filter-key]').forEach(el => {
    if (el.value) filters[el.dataset.filterKey] = el.value;
  });

  /* custom selects */
  document.querySelectorAll('.fin-custom-select[data-filter-key]').forEach(wrap => {
    const hidden = wrap.querySelector('input[type=hidden]');
    if (hidden && hidden.value !== '') {
      filters[wrap.dataset.filterKey] = hidden.value;
    }
  });

  return filters;
}

/* ─── Active filter hint ─────────────────────────────────── */
function updateActiveHint(filters) {
  const hint = document.getElementById('activeFiltersHint');
  if (!hint) return;
  const hasActive = Object.values(filters).some(v => v !== '' && v !== null && v !== undefined);
  hint.style.display = hasActive ? 'flex' : 'none';
}

/* ─── Custom select dropdown logic ──────────────────────── */
function initCustomSelects() {
  document.querySelectorAll('.fin-custom-select').forEach(wrap => {
    const btn      = wrap.querySelector('.fin-custom-select__button');
    const dropdown = wrap.querySelector('.fin-custom-select__dropdown');
    const hidden   = wrap.querySelector('input[type=hidden]');
    const label    = wrap.querySelector('.fin-custom-select__value');

    if (!btn || !dropdown) return;

    btn.addEventListener('click', e => {
      e.stopPropagation();
      const open = dropdown.classList.toggle('is-open');
      btn.classList.toggle('is-active', open);
    });

    dropdown.querySelectorAll('.fin-custom-select__option').forEach(opt => {
      opt.addEventListener('click', () => {
        if (hidden) hidden.value = opt.dataset.value || '';
        if (label)  label.textContent = opt.textContent.trim();
        dropdown.classList.remove('is-open');
        btn.classList.remove('is-active');

        dropdown.querySelectorAll('.fin-custom-select__option').forEach(o => o.classList.remove('is-selected'));
        opt.classList.add('is-selected');
      });
    });
  });

  /* Close dropdowns on outside click */
  document.addEventListener('click', () => {
    document.querySelectorAll('.fin-custom-select__dropdown.is-open').forEach(d => {
      d.classList.remove('is-open');
      d.closest('.fin-custom-select')?.querySelector('.fin-custom-select__button')?.classList.remove('is-active');
    });
  });
}

/* ─── Init ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initCustomSelects();
  loadSavedFilters();

  document.getElementById('applyGlobalFilters')?.addEventListener('click', async () => {
    const filters = collectFilters();
    await saveFilters(filters);
    updateActiveHint(filters);
    window.location.reload();
  });

  document.getElementById('resetGlobalFilters')?.addEventListener('click', async () => {
    await saveFilters({});

    /* Clear form visually */
    document.querySelectorAll('input[data-filter-key]').forEach(el => { el.value = ''; });
    document.querySelectorAll('.fin-custom-select[data-filter-key]').forEach(wrap => {
      const hidden = wrap.querySelector('input[type=hidden]');
      const label  = wrap.querySelector('.fin-custom-select__value');
      if (hidden) hidden.value = '';
      if (label)  label.textContent = 'Все';
      wrap.querySelectorAll('.fin-custom-select__option').forEach(o => o.classList.remove('is-selected'));
    });

    updateActiveHint({});
    window.location.reload();
  });
});
