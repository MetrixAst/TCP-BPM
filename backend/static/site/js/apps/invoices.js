document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('invoiceForm');
    if (!form) return;

    const periodInput = form.querySelector('[name="period"]');
    if (periodInput) {
       periodInput.setAttribute('autocomplete', 'off');
    }
  
    document.querySelectorAll('#invoiceForm select').forEach(function (select) {
      const emptyOption = select.querySelector('option[value=""]');
  
      if (emptyOption) {
        if (select.name === 'tenant') emptyOption.textContent = 'Выберите арендатора';
        else if (select.name === 'counterparty') emptyOption.textContent = 'Выберите контрагента';
        else if (select.name === 'sent_via') emptyOption.textContent = 'Выберите способ';
        else emptyOption.textContent = 'Выберите';
      }
    });
  
    if (window.jQuery && jQuery.fn.select2) {
      jQuery('#invoiceForm select').each(function () {
        const $select = jQuery(this);
  
        if ($select.hasClass('select2-hidden-accessible')) return;
  
        const placeholder = $select.find('option[value=""]').first().text() || 'Выберите';
  
        $select.select2({
          width: '100%',
          placeholder: placeholder,
          allowClear: false,
          dropdownParent: jQuery('.invoice-edit-card'),
          minimumResultsForSearch: Infinity
        });
      });
    }

    if (window.jQuery && jQuery.fn.datepicker) {
        jQuery('#invoiceForm input[name="period"]').datepicker({
          format: 'dd.mm.yyyy',
          autoclose: true,
          todayHighlight: true,
          orientation: 'bottom auto'
        });
      }
  
    const itemsContainer = document.getElementById('invoiceItems');
    const addButton = document.getElementById('addInvoiceItem');
    const template = document.getElementById('invoiceItemTemplate');
    const totalForms = form.querySelector('[name$="-TOTAL_FORMS"]');
  
    const totalInput = form.querySelector('[name="total_amount"]');
    const vatInput = form.querySelector('[name="vat_amount"]');
  
    if (!itemsContainer || !totalForms) return;
  
    function numberValue(input) {
      if (!input) return 0;
      return Number(String(input.value || '0').replace(',', '.')) || 0;
    }
  
    function money(value) {
      return new Intl.NumberFormat('ru-RU', {
        maximumFractionDigits: 0
      }).format(value || 0) + ' ₸';
    }
  
    function calculate() {
      let totalWithoutVat = 0;
      let totalVat = 0;
  
      itemsContainer.querySelectorAll('.invoice-item-row').forEach(function (row) {
        const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
  
        if (deleteInput && deleteInput.checked) {
          row.classList.add('is-deleted');
          return;
        }
  
        const quantity = numberValue(row.querySelector('[name$="-quantity"]'));
        const price = numberValue(row.querySelector('[name$="-price"]'));
        const vatRate = numberValue(row.querySelector('[name$="-vat_rate"]'));
  
        const rowTotal = quantity * price;
        const rowVat = rowTotal * vatRate / 100;
  
        totalWithoutVat += rowTotal;
        totalVat += rowVat;
  
        const rowTotalText = row.querySelector('[data-row-total]');
        if (rowTotalText) {
          rowTotalText.textContent = money(rowTotal);
        }
      });
  
      if (totalInput) totalInput.value = totalWithoutVat.toFixed(2);
      if (vatInput) vatInput.value = totalVat.toFixed(2);
    }
  
    function bindRow(row) {
      row.querySelectorAll('input, select, textarea').forEach(function (input) {
        input.addEventListener('input', calculate);
        input.addEventListener('change', calculate);
      });
  
      const removeButton = row.querySelector('.invoice-remove-row');
  
      removeButton?.addEventListener('click', function () {
        const deleteInput = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
  
        if (deleteInput) {
          deleteInput.checked = true;
          row.classList.add('is-deleted');
        } else {
          row.remove();
          totalForms.value = itemsContainer.querySelectorAll('.invoice-item-row').length;
        }
  
        calculate();
      });
    }
  
    addButton?.addEventListener('click', function () {
      if (!template) return;
  
      const index = Number(totalForms.value || 0);
      const html = template.innerHTML.replaceAll('__prefix__', index);
  
      const wrapper = document.createElement('div');
      wrapper.innerHTML = html.trim();
  
      const row = wrapper.firstElementChild;
      itemsContainer.appendChild(row);
  
      totalForms.value = index + 1;
  
      bindRow(row);
      calculate();
    });
  
    itemsContainer.querySelectorAll('.invoice-item-row').forEach(bindRow);
  
    calculate();
  });