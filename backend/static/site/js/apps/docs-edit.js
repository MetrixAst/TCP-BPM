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

    $form.on('click', '.doc-form-check span', function (e) {
      var checkbox = $(this).closest('.doc-form-check').find('input[type="checkbox"]')[0];
      if (!checkbox || checkbox.disabled) return;
    
      checkbox.checked = !checkbox.checked;
      checkbox.dispatchEvent(new Event('change', { bubbles: true }));
    });

    $form.find('input[type="file"]').each(function () {
      $(this).attr('multiple', 'multiple');
    });
    
    $form.find('input[type="file"]').on('change', function () {
      var input = this;
      var $input = $(input);
      var $uploadName = $input.closest('.doc-form-upload').find('[data-upload-name]');
    
      var previousFiles = $input.data('selectedFiles') || [];
      var newFiles = Array.from(input.files || []);
    
      if (!newFiles.length && !previousFiles.length) {
        $uploadName.text('Файлы не выбраны');
        return;
      }
    
      var mergedFiles = previousFiles.slice();
    
      newFiles.forEach(function (file) {
        var alreadyExists = mergedFiles.some(function (existingFile) {
          return existingFile.name === file.name &&
                 existingFile.size === file.size &&
                 existingFile.lastModified === file.lastModified;
        });
    
        if (!alreadyExists) {
          mergedFiles.push(file);
        }
      });
    
      if (window.DataTransfer) {
        var dataTransfer = new DataTransfer();
    
        mergedFiles.forEach(function (file) {
          dataTransfer.items.add(file);
        });
    
        input.files = dataTransfer.files;
      }
    
      $input.data('selectedFiles', mergedFiles);
    
      var names = mergedFiles.map(function (file) {
        return file.name;
      });
    
      $uploadName.text(names.join(', '));
    });
  });
})(window.jQuery);
