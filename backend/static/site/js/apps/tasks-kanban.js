(function () {
  "use strict";
  function getCsrf() {
    var tag = document.querySelector("[name=csrfmiddlewaretoken]");
    if (tag) return tag.value;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : "";
  }
  var page = document.getElementById("tasksKanbanPage");
  if (!page) return;
  var board = document.getElementById("tasksKanbanBoard");
  var apiUrl = page.dataset.kanbanApi;
  var statusUrlTpl = page.dataset.statusUrlTpl || "/tasks/api/kanban/0/status/";
  var i18n = {
    loading: page.dataset.i18nLoading || "Загрузка…",
    noColumns: page.dataset.i18nNoColumns || "Нет колонок статусов",
    loadError: page.dataset.i18nLoadError || "Не удалось загрузить канбан",
    noTasksHint: page.dataset.i18nNoTasksHint || "Задач пока нет.",
    noExecutor: page.dataset.i18nNoExecutor || "Без исполнителя",
    executorCol: page.dataset.i18nExecutorCol || "Исполнитель",
    moveConfirmMsg: page.dataset.i18nMoveConfirmMsg || "Перевести задачу в статус «{title}»?",
    moveConfirmTitle: page.dataset.i18nMoveConfirmTitle || "Смена статуса",
    moveConfirmText: page.dataset.i18nMoveConfirmText || "Подтвердить",
    statusError: page.dataset.i18nStatusError || "Не удалось сменить статус",
    networkError: page.dataset.i18nNetworkError || "Ошибка сети при смене статуса",
    errorTitle: page.dataset.i18nErrorTitle || "Ошибка",
    priorityLow: page.dataset.i18nPriorityLow || "Низкий",
    priorityMedium: page.dataset.i18nPriorityMedium || "Средний",
    priorityHigh: page.dataset.i18nPriorityHigh || "Высокий",
    priorityCritical: page.dataset.i18nPriorityCritical || "Критический",
  };
  var PRIORITY = {
    low: { label: i18n.priorityLow, cls: "low" },
    medium: { label: i18n.priorityMedium, cls: "medium" },
    high: { label: i18n.priorityHigh, cls: "high" },
    critical: { label: i18n.priorityCritical, cls: "critical" },
  };
  var dragTaskId = null, dragFromStatus = null, moveInFlight = false;
  function formatDeadline(iso) {
    if (!iso) return "";
    var p = iso.split("-");
    return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] : iso;
  }
  function esc(t) { var d = document.createElement("div"); d.textContent = t || ""; return d.innerHTML; }
  function statusUrl(id) { return statusUrlTpl.replace("/0/", "/" + id + "/"); }
  function buildSwimlaneData(data) {
    var columns = data.columns || [];
    var statuses = columns.map(function(c) { return { status: c.status, title: c.title, color: c.color || "neutral" }; });
    var rowsMap = {};
    columns.forEach(function(col) {
      (col.tasks || []).forEach(function(task) {
        var key = task.executor_id ? String(task.executor_id) : "_none";
        if (!rowsMap[key]) rowsMap[key] = { executor_id: task.executor_id, executor: task.executor || i18n.noExecutor, byStatus: {} };
        if (!rowsMap[key].byStatus[col.status]) rowsMap[key].byStatus[col.status] = [];
        rowsMap[key].byStatus[col.status].push(task);
      });
    });
    var rows = Object.keys(rowsMap).map(function(k) { return rowsMap[k]; }).sort(function(a, b) { return (a.executor || "").localeCompare(b.executor || "", "ru"); });
    return { statuses: statuses, rows: rows };
  }
  function cardHtml(task) {
    var prio = PRIORITY[task.priority];
    var init = task.executor ? esc(task.executor.charAt(0).toUpperCase()) : "";
    var pl = prio ? prio.label : (task.priority_title || "");
    return "<a class=\"tasks-kanban__card tasks-kanban__card--" + (task.status_color || "neutral") + "\" href=\"" + esc(task.url) + "\" draggable=\"true\" data-task-id=\"" + task.id + "\" data-status=\"" + esc(task.status || "") + "\">" +
      "<div class=\"tasks-kanban__card-head\"><span class=\"tasks-kanban__card-num\">" + esc(task.number || ("#" + task.id)) + "</span>" + (task.type ? "<span class=\"tasks-kanban__card-type\">" + esc(task.type) + "</span>" : "") + "</div>" +
      "<div class=\"tasks-kanban__card-top\"><div class=\"tasks-kanban__card-title\">" + esc(task.title) + "</div></div>" +
      (prio ? "<div class=\"tasks-kanban__card-prio\"><span class=\"tasks-kanban__prio tasks-kanban__prio--" + prio.cls + "\"></span>" + esc(pl) + "</div>" : "") +
      "<div class=\"tasks-kanban__card-meta\">" + (task.executor ? "<span class=\"tasks-kanban__assignee\"><span class=\"tasks-kanban__assignee-avatar\">" + init + "</span>" + esc(task.executor) + "</span>" : "") + (task.deadline ? "<span class=\"tasks-kanban__deadline\"><i class=\"bi bi-calendar3\"></i>" + formatDeadline(task.deadline) + "</span>" : "") + "</div></a>";
  }
  function renderBoard(data) {
    var swim = buildSwimlaneData(data); var statuses = swim.statuses; var rows = swim.rows;
    board.__statuses = statuses;
    if (!statuses.length) { board.innerHTML = "<div class=\"tasks-kanban__error\">" + esc(i18n.noColumns) + "</div>"; return; }
    var cw = board.offsetWidth || 1000; var ew = 130; var sw = Math.floor((cw - ew) / statuses.length);
    var gc = ew + "px repeat(" + statuses.length + ", " + sw + "px)";
    var html = "<div class=\"tasks-kanban-swim\" style=\"--kanban-cols:" + statuses.length + "\">";
    html += "<div class=\"tasks-kanban-swim__head\" style=\"grid-template-columns:" + gc + "\">";
    html += "<div class=\"tasks-kanban-swim__head-cell tasks-kanban-swim__head-cell--corner\">" + esc(i18n.executorCol) + "</div>";
    statuses.forEach(function(st) { html += "<div class=\"tasks-kanban-swim__head-cell\"><span class=\"tasks-kanban__dot tasks-status--" + st.color + "\"></span>" + esc(st.title) + "</div>"; });
    html += "</div>";
    if (!rows.length) { html += "<div class=\"tasks-kanban-swim__empty\">" + esc(i18n.noTasksHint) + "</div>"; }
    else { rows.forEach(function(row) {
      html += "<div class=\"tasks-kanban-swim__lane\" style=\"grid-template-columns:" + gc + "\">";
      html += "<div class=\"tasks-kanban-swim__lane-user\"><span class=\"tasks-kanban__assignee-avatar\">" + esc((row.executor || "?").charAt(0).toUpperCase()) + "</span><span class=\"tasks-kanban-swim__lane-name\">" + esc(row.executor) + "</span></div>";
      statuses.forEach(function(st) {
        html += "<div class=\"tasks-kanban-swim__cell\" data-drop-zone data-status=\"" + st.status + "\">";
        (row.byStatus[st.status] || []).forEach(function(t) { html += cardHtml(t); });
        html += "</div>";
      });
      html += "</div>";
    }); }
    html += "</div>";
    board.innerHTML = html;
    board.querySelectorAll("[data-drop-zone]").forEach(function(z) {
      z.addEventListener("dragover", function(e) { e.preventDefault(); z.classList.add("is-drag-over"); });
      z.addEventListener("dragleave", function() { z.classList.remove("is-drag-over"); });
      z.addEventListener("drop", function(e) { e.preventDefault(); z.classList.remove("is-drag-over"); if (!dragTaskId || moveInFlight) return; var ns = z.getAttribute("data-status"); if (ns === dragFromStatus) { dragTaskId = null; return; } confirmMove(dragTaskId, ns, dragFromStatus); });
    });
    board.querySelectorAll(".tasks-kanban__card").forEach(function(c) {
      c.addEventListener("dragstart", function() { dragTaskId = c.getAttribute("data-task-id"); dragFromStatus = c.getAttribute("data-status"); c.classList.add("is-dragging"); });
      c.addEventListener("dragend", function() { c.classList.remove("is-dragging"); if (!moveInFlight) { dragTaskId = null; dragFromStatus = null; } });
      c.addEventListener("click", function(e) { if (c.classList.contains("is-dragging")) e.preventDefault(); });
    });
  }
  function stTitle(s) { var m = {}; (board.__statuses || []).forEach(function(x) { m[x.status] = x.title; }); return m[s] || s; }
  async function confirmMove(tid, ns, fs) {
    var msg = i18n.moveConfirmMsg.replace("{title}", stTitle(ns));
    var ok = window.bpmModal ? await window.bpmModal.confirm(msg, { title: i18n.moveConfirmTitle, confirmText: i18n.moveConfirmText, variant: "info" }) : window.confirm(msg);
    if (!ok) { dragTaskId = null; dragFromStatus = null; return; }
    moveTask(tid, ns, fs);
  }
  function showErr(m) { if (window.bpmModal) window.bpmModal.alert(m, { variant: "danger", title: i18n.errorTitle }); else alert(m); }
  async function loadBoard() { var r = await fetch(apiUrl, { credentials: "same-origin" }); if (!r.ok) throw new Error("fail"); renderBoard(await r.json()); }
  async function moveTask(tid, ns, fs) {
    if (moveInFlight) return;
    if (fs && fs === ns) { dragTaskId = null; dragFromStatus = null; return; }
    moveInFlight = true;
    try {
      var r = await fetch(statusUrl(tid), { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf(), "X-Requested-With": "XMLHttpRequest" }, credentials: "same-origin", body: JSON.stringify({ status: ns }) });
      var d = {}; try { d = await r.json(); } catch(e) { if (r.ok) { await loadBoard(); return; } throw e; }
      if (!r.ok || d.ok === false) { showErr(d.message || i18n.statusError); await loadBoard(); return; }
      if (d.kanban) renderBoard(d.kanban); else await loadBoard();
    } catch(e) { console.error(e); showErr(i18n.networkError); try { await loadBoard(); } catch(x) { console.error(x); } }
    finally { moveInFlight = false; dragTaskId = null; dragFromStatus = null; }
  }
  loadBoard().catch(function() { board.innerHTML = "<div class=\"tasks-kanban__error\">" + esc(i18n.loadError) + "</div>"; });
})();
