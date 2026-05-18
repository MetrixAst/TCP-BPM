(function () {
    function parseNumber(value) {
      if (!value) return 0;
      return Number(String(value).replace(',', '.')) || 0;
    }
  
    function formatMoney(value) {
      return (Number(value) || 0).toFixed(2);
    }
  
    function renderJsonPreview(value) {
      if (!value || !Array.isArray(value) || !value.length) {
        return '<div class="onec-preview-empty">Нет данных</div>';
      }
  
      return value.map(function (item) {
        if (typeof item !== 'object') {
          return `<div class="onec-preview-line">${item}</div>`;
        }
  
        return `
          <div class="onec-preview-line">
            ${Object.entries(item).map(function ([key, val]) {
              return `<span><b>${key}:</b> ${val || '—'}</span>`;
            }).join('')}
          </div>
        `;
      }).join('');
    }
  
    function loadCounterpartyPreview(id) {
      const preview = document.getElementById('counterpartyPreview');
      const banks = document.getElementById('bankAccountsPreview');
      const contracts = document.getElementById('contractsPreview');
      const select = document.getElementById('cp_select');
  
      if (!preview || !banks || !contracts || !select || !id) return;
  
      const detailBase = select.dataset.detailBase || '/onec/api/counterparties/';
  
      fetch(`${detailBase}${id}/`)
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          banks.innerHTML = renderJsonPreview(data.bank_accounts);
          contracts.innerHTML = renderJsonPreview(data.contracts);
          preview.hidden = false;
        })
        .catch(function () {
          banks.innerHTML = '<div class="onec-preview-empty">Не удалось загрузить реквизиты</div>';
          contracts.innerHTML = '<div class="onec-preview-empty">Не удалось загрузить договоры</div>';
          preview.hidden = false;
        });
    }
  
    function initCounterpartySelect() {
        const tryInit = function () {
          if (!window.jQuery || !window.jQuery.fn || !window.jQuery.fn.select2) {
            setTimeout(tryInit, 100);
            return;
          }
      
          const select = $('#cp_select');
          if (!select.length || select.hasClass('select2-hidden-accessible')) return;
      
          select.select2({
            ajax: {
              url: select.data('url'),
              dataType: 'json',
              delay: 250,
              data: function (params) {
                return { q: params.term || '' };
              },
              processResults: function (data) {
                return { results: data.results || [] };
              },
              cache: false
            },
            templateSelection: function (item) {
                if (!item.id) return item.text;
              
                return item.text
                  .replace(/\s*\(БИН:\s*[^)]*\)/i, '')
                  .replace(/\s*—\s*БИН\s*.*/i, '');
            },
            placeholder: 'Поиск контрагента',
            minimumInputLength: 0,
            width: '100%',
            dropdownParent: $('#onecInvoiceForm'),
            language: {
              searching: function () { return 'Поиск...'; },
              noResults: function () { return 'Контрагенты не найдены'; }
            }
          });
      
          select.on('select2:open', function () {
            const search = document.querySelector('.select2-container--open .select2-search__field');
            if (search) search.focus();
          });
      
          select.on('select2:select', function (event) {
            if (event.params && event.params.data) {
              loadCounterpartyPreview(event.params.data.id);
            }
          });
        };
      
        tryInit();
      }
  
    function recalcInvoice() {
      let total = 0;
  
      document.querySelectorAll('#itemsTable .onec-items-row').forEach(function (row) {
        const qty = parseNumber(row.querySelector('.onec-item-qty')?.value);
        const price = parseNumber(row.querySelector('.onec-item-price')?.value);
        const rowTotal = qty * price;
  
        row.querySelector('.onec-item-total').textContent = formatMoney(rowTotal);
        total += rowTotal;
      });
  
      document.getElementById('invoiceTotal').textContent = formatMoney(total);
    }
  
    function addInvoiceRow() {
      const body = document.querySelector('#itemsTable .onec-items-list__body');
      if (!body) return;
  
      const row = document.createElement('div');
      row.className = 'onec-items-row';
  
      row.innerHTML = `
        <input type="text" name="item_name[]" class="onec-input" placeholder="Товар или услуга" required>
        <input type="number" name="item_qty[]" class="onec-input onec-item-qty" value="1" step="0.1" min="0" required>
        <input type="number" name="item_price[]" class="onec-input onec-item-price" value="0" step="0.01" min="0" required>
        <div class="onec-item-total">0.00</div>
        <button type="button" class="onec-row-remove" aria-label="Удалить позицию">×</button>
      `;
  
      body.appendChild(row);
      recalcInvoice();
    }

    function initInvoiceDatepicker() {
        if (!window.jQuery || !window.jQuery.fn.datepicker) {
          console.error('Datepicker is not loaded');
          return;
        }
      
        $('.onec-date-input').datepicker({
          format: 'dd.mm.yyyy',
          language: 'ru',
          autoclose: true,
          todayHighlight: true,
          orientation: 'bottom auto',
          templates: {
            leftArrow: '‹',
            rightArrow: '›'
          }
        });
      }

      document.addEventListener('click', function (event) {
        const createBtn = event.target.closest('.onec-tab-create');
        if (!createBtn) return;
      
        event.preventDefault();
        event.stopPropagation();
      
        alert('Создание "' + createBtn.dataset.create + '" будет подключено после backend endpoint.');
      });
  
    document.addEventListener('DOMContentLoaded', function () {
      initCounterpartySelect();
      recalcInvoice();
      initInvoiceDatepicker();
  
      const addBtn = document.getElementById('addRow');
      if (addBtn) addBtn.addEventListener('click', addInvoiceRow);
  
      document.addEventListener('input', function (event) {
        if (
          event.target.classList.contains('onec-item-qty') ||
          event.target.classList.contains('onec-item-price')
        ) {
          recalcInvoice();
        }
      });
  
      document.addEventListener('click', function (event) {
        if (!event.target.classList.contains('onec-row-remove')) return;
  
        const rows = document.querySelectorAll('#itemsTable .onec-items-row');
  
        if (rows.length <= 1) {
          alert('В счёте должна быть минимум одна позиция.');
          return;
        }
  
        event.target.closest('.onec-items-row').remove();
        recalcInvoice();
      });
    });
  })();