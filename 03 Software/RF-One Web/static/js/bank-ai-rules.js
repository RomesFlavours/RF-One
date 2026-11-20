/* Bank > AI Rules page (BANK_AI_RULES_002 … 006): the list of rules, drafts and movements around the AI Rule
   editor. The editor itself — the window, Preview, Save, Apply — is static/js/bank-ai-rule-editor.js
   (window.BankAIRuleEditor), the same one Completa uses.

   The selection of movements is a set of precise ids, kept across period
   changes (this browser tab); a period change never adds any. */

// "Search transactions" keeps the page where it was: the search reloads the
// page (GET, so the text and the filters stay in the URL), and the field comes
// back at the same height on the screen, with the focus — with or without
// results, search after search. Recorded for this tab only, used once, by the
// next load of this page within a minute; any other opening is left alone.
(function () {
  "use strict";

  var STORE = "rfone-ai-txn-search-position";
  var MAX_AGE_MS = 60000;
  var searchForm = document.querySelector(".ai-txn-search");
  var field = document.getElementById("ai-txn-search");
  if (!searchForm || !field) { return; }

  function storage() { try { return window.sessionStorage; } catch (e) { return null; } }

  searchForm.addEventListener("submit", function () {
    var store = storage();
    if (!store) { return; }
    try {
      store.setItem(STORE, JSON.stringify({ path: window.location.pathname, top: field.getBoundingClientRect().top,
                                            at: Date.now() }));
    } catch (e) { /* storage full or blocked: the page simply opens at the top */ }
  });

  var store = storage();
  var saved = null;
  try { saved = store && JSON.parse(store.getItem(STORE) || "null"); } catch (e) { saved = null; }
  if (store) { try { store.removeItem(STORE); } catch (e) { /* nothing to clean */ } }
  if (!saved || saved.path !== window.location.pathname || Date.now() - saved.at > MAX_AGE_MS) { return; }

  function place() { window.scrollBy(0, field.getBoundingClientRect().top - saved.top); }
  place();
  try { field.focus({ preventScroll: true }); } catch (e) { /* older browsers: focus without it */ }
  // Late layout (fonts, images) can move the field: place it again once everything is loaded.
  if (document.readyState === "complete") { place(); } else { window.addEventListener("load", place); }
})();

