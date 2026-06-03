(function () {
  "use strict";

  function applyI18n() {
    if (window.BPM && window.BPM.applyTranslations) {
      window.BPM.applyTranslations();
    }
  }

  function cleanEmptyOptions() {
    document.querySelectorAll(".hr-registry-edit-form select, .hr-registry-filters select").forEach(function (select) {
      Array.from(select.options).forEach(function (option) {
        const text = option.textContent.trim();

        if (text === "---------" || text === "----" || text === "---------") {
          option.textContent = "Выберите";
        }
      });
    });

    applyI18n();
  }

  function initRegistrySelects() {
    if (!window.jQuery || !jQuery.fn.select2) return;

    jQuery(".hr-registry-filters select, .hr-registry-edit-form select").each(function () {
      const $select = jQuery(this);

      if ($select.hasClass("select2-hidden-accessible")) return;

      $select.select2({
        width: "100%",
        minimumResultsForSearch: Infinity,
        dropdownParent: jQuery("#hrRegistryFormPage, #hrRegistryPage").first()
      });
    });

    setTimeout(applyI18n, 150);
  }

  function initRegistryDatepickers() {
    if (!window.jQuery || !jQuery.fn.datepicker) return;

    const selector = [
      'input[name*="date"]',
      'input[name*="issue"]',
      'input[name*="expiry"]',
      'input[name*="expires"]',
      'input[name*="valid"]'
    ].join(", ");

    document.querySelectorAll(".hr-registry-edit-form " + selector).forEach(function (input) {
      input.setAttribute("type", "text");
      input.setAttribute("autocomplete", "off");

      if (!input.getAttribute("placeholder")) {
        input.setAttribute("placeholder", "дд.мм.гггг");
      }

      jQuery(input).datepicker({
        format: "dd.mm.yyyy",
        autoclose: true,
        todayHighlight: true,
        orientation: "bottom auto"
      });
    });

    applyI18n();
  }

  function initInputs() {
    document.querySelectorAll(".hr-registry-edit-form input, .hr-registry-edit-form textarea").forEach(function (input) {
      input.setAttribute("autocomplete", "off");
    });
  }

  function initFileInputs() {
    document.querySelectorAll('.hr-registry-edit-form input[type="file"]').forEach(function (input) {
      const upload = input.closest(".hr-registry-upload");
      const name = upload ? upload.querySelector("[data-upload-name]") : null;

      input.addEventListener("change", function () {
        if (!name) return;

        if (input.files && input.files.length) {
          name.textContent = input.files[0].name;
          upload.classList.add("has-file");
        } else {
          name.textContent = "Файл не выбран";
          upload.classList.remove("has-file");
          applyI18n();
        }
      });
    });

    applyI18n();
  }

  function init() {
    cleanEmptyOptions();
    initRegistrySelects();
    initRegistryDatepickers();
    initInputs();
    initFileInputs();
    applyI18n();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();