'use strict';

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
            label: 'Поступления',
            data: income,
            backgroundColor: 'rgba(47,107,237,0.7)',
            borderColor: '#2f6bed',
            borderWidth: 1,
            order: 2,
          },
          {
            label: 'Выбытия',
            data: expense,
            backgroundColor: 'rgba(255,59,48,0.55)',
            borderColor: '#ff3b30',
            borderWidth: 1,
            order: 2,
          },
          {
            label: 'Чистый CF',
            data: net,
            type: 'line',
            borderColor: '#7b7890',
            backgroundColor: netColors,
            pointBackgroundColor: netColors,
            pointRadius: 4,
            fill: false,
            tension: 0.3,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${fmt(ctx.parsed.y)} ₸`,
            },
          },
          legend: { position: 'bottom' },
        },
        scales: {
          y: {
            ticks: { callback: v => `${fmt(v)} ₸` },
          },
        },
      },
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
            label: 'Чистый CF (нед.)',
            data: netCf,
            borderColor: '#2f6bed',
            backgroundColor: 'rgba(47,107,237,0.1)',
            pointBackgroundColor: netCf.map(v => v < 0 ? '#ff3b30' : '#22a85a'),
            pointRadius: 5,
            fill: true,
            tension: 0.35,
          },
        ],
      },
      options: {
        responsive: true,
        plugins: {
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${fmt(ctx.parsed.y)} ₸`,
            },
          },
          legend: { position: 'bottom' },
        },
        scales: {
          y: {
            ticks: { callback: v => `${fmt(v)} ₸` },
          },
        },
      },
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

async function openDrillPanel(type, period) {
  const panel = document.getElementById('drillPanel');
  const titleEl = document.getElementById('drillTitle');
  const bodyEl  = document.getElementById('drillBody');

  titleEl.textContent = DRILL_TITLES[type] || type;
  bodyEl.innerHTML = '<div class="fin-empty"><span class="fin-spinner"></span> Загрузка...</div>';
  panel.classList.add('is-open');
  panel.setAttribute('aria-hidden', 'false');

  try {
    const resp = await fetch(`/finances/dashboard/drilldown/?type=${type}&period=${period}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();
    const rows = data.data || [];

    if (!rows.length) {
      bodyEl.innerHTML = '<div class="fin-empty"><i class="bi bi-inbox"></i> Нет данных</div>';
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
    bodyEl.innerHTML = '<div class="fin-empty fin-empty--danger"><i class="bi bi-exclamation-circle"></i> Ошибка загрузки</div>';
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
    set('kpi-net-cf',        data.net_cf);
    set('kpi-overdue-amount',data.overdue_amount);

    const trendEl = document.getElementById('kpi-revenue-trend');
    if (trendEl && data.revenue_mtd_change !== undefined) {
      const up = data.revenue_mtd_change >= 0;
      trendEl.className = `fin-kpi-trend ${up ? 'is-up' : 'is-down'}`;
      trendEl.innerHTML = `<i class="bi bi-arrow-${up ? 'up' : 'down'}-short"></i> ${Number(data.revenue_mtd_change).toFixed(1)}%`;
    }

    const countEl = document.getElementById('kpi-overdue-count');
    if (countEl && data.overdue_count !== undefined) {
      countEl.textContent = `${data.overdue_count} позиций`;
    }
  } catch (e) {
    console.warn('KPI refresh failed', e);
  }
}

/* ─── 5. Multi-currency balances ─────────────────────────── */
async function loadBalances(currency) {
  const hintEl = document.getElementById('rateHint');
  if (!currency) {
    if (hintEl) hintEl.textContent = '';
    hintEl && hintEl.classList.remove('is-stale');
    return;
  }

  try {
    const resp = await fetch(`/finances/dashboard/balances/?currency=${currency}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const d = await resp.json();

    const cashEl    = document.getElementById('kpi-cash-balance');
    const cashFxEl  = document.getElementById('kpi-cash-balance-fx');
    const revEl     = document.getElementById('kpi-revenue-mtd');
    const revFxEl   = document.getElementById('kpi-revenue-mtd-fx');

    if (cashEl && d.cash_balance_kzt !== undefined)
      cashEl.textContent = `${fmt(d.cash_balance_kzt)} ₸`;
    if (cashFxEl && d.cash_balance_foreign !== undefined)
      cashFxEl.textContent = `≈ ${fmt(d.cash_balance_foreign)} ${d.currency}`;

    if (revEl && d.revenue_mtd_kzt !== undefined)
      revEl.textContent = `${fmt(d.revenue_mtd_kzt)} ₸`;
    if (revFxEl && d.revenue_mtd_foreign !== undefined)
      revFxEl.textContent = `≈ ${fmt(d.revenue_mtd_foreign)} ${d.currency}`;

    if (hintEl) {
      hintEl.textContent = `Курс: ${d.rate} ₸ / ${d.currency} на ${d.rate_date}`;
      if (!d.rate_is_fresh) {
        hintEl.classList.add('is-stale');
        hintEl.textContent += ' ⚠ устарел';
      } else {
        hintEl.classList.remove('is-stale');
      }
    }

    /* Stale banner */
    const banner  = document.getElementById('rateStaleBanner');
    const bannerT = document.getElementById('rateStaleBannerText');
    if (banner && bannerT) {
      if (!d.rate_is_fresh) {
        bannerT.textContent = `Курс устарел. Последний актуальный: ${d.rate} ₸ / ${d.currency} на ${d.rate_date}`;
        banner.style.display = 'flex';
      } else {
        banner.style.display = 'none';
      }
    }
  } catch (e) {
    console.error('loadBalances error', e);
  }
}

/* ─── Init ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  /* charts */
  loadCashflowChart(30);
  loadWeeklyChart(12);

  /* cashflow toggle */
  document.querySelectorAll('.fin-chart-btn[data-days]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.fin-chart-btn[data-days]').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      loadCashflowChart(Number(btn.dataset.days));
    });
  });

  /* KPI drill-down on card click */
  document.querySelectorAll('.fin-kpi-card[data-drill-type]').forEach(card => {
    card.addEventListener('click', () => {
      openDrillPanel(card.dataset.drillType, card.dataset.drillPeriod || '');
    });
  });

  /* close drill panel */
  document.querySelectorAll('[data-close-drill]').forEach(el => {
    el.addEventListener('click', closeDrillPanel);
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeDrillPanel();
  });

  /* currency select */
  const currSelect = document.getElementById('currencySelect');
  if (currSelect) {
    currSelect.addEventListener('change', () => loadBalances(currSelect.value));
  }

  /* KPI auto-refresh every 5 min */
  setInterval(refreshKPIs, 5 * 60 * 1000);
});
