/**
 * budget.js — FE-5.4
 * Динамический расчёт % освоения и подсветка перерасхода.
 */

(function () {
  'use strict';

  // ── Утилиты ──────────────────────────────────────────────────────────────

  /** Обновляет progress-bar: ширина + CSS-класс в зависимости от процента. */
  function updateBar(barEl, pct) {
    var clamped = Math.min(pct, 100);
    barEl.style.width = clamped + '%';
    barEl.classList.remove(
      'fin-progress__bar--success',
      'fin-progress__bar--warning',
      'fin-progress__bar--danger'
    );
    if (pct > 110) {
      barEl.classList.add('fin-progress__bar--danger');
    } else if (pct >= 80) {
      barEl.classList.add('fin-progress__bar--success');
    } else {
      barEl.classList.add('fin-progress__bar--warning');
    }
  }

  /** Добавляет/убирает класс перерасхода у строки таблицы. */
  function updateRowHighlight(row, isOverrun) {
    row.classList.remove('fin-row--danger', 'fin-row--success', 'fin-row--secondary');
    if (isOverrun) {
      row.classList.add('fin-row--danger');
    } else {
      row.classList.add('fin-row--success');
    }
  }

  // ── Список бюджета: прогресс-бары при загрузке ───────────────────────────

  function initBudgetTable() {
    var rows = document.querySelectorAll('#budget-table tbody tr[data-plan]');
    rows.forEach(function (row) {
      var plan = parseFloat(row.dataset.plan) || 0;
      var fact = parseFloat(row.dataset.fact) || 0;
      var pct  = plan > 0 ? (fact / plan) * 100 : (fact > 0 ? 100 : 0);

      var bar = row.querySelector('.fin-progress__bar');
      var lbl = row.querySelector('.fin-progress-label');

      if (bar) updateBar(bar, pct);
      if (lbl) lbl.textContent = pct.toFixed(1) + '%';

      updateRowHighlight(row, pct > 110);
    });
  }

  // ── Форма создания/редактирования: живой расчёт % освоения ───────────────

  function initBudgetItemForm() {
    var form = document.getElementById('budget-item-form');
    if (!form) return;

    var planInput = form.querySelector('[name="plan"], #id_plan');
    var factInput = form.querySelector('[name="fact"], #id_fact');
    var liveCalc  = document.getElementById('live-calc');
    var liveBar   = document.getElementById('live-bar');
    var livePct   = document.getElementById('live-pct');

    if (!planInput || !factInput || !liveCalc) return;

    function recalc() {
      var plan = parseFloat(planInput.value) || 0;
      var fact = parseFloat(factInput.value) || 0;

      if (plan === 0 && fact === 0) {
        liveCalc.style.display = 'none';
        return;
      }

      var pct = plan > 0 ? (fact / plan) * 100 : (fact > 0 ? 100 : 0);
      liveCalc.style.display = 'block';

      if (liveBar) updateBar(liveBar, pct);
      if (livePct) livePct.textContent = pct.toFixed(1) + '%';

      // Подсветить поле факта при перерасходе
      factInput.classList.toggle('fin-input--danger', pct > 110);
    }

    planInput.addEventListener('input', recalc);
    factInput.addEventListener('input', recalc);
    recalc();
  }

  // ── Инициализация ─────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    initBudgetTable();
    initBudgetItemForm();
  });

})();
