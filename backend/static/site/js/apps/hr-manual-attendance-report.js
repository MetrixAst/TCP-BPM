(function () {
    'use strict';
  
    function t(text) {
      return (window.BPM && window.BPM.t) ? window.BPM.t(text, text) : text;
    }
  
    function getCsrfToken() {
      var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      return match ? decodeURIComponent(match[1]) : '';
    }
  
    function apiFetch(url) {
      return fetch(url, {
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      }).then(function (res) {
        if (!res.ok) {
          return res.json().catch(function () { return {}; }).then(function (body) {
            throw new Error(body.detail || ('HTTP ' + res.status));
          });
        }
        return res.json();
      });
    }
  
    function escapeHtml(text) {
      var div = document.createElement('div');
      div.textContent = text == null ? '' : text;
      return div.innerHTML;
    }
  
    document.addEventListener('DOMContentLoaded', function () {
      var form = document.getElementById('marFilterForm');
      var tbody = document.getElementById('marTableBody');
      var exportBtn = document.getElementById('marExportBtn');
  
      if (window.jQuery && jQuery.fn.select2) {
        jQuery('.ma-select2').select2({ theme: 'bootstrap4', width: '100%' });
      }
  
      function buildQuery() {
        var params = new URLSearchParams();
        var dateFrom = document.getElementById('marDateFrom').value;
        var dateTo = document.getElementById('marDateTo').value;
        var employee = document.getElementById('marEmployee').value;
        var author = document.getElementById('marAuthor').value;
        if (dateFrom) params.set('date_from', dateFrom);
        if (dateTo) params.set('date_to', dateTo);
        if (employee) params.set('employee_id', employee);
        if (author) params.set('author_id', author);
        return params.toString();
      }
  
      function loadReport() {
        tbody.innerHTML = '<div class="ma-table__loading">' + t('Загрузка…') + '</div>';
        apiFetch('/api/v1/hr/attendance/report/?' + buildQuery())
          .then(function (data) {
            var rows = Array.isArray(data) ? data : (data.results || []);
            if (!rows.length) {
              tbody.innerHTML = '<div class="ma-table__empty">' + t('Нет данных за выбранный период.') + '</div>';
              return;
            }
            tbody.innerHTML = rows.map(function (r) {
              return (
                '<div class="hr-table__row mar-table__row">' +
                  '<div>' + escapeHtml(r.employee_name) + '</div>' +
                  '<div>' + escapeHtml(r.department || '—') + '</div>' +
                  '<div>' + r.total_records + '</div>' +
                  '<div>' + r.manual_records + '</div>' +
                  '<div>' + r.auto_records + '</div>' +
                  '<div>' + r.total_work_hours + ' ' + t('ч.') + '</div>' +
                '</div>'
              );
            }).join('');
  
            if (window.BPM && window.BPM.applyTranslations) {
              window.BPM.applyTranslations();
            }
          })
          .catch(function (err) {
            tbody.innerHTML = '<div class="ma-table__loading">' + t('Ошибка: ') + escapeHtml(err.message) + '</div>';
          });
      }
  
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        loadReport();
      });
  
      exportBtn.addEventListener('click', function () {
        var query = buildQuery();
        window.location.href = '/api/v1/hr/attendance/report/?' + query + '&export=xlsx';
      });
  
      loadReport();
    });
  })();