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
      alert('Настройка отображения колонок будет реализована позже.');
    });
  }

  function initTaskDetail() {
    const taskPage = document.querySelector('.task-page');
    if (!taskPage) return;



    document.querySelectorAll('[data-task-toggle]').forEach(function (button) {
      const taskId = button.getAttribute('data-task-id');
      const type = button.getAttribute('data-task-toggle');
    
      if (!taskId || !type) return;
    
      const key = 'task_' + taskId + '_' + type;
      const icon = button.querySelector('i');
    
      function applyState(isActive) {
        button.classList.toggle('is-active', isActive);
    
        if (type === 'favorite' && icon) {
          icon.classList.toggle('bi-star', !isActive);
          icon.classList.toggle('bi-star-fill', isActive);
        }
    
        if (type === 'urgent' && icon) {
          icon.classList.add('bi-fire');
        }
      }
    
      applyState(localStorage.getItem(key) === '1');
    
      button.addEventListener('click', function (event) {
        event.preventDefault();
    
        const nextState = !button.classList.contains('is-active');
        localStorage.setItem(key, nextState ? '1' : '0');
        applyState(nextState);
      });
    });

    document.querySelectorAll('[data-task-delete]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.preventDefault();

        const url = button.getAttribute('data-url');
        if (!url) return;

        const ok = confirm('Удалить задачу?');
        if (!ok) return;

        button.disabled = true;

        try {
          const response = await postAjax(url);

          if (response.ok) {
            window.location.href = '/tasks/';
          } else {
            alert('Не удалось удалить задачу.');
          }
        } catch (error) {
          console.error(error);
          alert('Ошибка сети.');
        } finally {
          button.disabled = false;
        }
      });
    });

    document.querySelectorAll('[data-task-action]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.preventDefault();
    
        const url = button.getAttribute('data-url');
        if (!url) return;
    
        button.disabled = true;
        button.classList.add('is-loading');
    
        try {
          const response = await postAjax(url);
    
          if (response.ok) {
            window.location.reload();
          } else {
            alert('Не удалось выполнить действие.');
          }
        } catch (error) {
          console.error(error);
          alert('Ошибка сети.');
        } finally {
          button.disabled = false;
          button.classList.remove('is-loading');
        }
      });
    });
    
    const prioritySelect = document.querySelector('.task-card__priority-select');
    prioritySelect?.addEventListener('change', async function () {
      const formData = new FormData();
      formData.append('priority', prioritySelect.value);

      try {
        const response = await postAjax(window.location.pathname, formData);

        if (!response.ok) {
          alert('Не удалось изменить приоритет.');
        }
      } catch (error) {
        console.error(error);
        alert('Ошибка сети.');
      }
    });

    const commentForm = document.getElementById('taskCommentForm');

    if (commentForm) {
        commentForm.addEventListener('submit', async (e) => {
            e.preventDefault();
    
            const input = commentForm.querySelector('input[name="text"]');
            const text = input.value.trim();
    
            if (!text) return;
    
            const formData = new FormData(commentForm);
    
            try {
                const response = await fetch(commentForm.action, {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                    },
                    body: formData,
                });
    
                if (!response.ok) {
                    throw new Error('Ошибка отправки комментария');
                }
    
                const data = await response.json();
    
                const historyList = document.getElementById('taskHistoryList');
    
                const avatar = data.avatar
                ? '<img src="' + data.avatar + '" alt="">'
                : '<i class="bi bi-person-fill"></i>';
              
                const commentHtml =
                  '<div class="task-history__item task-history__item--comment">' +
                    '<div class="task-history__avatar">' + avatar + '</div>' +
                    '<div class="task-history__content">' +
                      '<div class="task-history__name">' + data.name + '</div>' +
                      '<div class="task-history__text">' + data.text + '</div>' +
                    '</div>' +
                    '<div class="task-history__time">' + data.date + '</div>' +
                  '</div>';
                
                historyList.insertAdjacentHTML('beforeend', commentHtml);
      
                input.value = '';
    
            } catch (error) {
                console.error(error);
            }
        });
    }
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