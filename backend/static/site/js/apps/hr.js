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

        const placeholder = $select.data("placeholder") || "Выберите";

        $select.select2({
          width: "100%",
          placeholder: placeholder,
          allowClear: false,
          dropdownParent: jQuery(".hr-edit-card"),
          minimumResultsForSearch: $select.prop("multiple") ? 0 : Infinity
        });
      });
    }
  }

  function parseCsvLine(line) {
    const result = [];
    let current = "";
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const char = line[i];
      if (char === '"') {
        inQuotes = !inQuotes;
      } else if (char === "," && !inQuotes) {
        result.push(current.trim());
        current = "";
      } else {
        current += char;
      }
    }
    result.push(current.trim());
    return result;
  }

  function normalizeOrgData(raw) {
    if (!raw) return [];

    const lines = String(raw).trim().split(/\r?\n/);
    // Пропускаем заголовок, если первая строка начинается с "id"
    if (lines[0].toLowerCase().startsWith("id")) {
      lines.shift();
    }

    const rows = lines
      .map(parseCsvLine)
      .filter(row => row.length >= 2 && row[0]);

    return rows.map(function (row) {
      // Маппинг согласно твоей структуре:
      // 0:id, 1:imageUrl, 2:area, 7:positionName, 8:name, 9:parentId
      return {
        id: row[0],
        parentId: row[9] || "",
        name: row[8] || row[0],
        position: row[7] || "",
        type: row[2] || "", 
        imageUrl: row[1] || "" // Явно передаем URL для d3-org-chart
      };
    });
  }

  function getNodeHtml(d) {
    const data = d.data || d;
    const name = data.name || "Без названия";
    const position = data.position || "";
    const type = (data.type || "").toLowerCase();
    const imageUrl = data.imageUrl;
    
    let typeLabel = "Сотрудник";
    if (type.includes("компания")) typeLabel = "Компания";
    if (type.includes("департамент") || type.includes("отдел")) typeLabel = "Отдел";

    const highlightClass = data._highlighted ? " is-highlighted" : "";

    // Если есть imageUrl, показываем картинку, если нет — первую букву
    const avatarHtml = imageUrl && imageUrl.length > 5
      ? `<img class="hr-org-node__avatar-img" src="${imageUrl}" alt="">`
      : `<div class="hr-org-node__avatar-letter">${name.trim().charAt(0).toUpperCase()}</div>`;

    return `
      <div class="hr-org-node${highlightClass}">
        <div class="hr-org-node__top">
          <div class="hr-org-node__type">${typeLabel}</div>
          <div class="hr-org-node__name">${name}</div>
        </div>
        <div class="hr-org-node__bottom">
          <div class="hr-org-node__avatar">${avatarHtml}</div>
          <div class="hr-org-node__position">${position || typeLabel}</div>
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

    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(response => {
        if (!response.ok) throw new Error("Bad response");
        return response.text();
      })
      .then(raw => {
        chartData = normalizeOrgData(raw);

        if (!chartData.length) {
          container.innerHTML = `<div class="hr-empty"><h3>Нет данных</h3></div>`;
          return;
        }

        // Инициализация без вызова .imageUrl()
        chart = new d3.OrgChart()
          .container("#hrOrgChart")
          .data(chartData)
          .nodeId(d => d.id)
          .parentNodeId(d => d.parentId)
          // Если библиотека ругается на отсутствие метода, 
          // мы просто задаем контент через nodeContent (он у нас уже настроен)
          .nodeWidth(() => 220)
          .nodeHeight(() => 112)
          .childrenMargin(() => 52)
          .compactMarginBetween(() => 30)
          .siblingsMargin(() => 26)
          .nodeContent(getNodeHtml) 
          .render();

        setTimeout(() => chart.fit(), 200);
      })
      .catch(error => {
        console.error("Chart Error Details:", error);
        container.innerHTML = `
          <div class="hr-empty">
            <i class="bi bi-exclamation-circle"></i>
            <h3>Ошибка загрузки</h3>
            <p style="font-size: 12px; opacity: 0.6;">${error.message}</p>
          </div>`;
      });

    // Оставляем кнопки зума и поиска как были
    const setupAction = (id, action) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener("click", () => chart && chart[action]());
    };

    setupAction("hrOrgZoomIn", "zoomIn");
    setupAction("hrOrgZoomOut", "zoomOut");
    setupAction("hrOrgFit", "fit");

    const search = document.getElementById("hrOrgSearch");
    if (search) {
      search.addEventListener("input", function () {
        if (!chart || !chartData.length) return;
        const val = search.value.trim().toLowerCase();

        chartData.forEach(item => {
          const text = [item.name, item.position, item.type].join(" ").toLowerCase();
          item._highlighted = Boolean(val && text.includes(val));
          if (val && text.includes(val)) item._expanded = true;
        });

        chart.data(chartData).render().fit();
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