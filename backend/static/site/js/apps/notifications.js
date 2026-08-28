(function () {
  'use strict';

  function t(text) {
    return (window.BPM && window.BPM.t) ? window.BPM.t(text, text) : text;
  }

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.getElementById('bpmNotifRoot');
    if (!root) return;

    var toggle       = document.getElementById('bpmNotifToggle');
    var badge        = document.getElementById('bpmNotifBadge');
    var countEl      = document.getElementById('bpmNotifCount');
    var listEl       = document.getElementById('bpmNotifList');
    var footerEl     = document.getElementById('bpmNotifFooter');
    var markAllBtn   = document.getElementById('bpmNotifMarkAllRead');
    var clearReadBtn = document.getElementById('bpmNotifClearRead');
    var clearAllBtn  = document.getElementById('bpmNotifClearAll');

    var POLL_INTERVAL = 30000;
    var items = [];
    var isOpen = false;
    var isBusy = false;

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
            var err = new Error(body.detail || ('HTTP ' + res.status));
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
      div.textContent = text == null ? '' : String(text);
      return div.innerHTML;
    }

    function formatDate(iso) {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }

    function unreadCount() {
      return items.filter(function (n) { return !n.is_read; }).length;
    }

    function updateBadge() {
      var count = unreadCount();
      if (count > 0) {
        badge.textContent = count > 99 ? '99+' : String(count);
        badge.hidden = false;
        countEl.textContent = String(count);
        countEl.hidden = false;
        markAllBtn.hidden = false;
      } else {
        badge.hidden = true;
        countEl.hidden = true;
        markAllBtn.hidden = true;
      }
      footerEl.hidden = items.length === 0;
    }

    function itemHtml(n) {
      var unread = !n.is_read;
      var href = n.url || '#';
      return (
        '<div class="bpm-notif__item' + (unread ? ' bpm-notif__item--unread' : '') + '" data-notif-id="' + n.id + '">' +
          '<a href="' + escapeHtml(href) + '" class="bpm-notif__item-link" data-notif-open="' + n.id + '">' +
            '<div class="bpm-notif__item-head">' +
              (unread ? '<span class="bpm-notif__dot" aria-hidden="true"></span>' : '') +
              '<span class="bpm-notif__title">' + escapeHtml(n.title) + '</span>' +
              '<span class="bpm-notif__time">' + formatDate(n.created_date) + '</span>' +
            '</div>' +
            (n.text ? '<div class="bpm-notif__text">' + escapeHtml(n.text) + '</div>' : '') +
          '</a>' +
          '<button type="button" class="bpm-notif__delete" data-notif-dismiss="' + n.id + '" ' +
            'title="' + t('Удалить') + '" aria-label="' + t('Удалить') + '">' +
            '<i class="bi bi-x-lg"></i>' +
          '</button>' +
        '</div>'
      );
    }

    function render() {
      if (!items.length) {
        listEl.innerHTML =
          '<div class="bpm-notif__empty">' +
            '<i class="bi bi-bell-slash"></i>' +
            '<span>' + t('Список уведомлений пуст') + '</span>' +
          '</div>';
      } else {
        listEl.innerHTML = items.map(itemHtml).join('');
      }
      updateBadge();

      if (window.BPM && window.BPM.applyTranslations) {
        window.BPM.applyTranslations();
      }

      listEl.querySelectorAll('[data-notif-open]').forEach(function (link) {
        link.addEventListener('click', function (e) {
          var id = parseInt(link.getAttribute('data-notif-open'), 10);
          var item = items.find(function (n) { return n.id === id; });
          if (!item || !item.url) e.preventDefault();
          markRead(id);
        });
      });
      listEl.querySelectorAll('[data-notif-dismiss]').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          dismissOne(parseInt(btn.getAttribute('data-notif-dismiss'), 10));
        });
      });
    }

    function loadNotifications() {
      return apiFetch('/api/v1/notifications/')
        .then(function (data) {
          items = Array.isArray(data) ? data : [];
          render();
        })
        .catch(function () {
          if (isOpen) {
            listEl.innerHTML = '<div class="bpm-notif__empty"><i class="bi bi-exclamation-triangle"></i><span>' +
              t('Не удалось загрузить уведомления') + '</span></div>';
          }
        });
    }

    function markRead(id) {
      var item = items.find(function (n) { return n.id === id; });
      if (!item || item.is_read) return;
      item.is_read = true;
      updateBadge();
      var el = listEl.querySelector('[data-notif-id="' + id + '"]');
      if (el) {
        el.classList.remove('bpm-notif__item--unread');
        var dot = el.querySelector('.bpm-notif__dot');
        if (dot) dot.remove();
      }
      apiFetch('/api/v1/notifications/' + id + '/mark-read/', { method: 'POST' }).catch(function () {});
    }

    function dismissOne(id) {
      var el = listEl.querySelector('[data-notif-id="' + id + '"]');
      if (el) el.classList.add('bpm-notif__item--removing');
      apiFetch('/api/v1/notifications/' + id + '/dismiss/', { method: 'DELETE' })
        .then(function () {
          items = items.filter(function (n) { return n.id !== id; });
          render();
        })
        .catch(function () {
          if (el) el.classList.remove('bpm-notif__item--removing');
          notifyActionError();
        });
    }

    function notifyActionError() {
      var msg = t('Не удалось выполнить действие');
      if (window.bpmModal) window.bpmModal.alert(msg, { variant: 'danger', title: t('Ошибка') });
      else window.alert(msg);
    }

    function runBulkAction(promiseFactory) {
      if (isBusy) return;
      isBusy = true;
      markAllBtn.disabled = true;
      clearReadBtn.disabled = true;
      clearAllBtn.disabled = true;
      promiseFactory()
        .then(loadNotifications)
        .catch(notifyActionError)
        .finally(function () {
          isBusy = false;
          markAllBtn.disabled = false;
          clearReadBtn.disabled = false;
          clearAllBtn.disabled = false;
        });
    }

    async function confirmAction(message, opts) {
      if (window.bpmModal) {
        return window.bpmModal.confirm(message, Object.assign({ title: t('Подтверждение'), variant: 'danger' }, opts || {}));
      }
      return window.confirm(message);
    }

    markAllBtn.addEventListener('click', async function () {
      var ok = await confirmAction(t('Отметить все уведомления как прочитанные?'), { variant: 'info', confirmText: t('Отметить все как прочитанные') });
      if (!ok) return;
      runBulkAction(function () {
        var unread = items.filter(function (n) { return !n.is_read; });
        return Promise.all(unread.map(function (n) {
          return apiFetch('/api/v1/notifications/' + n.id + '/mark-read/', { method: 'POST' });
        }));
      });
    });

    clearReadBtn.addEventListener('click', async function () {
      var ok = await confirmAction(t('Удалить все прочитанные уведомления?'), { confirmText: t('Удалить прочитанные') });
      if (!ok) return;
      runBulkAction(function () {
        return apiFetch('/api/v1/notifications/dismiss-read/', { method: 'DELETE' });
      });
    });

    clearAllBtn.addEventListener('click', async function () {
      var ok = await confirmAction(t('Удалить все уведомления? Это действие нельзя отменить.'), { confirmText: t('Удалить все') });
      if (!ok) return;
      runBulkAction(function () {
        return apiFetch('/api/v1/notifications/dismiss-all/', { method: 'DELETE' });
      });
    });

    root.addEventListener('show.bs.dropdown', function () {
      isOpen = true;
      loadNotifications();
    });
    root.addEventListener('hide.bs.dropdown', function () {
      isOpen = false;
    });

    loadNotifications();
    setInterval(function () {
      if (!isOpen) loadNotifications();
    }, POLL_INTERVAL);
  });
})();
