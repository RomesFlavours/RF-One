/* Bank > AI Rules window (BANK_AI_RULES_002 … 006).

   Opened from a movement's "AI Rules" button (the movement is the rule's
   example), from a saved draft, or from an operative rule. Preview posts the
   rule and its scope — the period shown, "All existing transactions" or
   "Only the selected transactions" — and shows the matches, the doubtful
   cases and what applying would do to each (updated, unchanged, protected,
   conflict, unresolved). Any change of the text, the options, the scope or
   the selection marks that preview Superseded.

   Save Draft keeps the rule only. Save makes it operative without touching
   existing movements ("Apply automatically to transactions imported from now
   on" enables it for new imports). Save and Apply — disabled while no scope is chosen — applies it on the strength of
   a current preview of the same text and scope: when there is none, it runs
   the preview first, says why, and the next press applies that preview.
   When the server refuses a preview, its precise reason is shown.

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

  var overlay = document.getElementById("ai-rule-modal");
  if (!overlay || !window.RFOneModal) { return; }

  var form = document.getElementById("ai-rule-form");
  var text = document.getElementById("ai-rule-text");
  var userTitle = document.getElementById("ai-rule-user-title");
  var rewriteButton = document.getElementById("ai-rule-rewrite");
  var undoRewriteButton = document.getElementById("ai-rule-rewrite-undo");
  var rewriteStatus = document.getElementById("ai-rule-rewrite-status");
  var conflictsBox = document.getElementById("ai-rule-conflicts");
  var previewedConflicts = [];  // the conflicts with other active rules found by the current Preview
  var beforeRewrite = null;  // BANK_AI_RULES_026 — the text Undo rewrite restores
  var validatedText = null;  // the text "Rewritten and validated" refers to
  var saveTitleButton = document.getElementById("ai-rule-save-title");
  var createMissing = document.getElementById("ai-rule-create-missing");
  var applicationMode = document.getElementById("ai-rule-application-mode");
  var overrideProtected = document.getElementById("ai-rule-override-protected");
  // Radio pairs: each option is the "on" radio of its group, the alternative is the other one.
  var onlyUnsettled = document.getElementById("ai-rule-only-unsettled");
  var includeAiSettled = document.getElementById("ai-rule-include-ai-settled");
  var whoOnly = document.getElementById("ai-rule-who-only");
  var allParts = document.getElementById("ai-rule-all-parts");
  var originId = document.getElementById("ai-rule-origin-id");
  var draftId = document.getElementById("ai-rule-draft-id");
  var ruleId = document.getElementById("ai-rule-rule-id");
  var previewIdInput = document.getElementById("ai-rule-preview-id");
  var selectedInput = document.getElementById("ai-rule-selected-ids");
  var scopeNone = document.getElementById("ai-scope-none");
  var scopeAll = document.getElementById("ai-scope-all");
  var scopeSelected = document.getElementById("ai-scope-selected");
  var scopeFuture = document.getElementById("ai-scope-future");
  var scopeNote = document.getElementById("ai-rule-scope-note");
  var previewButton = document.getElementById("ai-rule-preview-button");
  var draftButton = document.getElementById("ai-rule-save-draft");
  var saveButton = document.getElementById("ai-rule-save");
  var saveApplyButton = document.getElementById("ai-rule-save-apply");
  var draftStatus = document.getElementById("ai-rule-draft-status");
  var operativeBadge = document.getElementById("ai-rule-operative-badge");
  var wait = document.getElementById("ai-rule-wait");
  var waitText = document.getElementById("ai-rule-wait-text");
  var errorBox = document.getElementById("ai-rule-error");
  var appliedBox = document.getElementById("ai-rule-applied");
  var result = document.getElementById("ai-rule-result");
  var stale = document.getElementById("ai-rule-stale");
  var interpretation = document.getElementById("ai-rule-interpretation");
  var newWhoBox = document.getElementById("ai-rule-new-who");
  var newWhoCount = document.getElementById("ai-rule-new-who-count");
  var createWhoButton = document.getElementById("ai-rule-create-who");
  var createWhoResult = document.getElementById("ai-rule-create-who-result");
  var batchSize = parseInt(overlay.getAttribute("data-batch-size"), 10) || 40;
  var periodCount = parseInt(overlay.getAttribute("data-period-count"), 10) || 0;
  var previewed = null;      // the last valid preview: {id, text, createMissing, scope, newWho}
  var busy = false;
  var loaded = null;         // BANK_AI_RULES_022 — the operative rule as opened: {title, text, options}

  var modal = window.RFOneModal.create({ overlay: overlay, initialFocus: function () { return text; } });

  // --- Selection of movements (BANK_AI_RULES_006) -------------------------
  var STORE = "rfone.bank.aiRules.selection";
  var selection = loadSelection();
  var rowBoxes = Array.prototype.slice.call(document.querySelectorAll(".ai-rule-select"));
  var periodBox = document.getElementById("ai-select-period");

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

  function selectedIds() {
    return Array.from(selection).map(Number).filter(function (n) { return n > 0; }).sort(function (a, b) { return a - b; });
  }

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
    document.getElementById("ai-scope-selected-count").textContent = count + " selected";
  }

  rowBoxes.forEach(function (box) {
    box.addEventListener("change", function () {
      if (box.checked) { selection.add(box.value); } else { selection.delete(box.value); }
      saveSelection();
      refreshSelection();
      markStale();
    });
  });
  if (periodBox) {
    periodBox.addEventListener("change", function () {
      rowBoxes.forEach(function (box) {
        if (periodBox.checked) { selection.add(box.value); } else { selection.delete(box.value); }
      });
      saveSelection();
      refreshSelection();
      markStale();
    });
  }
  var clearButton = document.getElementById("ai-selection-clear");
  if (clearButton) {
    clearButton.addEventListener("click", function () {
      selection.clear();
      saveSelection();
      refreshSelection();
      markStale();
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
        markStale();
      })
      .catch(function () { /* the selection is left as it was; nothing is applied from here */ })
      .then(function () { if (checking) { checking.hidden = true; } });
  })();

  // --- Scope -----------------------------------------------------------
  function scopeSignature() {
    if (scopeAll.checked) { return "ALL"; }
    if (scopeSelected.checked) { return "SELECTED:" + selectedIds().join(","); }
    return "PERIOD";
  }

  function describeScope() {
    var parts = [];
    if (scopeAll.checked) { parts.push("Preview and apply: every movement in the database."); }
    else if (scopeSelected.checked) { parts.push("Preview and apply: the " + selection.size + " selected movement(s)."); }
    else { parts.push("Preview: the " + periodCount + " movement(s) of the period shown (nothing is applied to them)."); }
    if (scopeFuture.checked) { parts.push("New transactions: applied automatically to imports, from Save on."); }
    scopeNote.textContent = parts.join(" ");
    saveApplyButton.disabled = busy || !(scopeAll.checked || scopeSelected.checked || scopeFuture.checked);
  }

  // One radio group: the browser itself unchecks the other choices.
  [scopeNone, scopeAll, scopeSelected].forEach(function (radio) {
    radio.addEventListener("change", function () {
      describeScope();
      markStale();
    });
  });
  scopeFuture.addEventListener("change", describeScope);

  // --- Window ----------------------------------------------------------
  function setText(id, value) { document.getElementById(id).textContent = value || "—"; }

  function showOrigin(t) {
    originId.value = t.id || "";
    setText("ai-rule-origin-description", t.description);
    setText("ai-rule-origin-date", t.date);
    setText("ai-rule-origin-amount", (t.amount || "") + (t.currency ? " " + t.currency : ""));
    setText("ai-rule-origin-source", t.source);
    setText("ai-rule-origin-who", t.who);
    setText("ai-rule-origin-why", t.why);
  }

  // The browser sends a multi-line text with CRLF line ends (form encoding)
  // while the field holds LF: both sides are compared in one form, or a
  // multi-line rule would never match its own preview.
  function ruleText(value) { return (value || "").replace(/\r\n?/g, "\n").trim(); }

  // Why the last preview no longer stands for what the window would apply
  // ("" when it does).
  function staleReason() {
    if (previewed && applicationMode && applicationMode.value !== previewed.applicationMode) { return "application mode changed"; }
    if (previewed === null) { return "there is no Preview of this rule in this window yet"; }
    if (ruleText(text.value) !== previewed.text) { return "the rule text changed after Preview #" + previewed.id; }
    if (createMissing.checked !== previewed.createMissing) {
      return "“Create missing WHO” changed after Preview #" + previewed.id;
    }
    if (whoOnly.checked !== previewed.whoOnly) {
      return "“Which parts of the rule should be applied?” changed after Preview #" + previewed.id;
    }
    if (onlyUnsettled.checked !== previewed.onlyUnsettled) {
      return "“Which AI classifications may be updated?” changed after Preview #" + previewed.id;
    }
    if (overrideProtected.checked !== previewed.overrideProtected) {
      return "“Allow this rule to replace manual or confirmed WHO and WHY” changed after Preview #" + previewed.id;
    }
    if (scopeSignature() !== previewed.scope) {
      var was = previewed.scope.split(":")[0];
      return (was === scopeSignature().split(":")[0] ? "the selected movements changed" : "the scope changed") +
        " after Preview #" + previewed.id;
    }
    return "";
  }

  function isCurrent() { return staleReason() === ""; }

  // BANK_AI_RULES_022 — what makes a version: the Title is not part of it.
  function optionsState() {
    return { title: userTitle.value.trim(), text: ruleText(text.value), createMissing: createMissing.checked,
             overrideProtected: overrideProtected.checked, future: scopeFuture.checked };
  }

  function onlyTitleChanged() {
    if (!loaded || !ruleId.value) { return false; }
    var now = optionsState();
    return now.text === loaded.text && now.createMissing === loaded.createMissing &&
      now.overrideProtected === loaded.overrideProtected && now.future === loaded.future && now.title !== loaded.title;
  }

  function refreshCreateWho() {
    createWhoButton.disabled = busy || !isCurrent() || !previewed.createMissing || !previewed.newWho;
  }

  function reset() {
    previewed = null;
    result.hidden = true;
    result.classList.remove("is-stale");
    stale.hidden = true;
    errorBox.hidden = true;
    appliedBox.hidden = true;
    wait.hidden = true;
    draftStatus.textContent = "";
    newWhoBox.hidden = true;
    createWhoResult.textContent = "";
    beforeRewrite = null;
    validatedText = null;
    undoRewriteButton.hidden = true;
    rewriteStatus.hidden = true;
    conflictsBox.hidden = true;
    previewedConflicts = [];
  }

  // --- Conflicts with the other active rules ------------------------------
  // Found by the server (ai_rules.rule_conflicts) at Rewrite with AI, Preview and Save / Save and Apply. A
  // conflict is about ANOTHER rule, never a problem of this text: shown on its own, never resolved here.
  function conflictLines(list) {
    return (list || []).map(function (c) {
      return c.message + (c.example ? " Example: " + (c.example.date || "") + " · " + c.example.description +
        " · " + c.example.amount + " (" + c.count + " movement(s))." : " No movement shows it yet: the conditions overlap.");
    });
  }

  function showConflicts(list, when) {
    conflictsBox.textContent = "";
    if (!list || !list.length) { conflictsBox.hidden = true; return; }
    var head = document.createElement("h4");
    head.textContent = "Conflict with " + (list.length === 1 ? "another active rule" : list.length + " other active rules") +
      " (" + when + ") — not a problem of this rule's text";
    conflictsBox.appendChild(head);
    list.forEach(function (c) {
      var box = document.createElement("div");
      box.className = "ai-conflict";
      var label = "rule #" + c.rule_id + (c.rule_title ? " ‘" + c.rule_title + "’" : "");
      var lines = [
        ["ai-conflict-message", c.message],
        ["", "Overlapping conditions — this rule: " + c.this.conditions + "; " + label +
              (c.other.branch && c.other.branch.indexOf("branch") === 0 ? " (" + c.other.branch + ")" : "") + ": " +
              c.other.conditions + "."],
        ["", "This rule assigns WHO = " + (c.this.who || "unchanged") + ", WHY = " + (c.this.why || "unchanged") +
              " · " + label + " assigns WHO = " + (c.other.who || "unchanged") + ", WHY = " + (c.other.why || "unchanged") + "."],
        ["", c.example ? "Example movement: " + (c.example.date || "") + " · " + c.example.description + " · " +
              c.example.amount + " — " + c.count + " movement(s) affected." : "No existing movement shows it yet: the conditions overlap."]
      ];
      lines.forEach(function (line) {
        var para = document.createElement("p");
        if (line[0]) { para.className = line[0]; }
        para.textContent = line[1];
        box.appendChild(para);
      });
      conflictsBox.appendChild(box);
    });
    var foot = document.createElement("p");
    foot.textContent = "Where both rules apply, the movements are NOT changed (Conflict). Nothing is resolved " +
      "automatically: change or disable one of the two rules if you decide so.";
    conflictsBox.appendChild(foot);
    conflictsBox.hidden = false;
  }

  // The choices a NEW rule starts with (boxes A–F), as decided by the Product Owner; every one can be changed.
  // A draft or an existing rule reopens with its own saved settings instead.
  var NEW_RULE_DEFAULTS = { scope: "all", future: true, onlyUnsettled: true, override: true, whoOnly: false,
                            createMissing: true };
  // The editable model text a NEW rule starts with (a real value, not a placeholder): the operator replaces the
  // description, WHO and WHY between the empty quotes. Drafts and existing rules keep their own text.
  var NEW_RULE_TEXT = 'If the description contains "", WHO is "" and WHY is "".';

  function openFor(transaction, rule, draft, withCreate, operative, withOverride, withOnlyUnsettled, title, isNew) {
    reset();
    showOrigin(transaction);
    text.value = isNew ? NEW_RULE_TEXT : rule || "";
    userTitle.value = title || "";
    draftId.value = draft || "";
    ruleId.value = operative && operative.rule_id ? operative.rule_id : "";
    createMissing.checked = !!withCreate;
    overrideProtected.checked = !!withOverride;
    var unsettledOnly = withOnlyUnsettled === undefined ? true : !!withOnlyUnsettled;   // default: selected
    onlyUnsettled.checked = unsettledOnly;
    includeAiSettled.checked = !unsettledOnly;
    allParts.checked = true;           // a run mode, never kept with the rule
    scopeNone.checked = true;          // never preselects an application to existing transactions
    scopeFuture.checked = !!(operative && operative.apply_future);
    if (isNew) {
      (NEW_RULE_DEFAULTS.scope === "all" ? scopeAll : NEW_RULE_DEFAULTS.scope === "selected" ? scopeSelected
        : scopeNone).checked = true;
      scopeFuture.checked = NEW_RULE_DEFAULTS.future;
      onlyUnsettled.checked = NEW_RULE_DEFAULTS.onlyUnsettled;
      includeAiSettled.checked = !NEW_RULE_DEFAULTS.onlyUnsettled;
      overrideProtected.checked = NEW_RULE_DEFAULTS.override;
      whoOnly.checked = NEW_RULE_DEFAULTS.whoOnly;
      allParts.checked = !NEW_RULE_DEFAULTS.whoOnly;
      createMissing.checked = NEW_RULE_DEFAULTS.createMissing;
    }
    operativeBadge.hidden = !(operative && operative.rule_id);
    operativeBadge.textContent = operative && operative.rule_id
      ? "Operative rule #" + operative.rule_id + (operative.version_no ? " v" + operative.version_no : "") +
        (operative.status === "INACTIVE" ? " (disabled)" : "") +
        (operative.applied_to_existing === false ? " · saved, not yet applied to existing transactions" : "") : "";
    resetPickers();
    // BANK_AI_RULES_022 — "Save title" only for an operative rule opened as it is (not a draft of a change).
    loaded = operative && operative.rule_id && !draft ? optionsState() : null;
    saveTitleButton.hidden = !loaded;
    previewButton.disabled = !transaction.id;
    draftButton.disabled = !transaction.id && !draft;
    describeScope();
    if (!transaction.id) { showError("The starting transaction is no longer available: this rule can be read but not previewed."); }
    if (applicationMode) { applicationMode.value = "FILL_MISSING"; syncApplicationMode(); }
    modal.open();
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function showApplied(message) {
    appliedBox.textContent = message;
    appliedBox.hidden = false;
  }

  function setBusy(on, message) {
    busy = on;
    wait.hidden = !on;
    if (message) { waitText.textContent = message; }
    previewButton.disabled = on;
    draftButton.disabled = on;
    saveButton.disabled = on;
    saveTitleButton.disabled = on;
    rewriteButton.disabled = on;
    undoRewriteButton.disabled = on;
    userTitle.readOnly = on;
    text.readOnly = on;
    createMissing.disabled = on;
    overrideProtected.disabled = on;
    onlyUnsettled.disabled = on;
    includeAiSettled.disabled = on;
    whoOnly.disabled = on;
    allParts.disabled = on;
    describeScope();
    refreshCreateWho();
  }

  function cell(row, label, value, className) {
    var td = document.createElement("td");
    td.setAttribute("data-label", label);
    if (className) { td.className = className; }
    if (value instanceof Node) { td.appendChild(value); } else { td.textContent = value || "—"; }
    row.appendChild(td);
    return td;
  }

  function proposal(name, isNew, newLabel) {
    var span = document.createElement("span");
    if (!name) { span.textContent = "—"; return span; }
    var strong = document.createElement("strong");
    strong.textContent = name;
    span.appendChild(strong);
    var badge = document.createElement("span");
    badge.className = "badge " + (isNew ? "warn" : "ok");
    badge.textContent = isNew ? newLabel : "Existing";
    span.appendChild(document.createTextNode(" "));
    span.appendChild(badge);
    return span;
  }

  // BANK_AI_RULES_016 — the text the rule extracted, when the final WHO is
  // another (an existing WHO reused for it).
  function withExtracted(span, item) {
    if (item.extracted_who && item.proposed_who && item.extracted_who !== item.proposed_who) {
      var note = document.createElement("span");
      note.className = "cell-note";
      note.textContent = " extracted: " + item.extracted_who + " · existing WHO reused";
      span.appendChild(document.createElement("br"));
      span.appendChild(note);
    }
    return span;
  }

  function toVerify() {
    var badge = document.createElement("span");
    badge.className = "badge warn";
    badge.textContent = "To verify";
    return badge;
  }

  var PLAN_LABEL = { UPDATED: "Will change", UNCHANGED: "Unchanged", PROTECTED: "Protected",
                     CONFLICT: "Conflict", UNRESOLVED: "Not applied" };

  function planCell(item) {
    var span = document.createElement("span");
    if (item.plan) {
      var badge = document.createElement("span");
      badge.className = "badge " + (item.plan === "UPDATED" ? "ok" : item.plan === "UNCHANGED" ? "" : "warn");
      badge.textContent = PLAN_LABEL[item.plan] || item.plan;
      span.appendChild(badge);
      span.appendChild(document.createTextNode(" "));
    }
    var note = document.createElement("span");
    note.className = "cell-note";
    note.textContent = item.plan_note || "";
    span.appendChild(note);
    return span;
  }

  // BANK_AI_RULES_010 — For Whom proposed by the rule: an active entity, a
  // name that is not one (never created), "Needs review" or unchanged.
  function forWhomProposal(item) {
    if (item.for_whom_to_verify) { return toVerify(); }
    if (!item.proposed_for_whom) { return "unchanged"; }
    if (item.proposed_for_whom_is_entity) { return item.proposed_for_whom; }
    var span = document.createElement("span");
    span.textContent = item.proposed_for_whom + " ";
    var badge = document.createElement("span");
    badge.className = "badge warn";
    badge.textContent = "Not an entity — not applied";
    span.appendChild(badge);
    return span;
  }

  function fill(table, items, whoNewLabel, forWhom) {
    table.innerHTML = "";
    if (!items.length) {
      var empty = table.insertRow();
      var td = empty.insertCell();
      td.className = "muted";
      td.textContent = "None.";
      return;
    }
    var head = table.createTHead().insertRow();
    var headings = forWhom
      ? ["Date", "Description", "Amount", "Current WHO / WHY", "Current For Whom", "Reason", "Proposed WHO",
         "Proposed WHY", "Proposed For Whom", "If applied"]
      : ["Date", "Description", "Amount", "Current WHO / WHY", "Reason", "Proposed WHO", "Proposed WHY", "If applied"];
    headings.forEach(function (h) {
      var th = document.createElement("th");
      th.textContent = h;
      head.appendChild(th);
    });
    var body = table.createTBody();
    items.forEach(function (item) {
      var row = body.insertRow();
      if (item.is_origin) { row.className = "ai-rule-origin-row"; }
      cell(row, "Date", item.date, "col-date");
      var description = document.createElement("span");
      description.textContent = item.description;
      if (item.is_origin) {
        var badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = "Starting transaction";
        description.appendChild(document.createTextNode(" "));
        description.appendChild(badge);
      }
      cell(row, "Description", description, "col-description");
      cell(row, "Amount", item.amount + (item.currency ? " " + item.currency : ""), "col-amount");
      cell(row, "Current WHO / WHY", (item.who || "—") + " / " + (item.why || "—"));
      if (forWhom) { cell(row, "Current For Whom", item.for_whom || "—"); }
      cell(row, "Reason", item.reason);
      // BANK_AI_RULES_007 — a field the rule cannot decide is "Needs review", never assigned.
      cell(row, "Proposed WHO", item.who_to_verify ? toVerify() :
           withExtracted(proposal(item.proposed_who, item.proposed_who_is_new, whoNewLabel), item));
      cell(row, "Proposed WHY", item.why_to_verify ? toVerify() : item.proposed_why ?
           proposal(item.proposed_why, item.proposed_why_is_new, "New — suggestion only") : "unchanged");
      if (forWhom) { cell(row, "Proposed For Whom", forWhomProposal(item)); }
      cell(row, "If applied", planCell(item));
    });
  }

  var SCOPE_LABEL = { PERIOD: "the period shown", ALL: "every movement in the database",
                      SELECTED: "the selected movements" };

  function showPreview(data) {
    var newWho = (data.new_who_names || []).length;
    previewedConflicts = applicationMode ? [] : (data.rule_conflicts || []);
    showConflicts(previewedConflicts, "found by Preview");
    previewed = { id: data.preview_id, text: ruleText(data.rule_text), createMissing: !!data.create_missing_who,
                  overrideProtected: !!data.override_protected, onlyUnsettled: !!data.only_unsettled,
                  applicationMode: data.application_mode, whoOnly: !!data.who_only,
                  scope: scopeSignature(), newWho: newWho };
    previewIdInput.value = data.preview_id;
    stale.hidden = true;
    result.classList.remove("is-stale");
    result.hidden = false;
    document.getElementById("ai-rule-summary").textContent =
      data.examined + " movements examined (" + (SCOPE_LABEL[data.scope] || "the period shown") +
      (data.scope === "PERIOD" ? ", " + (data.date_from || "…") + " – " + (data.date_to || "…") : "") + ") · " +
      data.matches + " matches · " + data.doubts + " doubtful · " +
      (data.who_only ? "MODE “Apply only WHO”: only WHO is applied (WHY, default WHY and For Whom left as they are) · " : "") +
      // BANK_AI_RULES_013 — what the option left out.
      (data.only_unsettled ? (data.excluded_ai_settled || 0) + " excluded because already settled by AI rules" +
        (data.excluded_ai_settled ? " (" + Object.keys(data.excluded_by_rule || {}).map(function (id) {
          return "rule #" + id + ": " + data.excluded_by_rule[id];
        }).join(", ") + ")" : "") + " · " : "AI-settled movements included · ") +
      data.ai_calls + " AI call" +
      (data.ai_calls === 1 ? "" : "s") + " · " + data.provider + (data.model ? " " + data.model : "");
    document.getElementById("ai-rule-plan").textContent =
      "If applied: " + data.planned_updates + (data.for_whom_rule ? " WHO/WHY/For Whom" : " WHO/WHY") +
      " change(s) · " + data.unchanged + " unchanged · " +
      data.protected + " protected · " + data.conflicts + " conflict(s) · " + data.unresolved +
      " not applied (unresolved " + (data.for_whom_rule ? "WHO/WHY/For Whom" : "WHO/WHY") + ") · " +
      data.doubts + " doubtful (never applied)." +
      // BANK_AI_RULES_011 — the explicit override option and the other rules on the same movements.
      (data.override_protected ? " Option “" + data.override_label + "” ON: " + (data.overridden || 0) +
        " manual / confirmed movement(s) would be overridden (For Whom kept, “To confirm”)." : "") +
      (data.overlaps ? " Overlap with other rules: " + data.overlaps + " movement(s) (" +
        Object.keys(data.overlap_rules || {}).map(function (id) {
          return (id.indexOf("WHO ") === 0 ? "WHO rule #" + id.slice(4) : "AI rule #" + id) + ": " +
            data.overlap_rules[id];
        }).join(", ") + ") — see “If applied”." : " No overlap with other rules.") +
      (data.who_reused ? " Existing WHO reused for " + data.who_reused + " movement(s) (see “Proposed WHO”)." : "") +
      (data.scope === "PERIOD" ? " Nothing is applied to the period shown: choose a scope to apply." : "");
    // BANK_AI_RULES_005 — the interpretation, line by line, so it can be checked.
    if (data.method === "CODE") {
      interpretation.textContent =
        "Interpretation of the rule (" + (data.interpretation_reused
          ? "saved interpretation reused: rule and instructions unchanged, no AI call"
          : "new: 1 AI call") + "), executed by RF-One code on every movement:\n" +
        data.interpretation_lines.map(function (line) { return "• " + line; }).join("\n") +
        "\n" + (data.not_matching || 0) + " movement(s) not matching." +
        (data.not_matching_with_prefix ? " " + data.not_matching_with_prefix +
          " movement(s) start the same way but do not contain the end text: not matching." : "");
    } else {
      interpretation.textContent = "The rule could not be turned into conditions the code can execute (" +
        (data.interpretation_rejected || "no executable form") + "): the AI judged each movement." +
        (data.batches ? " " + data.batches + " AI batch(es)" + (data.batches_reused ? ", " + data.batches_reused +
          " reused from an earlier attempt" : "") + "." : "") +
        (data.throttled ? " The AI service asked to slow down " + data.throttled +
          " time(s): those calls were retried with progressive waits." : "");
    }
    interpretation.hidden = false;
    document.getElementById("ai-rule-origin-verdict").textContent =
      data.origin_verdict === "MATCH" ? "The starting transaction matches the rule." :
      data.origin_verdict === "DOUBT" ? "The starting transaction is a doubtful case for this rule." :
      data.scope === "PERIOD" ? "Attention: as written, the rule does NOT match the starting transaction." :
      "The starting transaction is not among the matches of this scope.";
    document.getElementById("ai-rule-match-count").textContent = data.matches;
    document.getElementById("ai-rule-doubt-count").textContent = data.doubts;
    var whoNewLabel = data.create_missing_who ? "New WHO to create" : "New — suggestion only";
    fill(document.getElementById("ai-rule-matches"), data.match_items, whoNewLabel, !!data.for_whom_rule);
    fill(document.getElementById("ai-rule-doubts"), data.doubt_items, whoNewLabel, !!data.for_whom_rule);
    newWhoBox.hidden = !data.create_missing_who;
    newWhoCount.textContent = newWho ? newWho + " new WHO to create: " + data.new_who_names.join(", ") :
      "No new WHO to create: every extracted WHO is already in the list.";
    createWhoResult.textContent = "";
    refreshCreateWho();
  }

  // The form is read BEFORE setBusy disables its controls: a disabled field
  // is never sent.
  function syncApplicationMode() {
    if (!applicationMode) { return; }
    overrideProtected.checked = applicationMode.value === "UPDATE_ASSIGNED";
    onlyUnsettled.checked = false;
    includeAiSettled.checked = true;
    whoOnly.checked = false;
    allParts.checked = true;
  }
  if (applicationMode) {
    applicationMode.addEventListener("change", function () { syncApplicationMode(); markStale(); });
  }
  function formBody() {
    syncApplicationMode();
    selectedInput.value = scopeSelected.checked ? selectedIds().join(",") : "";
    var body = new FormData(form);
    // The "existing transactions" radio group is sent as the fields the server reads.
    body.delete("scope_existing");
    if (scopeAll.checked) { body.set("scope_all", "on"); }
    if (scopeSelected.checked) { body.set("scope_selected", "on"); }
    return body;
  }

  function post(url, body, done) {
    return fetch(url, { method: "POST", body: body, credentials: "same-origin",
                        headers: { "X-Requested-With": "fetch" } })
      .then(function (response) {
        return response.json().catch(function () {
          throw new Error("The server answered with status " + response.status + ".");
        });
      })
      .then(done)
      .catch(function (error) { showError(error.message || String(error)); });
  }

  function runPreview(after) {
    errorBox.hidden = true;
    var count = scopeAll.checked ? "every" : scopeSelected.checked ? String(selection.size) : String(periodCount);
    var body = formBody();
    // BANK_AI_RULES_012 — with the local Claude Code CLI a new rule is interpreted in this same click.
    setBusy(true, overlay.getAttribute("data-ai-provider") === "CLAUDE_CODE_CLI"
      ? "Evaluating " + count + " movement(s). A rule not interpreted yet is first interpreted by Claude Code on " +
        "this PC (usually under a minute), then executed by code. Nothing is applied."
      : "Evaluating " + count + " movement(s) (1 AI call to interpret the rule, more only if the AI must " +
        "judge each movement, about one every " + batchSize + ")… this can take a minute or more.");
    return post(overlay.getAttribute("data-preview-url"), body, function (data) {
      if (!data.ok) {
        showError(data.error ? "Preview not available: " + data.error : "Preview not available.");
        previewed = null;
        result.hidden = true;
        return;
      }
      showPreview(data);
      if (after) { after(data); }
    }).then(function () { setBusy(false); });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (busy) { return; }
    appliedBox.hidden = true;
    runPreview();
  });

  function markStale() {
    if (validatedText !== null && text.value !== validatedText) {   // any change at all
      validatedText = null;                    // BANK_AI_RULES_026 — no longer the validated text
      rewriteStatus.hidden = true;
    }
    if (previewed !== null) { stale.hidden = isCurrent(); }
    result.classList.toggle("is-stale", !stale.hidden);
    draftStatus.textContent = "";
    refreshCreateWho();
  }
  text.addEventListener("input", markStale);
  text.addEventListener("input", function () { conflictsBox.hidden = true; });
  createMissing.addEventListener("change", markStale);
  overrideProtected.addEventListener("change", markStale);
  onlyUnsettled.addEventListener("change", markStale);
  whoOnly.addEventListener("change", markStale);

  // --- WHO / WHY pick lists (BANK_AI_RULES_004) -------------------------
  var caret = null;   // {start, end} last known selection in the rule field

  function rememberCaret() { caret = { start: text.selectionStart, end: text.selectionEnd }; }
  ["keyup", "mouseup", "select", "input", "blur"].forEach(function (name) {
    text.addEventListener(name, rememberCaret);
  });

  function insertIntoRule(snippet) {
    if (busy) { return; }
    var value = text.value;
    var start = caret ? Math.min(caret.start, value.length) : value.length;
    var end = caret ? Math.min(caret.end, value.length) : value.length;
    var before = value.slice(0, start);
    var after = value.slice(end);
    var lead = before && !/\s$/.test(before) ? " " : "";
    var trail = after && !/^\s/.test(after) ? " " : "";
    var inserted = lead + snippet + trail;
    text.value = before + inserted + after;
    var position = before.length + inserted.length;
    text.focus();
    text.setSelectionRange(position, position);
    caret = { start: position, end: position };
    markStale();
  }

  Array.prototype.forEach.call(overlay.querySelectorAll(".ai-rule-picker"), function (picker) {
    var search = picker.querySelector(".ai-rule-picker-search");
    var picks = picker.querySelectorAll(".ai-rule-pick");
    var empty = picker.querySelector(".ai-rule-picker-empty");
    search.addEventListener("keydown", function (event) {
      if (event.key === "Enter") { event.preventDefault(); }
    });
    search.addEventListener("input", function () {
      var term = search.value.trim().toLowerCase();
      var shown = 0;
      Array.prototype.forEach.call(picks, function (pick) {
        var match = !term || pick.getAttribute("data-name").toLowerCase().indexOf(term) !== -1;
        pick.hidden = !match;
        if (match) { shown += 1; }
      });
      empty.hidden = shown > 0;
    });
    picker.addEventListener("click", function (event) {
      var pick = event.target.closest(".ai-rule-pick");
      if (!pick) { return; }
      insertIntoRule(pick.getAttribute("data-kind") + " = \"" + pick.getAttribute("data-name") + "\"");
    });
  });

  function resetPickers() {
    caret = null;
    Array.prototype.forEach.call(overlay.querySelectorAll(".ai-rule-picker-search"), function (search) {
      search.value = "";
      search.dispatchEvent(new Event("input"));
    });
  }

  // --- Rewrite with AI (BANK_AI_RULES_026) -------------------------------
  // Rewrites and verifies only: the server returns a text ONLY when Preview's
  // interpreter and checks accepted it; otherwise the text is left untouched.
  function showRewrite(kind, message, details) {
    rewriteStatus.className = "ai-rule-rewrite-status " + (kind === "ok" ? "is-ok" : "is-refused");
    rewriteStatus.textContent = message;
    if (details && details.length && kind !== "ok") {
      var list = document.createElement("ul");
      details.forEach(function (d) {
        if (!d) { return; }
        var li = document.createElement("li");
        li.textContent = d;
        list.appendChild(li);
      });
      rewriteStatus.appendChild(list);
    }
    rewriteStatus.hidden = false;
  }

  function invalidatePreview() {
    previewed = null;
    if (!result.hidden) { stale.hidden = false; result.classList.add("is-stale"); }
    previewIdInput.value = "";
    refreshCreateWho();
  }

  rewriteButton.addEventListener("click", function () {
    if (busy) { return; }                      // never two requests at once
    errorBox.hidden = true;
    var original = text.value;
    if (!ruleText(original)) { showRewrite("refused", "Write the rule before asking to rewrite it."); return; }
    var body = new FormData();
    body.append("csrf_token", form.querySelector("input[name='csrf_token']").value);
    body.append("rule_text", original);
    body.append("origin_transaction_id", originId.value);
    body.append("rule_id", ruleId.value);
    body.append("user_title", userTitle.value);
    rewriteStatus.hidden = true;
    conflictsBox.hidden = true;
    setBusy(true, "Rewriting with AI and verifying with the interpreter…");
    post(rewriteButton.getAttribute("data-rewrite-url"), body, function (data) {
      showConflicts(data && data.conflicts, "found by Rewrite with AI");
      if (!data || !data.ok || !data.text) {
        showRewrite("refused", (data && data.message) || "Rewrite failed. The text was not changed.",
                    data && data.details);
        return;                                 // the original text is left exactly as it was
      }
      if (text.value !== original) {
        showRewrite("refused", "The text was changed during the rewrite: the rewritten version was not inserted.");
        return;
      }
      beforeRewrite = original;
      text.value = data.text;
      validatedText = text.value;
      invalidatePreview();
      markStale();
      undoRewriteButton.hidden = false;
      showRewrite("ok", data.message || "Rewritten and validated");
    }).then(function () { setBusy(false); });
  });

  undoRewriteButton.addEventListener("click", function () {
    if (busy || beforeRewrite === null) { return; }
    text.value = beforeRewrite;
    beforeRewrite = null;
    validatedText = null;
    undoRewriteButton.hidden = true;
    rewriteStatus.hidden = true;
    invalidatePreview();
    markStale();
  });

  // --- Save Draft / Save / Save and Apply ---------------------------------
  draftButton.addEventListener("click", function () {
    if (busy) { return; }
    errorBox.hidden = true;
    var body = formBody();
    setBusy(true, "Saving the draft…");
    post(overlay.getAttribute("data-draft-url"), body, function (data) {
      if (!data.ok) { showError(data.error || "The draft could not be saved."); return; }
      draftId.value = data.draft_id;
      draftStatus.textContent = "Draft " + data.draft_id + " saved: not active, nothing applied" +
        (ruleId.value ? "; the operative rule's current version is unchanged." : ".");
    }).then(function () { setBusy(false); });
  });

  function savedMessage(data) {
    return "Rule #" + data.rule_id + " saved as operative (version " + data.version_no +
      (data.new_version ? ", new" : ", unchanged") + "; executed by " + (data.method === "CODE" ? "code" : "the AI") +
      "). New transactions: " + (data.apply_future ? "applied automatically to imports." : "not applied.") +
      (data.applied_to_existing === false ? " Version " + data.version_no + " is saved but NOT yet applied to the " +
        "existing transactions: use Save and Apply to apply it." : "") +
      ((data.rule_conflicts || []).length ? " CONFLICT with other active rules — where both apply, nothing is " +
        "changed: " + conflictLines(data.rule_conflicts).join(" ") : "");
  }

  function afterSave(data) {
    ruleId.value = data.rule_id;
    if (data.draft_removed) { draftId.value = ""; }
    operativeBadge.hidden = false;
    operativeBadge.textContent = "Operative rule #" + data.rule_id + " v" + data.version_no;
  }

  // BANK_AI_RULES_009 — after a successful save the window closes and the
  // page shows the rule in "Operative AI Rules" with what was done; on an
  // error the window stays open with the text and the actual outcome.
  var FLASH = "rfone.bank.aiRules.saved";

  function finishAndShow(data, message) {
    try {
      window.sessionStorage.setItem(FLASH, JSON.stringify({ rule_id: data.rule_id, message: message }));
    } catch (e) { /* the page still shows the rule in the list */ }
    modal.close();
    window.location.hash = "ai-operative-rules";
    window.location.reload();
  }

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

  // BANK_AI_RULES_022 — only the Title: no interpretation, no new version, nothing applied.
  function saveTitle() {
    if (busy || !ruleId.value) { return; }
    errorBox.hidden = true;
    var body = new FormData();
    body.append("csrf_token", form.querySelector("input[name='csrf_token']").value);
    body.append("user_title", userTitle.value);
    var url = overlay.getAttribute("data-rule-title-template").replace("/rules/0/", "/rules/" + ruleId.value + "/");
    setBusy(true, "Saving the title…");
    post(url, body, function (data) {
      if (!data.ok) { showError(data.error || "The title could not be saved."); return; }
      userTitle.value = data.user_title;
      if (loaded) { loaded.title = data.user_title; }
      draftStatus.textContent = "Title of rule #" + data.rule_id + " saved. The rule was not reinterpreted or " +
        "reapplied; no movement was changed.";
      var row = document.querySelector("#ai-operative-rules tr[data-rule-id='" + data.rule_id + "']");
      var name = row && row.querySelector(".ai-rule-name");
      if (name) {
        var shown = document.createElement(data.user_title ? "strong" : "em");
        shown.className = data.user_title ? "ai-rule-name" : "muted ai-rule-name";
        shown.textContent = data.user_title || "No title";
        name.replaceWith(shown);
      }
    }).then(function () { setBusy(false); });
  }
  saveTitleButton.addEventListener("click", saveTitle);
  userTitle.addEventListener("keydown", function (event) {
    if (event.key === "Enter") { event.preventDefault(); }     // never a Preview from the Title field
  });

  saveButton.addEventListener("click", function () {
    if (busy) { return; }
    if (onlyTitleChanged()) { saveTitle(); return; }
    errorBox.hidden = true;
    var body = formBody();
    setBusy(true, "Saving the rule…");
    post(overlay.getAttribute("data-save-url"), body, function (data) {
      if (!data.ok) { showError(data.error || "The rule could not be saved."); return; }
      afterSave(data);
      finishAndShow(data, savedMessage(data) + " No existing movement was changed." +
                    (data.draft_removed ? " Removed from the drafts." : ""));
    }).then(function () { setBusy(false); });
  });

  function applicationMessage(a) {
    return "Applied to " + (a.mode === "EXISTING_ALL" ? "every existing movement" : "the selected movements") + ": " +
      a.examined + " examined · " + (a.only_unsettled ? (a.excluded_ai_settled || 0) +
        " excluded (already settled by AI rules) · " : "") +
      a.updated + " updated · " + a.unchanged + " unchanged · " + a.protected +
      " protected · " + a.conflicts + " conflict(s) · " + a.unresolved + " not applied · " + a.errors + " error(s)." +
      (a.who_created && a.who_created.length ? " WHO created: " + a.who_created.join(", ") + "." : "");
  }

  saveApplyButton.addEventListener("click", function () {
    if (busy) { return; }
    errorBox.hidden = true;
    appliedBox.hidden = true;
    var historical = scopeAll.checked || scopeSelected.checked;
    if (historical && !isCurrent()) {
      // No valid preview: make one, said why. The next press applies THAT
      // preview — as long as nothing in the window changes.
      var reason = staleReason();
      runPreview(function (data) {
        var still = staleReason();
        if (still) {
          showError("Preview #" + data.preview_id + " cannot be applied: " + still + ".");
        } else {
          showApplied("New Preview #" + data.preview_id + " (" + reason + "). Check the planned changes, then press " +
                      "Save and Apply to apply this Preview.");
        }
      });
      return;
    }
    if (!applicationMode && historical && previewedConflicts.length && !window.confirm(
        "Conflict with other active rules:\n\n" + conflictLines(previewedConflicts).join("\n\n") +
        "\n\nThe movements where both rules apply will NOT be changed (Conflict); nothing is resolved " +
        "automatically. Apply the rule to the other movements anyway?")) {
      showConflicts(previewedConflicts, "checked before Save and Apply: not applied");
      return;
    }
    var body = formBody();
    setBusy(true, historical ? "Applying the rule…" : "Saving the rule for new movements…");
    post(overlay.getAttribute("data-save-apply-url"), body, function (data) {
      if (!data.ok) {
        if (data.needs_preview) {
          // The server's precise reason; the preview is no longer used.
          previewed = null;
          stale.hidden = false;
          result.classList.add("is-stale");
          showError("Not applied, nothing written: " + data.error);
        } else {
          showError(data.error || "The rule could not be applied.");
        }
        return;
      }
      afterSave(data);
      if (data.applied && !data.complete) {
        // Saved, but the application is NOT complete: never presented as done.
        showError("Application NOT complete — " + applicationMessage(data.application) +
                  " The rule is saved (" + savedMessage(data) + ") and stays in the drafts; the movements in error " +
                  "were not changed.");
        previewed = null;
        stale.hidden = false;
        result.classList.add("is-stale");
      } else if (data.applied) {
        finishAndShow(data, savedMessage(data) + " " + applicationMessage(data.application) +
                      (data.draft_removed ? " Removed from the drafts." : ""));
      } else {
        finishAndShow(data, savedMessage(data) + " No existing movement was changed." +
                      (data.draft_removed ? " Removed from the drafts." : ""));
      }
    }).then(function () { setBusy(false); });
  });

  createWhoButton.addEventListener("click", function () {
    if (busy || !isCurrent()) { return; }
    errorBox.hidden = true;
    var body = formBody();
    setBusy(true, "Adding the new WHO to the list…");
    var url = overlay.getAttribute("data-create-who-template").replace("/previews/0/", "/previews/" + previewed.id + "/");
    post(url, body, function (data) {
      if (!data.ok) { showError(data.error || "No WHO was created."); return; }
      var lines = [data.created_count + " WHO created" + (data.created_count ? ": " + data.created.join(", ") : ""),
                   data.present_count + " already in the list",
                   data.error_count + " error" + (data.error_count === 1 ? "" : "s")];
      createWhoResult.textContent = lines.join(" · ");
      data.errors.forEach(function (e) {
        var p = document.createElement("p");
        p.className = "error";
        p.textContent = e.name + ": " + e.error;
        createWhoResult.appendChild(p);
      });
    }).then(function () { setBusy(false); });
  });

  // BANK_AI_RULES_014 — a failed Open says why (a deleted rule, a session to
  // renew, the server not reachable) instead of failing silently or vaguely.
  function getJson(url, done, failure) {
    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) {
        var json = (response.headers.get("Content-Type") || "").indexOf("application/json") !== -1;
        if (!json) { throw new Error("the server did not answer with the rule (HTTP " + response.status + "): reload the page"); }
        return response.json().then(function (data) {
          if (!response.ok || data.ok === false) { throw new Error(data.error || "HTTP " + response.status); }
          return data;
        });
      })
      .then(done)
      .catch(function (error) { window.alert(failure + "\n\n" + (error && error.message ? error.message : error)); });
  }

  // BANK_AI_RULES_014 — Delete asks for confirmation, naming the rule.
  document.addEventListener("submit", function (event) {
    var form = event.target.closest && event.target.closest(".ai-rule-delete-form");
    if (!form) { return; }
    var message = "Delete the AI rule " + form.getAttribute("data-rule-name") + "?\n\n" +
      "It will no longer be executed. The classifications it already applied to the movements are NOT changed " +
      "and their origin stays recorded.";
    if (!window.confirm(message)) { event.preventDefault(); }
  });

  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest(".ai-rule-open");
    if (button) {
      openFor(JSON.parse(button.getAttribute("data-transaction")), "", "", false, null, false, undefined, "", true);
      return;
    }
    var draftOpen = event.target.closest && event.target.closest(".ai-rule-draft-open");
    if (draftOpen) {
      getJson(overlay.getAttribute("data-draft-get-template").replace(/\/0$/, "/" + draftOpen.getAttribute("data-draft-id")),
        function (data) {
          openFor(data.origin, data.rule_text, data.draft_id, data.create_missing_who,
                  data.rule_id ? { rule_id: data.rule_id } : null, data.override_protected, data.only_unsettled,
                  data.user_title);
        }, "The draft could not be opened; reload the page.");
      return;
    }
    var ruleOpen = event.target.closest && event.target.closest(".ai-rule-operative-open");
    if (ruleOpen) {
      getJson(overlay.getAttribute("data-rule-get-template").replace(/\/0$/, "/" + ruleOpen.getAttribute("data-rule-id")),
        function (data) {
          openFor(data.origin, data.rule_text, "", data.create_missing_who, data, data.override_protected, undefined,
                  data.user_title);
        },
        "The rule could not be opened; reload the page.");
    }
  });
})();
