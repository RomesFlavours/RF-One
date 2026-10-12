/* MyRF Project Management v1 — Plan dialogs and Gantt view
   (`01 Domains/Business Domain/Restaurant/MyRF/Project Management/README.md`).

   Plan: fills the chapter / task dialogs opened through the shared modal
   controller (`rf-one-modal.js`) and reopens a dialog the server refused,
   with the values entered and the reason (`#pm-dialog-state`). The rules
   themselves are checked on the server; here a task is only kept from
   choosing itself as parent or prerequisite, and a task with children from
   becoming a child (one level).

   Gantt: collapse / expand of Chapters and parent Tasks — a screen-only
   view, the print always shows every row — and the Print button. */

(function () {
  "use strict";

  function one(selector, root) { return (root || document).querySelector(selector); }
  function all(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function todayIso() {
    var d = new Date();
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function readJson(text) {
    try { return JSON.parse(text); } catch (e) { return null; }
  }

  function dialogState() {
    var node = document.getElementById("pm-dialog-state");
    return node ? readJson(node.textContent) : null;
  }

  // ------------------------------------------------------------------ Project (list and plan)

  function initProjectDialog() {
    var overlay = document.getElementById("pm-project-dialog");
    if (!overlay || !window.RFOneModal) { return; }
    var modal = window.RFOneModal.create({ overlay: overlay, initialFocus: function () { return one("#pm-project-name"); } });
    var form = one("[data-pm-form]", overlay);

    function open(values, id, trigger, error) {
      form.action = id
        ? form.getAttribute("data-pm-update-action").replace(/\/0\/rename$/, "/" + id + "/rename")
        : form.getAttribute("data-pm-create-action");
      one("[data-pm-dialog-title]", overlay).textContent = id ? "Rename project" : "New project";
      one("#pm-project-name").value = values.name || "";
      var box = one("[data-pm-error]", overlay);
      box.textContent = error || "";
      box.hidden = !error;
      modal.open(trigger);
    }

    document.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button) { return; }
      if (button.hasAttribute("data-pm-new-project")) {
        open({}, null, button);
      } else if (button.hasAttribute("data-pm-rename-project")) {
        var project = readJson(button.getAttribute("data-pm-rename-project")) || {};
        open(project, project.id, button);
      }
    });

    var state = dialogState();
    if (state && state.kind === "project") { open(state.values || {}, state.id, null, state.error); }
  }

  function initConfirmations() {
    all("form[data-pm-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-pm-confirm"))) { event.preventDefault(); }
      });
    });
  }

  // ------------------------------------------------------------------ Plan

  function initPlan() {
    var chapterOverlay = document.getElementById("pm-chapter-dialog");
    var taskOverlay = document.getElementById("pm-task-dialog");
    if (!chapterOverlay || !taskOverlay || !window.RFOneModal) { return; }

    var chapterModal = window.RFOneModal.create({
      overlay: chapterOverlay, initialFocus: function () { return one("#pm-chapter-title"); },
    });
    var taskModal = window.RFOneModal.create({
      overlay: taskOverlay, initialFocus: function () { return one("#pm-task-title"); },
    });

    function setAction(overlay, id) {
      var form = one("[data-pm-form]", overlay);
      form.action = id
        ? form.getAttribute("data-pm-update-action").replace(/\/0$/, "/" + id)
        : form.getAttribute("data-pm-create-action");
    }

    function showError(overlay, message) {
      var box = one("[data-pm-error]", overlay);
      box.textContent = message || "";
      box.hidden = !message;
    }

    function setTitle(overlay, text) { one("[data-pm-dialog-title]", overlay).textContent = text; }

    // --- chapter
    function openChapter(values, id, trigger, error) {
      setAction(chapterOverlay, id);
      setTitle(chapterOverlay, id ? "Edit chapter" : "New chapter");
      one("#pm-chapter-title").value = values.title || "";
      one("#pm-chapter-description").value = values.description || "";
      showError(chapterOverlay, error);
      chapterModal.open(trigger);
    }

    // --- task
    var parentSelect = one("#pm-task-parent");
    var chapterSelect = one("#pm-task-chapter");
    var startInput = one("#pm-task-start");
    var daysInput = one("#pm-task-days");
    var filterInput = one("[data-pm-pred-filter]");
    var currentTaskId = null;
    var currentHasChildren = false;

    function syncParentChapter() {
      var isChild = parentSelect.value !== "";
      one("[data-pm-chapter-field]").hidden = isChild;
      one("[data-pm-chapter-note]").hidden = !isChild;
      if (isChild) {
        var option = parentSelect.options[parentSelect.selectedIndex];
        if (option) { chapterSelect.value = option.getAttribute("data-chapter"); }
      }
    }

    function configureChoices() {
      var self = currentTaskId === null ? null : String(currentTaskId);
      all("option", parentSelect).forEach(function (option) {
        if (option.value) { option.disabled = option.value === self; }
      });
      // One level: a task with children stays a chapter task. A disabled
      // select is not submitted, so the task keeps no parent.
      parentSelect.disabled = currentHasChildren;
      one("[data-pm-parent-note]").hidden = !currentHasChildren;
      all("[data-pm-pred-option]").forEach(function (label) {
        var isSelf = label.getAttribute("data-pm-pred-option") === self;
        label.hidden = isSelf;
        label.querySelector("input").disabled = isSelf;
      });
    }

    function filterPredecessors() {
      var needle = filterInput ? filterInput.value.trim().toLowerCase() : "";
      var self = currentTaskId === null ? null : String(currentTaskId);
      all("[data-pm-pred-option]").forEach(function (label) {
        var isSelf = label.getAttribute("data-pm-pred-option") === self;
        var matches = !needle || label.textContent.toLowerCase().indexOf(needle) !== -1
          || label.querySelector("input").checked;
        label.hidden = isSelf || !matches;
      });
    }

    function updateEndPreview() {
      var out = one("[data-pm-end-preview]");
      var days = parseInt(daysInput.value, 10);
      var parts = (startInput.value || "").split("-");
      if (parts.length !== 3 || !(days >= 1)) { out.textContent = ""; return; }
      var end = new Date(Date.UTC(+parts[0], +parts[1] - 1, +parts[2] + days - 1));
      out.textContent = "Planned end date: " + pad(end.getUTCDate()) + "/" + pad(end.getUTCMonth() + 1) + "/"
        + end.getUTCFullYear() + " (start + " + days + " − 1, calendar days)";
    }

    function hasChildren(id) {
      var button = one('[data-rr-key="task:' + id + '"] [data-pm-edit-task]');
      var payload = button ? readJson(button.getAttribute("data-pm-edit-task")) : null;
      return !!(payload && payload.has_children);
    }

    function openTask(values, id, trigger, error) {
      currentTaskId = id || null;
      currentHasChildren = id ? (values.has_children !== undefined ? !!values.has_children : hasChildren(id)) : false;
      setAction(taskOverlay, id);
      setTitle(taskOverlay, id ? "Edit task" : (values.parent_task_id ? "New subtask" : "New task"));

      one("#pm-task-title").value = values.title || "";
      one("#pm-task-description").value = values.description || "";
      parentSelect.value = values.parent_task_id ? String(values.parent_task_id) : "";
      if (values.chapter_id) { chapterSelect.value = String(values.chapter_id); }
      else if (chapterSelect.options.length) { chapterSelect.selectedIndex = 0; }
      startInput.value = values.planned_start_date || todayIso();
      daysInput.value = values.planned_duration_days !== undefined && values.planned_duration_days !== null
        ? values.planned_duration_days : 1;
      var actual = values.actual_duration_days;
      one("#pm-task-actual").value = actual === undefined || actual === null ? "" : actual;
      var percent = values.percent_complete;
      one("#pm-task-percent").value = percent === undefined || percent === null || percent === "" ? 0 : percent;

      var chosen = (values.predecessor_ids || []).map(String);
      all('input[name="predecessor_ids"]', taskOverlay).forEach(function (box) {
        box.checked = chosen.indexOf(box.value) !== -1;
      });
      if (filterInput) { filterInput.value = ""; }

      configureChoices();
      filterPredecessors();
      syncParentChapter();
      updateEndPreview();
      showError(taskOverlay, error);
      taskModal.open(trigger);
    }

    parentSelect.addEventListener("change", syncParentChapter);
    startInput.addEventListener("input", updateEndPreview);
    daysInput.addEventListener("input", updateEndPreview);
    if (filterInput) { filterInput.addEventListener("input", filterPredecessors); }

    document.addEventListener("click", function (event) {
      var button = event.target.closest("button");
      if (!button) { return; }
      if (button.hasAttribute("data-pm-new-chapter")) {
        openChapter({}, null, button);
      } else if (button.hasAttribute("data-pm-edit-chapter")) {
        var chapter = readJson(button.getAttribute("data-pm-edit-chapter")) || {};
        openChapter(chapter, chapter.id, button);
      } else if (button.hasAttribute("data-pm-new-task")) {
        openTask({}, null, button);
      } else if (button.hasAttribute("data-pm-new-task-in")) {
        openTask({ chapter_id: button.getAttribute("data-pm-new-task-in") }, null, button);
      } else if (button.hasAttribute("data-pm-new-child")) {
        openTask({
          parent_task_id: button.getAttribute("data-pm-new-child"),
          chapter_id: button.getAttribute("data-pm-chapter"),
        }, null, button);
      } else if (button.hasAttribute("data-pm-edit-task")) {
        var task = readJson(button.getAttribute("data-pm-edit-task")) || {};
        openTask(task, task.id, button);
      }
    });

    // A refusal from the server: the same dialog, the values entered, the reason.
    var state = dialogState();
    if (state) {
      if (state.kind === "chapter") { openChapter(state.values || {}, state.id, null, state.error); }
      else if (state.kind === "task") { openTask(state.values || {}, state.id, null, state.error); }
    }
  }

  // ------------------------------------------------------------------ Gantt

  function initGantt() {
    var table = one(".pm-gantt");
    if (!table) { return; }
    var collapsed = {};
    var rows = all("tr[data-gantt-node]", table);
    var toggles = all("[data-gantt-toggle]", table);

    function apply() {
      rows.forEach(function (row) {
        var ancestors = (row.getAttribute("data-gantt-ancestors") || "").split(" ").filter(Boolean);
        row.classList.toggle("pm-collapsed", ancestors.some(function (key) { return collapsed[key]; }));
      });
      toggles.forEach(function (button) {
        var isCollapsed = !!collapsed[button.getAttribute("data-gantt-toggle")];
        button.textContent = isCollapsed ? "▸" : "▾";
        button.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      });
    }

    table.addEventListener("click", function (event) {
      var button = event.target.closest("[data-gantt-toggle]");
      if (!button) { return; }
      var key = button.getAttribute("data-gantt-toggle");
      collapsed[key] = !collapsed[key];
      apply();
    });

    var expandAll = one("[data-gantt-expand-all]");
    var collapseAll = one("[data-gantt-collapse-all]");
    var print = one("[data-gantt-print]");
    if (expandAll) { expandAll.addEventListener("click", function () { collapsed = {}; apply(); }); }
    if (collapseAll) {
      collapseAll.addEventListener("click", function () {
        toggles.forEach(function (button) { collapsed[button.getAttribute("data-gantt-toggle")] = true; });
        apply();
      });
    }
    // Collapsed rows are hidden by a screen-only rule: the print has them all.
    if (print) { print.addEventListener("click", function () { window.print(); }); }
  }

  initConfirmations();
  initProjectDialog();
  initPlan();
  initGantt();
})();
