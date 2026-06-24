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
      timer = setTimeout(function () { fn.apply(context, args); }, wait);
    };
  }

  async function postAjax(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf(), 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
      body: body || null
    });
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : text;
    return div.innerHTML;
  }

  function formatSize(bytes) {
    if (!bytes) return '';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function buildFileHtml(url, name, size, ooUrl) {
    const ext = (name || '').toLowerCase();
    let icon = 'bi-file-earmark';
    let color = '#74728a';
    if (ext.endsWith('.pdf'))                          { icon = 'bi-file-earmark-pdf';   color = '#ef4444'; }
    else if (ext.match(/\.docx?$/))                   { icon = 'bi-file-earmark-word';  color = '#2563eb'; }
    else if (ext.match(/\.xlsx?$/))                   { icon = 'bi-file-earmark-excel'; color = '#16a34a'; }
    else if (ext.match(/\.(png|jpg|jpeg|gif|webp)$/)) { icon = 'bi-file-earmark-image'; color = '#0ea5e9'; }

    let actions = '';
    if (ooUrl) {
      actions += '<a href="' + escapeHtml(ooUrl) + '" target="_blank" ' +
        'style="display:inline-flex;align-items:center;justify-content:center;' +
        'width:28px;height:28px;border-radius:50%;background:#eef2ff;color:#2f6bed;margin-left:8px;text-decoration:none" title="Открыть в ONLYOFFICE">' +
        '<i class="bi bi-eye" style="font-size:13px"></i></a>';
    }
    if (url) {
      actions += '<a href="' + escapeHtml(url) + '" download target="_blank" ' +
        'style="display:inline-flex;align-items:center;justify-content:center;' +
        'width:28px;height:28px;border-radius:50%;background:#f5f3fa;color:#25233f;margin-left:4px;text-decoration:none" title="Скачать">' +
        '<i class="bi bi-download" style="font-size:13px"></i></a>';
    }

    const nameHtml = url
      ? '<a href="' + escapeHtml(url) + '" target="_blank" style="color:#25233f;text-decoration:none">' + escapeHtml(name || '') + '</a>'
      : escapeHtml(name || '');

    return '<div style="display:inline-flex;align-items:center;gap:10px;' +
      'padding:10px 14px;background:#f5f3fa;border-radius:12px;max-width:400px;">' +
      '<i class="bi ' + icon + '" style="font-size:22px;color:' + color + ';flex-shrink:0"></i>' +
      '<div style="min-width:0;flex:1">' +
        '<div style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + nameHtml + '</div>' +
        (size ? '<div style="font-size:11px;color:#74728a">' + escapeHtml(size) + '</div>' : '') +
      '</div>' +
      (actions ? '<div style="display:flex;flex-shrink:0;align-items:center">' + actions + '</div>' : '') +
      '</div>';
  }

  function parseFileComment(raw) {
    // Формат: __file__:URL:__name__:NAME:__size__:SIZE[:__oo__:OO_URL]
    if (!raw || !raw.startsWith('__file__:')) return null;
    try {
      const withoutPrefix = raw.slice('__file__:'.length);
      const nameIdx = withoutPrefix.indexOf(':__name__:');
      if (nameIdx === -1) return null;
      const urlPart = withoutPrefix.slice(0, nameIdx);
      const afterName = withoutPrefix.slice(nameIdx + ':__name__:'.length);
      const sizeIdx = afterName.indexOf(':__size__:');
      if (sizeIdx === -1) return { url: urlPart, name: afterName, size: '', ooUrl: null };
      const namePart = afterName.slice(0, sizeIdx);
      const afterSize = afterName.slice(sizeIdx + ':__size__:'.length);
      const ooIdx = afterSize.indexOf(':__oo__:');
      const sizePart = ooIdx === -1 ? afterSize : afterSize.slice(0, ooIdx);
      const ooUrl = ooIdx === -1 ? null : afterSize.slice(ooIdx + ':__oo__:'.length);
      return { url: urlPart, name: namePart, size: sizePart, ooUrl: ooUrl };
    } catch (e) {
      console.error('parseFileComment error:', e);
      return null;
    }
  }

  function notifyError(text) {
    if (window.bpmModal) window.bpmModal.alert(text, { variant: 'danger', title: 'Ошибка' });
    else alert(text);
  }

  // ============================================================
  // TASKS LIST
  // ============================================================
  function initTasksList() {
    const page = document.getElementById('tasksPage');
    if (!page) return;

    const tableWrap  = document.getElementById('tasksTableWrap');
    const search     = document.getElementById('taskSearch');
    const stateSel   = document.getElementById('taskStateFilter');
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
      stateSel?.addEventListener('change', updateFilters);
    }

    tableWrap?.addEventListener('click', function (event) {
      const row = event.target.closest('.tasks-table__row');
      if (!row) return;
      const href = row.getAttribute('data-href');
      if (href) window.location.href = href;
    });

    function updateFilters() {
      if (!filterForm) return;
      const params = new URLSearchParams(new FormData(filterForm));
      window.history.pushState({}, '', window.location.pathname + '?' + params.toString());
      filterForm.submit();
    }

    search?.addEventListener('input', debounce(updateFilters, 500));

    document.getElementById('taskSettingsBtn')?.addEventListener('click', function () {
      if (window.bpmModal) window.bpmModal.alert('Настройка отображения колонок будет реализована позже.', { variant: 'info', title: 'Скоро' });
      else alert('Настройка отображения колонок будет реализована позже.');
    });
  }

  // ============================================================
  // TASK DETAIL
  // ============================================================
  function initTaskDetail() {
    const taskPage = document.querySelector('.task-deal');
    if (!taskPage) return;

    // ── Рендерим файловые комментарии при загрузке страницы ──
    document.querySelectorAll('.task-feed__text').forEach(function (el) {
      // Читаем из data-raw атрибута (там оригинальный текст с escapejs)
      const raw = el.dataset.raw || '';
      const text = raw || el.innerText.trim();

      if (text.startsWith('__file__:')) {
        const parsed = parseFileComment(text);
        if (parsed) el.innerHTML = buildFileHtml(parsed.url, parsed.name, parsed.size, parsed.ooUrl);
        return;
      }

      // Старый формат: 📎 filename (size)
      if (text.startsWith('\uD83D\uDCCE ') || text.startsWith('📎 ')) {
        try {
          const inner = text.slice(2).trim();
          const match = inner.match(/^(.+?)\s+\(([^)]+)\)$/);
          const namePart = match ? match[1] : inner;
          const sizePart = match ? match[2] : '';
          el.innerHTML = buildFileHtml(null, namePart, sizePart, null);
        } catch (e) { console.error(e); }
      }
    });

    // ── accordions ──
    document.querySelectorAll('[data-acc]').forEach(function (acc) {
      acc.querySelector('[data-acc-toggle]')?.addEventListener('click', function () {
        acc.classList.toggle('is-open');
      });
    });

    // ── favorite toggle ──
    document.querySelectorAll('[data-task-toggle]').forEach(function (button) {
      const taskId  = button.getAttribute('data-task-id');
      const type    = button.getAttribute('data-task-toggle');
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

      button.addEventListener('click', async function (event) {
        event.preventDefault();
        const nextState = !button.classList.contains('is-active');
        applyState(nextState);
        button.disabled = true;
        try {
          const fd = new FormData();
          fd.append('flag', type);
          fd.append('state', nextState ? '1' : '0');
          const res  = await postAjax(flagUrl, fd);
          const data = await res.json().catch(function () { return {}; });
          if (!res.ok || data.ok === false) { applyState(!nextState); notifyError('Не удалось сохранить пометку.'); }
          else applyState(Boolean(data.active));
        } catch (e) { console.error(e); applyState(!nextState); notifyError('Ошибка сети.'); }
        finally { button.disabled = false; }
      });
    });

    // ── copy link ──
    document.querySelector('[data-copy-link]')?.addEventListener('click', function () {
      const url  = window.location.href;
      const done = function () {
        if (window.bpmModal) window.bpmModal.alert('Ссылка скопирована в буфер обмена', { variant: 'success', title: 'Готово' });
      };
      if (navigator.clipboard?.writeText) navigator.clipboard.writeText(url).then(done).catch(function () {});
      else {
        const tmp = document.createElement('input');
        tmp.value = url;
        document.body.appendChild(tmp);
        tmp.select();
        try { document.execCommand('copy'); done(); } catch (e) {}
        document.body.removeChild(tmp);
      }
    });

    // ── delete task ──
    document.querySelectorAll('[data-task-delete]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.preventDefault();
        const url = button.getAttribute('data-url');
        if (!url) return;
        let ok = window.bpmModal
          ? await window.bpmModal.confirm('Задача будет удалена без возможности восстановления.', { title: 'Удалить задачу?', variant: 'danger', confirmText: 'Удалить' })
          : confirm('Удалить задачу?');
        if (!ok) return;
        button.disabled = true;
        try {
          const res = await postAjax(url);
          if (res.ok) window.location.href = '/tasks/';
          else notifyError('Не удалось удалить задачу.');
        } catch (e) { console.error(e); notifyError('Ошибка сети.'); }
        finally { button.disabled = false; }
      });
    });

    // ── workflow actions ──
    document.querySelectorAll('[data-task-action]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.preventDefault();
        const url = button.getAttribute('data-url');
        if (!url) return;
        const label    = (button.textContent || 'действие').trim();
        const isDanger = button.getAttribute('data-task-action') === 'cancel' || /отклон|удал/i.test(label);
        let confirmed = window.bpmModal
          ? await window.bpmModal.confirm('Вы собираетесь выполнить: «' + label + '».', { title: 'Подтверждение действия', confirmText: label, variant: isDanger ? 'danger' : 'info', checkboxLabel: 'Подтверждаю выполнение действия' })
          : window.confirm('Выполнить «' + label + '»?');
        if (!confirmed) return;
        button.disabled = true;
        button.classList.add('is-loading');
        try {
          const res = await postAjax(url);
          let data = {};
          try { data = await res.json(); } catch (e) { if (res.ok) { window.location.reload(); return; } }
          if (res.ok && data.ok !== false) window.location.reload();
          else notifyError(data.message || 'Не удалось выполнить действие.');
        } catch (e) { console.error(e); notifyError('Ошибка сети.'); }
        finally { button.disabled = false; button.classList.remove('is-loading'); }
      });
    });

    // ── priority ──
    document.querySelector('.task-deal__priority-select')?.addEventListener('change', async function () {
      const fd = new FormData();
      fd.append('priority', this.value);
      try {
        const res = await postAjax(window.location.pathname, fd);
        if (!res.ok) notifyError('Не удалось изменить приоритет.');
      } catch (e) { console.error(e); notifyError('Ошибка сети.'); }
    });

    // ── description inline editor ──
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
        body.querySelector('[data-desc-save]').addEventListener('click', async function () {
          const fd = new FormData();
          fd.append('text', ta.value);
          try {
            const res = await postAjax(descBox.dataset.url, fd);
            if (res.ok) window.location.reload();
            else notifyError('Не удалось сохранить описание.');
          } catch (e) { notifyError('Ошибка сети.'); }
        });
        body.querySelector('[data-desc-cancel]').addEventListener('click', function () { window.location.reload(); });
      }

      descBox.addEventListener('click', function (e) {
        if (e.target.closest('[data-description-add]') || e.target.closest('[data-description-text]')) {
          e.preventDefault();
          openEditor();
        }
      });
    }

    // ── checklist ──
    document.querySelectorAll('[data-checklist-toggle]').forEach(function (btn) {
      btn.addEventListener('click', async function (e) {
        e.preventDefault();
        const url = btn.getAttribute('data-url');
        if (!url) return;
        const res = await postAjax(url);
        if (res.ok) window.location.reload();
      });
    });

    document.getElementById('taskChecklistForm')?.addEventListener('submit', async function (e) {
      e.preventDefault();
      const res = await postAjax(this.dataset.url, new FormData(this));
      if (res.ok) window.location.reload();
      else notifyError('Не удалось добавить пункт.');
    });

    document.getElementById('taskLineItemForm')?.addEventListener('submit', async function (e) {
      e.preventDefault();
      const res = await postAjax(this.dataset.url, new FormData(this));
      if (res.ok) window.location.reload();
      else notifyError('Не удалось добавить позицию.');
    });

    // ── files ──
    const fileInput = document.getElementById('taskFileInput');

    document.querySelector('[data-file-add]')?.addEventListener('click', function () {
      if (fileInput) { fileInput._fromComposer = false; fileInput.click(); }
    });

    document.querySelector('[data-composer-attach]')?.addEventListener('click', function () {
      if (fileInput) { fileInput._fromComposer = true; fileInput.click(); }
    });

    fileInput?.addEventListener('change', async function () {
      if (!fileInput.files.length) return;
      const fromComposer = !!fileInput._fromComposer;
      fileInput._fromComposer = false;

      const formData = new FormData();
      Array.from(fileInput.files).forEach(function (f) { formData.append('files', f); });
      fileInput.value = '';

      try {
        const res = await postAjax(fileInput.dataset.url, formData);
        if (!res.ok) { notifyError('Не удалось загрузить файл.'); return; }
        const data = await res.json().catch(function () { return {}; });

        if (fromComposer && data.files && data.files.length) {
          const commentForm = document.getElementById('taskCommentForm');
          const commentUrl  = commentForm ? commentForm.action : null;
          if (commentUrl) {
            for (const f of data.files) {
              const fd = new FormData();
              const ooSuffix = f.oo_url ? ':__oo__:' + f.oo_url : '';
              fd.append('text', '__file__:' + f.url + ':__name__:' + f.name + ':__size__:' + formatSize(f.size) + ooSuffix);
              fd.append('csrfmiddlewaretoken', getCsrf());
              await fetch(commentUrl, {
                method: 'POST',
                headers: { 'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': getCsrf() },
                credentials: 'same-origin',
                body: fd,
              }).catch(function (e) { console.error(e); });
            }
          }
        }

        window.location.reload();
      } catch (e) { console.error(e); notifyError('Ошибка сети.'); }
    });

    document.querySelectorAll('[data-file-delete]').forEach(function (btn) {
      btn.addEventListener('click', async function () {
        let ok = window.bpmModal
          ? await window.bpmModal.confirm('Удалить этот файл?', { title: 'Удаление файла', variant: 'danger', confirmText: 'Удалить' })
          : confirm('Удалить файл?');
        if (!ok) return;
        const res = await postAjax(btn.dataset.url);
        if (res.ok) btn.closest('[data-file-id]')?.remove();
        else notifyError('Не удалось удалить файл.');
      });
    });

    // ── comment form ──
    document.getElementById('taskCommentForm')?.addEventListener('submit', async function (e) {
      e.preventDefault();
      const input = this.querySelector('input[name="text"]');
      const text  = input.value.trim();
      if (!text) return;
      try {
        const res = await fetch(this.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          credentials: 'same-origin',
          body: new FormData(this),
        });
        if (!res.ok) throw new Error('comment failed');
        const data = await res.json();
        const feed = document.getElementById('taskFeedList');
        feed?.querySelector('.task-feed__empty')?.remove();

        const avatar = data.avatar ? '<img src="' + data.avatar + '" alt="">' : '<i class="bi bi-person-fill"></i>';
        feed?.insertAdjacentHTML('beforeend',
          '<div class="task-feed__item task-feed__item--comment">' +
            '<div class="task-feed__avatar">' + avatar + '</div>' +
            '<div class="task-feed__content">' +
              '<div class="task-feed__name">' + escapeHtml(data.name) + '</div>' +
              '<div class="task-feed__text" data-raw="">' + escapeHtml(data.text) + '</div>' +
            '</div>' +
            '<div class="task-feed__time">' + escapeHtml(data.date) + '</div>' +
          '</div>'
        );
        input.value = '';
      } catch (e) { console.error(e); notifyError('Не удалось отправить сообщение.'); }
    });
  }

  // ============================================================
  // TASK EDIT
  // ============================================================
  function initTaskEdit() {
    const form = document.getElementById('taskEditForm');
    if (!form) return;

    if (typeof jQuery !== 'undefined' && jQuery.fn.select2) {
      jQuery('#taskEditForm select').each(function () {
        const $s = jQuery(this);
        if ($s.hasClass('select2-hidden-accessible')) return;
        $s.select2({
          width: '100%',
          placeholder: $s.data('placeholder') || $s.find('option[value=""]').first().text() || 'Выберите',
          allowClear: false,
          dropdownParent: jQuery('.task-edit-card'),
          minimumResultsForSearch: $s.prop('multiple') ? 0 : Infinity
        });
      });
    }

    if (window.jQuery && jQuery.fn.datepicker) {
      jQuery('.task-edit-date').datepicker({ format: 'dd.mm.yyyy', autoclose: true, todayHighlight: true, orientation: 'bottom auto' });
    }

    const fileInput = document.getElementById('taskAttachments');
    const fileNames = document.getElementById('taskAttachmentNames');
    if (fileInput && fileNames) {
      fileInput.addEventListener('change', function () {
        fileNames.textContent = this.files && this.files.length > 0
          ? Array.from(this.files).map(function (f) { return f.name; }).join(', ')
          : 'Файлы не выбраны';
      });
    }
  }

  // ============================================================
  // INIT
  // ============================================================
  function init() { initTasksList(); initTaskDetail(); initTaskEdit(); }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();