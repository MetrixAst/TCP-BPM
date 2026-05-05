(function () {
  'use strict';

  function getCsrf() {
    const tag = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tag) return tag.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function debounce(fn, wait) {
    let t;
    return function () {
      const ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, wait);
    };
  }

  // ── TASKS LIST PAGE ════════════════════════════════════════════════════════
  function initTasksList() {
    const page = document.getElementById('tasksPage');
    if (!page) return;

    const tableWrap = document.getElementById('tasksTableWrap');
    const search    = document.getElementById('taskSearch');
    const stateSel  = document.getElementById('taskStateFilter');
    const filterForm = document.getElementById('tasksFilterForm');

    // Click on row → open task detail
    tableWrap?.addEventListener('click', function(e) {
      const row = e.target.closest('.tasks-table__row');
      if (!row) return;
      const href = row.getAttribute('data-href');
      if (href) window.location.href = href;
    });

    // Submit фильтров — обычная отправка form (полный refresh, надёжно)
    // Это покрывает: поиск, состояние, искать
    // Form сама отправится при submit на любую кнопку type="submit" в форме

    // Поиск с debounce — авто-submit формы при наборе
    const onSearchInput = debounce(function() {
      filterForm?.submit();
    }, 500);
    search?.addEventListener('input', onSearchInput);

    // Состояние — submit сразу при изменении
    stateSel?.addEventListener('change', function() {
      filterForm?.submit();
    });

    // Settings dropdown — placeholder
    const settingsBtn = document.getElementById('taskSettingsBtn');
    settingsBtn?.addEventListener('click', function() {
      alert('Настройка отображения колонок будет реализована позже.');
    });
  }

  // ── TASK DETAIL PAGE ═══════════════════════════════════════════════════════
  function initTaskDetail() {
    const taskCard = document.querySelector('.task-card');
    if (!taskCard) return;

    // Star toggle
    const starBtn = document.querySelector('.task-card__icon-btn--star');
    starBtn?.addEventListener('click', function() {
      starBtn.classList.toggle('is-active');
      const icon = starBtn.querySelector('i');
      if (icon) {
        if (starBtn.classList.contains('is-active')) {
          icon.classList.remove('bi-star');
          icon.classList.add('bi-star-fill');
        } else {
          icon.classList.remove('bi-star-fill');
          icon.classList.add('bi-star');
        }
      }
    });

    // Priority change — отправляем POST на тот же URL (или на специальный)
    const prioritySelect = document.querySelector('.task-card__priority-select');
    prioritySelect?.addEventListener('change', async function() {
      const value = prioritySelect.value;
      try {
        const fd = new FormData();
        fd.append('priority', value);
        await fetch(window.location.pathname, {
          method: 'POST',
          headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin',
          body: fd,
        });
      } catch(e) {
        console.warn('priority change failed', e);
      }
    });

    // Delete confirm
    const deleteBtn = document.getElementById('taskDeleteBtn');
    deleteBtn?.addEventListener('click', function(e) {
      if (!confirm('Удалить задачу?')) {
        e.preventDefault();
      }
    });

    // Workflow buttons (теперь это <a>, переход обычный — но добавим confirm для опасных)
    document.querySelectorAll('.task-card__btn[data-action]').forEach(function(btn) {
      const action = btn.getAttribute('data-action');
      if (action === 'reject' || action === 'cancel' || action === 'revise' || action === 'delete') {
        btn.addEventListener('click', function(e) {
          if (!confirm('Подтвердите действие')) {
            e.preventDefault();
          }
        });
      }
    });
  }

  // ── EDIT TASK FORM ═════════════════════════════════════════════════════════
  function initTaskEdit() {
    const form = document.getElementById('taskEditForm');
    if (!form) return;

    // Init Select2 для всех select-полей в форме
    // Select2
    if (typeof jQuery !== 'undefined' && jQuery.fn.select2) {
      jQuery('#taskEditForm select').each(function () {
        const $sel = jQuery(this);

        if ($sel.hasClass('select2-hidden-accessible')) return;

        const placeholder =
          $sel.data('placeholder') ||
          $sel.find('option[value=""]').first().text() ||
          'Выберите';

        $sel.select2({
          width: '100%',
          placeholder: placeholder,
          allowClear: false,
          dropdownParent: jQuery('.task-edit-modal')
        });
      });
    }


    // Dropzone
    const dropzone = document.getElementById('taskDropzone');
    const fileInput = document.getElementById('taskFileInput');
    const filesList = document.getElementById('taskFilesList');

    function formatSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    }

    function renderFiles() {
      if (!filesList || !fileInput) return;
      filesList.innerHTML = '';
      if (!fileInput.files || !fileInput.files.length) return;
      Array.from(fileInput.files).forEach(function(f, i) {
        const div = document.createElement('div');
        div.className = 'task-files__item';
        div.innerHTML =
          '<i class="bi bi-file-earmark-text task-files__icon"></i>' +
          '<div class="task-files__info">' +
            '<div class="task-files__name">' + escapeHtml(f.name) + '</div>' +
            '<div class="task-files__meta">' + formatSize(f.size) + '</div>' +
          '</div>' +
          '<div class="task-files__actions">' +
            '<button type="button" class="task-files__action task-files__action--danger" data-idx="' + i + '" title="Убрать">' +
              '<i class="bi bi-x"></i>' +
            '</button>' +
          '</div>';
        filesList.appendChild(div);
      });
    }

    function escapeHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    dropzone?.addEventListener('click', function(e) {
      // Не дублировать клик — label сам триггерит input
    });

    dropzone?.addEventListener('dragover', function(e) {
      e.preventDefault();
      dropzone.classList.add('is-dragover');
    });
    dropzone?.addEventListener('dragleave', function() {
      dropzone.classList.remove('is-dragover');
    });
    dropzone?.addEventListener('drop', function(e) {
      e.preventDefault();
      dropzone.classList.remove('is-dragover');
      if (fileInput && e.dataTransfer.files && e.dataTransfer.files.length) {
        // Объединяем существующие файлы с дропнутыми
        const dt = new DataTransfer();
        if (fileInput.files) {
          Array.from(fileInput.files).forEach(function(f) { dt.items.add(f); });
        }
        Array.from(e.dataTransfer.files).forEach(function(f) { dt.items.add(f); });
        fileInput.files = dt.files;
        renderFiles();
      }
    });

    fileInput?.addEventListener('change', renderFiles);

    filesList?.addEventListener('click', function(e) {
      const btn = e.target.closest('.task-files__action--danger');
      if (!btn) return;
      e.preventDefault();
      const idx = parseInt(btn.getAttribute('data-idx'), 10);
      if (isNaN(idx) || !fileInput) return;
      const dt = new DataTransfer();
      Array.from(fileInput.files).forEach(function(f, i) {
        if (i !== idx) dt.items.add(f);
      });
      fileInput.files = dt.files;
      renderFiles();
    });
  }

  // DATE PICKER
  if (window.jQuery && jQuery.fn.datepicker) {
    jQuery('.task-edit-date').datepicker({
      format: 'dd.mm.yyyy',
      autoclose: true,
      todayHighlight: true,
      orientation: 'bottom auto'
    });
  }

  // ── INIT ═══════════════════════════════════════════════════════════════════
  function init() {
    initTasksList();
    initTaskDetail();
    initTaskEdit();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
