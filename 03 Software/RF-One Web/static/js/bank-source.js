/* Source page — the ONE New / Edit Source modal
   (BANK_SOURCE_AND_IMPORT_REVIEW_001).

   "+ New Source" opens it empty and saves to the create route; a row's
   "Edit" opens it filled from that row and saves to the row's edit route.
   Both are the existing PaymentInstrument routes, so validation lives in
   one place. Saved with fetch: an error stays in the modal; a success
   closes it and reloads the page, so the list shows the Source in its
   place (the list is ordered by name). Cancel / Escape save nothing. */

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
  var settlementNote = document.getElementById("source-settlement-note");
  var FIELDS = ["display_name", "instrument_type", "institution", "last_four",
                "legal_entity_id", "currency", "linked_instrument_id"];
  var identifierInput = document.getElementById("source-external_account_identifier");
  var keepIdentifier = document.getElementById("source-keep_external_account_identifier");

  var editing = null;

  function field(name) { return document.getElementById("source-" + name); }

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  // Only the fields that mean something for the chosen type are shown. A
  // card's entity comes from its settlement account and its settlement
  // account has its own dated history (Card settings), so neither is typed
  // here; PayPal alone has a "Funded by" account.
  function syncType() {
    var type = typeSelect.value;
    Array.prototype.forEach.call(overlay.querySelectorAll("[data-source-only]"), function (el) {
      el.hidden = el.getAttribute("data-source-only") !== type;
    });
    // A hidden "Funded by" is not sent at all, exactly like the forms this
    // modal replaced. The entity select stays enabled for every type so an
    // edit never clears a value it did not show.
    field("linked_instrument_id").disabled = type !== "PAYPAL";
  }

  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      showError("");
      form.reset();
      saveButton.disabled = false;
      saveButton.textContent = "Save";
      if (editing) {
        title.textContent = "Edit Source";
        form.action = editing.url;
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
        settlementNote.textContent = editing.settlement
          ? "Currently " + editing.settlement + ". Change it, with its effective date, in Card settings."
          : "Not configured yet. Set it, with its effective date, in Card settings.";
      } else {
        title.textContent = "New Source";
        form.action = overlay.dataset.createUrl;
        identifierInput.placeholder = "";
        keepIdentifier.value = "";
        stateRow.hidden = true;
        statusSelect.disabled = true;
        settlementNote.textContent = "Set it after saving, in the card's Card settings — it is recorded with an effective date.";
      }
      syncType();
    },
    initialFocus: function () { return field("display_name"); },
  });

  document.querySelectorAll("[data-source-new]").forEach(function (button) {
    button.addEventListener("click", function () { editing = null; modal.open(button); });
  });
  document.querySelectorAll("[data-source-edit]").forEach(function (button) {
    button.addEventListener("click", function () {
      try { editing = JSON.parse(button.getAttribute("data-source")); } catch (e) { editing = null; }
      if (editing) { modal.open(button); }
    });
  });

  typeSelect.addEventListener("change", syncType);
  identifierInput.addEventListener("input", function () { keepIdentifier.value = ""; });
  form.addEventListener("input", function () { showError(""); });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    if (!field("display_name").value.trim()) { showError("Write the Source name."); field("display_name").focus(); return; }
    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
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
        if (!data || !data.ok) {
          showError((data && data.error) || "Not saved.");
          saveButton.disabled = false;
          saveButton.textContent = "Save";
          return;
        }
        modal.close();
        window.location.reload();
      })
      .catch(function () {
        showError("The server did not answer. Reload the page to see whether the Source was saved.");
        saveButton.disabled = false;
        saveButton.textContent = "Save";
      });
  });
})();
