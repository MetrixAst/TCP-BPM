(function () {
  'use strict';

  function getCsrf() {
    const tag = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tag) return tag.value;

    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  function debounce(fn, wait) {
    let timer;

    return function () {
      const context = this;
      const args = arguments;

      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(context, args);
      }, wait);
    };
  }

  async function postAjax(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': getCsrf(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      credentials: 'same-origin',
      body: body || null
    });
  }

  function initTasksList() {
    const page = document.getElementById('tasksPage');
    if (!page) return;

    const tableWrap = document.getElementById('tasksTableWrap');
    const search = document.getElementById('taskSearch');
    const stateSel = document.getElementById('taskStateFilter');
    const filterForm = document.getElementById('tasksFilterForm');

    if (typeof jQuery !== 'undefined' && jQuery.fn.select2 && stateSel) {
      const $stateSel = jQuery(stateSel);
    
if (!$stateSel.hasClass('select2-hidden-accessible')) {
        $stateSel.select2({
          width: '170px',
          minimumResultsForSearch: Infinity,
          dropdownParent: jQuery('#tasksPage')
        });
      }

      if (window.BPM && window.BPM.applyTranslations) {
        window.BPM.applyTranslations();
      }

      $stateSel.on('change', updateFiltersWithoutReload);
    } else {
      stateSel?.addEventListener('change', updateFiltersWithoutReload);
    }

    tableWrap?.addEventListener('click', function (event) {
      const row = event.target.closest('.tasks-table__row');
      if (!row) return;

      const href = row.getAttribute('data-href');
      if (href) window.location.href = href;
    });

    function updateFiltersWithoutReload() {
      if (!filterForm) return;

      const params = new URLSearchParams(new FormData(filterForm));
      const url = `${window.location.pathname}?${params.toString()}`;

      window.history.pushState({}, '', url);

      filterForm.submit();
    }

    search?.addEventListener('input', debounce(updateFiltersWithoutReload, 500));

    const settingsBtn = document.getElementById('taskSettingsBtn');
    settingsBtn?.addEventListener('click', function () {
      if (window.bpmModal) {
        window.bpmModal.alert('Настройка отображения колонок будет реализована позже.', { variant: 'info', title: 'Скоро' });
      } else {
        alert('Настройка отображения колонок будет реализована позже.');
      }
    });
  }

  function notifyError(text) {
    if (window.bpmModal) {
      window.bpmModal.alert(text, { variant: 'danger', title: 'Ошибка' });
    } else {
      alert(text);
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : text;
    return div.innerHTML;
  }

  function initTaskDetail() {
    const taskPage = document.querySelector('.task-deal');
    if (!taskPage) return;

    // --- accordions ---
    document.querySelectorAll('[data-acc]').forEach(function (acc) {
      const head = acc.querySelector('[data-acc-toggle]');
      head?.addEventListener('click', function () {
        acc.classList.toggle('is-open');
      });
    });

    // --- favorite toggle (persisted in DB) ---
    document.querySelectorAll('[data-task-toggle]').forEach(function (button) {
      const taskId = button.getAttribute('data-task-id');
      const type = button.getAttribute('data-task-toggle');
      const flagUrl = button.getAttribute('data-flag-url');
      if (!taskId || !type || !flagUrl) return;

      const icon = button.querySelector('i');

      function applyState(isActive) {
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        if (type === 'favorite' && icon) {
          icon.classList.toggle('bi-star', !isActive);
          icon.classList.toggle('bi-star-fill', isActive);
        }
      }

      // Initial state is rendered server-side; JS only persists changes.
      button.addEventListener('click', async function (event) {
        event.preventDefault();
        const nextState = !button.classList.contains('is-active');
        applyState(nextState);
        button.disabled = true;
        try {
          const formData = new FormData();
          formData.append('flag', type);
          formData.append('state', nextState ? '1' : '0');
          const response = await postAjax(flagUrl, formData);
          const data = await response.json().catch(function () { return {}; });
          if (!response.ok || data.ok === false) {
            applyState(!nextState);
            notifyError('Не удалось сохранить пометку.');
          } else {
            applyState(Boolean(data.active));
          }
        } catch (error) {
          console.error(error);
          applyState(!nextState);
          notifyError('Ошибка сети.');
        } finally {
          button.disabled = false;
        }
      });
    });

    // --- copy link ---
    const copyBtn = document.querySelector('[data-copy-link]');
    copyBtn?.addEventListener('click', function () {
      const url = window.location.href;
      const done = function () {
        if (window.bpmModal) {
          window.bpmModal.alert('Ссылка скопирована в буфер обмена', { variant: 'success', title: 'Готово' });
        }
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done).catch(function () {});
      } else {
        const tmp = document.createElement('input');
        tmp.value = url;
        document.body.appendChild(tmp);
        tmp.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(tmp);
      }
    });

    // --- delete task (modal confirm) ---
    document.querySelectorAll('[data-task-delete]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.preventDefault();
        const url = button.getAttribute('data-url');
        if (!url) return;

        let ok = true;
        if (window.bpmModal) {
          ok = await window.bpmModal.confirm('Задача будет удалена без возможности восстановления.', {
            title: 'Удалить задачу?', variant: 'danger', confirmText: 'Удалить'
          });
        } else {
          ok = confirm('Удалить задачу?');
        }
        if (!ok) return;

        button.disabled = true;
        try {
          const response = await postAjax(url);
          if (response.ok) {
            window.location.href = '/tasks/';
          } else {
            notifyError('Не удалось удалить задачу.');
          }
        } catch (error) {
          console.error(error);
          notifyError('Ошибка сети.');
        } finally {
          button.disabled = false;
        }
      });
    });

    // --- workflow actions ---
    document.querySelectorAll('[data-task-action]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.preventDefault();
        const url = button.getAttribute('data-url');
        if (!url) return;

        // Подтверждение смены статуса: галочка + подтвердить
        const label = (button.textContent || 'действие').trim();
        const isDanger = button.getAttribute('data-task-action') === 'cancel'
          || /отклон|удал/i.test(label);
        let confirmed;
        if (window.bpmModal) {
          confirmed = await window.bpmModal.confirm(
            'Вы собираетесь выполнить: «' + label + '».',
            {
              title: 'Подтверждение действия',
              confirmText: label,
              variant: isDanger ? 'danger' : 'info',
              checkboxLabel: 'Подтверждаю выполнение действия'
            }
          );
        } else {
          confirmed = window.confirm('Выполнить «' + label + '»?');
        }
        if (!confirmed) return;

        button.disabled = true;
        button.classList.add('is-loading');
        try {
          const response = await postAjax(url);
          let data = {};
          try {
            data = await response.json();
          } catch (parseErr) {
            if (response.ok) {
              window.location.reload();
              return;
            }
          }
          if (response.ok && data.ok !== false) {
            window.location.reload();
          } else {
            notifyError(data.message || 'Не удалось выполнить действие.');
          }
        } catch (error) {
          console.error(error);
          notifyError('Ошибка сети.');
        } finally {
          button.disabled = false;
          button.classList.remove('is-loading');
        }
      });
    });

    // --- priority ---
    const prioritySelect = document.querySelector('.task-deal__priority-select');
    prioritySelect?.addEventListener('change', async function () {
      const formData = new FormData();
      formData.append('priority', prioritySelect.value);
      try {
        const response = await postAjax(window.location.pathname, formData);
        if (!response.ok) notifyError('Не удалось изменить приоритет.');
      } catch (error) {
        console.error(error);
        notifyError('Ошибка сети.');
      }
    });

    // --- description inline editor ---
    const descBox = document.getElementById('taskDescription');
    if (descBox && descBox.dataset.canEdit === '1') {
      const body = descBox.querySelector('.task-deal__description-body');

      function openEditor() {
        const current = descBox.querySelector('[data-description-text]');
        const initial = current ? current.innerText.trim() : '';
        body.innerHTML =
          '<textarea class="task-deal__description-editor">' + escapeHtml(initial) + '</textarea>' +
          '<div class="task-deal__description-editor-actions">' +
            '<button type="button" class="task-deal__action-btn task-deal__action-btn--primary" data-desc-save>Сохранить</button>' +
            '<button type="button" class="task-deal__action-btn task-deal__action-btn--danger" data-desc-cancel>Отмена</button>' +
          '</div>';
        const ta = body.querySelector('textarea');
        ta.focus();
        body.querySelector('[data-desc-save]').addEventListener('click', saveEditor);
        body.querySelector('[data-desc-cancel]').addEventListener('click', function () { window.location.reload(); });
      }

      async function saveEditor() {
        const ta = body.querySelector('textarea');
        const formData = new FormData();
        formData.append('text', ta.value);
        try {
          const res = await postAjax(descBox.dataset.url, formData);
          if (res.ok) window.location.reload();
          else notifyError('Не удалось сохранить описание.');
        } catch (e) {
          notifyError('Ошибка сети.');
        }
      }

      descBox.addEventListener('click', function (e) {
        if (e.target.closest('[data-description-add]') || e.target.closest('[data-description-text]')) {
          e.preventDefault();
          openEditor();
        }
      });
    }

    // --- checklist ---
    document.querySelectorAll('[data-checklist-toggle]').forEach(function (btn) {
      btn.addEventListener('click', async function (e) {
        e.preventDefault();
        const url = btn.getAttribute('data-url');
        if (!url) return;
        const res = await postAjax(url);
        if (res.ok) window.location.reload();
      });
    });

    const checklistForm = document.getElementById('taskChecklistForm');
    checklistForm?.addEventListener('submit', async function (e) {
      e.preventDefault();
      const res = await postAjax(checklistForm.dataset.url, new FormData(checklistForm));
      if (res.ok) window.location.reload();
      else notifyError('Не удалось добавить пункт.');
    });

    const lineItemForm = document.getElementById('taskLineItemForm');
    lineItemForm?.addEventListener('submit', async function (e) {
      e.preventDefault();
      const res = await postAjax(lineItemForm.dataset.url, new FormData(lineItemForm));
      if (res.ok) window.location.reload();
      else notifyError('Не удалось добавить позицию.');
    });

    // --- files ---
    const fileInput = document.getElementById('taskFileInput');
    document.querySelector('[data-file-add]')?.addEventListener('click', function () {
      fileInput?.click();
    });
    fileInput?.addEventListener('change', async function () {
      if (!fileInput.files.length) return;
      const formData = new FormData();
      Array.from(fileInput.files).forEach(function (f) { formData.append('files', f); });
      try {
        const res = await postAjax(fileInput.dataset.url, formData);
        if (res.ok) window.location.reload();
        else notifyError('Не удалось загрузить файл.');
      } catch (e) {
        notifyError('Ошибка сети.');
      }
    });

    document.querySelectorAll('[data-file-delete]').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        let ok = true;
        if (window.bpmModal) {
          ok = await window.bpmModal.confirm('Удалить этот файл?', {
            title: 'Удаление файла', variant: 'danger', confirmText: 'Удалить'
          });
        } else {
          ok = confirm('Удалить файл?');
        }
        if (!ok) return;
        const res = await postAjax(btn.dataset.url);
        if (res.ok) {
          const item = btn.closest('[data-file-id]');
          item?.remove();
        } else {
          notifyError('Не удалось удалить файл.');
        }
      });
    });

    // --- composer attach uses the same file input ---
    document.querySelector('[data-composer-attach]')?.addEventListener('click', function () {
      fileInput?.click();
    });

    // --- comment form ---
    const commentForm = document.getElementById('taskCommentForm');
    commentForm?.addEventListener('submit', async function (e) {
      e.preventDefault();
      const input = commentForm.querySelector('input[name="text"]');
      const text = input.value.trim();
      if (!text) return;

      try {
        const response = await fetch(commentForm.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin',
          body: new FormData(commentForm),
        });
        if (!response.ok) throw new Error('comment failed');
        const data = await response.json();

        const feed = document.getElementById('taskFeedList');
        const emptyEl = feed?.querySelector('.task-feed__empty');
        if (emptyEl) emptyEl.remove();

        const avatar = data.avatar
          ? '<img src="' + data.avatar + '" alt="">'
          : '<i class="bi bi-person-fill"></i>';

        const html =
          '<div class="task-feed__item task-feed__item--comment">' +
            '<div class="task-feed__avatar">' + avatar + '</div>' +
            '<div class="task-feed__content">' +
              '<div class="task-feed__name">' + escapeHtml(data.name) + '</div>' +
              '<div class="task-feed__text">' + escapeHtml(data.text) + '</div>' +
            '</div>' +
            '<div class="task-feed__time">' + escapeHtml(data.date) + '</div>' +
          '</div>';

        feed?.insertAdjacentHTML('beforeend', html);
        input.value = '';
      } catch (error) {
        console.error(error);
        notifyError('Не удалось отправить сообщение.');
      }
    });
  }

  function initTaskEdit() {
    const form = document.getElementById('taskEditForm');
    if (!form) return;

    if (typeof jQuery !== 'undefined' && jQuery.fn.select2) {
      jQuery('#taskEditForm select').each(function () {
        const $select = jQuery(this);

        if ($select.hasClass('select2-hidden-accessible')) return;

        const placeholder =
          $select.data('placeholder') ||
          $select.find('option[value=""]').first().text() ||
          'Выберите';

        $select.select2({
          width: '100%',
          placeholder: placeholder,
          allowClear: false,
          dropdownParent: jQuery('.task-edit-card'),
          minimumResultsForSearch: $select.prop('multiple') ? 0 : Infinity
        });
      });
    }

    if (window.jQuery && jQuery.fn.datepicker) {
      jQuery('.task-edit-date').datepicker({
        format: 'dd.mm.yyyy',
        autoclose: true,
        todayHighlight: true,
        orientation: 'bottom auto'
      });
    }

    const fileInput = document.getElementById('taskAttachments');
    const fileNames = document.getElementById('taskAttachmentNames');
    if (fileInput && fileNames) {
      fileInput.addEventListener('change', function () {
        if (this.files && this.files.length > 0) {
          const names = Array.from(this.files).map(function (f) { return f.name; });
          fileNames.textContent = names.join(', ');
        } else {
          fileNames.textContent = 'Файлы не выбраны';
        }
      });
    }
  }

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