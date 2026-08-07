(function () {
    'use strict';
  
    var BLOCK_LABELS = {
      users: 'Пользователи', documents: 'Документы', finances: 'Финансы', hr: 'HR',
      purchases: 'Закупки', requests: 'Заявки', suppliers: 'Поставщики', tasks: 'Задачи', tenants: 'Арендаторы',
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
      if (opts.method && opts.method !== 'GET') opts.headers['X-CSRFToken'] = getCsrfToken();
      return fetch(url, opts).then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            var err = new Error(body.detail || body.error || JSON.stringify(body) || ('HTTP ' + res.status));
            err.body = body;
            throw err;
          });
        }
        if (res.status === 204) return null;
        return res.json();
      });
    }
  
    document.addEventListener('DOMContentLoaded', function () {
  
      var catalogCache = null;
      function getCatalog() {
        if (catalogCache) return Promise.resolve(catalogCache);
        return apiFetch('/api/v1/permissions/catalog/').then(function (data) {
          var items = Array.isArray(data) ? data : (data.results || []);
          var next = Array.isArray(data) ? null : data.next;
          catalogCache = items;
          function loadMore(url) {
            if (!url) return Promise.resolve(catalogCache);
            return apiFetch(url).then(function (d) {
              catalogCache = catalogCache.concat(d.results || []);
              return loadMore(d.next);
            });
          }
          return loadMore(next);
        });
      }
  
      /* ───────────────── Матрица прав профиля ───────────────── */
      var matrixModal = document.getElementById('profileMatrixModal');
      var matrixBody = matrixModal.querySelector('[data-profile-modal-body]');
      var matrixCloseBtn = matrixModal.querySelector('[data-profile-modal-close]');
      var currentProfile = null;
  
      function openMatrixModal() { matrixModal.classList.add('is-open'); }
      function closeMatrixModal() { matrixModal.classList.remove('is-open'); matrixBody.innerHTML = ''; currentProfile = null; }
  
      function renderMatrixForm() {
        var perms = catalogCache;
        var gridPerms = perms.filter(function (p) { return p.operation; });
        var flatPerms = perms.filter(function (p) { return !p.operation; });
        var selectedIds = (currentProfile.permissions || []).map(function (p) { return p.id; });
  
        var blocks = [];
        gridPerms.forEach(function (p) { if (blocks.indexOf(p.block) === -1) blocks.push(p.block); });
        var operations = OPERATION_ORDER.filter(function (op) { return gridPerms.some(function (p) { return p.operation === op; }); });
  
        var html = '';
        html += '<h3 class="access-modal__title">' + (currentProfile.id ? 'Редактирование профиля' : 'Новый профиль') + '</h3>';
  
        html += '<div class="access-form-row"><label class="access-page__label">Название</label>' +
          '<input type="text" class="access-page__search-input" style="padding-left:16px" id="profileNameInput" value="' +
          (currentProfile.name || '').replace(/"/g, '&quot;') + '" /></div>';
  
        html += '<div class="access-form-row"><label class="access-page__label">Описание</label>' +
          '<input type="text" class="access-page__search-input" style="padding-left:16px" id="profileDescInput" value="' +
          (currentProfile.description || '').replace(/"/g, '&quot;') + '" /></div>';
  
        html += '<div class="access-matrix-wrap"><table class="access-matrix">';
        html += '<thead><tr><th></th>' + operations.map(function (op) {
          return '<th>' + (OPERATION_LABELS[op] || op) + '</th>';
        }).join('') + '</tr></thead><tbody>';
  
        blocks.forEach(function (block) {
          html += '<tr><th class="access-matrix__block">' + (BLOCK_LABELS[block] || block) + '</th>';
          operations.forEach(function (op) {
            var cellPerms = gridPerms.filter(function (p) { return p.block === block && p.operation === op; });
            if (!cellPerms.length) { html += '<td class="access-matrix__cell access-matrix__cell--empty">—</td>'; return; }
            html += '<td class="access-matrix__cell">';
            cellPerms.forEach(function (p) {
              var on = selectedIds.indexOf(p.id) !== -1;
              html += '<label class="access-matrix__item"><input type="checkbox" data-profile-perm-id="' + p.id + '" ' + (on ? 'checked' : '') + ' /><span>' + p.label + '</span></label>';
            });
            html += '</td>';
          });
          html += '</tr>';
        });
        html += '</tbody></table></div>';
  
        if (flatPerms.length) {
          html += '<h4>Общие права</h4><div class="access-matrix__flat">';
          flatPerms.forEach(function (p) {
            var on = selectedIds.indexOf(p.id) !== -1;
            html += '<label class="access-matrix__item"><input type="checkbox" data-profile-perm-id="' + p.id + '" ' + (on ? 'checked' : '') + ' /><span>' + p.label + '</span></label>';
          });
          html += '</div>';
        }
  
        html += '<div class="access-modal__actions">' +
          '<button type="button" class="access-page__btn access-page__btn--light" id="profileCancelBtn">Отмена</button>' +
          '<button type="button" class="access-page__btn access-page__btn--primary" id="profileSaveBtn">Сохранить</button>' +
          '</div>' +
          '<div class="access-modal__error" id="profileFormError" style="display:none;color:#ef4444;font-size:13px;margin-top:8px;"></div>';
  
        matrixBody.innerHTML = html;
        document.getElementById('profileCancelBtn').addEventListener('click', closeMatrixModal);
        document.getElementById('profileSaveBtn').addEventListener('click', saveProfile);
      }
  
      function saveProfile() {
        var errEl = document.getElementById('profileFormError');
        errEl.style.display = 'none';
        var name = document.getElementById('profileNameInput').value.trim();
        var description = document.getElementById('profileDescInput').value.trim();
        if (!name) {
          errEl.textContent = 'Укажите название профиля.';
          errEl.style.display = 'block';
          return;
        }
        var permIds = Array.prototype.slice.call(matrixBody.querySelectorAll('input[data-profile-perm-id]:checked'))
          .map(function (el) { return parseInt(el.getAttribute('data-profile-perm-id'), 10); });
  
        var saveBtn = document.getElementById('profileSaveBtn');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Сохранение…';
  
        var basePromise = currentProfile.id
          ? apiFetch('/api/v1/permissions/profiles/' + currentProfile.id + '/', {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: name, description: description }),
            })
          : apiFetch('/api/v1/permissions/profiles/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ name: name, description: description }),
            });
  
        basePromise
          .then(function (profile) {
            return apiFetch('/api/v1/permissions/profiles/' + profile.id + '/set-permissions/', {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ permission_ids: permIds }),
            });
          })
          .then(function () {
            window.location.reload();
          })
          .catch(function (err) {
            errEl.textContent = 'Не удалось сохранить: ' + err.message;
            errEl.style.display = 'block';
            saveBtn.disabled = false;
            saveBtn.textContent = 'Сохранить';
          });
      }
  
      function openCreateProfile() {
        currentProfile = { id: null, name: '', description: '', permissions: [] };
        openMatrixModal();
        matrixBody.innerHTML = '<div class="access-modal__loading">Загрузка…</div>';
        getCatalog().then(renderMatrixForm);
      }
  
      function openEditProfile(profileId) {
        openMatrixModal();
        matrixBody.innerHTML = '<div class="access-modal__loading">Загрузка…</div>';
        Promise.all([getCatalog(), apiFetch('/api/v1/permissions/profiles/' + profileId + '/')])
          .then(function (results) {
            currentProfile = results[1];
            renderMatrixForm();
          })
          .catch(function () {
            matrixBody.innerHTML = '<p class="access-muted">Не удалось загрузить профиль.</p>';
          });
      }
  
      document.getElementById('createProfileBtn').addEventListener('click', openCreateProfile);
      document.querySelectorAll('[data-edit-profile]').forEach(function (btn) {
        btn.addEventListener('click', function () { openEditProfile(btn.getAttribute('data-edit-profile')); });
      });
      matrixCloseBtn.addEventListener('click', closeMatrixModal);
      matrixModal.addEventListener('click', function (e) { if (e.target === matrixModal) closeMatrixModal(); });
  
      /* ───────────────── Назначение профиля + предпросмотр ───────────────── */
      var assignModal = document.getElementById('assignModal');
      var assignBody = assignModal.querySelector('[data-assign-modal-body]');
      var assignCloseBtn = assignModal.querySelector('[data-assign-modal-close]');
  
      function openAssignModal() { assignModal.classList.add('is-open'); }
      function closeAssignModal() { assignModal.classList.remove('is-open'); assignBody.innerHTML = ''; }
  
      function renderAssignForm(profileId, profileName) {
        var roleOptions = (window.ACCESS_ROLES || []).map(function (r) {
          return '<option value="' + r.value + '">' + r.label + '</option>';
        }).join('');
        var deptOptions = (window.ACCESS_DEPARTMENTS || []).map(function (d) {
          return '<option value="' + d.id + '">' + d.name + '</option>';
        }).join('');
  
        var html = '';
        html += '<h3 class="access-modal__title">Назначить профиль «' + profileName + '»</h3>';
        html += '<div class="access-form-row"><label class="access-page__label">Тип группы</label>' +
          '<select id="assignScopeType" class="access-page__search-input" style="padding-left:16px">' +
          '<option value="role">По роли</option><option value="department">По отделу</option>' +
          '</select></div>';
        html += '<div class="access-form-row" id="assignRoleRow"><label class="access-page__label">Роль</label>' +
          '<select id="assignRoleSelect" class="access-page__search-input" style="padding-left:16px">' + roleOptions + '</select></div>';
        html += '<div class="access-form-row" id="assignDeptRow" style="display:none"><label class="access-page__label">Отдел</label>' +
          '<select id="assignDeptSelect" class="access-page__search-input" style="padding-left:16px">' + deptOptions + '</select></div>';
        html += '<div class="access-form-row"><label class="access-page__item"><input type="checkbox" id="assignCanDelegate" /> Разрешить делегирование</label></div>';
  
        html += '<div class="access-preview-box" id="assignPreviewBox"><div class="access-modal__loading">Считаем затронутых сотрудников…</div></div>';
  
        html += '<div class="access-modal__actions">' +
          '<button type="button" class="access-page__btn access-page__btn--light" id="assignCancelBtn">Отмена</button>' +
          '<button type="button" class="access-page__btn access-page__btn--primary" id="assignConfirmBtn" disabled>Подтвердить применение</button>' +
          '</div>' +
          '<div class="access-modal__error" id="assignFormError" style="display:none;color:#ef4444;font-size:13px;margin-top:8px;"></div>';
  
        assignBody.innerHTML = html;
  
        var scopeSelect = document.getElementById('assignScopeType');
        var roleRow = document.getElementById('assignRoleRow');
        var deptRow = document.getElementById('assignDeptRow');
        var roleSelect = document.getElementById('assignRoleSelect');
        var deptSelect = document.getElementById('assignDeptSelect');
        var previewBox = document.getElementById('assignPreviewBox');
        var confirmBtn = document.getElementById('assignConfirmBtn');
  
        function refreshPreview() {
          confirmBtn.disabled = true;
          previewBox.innerHTML = '<div class="access-modal__loading">Считаем затронутых сотрудников…</div>';
          var scopeType = scopeSelect.value;
          var query = scopeType === 'role' ? ('role=' + encodeURIComponent(roleSelect.value)) : ('department=' + encodeURIComponent(deptSelect.value));
          apiFetch('/api/v1/permissions/users/?' + query + '&page_size=1000')
            .then(function (data) {
              var items = data.results || (Array.isArray(data) ? data : []);
              var count = typeof data.count === 'number' ? data.count : items.length;
              var names = items.slice(0, 8).map(function (u) { return u.full_name || u.username; });
              var extra = count > names.length ? (' и ещё ' + (count - names.length)) : '';
              previewBox.innerHTML =
                '<div class="access-preview-box__count">Будет затронуто: <strong>' + count + '</strong> сотрудник(ов)</div>' +
                (names.length ? '<div class="access-muted">' + names.join(', ') + extra + '</div>' : '<div class="access-muted">Никто не подпадает под этот критерий</div>');
              confirmBtn.disabled = count === 0;
            })
            .catch(function () {
              previewBox.innerHTML = '<div class="access-muted">Не удалось посчитать сотрудников.</div>';
            });
        }
  
        scopeSelect.addEventListener('change', function () {
          var isRole = scopeSelect.value === 'role';
          roleRow.style.display = isRole ? '' : 'none';
          deptRow.style.display = isRole ? 'none' : '';
          refreshPreview();
        });
        roleSelect.addEventListener('change', refreshPreview);
        deptSelect.addEventListener('change', refreshPreview);
  
        document.getElementById('assignCancelBtn').addEventListener('click', closeAssignModal);
        confirmBtn.addEventListener('click', function () {
          var errEl = document.getElementById('assignFormError');
          errEl.style.display = 'none';
          var scopeType = scopeSelect.value;
          var payload = {
            profile: profileId,
            scope_type: scopeType,
            can_delegate: document.getElementById('assignCanDelegate').checked,
          };
          if (scopeType === 'role') payload.role = roleSelect.value;
          else payload.department = parseInt(deptSelect.value, 10);
  
          confirmBtn.disabled = true;
          confirmBtn.textContent = 'Применяем…';
          apiFetch('/api/v1/permissions/assignments/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          })
            .then(function () { window.location.reload(); })
            .catch(function (err) {
              errEl.textContent = 'Не удалось применить: ' + err.message;
              errEl.style.display = 'block';
              confirmBtn.disabled = false;
              confirmBtn.textContent = 'Подтвердить применение';
            });
        });
  
        refreshPreview();
      }
  
      document.querySelectorAll('[data-assign-profile]').forEach(function (btn) {
        btn.addEventListener('click', function () {
          openAssignModal();
          renderAssignForm(btn.getAttribute('data-assign-profile'), btn.getAttribute('data-profile-name'));
        });
      });
      assignCloseBtn.addEventListener('click', closeAssignModal);
      assignModal.addEventListener('click', function (e) { if (e.target === assignModal) closeAssignModal(); });
  
      document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape') return;
        if (matrixModal.classList.contains('is-open')) closeMatrixModal();
        if (assignModal.classList.contains('is-open')) closeAssignModal();
      });
    });
  })();