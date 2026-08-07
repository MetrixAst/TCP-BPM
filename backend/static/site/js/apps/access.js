(function () {
    'use strict';
  
    var BLOCK_LABELS = {
      users: 'Пользователи',
      documents: 'Документы',
      finances: 'Финансы',
      hr: 'HR',
      purchases: 'Закупки',
      requests: 'Заявки',
      suppliers: 'Поставщики',
      tasks: 'Задачи',
      tenants: 'Арендаторы',
    };
    var FLAT_BLOCK_LABELS = {
      comment: 'Комментарии',
      dashboard: 'Дашборд',
      ecopark: 'Эксплуатация',
      profile: 'Профиль',
      reports: 'Показатели',
    };
    var OPERATION_LABELS = { view: 'Просмотр', create: 'Создание', edit: 'Изменение', delete: 'Удаление' };
    var OPERATION_ORDER = ['view', 'create', 'edit', 'delete'];
  
    function getCsrfToken() {
      var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      return match ? decodeURIComponent(match[1]) : '';
    }
  
    function apiFetch(url, options) {
      var opts = Object.assign({ credentials: 'same-origin' }, options || {});
      opts.headers = Object.assign({ 'X-Requested-With': 'XMLHttpRequest' }, opts.headers || {});
      if (opts.method && opts.method !== 'GET') {
        opts.headers['X-CSRFToken'] = getCsrfToken();
      }
      return fetch(url, opts).then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            var err = new Error(body.detail || body.error || ('HTTP ' + res.status));
            err.body = body;
            throw err;
          });
        }
        if (res.status === 204) return null;
        return res.json();
      });
    }
  
    document.addEventListener('DOMContentLoaded', function () {
  
      if (window.jQuery && jQuery.fn.select2) {
        jQuery('.access-page__select--select2').select2({ theme: 'bootstrap4', width: '160px' });
      }
  
      var modal = document.getElementById('accessMatrixModal');
      if (!modal) return;
  
      var body = modal.querySelector('[data-access-modal-body]');
      var closeBtn = modal.querySelector('[data-access-modal-close]');
      var rows = document.querySelectorAll('.access-table__row');
  
      var catalogCache = null;
      var currentUserId = null;
      var currentUserName = '';
      var currentUsername = '';
      var currentRole = '';
      var currentRolePerms = [];
      var currentOverrides = []; // [{id, permission_code, effect, reason}]
  
      function openModal() { modal.classList.add('is-open'); }
      function closeModal() { modal.classList.remove('is-open'); body.innerHTML = '<div class="access-modal__loading">Загрузка…</div>'; }
  
      function getCatalog() {
        if (catalogCache) return Promise.resolve(catalogCache);
        return apiFetch('/api/v1/permissions/catalog/').then(function (data) {
          catalogCache = Array.isArray(data) ? data : (data.results || []);
          return catalogCache;
        });
      }
  
      function findOverride(code) {
        return currentOverrides.find(function (o) { return o.permission_code === code; }) || null;
      }
  
      function cellState(code) {
        var inherited = currentRolePerms.indexOf(code) !== -1;
        var override = findOverride(code);
        if (override) {
          return { on: override.effect === 'ALLOW', source: override.effect === 'ALLOW' ? 'allow' : 'deny', override: override };
        }
        return { on: inherited, source: inherited ? 'inherited' : 'none', override: null };
      }
  
      function render() {
        var perms = catalogCache;
        var gridPerms = perms.filter(function (p) { return p.operation; });
        var flatPerms = perms.filter(function (p) { return !p.operation; });
  
        var blocks = [];
        gridPerms.forEach(function (p) {
          if (blocks.indexOf(p.block) === -1) blocks.push(p.block);
        });
        var operations = OPERATION_ORDER.filter(function (op) {
          return gridPerms.some(function (p) { return p.operation === op; });
        });
  
        var html = '';
        html += '<h3 class="access-modal__title">' + (currentUserName || currentUsername) + '</h3>';
        html += '<p class="access-muted">@' + currentUsername + ' · роль: ' + currentRole + '</p>';
  
        html += '<div class="access-matrix-wrap"><table class="access-matrix">';
        html += '<thead><tr><th></th>' + operations.map(function (op) {
          return '<th>' + (OPERATION_LABELS[op] || op) + '</th>';
        }).join('') + '</tr></thead><tbody>';
  
        blocks.forEach(function (block) {
          html += '<tr><th class="access-matrix__block">' + (BLOCK_LABELS[block] || block) + '</th>';
          operations.forEach(function (op) {
            var cellPerms = gridPerms.filter(function (p) { return p.block === block && p.operation === op; });
            if (!cellPerms.length) {
              html += '<td class="access-matrix__cell access-matrix__cell--empty">—</td>';
              return;
            }
            html += '<td class="access-matrix__cell">';
            cellPerms.forEach(function (p) {
              var st = cellState(p.code);
              html +=
                '<label class="access-matrix__item access-matrix__item--' + st.source + '">' +
                  '<input type="checkbox" data-perm-code="' + p.code + '" ' + (st.on ? 'checked' : '') + ' />' +
                  '<span>' + p.label + '</span>' +
                '</label>';
            });
            html += '</td>';
          });
          html += '</tr>';
        });
        html += '</tbody></table></div>';
  
        if (flatPerms.length) {
          html += '<h4>Общие права</h4><div class="access-matrix__flat">';
          flatPerms.forEach(function (p) {
            var st = cellState(p.code);
            html +=
              '<label class="access-matrix__item access-matrix__item--' + st.source + '">' +
                '<input type="checkbox" data-perm-code="' + p.code + '" ' + (st.on ? 'checked' : '') + ' />' +
                '<span>' + p.label + '</span>' +
              '</label>';
          });
          html += '</div>';
        }
  
        html += '<div class="access-matrix__legend">' +
          '<span class="access-matrix__legend-item access-matrix__legend-item--inherited">унаследовано от роли</span>' +
          '<span class="access-matrix__legend-item access-matrix__legend-item--allow">добавлено индивидуально</span>' +
          '<span class="access-matrix__legend-item access-matrix__legend-item--deny">исключено индивидуально</span>' +
        '</div>';
  
        body.innerHTML = html;
        body.querySelectorAll('input[data-perm-code]').forEach(function (input) {
          input.addEventListener('change', onToggle);
        });
      }
  
      function onToggle(e) {
        var input = e.target;
        var code = input.getAttribute('data-perm-code');
        var wantOn = input.checked;
        var inherited = currentRolePerms.indexOf(code) !== -1;
        var override = findOverride(code);
  
        input.disabled = true;
  
        var request;
        if (wantOn === inherited) {
          // возвращаемся к дефолту роли — override больше не нужен
          request = override
            ? apiFetch('/api/v1/permissions/users/' + currentUserId + '/overrides/' + override.id + '/', { method: 'DELETE' })
                .then(function () { currentOverrides = currentOverrides.filter(function (o) { return o.id !== override.id; }); })
            : Promise.resolve();
        } else {
          var effect = wantOn ? 'ALLOW' : 'DENY';
          if (override) {
            request = apiFetch('/api/v1/permissions/users/' + currentUserId + '/overrides/' + override.id + '/', {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ effect: effect }),
            }).then(function (data) {
              override.effect = data.effect;
            });
          } else {
            request = apiFetch('/api/v1/permissions/users/' + currentUserId + '/overrides/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ permission_code: code, effect: effect }),
            }).then(function (data) {
              currentOverrides.push(data);
            });
          }
        }
  
        request
          .then(function () { render(); })
          .catch(function (err) {
            input.checked = !wantOn;
            input.disabled = false;
            window.alert('Не удалось сохранить изменение: ' + err.message);
          });
      }
  
      function loadUser(userId, userName, username) {
        currentUserId = userId;
        currentUserName = userName;
        currentUsername = username;
        openModal();
        body.innerHTML = '<div class="access-modal__loading">Загрузка…</div>';
  
        Promise.all([
          getCatalog(),
          apiFetch('/api/v1/permissions/users/' + userId + '/'),
        ]).then(function (results) {
          var userData = results[1];
          currentRole = userData.role;
          currentRolePerms = userData.role_permissions || [];
          currentOverrides = (userData.overrides || []).map(function (o) {
            return { id: o.id, permission_code: o.permission_code, effect: o.effect, reason: o.reason };
          });
          render();
        }).catch(function () {
          body.innerHTML = '<p class="access-muted">Не удалось загрузить матрицу прав. Попробуйте ещё раз.</p>';
        });
      }
  
      rows.forEach(function (row) {
        row.addEventListener('click', function () {
          var userId = row.getAttribute('data-user-id');
          var name = row.getAttribute('data-user-name') || '';
          var username = row.querySelector('.access-user__meta') ? row.querySelector('.access-user__meta').textContent.replace('@', '') : '';
          loadUser(userId, name, username);
        });
      });
  
      if (closeBtn) closeBtn.addEventListener('click', closeModal);
      modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && modal.classList.contains('is-open')) closeModal();
      });
    });
  })();