(function () {
  "use strict";

  var editor = window.BankAIRuleEditor;
  if (!editor) { return; }

  // --- Selection of movements (BANK_AI_RULES_006) -------------------------
  var STORE = "rfone.bank.aiRules.selection";
  var selection = loadSelection();
  var rowBoxes = Array.prototype.slice.call(document.querySelectorAll(".ai-rule-select"));
  var periodBox = document.getElementById("ai-select-period");
  editor.setSelection(function () { return Array.from(selection); });

  // BANK_AI_RULES_019 — with a "Classification" filter, the movements of the
  // period it excludes leave the selection (also those an application just
  // made no longer match); changing the filter reloads the list, with a spinner.
  (function applyClassificationFilter() {
    var bar = document.getElementById("ai-selection-bar");
    if (!bar || (bar.getAttribute("data-cls") || "all") === "all") { return; }
    var excluded = [];
    try { excluded = JSON.parse(bar.getAttribute("data-excluded-ids") || "[]"); } catch (e) { excluded = []; }
    var changed = false;
    excluded.forEach(function (id) { if (selection.delete(String(id))) { changed = true; } });
    if (changed) { try { window.sessionStorage.setItem(STORE, JSON.stringify(Array.from(selection))); } catch (e) { /* ignore */ } }
  })();
  // BANK_AI_RULES_025 — with a movements' search, the selection is limited to
  // its results (period, Classification and search, as listed): the others
  // leave it for good — emptying or changing the search never brings them back.
  (function applySearchPerimeter() {
    var search = document.querySelector(".ai-txn-search[data-search-active='1']");
    if (!search) { return; }
    var inPerimeter = new Set(rowBoxes.map(function (box) { return box.value; }));
    var changed = false;
    Array.from(selection).forEach(function (id) {
      if (!inPerimeter.has(String(id))) { selection.delete(id); changed = true; }
    });
    if (changed) { saveSelection(); }
  })();
  (function filterLoading() {
    var periodForm = document.getElementById("ai-rules-period");
    var cls = document.getElementById("ai-rules-cls");
    var loading = document.getElementById("ai-rules-loading");
    if (!periodForm) { return; }
    periodForm.addEventListener("submit", function () { if (loading) { loading.hidden = false; } });
    if (cls) {
      cls.addEventListener("change", function () {
        if (loading) { loading.hidden = false; }
        if (periodForm.requestSubmit) { periodForm.requestSubmit(); } else { periodForm.submit(); }
      });
    }
  })();

  function loadSelection() {
    try {
      var raw = window.sessionStorage.getItem(STORE);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch (e) { return new Set(); }
  }

  function saveSelection() {
    try { window.sessionStorage.setItem(STORE, JSON.stringify(Array.from(selection))); } catch (e) { /* ignore */ }
  }

  // The page's counts; then the editor's scope count and its Preview, which a change of the selection supersedes.
  function refreshSelection() {
    var visible = 0;
    rowBoxes.forEach(function (box) {
      box.checked = selection.has(box.value);
      if (box.checked) { visible += 1; }
    });
    var count = selection.size;
    var countEl = document.getElementById("ai-selection-count");
    if (countEl) { countEl.textContent = count; }
    var visibleEl = document.getElementById("ai-selection-visible");
    if (visibleEl) { visibleEl.textContent = visible; }
    var outsideEl = document.getElementById("ai-selection-outside");
    if (outsideEl) { outsideEl.textContent = count - visible; }
    if (periodBox) { periodBox.checked = rowBoxes.length > 0 && visible === rowBoxes.length; }
    editor.selectionChanged();
  }

  rowBoxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked) { selection.add(box.value); } else { selection.delete(box.value); }
      saveSelection();
      refreshSelection();
    });
  });
  if (periodBox) {
    periodBox.addEventListener("change", function () {
      rowBoxes.forEach(function (box) {
        if (periodBox.checked) { selection.add(box.value); } else { selection.delete(box.value); }
      });
      saveSelection();
      refreshSelection();
    });
  }
  var clearButton = document.getElementById("ai-selection-clear");
  if (clearButton) {
    clearButton.addEventListener("click", function () {
      selection.clear();
      saveSelection();
      refreshSelection();
    });
  }
  refreshSelection();

  // BANK_AI_RULES_020 — with a "Classification" filter, the selected movements
  // of OTHER periods are checked on the server too: those that do not satisfy
  // the filter leave the selection; the compatible ones stay.
  (function checkOtherPeriods() {
    var bar = document.getElementById("ai-selection-bar");
    var cls = bar ? (bar.getAttribute("data-cls") || "all") : "all";
    if (!bar || cls === "all") { return; }
    var shown = new Set(rowBoxes.map(function (box) { return box.value; }));
    var outside = Array.from(selection).filter(function (id) { return !shown.has(String(id)); });
    if (!outside.length) { return; }
    var checking = document.getElementById("ai-selection-checking");
    if (checking) { checking.hidden = false; }
    var body = new FormData();
    body.append("csrf_token", bar.getAttribute("data-csrf"));
    body.append("cls", cls);
    body.append("ids", outside.join(","));
    fetch(bar.getAttribute("data-check-url"), { method: "POST", body: body, credentials: "same-origin",
                                               headers: { "X-Requested-With": "fetch" } })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data || !data.ok) { return; }
        var keep = new Set(data.matching);
        outside.forEach(function (id) { if (!keep.has(String(id))) { selection.delete(id); } });
        saveSelection();
        refreshSelection();
      })
      .catch(function () { /* the selection is left as it was; nothing is applied from here */ })
      .then(function () { if (checking) { checking.hidden = true; } });
  })();

  // BANK_AI_RULES_009 — the outcome of a save that closed the editor, shown above the list of rules.
  var FLASH = "rfone.bank.aiRules.saved";
  (function showSaved() {
    var raw = null;
    try { raw = window.sessionStorage.getItem(FLASH); window.sessionStorage.removeItem(FLASH); } catch (e) { raw = null; }
    if (!raw) { return; }
    var saved = JSON.parse(raw);
    var section = document.getElementById("ai-operative-rules");
    if (!section) { return; }
    var note = document.createElement("div");
    note.className = "ai-rule-applied";
    note.setAttribute("role", "status");
    note.id = "ai-rule-saved-flash";
    note.textContent = saved.message;
    section.insertBefore(note, section.children[1] || null);
    var row = section.querySelector("tr[data-rule-id='" + saved.rule_id + "']");
    if (row) { row.classList.add("ai-rule-just-saved"); row.scrollIntoView({ block: "center" }); }
  })();

  // BANK_AI_RULES_014 — Delete asks for confirmation, naming the rule.
  document.addEventListener("submit", function (event) {
    var form = event.target.closest && event.target.closest(".ai-rule-delete-form");
    if (!form) { return; }
    var message = "Delete the AI rule " + form.getAttribute("data-rule-name") + "?\n\n" +
      "It will no longer be executed. The classifications it already applied to the movements are NOT changed " +
      "and their origin stays recorded.";
    if (!window.confirm(message)) { event.preventDefault(); }
  });

  // The list's buttons open the editor: a new rule from a movement, a draft, an operative rule.
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".ai-rule-open");
    if (button) { editor.openNew(JSON.parse(button.getAttribute("data-transaction"))); return; }
    var draftOpen = event.target.closest && event.target.closest(".ai-rule-draft-open");
    if (draftOpen) { editor.openDraft(draftOpen.getAttribute("data-draft-id")); return; }
    var ruleOpen = event.target.closest && event.target.closest(".ai-rule-operative-open");
    if (ruleOpen) { editor.openRule(ruleOpen.getAttribute("data-rule-id")); }
  });
})();
