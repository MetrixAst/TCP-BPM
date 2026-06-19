(function () {
  'use strict';

  const page = document.getElementById('ticketsKanbanPage');
  if (!page) return;

  const board = document.getElementById('ticketsKanbanBoard');
  const apiUrl = page.dataset.kanbanApi;
  const statusUrlTpl = page.dataset.statusUrlTpl || '/tickets/api/kanban/0/status/';

  // ── i18n: читаем переводы из data-атрибутов шаблона
  const i18n = {
    loading:          page.dataset.i18nLoading         || 'Загрузка…',
    noColumns:        page.dataset.i18nNoColumns        || 'Нет колонок',
    loadError:        page.dataset.i18nLoadError        || 'Не удалось загрузить канбан',
    moveConfirmMsg:   page.dataset.i18nMoveConfirmMsg   || 'Перевести заявку в статус «{title}»?',
    moveConfirmTitle: page.dataset.i18nMoveConfirmTitle || 'Смена статуса',
    moveConfirmText:  page.dataset.i18nMoveConfirmText  || 'Подтвердить',
    statusError:      page.dataset.i18nStatusError      || 'Не удалось сменить статус',
    networkError:     page.dataset.i18nNetworkError     || 'Ошибка сети при смене статуса',
    errorTitle:       page.dataset.i18nErrorTitle       || 'Ошибка',
  };

  let dragId = null;
  let dragFrom = null;
  let inFlight = false;

  function getCsrf() {
    const tag = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tag) return tag.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  function esc(t) {
    const d = document.createElement('div');
    d.textContent = t == null ? '' : t;
    return d.innerHTML;
  }

  function statusUrl(id) {
    return statusUrlTpl.replace('/0/', '/' + String(id) + '/');
  }

  function cardHtml(t) {
    let meta = '';
    if (t.tenant)     meta += '<span><i class="bi bi-shop"></i>'    + esc(t.tenant)     + '</span>';
    if (t.room)       meta += '<span><i class="bi bi-geo-alt"></i>' + esc(t.room)       + '</span>';
    if (t.assignee)   meta += '<span><i class="bi bi-person"></i>'  + esc(t.assignee)   + '</span>';
    if (t.created_at) meta += '<span><i class="bi bi-clock"></i>'   + esc(t.created_at) + '</span>';

    return (
      '<a class="tk-card tk-card--' + esc(t.status_color || 'neutral') + '"' +
        ' href="' + esc(t.url) + '" draggable="true"' +
        ' data-id="' + t.id + '" data-status="' + esc(t.status) + '">' +
        '<div class="tk-card__top">' +
          '<span class="tk-card__num">' + esc(t.number) + '</span>' +
          '<span class="tk-prio tk-prio--' + esc(t.priority_color || 'neutral') + '">' +
            '<span class="tk-prio__dot"></span>' + esc(t.priority_title) +
          '</span>' +
        '</div>' +
        '<div class="tk-card__title">' + esc(t.title) + '</div>' +
        '<div class="tk-card__cat">' + esc(t.category) + '</div>' +
        '<div class="tk-card__meta">' + meta + '</div>' +
      '</a>'
    );
  }

  function render(data) {
    const columns = (data && data.columns) || [];
    if (!columns.length) {
      board.innerHTML = '<div class="tk-kanban-loading">' + esc(i18n.noColumns) + '</div>';  // ── i18n
      return;
    }

    let html = '<div class="tk-board">';
    columns.forEach(function (col) {
      html +=
        '<div class="tk-col" data-drop-zone data-status="' + esc(col.status) + '">' +
          '<div class="tk-col__head">' +
            '<span class="tk-col__dot tk-badge--' + esc(col.color) + '"></span>' +
            esc(col.title) +
            '<span class="tk-col__count">' + col.count + '</span>' +
          '</div>' +
          '<div class="tk-col__body">';

      if (!col.tickets.length) {
        html += '<div class="tk-col__empty">—</div>';
      } else {
        col.tickets.forEach(function (t) { html += cardHtml(t); });
      }

      html += '</div></div>';
    });
    html += '</div>';

    board.innerHTML = html;
    bindEvents();
  }

  function bindEvents() {
    board.querySelectorAll('.tk-card').forEach(function (card) {
      card.addEventListener('dragstart', function () {
        dragId   = card.getAttribute('data-id');
        dragFrom = card.getAttribute('data-status');
        card.classList.add('is-dragging');
      });
      card.addEventListener('dragend', function () {
        card.classList.remove('is-dragging');
      });
      card.addEventListener('click', function (e) {
        if (card.classList.contains('is-dragging')) e.preventDefault();
      });
    });

    board.querySelectorAll('[data-drop-zone]').forEach(function (zone) {
      zone.addEventListener('dragover',  function (e) { e.preventDefault(); zone.classList.add('is-drag-over'); });
      zone.addEventListener('dragleave', function ()  { zone.classList.remove('is-drag-over'); });
      zone.addEventListener('drop', function (e) {
        e.preventDefault();
        zone.classList.remove('is-drag-over');
        const target = zone.getAttribute('data-status');
        if (!dragId || inFlight || target === dragFrom) { dragId = null; return; }
        confirmMove(dragId, target);
      });
    });
  }

  function colTitle(status) {
    const head = board.querySelector('[data-status="' + status + '"] .tk-col__head');
    return head ? head.textContent.replace(/\d+$/, '').trim() : status;
  }

  async function confirmMove(id, target) {
    const title = colTitle(target);
    const msg = i18n.moveConfirmMsg.replace('{title}', title);  // ── i18n
    const proceed = window.bpmModal
      ? await window.bpmModal.confirm(msg, {
          title: i18n.moveConfirmTitle,      // ── i18n
          confirmText: i18n.moveConfirmText, // ── i18n
          variant: 'info',
        })
      : window.confirm(msg);
    if (!proceed) { dragId = null; dragFrom = null; return; }
    move(id, target);
  }

  function showError(msg) {
    if (window.bpmModal) window.bpmModal.alert(msg, { variant: 'danger', title: i18n.errorTitle });  // ── i18n
    else alert(msg);
  }

  async function load() {
    const res = await fetch(apiUrl, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('load failed');
    render(await res.json());
  }

  async function move(id, target) {
    inFlight = true;
    try {
      const res = await fetch(statusUrl(id), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrf(),
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ status: target }),
      });
      const data = await res.json().catch(function () { return {}; });
      if (!res.ok || data.ok === false) {
        showError(data.message || i18n.statusError);  // ── i18n
        await load();
        return;
      }
      if (data.kanban) render(data.kanban); else await load();
    } catch (err) {
      console.error(err);
      showError(i18n.networkError);  // ── i18n
      try { await load(); } catch (e) { console.error(e); }
    } finally {
      inFlight = false; dragId = null; dragFrom = null;
    }
  }

  load().catch(function () {
    board.innerHTML = '<div class="tk-kanban-loading">' + esc(i18n.loadError) + '</div>';  // ── i18n
  });
})();