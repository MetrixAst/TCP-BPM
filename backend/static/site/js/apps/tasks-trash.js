(function () {
  'use strict';

  function t(text) {
    return (window.BPM && window.BPM.t) ? window.BPM.t(text, text) : text;
  }
  
    var RETENTION_DAYS = 30; // держим в синхроне с settings.py: kwargs={'days': 30}
  
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
            var err = new Error(body.detail || body.message || ('HTTP ' + res.status));
            err.body = body;
            throw err;
          });
        }
        if (res.status === 204) return null;
        return res.json();
      });
    }
  
    function escapeHtml(text) {
      var div = document.createElement('div');
      div.textContent = text == null ? '' : text;
      return div.innerHTML;
    }
  
 // Бэкенд отдаёт datetime в формате "%d.%m.%Y, %H:%M" (project/settings.py DATETIME_FORMAT),
    // не в ISO — парсим вручную вместо new Date(iso).
    function parseServerDateTime(str) {
      if (!str) return null;
      var m = String(str).match(/^(\d{2})\.(\d{2})\.(\d{4}),?\s*(\d{2}):(\d{2})/);
      if (!m) return null;
      return new Date(m[3], m[2] - 1, m[1], m[4], m[5]);
    }

    function formatDate(raw) {
      var d = parseServerDateTime(raw);
      if (!d) return '—';
      return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }

    function purgeDate(raw) {
      var d = parseServerDateTime(raw);
      if (!d) return '—';
      d.setDate(d.getDate() + RETENTION_DAYS);
      var now = new Date();
      var daysLeft = Math.ceil((d - now) / (1000 * 60 * 60 * 24));
      var label = d.toLocaleDateString('ru-RU');
      var purgeText = t('через {n} дн.').replace('{n}', daysLeft);
      if (daysLeft <= 0) return label + ' (' + t('сегодня-завтра') + ')';
      if (daysLeft <= 3) return '<span class="trash-purge-soon">' + label + ' (' + purgeText + ')</span>';
      return label + ' (' + purgeText + ')';
    }
  
    document.addEventListener('DOMContentLoaded', function () {
      var page = document.getElementById('tasksTrashPage');
      if (!page) return;
  
      var tbody = document.getElementById('trashTableBody');
      var searchInput = document.getElementById('trashSearch');
      var modal = document.getElementById('trashViewModal');
      var modalBody = modal.querySelector('[data-trash-modal-body]');
      var modalCloseBtn = modal.querySelector('[data-trash-modal-close]');
  
      var allItems = [];
  
      function renderRows(items) {
        if (!items.length) {
          tbody.innerHTML =
            '<tr><td colspan="7" class="tasks-table__empty">' +
              '<div class="tasks-empty"><i class="bi bi-trash tasks-empty__icon"></i>' +
              '<div class="tasks-empty__title">' + t('Корзина пуста') + '</div></div>' +
            '</td></tr>';
          return;
        }
  
        tbody.innerHTML = items.map(function (task) {
          var authorName = task.author ? (task.author.full_name || task.author.username) : '—';
          var deletedByName = task.deleted_by ? (task.deleted_by.full_name || task.deleted_by.username) : '—';
          return (
            '<tr class="tasks-table__row" data-task-id="' + task.id + '">' +
              '<td class="tasks-table__td tasks-table__td--title">' + escapeHtml(task.title) + '</td>' +
              '<td class="tasks-table__td">' + escapeHtml(authorName) + '</td>' +
              '<td class="tasks-table__td">' + escapeHtml(deletedByName) + '</td>' +
              '<td class="tasks-table__td tasks-table__td--date">' + formatDate(task.deleted_at) + '</td>' +
              '<td class="tasks-table__td">' + escapeHtml(task.deleted_reason || '—') + '</td>' +
              '<td class="tasks-table__td">' + purgeDate(task.deleted_at) + '</td>' +
              '<td class="tasks-table__td">' +
                '<button type="button" class="tasks-page__btn tasks-page__btn--outline" data-trash-view="' + task.id + '">' + t('Просмотр') + '</button> ' +
                '<button type="button" class="tasks-page__btn tasks-page__btn--primary" data-trash-restore="' + task.id + '">' + t('Восстановить') + '</button>' +
              '</td>' +
            '</tr>'
          );
        }).join('');

        if (window.BPM && window.BPM.applyTranslations) {
          window.BPM.applyTranslations();
        }

        tbody.querySelectorAll('[data-trash-view]').forEach(function (btn) {
          btn.addEventListener('click', function () { openViewModal(btn.getAttribute('data-trash-view')); });
        });
        tbody.querySelectorAll('[data-trash-restore]').forEach(function (btn) {
          btn.addEventListener('click', function () { restoreTask(btn.getAttribute('data-trash-restore'), btn); });
        });
      }
  
      function applySearch() {
        var q = (searchInput.value || '').trim().toLowerCase();
        if (!q) { renderRows(allItems); return; }
        renderRows(allItems.filter(function (t) { return (t.title || '').toLowerCase().indexOf(q) !== -1; }));
      }
  
      function loadBin() {
        tbody.innerHTML = '<tr><td colspan="7" class="tasks-table__empty"><div class="tasks-empty__title">' + t('Загрузка…') + '</div></td></tr>';
        apiFetch('/api/v1/tasks/bin/?page_size=500')
          .then(function (data) {
            allItems = data.results || (Array.isArray(data) ? data : []);
            renderRows(allItems);
          })
          .catch(function (err) {
            tbody.innerHTML = '<tr><td colspan="7" class="tasks-table__empty"><div class="tasks-empty__title">' + t('Не удалось загрузить корзину: ') + escapeHtml(err.message) + '</div></td></tr>';
          });
      }
  
      function restoreTask(id, btn) {
        if (!window.confirm(t('Восстановить задачу? Она снова появится в общем списке.'))) return;
        btn.disabled = true;
        apiFetch('/api/v1/tasks/' + id + '/restore/', { method: 'POST' })
          .then(function () {
            allItems = allItems.filter(function (t) { return String(t.id) !== String(id); });
            applySearch();
          })
          .catch(function (err) {
            window.alert(t('Не удалось восстановить: ') + err.message);
            btn.disabled = false;
          });
      }
  
      function openViewModal(id) {
        var task = allItems.find(function (t) { return String(t.id) === String(id); });
        if (!task) return;
        modal.classList.add('is-open');
  
        var coExecutors = (task.co_executor_ids || []).length;
        var observers = (task.observer_ids || []).length;
  
        modalBody.innerHTML =
          '<h3 class="trash-modal__title">' + escapeHtml(task.title) + '</h3>' +
          '<p class="access-muted">' + escapeHtml(task.text || '') + '</p>' +
          '<div class="trash-modal__section">' +
            '<h4>' + t('Сохранённые связи') + '</h4>' +
            '<div class="trash-modal__row"><span>' + t('Автор') + '</span><span>' + escapeHtml(task.author ? (task.author.full_name || task.author.username) : '—') + '</span></div>' +
            '<div class="trash-modal__row"><span>' + t('Исполнитель') + '</span><span>' + escapeHtml(task.executor ? (task.executor.full_name || task.executor.username) : '—') + '</span></div>' +
            '<div class="trash-modal__row"><span>' + t('Соисполнители') + '</span><span>' + coExecutors + '</span></div>' +
            '<div class="trash-modal__row"><span>' + t('Наблюдатели') + '</span><span>' + observers + '</span></div>' +
            '<div class="trash-modal__row"><span>' + t('Комментариев в истории') + '</span><span>' + ((task.history || []).length) + '</span></div>' +
          '</div>' +
          '<div class="trash-modal__section">' +
            '<h4>' + t('Удаление') + '</h4>' +
            '<div class="trash-modal__row"><span>' + t('Кто удалил') + '</span><span>' + escapeHtml(task.deleted_by ? (task.deleted_by.full_name || task.deleted_by.username) : '—') + '</span></div>' +
            '<div class="trash-modal__row"><span>' + t('Когда') + '</span><span>' + formatDate(task.deleted_at) + '</span></div>' +
            '<div class="trash-modal__row"><span>' + t('Причина') + '</span><span>' + escapeHtml(task.deleted_reason || '—') + '</span></div>' +
          '</div>';

        if (window.BPM && window.BPM.applyTranslations) {
          window.BPM.applyTranslations();
        }
      }
  
      function closeModal() { modal.classList.remove('is-open'); modalBody.innerHTML = ''; }
      modalCloseBtn.addEventListener('click', closeModal);
      modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
      document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && modal.classList.contains('is-open')) closeModal(); });
  
      var searchTimer;
      searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(applySearch, 250);
      });
  
      loadBin();
    });
  })();