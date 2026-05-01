(function () {
    'use strict';
  
    // ── DOM ────────────────────────────────────────────────────────────────────
    const sidebar  = document.getElementById('bpmSidebar');
    const main     = document.getElementById('bpmMain');
    const topbar   = document.getElementById('bpmTopbar');
    const overlay  = document.getElementById('bpmOverlay');
    const burger   = document.getElementById('bpmBurger');
  
    const BP_LG    = 992; // matches $bp-lg in layout.scss
  
    // ==========================================================================
    // 1. SIDEBAR TOGGLE (mobile)
    // ==========================================================================
  
    function openSidebar() {
      sidebar?.classList.add('is-open');
      overlay?.classList.add('is-visible');
      burger?.setAttribute('aria-expanded', 'true');
      document.body.style.overflow = 'hidden';
    }
  
    function closeSidebar() {
      sidebar?.classList.remove('is-open');
      overlay?.classList.remove('is-visible');
      burger?.setAttribute('aria-expanded', 'false');
      document.body.style.overflow = '';
    }
  
    function isMobile() {
      return window.innerWidth < BP_LG;
    }
  
    // Burger click
    burger?.addEventListener('click', function () {
      sidebar?.classList.contains('is-open') ? closeSidebar() : openSidebar();
    });
  
    // Overlay click → close
    overlay?.addEventListener('click', closeSidebar);
  
    // ESC → close
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && sidebar?.classList.contains('is-open')) {
        closeSidebar();
      }
    });
  
    // Resize: if desktop → reset mobile state
    window.addEventListener('resize', function () {
      if (!isMobile()) {
        closeSidebar();
      }
    });
  
    // ==========================================================================
    // 2. ACTIVE NAV HIGHLIGHT
    // ==========================================================================
    (function highlightNav() {
      if (!sidebar) return;
  
      const path     = window.location.pathname;
      const allLinks = sidebar.querySelectorAll('a.bpm-sidebar__item');
  
      let bestMatch = null;
      let bestLen   = 0;
  
      allLinks.forEach(function (link) {
        const href = link.getAttribute('href');
        if (!href || href === '#' || href === '/') return;
  
        if (path.startsWith(href) && href.length > bestLen) {
          bestLen   = href.length;
          bestMatch = link;
        }
      });
  
      if (bestMatch) {
        bestMatch.classList.add('is-active');
        bestMatch.setAttribute('aria-current', 'page');
  
        // Open parent collapse
        const collapseEl = bestMatch.closest('.collapse');
        if (collapseEl) {
          collapseEl.classList.add('show');
          const parentBtn = sidebar.querySelector(
            '[data-bs-target="#' + collapseEl.id + '"]'
          );
          if (parentBtn) {
            parentBtn.setAttribute('aria-expanded', 'true');
            parentBtn.classList.add('is-active');
          }
        }
      }
    })();
  
    // ==========================================================================
    // 3. COLLAPSE CHEVRON SYNC (Bootstrap events)
    // ==========================================================================
    document.querySelectorAll('.bpm-sidebar__item--parent').forEach(function (btn) {
      const targetId   = btn.getAttribute('data-bs-target');
      const collapseEl = targetId ? document.querySelector(targetId) : null;
  
      if (!collapseEl) return;
  
      collapseEl.addEventListener('show.bs.collapse', function () {
        btn.setAttribute('aria-expanded', 'true');
      });
      collapseEl.addEventListener('hide.bs.collapse', function () {
        btn.setAttribute('aria-expanded', 'false');
      });
    });
  
    // ==========================================================================
    // 4. CLOSE SIDEBAR ON NAV LINK CLICK (mobile)
    // ==========================================================================
    sidebar?.querySelectorAll('a.bpm-sidebar__item').forEach(function (link) {
      link.addEventListener('click', function () {
        if (isMobile()) closeSidebar();
      });
    });
  
    // ==========================================================================
    // 5. CSRF HELPER (for AJAX calls from child templates)
    // ==========================================================================
    function getCsrf() {
      const meta = document.querySelector('meta[name="csrf-token"]');
      if (meta) return meta.getAttribute('content');
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      return match ? match[1] : '';
    }
  
    // ==========================================================================
    // 6. EXPOSE PUBLIC API
    // ==========================================================================
    window.bpmLayout = {
      openSidebar:  openSidebar,
      closeSidebar: closeSidebar,
      getCsrf:      getCsrf,
    };
  
  })();