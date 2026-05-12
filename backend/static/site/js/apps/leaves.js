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

    function setupLeaveTimeline() {
        const page = document.querySelector('#leaveTimelinePage');
        const root = document.querySelector('#leaveTimeline');
      
        if (!page || !root) return;
      
        const sourceUrl = page.getAttribute('data-source-url');
        if (!sourceUrl) return;
      
        fetch(sourceUrl)
          .then(function (response) {
            return response.json();
          })
          .then(function (items) {
            if (!Array.isArray(items) || !items.length) return;
            renderTimeline(root, items);
          })
          .catch(function () {
            return;
          });
      }
      
      function renderTimeline(root, items) {
        const daysCount = 31;
        const groups = {};
      
        items.forEach(function (item) {
          const group = item.group || 'Без отдела';
          if (!groups[group]) groups[group] = [];
          groups[group].push(item);
        });
      
        let html = '<div class="leave-timeline__grid">';
        html += '<div class="leave-timeline__head">';
        html += '<div class="leave-timeline__cell leave-timeline__employee">Сотрудник / отдел</div>';
      
        for (let day = 1; day <= daysCount; day++) {
          html += '<div class="leave-timeline__cell">' + day + '</div>';
        }
      
        html += '</div>';
      
        Object.keys(groups).forEach(function (groupName) {
          groups[groupName].forEach(function (item) {
            const start = new Date(item.start);
            const end = new Date(item.end);
            const startDay = Math.max(1, start.getDate());
            const endDay = Math.min(daysCount, end.getDate());
            const span = Math.max(1, endDay - startDay + 1);
            const status = item.status || 'pending';
      
            html += '<div class="leave-timeline__row">';
            html += '<div class="leave-timeline__cell leave-timeline__employee">' + groupName + '</div>';
      
            for (let day = 1; day <= daysCount; day++) {
              html += '<div class="leave-timeline__cell"></div>';
            }
      
            html += '<div class="leave-timeline__bar leave-timeline__bar--' + status + '" ';
            html += 'style="grid-column:' + (startDay + 1) + ' / span ' + span + '">';
            html += item.content || 'Отпуск';
            html += '</div>';
      
            html += '</div>';
          });
        });
      
        html += '</div>';
        root.innerHTML = html;
      }
  
    document.addEventListener('DOMContentLoaded', function () {
      setupLeaveFilters();
      setupLeaveCreateForm();
      setupLeaveTimeline();
    });
  })();