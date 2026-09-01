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
    comment: 'Комментарии',
    dashboard: 'Дашборд',
    ecopark: 'Эксплуатация',
    profile: 'Профиль',
    reports: 'Показатели',
  };
  var OPERATION_LABELS = { view: 'Просмотр', create: 'Создание', edit: 'Изменение', delete: 'Удаление' };
  var STATUS_LABELS = { active: 'Активен', revoked: 'Отозван', expired: 'Истёк' };

  function t(ru) { return window.BPM ? window.BPM.t(ru, ru) : ru; }

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
          var msg = body.error || body.detail;
          if (!msg && typeof body === 'object') {
            var firstKey = Object.keys(body)[0];
            if (firstKey) msg = Array.isArray(body[firstKey]) ? body[firstKey][0] : body[firstKey];
          }
          var err = new Error(msg || ('HTTP ' + res.status));
          err.body = body;
          throw err;
        });
      }
      if (res.status === 204) return null;
      return res.json();
    });
  }

  // API отдаёт даты уже в готовом для показа виде (REST_FRAMEWORK.DATETIME_FORMAT
  // = "%d.%m.%Y, %H:%M"), поэтому для таблицы достаточно использовать строку
  // как есть — здесь только разбор для предзаполнения <input type="datetime-local">.
  function parseServerDateTime(str) {
    var m = /^(\d{2})\.(\d{2})\.(\d{4}),?\s*(\d{2}):(\d{2})/.exec(str || '');
    if (!m) return '';
    return m[3] + '-' + m[2] + '-' + m[1] + 'T' + m[4] + ':' + m[5];
  }

  document.addEventListener('DOMContentLoaded', function () {
    var page = document.getElementById('taPage');
    if (!page) return;

    var tableBody = document.getElementById('taTableBody');
    var emptyState = document.getElementById('taEmpty');
    var tabs = document.querySelectorAll('.ta-tab');
    var grantForm = document.getElementById('taGrantForm');
    var grantError = document.getElementById('taGrantError');
    var grantSubmit = document.getElementById('taGrantSubmit');
    var userSelect = document.getElementById('taUserSelect');
    var permSelect = document.getElementById('taPermSelect');

    var extendModal = document.getElementById('taExtendModal');
    var extendSubtitle = document.getElementById('taExtendSubtitle');
    var extendDateTo = document.getElementById('taExtendDateTo');
    var extendError = document.getElementById('taExtendError');
    var extendConfirmBtn = document.getElementById('taExtendConfirm');
    var extendCloseBtn = extendModal.querySelector('[data-ta-extend-close]');
    var extendTargetId = null;

    var currentStatus = 'active';
    var catalogCache = null;

    function permOptionLabel(p) {
      var block = BLOCK_LABELS[p.block] ? t(BLOCK_LABELS[p.block]) : (p.block || '');
      var op = p.operation && OPERATION_LABELS[p.operation] ? t(OPERATION_LABELS[p.operation]) : '';
      var parts = [block, op].filter(Boolean);
      var prefix = parts.length ? parts.join(' / ') + ' — ' : '';
      return prefix + (p.label || p.code);
    }

    function loadCatalog() {
      if (catalogCache) return Promise.resolve(catalogCache);
      return apiFetch('/api/v1/permissions/catalog/').then(function (data) {
        catalogCache = Array.isArray(data) ? data : (data.results || []);
        return catalogCache;
      });
    }

    function initPermSelect() {
      loadCatalog().then(function (perms) {
        var byBlock = {};
        var order = [];
        perms.forEach(function (p) {
          var key = p.block || '';
          if (!byBlock[key]) { byBlock[key] = []; order.push(key); }
          byBlock[key].push(p);
        });

        var html = '<option></option>';
        order.forEach(function (block) {
          var label = block ? (BLOCK_LABELS[block] ? t(BLOCK_LABELS[block]) : block) : t('Общие права');
          html += '<optgroup label="' + label + '">';
          byBlock[block].forEach(function (p) {
            html += '<option value="' + p.id + '">' + permOptionLabel(p) + '</option>';
          });
          html += '</optgroup>';
        });
        permSelect.innerHTML = html;

        if (window.jQuery && jQuery.fn.select2) {
          jQuery(permSelect).select2({ theme: 'bootstrap4', width: '100%', placeholder: t('Выберите право'), allowClear: true });
        }
      });
    }

    function initUserSelect() {
      if (!(window.jQuery && jQuery.fn.select2)) return;
      jQuery(userSelect).select2({
        theme: 'bootstrap4',
        width: '100%',
        placeholder: t('Начните вводить имя или логин'),
        minimumInputLength: 1,
        ajax: {
          url: '/api/v1/permissions/users/',
          dataType: 'json',
          delay: 250,
          data: function (params) { return { search: params.term || '' }; },
          processResults: function (data) {
            var results = Array.isArray(data) ? data : (data.results || []);
            return {
              results: results.map(function (u) {
                return { id: u.id, text: (u.full_name || u.username) + ' (@' + u.username + ')' };
              }),
            };
          },
          cache: true,
        },
      });
    }

    function rowActionsHtml(access) {
      if (access.status !== 'active') return '';
      return (
        '<button type="button" class="hr-icon-btn" data-ta-extend title="' + t('Продлить') + '"><i class="bi bi-clock-history"></i></button>' +
        '<button type="button" class="hr-icon-btn hr-icon-btn--danger" data-ta-revoke title="' + t('Отозвать') + '"><i class="bi bi-x-circle"></i></button>'
      );
    }

    function statusBadgeHtml(access) {
      var variant = access.status === 'active' ? 'active' : (access.status === 'expired' ? 'inactive' : 'inactive');
      var label = STATUS_LABELS[access.status] ? t(STATUS_LABELS[access.status]) : access.status;
      return '<span class="access-status access-status--' + variant + '">' + label + '</span>';
    }

    function renderRow(access) {
      var tr = document.createElement('tr');
      tr.className = 'ta-table__row';
      tr.dataset.id = access.id;
      tr.innerHTML =
        '<td>' +
          '<div class="access-user__name">' + (access.user_name || '') + '</div>' +
        '</td>' +
        '<td class="access-muted">' + (BLOCK_LABELS[access.block] ? t(BLOCK_LABELS[access.block]) : (access.block || '—')) + '</td>' +
        '<td class="access-muted">' + (OPERATION_LABELS[access.operation] ? t(OPERATION_LABELS[access.operation]) : (access.operation || '—')) + '</td>' +
        '<td class="access-muted">' + (access.date_from || '—') + '</td>' +
        '<td class="access-muted" data-ta-date-to data-raw="' + (access.date_to || '') + '">' + (access.date_to || '—') + '</td>' +
        '<td class="access-muted">' + (access.reason || '—') + '</td>' +
        '<td class="access-muted">' + (access.granted_by_name || '—') + '</td>' +
        '<td data-ta-status>' + statusBadgeHtml(access) + '</td>' +
        '<td class="ta-table__actions" data-ta-actions>' + rowActionsHtml(access) + '</td>';
      return tr;
    }

    function renderList(items) {
      tableBody.innerHTML = '';
      if (!items.length) {
        emptyState.hidden = false;
        return;
      }
      emptyState.hidden = true;
      items.forEach(function (access) {
        tableBody.appendChild(renderRow(access));
      });
    }

    function loadList(status) {
      currentStatus = status;
      var url = '/api/v1/permissions/temporary/';
      if (status === 'active') url += '?active_only=true';
      else if (status === 'all') url += '';
      else url += '?status=' + encodeURIComponent(status);

      tableBody.innerHTML = '<tr><td colspan="9" class="access-muted" style="text-align:center;padding:24px;">' + t('Загрузка…') + '</td></tr>';
      emptyState.hidden = true;

      apiFetch(url).then(function (data) {
        var items = Array.isArray(data) ? data : (data.results || []);
        renderList(items);
      }).catch(function () {
        tableBody.innerHTML = '';
        emptyState.hidden = false;
      });
    }

    tabs.forEach(function (tab) {
      tab.addEventListener('click', function () {
        tabs.forEach(function (b) { b.classList.remove('is-active'); });
        tab.classList.add('is-active');
        loadList(tab.getAttribute('data-status'));
      });
    });

    function showGrantError(message) {
      grantError.textContent = message;
      grantError.hidden = false;
    }

    grantForm.addEventListener('submit', function (e) {
      e.preventDefault();
      grantError.hidden = true;

      var userId = userSelect.value;
      var permId = permSelect.value;
      var dateFrom = document.getElementById('taDateFrom').value;
      var dateTo = document.getElementById('taDateTo').value;
      var reason = document.getElementById('taReason').value.trim();

      if (!userId || !permId || !dateFrom || !dateTo || !reason) {
        showGrantError(t('Заполните все поля.'));
        return;
      }
      if (dateTo <= dateFrom) {
        showGrantError(t('Дата окончания должна быть позже даты начала.'));
        return;
      }

      grantSubmit.disabled = true;
      apiFetch('/api/v1/permissions/temporary/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user: userId,
          permission: permId,
          date_from: dateFrom,
          date_to: dateTo,
          reason: reason,
        }),
      }).then(function () {
        grantForm.reset();
        jQuery(userSelect).val(null).trigger('change');
        jQuery(permSelect).val(null).trigger('change');
        tabs.forEach(function (b) { b.classList.remove('is-active'); });
        document.querySelector('.ta-tab[data-status="active"]').classList.add('is-active');
        loadList('active');
      }).catch(function (err) {
        showGrantError(err.message);
      }).finally(function () {
        grantSubmit.disabled = false;
      });
    });

    tableBody.addEventListener('click', function (e) {
      var row = e.target.closest('tr[data-id]');
      if (!row) return;
      var id = row.dataset.id;

      if (e.target.closest('[data-ta-revoke]')) {
        if (!window.confirm(t('Отозвать этот временный доступ?'))) return;
        apiFetch('/api/v1/permissions/temporary/' + id + '/revoke/', { method: 'POST' })
          .then(function (updated) {
            row.querySelector('[data-ta-status]').innerHTML = statusBadgeHtml(updated);
            row.querySelector('[data-ta-actions]').innerHTML = rowActionsHtml(updated);
          })
          .catch(function (err) { window.alert(err.message); });
        return;
      }

      if (e.target.closest('[data-ta-extend]')) {
        extendTargetId = id;
        var userName = row.querySelector('.access-user__name').textContent;
        extendSubtitle.textContent = userName;
        extendDateTo.value = parseServerDateTime(row.querySelector('[data-ta-date-to]').getAttribute('data-raw') || '');
        extendError.hidden = true;
        extendModal.classList.add('is-open');
      }
    });

    function closeExtendModal() {
      extendModal.classList.remove('is-open');
      extendTargetId = null;
    }
    extendCloseBtn.addEventListener('click', closeExtendModal);
    extendModal.addEventListener('click', function (e) { if (e.target === extendModal) closeExtendModal(); });

    extendConfirmBtn.addEventListener('click', function () {
      if (!extendTargetId || !extendDateTo.value) {
        extendError.textContent = t('Укажите дату окончания.');
        extendError.hidden = false;
        return;
      }
      extendConfirmBtn.disabled = true;
      apiFetch('/api/v1/permissions/temporary/' + extendTargetId + '/extend/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ date_to: extendDateTo.value }),
      }).then(function (updated) {
        var row = tableBody.querySelector('tr[data-id="' + extendTargetId + '"]');
        if (row) {
          var cell = row.querySelector('[data-ta-date-to]');
          cell.textContent = updated.date_to || '—';
          cell.setAttribute('data-raw', updated.date_to);
        }
        closeExtendModal();
      }).catch(function (err) {
        extendError.textContent = err.message;
        extendError.hidden = false;
      }).finally(function () {
        extendConfirmBtn.disabled = false;
      });
    });

    initPermSelect();
    initUserSelect();
    loadList('active');
  });
})();
