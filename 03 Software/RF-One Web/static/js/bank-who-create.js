/* "Create New WHO" (BANK_RECONCILIATION_NEW_WHO_001) — the dialog in
   `_bank_who_create_dialog.html`. Select WHO / WHY calls

     RFOneWhoCreate.open({
       name,                            // a name to start from (optional)
       onSaved: function (who, result) { ... },   // {id, name}
     }, trigger)

   It opens ON TOP of the calling modal (RFOneModal stacks them). While the
   name is typed it asks the existing lookup which active WHO the name
   already IS (Save then selects that WHO: nothing is created twice) and
   which ones only LOOK alike (offered as buttons, to choose instead). Save
   posts to the one route and hands the WHO back — created or reused — so
   the caller selects it; choosing an offered WHO hands that one back
   without saving anything. Cancel / Escape close it: nothing is created and
   the calling modal is untouched. The global wait cursor / spinner runs
   while the server answers. */

(function () {
  "use strict";

  var overlay = document.getElementById("who-create-dialog");
  if (!overlay || !window.RFOneModal) { return; }

  var form = document.getElementById("who-create-form");
  var nameInput = document.getElementById("who-create-name");
  var existingNote = document.getElementById("who-create-existing");
  var similarBox = document.getElementById("who-create-similar");
  var similarList = document.getElementById("who-create-similar-list");
  var errorBox = document.getElementById("who-create-error");
  var saveButton = document.getElementById("who-create-save");

  var pending = {};
  var lookupTimer = null;
  var lookupSeq = 0;

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }
  function busy(on) {
    if (!window.RFOneBusy) { return; }
    if (on) { window.RFOneBusy.start(); } else { window.RFOneBusy.stop(); }
  }

  function hand(who, result) {
    var done = pending.onSaved;
    modal.close();
    if (typeof done === "function") { done(who, result || {}); }
  }

  function useButton(who) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "btn-secondary btn-inline";
    button.textContent = "Use “" + who.name + "”";
    button.addEventListener("click", function () { hand({ id: who.id, name: who.name }, { reused: true }); });
    return button;
  }

  // What the typed name already is, or looks like (the WHO lookup).
  function lookup() {
    var text = nameInput.value.trim();
    var seq = ++lookupSeq;
    if (!text) { render(null); return; }
    fetch(overlay.dataset.optionsUrl + "?q=" + encodeURIComponent(text), { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) { if (seq === lookupSeq) { render(data); } })
      .catch(function () { /* the lookup only advises: Save still checks */ });
  }

  function render(data) {
    var identity = data && data.identity;
    existingNote.hidden = !identity;
    existingNote.textContent = identity
      ? "Existing WHO found: “" + identity.name + "”. Save selects it — nothing is created twice." : "";
    similarList.innerHTML = "";
    var offered = {};
    if (identity) { offered[identity.id] = true; }
    var others = [];
    ((data && data.similar) || []).concat((data && data.matches) || []).forEach(function (who) {
      if (offered[who.id]) { return; }
      offered[who.id] = true;
      others.push(who);
    });
    others.slice(0, 8).forEach(function (who) { similarList.appendChild(useButton(who)); });
    similarBox.hidden = others.length === 0;
  }

  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      showError("");
      form.reset();
      nameInput.value = pending.name || "";
      saveButton.disabled = false;
      saveButton.textContent = "Save";
      render(null);
      lookup();
    },
    initialFocus: function () { return nameInput; },
  });

  function open(config, trigger) {
    pending = config || {};
    modal.open(trigger);
  }

  window.RFOneWhoCreate = { open: open, isOpen: function () { return modal.isOpen(); } };

  nameInput.addEventListener("input", function () {
    showError("");
    clearTimeout(lookupTimer);
    lookupTimer = setTimeout(lookup, 200);
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    if (!nameInput.value.trim()) { showError("Write the WHO Name."); nameInput.focus(); return; }
    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
    busy(true);
    function failed(message) {
      busy(false);
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
        busy(false);
        hand(data.who, data);
      })
      .catch(function () {
        failed("The server did not answer. Reload the page to see whether the WHO was saved.");
      });
  });
})();
