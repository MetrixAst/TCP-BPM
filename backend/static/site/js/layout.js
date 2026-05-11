(function () {
  'use strict';

  const sidebar = document.getElementById('bpmSidebar');
  const overlay = document.getElementById('bpmOverlay');
  const toggleBtn = document.getElementById('bpmSidebarToggle');
  const search = document.getElementById('bpmSearch');
  const searchRes = document.getElementById('bpmSearchResults');

  const BP_LG = 992;
  const STORAGE_KEY = 'bpm_sidebar_collapsed';
  const SEARCH_DEBOUNCE = 250;

  function isMobile() {
    return window.innerWidth < BP_LG;
  }

  function openMobileSidebar() {
    sidebar?.classList.add('is-open');
    overlay?.classList.add('is-visible');
    toggleBtn?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  function closeMobileSidebar() {
    sidebar?.classList.remove('is-open');
    overlay?.classList.remove('is-visible');
    toggleBtn?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  function toggleDesktopSidebar() {
    const collapsed = document.body.classList.toggle('sidebar-collapsed');
    toggleBtn?.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
  }

  toggleBtn?.addEventListener('click', function () {
    if (isMobile()) {
      sidebar?.classList.contains('is-open') ? closeMobileSidebar() : openMobileSidebar();
    } else {
      toggleDesktopSidebar();
    }
  });

  overlay?.addEventListener('click', closeMobileSidebar);

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeMobileSidebar();
      hideSearchResults();
    }
  });

  window.addEventListener('resize', function () {
    if (!isMobile()) {
      closeMobileSidebar();
    }
  });

  try {
    if (!isMobile() && localStorage.getItem(STORAGE_KEY) === '1') {
      document.body.classList.add('sidebar-collapsed');
      toggleBtn?.setAttribute('aria-expanded', 'false');
    }
  } catch (error) {}

  function activateSidebarItem() {
    if (!sidebar) return;

    const path = window.location.pathname;
    const links = sidebar.querySelectorAll('a.bpm-sidebar__item');
    let bestMatch = null;
    let bestLength = 0;

    links.forEach(function (link) {
      const href = link.getAttribute('href');
      if (!href || href === '#') return;

      if ((path === href || path.startsWith(href)) && href.length > bestLength) {
        bestMatch = link;
        bestLength = href.length;
      }
    });

    if (!bestMatch && path === '/') {
      bestMatch = sidebar.querySelector('a.bpm-sidebar__item[href="/"]');
    }

    if (!bestMatch) return;

    bestMatch.classList.add('is-active');
    bestMatch.setAttribute('aria-current', 'page');

    const collapse = bestMatch.closest('.collapse');
    if (collapse) {
      collapse.classList.add('show');
      const parent = sidebar.querySelector('[data-bs-target="#' + collapse.id + '"]');
      parent?.classList.add('is-open');
      parent?.setAttribute('aria-expanded', 'true');
    }
  }

  activateSidebarItem();

  document.querySelectorAll('.bpm-sidebar__item--parent').forEach(function (button) {
    const target = document.querySelector(button.getAttribute('data-bs-target'));
    if (!target) return;

    target.addEventListener('show.bs.collapse', function () {
      button.classList.add('is-open');
      button.setAttribute('aria-expanded', 'true');
    });

    target.addEventListener('hide.bs.collapse', function () {
      button.classList.remove('is-open');
      button.setAttribute('aria-expanded', 'false');
    });
  });

  sidebar?.querySelectorAll('a.bpm-sidebar__item').forEach(function (link) {
    link.addEventListener('click', function () {
      if (isMobile()) closeMobileSidebar();
    });
  });

  function escapeHtml(value) {
    return String(value || '')
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

  function getLocalMenuResults(query) {
    if (!sidebar) return [];

    return Array.from(sidebar.querySelectorAll('a.bpm-sidebar__item'))
      .map(function (link) {
        return {
          title: link.textContent.trim(),
          url: link.getAttribute('href') || '#',
          subtitle: 'Раздел меню'
        };
      })
      .filter(function (item) {
        return item.title.toLowerCase().includes(query.toLowerCase());
      })
      .slice(0, 8);
  }

  function renderSearchResults(items) {
    if (!searchRes) return;

    if (!items.length) {
      searchRes.innerHTML = '<div class="bpm-topbar__search-empty">Ничего не найдено</div>';
      showSearchResults();
      return;
    }

    searchRes.innerHTML = items.map(function (item) {
      return (
        '<a class="bpm-topbar__search-result-item" href="' + escapeHtml(item.url) + '">' +
          '<div>' + escapeHtml(item.title) + '</div>' +
          '<div class="text-muted">' + escapeHtml(item.subtitle || '') + '</div>' +
        '</a>'
      );
    }).join('');

    showSearchResults();
  }

  async function doSearch(query) {
    const localResults = getLocalMenuResults(query);

    try {
      const response = await fetch('/api/search/?q=' + encodeURIComponent(query), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin'
      });

      if (!response.ok) {
        renderSearchResults(localResults);
        return;
      }

      const data = await response.json();
      renderSearchResults((data.results || localResults).slice(0, 8));
    } catch (error) {
      renderSearchResults(localResults);
    }
  }

  let timer = null;

  search?.addEventListener('input', function (event) {
    const query = event.target.value.trim();
    clearTimeout(timer);

    if (query.length < 2) {
      hideSearchResults();
      return;
    }

    timer = setTimeout(function () {
      doSearch(query);
    }, SEARCH_DEBOUNCE);
  });

  search?.addEventListener('focus', function () {
    if (search.value.trim().length >= 2) {
      doSearch(search.value.trim());
    }
  });

  document.addEventListener('click', function (event) {
    if (!search?.contains(event.target) && !searchRes?.contains(event.target)) {
      hideSearchResults();
    }
  });

  window.bpmLayout = {
    openSidebar: openMobileSidebar,
    closeSidebar: closeMobileSidebar,
    toggleDesktop: toggleDesktopSidebar,
    isMobile: isMobile
  };
})();