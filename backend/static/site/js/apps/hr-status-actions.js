(function () {
  'use strict';

  function t(text) {
    return (window.BPM && window.BPM.t) ? window.BPM.t(text, text) : text;
  }
  
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
      div.textContent = text == null ? '' : text;
      return div.innerHTML;
    }
  
    // Открывает диалог. targets — массив { id, name, status } (1 или много).
    // action — 'activate' | 'deactivate'. Возвращает Promise<string|null> (причина или null при отмене).
    function openStatusDialog(action, targets) {
      return new Promise(function (resolve) {
        var isDeactivate = action === 'deactivate';
        var title = isDeactivate ? t('Деактивировать сотрудника') : t('Активировать сотрудника');
        if (targets.length > 1) {
          title = isDeactivate ? t('Деактивировать сотрудников (') + targets.length + ')' : t('Активировать сотрудников (') + targets.length + ')';
        }
  
        var listHtml = targets.map(function (t) {
          return '<div class="hr-status-dialog__person">' +
            '<span class="hr-status-dialog__person-name">' + escapeHtml(t.name) + '</span>' +
            (t.status ? '<span class="hr-status-dialog__person-status">' + escapeHtml(t.status) + '</span>' : '') +
          '</div>';
        }).join('');
  
        var overlay = document.createElement('div');
        overlay.className = 'hr-status-dialog';
        overlay.innerHTML =
          '<div class="hr-status-dialog__box" role="dialog" aria-modal="true">' +
            '<h3 class="hr-status-dialog__title">' + title + '</h3>' +
            '<div class="hr-status-dialog__people">' + listHtml + '</div>' +
            (isDeactivate
              ? '<label class="hr-status-dialog__label">' + t('Причина деактивации (минимум 5 символов)') + '</label>' +
                '<textarea class="hr-status-dialog__textarea" data-reason rows="3" placeholder="' + t('Например: увольнение по собственному желанию') + '"></textarea>' +
                '<p class="hr-status-dialog__error" data-error style="display:none"></p>'
              : '<label class="hr-status-dialog__label">' + t('Комментарий (необязательно)') + '</label>' +
                '<textarea class="hr-status-dialog__textarea" data-reason rows="2" placeholder="' + t('Например: возвращение из отпуска') + '"></textarea>'
            ) +
            '<div class="hr-status-dialog__actions">' +
              '<button type="button" class="hr-btn hr-btn--light" data-cancel>' + t('Отмена') + '</button>' +
              '<button type="button" class="hr-btn ' + (isDeactivate ? 'hr-btn--danger' : 'hr-btn--primary') + '" data-confirm>' +
                (isDeactivate ? t('Деактивировать') : t('Активировать')) +
              '</button>' +
            '</div>' +
          '</div>';
        (document.getElementById('bpmMain') || document.body).appendChild(overlay);

        if (window.BPM && window.BPM.applyTranslations) {
          window.BPM.applyTranslations();
        }
  
        var textarea = overlay.querySelector('[data-reason]');
        var errorEl = overlay.querySelector('[data-error]');
        var confirmBtn = overlay.querySelector('[data-confirm]');
        var cancelBtn = overlay.querySelector('[data-cancel]');
  
        function close(result) {
          (document.getElementById('bpmMain') || document.body).removeChild(overlay)
          document.removeEventListener('keydown', onKey);
          resolve(result);
        }
        function onKey(e) { if (e.key === 'Escape') close(null); }
  
        confirmBtn.addEventListener('click', function () {
          var reason = textarea.value.trim();
          if (isDeactivate && reason.length < 5) {
            errorEl.textContent = t('Причина должна содержать не менее 5 символов.');
            errorEl.style.display = 'block';
            textarea.focus();
            return;
          }
          close(reason);
        });
        cancelBtn.addEventListener('click', function () { close(null); });
        overlay.addEventListener('click', function (e) { if (e.target === overlay) close(null); });
        document.addEventListener('keydown', onKey);
  
        requestAnimationFrame(function () { overlay.classList.add('is-open'); textarea.focus(); });
      });
    }
  
    document.addEventListener('DOMContentLoaded', function () {
  
      /* ── одиночное действие (карточка сотрудника) ── */
      document.querySelectorAll('[data-status-action]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          var action = btn.getAttribute('data-status-action');
          var id = btn.getAttribute('data-employee-id');
          var name = btn.getAttribute('data-employee-name') || '';
          var currentStatus = btn.getAttribute('data-employee-status') || '';
  
          var reason = await openStatusDialog(action, [{ name: name, status: currentStatus }]);
          if (reason === null) return;
  
          btn.disabled = true;
          try {
            await apiFetch('/api/v1/hr/employees/' + id + '/' + action + '/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ reason: reason }),
            });
            window.location.reload();
          } catch (err) {
            window.alert(t('Не удалось выполнить действие: ') + err.message);
            btn.disabled = false;
          }
        });
      });
  
      /* ── массовое действие (список сотрудников) ── */
      var bulkBar = document.getElementById('employeesBulkBar');
      if (!bulkBar) return;
  
      var bulkCount = document.getElementById('employeesBulkCount');
      var clearBtn = document.getElementById('employeesBulkClear');
      var checkboxes = document.querySelectorAll('[data-employee-checkbox]');
  
      function selectedItems() {
        return Array.prototype.slice.call(checkboxes)
          .filter(function (cb) { return cb.checked; })
          .map(function (cb) { return { id: cb.value, name: cb.getAttribute('data-employee-name') || '', status: cb.getAttribute('data-employee-status') || '' }; });
      }
  
      var activateBtn = bulkBar.querySelector('[data-bulk-action="activate"]');
      var deactivateBtn = bulkBar.querySelector('[data-bulk-action="deactivate"]');
  
      function refreshBar() {
        var items = selectedItems();
        if (items.length === 0) {
          bulkBar.hidden = true;
          return;
        }
        bulkBar.hidden = false;
        bulkCount.textContent = items.length + t(' выбрано');
  
        var allActive = items.every(function (i) { return i.status === 'active'; });
        var allDismissed = items.every(function (i) { return i.status !== 'active'; });
  
        activateBtn.disabled = allActive;
        activateBtn.title = allActive ? t('Все выбранные уже активны') : '';
        deactivateBtn.disabled = allDismissed;
        deactivateBtn.title = allDismissed ? t('Все выбранные уже деактивированы') : '';
      }
  
      checkboxes.forEach(function (cb) {
        cb.addEventListener('change', refreshBar);
      });
  
      clearBtn.addEventListener('click', function () {
        checkboxes.forEach(function (cb) { cb.checked = false; });
        refreshBar();
      });
  
      bulkBar.querySelectorAll('[data-bulk-action]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          var action = btn.getAttribute('data-bulk-action');
          var items = selectedItems();
          if (!items.length) return;
  
          var reason = await openStatusDialog(action, items);
          if (reason === null) return;
  
          btn.disabled = true;
          try {
            await apiFetch('/api/v1/hr/employees/batch-status/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                employee_ids: items.map(function (i) { return parseInt(i.id, 10); }),
                action: action,
                reason: reason,
              }),
            });
            window.location.reload();
          } catch (err) {
            window.alert(t('Не удалось выполнить массовое действие: ') + err.message);
            btn.disabled = false;
          }
        });
      });
    });
  })();