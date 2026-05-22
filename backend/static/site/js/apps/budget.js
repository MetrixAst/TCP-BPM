(function () {
    'use strict';
  
    document.addEventListener('DOMContentLoaded', function () {
      initAllSelect2();
      initRowNavigation();
      initTree();
      initChart();
      initTotals();
      initPeriodFields();
    });
  
    function initAllSelect2() {
      if (!window.jQuery || !jQuery.fn.select2) return;
  
      // Все фильтрующие select на любой странице модуля
      // (budget_list, opiu, cashflow, credit_model)
      jQuery(
        '#budgetCatType, #budgetPeriodType,' +
        '#opiumPeriodType,' +
        '#cfDirection, #cfFlowType,' +
        '#cmScenario, #cmRisk'
      ).each(function () {
        var $s = jQuery(this);
        if ($s.data('select2')) return; // уже инициализирован
        $s.select2({ minimumResultsForSearch: Infinity, width: '100%' });
        $s.on('change', function () {
          // auto-submit ближайшей формы
          var form = $s.closest('form')[0];
          if (form) form.submit();
        });
      });
  
      // select внутри формы строки/категории — без auto-submit
      jQuery('#taskEditForm select').each(function () {
        var $s = jQuery(this);
        if ($s.data('select2')) return;
        $s.select2({ width: '100%' });
      });
    }
  
    /* -------------------------------------------------------------------------
     * Клик по строке таблицы → переход на деталь
     * ------------------------------------------------------------------------- */
    function initRowNavigation() {
      document.querySelectorAll('.tasks-table__row[data-href]').forEach(function (row) {
        row.addEventListener('click', function (e) {
          if (e.target.closest('[data-budget-toggle]') || e.target.closest('a, button, form')) return;
          window.location.href = row.dataset.href;
        });
      });
    }
  
    /* -------------------------------------------------------------------------
     * Дерево категорий (budget_list)
     * ------------------------------------------------------------------------- */
    function initTree() {
      var rows = Array.prototype.slice.call(
        document.querySelectorAll('#budgetTableBody .tasks-table__row')
      );
      if (!rows.length) return;
  
      var byParent = {};
      rows.forEach(function (row) {
        var pid = row.dataset.parent || '';
        if (!pid) return;
        (byParent[pid] = byParent[pid] || []).push(row);
      });
  
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
  
    /* -------------------------------------------------------------------------
     * График отклонений (budget_detail) — нормализация ширины баров
     * ------------------------------------------------------------------------- */
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
  
    /* -------------------------------------------------------------------------
     * Итоги на детали (budget_detail) — суммирует строки графика
     * ------------------------------------------------------------------------- */
    function initTotals() {
      var totals = document.getElementById('budgetTotals');
      var chart  = document.getElementById('budgetChart');
      if (!totals || !chart) return;
  
      var sum = { plan: 0, fact: 0, forecast: 0 };
      chart.querySelectorAll('.budget-chart__row').forEach(function (row) {
        sum.plan     += num(row.dataset.plan);
        sum.fact     += num(row.dataset.fact);
        sum.forecast += num(row.dataset.forecast);
      });
  
      setTotal(totals, 'plan',     sum.plan);
      setTotal(totals, 'fact',     sum.fact);
      setTotal(totals, 'forecast', sum.forecast);
  
      var variance = sum.fact - sum.plan;
      setTotal(totals, 'variance', variance, true);
  
      var exec = sum.plan > 0 ? Math.round((sum.fact / sum.plan) * 100) : 0;
      var execEl = totals.querySelector('[data-total="exec"]');
      if (execEl) execEl.textContent = exec + '%';
  
      var card = document.getElementById('budgetVarianceCard');
      if (card) {
        card.classList.remove('budget-stat--over', 'budget-stat--under');
        if (variance > 0) card.classList.add('budget-stat--over');
        else if (variance < 0) card.classList.add('budget-stat--under');
      }
    }
  
    /* -------------------------------------------------------------------------
     * Форма строки: показывать месяц / квартал по выбранному period_type
     * ------------------------------------------------------------------------- */
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
      if (window.jQuery) jQuery(sel).on('change', apply);
      else sel.addEventListener('change', apply);
    }
  
    /* -------------------------------------------------------------------------
     * Helpers
     * ------------------------------------------------------------------------- */
    function num(v) {
      var n = parseFloat(String(v == null ? '' : v).replace(',', '.'));
      return isNaN(n) ? 0 : n;
    }
  
    function setTotal(scope, key, value, signed) {
      var el = scope.querySelector('[data-total="' + key + '"]');
      if (!el) return;
      var prefix = (signed && value > 0) ? '+' : '';
      el.textContent = prefix + Math.round(value).toLocaleString('ru-RU');
    }
  
  })();