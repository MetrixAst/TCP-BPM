'use strict';

/* ─── Translation helper ──────────────────────────────────── */
function t(key) {
  return (window.BPM && window.BPM.t) ? window.BPM.t(key, key) : key;
}

/* ─── Chart instances ─────────────────────────────────────── */
let cashflowChartInstance = null;
let weeklyChartInstance   = null;

/* ─── Helpers ────────────────────────────────────────────── */
function fmt(n) {
  return Number(n).toLocaleString('ru-RU');
}

function getCsrfToken() {
  const el = document.querySelector('[name=csrfmiddlewaretoken]');
  if (el) return el.value;
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : '';
}

function showSpinner(spinnerId, canvasId) {
  const sp = document.getElementById(spinnerId);
  const cv = document.getElementById(canvasId);
  if (sp) sp.style.display = 'flex';
  if (cv) cv.style.display = 'none';
}

function hideSpinner(spinnerId, canvasId) {
  const sp = document.getElementById(spinnerId);
  const cv = document.getElementById(canvasId);
  if (sp) sp.style.display = 'none';
  if (cv) cv.style.display = 'block';
}

/* ─── 1. Cashflow daily chart ─────────────────────────────── */
async function loadCashflowChart(days) {
  showSpinner('cashflowSpinner', 'cashflowChart');
  try {
    const resp = await fetch(`/finances/dashboard/cashflow-daily/?days=${days}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();

    const labels   = data.labels   || [];
    const income   = data.income   || [];
    const expense  = data.expense  || [];
    const net      = data.net      || [];

    const netColors = net.map(v => v < 0 ? 'rgba(255,59,48,0.85)' : 'rgba(34,168,90,0.85)');

    const ctx = document.getElementById('cashflowChart').getContext('2d');
    if (cashflowChartInstance) cashflowChartInstance.destroy();

    cashflowChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: t('Поступления'),
            data: income,
            backgroundColor: 'rgba(47, 107, 237, 0.75)',
            borderColor: 'rgba(47, 107, 237, 0)',
            borderWidth: 0,
            borderRadius: 6,
            borderSkipped: false,
            order: 2,
          },
          {
            label: t('Выбытия'),
            data: expense,
            backgroundColor: 'rgba(255, 149, 0, 0.65)',
            borderColor: 'rgba(255, 149, 0, 0)',
            borderWidth: 0,
            borderRadius: 6,
            borderSkipped: false,
            order: 2,
          },
          {
            label: t('Чистый CF'),
            data: net,
            type: 'line',
            borderColor: '#25233f',
            backgroundColor: 'rgba(37, 35, 63, 0.06)',
            pointBackgroundColor: netColors,
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 5,
            pointHoverRadius: 7,
            fill: true,
            tension: 0.35,
            order: 1,
          },
        ],
      },
      options: chartBaseOptions({
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: {
            callbacks: {
              label: c => `${c.dataset.label}: ${fmt(c.parsed.y)} ₸`,
            },
          },
        },
      }),
    });
  } catch (e) {
    console.error('cashflow chart error', e);
  } finally {
    hideSpinner('cashflowSpinner', 'cashflowChart');
  }
}

/* ─── 2. Weekly CF chart ──────────────────────────────────── */
async function loadWeeklyChart(weeks) {
  showSpinner('weeklySpinner', 'weeklyChart');
  try {
    const resp = await fetch(`/finances/dashboard/cashflow-weekly/?weeks=${weeks}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();

    const labels  = data.labels  || [];
    const netCf   = data.net_cf  || data.net || [];

    const ctx = document.getElementById('weeklyChart').getContext('2d');
    if (weeklyChartInstance) weeklyChartInstance.destroy();

    weeklyChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: t('Чистый CF (нед.)'),
            data: netCf,
            borderColor: '#2f6bed',
            borderWidth: 2.5,
            backgroundColor: (context) => {
              const { chart } = context;
              const { ctx: c, chartArea } = chart;
              if (!chartArea) return 'rgba(47, 107, 237, 0.08)';
              const grad = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
              grad.addColorStop(0, 'rgba(47, 107, 237, 0.22)');
              grad.addColorStop(1, 'rgba(47, 107, 237, 0.02)');
              return grad;
            },
            pointBackgroundColor: netCf.map(v => (v < 0 ? '#ff3b30' : '#22a85a')),
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointRadius: 6,
            pointHoverRadius: 8,
            fill: true,
            tension: 0.4,
          },
        ],
      },
      options: chartBaseOptions({
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: c => `${c.dataset.label}: ${fmt(c.parsed.y)} ₸`,
            },
          },
        },
      }),
    });
  } catch (e) {
    console.error('weekly chart error', e);
  } finally {
    hideSpinner('weeklySpinner', 'weeklyChart');
  }
}

