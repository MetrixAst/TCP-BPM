(function () {
    "use strict";
  
    function initTableSearch() {
      const searchInput = document.querySelector(".hr-table-search");
      if (!searchInput) return;
  
      const rows = document.querySelectorAll(".hr-table__body .hr-table__row");
  
      searchInput.addEventListener("input", function () {
        const value = searchInput.value.trim().toLowerCase();
  
        rows.forEach(function (row) {
          const text = row.textContent.toLowerCase();
          row.style.display = text.includes(value) ? "" : "none";
        });
      });
    }
  
    function initInlineModals() {
      document.querySelectorAll("[data-hr-modal-open]").forEach(function (button) {
        button.addEventListener("click", function () {
          const id = button.getAttribute("data-hr-modal-open");
          const modal = document.getElementById(id);
          if (modal) modal.hidden = false;
        });
      });
  
      document.querySelectorAll("[data-hr-modal-close]").forEach(function (button) {
        button.addEventListener("click", function () {
          const modal = button.closest(".hr-inline-modal");
          if (modal) modal.hidden = true;
        });
      });
  
      document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
  
        document.querySelectorAll(".hr-inline-modal:not([hidden])").forEach(function (modal) {
          modal.hidden = true;
        });
      });
      
      if (window.jQuery && jQuery.fn.datepicker) {
        jQuery(".hr-inline-date").datepicker({
          format: "dd.mm.yyyy",
          autoclose: true,
          todayHighlight: true,
          orientation: "bottom auto"
        });
      }
    }
  
    function initEmployeeForm() {
      const form = document.getElementById("hrEmployeeForm");
      if (!form) return;
  
      if (window.jQuery && jQuery.fn.select2) {
        jQuery("#hrEmployeeForm select").each(function () {
          const $select = jQuery(this);
  
          if ($select.hasClass("select2-hidden-accessible")) return;
  
          const placeholder =
            $select.data("placeholder") ||
            $select.find('option[value=""]').first().text() ||
            "Выберите";
  
          $select.select2({
            width: "100%",
            placeholder: placeholder,
            allowClear: false,
            dropdownParent: jQuery(".hr-edit-card"),
            minimumResultsForSearch: $select.prop("multiple") ? 0 : Infinity
          });
        });
      }
  
      if (window.jQuery && jQuery.fn.datepicker) {
        jQuery("#hrEmployeeForm .hr-edit-date").datepicker({
          format: "dd.mm.yyyy",
          autoclose: true,
          todayHighlight: true,
          orientation: "bottom auto"
        });
      }
    }
  
    function normalizeOrgData(raw) {
      if (!raw) return [];
  
      if (Array.isArray(raw)) return raw;
      if (raw.data && Array.isArray(raw.data)) return raw.data;
      if (raw.items && Array.isArray(raw.items)) return raw.items;
      if (raw.children) return flattenTree(raw);
  
      return [];
    }
  
    function flattenTree(root) {
      const result = [];
  
      function walk(node, parentId) {
        const id = node.id || node.pk || node.name || Math.random().toString(36).slice(2);
  
        result.push({
          id: id,
          parentId: parentId || "",
          name: node.name || node.title || node.full_name || "Без названия",
          position: node.position || node.role || node.type || "",
          type: node.type || "employee"
        });
  
        if (Array.isArray(node.children)) {
          node.children.forEach(function (child) {
            walk(child, id);
          });
        }
      }
  
      walk(root, "");
      return result;
    }
  
    function getNodeHtml(d) {
      const data = d.data || d;
      const name = data.name || data.title || data.full_name || "Без названия";
      const position = data.position || data.role || data.department || "";
      const type = data.type || data.kind || "employee";
      const letter = name.trim().charAt(0).toUpperCase();
  
      return `
        <div class="hr-org-node">
          <div class="hr-org-node__top">
            <div class="hr-org-node__type">${type}</div>
            <div class="hr-org-node__name">${name}</div>
          </div>
          <div class="hr-org-node__bottom">
            <div class="hr-org-node__avatar">${letter}</div>
            <div class="hr-org-node__position">${position || "Сотрудник"}</div>
          </div>
        </div>
      `;
    }
  
    function initOrgChart() {
      const container = document.getElementById("hrOrgChart");
      if (!container || typeof d3 === "undefined" || typeof d3.OrgChart === "undefined") return;
  
      const url = container.dataset.url;
      let chart = null;
      let chartData = [];
  
      fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest"
        }
      })
        .then(function (response) {
          return response.json();
        })
        .then(function (raw) {
          chartData = normalizeOrgData(raw);
  
          if (!chartData.length) {
            container.innerHTML = `
              <div class="hr-empty">
                <i class="bi bi-diagram-3"></i>
                <h3>Нет данных для оргструктуры</h3>
                <p>Backend вернул пустой список.</p>
              </div>
            `;
            return;
          }
  
          chart = new d3.OrgChart()
            .container("#hrOrgChart")
            .data(chartData)
            .nodeWidth(function () { return 220; })
            .nodeHeight(function () { return 118; })
            .childrenMargin(function () { return 46; })
            .compactMarginBetween(function () { return 28; })
            .compactMarginPair(function () { return 52; })
            .siblingsMargin(function () { return 24; })
            .buttonContent(function () {
              return `<div style="width:24px;height:24px;border-radius:50%;background:#2f6bed;color:#fff;display:flex;align-items:center;justify-content:center;font-size:12px;">+</div>`;
            })
            .nodeContent(getNodeHtml)
            .render();
  
          setTimeout(function () {
            chart.fit();
          }, 200);
        })
        .catch(function () {
          container.innerHTML = `
            <div class="hr-empty">
              <i class="bi bi-exclamation-circle"></i>
              <h3>Не удалось загрузить оргструктуру</h3>
              <p>Проверь endpoint в data-url.</p>
            </div>
          `;
        });
  
      const zoomIn = document.getElementById("hrOrgZoomIn");
      const zoomOut = document.getElementById("hrOrgZoomOut");
      const fit = document.getElementById("hrOrgFit");
  
      if (zoomIn) {
        zoomIn.addEventListener("click", function () {
          if (chart) chart.zoomIn();
        });
      }
  
      if (zoomOut) {
        zoomOut.addEventListener("click", function () {
          if (chart) chart.zoomOut();
        });
      }
  
      if (fit) {
        fit.addEventListener("click", function () {
          if (chart) chart.fit();
        });
      }
    }
  
    function init() {
      initTableSearch();
      initInlineModals();
      initEmployeeForm();
      initOrgChart();
    }
  
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", init);
    } else {
      init();
    }
  })();