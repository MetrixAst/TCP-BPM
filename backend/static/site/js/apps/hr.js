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

    const positionsUrl = form.dataset.positionsUrl;

    if (window.jQuery && jQuery.fn.select2) {
      jQuery("#hrEmployeeForm select").each(function () {
        const $select = jQuery(this);
        if ($select.hasClass("select2-hidden-accessible")) return;

        const placeholder = $select.data("placeholder") || "Выберите";

        $select.select2({
          width: "100%",
          placeholder: placeholder,
          allowClear: Boolean($select.data("allow-clear")),
          dropdownParent: jQuery(".hr-edit-card"),
          minimumResultsForSearch: $select.prop("multiple") ? 0 : Infinity
        });
      });
    }

    const deptSelect = form.querySelector('[name$="department"]');
    const positionSelect = form.querySelector('[name$="position"]');

    function loadPositions(deptId, keepValue) {
      if (!positionSelect || !positionsUrl || !deptId) {
        if (positionSelect) {
          positionSelect.innerHTML = '<option value="">— Выберите отдел —</option>';
          if (window.jQuery) jQuery(positionSelect).trigger("change");
        }
        return;
      }

      const saved = keepValue ? positionSelect.value : "";

      fetch(positionsUrl + "?department=" + encodeURIComponent(deptId), {
        headers: { "X-Requested-With": "XMLHttpRequest" }
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          const list = data.positions || [];
          positionSelect.innerHTML = '<option value="">— Выберите должность —</option>';

          list.forEach(function (p) {
            const opt = document.createElement("option");
            opt.value = String(p.id);
            opt.textContent = p.title;
            positionSelect.appendChild(opt);
          });

          if (saved && list.some(function (p) { return String(p.id) === saved; })) {
            positionSelect.value = saved;
          }

          if (window.jQuery) jQuery(positionSelect).trigger("change");
        })
        .catch(function () {
          console.error("Не удалось загрузить должности отдела");
        });
    }

    if (deptSelect && positionSelect && positionsUrl) {
      if (deptSelect.value) {
        loadPositions(deptSelect.value, true);
      }

      deptSelect.addEventListener("change", function () {
        loadPositions(deptSelect.value, false);
      });

      if (window.jQuery) {
        jQuery(deptSelect).on("select2:select select2:clear", function () {
          loadPositions(deptSelect.value, false);
        });
      }
    }

    const rolePick = form.querySelector('[name$="role_pick"]');
    const roleCustomWrap = document.getElementById("hrRoleCustomWrap");
    const roleCustomInput = form.querySelector('[name$="role_custom"]');

    function syncRoleCustomVisibility() {
      if (!rolePick || !roleCustomWrap) return;

      const show = rolePick.value === "__new_role__";
      roleCustomWrap.style.display = show ? "" : "none";

      if (roleCustomInput) {
        roleCustomInput.required = show;
      }
    }

    if (rolePick) {
      syncRoleCustomVisibility();
      rolePick.addEventListener("change", syncRoleCustomVisibility);

      if (window.jQuery) {
        jQuery(rolePick).on("select2:select", syncRoleCustomVisibility);
      }
    }

    form.addEventListener("submit", function (event) {
      const nameField = form.querySelector('[name$="first_name"], [name$="username"]');
      const employeeName = nameField ? nameField.value.trim() : "сотрудника";
      const msg = "Сохранить данные сотрудника «" + (employeeName || "…") + "»?";

      if (!window.confirm(msg)) {
        event.preventDefault();
      }
    });
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

    if (lines[0] && lines[0].toLowerCase().startsWith("id")) {
      lines.shift();
    }

    const rows = lines
      .map(parseCsvLine)
      .filter(function (row) {
        return row.length >= 2 && row[0];
      });

    return rows.map(function (row) {
      return {
        id: row[0],
        parentId: row[9] || "",
        name: row[8] || row[0],
        position: row[7] || "",
        type: row[2] || "",
        imageUrl: row[1] || "",
        profileUrl: row[3] && row[3] !== "#" ? row[3] : ""
      };
    });
  }

  function getCleanDepartmentId(id) {
    const raw = String(id || "");
    const match = raw.match(/(\d+)$/);
    return match ? match[1] : "";
  }

  function iconForDept(name) {
    const n = name.toLowerCase();

    if (n.includes("финанс") || n.includes("бухгалт")) return '<i class="bi bi-bar-chart-fill"></i>';
    if (n.includes("hr") || n.includes("кадр") || n.includes("персон")) return '<i class="bi bi-people-fill"></i>';
    if (n.includes("эксплуат") || n.includes("безопасн") || n.includes("техн")) return '<i class="bi bi-tools"></i>';
    if (n.includes("коммерч") || n.includes("аренд") || n.includes("маркет")) return '<i class="bi bi-shop"></i>';
    if (n.includes("админ") || n.includes("дирекц")) return '<i class="bi bi-building"></i>';
    if (n.includes("it") || n.includes("ит") || n.includes("цифр")) return '<i class="bi bi-cpu-fill"></i>';

    return '<i class="bi bi-diagram-3-fill"></i>';
  }

  function getNodeHtml(d) {
    const data = d.data || d;
    const rawName = (data.name || "Без названия").trim();
    const position = (data.position || "").trim();
    const type = (data.type || "").toLowerCase();
    const imageUrl = (data.imageUrl || "").trim();
    const profileUrl = (data.profileUrl || "").trim();
    const highlighted = data._highlighted ? " org-node--hl" : "";

    const nodeId = String(data.id || "");
    const isCompany = nodeId.startsWith("company_") || type.includes("компания");
    const isDept = nodeId.startsWith("dept_") || type.includes("департамент") || type.includes("отдел");
    const isEmployee = nodeId.startsWith("emp_");

    if (isCompany) {
      const initials = rawName
        .split(/\s+/)
        .slice(0, 2)
        .map(function (w) { return w[0]; })
        .join("")
        .toUpperCase();

      return `
        <div class="org-node org-node--company${highlighted}">
          <div class="org-node__company-logo">${initials}</div>
          <div class="org-node__company-name">${rawName}</div>
          <div class="org-node__company-label">Компания</div>
        </div>`;
    }

    if (isDept) {
      const parts = rawName.split("·");
      const deptName = parts[0].trim();
      const count = parts[1] ? parts[1].trim() : "";
      const icon = iconForDept(deptName);

      return `
        <div class="org-node org-node--dept${highlighted}" data-org-node-id="${data.id}">
          <div class="org-node__edit-actions">
            <button type="button" class="org-node__edit-btn" data-org-action="create-child" data-org-id="${data.id}" title="Добавить подотдел">
              <i class="bi bi-plus-lg"></i>
            </button>
            <button type="button" class="org-node__edit-btn" data-org-action="edit" data-org-id="${data.id}" title="Редактировать отдел">
              <i class="bi bi-pencil"></i>
            </button>
            <button type="button" class="org-node__edit-btn" data-org-action="move" data-org-id="${data.id}" title="Переместить отдел">
              <i class="bi bi-diagram-3"></i>
            </button>
          </div>

          <div class="org-node__dept-icon">${icon}</div>
          <div class="org-node__dept-body">
            <div class="org-node__dept-name">${deptName}</div>
            ${count ? `<div class="org-node__dept-count">${count}</div>` : ""}
            ${position && position !== "Отдел" ? `<div class="org-node__dept-head">Рук.: ${position}</div>` : ""}
          </div>
        </div>`;
    }

    if (!isEmployee && !isCompany && !isDept) {
      return `
        <div class="org-node org-node--dept${highlighted}" data-org-node-id="${data.id}">
          <div class="org-node__dept-icon">${iconForDept(rawName)}</div>
          <div class="org-node__dept-body">
            <div class="org-node__dept-name">${rawName}</div>
            ${position ? `<div class="org-node__dept-head">${position}</div>` : ""}
          </div>
        </div>`;
    }

    const clickClass = profileUrl ? " org-node--link" : "";
    const dataProp = profileUrl ? ` data-href="${profileUrl}"` : "";

    const words = rawName.split(/\s+/).filter(Boolean);
    const initials = words.length >= 2
      ? words[0][0].toUpperCase() + words[1][0].toUpperCase()
      : rawName.charAt(0).toUpperCase();

    const isDefaultAvatar = !imageUrl || imageUrl.includes("/profile/profile-") || imageUrl.length < 6;
    const hasPhoto = !isDefaultAvatar;
    const avatar = hasPhoto
      ? `<img class="org-emp__photo" src="${imageUrl}" alt="${rawName}">`
      : `<div class="org-emp__initials">${initials}</div>`;

    return `
      <div class="org-node org-node--emp${clickClass}${highlighted}"${dataProp}>
        <div class="org-emp__avatar">${avatar}</div>
        <div class="org-emp__info">
          <div class="org-emp__name">${rawName}</div>
          ${position ? `<div class="org-emp__pos">${position}</div>` : ""}
        </div>
        ${profileUrl ? `<div class="org-emp__arrow"><i class="bi bi-chevron-right"></i></div>` : ""}
      </div>`;
  }

  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function initOrgChart() {
    const container = document.getElementById("hrOrgChart");
    if (!container || typeof d3 === "undefined" || typeof d3.OrgChart === "undefined") return;

    const url = container.dataset.url;
    const editUrlTemplate = container.dataset.editUrlTemplate || "/hr/departments/__ID__/edit/";
    const moveUrlTemplate = container.dataset.moveUrlTemplate || "/hr/departments/__ID__/move/";
    let movingDeptId = null;
    let movingDeptName = "";
    const createUrl = container.dataset.createUrl || "/hr/departments/create/";
    let chart = null;
    let chartData = [];
    let editMode = false;

    function renderChart() {
      if (!chart || !chartData.length) return;
      chart.data(chartData).render();
    }

    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(function (response) {
        if (!response.ok) throw new Error("Bad response");
        return response.text();
      })
      .then(function (raw) {
        chartData = normalizeOrgData(raw);

        if (!chartData.length) {
          container.innerHTML = `<div class="hr-empty"><h3>Нет данных</h3></div>`;
          return;
        }

        chart = new d3.OrgChart()
          .container("#hrOrgChart")
          .data(chartData)
          .nodeId(function (d) { return d.id; })
          .parentNodeId(function (d) { return d.parentId; })
          .nodeWidth(function (d) {
            const t = (d.data.type || "").toLowerCase();
            if (t.includes("компания")) return 220;
            if (t.includes("департамент") || t.includes("отдел")) return 200;
            return 240;
          })
          .nodeHeight(function (d) {
            const t = (d.data.type || "").toLowerCase();
            if (t.includes("компания")) return 100;
            if (t.includes("департамент") || t.includes("отдел")) return 80;
            return 72;
          })
          .childrenMargin(function () { return 48; })
          .compactMarginBetween(function () { return 16; })
          .siblingsMargin(function () { return 20; })
          .nodeContent(getNodeHtml)
          .linkUpdate(function () {
            d3.select(this)
              .attr("stroke", "#d0d8f0")
              .attr("stroke-width", 1.5)
              .attr("stroke-dasharray", "none");
          })
          .onNodeClick(function (node) {
            if (editMode) return;

            const data = node && node.data ? node.data : node;
            const profileUrl = data && data.profileUrl;

            if (profileUrl && String(data.id || "").startsWith("emp_")) {
              window.location.href = profileUrl;
            }
          })
          .render();

        setTimeout(function () {
          chart.fit();

          const highlightId = container.dataset.highlight;
          if (highlightId) {
            chartData.forEach(function (item) {
              item._highlighted = item.id === highlightId;
              if (item._highlighted) item._expanded = true;
            });

            chart.data(chartData).render().fit();
          }
        }, 200);
      })
      .catch(function (error) {
        console.error("Chart Error Details:", error);
        container.innerHTML = `
          <div class="hr-empty">
            <i class="bi bi-exclamation-circle"></i>
            <h3>Ошибка загрузки</h3>
            <p style="font-size: 12px; opacity: 0.6;">${error.message}</p>
          </div>`;
      });

    function setupAction(id, action) {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("click", function () {
          if (chart && typeof chart[action] === "function") {
            chart[action]();
          }
        });
      }
    }

    setupAction("hrOrgZoomIn", "zoomIn");
    setupAction("hrOrgZoomOut", "zoomOut");
    setupAction("hrOrgFit", "fit");

    const expandAll = document.getElementById("hrOrgExpandAll");
    if (expandAll) {
      expandAll.addEventListener("click", function () {
        if (!chart || !chartData.length) return;

        chartData.forEach(function (item) {
          item._expanded = true;
          item._highlighted = false;
        });

        chart.data(chartData).render().fit();
      });
    }

    const search = document.getElementById("hrOrgSearch");
    if (search) {
      search.addEventListener("input", function () {
        if (!chart || !chartData.length) return;

        const val = search.value.trim().toLowerCase();

        chartData.forEach(function (item) {
          const text = [item.name, item.position, item.type].join(" ").toLowerCase();
          item._highlighted = Boolean(val && text.includes(val));
          if (val && text.includes(val)) item._expanded = true;
        });

        chart.data(chartData).render().fit();
      });
    }

    const editToggle = document.getElementById("hrOrgEditToggle");
    if (editToggle) {
      editToggle.addEventListener("click", function () {
        editMode = !editMode;

        document.body.classList.toggle("hr-org-edit-mode", editMode);
        editToggle.classList.toggle("is-active", editMode);

        renderChart();
      });
    }

    container.addEventListener("click", function (event) {
      const deptNode = event.target.closest(".org-node--dept");
      const button = event.target.closest("[data-org-action]");
    
      if (!editMode) return;
    
      if (button) {
        event.preventDefault();
        event.stopPropagation();
    
        const action = button.dataset.orgAction;
        const nodeId = button.dataset.orgId;
        const cleanId = getCleanDepartmentId(nodeId);
        const node = chartData.find(function (item) {
          return String(item.id) === String(nodeId);
        });
    
        if (!cleanId) return;
    
        if (action === "create-child") {
          window.location.href = createUrl + "?parent=" + encodeURIComponent(cleanId);
          return;
        }
    
        if (action === "edit") {
          window.location.href = editUrlTemplate.replace("__ID__", cleanId);
          return;
        }
    
        if (action === "move") {
          movingDeptId = cleanId;
          movingDeptName = node ? String(node.name || "").split("·")[0].trim() : "отдел";
    
          document.body.classList.add("hr-org-move-mode");
    
          if (chart) {
            chart.data(chartData).render();
          }
    
          alert("Теперь нажмите на отдел, внутрь которого нужно переместить «" + movingDeptName + "».");
          return;
        }
      }
    
      if (movingDeptId && deptNode) {
        event.preventDefault();
        event.stopPropagation();
    
        const targetRawId = deptNode.getAttribute("data-org-node-id");
        const targetId = getCleanDepartmentId(targetRawId);
    
        if (!targetId || targetId === movingDeptId) return;
    
        if (!confirm("Переместить отдел «" + movingDeptName + "» внутрь выбранного отдела?")) {
          movingDeptId = null;
          movingDeptName = "";
          document.body.classList.remove("hr-org-move-mode");
          return;
        }
    
        const csrfToken = getCsrfToken();
    
        fetch(moveUrlTemplate.replace("__ID__", movingDeptId), {
          method: "POST",
          headers: {
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "X-CSRFToken": csrfToken
          },
          body: new URLSearchParams({
            parent: targetId
          })
        })
          .then(function (response) {
            if (!response.ok) throw new Error("Move failed");
            return response.json();
          })
          .then(function () {
            window.location.reload();
          })
          .catch(function () {
            alert("Не удалось переместить отдел.");
          });
      }
    });
  }

  function initHrDatepickers() {
    const selectors = [
      'input[name="hire_date"]',
      'input[name="date_joined"]',
      'input[name="birth_date"]',
      'input[name="registration_date"]',
      ".js-hr-datepicker"
    ];

    document.querySelectorAll(selectors.join(",")).forEach(function (input) {
      input.setAttribute("type", "text");
      input.setAttribute("autocomplete", "off");
      input.setAttribute("placeholder", "дд.мм.гггг");

      if (window.jQuery && jQuery.fn.datepicker) {
        jQuery(input).datepicker({
          format: "yyyy-mm-dd",
          autoclose: true,
          todayHighlight: true,
          orientation: "bottom auto"
        });
      }
    });
  }

  function initHrEmployeesFilters() {
    const page = document.querySelector(".hr-employees-page");
    if (!page) return;

    const form = page.querySelector("#filter_form");
    if (!form) return;

    const fields = Array.from(form.querySelectorAll(".grid_child"));

    fields.forEach(function (field) {
      if (field.querySelector(".hr-filter-label")) return;

      const input = field.querySelector("input, select, textarea");
      if (!input) return;

      let labelText = "Фильтр";

      const key = (
        input.name ||
        input.id ||
        input.placeholder ||
        ""
      ).toLowerCase();

      if (key.includes("search") || key.includes("q")) {
        labelText = "Поиск";
      } else if (key.includes("company")) {
        labelText = "Компания";
      } else if (key.includes("department")) {
        labelText = "Отдел";
      } else if (key.includes("position")) {
        labelText = "Должность";
      } else if (key.includes("status")) {
        labelText = "Статус";
      } else if (key.includes("sort")) {
        labelText = "Сортировка";
      }

      const label = document.createElement("label");
      label.className = "hr-filter-label";
      label.textContent = labelText;

      if (input.id) {
        label.setAttribute("for", input.id);
      }

      field.insertBefore(label, field.firstChild);
    });

    if (window.jQuery && jQuery.fn.select2) {
      jQuery(form).find("select").each(function () {
        const $select = jQuery(this);

        if ($select.hasClass("select2-hidden-accessible")) return;

        $select.select2({
          width: "100%",
          minimumResultsForSearch: Infinity,
          dropdownParent: jQuery(".hr-employees-page")
        });
      });
    }
  }

  function initDepartmentForm() {
    const form = document.getElementById("hrDepartmentForm");
    if (!form) return;
  
    if (window.jQuery && jQuery.fn.select2) {
      jQuery(form).find("select").each(function () {
        const $select = jQuery(this);
  
        if ($select.hasClass("select2-hidden-accessible")) return;
  
        $select.select2({
          width: "100%",
          minimumResultsForSearch: Infinity,
          dropdownParent: jQuery(".hr-edit-card")
        });
      });
    }
  }

  function init() {
    initTableSearch();
    initInlineModals();
    initEmployeeForm();
    initOrgChart();
    initHrDatepickers();
    initHrEmployeesFilters();
    initDepartmentForm();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();