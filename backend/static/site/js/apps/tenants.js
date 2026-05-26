(function () {
  'use strict';

  var form = document.getElementById('createTenantForm');
  if (!form) return;

  var alertBox = document.getElementById('tenantFormAlert');
  var submitBtn = document.getElementById('tenantFormSubmit');

  form.addEventListener('submit', function (event) {
    event.preventDefault();

    if (alertBox) {
      alertBox.hidden = true;
      alertBox.textContent = '';
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Сохранение...';

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
          var modalEl = document.getElementById('createTenantModal');
          if (modalEl && window.bootstrap) {
            bootstrap.Modal.getInstance(modalEl).hide();
          }
          window.location.reload();
          return;
        }

        var message = 'Проверьте данные формы.';
        if (result.data.errors) {
          var parts = [];
          Object.keys(result.data.errors).forEach(function (key) {
            parts.push(result.data.errors[key].join(', '));
          });
          if (parts.length) message = parts.join(' ');
        }

        if (alertBox) {
          alertBox.hidden = false;
          alertBox.textContent = message;
        }
      })
      .catch(function () {
        if (alertBox) {
          alertBox.hidden = false;
          alertBox.textContent = 'Ошибка при сохранении. Попробуйте ещё раз.';
        }
      })
      .finally(function () {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Добавить';
      });
  });
})();
