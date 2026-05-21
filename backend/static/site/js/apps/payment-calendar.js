document.addEventListener('DOMContentLoaded', function () {
    const panel = document.getElementById('paymentDayPanel');
    const title = document.getElementById('paymentDayTitle');
    const plan = document.getElementById('paymentDayPlan');
    const fact = document.getElementById('paymentDayFact');
    const balance = document.getElementById('paymentDayBalance');
    const list = document.getElementById('paymentDayList');
  
    const formatMoney = function (value) {
      const number = Number(value || 0);
  
      return new Intl.NumberFormat('ru-RU', {
        maximumFractionDigits: 0
      }).format(number);
    };
  
    const openPanel = function (dayButton) {
      const dayTitle = dayButton.dataset.title || '—';
      const dayPlan = dayButton.dataset.plan || 0;
      const dayFact = dayButton.dataset.fact || 0;
      const dayBalance = dayButton.dataset.balance || 0;
  
      title.textContent = dayTitle;
      plan.textContent = formatMoney(dayPlan);
      fact.textContent = formatMoney(dayFact);
      balance.textContent = formatMoney(dayBalance);
  
      list.innerHTML = `
        <div class="fin-day-item">
          <div>
            <strong>Плановая сумма</strong>
            <span>${formatMoney(dayPlan)}</span>
          </div>
          <i class="is-plan"></i>
        </div>
  
        <div class="fin-day-item">
          <div>
            <strong>Фактическая сумма</strong>
            <span>${formatMoney(dayFact)}</span>
          </div>
          <i class="is-fact"></i>
        </div>
  
        <div class="fin-day-item">
          <div>
            <strong>Разница</strong>
            <span>${formatMoney(dayBalance)}</span>
          </div>
          <i class="is-danger"></i>
        </div>
      `;
  
      panel.classList.add('is-open');
      panel.setAttribute('aria-hidden', 'false');
    };
  
    const closePanel = function () {
      panel.classList.remove('is-open');
      panel.setAttribute('aria-hidden', 'true');
    };
  
    document.querySelectorAll('.fin-calendar-day').forEach(function (dayButton) {
      dayButton.addEventListener('click', function () {
        openPanel(dayButton);
      });
    });
  
    document.querySelectorAll('[data-close-day-panel]').forEach(function (button) {
      button.addEventListener('click', closePanel);
    });
  
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') {
        closePanel();
      }
    });
  });