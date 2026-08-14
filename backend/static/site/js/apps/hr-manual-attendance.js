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
            var msg = extractErrorMessage(body) || ('HTTP ' + res.status);
            var err = new Error(msg);
            err.body = body;
            throw err;
          });
        }
        if (res.status === 204) return null;
        return res.json();
      });
    }
  
    // DRF отдаёт ошибки по-разному: {"detail": "..."} или {"field": ["..."]} или {"non_field_errors": [...]}
    function extractErrorMessage(body) {
      if (!body || typeof body !== 'object') return null;
      if (body.detail) return body.detail;
      var parts = [];
      Object.keys(body).forEach(function (key) {
        var val = body[key];
        var text = Array.isArray(val) ? val.join(' ') : String(val);
        parts.push(key === 'non_field_errors' ? text : (key + ': ' + text));
      });
      return parts.join(' ');
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

    function formatDateTime(raw) {
      var d = parseServerDateTime(raw);
      if (!d) return '—';
      return d.toLocaleDateString('ru-RU') + ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }
  
    var EVENT_LABELS = { day_start: 'Приход', day_end: 'Уход' };
  
    document.addEventListener('DOMContentLoaded', function () {
      var tbody = document.getElementById('maTableBody');
      var createBtn = document.getElementById('maCreateBtn');
      var formDialog = document.getElementById('maFormDialog');
      var formTitle = document.getElementById('maFormTitle');
      var form = document.getElementById('maForm');
      var cancelBtn = document.getElementById('maCancelBtn');
      var formError = document.getElementById('maFormError');
      var historyDialog = document.getElementById('maHistoryDialog');
      var historyBody = document.getElementById('maHistoryBody');
      var historyCloseBtn = document.getElementById('maHistoryCloseBtn');
  
      if (window.jQuery && jQuery.fn.select2) {
        jQuery('.ma-select2').select2({ theme: 'bootstrap4', width: '100%' });
      }
  
      var allRecords = [];
  
      function loadRecords() {
        tbody.innerHTML = '<div class="ma-table__loading">' + t('Загрузка…') + '</div>';
        apiFetch('/api/v1/hr/attendance/manual/?page_size=200')
          .then(function (data) {
            allRecords = data.results || (Array.isArray(data) ? data : []);
            renderTable();
          })
          .catch(function (err) {
            tbody.innerHTML = '<div class="ma-table__loading">' + t('Не удалось загрузить: ') + escapeHtml(err.message) + '</div>';
          });
      }
  
      function employeeLabel(empId) {
        var opt = document.querySelector('#maEmployee option[value="' + empId + '"]');
        return opt ? opt.textContent : ('#' + empId);
      }
  
      function renderTable() {
        if (!allRecords.length) {
          tbody.innerHTML = '<div class="ma-table__empty">' + t('Ручных отметок пока нет.') + '</div>';
          return;
        }
        tbody.innerHTML = allRecords.map(function (r) {
          return (
            '<div class="hr-table__row ma-table__row">' +
              '<div>' + escapeHtml(employeeLabel(r.employee)) + '</div>' +
              '<div>' + (EVENT_LABELS[r.event_type] || r.event_type) + '</div>' +
              '<div>' + formatDateTime(r.timestamp) + '</div>' +
              '<div>' + escapeHtml(r.manual_reason_label || '—') + '</div>' +
              '<div>' + escapeHtml(r.manual_author_name || '—') + '</div>' +
              '<div class="ma-table__actions">' +
                '<button type="button" class="hr-icon-btn" data-ma-edit="' + r.id + '" title="' + t('Редактировать') + '"><i class="bi bi-pencil"></i></button>' +
                '<button type="button" class="hr-icon-btn" data-ma-history="' + r.id + '" title="' + t('История') + '"><i class="bi bi-clock-history"></i></button>' +
                '<button type="button" class="hr-icon-btn" data-ma-delete="' + r.id + '" title="' + t('Удалить') + '"><i class="bi bi-trash"></i></button>' +
              '</div>' +
            '</div>'
          );
        }).join('');

        if (window.BPM && window.BPM.applyTranslations) {
          window.BPM.applyTranslations();
        }

        tbody.querySelectorAll('[data-ma-edit]').forEach(function (btn) {
          btn.addEventListener('click', function () { openForm(btn.getAttribute('data-ma-edit')); });
        });
        tbody.querySelectorAll('[data-ma-delete]').forEach(function (btn) {
          btn.addEventListener('click', function () { deleteRecord(btn.getAttribute('data-ma-delete')); });
        });
        tbody.querySelectorAll('[data-ma-history]').forEach(function (btn) {
          btn.addEventListener('click', function () { openHistory(btn.getAttribute('data-ma-history')); });
        });
      }
  
      function openForm(recordId) {
        formError.style.display = 'none';
        form.reset();
        document.getElementById('maId').value = recordId || '';
  
        if (window.jQuery && jQuery.fn.select2) {
          jQuery('#maEmployee').val(null).trigger('change');
          jQuery('#maEventType').val('day_start').trigger('change');
          jQuery('#maReason').val(null).trigger('change');
        }
  
        if (recordId) {
          formTitle.textContent = t('Редактирование отметки');
          var record = allRecords.find(function (r) { return String(r.id) === String(recordId); });
          if (record) {
            if (window.jQuery && jQuery.fn.select2) {
              jQuery('#maEmployee').val(record.employee).trigger('change');
              jQuery('#maEventType').val(record.event_type).trigger('change');
              jQuery('#maReason').val(record.manual_reason || null).trigger('change');
            }
            document.getElementById('maComment').value = record.manual_comment || '';
            if (record.timestamp) {
              var d = parseServerDateTime(record.timestamp);
              if (d) {
                var pad = function (n) { return String(n).padStart(2, '0'); };
                document.getElementById('maTimestamp').value =
                  d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + 'T' + pad(d.getHours()) + ':' + pad(d.getMinutes());
              }
            }
          }
        } else {
            formTitle.textContent = t('Новая отметка');
        }
  
        formDialog.classList.add('is-open');
      }
  
      function closeForm() {
        formDialog.classList.remove('is-open');
      }
  
      createBtn.addEventListener('click', function () { openForm(null); });
      cancelBtn.addEventListener('click', closeForm);
      formDialog.addEventListener('click', function (e) { if (e.target === formDialog) closeForm(); });
  
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        formError.style.display = 'none';
  
        var recordId = document.getElementById('maId').value;
        var employee = document.getElementById('maEmployee').value;
        var eventType = document.getElementById('maEventType').value;
        var timestampLocal = document.getElementById('maTimestamp').value;
        var reason = document.getElementById('maReason').value;
        var comment = document.getElementById('maComment').value;
  
        if (!employee) {
          formError.textContent = t('Выберите сотрудника.');
          formError.style.display = 'block';
          return;
        }
        if (!timestampLocal) {
          formError.textContent = t('Укажите дату и время.');
          formError.style.display = 'block';
          return;
        }
  
        var payload = {
          employee: parseInt(employee, 10),
          event_type: eventType,
          timestamp: new Date(timestampLocal).toISOString(),
          manual_reason: reason ? parseInt(reason, 10) : null,
          manual_comment: comment,
        };
  
        var url = recordId ? '/api/v1/hr/attendance/manual/' + recordId + '/' : '/api/v1/hr/attendance/manual/';
        var method = recordId ? 'PATCH' : 'POST';
  
        apiFetch(url, {
          method: method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
          .then(function () {
            closeForm();
            loadRecords();
          })
          .catch(function (err) {
            formError.textContent = err.message;
            formError.style.display = 'block';
          });
      });
  
      function deleteRecord(recordId) {
        if (!window.confirm(t('Удалить ручную отметку? Действие необратимо.'))) return;
        apiFetch('/api/v1/hr/attendance/manual/' + recordId + '/', { method: 'DELETE' })
          .then(function () { loadRecords(); })
          .catch(function (err) { window.alert(t('Не удалось удалить: ') + err.message); });
      }
  
      var ACTION_LABELS = { create: 'Создание', update: 'Изменение', delete: 'Удаление' };

    function formatSnapshot(snapshot) {
      if (!snapshot) return '—';
      var parts = [];
      if (snapshot.event_type) parts.push(t('тип: ') + (EVENT_LABELS[snapshot.event_type] || snapshot.event_type));
      if (snapshot.timestamp) parts.push(t('время: ') + formatDateTime(snapshot.timestamp));
      if (snapshot.manual_comment) parts.push(t('комментарий: «') + snapshot.manual_comment + '»');
      return parts.join(', ') || '—';
    }

    function openHistory(recordId) {
      historyBody.innerHTML = '<div class="ma-table__loading">' + t('Загрузка…') + '</div>';
      historyDialog.classList.add('is-open');
      apiFetch('/api/v1/hr/attendance/manual/' + recordId + '/history/')
        .then(function (data) {
          var logs = data.results || [];
          if (!logs.length) {
            historyBody.innerHTML = '<p class="access-muted">' + t('История пуста.') + '</p>';
            return;
          }
          historyBody.innerHTML = logs.map(function (log) {
            return (
              '<div class="ma-history-item">' +
                '<div class="ma-history-item__head">' +
                  '<strong>' + (ACTION_LABELS[log.action] || log.action) + '</strong>' +
                  '<span class="access-muted">' + formatDateTime(log.created_at) + (log.actor ? ' · ' + escapeHtml(log.actor) : '') + '</span>' +
                '</div>' +
                (log.action === 'update'
                    ? '<div class="ma-history-item__diff"><div>' + t('До: ') + escapeHtml(formatSnapshot(log.before)) + '</div><div>' + t('После: ') + escapeHtml(formatSnapshot(log.after)) + '</div></div>'
                    : '<div class="ma-history-item__diff">' + escapeHtml(formatSnapshot(log.action === 'delete' ? log.before : log.after)) + '</div>'
                  ) +
                '</div>'
              );
            }).join('');
  
            if (window.BPM && window.BPM.applyTranslations) {
              window.BPM.applyTranslations();
            }
          })
          .catch(function (err) {
            historyBody.innerHTML = '<p class="access-muted">' + t('Ошибка: ') + escapeHtml(err.message) + '</p>';
        });
    }
  
      historyCloseBtn.addEventListener('click', function () { historyDialog.classList.remove('is-open'); });
      historyDialog.addEventListener('click', function (e) { if (e.target === historyDialog) historyDialog.classList.remove('is-open'); });
  
      loadRecords();
    });
  })();