(function () {
    'use strict';
  
    const board = document.getElementById('tasksKanbanBoard');
    if (!board) return;
  
    const boardUrl = board.dataset.boardUrl;
    const patchUrlTemplate = board.dataset.patchUrlTemplate;
  
    const actionByStatus = {
      created: 'create',
      accepted: 'accept',
      revision: 'revision',
      completed: 'complete',
      rejected: 'reject'
    };
  
    function getCookie(name) {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; ${name}=`);
      if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
      return '';
    }
  
    function statusClass(priority) {
      if (!priority) return '';
      return `kanban-card--${priority}`;
    }
  
    function taskUrl(id) {
      return `/tasks/task/${id}`;
    }
  
    function patchUrl(id) {
      return patchUrlTemplate.replace('__TASK_ID__', id);
    }
  
    function renderCard(task) {
      const card = document.createElement('article');
      card.className = `kanban-card ${statusClass(task.priority)}`;
      card.draggable = true;
      card.dataset.taskId = task.id;
      card.dataset.availableActions = JSON.stringify(task.available_actions || []);
  
      card.innerHTML = `
        <div class="kanban-card__title">${task.title || 'Без названия'}</div>
        <div class="kanban-card__meta">
          <span>Автор: ${task.author || '—'}</span>
          <span>Исполнитель: ${task.executor || '—'}</span>
          <span>Срок: ${task.deadline || '—'}</span>
        </div>
      `;
  
      card.addEventListener('click', function (event) {
        if (card.classList.contains('is-dragging')) return;
        window.location.href = taskUrl(task.id);
      });
  
      card.addEventListener('dragstart', function (event) {
        card.classList.add('is-dragging');
        event.dataTransfer.setData('text/plain', task.id);
        event.dataTransfer.effectAllowed = 'move';
      });
  
      card.addEventListener('dragend', function () {
        card.classList.remove('is-dragging');
      });
  
      return card;
    }
  
    function renderColumn(column) {
      const col = document.createElement('section');
      col.className = 'kanban-column';
      col.dataset.status = column.status;
  
      col.innerHTML = `
        <div class="kanban-column__head">
          <h2 class="kanban-column__title">${column.title}</h2>
          <span class="kanban-column__count">${column.count || 0}</span>
        </div>
        <div class="kanban-column__body"></div>
      `;
  
      const body = col.querySelector('.kanban-column__body');
  
      if (column.tasks && column.tasks.length) {
        column.tasks.forEach(task => body.appendChild(renderCard(task)));
      } else {
        const empty = document.createElement('div');
        empty.className = 'kanban-empty';
        empty.textContent = 'Нет задач';
        body.appendChild(empty);
      }
  
      col.addEventListener('dragover', function (event) {
        event.preventDefault();
        col.classList.add('is-over');
      });
  
      col.addEventListener('dragleave', function () {
        col.classList.remove('is-over');
      });
  
      col.addEventListener('drop', async function (event) {
        event.preventDefault();
        col.classList.remove('is-over');
  
        const taskId = event.dataTransfer.getData('text/plain');
        const targetStatus = col.dataset.status;
        const draggedCard = board.querySelector(`[data-task-id="${taskId}"]`);
        if (!draggedCard) return;
  
        const availableActions = JSON.parse(draggedCard.dataset.availableActions || '[]');
        const action = actionByStatus[targetStatus] || targetStatus;
  
        if (!availableActions.includes(action)) {
          alert('Недоступное действие для этой задачи');
          return;
        }
  
        try {
          const response = await fetch(patchUrl(taskId), {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              'X-CSRFToken': getCookie('csrftoken'),
              'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ action: action })
          });
  
          const data = await response.json();
  
          if (!response.ok) {
            alert(data.error || 'Не удалось изменить статус');
            return;
          }
  
          await loadBoard();
        } catch (error) {
          alert('Ошибка сети');
        }
      });
  
      return col;
    }
  
    async function loadBoard() {
      board.innerHTML = '';
  
      const response = await fetch(boardUrl, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
  
      const data = await response.json();
  
      if (!data.board) {
        board.innerHTML = '<div class="tasks-empty">Не удалось загрузить канбан</div>';
        return;
      }
  
      data.board.forEach(column => {
        board.appendChild(renderColumn(column));
      });
    }
  
    loadBoard();
  })();