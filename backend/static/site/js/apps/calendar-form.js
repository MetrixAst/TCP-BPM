(function () {
  'use strict';

  function toDisplayDate(iso) {
    if (!iso || iso.indexOf('-') === -1) return iso;
    var p = iso.split('-');
    if (p.length !== 3) return iso;
    return p[2] + '.' + p[1] + '.' + p[0];
  }

  function initDatepicker(input) {
    if (!input || !window.jQuery || !jQuery.fn.datepicker) return;

    input.setAttribute('type', 'text');
    input.setAttribute('autocomplete', 'off');

    if (input.value) {
      input.value = toDisplayDate(input.value.trim());
    }

    jQuery(input).datepicker({
      format: 'dd.mm.yyyy',
      autoclose: true,
      todayHighlight: true,
      language: 'ru',
      orientation: 'bottom auto',
      weekStart: 1,
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.js-cal-date').forEach(initDatepicker);
  });
})();
