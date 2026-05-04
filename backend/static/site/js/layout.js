(function () {
  'use strict';

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const sidebar   = document.getElementById('bpmSidebar');
  const main      = document.getElementById('bpmMain');
  const topbar    = document.getElementById('bpmTopbar');
  const overlay   = document.getElementById('bpmOverlay');
  const toggleBtn = document.getElementById('bpmSidebarToggle');
  const search    = document.getElementById('bpmSearch');
  const searchRes = document.getElementById('bpmSearchResults');

  const BP_LG     = 992;
  const STORAGE_KEY = 'bpm_sidebar_collapsed';
  const SEARCH_DEBOUNCE = 300;

  // ── helpers ────────────────────────────────────────────────────────────────
  function isMobile() {
    return window.innerWidth < BP_LG;
  }

  // ============================================================================
  // 1. SIDEBAR TOGGLE
  // ============================================================================

  // Открыть на мобильном
  function openMobileSidebar() {
    sidebar?.classList.add('is-open');
    overlay?.classList.add('is-visible');
    toggleBtn?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  // Закрыть на мобильном
  function closeMobileSidebar() {
    sidebar?.classList.remove('is-open');
    overlay?.classList.remove('is-visible');
    toggleBtn?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  // Свернуть/развернуть на десктопе
  function toggleDesktopSidebar() {
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    toggleBtn?.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    try { localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0'); } catch (e) {}
  }

  // Универсальный обработчик toggle-кнопки
  toggleBtn?.addEventListener('click', function () {
    if (isMobile()) {
      sidebar?.classList.contains('is-open')
        ? closeMobileSidebar()
        : openMobileSidebar();
    } else {
      toggleDesktopSidebar();
    }
  });

  // Overlay click → close (mobile)
  overlay?.addEventListener('click', closeMobileSidebar);

  // ESC → close (mobile)
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sidebar?.classList.contains('is-open')) {
      closeMobileSidebar();
    }
  });

  // Resize: на десктопе закрываем мобильный режим
  window.addEventListener('resize', function () {
    if (!isMobile()) {
      sidebar?.classList.remove('is-open');
      overlay?.classList.remove('is-visible');
      document.body.style.overflow = '';
    }
  });

  // Восстановить collapsed состояние на десктопе
  try {
    if (!isMobile() && localStorage.getItem(STORAGE_KEY) === '1') {
      document.body.classList.add('sidebar-collapsed');
      toggleBtn?.setAttribute('aria-expanded', 'false');
    }
  } catch (e) {}

  // ============================================================================
  // 2. ACTIVE NAV HIGHLIGHT
  // ============================================================================
  (function () {
    if (!sidebar) return;

    const path  = window.location.pathname;
    const links = sidebar.querySelectorAll('a.bpm-sidebar__item');

    let bestMatch = null;
    let bestLen   = 0;

    links.forEach(function (link) {
      const href = link.getAttribute('href');
      if (!href || href === '#' || href === '/') return;

      // ищем самое длинное совпадение префикса
      if (path.startsWith(href) && href.length > bestLen) {
        bestLen   = href.length;
        bestMatch = link;
      }
    });

    // также проверяем точное совпадение для главной
    if (!bestMatch && path === '/') {
      bestMatch = sidebar.querySelector('a.bpm-sidebar__item[href="/"]');
    }

    if (bestMatch) {
      bestMatch.classList.add('is-active');
      bestMatch.setAttribute('aria-current', 'page');

      // Раскрыть родительскую группу если это sub-item
      const collapseEl = bestMatch.closest('.collapse');
      if (collapseEl) {
        collapseEl.classList.add('show');
        const parent = sidebar.querySelector(
          '[data-bs-target="#' + collapseEl.id + '"]'
        );
        parent?.setAttribute('aria-expanded', 'true');
        parent?.classList.add('is-open');
      }
    }
  })();

  // ============================================================================
  // 3. COLLAPSE CHEVRON SYNC
  // ============================================================================
  document.querySelectorAll('.bpm-sidebar__item--parent').forEach(function (btn) {
    const targetId = btn.getAttribute('data-bs-target');
    const target   = targetId ? document.querySelector(targetId) : null;
    if (!target) return;

    target.addEventListener('show.bs.collapse', function () {
      btn.classList.add('is-open');
      btn.setAttribute('aria-expanded', 'true');
    });
    target.addEventListener('hide.bs.collapse', function () {
      btn.classList.remove('is-open');
      btn.setAttribute('aria-expanded', 'false');
    });
  });

  // ============================================================================
  // 4. CLOSE SIDEBAR ON LINK CLICK (mobile)
  // ============================================================================
  sidebar?.querySelectorAll('a.bpm-sidebar__item').forEach(function (link) {
    link.addEventListener('click', function () {
      if (isMobile()) closeMobileSidebar();
    });
  });

  // ============================================================================
  // 5. SEARCH (с debounce)
  // ============================================================================
  let searchTimer = null;

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function hideSearchResults() {
    if (searchRes) searchRes.hidden = true;
  }

  function showSearchResults() {
    if (searchRes) searchRes.hidden = false;
  }

  function renderSearchResults(items) {
    if (!searchRes) return;

    if (!items || items.length === 0) {
      searchRes.innerHTML =
        '<div class="bpm-topbar__search-empty">Ничего не найдено</div>';
    } else {
      searchRes.innerHTML = items.map(function (it) {
        return (
          '<a class="bpm-topbar__search-result-item" href="' + escapeHtml(it.url || '#') + '">' +
            '<div>' + escapeHtml(it.title || '') + '</div>' +
            (it.subtitle ? '<div class="text-muted">' + escapeHtml(it.subtitle) + '</div>' : '') +
          '</a>'
        );
      }).join('');
    }
    showSearchResults();
  }

  async function doSearch(query) {
    try {
      const res = await fetch('/api/search/?q=' + encodeURIComponent(query), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
      });
      if (!res.ok) { hideSearchResults(); return; }
      const data = await res.json();
      renderSearchResults(data.results || []);
    } catch (e) {
      hideSearchResults();
    }
  }

  search?.addEventListener('input', function (e) {
    const q = e.target.value.trim();
    clearTimeout(searchTimer);
    if (q.length < 2) { hideSearchResults(); return; }
    searchTimer = setTimeout(function () { doSearch(q); }, SEARCH_DEBOUNCE);
  });

  search?.addEventListener('focus', function (e) {
    if (e.target.value.trim().length >= 2) showSearchResults();
  });

  // Click outside → закрыть
  document.addEventListener('click', function (e) {
    if (!search?.contains(e.target) && !searchRes?.contains(e.target)) {
      hideSearchResults();
    }
  });

  // ESC в поиске → закрыть
  search?.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      hideSearchResults();
      search.blur();
    }
  });

  // ============================================================================
  // 6. CSRF HELPER
  // ============================================================================
  function getCsrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute('content');
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  // ============================================================================
  // PUBLIC API
  // ============================================================================
  window.bpmLayout = {
    openSidebar:        openMobileSidebar,
    closeSidebar:       closeMobileSidebar,
    toggleDesktop:      toggleDesktopSidebar,
    isMobile:           isMobile,
    getCsrf:            getCsrf,
  };

})();