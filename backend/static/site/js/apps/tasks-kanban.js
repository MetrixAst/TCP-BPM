(function () {
  'use strict';

  function getCsrf() {
    const tag = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tag) return tag.value;
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
  }

  const page = document.getElementById('tasksKanbanPage');
  if (!page) return;

  const board = document.getElementById('tasksKanbanBoard');
  const apiUrl = page.dataset.kanbanApi;
  const statusUrlTpl = page.dataset.statusUrlTpl || '/tasks/api/kanban/0/status/';

  // ── i18n: читаем все переводы из data-атрибутов шаблона
  const i18n = {
    loading:          page.dataset.i18nLoading         || 'Загрузка…',
    executor:         page.dataset.i18nExecutor        || 'Исполнитель',
    noTasks:          page.dataset.i18nNoTasks         || 'Нет задач',
    noExecutor:       page.dataset.i18nNoExecutor      || 'Без исполнителя',
    noColumns:        page.dataset.i18nNoColumns       || 'Нет колонок статусов',
    noTasksHint:      page.dataset.i18nNoTasksHint     || 'Задач пока нет. Создайте задачу или назначьте исполнителя.',
    loadError:        page.dataset.i18nLoadError       || 'Не удалось загрузить канбан',
    networkError:     page.dataset.i18nNetworkError    || 'Ошибка сети при смене статуса',
    statusError:      page.dataset.i18nStatusError     || 'Не удалось сменить статус',
    moveConfirmTitle: page.dataset.i18nMoveConfirmTitle|| 'Смена статуса',
    moveConfirmText:  page.dataset.i18nMoveConfirmText || 'Подтвердить',
    moveConfirmMsg:   page.dataset.i18nMoveConfirmMsg  || 'Перевести задачу в статус «{title}»?',
    errorTitle:       page.dataset.i18nErrorTitle      || 'Ошибка',
    // приоритеты
    priorityLow:      page.dataset.i18nPriorityLow      || 'Низкий',
    priorityMedium:   page.dataset.i18nPriorityMedium   || 'Средний',
    priorityHigh:     page.dataset.i18nPriorityHigh     || 'Высокий',
    priorityCritical: page.dataset.i18nPriorityCritical || 'Критический',
  };

  let dragTaskId = null;
  let dragFromStatus = null;
  let moveInFlight = false;

  // ── PRIORITY теперь берёт label из i18n
  function getPriority(key) {
    const map = {
      low:      { label: i18n.priorityLow,      cls: 'low' },
      medium:   { label: i18n.priorityMedium,   cls: 'medium' },
      high:     { label: i18n.priorityHigh,     cls: 'high' },
      critical: { label: i18n.priorityCritical, cls: 'critical' },
    };
    return map[key] || null;
  }

  function formatDeadline(iso) {
    if (!iso) return '';
    const parts = iso.split('-');
    if (parts.length === 3) return parts[2] + '.' + parts[1] + '.' + parts[0];
    return iso;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
  }

  function statusUrl(taskId) {
    return statusUrlTpl.replace('/0/', '/' + String(taskId) + '/');
  }

  function buildSwimlaneData(data) {
    const columns = data.columns || [];
    const statuses = columns.map(function (col) {
      return { status: col.status, title: col.title, color: col.color || 'neutral' };
    });

    const rowsMap = {};

    columns.forEach(function (column) {
      (column.tasks || []).forEach(function (task) {
        const key = task.executor_id ? String(task.executor_id) : '_none';
        if (!rowsMap[key]) {
          rowsMap[key] = {
            executor_id: task.executor_id,
            executor: task.executor || i18n.noExecutor,  // ── i18n
            byStatus: {},
          };
        }
        if (!rowsMap[key].byStatus[column.status]) {
          rowsMap[key].byStatus[column.status] = [];
        }
        rowsMap[key].byStatus[column.status].push(task);
      });
    });

    const rows = Object.keys(rowsMap)
      .map(function (k) { return rowsMap[k]; })
      .sort(function (a, b) {
        return (a.executor || '').localeCompare(b.executor || '', 'ru');
      });

    return { statuses: statuses, rows: rows };
  }

  function renderBoard(data) {
    const swim = buildSwimlaneData(data);
    const statuses = swim.statuses;
    const rows = swim.rows;
    board.__statuses = statuses;

    if (!statuses.length) {
      board.innerHTML = '<div class="tasks-kanban__error">' + escapeHtml(i18n.noColumns) + '</div>';  // ── i18n
      return;
    }

    const colCount = statuses.length;

    const boardWidth = board.offsetWidth || 1000;
    const executorColW = 130;
    const statusColW = Math.floor((boardWidth - executorColW) / colCount);
    const gridCols = executorColW + 'px repeat(' + colCount + ', ' + statusColW + 'px)';

    let html = '<div class="tasks-kanban-swim" style="--kanban-cols:' + colCount + '">';

    html += '<div class="tasks-kanban-swim__head" style="grid-template-columns:' + gridCols + '">';
    html += '<div class="tasks-kanban-swim__head-cell tasks-kanban-swim__head-cell--corner">' + escapeHtml(i18n.executor) + '</div>';  // ── i18n
    statuses.forEach(function (st) {
      html +=
        '<div class="tasks-kanban-swim__head-cell">' +
          '<span class="tasks-kanban__dot tasks-status--' + st.color + '"></span>' +
          escapeHtml(st.title) +
        '</div>';
    });
    html += '</div>';

    if (!rows.length) {
      html +=
        '<div class="tasks-kanban-swim__empty">' +
          escapeHtml(i18n.noTasksHint) +  // ── i18n
        '</div>';
    } else {
      rows.forEach(function (row) {
        html +=
          '<div class="tasks-kanban-swim__lane" style="grid-template-columns:' + gridCols + '">';

        html +=
          '<div class="tasks-kanban-swim__lane-user">' +
            '<span class="tasks-kanban__assignee-avatar">' +
              escapeHtml((row.executor || '?').charAt(0).toUpperCase()) +
            '</span>' +
            '<span class="tasks-kanban-swim__lane-name">' + escapeHtml(row.executor) + '</span>' +
          '</div>';

        statuses.forEach(function (st) {
          const tasks = (row.byStatus[st.status] || []);
          html +=
            '<div class="tasks-kanban-swim__cell" data-drop-zone data-status="' + st.status + '">';

          tasks.forEach(function (task) {
            html += cardHtml(task);
          });

          html += '</div>';
        });

        html += '</div>';
      });
    }

    html += '</div>';
    board.innerHTML = html;

    board.querySelectorAll('[data-drop-zone]').forEach(function (zone) {
      zone.addEventListener('dragover', function (e) {
        e.preventDefault();
        zone.classList.add('is-drag-over');
      });

      zone.addEventListener('dragleave', function () {
        zone.classList.remove('is-drag-over');
      });

      zone.addEventListener('drop', function (e) {
        e.preventDefault();
        zone.classList.remove('is-drag-over');
        if (!dragTaskId || moveInFlight) return;
        const newStatus = zone.getAttribute('data-status');
        if (newStatus === dragFromStatus) { dragTaskId = null; return; }
        confirmMove(dragTaskId, newStatus, dragFromStatus);
      });
    });

    board.querySelectorAll('.tasks-kanban__card').forEach(function (card) {
      bindCardDrag(card);
    });
  }

  function cardHtml(task) {
    const prio = getPriority(task.priority);  // ── i18n через функцию
    const initial = task.executor ? escapeHtml(task.executor.charAt(0).toUpperCase()) : '';
    const prioLabel = prio ? prio.label : (task.priority_title || '');

    return (
      '<a class="tasks-kanban__card tasks-kanban__card--' + (task.status_color || 'neutral') + '"' +
        ' href="' + escapeHtml(task.url) + '"' +
        ' draggable="true"' +
        ' data-task-id="' + task.id + '"' +
        ' data-status="' + escapeHtml(task.status || '') + '">' +
        '<div class="tasks-kanban__card-head">' +
          '<span class="tasks-kanban__card-num">' + escapeHtml(task.number || ('#' + task.id)) + '</span>' +
          (task.type ? '<span class="tasks-kanban__card-type">' + escapeHtml(task.type) + '</span>' : '') +
        '</div>' +
        '<div class="tasks-kanban__card-top">' +
          '<div class="tasks-kanban__card-title">' + escapeHtml(task.title) + '</div>' +
        '</div>' +
        (prio
          ? '<div class="tasks-kanban__card-prio"><span class="tasks-kanban__prio tasks-kanban__prio--' + prio.cls + '"></span>' + escapeHtml(prioLabel) + '</div>'
          : '') +
        '<div class="tasks-kanban__card-meta">' +
          (task.executor
            ? '<span class="tasks-kanban__assignee"><span class="tasks-kanban__assignee-avatar">' + initial + '</span>' + escapeHtml(task.executor) + '</span>'
            : '') +
          (task.deadline
            ? '<span class="tasks-kanban__deadline"><i class="bi bi-calendar3"></i>' + formatDeadline(task.deadline) + '</span>'
            : '') +
        '</div>' +
      '</a>'
    );
  }

  function bindCardDrag(card) {
    card.addEventListener('dragstart', function () {
      dragTaskId = card.getAttribute('data-task-id');
      dragFromStatus = card.getAttribute('data-status');
      card.classList.add('is-dragging');
    });

    card.addEventListener('dragend', function () {
      card.classList.remove('is-dragging');
      if (!moveInFlight) {
        dragTaskId = null;
        dragFromStatus = null;
      }
    });

    card.addEventListener('click', function (e) {
      if (card.classList.contains('is-dragging')) {
        e.preventDefault();
      }
    });
  }

  function statusTitle(status) {
    const map = {};
    (board.__statuses || []).forEach(function (s) { map[s.status] = s.title; });
    return map[status] || status;
  }

  async function confirmMove(taskId, newStatus, fromStatus) {
    const title = statusTitle(newStatus);
    const msg = i18n.moveConfirmMsg.replace('{title}', title);  // ── i18n
    const proceed = window.bpmModal
      ? await window.bpmModal.confirm(msg, {
          title: i18n.moveConfirmTitle,        // ── i18n
          confirmText: i18n.moveConfirmText,   // ── i18n
          variant: 'info',
        })
      : window.confirm(msg);
    if (!proceed) { dragTaskId = null; dragFromStatus = null; return; }
    moveTask(taskId, newStatus, fromStatus);
  }

  function showError(message) {
    if (window.bpmModal) {
      window.bpmModal.alert(message, { variant: 'danger', title: i18n.errorTitle });  // ── i18n
    } else {
      alert(message);
    }
  }

  async function loadBoard() {
    const res = await fetch(apiUrl, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('load failed');
    const data = await res.json();
    renderBoard(data);
  }

  async function moveTask(taskId, newStatus, fromStatus) {
    if (moveInFlight) return;
    if (fromStatus && fromStatus === newStatus) {
      dragTaskId = null;
      dragFromStatus = null;
      return;
    }

    moveInFlight = true;

    try {
      const res = await fetch(statusUrl(taskId), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrf(),
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ status: newStatus }),
      });

      let data = {};
      try {
        data = await res.json();
      } catch (parseErr) {
        if (res.ok) {
          await loadBoard();
          return;
        }
        throw parseErr;
      }

      if (!res.ok || data.ok === false) {
        showError(data.message || i18n.statusError);  // ── i18n
        await loadBoard();
        return;
      }

      if (data.kanban) {
        renderBoard(data.kanban);
      } else {
        await loadBoard();
      }
    } catch (err) {
      console.error(err);
      showError(i18n.networkError);  // ── i18n
      try {
        await loadBoard();
      } catch (loadErr) {
        console.error(loadErr);
      }
    } finally {
      moveInFlight = false;
      dragTaskId = null;
      dragFromStatus = null;
    }
  }

  loadBoard().catch(function () {
    board.innerHTML = '<div class="tasks-kanban__error">' + escapeHtml(i18n.loadError) + '</div>';  // ── i18n
  });
})();