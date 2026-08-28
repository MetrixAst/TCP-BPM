(function () {
  'use strict';

  var SOURCE_LABELS = {
    face: 'Фотофиксация',
    qr: 'QR-код',
    manual: 'Ручная отметка',
    mixed: 'Смешанный',
  };

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
          var err = new Error(body.detail || body.error || ('HTTP ' + res.status));
          err.body = body;
          throw err;
        });
      }
      return res.json();
    });
  }

  function fmtDate(isoDate) {
    if (!isoDate) return '—';
    var parts = isoDate.split('-');
    if (parts.length !== 3) return isoDate;
    return parts[2] + '.' + parts[1] + '.' + parts[0];
  }

  function fmtTime(isoDateTime) {
    if (!isoDateTime) return '—';
    var d = new Date(isoDateTime);
    if (isNaN(d.getTime())) return isoDateTime;
    var pad = function (n) { return String(n).padStart(2, '0'); };
    return pad(d.getHours()) + ':' + pad(d.getMinutes());
  }

  function sourceBadgeHtml(source) {
    if (!source) return '<span class="access-muted">—</span>';
    var label = SOURCE_LABELS[source] ? t(SOURCE_LABELS[source]) : source;
    return '<span class="ar-source-badge ar-source-badge--' + source + '">' + label + '</span>';
  }

  function detailsHtml(row) {
    if (!row.day_start && !row.day_end) {
      return '<span class="ar-detail-ok">—</span>';
    }
    if (!row.is_complete) {
      return '<span class="ar-detail-flag" title="' + t('Не хватает отметки прихода или ухода') + '">' + t('Не завершён') + '</span>';
    }
    return '<span class="ar-detail-ok">' + t('Завершён') + '</span>';
  }

  document.addEventListener('DOMContentLoaded', function () {
    var page = document.getElementById('attendanceRegistryPage');
    if (!page) return;

    var form = document.getElementById('arFilters');
    var dateFrom = document.getElementById('arDateFrom');
    var dateTo = document.getElementById('arDateTo');
    var departmentSelect = document.getElementById('arDepartment');
    var employeeSelect = document.getElementById('arEmployee');
    var tableBody = document.getElementById('arTableBody');
    var emptyState = document.getElementById('arEmpty');
    var exportBtn = document.getElementById('arExportBtn');

    var employeeOptions = Array.from(employeeSelect.options);

    function setDefaultDates() {
      var today = new Date();
      var from = new Date(today.getTime() - 29 * 24 * 3600 * 1000);
      function fmt(d) {
        var pad = function (n) { return String(n).padStart(2, '0'); };
        return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
      }
      dateFrom.value = fmt(from);
      dateTo.value = fmt(today);
    }

    function filterEmployeesByDepartment() {
      var deptId = departmentSelect.value;
      var current = employeeSelect.value;
      employeeSelect.innerHTML = '';
      employeeOptions.forEach(function (opt) {
        var dept = opt.getAttribute('data-department') || '';
        if (!deptId || !dept || dept === deptId) {
          employeeSelect.appendChild(opt.cloneNode(true));
        }
      });
      var stillExists = Array.from(employeeSelect.options).some(function (o) { return o.value === current; });
      employeeSelect.value = stillExists ? current : '';
    }

    function currentParams() {
      var params = new URLSearchParams();
      if (dateFrom.value) params.set('date_from', dateFrom.value);
      if (dateTo.value) params.set('date_to', dateTo.value);
      if (departmentSelect.value) params.set('department_id', departmentSelect.value);
      if (employeeSelect.value) params.set('employee_id', employeeSelect.value);
      return params;
    }

    function renderRow(row) {
      var tr = document.createElement('tr');
      tr.innerHTML =
        '<td>' + fmtDate(row.date) + '</td>' +
        '<td><strong>' + (row.employee_name || '') + '</strong></td>' +
        '<td class="hr-muted">' + (row.department || '—') + '</td>' +
        '<td class="hr-muted">' + fmtTime(row.day_start) + '</td>' +
        '<td class="hr-muted">' + fmtTime(row.day_end) + '</td>' +
        '<td class="hr-muted">' + (row.total_hours || 0) + '</td>' +
        '<td>' + sourceBadgeHtml(row.source) + '</td>' +
        '<td>' + detailsHtml(row) + '</td>';
      return tr;
    }

    function loadList() {
      tableBody.innerHTML = '<tr><td colspan="8" class="hr-muted" style="text-align:center;padding:24px;">' + t('Загрузка…') + '</td></tr>';
      emptyState.hidden = true;

      apiFetch('/api/v1/hr/attendance/registry/?' + currentParams().toString())
        .then(function (data) {
          var rows = Array.isArray(data) ? data : (data.results || []);
          tableBody.innerHTML = '';
          if (!rows.length) {
            emptyState.hidden = false;
            return;
          }
          rows.forEach(function (row) {
            tableBody.appendChild(renderRow(row));
          });
        })
        .catch(function () {
          tableBody.innerHTML = '';
          emptyState.hidden = false;
        });
    }

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      loadList();
    });

    departmentSelect.addEventListener('change', function () {
      filterEmployeesByDepartment();
    });

    exportBtn.addEventListener('click', function (e) {
      e.preventDefault();
      var params = currentParams();
      params.set('export', 'xlsx');
      window.location.href = '/api/v1/hr/attendance/registry/?' + params.toString();
    });

    setDefaultDates();
    loadList();
  });
})();