/* ─── 3. Drill-down panel ─────────────────────────────────── */
const DRILL_TITLES = {
  revenue:      'Поступления',
  revenue_ytd:  'Выручка (год)',
  expenses:     'Расходы',
  overdue:      'Просрочка',
  net_cf:       'Чистый CF',
  cash:         'Остаток ДС',
  budget:       'Бюджет',
};

const CHART_FONT = '"Inter", system-ui, -apple-system, sans-serif';
const CHART_GRID = 'rgba(236, 234, 243, 0.9)';
const CHART_TICK = '#9a98aa';

function chartBaseOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          font: { family: CHART_FONT, size: 12, weight: '500' },
          color: '#74728a',
          padding: 16,
          usePointStyle: true,
          pointStyleWidth: 8,
        },
      },
      tooltip: {
        backgroundColor: '#25233f',
        titleFont: { family: CHART_FONT, size: 12 },
        bodyFont: { family: CHART_FONT, size: 13 },
        padding: 12,
        cornerRadius: 10,
        displayColors: true,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: { font: { family: CHART_FONT, size: 11 }, color: CHART_TICK, maxRotation: 0 },
      },
      y: {
        grid: { color: CHART_GRID, drawBorder: false },
        ticks: {
          font: { family: CHART_FONT, size: 11 },
          color: CHART_TICK,
          callback: v => `${fmt(v)} ₸`,
        },
      },
    },
    ...extra,
  };
}

