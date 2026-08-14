(function () {
  'use strict';

  function t(text) {
    return (window.BPM && window.BPM.t) ? window.BPM.t(text, text) : text;
  }
  
    function getCsrfToken() {
      var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
      return match ? decodeURIComponent(match[1]) : '';
    }
  
    function postAjax(url, body) {
      return fetch(url, {
        method: 'POST',
        headers: { 'X-CSRFToken': getCsrfToken(), 'X-Requested-With': 'XMLHttpRequest' },
        credentials: 'same-origin',
        body: body || null,
      });
    }
  
    function escapeHtml(text) {
      var div = document.createElement('div');
      div.textContent = text == null ? '' : text;
      return div.innerHTML;
    }
  
    function notifyError(text) {
      if (window.bpmModal) window.bpmModal.alert(text, { variant: 'danger', title: t('Ошибка') });
      else alert(text);
    }
  
    // action: 'approve' | 'reject'. Возвращает Promise<string|null> (комментарий или null при отмене).
    function openApprovalDialog(action, ticketTitle) {
      return new Promise(function (resolve) {
        var isReject = action === 'reject';
        var overlay = document.createElement('div');
        overlay.className = 'hr-status-dialog';
        overlay.innerHTML =
          '<div class="hr-status-dialog__box" role="dialog" aria-modal="true">' +
            '<h3 class="hr-status-dialog__title">' + (isReject ? t('Отклонить заявку') : t('Согласовать заявку')) + '</h3>' +
            '<p class="hr-status-dialog__person-name">«' + escapeHtml(ticketTitle) + '»</p>' +
            (isReject
              ? '<label class="hr-status-dialog__label">' + t('Комментарий (обязателен, минимум 5 символов)') + '</label>' +
                '<textarea class="hr-status-dialog__textarea" data-comment rows="3" placeholder="' + t('Например: требуется уточнить детали') + '"></textarea>' +
                '<p class="hr-status-dialog__error" data-error style="display:none"></p>'
              : '<label class="hr-status-dialog__label">' + t('Комментарий (необязательно)') + '</label>' +
                '<textarea class="hr-status-dialog__textarea" data-comment rows="2"></textarea>'
            ) +
            '<div class="hr-status-dialog__actions">' +
              '<button type="button" class="hr-btn hr-btn--light" data-cancel>' + t('Отмена') + '</button>' +
              '<button type="button" class="hr-btn ' + (isReject ? 'hr-btn--danger' : 'hr-btn--primary') + '" data-confirm>' +
                (isReject ? t('Отклонить') : t('Согласовать')) +
              '</button>' +
            '</div>' +
          '</div>';
          (document.getElementById('bpmMain') || document.body).appendChild(overlay);

        if (window.BPM && window.BPM.applyTranslations) {
          window.BPM.applyTranslations();
        }
  
        var textarea = overlay.querySelector('[data-comment]');
        var errorEl = overlay.querySelector('[data-error]');
        var confirmBtn = overlay.querySelector('[data-confirm]');
        var cancelBtn = overlay.querySelector('[data-cancel]');
  
        function close(result) {
          (document.getElementById('bpmMain') || document.body).removeChild(overlay)
          document.removeEventListener('keydown', onKey);
          resolve(result);
        }
        function onKey(e) { if (e.key === 'Escape') close(null); }
  
        confirmBtn.addEventListener('click', function () {
          var comment = textarea.value.trim();
          if (isReject && comment.length < 5) {
            errorEl.textContent = t('Комментарий должен содержать не менее 5 символов.');
            errorEl.style.display = 'block';
            textarea.focus();
            return;
          }
          close(comment);
        });
        cancelBtn.addEventListener('click', function () { close(null); });
        overlay.addEventListener('click', function (e) { if (e.target === overlay) close(null); });
        document.addEventListener('keydown', onKey);
  
        requestAnimationFrame(function () { overlay.classList.add('is-open'); textarea.focus(); });
      });
    }
    window.openApprovalDialog = openApprovalDialog;
    
    document.addEventListener('DOMContentLoaded', function () {
      document.querySelectorAll('[data-approval-action]').forEach(function (btn) {
        btn.addEventListener('click', async function () {
          var action = btn.getAttribute('data-approval-action');
          var url = btn.getAttribute('data-url');
          var title = btn.getAttribute('data-ticket-title') || '';
  
          var comment = await openApprovalDialog(action, title);
          if (comment === null) return;
  
          btn.disabled = true;
          try {
            var fd = new FormData();
            fd.append('action', action);
            fd.append('comment', comment);
            var res = await postAjax(url, fd);
            var data = {};
            try { data = await res.json(); } catch (e) { if (res.ok) { window.location.reload(); return; } }
            if (res.ok && data.ok !== false) {
              window.location.reload();
            } else {
              notifyError(data.message || t('Не удалось выполнить действие.'));
              btn.disabled = false;
            }
          } catch (e) {
            console.error(e);
            notifyError(t('Ошибка сети.'));
            btn.disabled = false;
          }
        });
      });
    });
  })();