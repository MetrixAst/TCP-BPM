'use strict';

const RENT_CHART_FONT = '"Inter", system-ui, -apple-system, sans-serif';
const PIE_COLORS = [
  '#2f6bed', '#22a85a', '#ff9500', '#ff3b30', '#5856d6',
  '#34aadc', '#4cd964', '#ff2d55', '#af52de', '#ffcc00',
];

function readJsonScript(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  try {
    return JSON.parse(el.textContent);
  } catch (e) {
    console.error(`JSON parse error (${id})`, e);
    return null;
  }
}

function rentChartOptions(extra = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        labels: {
          font: { family: RENT_CHART_FONT, size: 12 },
          color: '#74728a',
          padding: 14,
          usePointStyle: true,
        },
      },
      tooltip: {
        backgroundColor: '#25233f',
        titleFont: { family: RENT_CHART_FONT, size: 12 },
        bodyFont: { family: RENT_CHART_FONT, size: 13 },
        padding: 12,
        cornerRadius: 10,
      },
    },
    ...extra,
  };
}

function renderTenantPie(data) {
  const canvas = document.getElementById('tenantPieChart');
  const emptyEl = document.getElementById('tenantPieEmpty');
  if (!canvas) return;

  const labels = data?.labels || [];
  const values = data?.values || [];
  const hasData = labels.length && values.some(v => Number(v) > 0);

  if (!hasData) {
    canvas.hidden = true;
    if (emptyEl) emptyEl.hidden = false;
    return;
  }

  if (emptyEl) emptyEl.hidden = true;
  canvas.hidden = false;

  new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
        borderColor: '#fff',
        borderWidth: 3,
        hoverOffset: 8,
      }],
    },
    options: rentChartOptions({
      cutout: '58%',
      plugins: {
        legend: {
          position: 'right',
          labels: {
            font: { family: RENT_CHART_FONT, size: 11 },
            color: '#25233f',
            padding: 10,
            boxWidth: 12,
          },
        },
        tooltip: {
          callbacks: {
            label(ctx) {
              const total = ctx.dataset.data.reduce((a, b) => a + Number(b), 0);
              const pct = total > 0 ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
              return ` ${ctx.label}: ${Number(ctx.parsed).toLocaleString('ru-RU')} ₸ (${pct}%)`;
            },
          },
        },
      },
    }),
  });
}

function renderDynamicsChart(dynamics) {
  const canvas = document.getElementById('dynamicsChart');
  if (!canvas || !dynamics) return;

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
        borderWidth: 2.5,
        backgroundColor(ctx) {
          const { chart } = ctx;
          const { ctx: c, chartArea } = chart;
          if (!chartArea) return 'rgba(47, 107, 237, 0.08)';
          const grad = c.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          grad.addColorStop(0, 'rgba(47, 107, 237, 0.22)');
          grad.addColorStop(1, 'rgba(47, 107, 237, 0.02)');
          return grad;
        },
        pointBackgroundColor: '#2f6bed',
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        fill: true,
        tension: 0.4,
      }],
    },
    options: rentChartOptions({
      plugins: { legend: { display: false } },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: RENT_CHART_FONT, size: 11 }, color: '#9a98aa' },
        },
        y: {
          grid: { color: 'rgba(236, 234, 243, 0.9)' },
          ticks: {
            font: { family: RENT_CHART_FONT, size: 11 },
            color: '#9a98aa',
            callback: v => `${Number(v).toLocaleString('ru-RU')} ₸`,
          },
        },
      },
    }),
  });
}

document.addEventListener('DOMContentLoaded', () => {
  renderTenantPie(readJsonScript('tenant-chart-data'));
  renderDynamicsChart(readJsonScript('dynamics-chart-data'));
});
