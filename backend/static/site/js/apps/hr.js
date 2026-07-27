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
        imageUrl: row[1] || "",
        profileUrl: row[3] && row[3] !== "#" ? row[3] : "",
      };
    });
  }

  const orgChartState = {
    editMode: false,
    canEdit: false,
    chart: null,
    chartData: [],
    reload: null,
    departmentsApi: "",
    companiesApi: "",
  };

  function orgEditActionsHtml(nodeId, kind) {
    if (!orgChartState.editMode || !orgChartState.canEdit) return "";
    if (kind === "company") {
      const companyId = String(nodeId).replace("company_", "");
      return `
        <div class="org-node__actions" onclick="event.stopPropagation()">
          <button type="button" class="org-node__btn" data-org-company-add="${companyId}" title="Добавить отдел">
            <i class="bi bi-plus-lg"></i>
          </button>
        </div>`;
    }
    if (kind === "dept") {
      const deptId = String(nodeId).replace("dept_", "");
      return `
        <div class="org-node__actions" onclick="event.stopPropagation()">
          <button type="button" class="org-node__btn" data-org-dept-edit="${deptId}" title="Изменить">
            <i class="bi bi-pencil"></i>
          </button>
          <button type="button" class="org-node__btn" data-org-dept-child="${deptId}" title="Подотдел">
            <i class="bi bi-plus-lg"></i>
          </button>
        </div>`;
    }
    return "";
  }

  function getNodeHtml(d) {
    const data = d.data || d;
    const rawName  = (data.name     || "Без названия").trim();
    const position = (data.position || "").trim();
    const type     = (data.type     || "").toLowerCase();
    const imageUrl = (data.imageUrl || "").trim();
    const profileUrl = (data.profileUrl || "").trim();
    const highlighted = data._highlighted ? " org-node--hl" : "";
    const nodeId = String(data.id || "");

    const isCompany  = type.includes("компания");
    const isDept     = type.includes("департамент") || type.includes("отдел");
    const isEmployee = nodeId.startsWith("emp_");

    /* ── COMPANY ── */
    if (isCompany) {
      const initials = rawName.split(/\s+/).slice(0, 2).map(w => w[0]).join("").toUpperCase();
      return `
        <div class="org-node org-node--company${highlighted}${orgChartState.editMode ? " org-node--editable" : ""}">
          <div class="org-node__company-logo">${initials}</div>
          <div class="org-node__company-name">${rawName}</div>
          <div class="org-node__company-label">Компания</div>
          ${orgEditActionsHtml(nodeId, "company")}
        </div>`;
    }

    /* ── DEPT ── */
    if (isDept) {
      // name может быть "Финансы · 3 чел." — разобьём
      const parts    = rawName.split("·");
      const deptName = parts[0].trim();
      const count    = parts[1] ? parts[1].trim() : "";
      const icon     = iconForDept(deptName);
      return `
        <div class="org-node org-node--dept${highlighted}${orgChartState.editMode ? " org-node--editable" : ""}">
          <div class="org-node__dept-icon">${icon}</div>
          <div class="org-node__dept-body">
            <div class="org-node__dept-name">${deptName}</div>
            ${count ? `<div class="org-node__dept-count">${count}</div>` : ""}
            ${position && position !== "Отдел" ? `<div class="org-node__dept-head">Рук.: ${position}</div>` : ""}
          </div>
          ${orgEditActionsHtml(nodeId, "dept")}
        </div>`;
    }

    /* ── EMPLOYEE ── */
    const clickClass = profileUrl ? " org-node--link" : "";
    const dataProp   = profileUrl ? ` data-href="${profileUrl}"` : "";

    // Инициалы из имени
    const words    = rawName.split(/\s+/).filter(Boolean);
    const initials = words.length >= 2
      ? words[0][0].toUpperCase() + words[1][0].toUpperCase()
      : rawName.charAt(0).toUpperCase();

    // Аватар — фото если есть, иначе инициалы
    // дефолтный аватар из utils.py — profile-1.webp; если это он — показываем инициалы
    const isDefaultAvatar = !imageUrl || imageUrl.includes("/profile/profile-") || imageUrl.length < 6;
    const hasPhoto = !isDefaultAvatar;
    const avatar   = hasPhoto
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

  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function apiFetch(url, options) {
    const opts = Object.assign({
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
    }, options || {});
    if (opts.method && opts.method !== "GET") {
      opts.headers["X-CSRFToken"] = getCsrfToken();
    }
    return fetch(url, opts).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (body) {
          let msg = body.detail;
          if (!msg && typeof body === "object") {
            const firstKey = Object.keys(body)[0];
            if (firstKey && Array.isArray(body[firstKey])) msg = body[firstKey][0];
            else if (firstKey) msg = body[firstKey];
          }
          throw new Error(msg || "Ошибка запроса");
        });
      }
      if (response.status === 204) return null;
      return response.json();
    });
  }

  function initOrgChartEdit(container) {
    if (!container || container.dataset.canEdit !== "1") return;

    orgChartState.canEdit = true;
    orgChartState.departmentsApi = container.dataset.departmentsApi || "/api/v1/hr/departments/";
    orgChartState.companiesApi = container.dataset.companiesApi || "/api/v1/hr/companies/";

    const modal = document.getElementById("hrOrgDeptModal");
    const form = document.getElementById("hrOrgDeptForm");
    const toggle = document.getElementById("hrOrgEditToggle");
    const deleteBtn = document.getElementById("hrOrgDeptDelete");
    const errorEl = document.getElementById("hrOrgDeptError");
    const companySelect = document.getElementById("hrOrgDeptCompany");
    const parentSelect = document.getElementById("hrOrgDeptParent");

    if (!modal || !form || !toggle) return;

    let modalContext = { companyId: null, parentId: null, departmentId: null };
    let companiesCache = null;
    let departmentsCache = null;

    function showError(message) {
      if (!errorEl) return;
      if (message) {
        errorEl.textContent = message;
        errorEl.hidden = false;
      } else {
        errorEl.textContent = "";
        errorEl.hidden = true;
      }
    }

    function closeModal() {
      modal.hidden = true;
      showError("");
    }

    function loadCompanies() {
      if (companiesCache) return Promise.resolve(companiesCache);
      return apiFetch(orgChartState.companiesApi + "?page_size=200").then(function (data) {
        companiesCache = data.results || data;
        return companiesCache;
      });
    }

    function loadDepartments(companyId) {
      const url = orgChartState.departmentsApi + "tree/?company=" + encodeURIComponent(companyId);
      return apiFetch(url).then(function (data) {
        departmentsCache = data.results || data;
        return departmentsCache;
      });
    }

    function fillParentOptions(companyId, excludeId, selectedId) {
      return loadDepartments(companyId).then(function (rows) {
        parentSelect.innerHTML = '<option value="">— корневой отдел компании —</option>';
        rows.forEach(function (row) {
          if (excludeId && String(row.id) === String(excludeId)) return;
          const opt = document.createElement("option");
          opt.value = row.id;
          const indent = row.level ? "—".repeat(row.level) + " " : "";
          opt.textContent = indent + row.name;
          if (selectedId && String(row.id) === String(selectedId)) {
            opt.selected = true;
          }
          parentSelect.appendChild(opt);
        });
      });
    }

    function openDeptModal(ctx) {
      modalContext = ctx || {};
      showError("");
      const isEdit = Boolean(modalContext.departmentId);
      document.getElementById("hrOrgDeptModalTitle").textContent = isEdit ? "Редактировать отдел" : "Новый отдел";
      deleteBtn.hidden = !isEdit;
      document.getElementById("hrOrgDeptId").value = modalContext.departmentId || "";
      document.getElementById("hrOrgDeptName").value = "";
      document.getElementById("hrOrgDeptLevel").value = "department";
      modal.hidden = false;

      loadCompanies().then(function (companies) {
        companySelect.innerHTML = "";
        companies.forEach(function (c) {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = c.name;
          companySelect.appendChild(opt);
        });

        const companyId = modalContext.companyId || (companies[0] && companies[0].id);
        if (companyId) companySelect.value = companyId;

        if (isEdit) {
          return apiFetch(orgChartState.departmentsApi + modalContext.departmentId + "/").then(function (dept) {
            document.getElementById("hrOrgDeptName").value = dept.name || "";
            companySelect.value = dept.company;
            document.getElementById("hrOrgDeptLevel").value = dept.level_type || "department";
            return fillParentOptions(dept.company, dept.id, dept.parent);
          });
        }

        if (modalContext.companyId) {
          companySelect.value = modalContext.companyId;
        }
        return fillParentOptions(companySelect.value, null, modalContext.parentId || null);
      }).catch(function (err) {
        showError(err.message);
      });
    }

    companySelect.addEventListener("change", function () {
      fillParentOptions(companySelect.value, modalContext.departmentId || null, null);
    });

    toggle.addEventListener("click", function () {
      orgChartState.editMode = !orgChartState.editMode;
      toggle.classList.toggle("is-active", orgChartState.editMode);
      toggle.querySelector("span").textContent = orgChartState.editMode ? "Готово" : "Редактировать";
      if (orgChartState.chart && orgChartState.chartData.length) {
        orgChartState.chart.data(orgChartState.chartData).render().fit();
      }
    });

    container.addEventListener("click", function (event) {
      const editBtn = event.target.closest("[data-org-dept-edit]");
      const childBtn = event.target.closest("[data-org-dept-child]");
      const companyBtn = event.target.closest("[data-org-company-add]");
      if (editBtn) {
        event.preventDefault();
        event.stopPropagation();
        const row = (departmentsCache || []).find(function (d) {
          return String(d.id) === editBtn.getAttribute("data-org-dept-edit");
        });
        openDeptModal({
          departmentId: editBtn.getAttribute("data-org-dept-edit"),
          companyId: row && row.company,
        });
        return;
      }
      if (childBtn) {
        event.preventDefault();
        event.stopPropagation();
        const deptId = childBtn.getAttribute("data-org-dept-child");
        const row = (departmentsCache || []).find(function (d) {
          return String(d.id) === deptId;
        });
        openDeptModal({
          parentId: deptId,
          companyId: row && row.company,
        });
        return;
      }
      if (companyBtn) {
        event.preventDefault();
        event.stopPropagation();
        openDeptModal({ companyId: companyBtn.getAttribute("data-org-company-add") });
      }
    });

    modal.querySelectorAll("[data-hr-org-modal-close]").forEach(function (el) {
      el.addEventListener("click", closeModal);
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      showError("");
      const payload = {
        name: document.getElementById("hrOrgDeptName").value.trim(),
        company: parseInt(companySelect.value, 10),
        level_type: document.getElementById("hrOrgDeptLevel").value,
        parent: parentSelect.value ? parseInt(parentSelect.value, 10) : null,
      };
      const deptId = document.getElementById("hrOrgDeptId").value;
      const method = deptId ? "PATCH" : "POST";
      const url = deptId
        ? orgChartState.departmentsApi + deptId + "/"
        : orgChartState.departmentsApi;

      apiFetch(url, { method: method, body: JSON.stringify(payload) })
        .then(function () {
          closeModal();
          departmentsCache = null;
          if (typeof orgChartState.reload === "function") {
            orgChartState.reload();
          }
        })
        .catch(function (err) {
          showError(err.message);
        });
    });

    deleteBtn.addEventListener("click", function () {
      const deptId = document.getElementById("hrOrgDeptId").value;
      if (!deptId || !window.confirm("Удалить отдел?")) return;
      apiFetch(orgChartState.departmentsApi + deptId + "/", { method: "DELETE" })
        .then(function () {
          closeModal();
          departmentsCache = null;
          if (typeof orgChartState.reload === "function") {
            orgChartState.reload();
          }
        })
        .catch(function (err) {
          showError(err.message);
        });
    });

    window.hrOrgOpenDeptModal = openDeptModal;
  }

  function initOrgChart() {
    const container = document.getElementById("hrOrgChart");
    if (!container || typeof d3 === "undefined" || typeof d3.OrgChart === "undefined") return;

    const url = container.dataset.url;
    let chart = null;
    let chartData = [];

    function renderChart() {
      return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
      .then(response => {
        if (!response.ok) throw new Error("Bad response");
        return response.text();
      })
      .then(function (raw) {
        chartData = normalizeOrgData(raw);
        orgChartState.chartData = chartData;

        if (!chartData.length) {
          container.innerHTML = `<div class="hr-empty"><h3>Нет данных</h3></div>`;
          orgChartState.chart = null;
          return;
        }

        if (!chart) {
          chart = new d3.OrgChart()
          .container("#hrOrgChart")
          .data(chartData)
          .nodeId(d => d.id)
          .parentNodeId(d => d.parentId)
          // Если библиотека ругается на отсутствие метода, 
          // мы просто задаем контент через nodeContent (он у нас уже настроен)
          .nodeWidth(d => {
            const t = (d.data.type || "").toLowerCase();
            if (t.includes("компания")) return 220;
            if (t.includes("департамент") || t.includes("отдел")) return 200;
            return 240;
          })
          .nodeHeight(d => {
            const t = (d.data.type || "").toLowerCase();
            if (t.includes("компания")) return 100;
            if (t.includes("департамент") || t.includes("отдел")) return 80;
            return 72;
          })
          .childrenMargin(() => 48)
          .compactMarginBetween(() => 16)
          .siblingsMargin(() => 20)
          .nodeContent(getNodeHtml)
          .linkUpdate(function (d) {
            d3.select(this)
              .attr("stroke", "#d0d8f0")
              .attr("stroke-width", 1.5)
              .attr("stroke-dasharray", "none");
          })
          .onNodeClick(function (node) {
            const data = node && node.data ? node.data : node;
            if (!data) return;
            const id = String(data.id || "");
            if (orgChartState.editMode && orgChartState.canEdit) {
              if (id.startsWith("dept_") && window.hrOrgOpenDeptModal) {
                window.hrOrgOpenDeptModal({ departmentId: id.replace("dept_", "") });
                return;
              }
              if (id.startsWith("company_") && window.hrOrgOpenDeptModal) {
                window.hrOrgOpenDeptModal({ companyId: id.replace("company_", "") });
                return;
              }
            }
            const profileUrl = data.profileUrl;
            if (profileUrl && id.startsWith("emp_")) {
              window.location.href = profileUrl;
            }
          });
        }

        chart.data(chartData).render();

        orgChartState.chart = chart;

        setTimeout(function () {
          chart.fit();
          const highlightId = container.dataset.highlight;
          if (highlightId) {
            chartData.forEach(function (item) {
              item._highlighted = item.id === highlightId;
              if (item._highlighted) {
                item._expanded = true;
              }
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
    }

    orgChartState.reload = function () {
      renderChart();
    };

    renderChart();
    initOrgChartEdit(container);

    // Оставляем кнопки зума и поиска как были
    const setupAction = function (id, action) {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("click", function () {
          if (orgChartState.chart) orgChartState.chart[action]();
        });
      }
    };

    setupAction("hrOrgZoomIn", "zoomIn");
    setupAction("hrOrgZoomOut", "zoomOut");
    setupAction("hrOrgFit", "fit");

    const expandAll = document.getElementById("hrOrgExpandAll");
    if (expandAll) {
      expandAll.addEventListener("click", function () {
        if (!orgChartState.chart || !orgChartState.chartData.length) return;
        orgChartState.chartData.forEach(function (item) {
          item._expanded = true;
          item._highlighted = false;
        });
        orgChartState.chart.data(orgChartState.chartData).render().fit();
      });
    }

    const search = document.getElementById("hrOrgSearch");
    if (search) {
      search.addEventListener("input", function () {
        if (!orgChartState.chart || !orgChartState.chartData.length) return;
        const val = search.value.trim().toLowerCase();

        orgChartState.chartData.forEach(function (item) {
          const text = [item.name, item.position, item.type].join(" ").toLowerCase();
          item._highlighted = Boolean(val && text.includes(val));
          if (val && text.includes(val)) item._expanded = true;
        });

        orgChartState.chart.data(orgChartState.chartData).render().fit();
      });
    }
  }

  function initHrDatepickers() {
    const selectors = [
      'input[name="hire_date"]',
      'input[name="date_joined"]',
      'input[name="birth_date"]',
      'input[name="registration_date"]',
      '.js-hr-datepicker'
    ];

    document.querySelectorAll(selectors.join(',')).forEach(function (input) {
      input.setAttribute('type', 'text');
      input.setAttribute('autocomplete', 'off');
      input.setAttribute('placeholder', 'дд.мм.гггг');

      if (window.jQuery && jQuery.fn.datepicker) {
        jQuery(input).datepicker({
          format: 'yyyy-mm-dd',
          autoclose: true,
          todayHighlight: true,
          orientation: 'bottom auto'
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
  
  function initHrPagination() {
    document.querySelectorAll(".paginator_handler .page-link").forEach(function (el) {
      el.addEventListener("click", function () {
        const pageInput = document. getElementById("id_page");
        const form = document.getElementById("filter_form");
        if (pageInput) pageInput.value = this.getAttribute("data-page");
        if (form) form.submit();
      });
    });
  } 

  function init() {
    initTableSearch();
    initInlineModals();
    initEmployeeForm();
    initOrgChart();
    initHrDatepickers();
    initHrEmployeesFilters();
    initHrPagination();

    if (window.BPM && window.BPM.applyTranslations) {
      window.BPM.applyTranslations();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