async function openDrillPanel(type, period) {
  const panel = document.getElementById('drillPanel');
  const titleEl = document.getElementById('drillTitle');
  const bodyEl  = document.getElementById('drillBody');

  titleEl.textContent = t(DRILL_TITLES[type] || type);
  bodyEl.innerHTML = `<div class="fin-empty"><span class="fin-spinner"></span> ${t('Загрузка...')}</div>`;
  panel.classList.add('is-open');
  panel.setAttribute('aria-hidden', 'false');

  try {
    const resp = await fetch(`/finances/dashboard/drilldown/?type=${type}&period=${period}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();
    const rows = data.data || [];

    if (!rows.length) {
      bodyEl.innerHTML = `<div class="fin-empty"><i class="bi bi-inbox"></i> ${t('Нет данных')}</div>`;
      return;
    }

    const keys = Object.keys(rows[0]);
    let html = '<div class="fin-table-wrap"><table class="fin-table"><thead><tr>';
    keys.forEach(k => { html += `<th>${k}</th>`; });
    html += '</tr></thead><tbody>';

    rows.forEach(row => {
      const isOverdue = row.is_overdue || row.status === 'overdue';
      html += `<tr class="fin-row${isOverdue ? ' fin-row--danger' : ''}">`;
      keys.forEach(k => {
        const v = row[k];
        let cell = (v !== null && v !== undefined) ? v : '—';
        if (k === 'onec_id' && v) {
          cell = `<a href="/finances/dashboard/drilldown/record/${v}/" class="fin-link" target="_blank">${v}</a>`;
        }
        html += `<td>${cell}</td>`;
      });
      html += '</tr>';
    });

    html += '</tbody></table></div>';
    bodyEl.innerHTML = html;
  } catch (e) {
    bodyEl.innerHTML = `<div class="fin-empty fin-empty--danger"><i class="bi bi-exclamation-circle"></i> ${t('Ошибка загрузки')}</div>`;
    console.error('drill-down error', e);
  }
}

function closeDrillPanel() {
  const panel = document.getElementById('drillPanel');
  panel.classList.remove('is-open');
  panel.setAttribute('aria-hidden', 'true');
}

/* ─── 4. KPI refresh (every 5 min) ────────────────────────── */
async function refreshKPIs() {
  try {
    const resp = await fetch('/finances/dashboard/kpi/');
    if (!resp.ok) return;
    const data = await resp.json();

    const set = (id, val) => {
      const el = document.getElementById(id);
      if (el && val !== undefined) el.textContent = `${fmt(val)} ₸`;
    };

    set('kpi-cash-balance',  data.cash_balance);
    set('kpi-revenue-mtd',   data.revenue_mtd);
    set('kpi-revenue-ytd',   data.revenue_ytd);
    set('kpi-expenses-mtd',  data.expenses_mtd);
    const netEl = document.getElementById('kpi-net-cf');
    if (netEl && data.net_cf !== undefined) {
      netEl.textContent = `${fmt(data.net_cf)} ₸`;
      netEl.classList.toggle('fin-kpi-value--success', data.net_cf >= 0);
      netEl.classList.toggle('fin-kpi-value--danger', data.net_cf < 0);
    }
    set('kpi-overdue-amount', data.overdue_amount);

    const trendEl = document.getElementById('kpi-revenue-trend');
    if (trendEl && data.revenue_mtd_change !== undefined) {
      const up = data.revenue_mtd_change >= 0;
      trendEl.className = `fin-kpi-trend ${up ? 'is-up' : 'is-down'}`;
      trendEl.innerHTML = `<i class="bi bi-arrow-${up ? 'up' : 'down'}-short"></i> ${Number(data.revenue_mtd_change).toFixed(1)}%`;
    }

    const countEl = document.getElementById('kpi-overdue-count');
    if (countEl && data.overdue_count !== undefined) {
      countEl.textContent = `${data.overdue_count} ${t('позиций')}`;
    }
  } catch (e) {
    console.warn('KPI refresh failed', e);
  }
}

/* ─── Init ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadCashflowChart(30);
  loadWeeklyChart(12);

  document.querySelectorAll('.fin-chart-btn[data-days]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.fin-chart-btn[data-days]').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      loadCashflowChart(Number(btn.dataset.days));
    });
  });

  document.querySelectorAll('.fin-kpi-card[data-drill-type]').forEach(card => {
    const open = () => openDrillPanel(card.dataset.drillType, card.dataset.drillPeriod || '');
    card.addEventListener('click', open);
    card.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        open();
      }
    });
  });

  document.querySelectorAll('[data-close-drill]').forEach(el => {
    el.addEventListener('click', closeDrillPanel);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeDrillPanel();
  });

  setInterval(refreshKPIs, 5 * 60 * 1000);
});


(function () {
  'use strict';

  function getCsrf() {
    const el = document.querySelector('[name=csrfmiddlewaretoken]');
    if (el) return el.value;
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }

  document.querySelectorAll('[data-checkin-action]').forEach(function (btn) {
    btn.addEventListener('click', async function () {
      const action = btn.dataset.checkinAction;
      const url    = btn.dataset.checkinUrl;

      btn.disabled = true;
      const origHtml = btn.innerHTML;
      btn.innerHTML = '<i class="bi bi-arrow-repeat" style="animation:task-spin .7s linear infinite;display:inline-block"></i> ' + t('Загрузка...');

      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrf(),
            'X-Requested-With': 'XMLHttpRequest',
          },
          credentials: 'same-origin',
          body: JSON.stringify({ action: action }),
        });

        const data = await res.json();

        if (res.ok && data.ok !== false) {
          window.location.reload();
        } else {
          alert(data.message || t('Ошибка'));
          btn.disabled = false;
          btn.innerHTML = origHtml;
        }
      } catch (err) {
        console.error(err);
        alert(t('Ошибка'));
        btn.disabled = false;
        btn.innerHTML = origHtml;
      }
    });
  });
})();