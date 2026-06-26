(function () {
  'use strict';

  var modalEl = document.getElementById('createTenantModal');
  var form = document.getElementById('createTenantForm');
  if (!form) return;

  var alertBox = document.getElementById('tenantFormAlert');
  var submitBtn = document.getElementById('tenantFormSubmit');

  function getLang() {
    var match = document.cookie.match(/bpm_lang=([^;]+)/);
    return match ? match[1] : 'ru';
  }

  function getFieldLabels() {
    var lang = getLang();
    if (lang === 'en') {
      return {
        'name': 'Name',
        'area': 'Area',
        'price': 'Rate per m²',
        'start_date': 'Lease start',
        'end_date': 'Lease end',
        'discount_date': 'Discount period',
        'increase_type': 'Rate increase',
        'contact': 'Responsible person',
        'phone': 'Phone',
        'email': 'Email',
        'address': 'Address',
      };
    } else if (lang === 'kk') {
      return {
        'name': 'Атауы',
        'area': 'Аудан',
        'price': 'м² бағасы',
        'start_date': 'Жалдау басталуы',
        'end_date': 'Жалдау аяқталуы',
        'discount_date': 'Жеңілдік мерзімі',
        'increase_type': 'Ставканы көтеру',
        'contact': 'Жауапты тұлға',
        'phone': 'Телефон',
        'email': 'Email',
        'address': 'Мекенжай',
      };
    } else {
      return {
        'name': 'Название',
        'area': 'Площадь',
        'price': 'Ставка за м²',
        'start_date': 'Начало аренды',
        'end_date': 'Завершение аренды',
        'discount_date': 'Срок скидки',
        'increase_type': 'Повышение ставки',
        'contact': 'Ответственное лицо',
        'phone': 'Телефон',
        'email': 'Email',
        'address': 'Адрес',
      };
    }
  }

  function t(key, fallback) {
    return (window.BPM && window.BPM.t) ? window.BPM.t(key, fallback) : fallback;
  }

  function getDateInputs() {
    return form.querySelectorAll(
      '[name="start_date"], [name="end_date"], [name="discount_date"], ' +
      '#id_start_date, #id_end_date, #id_discount_date'
    );
  }

  function prepareDateInputs() {
    getDateInputs().forEach(function (input) {
      input.setAttribute('type', 'text');
      input.setAttribute('autocomplete', 'off');
      input.setAttribute('placeholder', 'дд.мм.гггг');
      input.classList.add('tenant-datepicker');
    });
  }

  function initTenantDatepickers() {
    prepareDateInputs();

    if (!window.jQuery || !jQuery.fn.datepicker) {
      console.warn('bootstrap-datepicker is not loaded');
      return;
    }

    jQuery(getDateInputs()).each(function () {
      var $input = jQuery(this);

      if ($input.data('datepicker')) {
        $input.datepicker('destroy');
      }

      $input.datepicker({
        format: 'dd.mm.yyyy',
        language: 'ru',
        autoclose: true,
        todayHighlight: true,
        clearBtn: true,
        todayBtn: false,
        orientation: 'bottom auto',
        container: 'body',
        zIndexOffset: 3000
      });
    });
  }

  function initTenantSelect2() {
    if (!window.jQuery || !jQuery.fn.select2 || !modalEl) return;

    var $modal = jQuery(modalEl);

    $modal.find('select').each(function () {
      var $select = jQuery(this);

      if ($select.data('select2')) {
        $select.select2('destroy');
      }

      $select.select2({
        width: '100%',
        theme: 'default',
        dropdownParent: $modal,
        dropdownCssClass: 'tenant-select2-dropdown',
        minimumResultsForSearch: Infinity
      });
    });
  }

  function initTenantModalPlugins() {
    prepareDateInputs();
    initTenantSelect2();
    initTenantDatepickers();
  }

  document.addEventListener('DOMContentLoaded', function () {
    initTenantModalPlugins();
  });

  if (modalEl) {
    modalEl.addEventListener('shown.bs.modal', function () {
      initTenantModalPlugins();
    });
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();

    if (alertBox) {
      alertBox.hidden = true;
      alertBox.innerHTML = '';
    }

    if (submitBtn) {
      if (!submitBtn.dataset.originalHtml) {
        submitBtn.dataset.originalHtml = submitBtn.innerHTML;
      }
      submitBtn.disabled = true;
      submitBtn.textContent = t('Сохранение...', 'Сохранение...');
    }

    var formData = new FormData(form);

    fetch(form.action, {
      method: 'POST',
      body: formData,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        if (result.ok && result.data.success) {
          if (modalEl && window.bootstrap) {
            var modal = bootstrap.Modal.getInstance(modalEl) || bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.hide();
          }
          window.location.reload();
          return;
        }

        if (result.data.errors) {
          var fieldLabels = getFieldLabels();
          var parts = [];
          Object.keys(result.data.errors).forEach(function (key) {
            var label = fieldLabels[key] || key;
            parts.push(label);
          });

          if (alertBox) {
            alertBox.hidden = false;
            alertBox.innerHTML = '<strong>' + t('Заполните обязательные поля:', 'Заполните обязательные поля:') + '</strong> ' + parts.join(', ');
          }
        } else {
          if (alertBox) {
            alertBox.hidden = false;
            alertBox.textContent = t('Проверьте данные формы.', 'Проверьте данные формы.');
          }
        }
      })
      .catch(function () {
        if (alertBox) {
          alertBox.hidden = false;
          alertBox.textContent = t('Ошибка при сохранении. Попробуйте ещё раз.', 'Ошибка при сохранении. Попробуйте ещё раз.');
        }
      })
      .finally(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = submitBtn.dataset.originalHtml || 'Добавить';
        }
      });
  });
})();