(function () {
    'use strict';
  
    document.addEventListener('DOMContentLoaded', function () {
  
      // --- select2 на фильтрах ---
      if (window.jQuery && jQuery.fn.select2) {
        jQuery('.access-page__select--select2').select2({
          theme: 'bootstrap4',
          width: '160px',
        });
      }
  
      // --- модалка матрицы прав ---
      const modal = document.getElementById('accessMatrixModal');
      if (!modal) return;
  
      const body = modal.querySelector('[data-access-modal-body]');
      const closeBtn = modal.querySelector('[data-access-modal-close]');
      const rows = document.querySelectorAll('.access-table__row');
  
      function openModal() {
        modal.classList.add('is-open');
      }
  
      function closeModal() {
        modal.classList.remove('is-open');
        body.innerHTML = '<div class="access-modal__loading">Загрузка…</div>';
      }
  
      function renderMatrix(data) {
        const overridesHtml = (data.overrides || []).map(function (o) {
          const effectClass = o.effect === 'ALLOW' ? 'access-effect--allow' : 'access-effect--deny';
          return (
            '<div class="access-override-row">' +
              '<span class="access-effect ' + effectClass + '">' + o.effect + '</span>' +
              '<span>' + (o.permission_label || o.permission_code) + '</span>' +
              (o.reason ? '<span class="access-muted"> — ' + o.reason + '</span>' : '') +
            '</div>'
          );
        }).join('') || '<p class="access-muted">Нет индивидуальных переопределений</p>';
  
        const rolePermsHtml = (data.role_permissions || []).map(function (code) {
          return '<span class="access-chip">' + code + '</span>';
        }).join('') || '<p class="access-muted">Нет прав по роли</p>';
  
        body.innerHTML =
          '<h3>' + (data.full_name || data.username) + '</h3>' +
          '<p class="access-muted">@' + data.username + ' · роль: ' + data.role + '</p>' +
          '<h4>Права по роли</h4>' +
          '<div class="access-chips">' + rolePermsHtml + '</div>' +
          '<h4>Индивидуальные переопределения</h4>' +
          '<div class="access-overrides">' + overridesHtml + '</div>';
      }
  
      rows.forEach(function (row) {
        row.addEventListener('click', function () {
          const userId = row.getAttribute('data-user-id');
          openModal();
          fetch('/api/v1/permissions/users/' + userId + '/', {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
          })
            .then(function (res) {
              if (!res.ok) throw new Error('Request failed: ' + res.status);
              return res.json();
            })
            .then(renderMatrix)
            .catch(function () {
              body.innerHTML = '<p class="access-muted">Не удалось загрузить матрицу прав. Попробуйте ещё раз.</p>';
            });
        });
      });
  
      if (closeBtn) closeBtn.addEventListener('click', closeModal);
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
      });
  
    });
  })();