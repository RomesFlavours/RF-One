/* Source page — the ONE New / Edit Source modal
   (BANK_SOURCE_AND_IMPORT_REVIEW_001, BANK_SOURCE_EDIT_AND_ENTITIES_001).

   "+ New Source" opens it empty and saves to the create route; a row's
   "Edit" — the only action per Source — opens it filled from that row and
   saves to the row's edit route. For a card the same modal carries its
   settlement account and cardholder (each from a date) and its history, so
   there is no separate Card settings page. One Save sends everything; the
   server saves it in one transaction or not at all. Saved with fetch: an
   error stays in the modal; a success reloads the list.

   "+ New Entity" opens a small dialog on top: it creates the Entity (or
   reuses an equivalent active one) and selects it as the owner.

   Import session (BANK_COMPLETE_SOURCE_ALL_ROWS_001): every file row's
   "Complete Source" opens this same modal for that file. "Source of this
   file" chooses between the row's Source, an existing one, or a new one
   prefilled with what the file states; Save saves that Source AND links it
   to the file (the server does both). Cancel sends nothing, so it never
   leaves a Source behind. */

(function () {
  "use strict";

  var overlay = document.getElementById("source-dialog");
  if (!overlay || !window.RFOneModal) { return; }

  var form = document.getElementById("source-form");
  var title = document.getElementById("source-dialog-title");
  var errorBox = document.getElementById("source-error");
  var saveButton = document.getElementById("source-save");
  var typeSelect = document.getElementById("source-instrument_type");
  var stateRow = document.getElementById("source-state-row");
  var statusSelect = document.getElementById("source-status");
  var ownerSelect = document.getElementById("source-owner_entity");
  var derivedOwner = document.getElementById("source-derived-owner");
  var settlementSelect = document.getElementById("source-settlement_bank_account_id");
  var holderSelect = document.getElementById("source-cardholder");
  var holderNameRow = document.getElementById("source-cardholder-name-row");
  var history = document.getElementById("source-history");
  var historyBody = document.getElementById("source-history-body");
  var identifierInput = document.getElementById("source-external_account_identifier");
  var keepIdentifier = document.getElementById("source-keep_external_account_identifier");
  var support = {};
  try { support = JSON.parse(document.getElementById("source-support").textContent) || {}; } catch (e) { support = {}; }
  var fileRow = document.getElementById("source-file-row");
  var fileChoice = document.getElementById("source-file-choice");
  var allSources = {};
  try { allSources = JSON.parse((document.getElementById("source-all") || {}).textContent || "{}") || {}; } catch (e) { allSources = {}; }

  var FIELDS = ["display_name", "instrument_type", "institution", "last_four", "owner_entity", "currency",
                "linked_instrument_id", "settlement_bank_account_id", "cardholder", "cardholder_name"];
  var CARD_FIELDS = ["settlement_bank_account_id", "settlement_valid_from", "cardholder",
                     "cardholder_valid_from", "cardholder_name"];
  var editing = null;
  var fileCtx = null;   // the import-session file the modal is open for
  var returnAnchor = "";
  var note = null;

  function field(name) { return document.getElementById("source-" + name); }
  function esc(text) {
    var div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }
  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }
  function showNote(message) {
    if (!note) {
      note = document.createElement("p");
      note.className = "cell-note";
      note.setAttribute("role", "status");
      ownerSelect.parentNode.parentNode.appendChild(note);
    }
    note.textContent = message || "";
    note.hidden = !message;
  }

  // Only the fields that mean something for the chosen type are shown AND
  // sent (a disabled control is not posted, so nothing hidden is changed).
  // A card's owner is never chosen: it comes from its settlement account.
  function syncType() {
    var type = typeSelect.value;
    var isCard = type === "CREDIT_CARD";
    // A card's owner is derived from its settlement account; every other
    // Source — a purchase platform too — may have an owner chosen here.
    var noOwner = isCard;
    Array.prototype.forEach.call(overlay.querySelectorAll("[data-source-only]"), function (el) {
      el.hidden = el.getAttribute("data-source-only") !== type;
    });
    Array.prototype.forEach.call(overlay.querySelectorAll("[data-source-hide]"), function (el) {
      el.hidden = el.getAttribute("data-source-hide").split(" ").indexOf(type) !== -1;
    });
    ownerSelect.disabled = noOwner;
    document.getElementById("entity-new").disabled = noOwner;
    CARD_FIELDS.forEach(function (name) { field(name).disabled = !isCard; });
    field("linked_instrument_id").disabled = type !== "PAYPAL";
    history.hidden = !(isCard && editing && editing.history);
    syncHolder();
  }
  function syncHolder() {
    var other = holderSelect.value === "other" && !holderSelect.disabled;
    holderNameRow.hidden = !other;
    field("cardholder_name").disabled = !other;
  }

  // ------------------------------------------------------------ history
  // Each past period can be corrected in place (never deleted), through the
  // existing correction routes; the page then reopens on this Source.
  function optionsFrom(select, keepEmpty) {
    return Array.prototype.filter.call(select.options, function (o) { return keepEmpty || o.value; })
      .map(function (o) { return "<option value=\"" + esc(o.value) + "\">" + esc(o.textContent) + "</option>"; })
      .join("");
  }
  function labelOf(select, value) {
    var option = Array.prototype.find.call(select.options, function (o) { return o.value === String(value); });
    return option ? option.textContent : "—";
  }
  function period(row) { return row.valid_from + " → " + (row.valid_to || "open"); }

  function renderHistory() {
    var h = editing && editing.history;
    if (!h) { historyBody.innerHTML = ""; return; }
    var html = "<h4>Settlement account</h4>";
    html += h.settlement.length ? h.settlement.map(function (row) {
      return "<div class=\"history-row\" data-kind=\"settlement\" data-id=\"" + row.id + "\">"
        + "<span>" + esc(labelOf(settlementSelect, row.account_id)) + " · " + esc(period(row))
        + (row.notes ? " · " + esc(row.notes) : "") + "</span> "
        + "<button type=\"button\" class=\"btn-secondary btn-inline\" data-correct>Correct</button>"
        + "<form hidden data-correct-form>"
        + "<select name=\"settlement_bank_account_id\" aria-label=\"Settlement account\">" + optionsFrom(settlementSelect, false) + "</select>"
        + "<input type=\"date\" name=\"valid_from\" value=\"" + esc(row.valid_from) + "\" aria-label=\"From\">"
        + "<input type=\"text\" name=\"notes\" maxlength=\"500\" placeholder=\"Reason for the correction\" value=\"" + esc(row.notes) + "\">"
        + "<button type=\"submit\">Save correction</button></form></div>";
    }).join("") : "<p class=\"muted\">No settlement account recorded.</p>";
    html += "<h4>Cardholder</h4>";
    html += h.holder.length ? h.holder.map(function (row) {
      return "<div class=\"history-row\" data-kind=\"cardholder\" data-id=\"" + row.id + "\">"
        + "<span>" + esc(row.name) + " · " + esc(period(row)) + (row.notes ? " · " + esc(row.notes) : "") + "</span> "
        + "<button type=\"button\" class=\"btn-secondary btn-inline\" data-correct>Correct</button>"
        + "<form hidden data-correct-form>"
        + "<select name=\"choice\" aria-label=\"Cardholder\">" + optionsFrom(holderSelect, false) + "</select>"
        + "<input type=\"text\" name=\"holder_display_name\" maxlength=\"255\" placeholder=\"Name (other person)\" value=\"" + esc(row.name) + "\">"
        + "<input type=\"date\" name=\"valid_from\" value=\"" + esc(row.valid_from) + "\" aria-label=\"From\">"
        + "<input type=\"text\" name=\"notes\" maxlength=\"500\" placeholder=\"Reason for the correction\" value=\"" + esc(row.notes) + "\">"
        + "<button type=\"submit\">Save correction</button></form></div>";
    }).join("") : "<p class=\"muted\">No cardholder recorded.</p>";
    historyBody.innerHTML = html;
    // Preselect each correction form on its own row's current value.
    Array.prototype.forEach.call(historyBody.querySelectorAll(".history-row"), function (div) {
      var rows = div.getAttribute("data-kind") === "settlement" ? h.settlement : h.holder;
      var row = rows.filter(function (r) { return String(r.id) === div.getAttribute("data-id"); })[0];
      var select = div.querySelector("select");
      if (div.getAttribute("data-kind") === "settlement") { select.value = String(row.account_id); }
      else {
        select.value = row.kind === "ACTING_IDENTITY" ? "identity:" + row.identity_id
          : row.kind === "EMPLOYEE" ? "employee:" + row.employee_id : "other";
      }
    });
  }

  historyBody.addEventListener("click", function (event) {
    var button = event.target.closest("[data-correct]");
    if (!button) { return; }
    var correction = button.parentNode.querySelector("[data-correct-form]");
    correction.hidden = !correction.hidden;
  });
  historyBody.addEventListener("submit", function (event) {
    var correction = event.target.closest("[data-correct-form]");
    if (!correction) { return; }
    event.preventDefault();
    var row = correction.parentNode;
    var kind = row.getAttribute("data-kind");
    var data = new FormData(correction);
    data.append("csrf_token", support.csrf || "");
    if (kind === "cardholder") {
      var choice = data.get("choice") || "";
      var parts = choice.split(":");
      data.delete("choice");
      data.append("holder_kind", parts[0] === "identity" ? "ACTING_IDENTITY" : parts[0] === "employee" ? "EMPLOYEE" : "UNLINKED_PERSON");
      data.append("holder_acting_identity_id", parts[0] === "identity" ? parts[1] : "");
      data.append("holder_employee_id", parts[0] === "employee" ? parts[1] : "");
    }
    var url = "/bank/instruments/" + editing.id + "/" + kind + "/" + row.getAttribute("data-id");
    fetch(url, { method: "POST", body: data, credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (response) { return response.json().catch(function () { return { ok: false, error: "Not saved (HTTP " + response.status + ")." }; }); })
      .then(function (result) {
        if (!result || !result.ok) { showError((result && result.error) || "Not saved."); return; }
        window.location.href = window.location.pathname + "?edit=" + editing.id + returnAnchor;
      })
      .catch(function () { showError("The server did not answer. Reload the page and try again."); });
  });

  // ------------------------------------------------------------ the modal
  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      showError("");
      showNote("");
      form.reset();
      saveButton.disabled = false;
      saveButton.textContent = "Save";
      setupFile();
      fill();
    },
    initialFocus: function () { return fileCtx && fileChoice ? fileChoice : field("display_name"); },
  });

  function sourceLabel(data) {
    var digits = data.last_four ? " ··" + data.last_four : (data.account_hint ? " " + data.account_hint : "");
    return data.display_name + digits;
  }
  function addOption(value, label) {
    var option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    fileChoice.appendChild(option);
  }
  // The file's choices: its current Source, the Sources its name matches,
  // a new Source from the file, then every other Source the file may take.
  function setupFile() {
    if (!fileRow) { return; }
    fileRow.hidden = !fileCtx;
    Array.prototype.forEach.call(fileRow.querySelectorAll("input"), function (input) { input.disabled = !fileCtx; });
    if (!fileCtx) { return; }
    document.getElementById("source-import_file_index").value = String(fileCtx.index);
    document.getElementById("source-file-name").textContent = fileCtx.file_name;
    fileChoice.innerHTML = "";
    var shown = {};
    if (fileCtx.source_id && allSources[fileCtx.source_id]) {
      addOption(String(fileCtx.source_id), sourceLabel(allSources[fileCtx.source_id]) + " (current)");
      shown[fileCtx.source_id] = true;
    }
    (fileCtx.candidates || []).forEach(function (id) {
      if (shown[id] || !allSources[id]) { return; }
      addOption(String(id), sourceLabel(allSources[id]) + " (matches the file)");
      shown[id] = true;
    });
    var prefill = fileCtx.prefill || {};
    addOption("new", "New Source" + (prefill.display_name ? " from the file: " + prefill.display_name : ""));
    (fileCtx.choices || []).forEach(function (id) {
      if (shown[id] || !allSources[id]) { return; }
      addOption(String(id), sourceLabel(allSources[id]));
      shown[id] = true;
    });
    fileChoice.value = fileChoice.options[0].value;
    editing = fileChoice.value === "new" ? null : allSources[fileChoice.value];
  }
  if (fileChoice) {
    fileChoice.addEventListener("change", function () {
      var value = fileChoice.value;
      editing = value === "new" ? null : allSources[value];
      showError("");
      form.reset();
      fileChoice.value = value;
      fill();
    });
  }

  // The form for `editing` (an existing Source) or for a new one — prefilled,
  // in an import session, with what the file states.
  function fill() {
      if (editing) {
        title.textContent = "Edit Source";
        form.action = editing.url;
        Array.prototype.forEach.call(ownerSelect.querySelectorAll("option[data-current-only]"), function (o) { o.remove(); });
        // An owner no longer offered (an inactive Entity) is kept as it is:
        // it is shown, marked, so an unrelated edit never clears it.
        if (editing.owner_entity && !Array.prototype.some.call(ownerSelect.options, function (o) { return o.value === editing.owner_entity; })) {
          var kept = document.createElement("option");
          kept.value = editing.owner_entity;
          kept.textContent = (editing.derived_owner || "Current owner") + " (inactive)";
          kept.setAttribute("data-current-only", "");
          ownerSelect.appendChild(kept);
        }
        FIELDS.forEach(function (name) {
          var input = field(name);
          if (input) { input.value = editing[name] == null ? "" : String(editing[name]); }
        });
        // The stored account identifier is never sent to this page: the
        // field shows only its last four as a hint and is kept unless the
        // operator types a replacement.
        identifierInput.value = "";
        identifierInput.placeholder = editing.account_hint
          ? "Unchanged (" + editing.account_hint + ") — type to replace" : "";
        keepIdentifier.value = "1";
        // Active / Inactive is offered on Edit only (a new Source starts
        // Active) and is sent only then: a disabled select is not posted.
        stateRow.hidden = false;
        statusSelect.disabled = false;
        statusSelect.value = editing.status === "ACTIVE" ? "ACTIVE" : "INACTIVE";
        derivedOwner.textContent = editing.derived_owner
          ? editing.derived_owner + " — derived from its settlement account."
          : "Not configured — it comes from the settlement account below.";
      } else {
        title.textContent = "New Source";
        form.action = overlay.dataset.createUrl;
        identifierInput.placeholder = "";
        keepIdentifier.value = "";
        stateRow.hidden = true;
        statusSelect.disabled = true;
        derivedOwner.textContent = "It comes from the settlement account below.";
        var prefill = (fileCtx && fileCtx.prefill) || {};
        Object.keys(prefill).forEach(function (name) {
          var input = field(name);
          if (input && prefill[name]) { input.value = prefill[name]; }
        });
      }
      if (fileCtx) { title.textContent = "Complete Source"; }
      renderHistory();
      syncType();
  }

  document.querySelectorAll("[data-source-new]").forEach(function (button) {
    button.addEventListener("click", function () { editing = null; fileCtx = null; returnAnchor = ""; modal.open(button); });
  });
  document.querySelectorAll("[data-source-edit]").forEach(function (button) {
    button.addEventListener("click", function () {
      try { editing = JSON.parse(button.getAttribute("data-source")); } catch (e) { editing = null; }
      try { fileCtx = JSON.parse(button.getAttribute("data-source-file")); } catch (e) { fileCtx = null; }
      // Where the page lands after Save (the import session: this file's row).
      returnAnchor = button.getAttribute("data-source-return") || "";
      if (editing || fileCtx) { modal.open(button); }
    });
  });

  typeSelect.addEventListener("change", syncType);
  holderSelect.addEventListener("change", syncHolder);
  identifierInput.addEventListener("input", function () { keepIdentifier.value = ""; });
  form.addEventListener("input", function () { showError(""); });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    if (!field("display_name").value.trim()) { showError("Write the Source name."); field("display_name").focus(); return; }
    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
    // A fetch is not a form submit: the global wait cursor / spinner is
    // started here, and stopped if the modal stays open on an error.
    if (window.RFOneBusy) { window.RFOneBusy.start(); }
    function failed(message) {
      if (window.RFOneBusy) { window.RFOneBusy.stop(); }
      showError(message);
      saveButton.disabled = false;
      saveButton.textContent = "Save";
    }
    fetch(form.action, {
      method: "POST", body: new FormData(form), credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" },
    })
      .then(function (response) {
        return response.json().catch(function () {
          return { ok: false, error: "Not saved (HTTP " + response.status + "). Reload the page and try again." };
        });
      })
      .then(function (data) {
        if (!data || !data.ok) { failed((data && data.error) || "Not saved."); return; }
        modal.close();
        // Reload without ?edit (so the modal does not reopen); a change of
        // the #anchor alone would not reload, hence replaceState + reload.
        window.history.replaceState(null, "", window.location.pathname + returnAnchor);
        window.location.reload();
      })
      .catch(function () {
        failed("The server did not answer. Reload the page to see whether the Source was saved.");
      });
  });

  // ------------------------------------------------------------ + New Entity
  var entityOverlay = document.getElementById("entity-dialog");
  var entityForm = document.getElementById("entity-form");
  var entityError = document.getElementById("entity-error");
  var entitySave = document.getElementById("entity-save");
  var entityModal = window.RFOneModal.create({
    overlay: entityOverlay,
    onOpen: function () {
      entityForm.reset();
      entityError.hidden = true;
      entitySave.disabled = false;
    },
    initialFocus: function () { return document.getElementById("entity-name"); },
  });
  document.getElementById("entity-new").addEventListener("click", function (event) {
    entityModal.open(event.currentTarget);
  });

  // The new (or reused) Entity joins the owner list in its group, in
  // alphabetical order, and is selected.
  function selectEntity(entity) {
    var existing = Array.prototype.find.call(ownerSelect.options, function (o) { return o.value === entity.value; });
    if (!existing) {
      var group = ownerSelect.querySelector("optgroup[data-kind=\"" + entity.kind + "\"]") || ownerSelect;
      existing = document.createElement("option");
      existing.value = entity.value;
      existing.textContent = entity.label;
      var before = Array.prototype.find.call(group.querySelectorAll("option"), function (o) {
        return o.textContent.localeCompare(entity.label, undefined, { sensitivity: "base" }) > 0;
      });
      group.insertBefore(existing, before || null);
    }
    ownerSelect.value = entity.value;
  }

  entityForm.addEventListener("submit", function (event) {
    event.preventDefault();
    entityError.hidden = true;
    var name = document.getElementById("entity-name").value.trim();
    if (!name) { entityError.textContent = "Write the entity name."; entityError.hidden = false; return; }
    var data = new FormData(entityForm);
    if (!entityForm.querySelector("[name=active]").checked) { data.set("active", "0"); }
    entitySave.disabled = true;
    fetch(entityOverlay.dataset.url, {
      method: "POST", body: data, credentials: "same-origin", headers: { "X-Requested-With": "fetch" },
    })
      .then(function (response) { return response.json().catch(function () { return { ok: false, error: "Not saved (HTTP " + response.status + ")." }; }); })
      .then(function (result) {
        entitySave.disabled = false;
        if (!result || !result.ok) { entityError.textContent = (result && result.error) || "Not saved."; entityError.hidden = false; return; }
        if (result.entity.active) { selectEntity(result.entity); }
        entityModal.close();
        showNote(result.created
          ? (result.entity.active ? "Entity “" + result.entity.label + "” created and selected." : "Entity “" + result.entity.label + "” created as inactive (not selectable).")
          : "“" + result.entity.label + "” already exists — selected.");
      })
      .catch(function () { entitySave.disabled = false; entityError.textContent = "The server did not answer."; entityError.hidden = false; });
  });

  // ?edit=<id> — the retired Card settings page and "Open Source" links land
  // here with that Source's modal open.
  if (support.open_id) {
    var target = Array.prototype.find.call(document.querySelectorAll("[data-source-edit]"), function (button) {
      // In an import session: the row the page came back to.
      var back = button.getAttribute("data-source-return");
      if (back && window.location.hash && back !== window.location.hash) { return false; }
      try { return JSON.parse(button.getAttribute("data-source")).id === support.open_id; } catch (e) { return false; }
    });
    if (target) { target.click(); }
  }
})();
