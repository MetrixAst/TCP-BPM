'use strict';

/* ─── Палитра для Pie ────────────────────────────────────── */
const PIE_COLORS = [
  '#2f6bed', '#22a85a', '#ff9500', '#ff3b30', '#5856d6',
  '#34aadc', '#4cd964', '#ff2d55', '#8e8e93', '#ffcc00',
];

/* ─── Pie chart — доли арендаторов ─────────────────────── */
function renderTenantPie(data) {
  const canvas = document.getElementById('tenantPieChart');
  if (!canvas) return;

  const labels = data.labels || [];
  const values = data.values || [];

  if (!labels.length) {
    canvas.closest('.fin-chart-card').innerHTML +=
      '<div class="fin-empty"><i class="bi bi-inbox"></i> Нет данных</div>';
    return;
  }

  new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
        borderColor: '#fff',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'right' },
        tooltip: {
          callbacks: {
            label: ctx => {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct   = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${Number(ctx.parsed).toLocaleString('ru-RU')} ₸ (${pct}%)`;
            },
          },
        },
      },
    },
  });
}

/* ─── Line chart — динамика поступлений ─────────────────── */
function renderDynamicsChart(dynamics) {
  const canvas = document.getElementById('dynamicsChart');
  if (!canvas) return;

  const labels = dynamics.labels || [];
  const actual = dynamics.actual || [];

  new Chart(canvas, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Поступления',
        data: actual,
        borderColor: '#2f6bed',
        backgroundColor: 'rgba(47,107,237,0.12)',
        pointBackgroundColor: '#2f6bed',
        pointRadius: 5,
        fill: true,
        tension: 0.35,
      }],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `Поступления: ${Number(ctx.parsed.y).toLocaleString('ru-RU')} ₸`,
          },
        },
      },
      scales: {
        y: {
          ticks: { callback: v => `${Number(v).toLocaleString('ru-RU')} ₸` },
        },
      },
    },
  });
}

/* ─── Init ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const tenantEl   = document.getElementById('tenantData');
  const dynamicsEl = document.getElementById('dynamicsData');

  if (tenantEl) {
    try { renderTenantPie(JSON.parse(tenantEl.textContent)); }
    catch (e) { console.error('tenantData parse error', e); }
  }

  if (dynamicsEl) {
    try { renderDynamicsChart(JSON.parse(dynamicsEl.textContent)); }
    catch (e) { console.error('dynamicsData parse error', e); }
  }
});
