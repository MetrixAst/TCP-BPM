/* ===========================================================================
 * FE-5.4 — Бюджетирование (budget.js)
 * Зависимости: jQuery + select2 (как в tasks.js)
 * Покрывает budget_list.html / budget_detail.html / budget_item_form.html /
 * budget_create.html
 *
 * Заметки по бэку (BE-5.11):
 *  - суммы категорий в списке агрегируются во вью (rows[].plan/fact/...);
 *  - детям категорий суммы НЕ считаются → в дереве это просто строки-ссылки;
 *  - удаление строки = обычная POST-форма с redirect (не AJAX);
 *  - exec_pct и overrun приходят из вью, тут только визуализация.
 * =========================================================================== */
(function () {
    'use strict';
  
    document.addEventListener('DOMContentLoaded', function () {
      initSelect2();
      initRowNavigation();
      initTree();
      initChart();
      initTotals();
      initPeriodFields();
    });
  
    /* ----- select2 для всех select модуля -------------------------------------- */
    function initSelect2() {
      if (!window.jQuery || !jQuery.fn.select2) return;
  
      // фильтры списка — авто-submit при выборе
      jQuery('#budgetCatType, #budgetPeriodType').each(function () {
        var $s = jQuery(this);
        $s.select2({ minimumResultsForSearch: Infinity, width: '170px' });
        $s.on('change', function () {
          var form = document.getElementById('budgetFilterForm');
          if (form) form.submit();
        });
      });
  
      // select-поля формы строки/категории
      jQuery('#taskEditForm select').each(function () {
        jQuery(this).select2({ width: '100%' });
      });
    }
  
    /* ----- клик по строке таблицы → переход на деталь -------------------------- */
    function initRowNavigation() {
      document.querySelectorAll('.tasks-table__row[data-href]').forEach(function (row) {
        row.addEventListener('click', function (e) {
          if (e.target.closest('[data-budget-toggle]') || e.target.closest('a')) return;
          window.location.href = row.dataset.href;
        });
      });
    }
  
    /* ----- дерево категорий: раскрытие/сворачивание ---------------------------- */
    function initTree() {
      var rows = Array.prototype.slice.call(
        document.querySelectorAll('#budgetTableBody .tasks-table__row')
      );
      if (!rows.length) return;
  
      // parentId -> [дочерние строки]
      var byParent = {};
      rows.forEach(function (row) {
        var pid = row.dataset.parent || '';
        if (!pid) return;
        (byParent[pid] = byParent[pid] || []).push(row);
      });
  
      // по умолчанию все дочерние свёрнуты
      rows.forEach(function (row) {
        if (row.dataset.parent) row.classList.add('is-collapsed');
      });
  
      function collapseDescendants(id) {
        (byParent[id] || []).forEach(function (child) {
          child.classList.add('is-collapsed');
          var t = child.querySelector('[data-budget-toggle]');
          if (t) t.classList.remove('is-open');
          collapseDescendants(child.dataset.id);
        });
      }
  
      document.querySelectorAll('[data-budget-toggle]').forEach(function (btn) {
        if (btn.classList.contains('budget-tree__toggle--leaf')) return;
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var id = btn.getAttribute('data-budget-toggle');
          var children = byParent[id] || [];
          var willOpen = !btn.classList.contains('is-open');
  
          btn.classList.toggle('is-open', willOpen);
          children.forEach(function (child) {
            child.classList.toggle('is-collapsed', !willOpen);
          });
          if (!willOpen) collapseDescendants(id);
        });
      });
    }
  
    /* ----- столбчатый график: нормализация ширины баров ------------------------ */
    function initChart() {
      var chart = document.getElementById('budgetChart');
      if (!chart) return;
  
      var rows = Array.prototype.slice.call(chart.querySelectorAll('.budget-chart__row'));
  
      var max = 0;
      rows.forEach(function (row) {
        ['plan', 'fact', 'forecast'].forEach(function (k) {
          var v = num(row.dataset[k]);
          if (v > max) max = v;
        });
      });
      if (max <= 0) max = 1;
  
      rows.forEach(function (row) {
        ['plan', 'fact', 'forecast'].forEach(function (k) {
          var v = num(row.dataset[k]);
          var fill = row.querySelector('.budget-chart__bar-fill[data-bar="' + k + '"]');
          if (fill) fill.style.width = Math.min(100, (v / max) * 100) + '%';
        });
      });
    }
  
    /* ----- итоги на детали (сумма по всем строкам) ----------------------------- */
    function initTotals() {
      var totals = document.getElementById('budgetTotals');
      var chart = document.getElementById('budgetChart');
      if (!totals || !chart) return;
  
      var sum = { plan: 0, fact: 0, forecast: 0 };
      chart.querySelectorAll('.budget-chart__row').forEach(function (row) {
        sum.plan     += num(row.dataset.plan);
        sum.fact     += num(row.dataset.fact);
        sum.forecast += num(row.dataset.forecast);
      });
  
      setTotal(totals, 'plan', sum.plan);
      setTotal(totals, 'fact', sum.fact);
      setTotal(totals, 'forecast', sum.forecast);
  
      var variance = sum.fact - sum.plan;
      setTotal(totals, 'variance', variance, true);
  
      var exec = sum.plan > 0 ? Math.round((sum.fact / sum.plan) * 100) : 0;
      var execEl = totals.querySelector('[data-total="exec"]');
      if (execEl) execEl.textContent = exec + '%';
  
      // подсветка карточки отклонения
      var card = document.getElementById('budgetVarianceCard');
      if (card) {
        card.classList.remove('budget-stat--over', 'budget-stat--under');
        if (variance > 0) card.classList.add('budget-stat--over');
        else if (variance < 0) card.classList.add('budget-stat--under');
      }
    }
  
    function setTotal(scope, key, value, signed) {
      var el = scope.querySelector('[data-total="' + key + '"]');
      if (!el) return;
      var prefix = (signed && value > 0) ? '+' : '';
      el.textContent = prefix + formatMoney(value);
    }
  
    /* ----- форма строки: показывать месяц/квартал по period_type --------------- */
    function initPeriodFields() {
      var form = document.getElementById('taskEditForm');
      if (!form) return;
      var sel = form.querySelector('[name="period_type"]');
      if (!sel) return;
  
      var monthField   = form.querySelector('[data-period-field="monthly"]');
      var quarterField = form.querySelector('[data-period-field="quarterly"]');
      if (!monthField && !quarterField) return;
  
      function apply() {
        var v = sel.value;
        if (monthField)   monthField.style.display   = (v === 'monthly')   ? '' : 'none';
        if (quarterField) quarterField.style.display = (v === 'quarterly') ? '' : 'none';
      }
      apply();
  
      // select2 шлёт change через jQuery
      if (window.jQuery) jQuery(sel).on('change', apply);
      else sel.addEventListener('change', apply);
    }
  
    /* ----- helpers ------------------------------------------------------------- */
    function num(v) {
      var n = parseFloat(String(v == null ? '' : v).replace(',', '.'));
      return isNaN(n) ? 0 : n;
    }
  
    function formatMoney(v) {
      // округляем и разбиваем разряды пробелом, как в RU-формате
      var rounded = Math.round(v);
      return rounded.toLocaleString('ru-RU');
    }
  })();