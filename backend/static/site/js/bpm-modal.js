(function () {
  'use strict';

  function buildModal() {
    let overlay = document.getElementById('bpmModal');
    if (overlay) return overlay;

    overlay = document.createElement('div');
    overlay.className = 'bpm-modal';
    overlay.id = 'bpmModal';
    overlay.innerHTML =
      '<div class="bpm-modal__dialog" role="dialog" aria-modal="true">' +
        '<div class="bpm-modal__icon" data-modal-icon></div>' +
        '<h3 class="bpm-modal__title" data-modal-title></h3>' +
        '<p class="bpm-modal__text" data-modal-text></p>' +
        '<div class="bpm-modal__actions">' +
          '<button type="button" class="bpm-modal__btn bpm-modal__btn--ghost" data-modal-cancel></button>' +
          '<button type="button" class="bpm-modal__btn bpm-modal__btn--primary" data-modal-confirm></button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(overlay);
    return overlay;
  }

  const ICONS = {
    info: '<i class="bi bi-info-circle"></i>',
    danger: '<i class="bi bi-exclamation-triangle"></i>',
    success: '<i class="bi bi-check-circle"></i>',
    warning: '<i class="bi bi-exclamation-circle"></i>'
  };

  function open(options) {
    const opts = options || {};
    const overlay = buildModal();
    const dialog = overlay.querySelector('.bpm-modal__dialog');
    const iconEl = overlay.querySelector('[data-modal-icon]');
    const titleEl = overlay.querySelector('[data-modal-title]');
    const textEl = overlay.querySelector('[data-modal-text]');
    const cancelEl = overlay.querySelector('[data-modal-cancel]');
    const confirmEl = overlay.querySelector('[data-modal-confirm]');

    const variant = opts.variant || 'info';

    iconEl.className = 'bpm-modal__icon bpm-modal__icon--' + variant;
    iconEl.innerHTML = ICONS[variant] || ICONS.info;

    titleEl.textContent = opts.title || '';
    titleEl.style.display = opts.title ? '' : 'none';
    textEl.textContent = opts.text || '';

    confirmEl.textContent = opts.confirmText || 'OK';
    confirmEl.className = 'bpm-modal__btn ' +
      (variant === 'danger' ? 'bpm-modal__btn--danger' : 'bpm-modal__btn--primary');

    const isConfirm = !!opts.confirm;
    cancelEl.textContent = opts.cancelText || 'Отмена';
    cancelEl.style.display = isConfirm ? '' : 'none';

    return new Promise(function (resolve) {
      function close(result) {
        overlay.classList.remove('is-open');
        document.removeEventListener('keydown', onKey);
        confirmEl.onclick = null;
        cancelEl.onclick = null;
        overlay.onclick = null;
        setTimeout(function () { resolve(result); }, 60);
      }

      function onKey(e) {
        if (e.key === 'Escape') close(false);
        else if (e.key === 'Enter') close(true);
      }

      confirmEl.onclick = function () { close(true); };
      cancelEl.onclick = function () { close(false); };
      overlay.onclick = function (e) {
        if (e.target === overlay && isConfirm) close(false);
        else if (e.target === overlay && !isConfirm) close(false);
      };

      document.addEventListener('keydown', onKey);

      requestAnimationFrame(function () { overlay.classList.add('is-open'); });
      setTimeout(function () { confirmEl.focus(); }, 40);
      void dialog;
    });
  }

  window.bpmModal = {
    alert: function (text, options) {
      const o = Object.assign({ variant: 'info', confirmText: 'OK' }, options || {});
      o.text = text;
      o.confirm = false;
      return open(o);
    },
    confirm: function (text, options) {
      const o = Object.assign({ variant: 'danger', confirmText: 'Подтвердить' }, options || {});
      o.text = text;
      o.confirm = true;
      return open(o);
    }
  };
})();
