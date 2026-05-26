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

    function setupLeaveTimeline() {
      var page = document.querySelector('#leaveTimelinePage');
      var root = document.querySelector('#leaveTimeline');
      if (!page || !root) return;

      var sourceUrl = page.getAttribute('data-source-url');
      if (!sourceUrl) return;

      var today = new Date();
      tlYear  = today.getFullYear();
      tlMonth = today.getMonth();

      var prevBtn  = document.getElementById('tlPrevMonth');
      var nextBtn  = document.getElementById('tlNextMonth');
      var todayBtn = document.getElementById('tlToday');

      if (prevBtn)  prevBtn.addEventListener('click',  function () { tlMonth--; if (tlMonth < 0)  { tlMonth = 11; tlYear--; } renderCalendar(); });
      if (nextBtn)  nextBtn.addEventListener('click',  function () { tlMonth++; if (tlMonth > 11) { tlMonth = 0;  tlYear++; } renderCalendar(); });
      if (todayBtn) todayBtn.addEventListener('click', function () { tlYear = today.getFullYear(); tlMonth = today.getMonth(); renderCalendar(); });

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

    function renderCalendar() {
      var root     = document.getElementById('leaveTimeline');
      var subtitle = document.getElementById('tlSubtitle');
      if (!root) return;

      var numDays  = daysInMonth(tlYear, tlMonth);
      var monthStart = new Date(tlYear, tlMonth, 1);
      var monthEnd   = new Date(tlYear, tlMonth, numDays);

      if (subtitle) subtitle.textContent = RU_MONTHS[tlMonth] + ' ' + tlYear;

      // Фильтруем заявки пересекающиеся с месяцем
      var items = tlAllItems.filter(function (item) {
        var s = new Date(item.start);
        var e = new Date(item.end);
        return s <= monthEnd && e >= monthStart;
      });

      if (!items.length) {
        root.innerHTML = '<div class="leave-timeline__empty"><i class="bi bi-calendar-x"></i><strong>Нет заявок за ' + RU_MONTHS[tlMonth].toLowerCase() + ' ' + tlYear + '</strong><span>Попробуйте другой месяц или создайте заявку</span></div>';
        return;
      }

      // ── шапка с датами ──
      var cols = numDays + 1;
      var gridStyle = 'grid-template-columns: 180px repeat(' + numDays + ', 1fr)';

      var headHtml = '<div class="tl-grid__row tl-grid__row--head" style="' + gridStyle + '">';
      headHtml += '<div class="tl-grid__cell tl-grid__cell--name">Сотрудник</div>';
      var today = new Date();
      for (var d = 1; d <= numDays; d++) {
        var dt = new Date(tlYear, tlMonth, d);
        var isToday = (dt.toDateString() === today.toDateString());
        var isWeekend = (dt.getDay() === 0 || dt.getDay() === 6);
        var cls = 'tl-grid__cell tl-grid__cell--day';
        if (isToday)   cls += ' tl-grid__cell--today';
        if (isWeekend) cls += ' tl-grid__cell--weekend';
        headHtml += '<div class="' + cls + '">';
        headHtml += '<span class="tl-day-num">' + d + '</span>';
        headHtml += '<span class="tl-day-name">' + RU_DAYS[dt.getDay()] + '</span>';
        headHtml += '</div>';
      }
      headHtml += '</div>';

      // ── строки сотрудников ──
      // Группируем по group (отделу) + content (сотрудник)
      var empMap = {};
      items.forEach(function (item) {
        var key = (item.group || '') + '||' + (item.content || '');
        if (!empMap[key]) empMap[key] = { label: item.content, group: item.group, items: [] };
        empMap[key].items.push(item);
      });

      var rowsHtml = '';
      Object.keys(empMap).forEach(function (key) {
        var emp = empMap[key];
        rowsHtml += '<div class="tl-grid__row" style="' + gridStyle + '">';
        rowsHtml += '<div class="tl-grid__cell tl-grid__cell--name">';
        rowsHtml += '<span class="tl-emp-name">' + (emp.label || '—') + '</span>';
        rowsHtml += '<span class="tl-dept-name">' + (emp.group || '') + '</span>';
        rowsHtml += '</div>';

        // Ячейки дней
        for (var d = 1; d <= numDays; d++) {
          var dt2   = new Date(tlYear, tlMonth, d);
          var isWeekend2 = (dt2.getDay() === 0 || dt2.getDay() === 6);
          var isToday2   = dt2.toDateString() === today.toDateString();

          // Попадает ли в этот день хоть одна заявка
          var dayItems = emp.items.filter(function (item) {
            var s = new Date(item.start);
            var e = new Date(item.end);
            return dt2 >= s && dt2 <= e;
          });

          var cellCls = 'tl-grid__cell tl-grid__cell--slot';
          if (isWeekend2) cellCls += ' tl-grid__cell--weekend';
          if (isToday2)   cellCls += ' tl-grid__cell--today';

          var inner = '';
          if (dayItems.length) {
            var st = dayItems[0].status || 'pending';
            cellCls += ' tl-grid__cell--filled tl-grid__cell--' + st;
            inner = '<span class="tl-cell-dot"></span>';
          }

          rowsHtml += '<div class="' + cellCls + '">' + inner + '</div>';
        }

        rowsHtml += '</div>';
      });

      root.innerHTML = '<div class="tl-grid">' + headHtml + rowsHtml + '</div>';
    }
  
    document.addEventListener('DOMContentLoaded', function () {
      setupLeaveFilters();
      setupLeaveCreateForm();
      setupLeaveTimeline();
    });
  })();