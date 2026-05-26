(function ($) {
  'use strict';

  function initSelect2Ajax($select) {
    if (!$select.length || !$.fn.select2) return;

    var values = [];
    $select.find('option').each(function () {
      if (this.selected || $(this).attr('selected') === 'selected') {
        values.push($(this).val());
      }
    });

    var url = $select.attr('data-url');
    var placeholder = $select.attr('placeholder') || 'Выберите из списка';

    if ($select.hasClass('select2-hidden-accessible')) {
      $select.select2('destroy');
    }

    if (!$select.parent().hasClass('position-relative')) {
      $select.wrap('<div class="position-relative"></div>');
    }

    $select.select2({
      dropdownAutoWidth: true,
      width: '100%',
      theme: 'bootstrap4',
      dropdownParent: $select.parent(),
      allowClear: true,
      placeholder: placeholder,
      ajax: {
        url: url,
        dataType: 'json',
        delay: 250,
        data: function (params) {
          return {
            term: params.term || '',
            page: params.page || 1,
          };
        },
      },
      escapeMarkup: function (markup) {
        return markup;
      },
      templateResult: function (result) {
        if (result.loading) return result.text;
        var markup = '<div class="clearfix"><div>' + result.text + '</div>';
        if (result.addit) {
          markup += '<div class="text-muted small">' + result.addit + '</div>';
        }
        return markup;
      },
      templateSelection: function (result) {
        return result.text || result.id;
      },
    });

    if (values.length) {
      $select.val(values).trigger('change');
    }
  }

  $(function () {
    var $form = $('#docEditForm');
    if (!$form.length) return;

    if ($.fn.select2) {
      $.fn.select2.defaults.set('theme', 'bootstrap4');

      $form.find('select.select2_ajax').each(function () {
        initSelect2Ajax($(this));
      });

      $form.find('select').not('.select2_ajax').each(function () {
        var $el = $(this);
        if ($el.hasClass('select2-hidden-accessible')) return;
        $el.select2({ width: '100%', theme: 'bootstrap4' });
      });
    }

    $form.find('.single_date_picker').each(function () {
      var $input = $(this);
      var val = $input.val();
      if (val && val.indexOf('-') !== -1) {
        $input.val(val.split('-').reverse().join('.'));
      }
      $input.datepicker({
        autoclose: true,
        language: 'ru',
        format: 'dd.mm.yyyy',
      });
    });

    $form.find('input[type="file"]').on('change', function () {
      var name = this.files && this.files[0] ? this.files[0].name : 'Файл не выбран';
      $(this).closest('.doc-form-upload').find('[data-upload-name]').text(name);
    });
  });
})(window.jQuery);
