'use strict';

/* ─── Chart instances ─────────────────────────────────────── */
let forecastChartInstance   = null;
let scenarioChartInstance   = null;

/* ─── Helpers ────────────────────────────────────────────── */
function fmtNum(n) {
  return Number(n).toLocaleString('ru-RU');
}

/* ─── Forecast CF chart ──────────────────────────────────── */
async function loadForecast(days) {
  const btn = document.querySelector(`.fin-chart-btn[data-forecast-days="${days}"]`);
  document.querySelectorAll('.fin-chart-btn[data-forecast-days]').forEach(b => b.classList.remove('is-active'));
  if (btn) btn.classList.add('is-active');

  const spinner = document.getElementById('forecastSpinner');
  const canvas  = document.getElementById('forecastChart');
  if (spinner) { spinner.style.display = 'flex'; }
  if (canvas)  { canvas.style.display  = 'none'; }

  try {
    const resp = await fetch(`/finances/dashboard/forecast/?days=${days}`);
    if (!resp.ok) throw new Error(resp.statusText);
    const data = await resp.json();

    const labels   = data.labels            || [];
    const income   = data.projected_income  || [];
    const expense  = data.projected_expense || [];
    const net      = data.net_cf            || [];
    const gapDates = new Set(data.gap_dates || []);

    const pointColors = labels.map((lbl, i) =>
      (net[i] !== undefined && net[i] < 0) ? '#ff3b30' : '#22a85a'
    );
    const pointRadius = labels.map((lbl, i) =>
      gapDates.has(lbl) ? 7 : 4
    );

    const ctx = canvas.getContext('2d');
    if (forecastChartInstance) forecastChartInstance.destroy();

    forecastChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Прогноз поступлений',
            data: income,
            borderColor: '#2f6bed',
            backgroundColor: 'rgba(47,107,237,0.08)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
          },
          {
            label: 'Прогноз расходов',
            data: expense,
            borderColor: '#ff3b30',
            backgroundColor: 'rgba(255,59,48,0.06)',
            fill: true,
            tension: 0.3,
            pointRadius: 3,
          },
          {
            label: 'Чистый CF',
            data: net,
            borderColor: '#7b7890',
            backgroundColor: 'transparent',
            fill: false,
            tension: 0.3,
            pointBackgroundColor: pointColors,
            pointRadius: pointRadius,
            pointHoverRadius: 8,
          },
        ],
      },
      options: {
        responsive: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          tooltip: {
            callbacks: {
              label: ctx => `${ctx.dataset.label}: ${fmtNum(ctx.parsed.y)} ₸`,
            },
          },
          legend: { position: 'bottom' },
        },
        scales: {
          y: {
            ticks: { callback: v => `${fmtNum(v)} ₸` },
          },
        },
      },
    });

    /* Gap-date alert */
    const alertEl = document.getElementById('gapAlert');
    if (alertEl) {
      const gaps = data.gap_dates || [];
      if (gaps.length > 0) {
        alertEl.textContent = `⚠ Ближайший кассовый разрыв: ${gaps[0]}`;
        alertEl.style.display = 'block';
      } else {
        alertEl.style.display = 'none';
      }
    }

  } catch (e) {
    console.error('loadForecast error', e);
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (canvas)  canvas.style.display  = 'block';
  }
}

/* ─── Scenario chart ─────────────────────────────────────── */
async function loadScenarioChart(pk, name) {
  const card     = document.getElementById('scenarioChartCard');
  const titleEl  = document.getElementById('scenarioChartTitle');
  const canvas   = document.getElementById('scenarioChart');

  if (card) card.style.display = '';
  if (titleEl) titleEl.textContent = name || `Сценарий #${pk}`;

  try {
    const resp = await fetch(`/finances/scenarios/${pk}/json/`);
    if (!resp.ok) throw new Error(resp.statusText);
    const d = await resp.json();

    const labels = Object.keys(d.projected_cashflow || {});
    const values = labels.map(k => Number(d.projected_cashflow[k]));

    if (titleEl) {
      const dscr = d.dscr != null ? Number(d.dscr).toFixed(4) : '—';
      titleEl.textContent = `${d.name} (${d.scenario}) — DSCR: ${dscr} | Риск: ${d.risk_level}`;
    }

    const ctx = canvas.getContext('2d');
    if (scenarioChartInstance) scenarioChartInstance.destroy();

    scenarioChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Прогноз ДДС, ₸',
          data: values,
          backgroundColor: values.map(v => v >= 0 ? 'rgba(34,168,90,0.65)' : 'rgba(255,59,48,0.65)'),
          borderColor:      values.map(v => v >= 0 ? '#22a85a' : '#ff3b30'),
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => `${fmtNum(ctx.parsed.y)} ₸` } },
        },
        scales: {
          y: { ticks: { callback: v => `${fmtNum(v)} ₸` } },
        },
      },
    });

    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (e) {
    console.error('loadScenarioChart error', e);
  }
}

/* ─── Init ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  /* Default forecast load */
  loadForecast(90);

  /* Forecast horizon toggle */
  document.querySelectorAll('.fin-chart-btn[data-forecast-days]').forEach(btn => {
    btn.addEventListener('click', () => loadForecast(Number(btn.dataset.forecastDays)));
  });

  /* Scenario buttons (delegated) */
  document.addEventListener('click', e => {
    const btn = e.target.closest('[data-scenario-pk]');
    if (btn) {
      loadScenarioChart(btn.dataset.scenarioPk, btn.dataset.scenarioName);
    }
  });
});
