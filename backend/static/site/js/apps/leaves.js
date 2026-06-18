(function () {
  function initDatepicker(input) {
    if (!input) return;

    input.setAttribute('autocomplete', 'off');
    input.setAttribute('placeholder', 'дд.мм.гггг');

    if (window.jQuery && jQuery.fn.datepicker) {
      input.setAttribute('type', 'text');

      jQuery(input).datepicker({
        format: 'yyyy-mm-dd',
        autoclose: true,
        todayHighlight: true,
        orientation: 'bottom auto'
      });
    }
  }

  function setupLeaveFilters() {
    const page = document.querySelector('#leavesPage');
    if (!page) return;

    const search = page.querySelector('input[name="search"]');

    if (search) {
      search.classList.add('leaves-page__search-input');
      search.setAttribute('placeholder', 'Поиск по сотруднику');
      search.setAttribute('autocomplete', 'off');
    }

    page.querySelectorAll('select').forEach(function (select) {
      select.classList.add('leaves-page__select');

      if (window.jQuery && jQuery.fn.select2) {
        const $select = jQuery(select);

        if ($select.data('select2')) {
          $select.select2('destroy');
        }

        $select.select2({
          theme: 'bootstrap4',
          width: '100%',
          minimumResultsForSearch: Infinity,
          dropdownCssClass: 'leaves-select2-dropdown',
          selectionCssClass: 'leaves-select2-selection'
        });
      }
    });

    page.querySelectorAll('input[type="date"], input[name="date_from"], input[name="date_to"]').forEach(function (input) {
      input.classList.add('leaves-page__date');
      initDatepicker(input);
    });

    page.querySelectorAll('[data-confirm]').forEach(function (button) {
      button.addEventListener('click', function (event) {
        const message = button.getAttribute('data-confirm') || 'Подтвердить действие?';

        if (!window.confirm(message)) {
          event.preventDefault();
        }
      });
    });
  }

  function setupLeaveCreateForm() {
    const form = document.querySelector('#leaveCreateForm');
    if (!form) return;

    const startInput = document.getElementById('id_start_date');
    const endInput = document.getElementById('id_end_date');
    const preview = document.getElementById('days-preview');
    const counter = document.getElementById('days-count');
    const ajaxUrl = form.getAttribute('data-calculate-url');

    if (!startInput || !endInput || !preview || !counter || !ajaxUrl) return;

    [startInput, endInput].forEach(function (input) {
      input.classList.add('leave-create-date');
      initDatepicker(input);
    });

    const leaveType = form.querySelector('select[name="leave_type"], #id_leave_type');

    if (leaveType && window.jQuery && jQuery.fn.select2) {
      const $leaveType = jQuery(leaveType);

      if ($leaveType.data('select2')) {
        $leaveType.select2('destroy');
      }

      $leaveType.select2({
        theme: 'bootstrap4',
        width: '100%',
        minimumResultsForSearch: Infinity,
        dropdownCssClass: 'leaves-select2-dropdown',
        selectionCssClass: 'leaves-select2-selection'
      });
    }

    let debounceTimer = null;

    function calculateDays() {
      const start = startInput.value;
      const end = endInput.value;

      if (!start || !end) {
        counter.textContent = '—';
        return;
      }

      clearTimeout(debounceTimer);

      debounceTimer = setTimeout(function () {
        fetch(
          ajaxUrl +
            '?start=' +
            encodeURIComponent(start) +
            '&end=' +
            encodeURIComponent(end)
        )
          .then(function (response) {
            return response.json();
          })
          .then(function (data) {
            if (data.days !== undefined) {
              counter.textContent = data.days;
            } else {
              counter.textContent = '—';
            }
          })
          .catch(function () {
            counter.textContent = '—';
          });
      }, 350);
    }

    startInput.addEventListener('change', calculateDays);
    endInput.addEventListener('change', calculateDays);

    if (window.jQuery && jQuery.fn.datepicker) {
      jQuery(startInput).on('changeDate', calculateDays);
      jQuery(endInput).on('changeDate', calculateDays);
    }

    calculateDays();
  }

  /* ═══════════════════════════════════
     LEAVE TIMELINE / CALENDAR
     ═══════════════════════════════════ */
  var tlYear, tlMonth, tlAllItems = [];

  var RU_MONTHS = [
    'Январь','Февраль','Март','Апрель','Май','Июнь',
    'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'
  ];
  var RU_DAYS = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];

  function daysInMonth(y, m) {
    return new Date(y, m + 1, 0).getDate();
  }

  var TL_COLORS = [
    '#2f6bed', '#22a85a', '#f59e0b', '#8b5cf6', '#ec4899',
    '#06b6d4', '#ef4444', '#84cc16', '#6366f1', '#14b8a6',
  ];

  function parseIsoDate(str) {
    var p = (str || '').split('-');
    if (p.length !== 3) return null;
    return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
  }

  function fmtPeriod(start, end) {
    function f(d) {
      return ('0' + d.getDate()).slice(-2) + '.' + ('0' + (d.getMonth() + 1)).slice(-2);
    }
    return f(start) + ' — ' + f(end);
  }

  function escapeHtml(text) {
    var div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function renderCalendar() {
    var root     = document.getElementById('leaveTimeline') || document.getElementById('calendarTimeline');
    var legend   = document.getElementById('tlLegendList') || document.getElementById('calendarLegendList');
    var subtitle = document.getElementById('tlSubtitle') || document.getElementById('calendarTlSubtitle');
    if (!root) return;

    var numDays  = daysInMonth(tlYear, tlMonth);
    var monthStart = new Date(tlYear, tlMonth, 1);
    var monthEnd   = new Date(tlYear, tlMonth, numDays);
    var today = new Date();

    if (subtitle) subtitle.textContent = RU_MONTHS[tlMonth] + ' ' + tlYear;

    var items = tlAllItems.filter(function (item) {
      var s = parseIsoDate(item.start);
      var e = parseIsoDate(item.end);
      if (!s || !e) return false;
      return s <= monthEnd && e >= monthStart;
    });

    var gridStyle = 'grid-template-columns: 180px repeat(' + numDays + ', minmax(28px, 1fr))';

    var headHtml = '<div class="tl-grid__row tl-grid__row--head" style="' + gridStyle + '">';
    headHtml += '<div class="tl-grid__cell tl-grid__cell--name">Сотрудник</div>';
    for (var d = 1; d <= numDays; d++) {
      var dt = new Date(tlYear, tlMonth, d);
      var isToday = (dt.toDateString() === today.toDateString());
      var isWeekend = (dt.getDay() === 0 || dt.getDay() === 6);
      var cls = 'tl-grid__cell tl-grid__cell--day';
      if (isToday) cls += ' tl-grid__cell--today';
      if (isWeekend) cls += ' tl-grid__cell--weekend';
      headHtml += '<div class="' + cls + '">';
      headHtml += '<span class="tl-day-num">' + d + '</span>';
      headHtml += '<span class="tl-day-name">' + RU_DAYS[dt.getDay()] + '</span>';
      headHtml += '</div>';
    }
    headHtml += '</div>';

    var empMap = {};
    var colorIdx = 0;
    items.forEach(function (item) {
      var label = (item.content || '').replace(/\s*\([^)]*\)\s*$/, '').trim() || item.content || '—';
      var key = (item.group || '') + '||' + label;
      if (!empMap[key]) {
        empMap[key] = {
          label: label,
          group: item.group || '',
          color: TL_COLORS[colorIdx % TL_COLORS.length],
          items: [],
        };
        colorIdx++;
      }
      empMap[key].items.push(item);
    });

    var rowsHtml = '';
    var empKeys = Object.keys(empMap);

    if (!empKeys.length) {
      rowsHtml += '<div class="tl-grid__row tl-grid__row--empty" style="' + gridStyle + '">';
      rowsHtml += '<div class="tl-grid__cell tl-grid__cell--name tl-grid__cell--placeholder">Нет отпусков в этом месяце</div>';
      for (var e = 1; e <= numDays; e++) {
        var dtE = new Date(tlYear, tlMonth, e);
        var clsE = 'tl-grid__cell tl-grid__cell--slot';
        if (dtE.getDay() === 0 || dtE.getDay() === 6) clsE += ' tl-grid__cell--weekend';
        rowsHtml += '<div class="' + clsE + '"></div>';
      }
      rowsHtml += '</div>';
    } else {
      empKeys.forEach(function (key) {
        var emp = empMap[key];
        rowsHtml += '<div class="tl-grid__row tl-grid__row--track" style="' + gridStyle + '">';
        rowsHtml += '<div class="tl-grid__cell tl-grid__cell--name tl-grid__cell--track-name">';
        rowsHtml += '<span class="tl-emp-color" style="background:' + emp.color + '"></span>';
        rowsHtml += '<span class="tl-emp-info">';
        rowsHtml += '<span class="tl-emp-name">' + escapeHtml(emp.label) + '</span>';
        if (emp.group) {
          rowsHtml += '<span class="tl-dept-name">' + escapeHtml(emp.group) + '</span>';
        }
        rowsHtml += '</span></div>';

        rowsHtml += '<div class="tl-track" style="grid-column:2/' + (numDays + 2) + ';--tl-days:' + numDays + ';">';
        for (var di = 1; di <= numDays; di++) {
          var dtD = new Date(tlYear, tlMonth, di);
          var c = 'tl-track__day';
          if (dtD.getDay() === 0 || dtD.getDay() === 6) c += ' tl-track__day--weekend';
          if (dtD.toDateString() === today.toDateString()) c += ' tl-track__day--today';
          rowsHtml += '<div class="' + c + '" style="grid-column:' + di + ';grid-row:1;"></div>';
        }

        emp.items.forEach(function (item) {
          var s = parseIsoDate(item.start);
          var e = parseIsoDate(item.end);
          if (!s || !e) return;
          var visStart = s < monthStart ? 1 : s.getDate();
          var visEnd = e > monthEnd ? numDays : e.getDate();
          if (visStart > numDays || visEnd < 1) return;
          var colStart = visStart;
          var colEnd = visEnd + 1;
          var title = fmtPeriod(s, e);
          var barHref = item.url || ('/hr/leaves/' + item.id + '/');
          var statusCls = item.status ? ' tl-bar--' + item.status : '';
          rowsHtml += '<a class="tl-bar' + statusCls + '" href="' + barHref + '"'
            + ' style="grid-column:' + colStart + '/' + colEnd + ';grid-row:1;background:' + emp.color + ';"'
            + ' title="' + escapeHtml(title) + '"></a>';
        });

        rowsHtml += '</div></div>';
      });
    }

    root.innerHTML = '<div class="tl-grid">' + headHtml + rowsHtml + '</div>';

    if (legend) {
      if (!empKeys.length) {
        legend.innerHTML = '<div class="tl-legend-panel__empty">В этом месяце отпусков нет. Календарь доступен для планирования.</div>';
      } else {
        var legHtml = '';
        empKeys.forEach(function (key) {
          var emp = empMap[key];
          legHtml += '<div class="tl-legend-item">';
          legHtml += '<span class="tl-legend-item__swatch" style="background:' + emp.color + '"></span>';
          legHtml += '<div class="tl-legend-item__body">';
          legHtml += '<span class="tl-legend-item__name">' + escapeHtml(emp.label) + '</span>';
          emp.items.forEach(function (item) {
            var s = parseIsoDate(item.start);
            var e = parseIsoDate(item.end);
            if (s && e) {
              legHtml += '<span class="tl-legend-item__period">' + fmtPeriod(s, e) + '</span>';
            }
          });
          legHtml += '</div></div>';
        });
        legend.innerHTML = legHtml;
      }
    }
  }

  function bindTimelineNav(prevId, nextId, todayId, renderFn) {
    var prevBtn  = document.getElementById(prevId);
    var nextBtn  = document.getElementById(nextId);
    var todayBtn = document.getElementById(todayId);
    var today = new Date();
    if (prevBtn)  prevBtn.addEventListener('click',  function () { tlMonth--; if (tlMonth < 0)  { tlMonth = 11; tlYear--; } renderFn(); });
    if (nextBtn)  nextBtn.addEventListener('click',  function () { tlMonth++; if (tlMonth > 11) { tlMonth = 0;  tlYear++; } renderFn(); });
    if (todayBtn) todayBtn.addEventListener('click', function () { tlYear = today.getFullYear(); tlMonth = today.getMonth(); renderFn(); });
  }

  function initTimelinePage(cfg) {
    var page = document.querySelector(cfg.page);
    var root = document.querySelector(cfg.root);
    if (!page || !root) return;

    var sourceUrl = page.getAttribute(cfg.urlAttr || 'data-source-url');
    if (!sourceUrl) return;

    var legend = cfg.legend ? document.querySelector(cfg.legend) : null;
    var subtitle = cfg.subtitle ? document.getElementById(cfg.subtitle) : null;

    var today = new Date();
    tlYear  = today.getFullYear();
    tlMonth = today.getMonth();

    bindTimelineNav(cfg.prevId, cfg.nextId, cfg.todayId, renderCalendar);

    root.innerHTML = '<div class="leave-timeline__loading"><span>Загрузка…</span></div>';

    fetch(sourceUrl)
      .then(function (r) { return r.json(); })
      .then(function (items) {
        tlAllItems = Array.isArray(items) ? items : [];
        renderCalendar();
      })
      .catch(function () {
        root.innerHTML = '<div class="leave-timeline__empty"><i class="bi bi-exclamation-circle"></i><strong>Ошибка загрузки</strong></div>';
      });
  }

  function setupLeaveTimeline() {
    initTimelinePage({
      page: '#leaveTimelinePage',
      root: '#leaveTimeline',
      legend: '#tlLegendList',
      subtitle: 'tlSubtitle',
      prevId: 'tlPrevMonth',
      nextId: 'tlNextMonth',
      todayId: 'tlToday',
    });
  }

  function setupCalendarTimeline() {
    initTimelinePage({
      page: '#calendarTimelinePage',
      root: '#calendarTimeline',
      legend: '#calendarLegendList',
      subtitle: 'calendarTlSubtitle',
      prevId: 'calendarTlPrev',
      nextId: 'calendarTlNext',
      todayId: 'calendarTlToday',
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    setupLeaveFilters();
    setupLeaveCreateForm();
    setupLeaveTimeline();
    setupCalendarTimeline();

    if (window.BPM && window.BPM.applyTranslations) {
      window.BPM.applyTranslations();
    }
  });
})();