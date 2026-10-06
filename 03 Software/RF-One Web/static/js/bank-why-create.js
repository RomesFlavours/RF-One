/* "Create New WHY" — the ONE creation flow of both reconciliation modals.

   One script for the one dialog in `_bank_why_create_dialog.html`. The
   Select WHO / WHY popup and the WHO Rule modal both call

     RFOneWhyCreate.open({
       whoId, whoName,      // the WHO the WHY is added to (optional)
       groupId,             // the WHY group to preselect (optional)
       name,                // a name to start from (optional)
       onSaved: function (why, result) { ... },
     }, trigger)

   It opens ON TOP of the calling modal (RFOneModal stacks them), posts to
   the one route, and on success closes and hands the WHY back — created, or
   the existing WHY of that name reused — so the caller selects it where it
   is. Cancel / Escape close it and focus returns to the button that opened
   it; the calling modal is untouched. Groups, WHAT and names are fetched
   once per page, on first use. */

(function () {
  "use strict";

  var overlay = document.getElementById("why-create-dialog");
  if (!overlay || !window.RFOneModal) { return; }

  var form = document.getElementById("why-create-form");
  var context = document.getElementById("why-create-context");
  var whoInput = document.getElementById("why-create-occurrence-id");
  var nameInput = document.getElementById("why-create-dialog-name");
  var existingNote = document.getElementById("why-create-dialog-existing");
  var groupField = document.getElementById("why-create-dialog-group-field");
  var groupSelect = document.getElementById("why-create-dialog-group");
  var whatField = document.getElementById("why-create-dialog-what-field");
  var whatSearch = document.getElementById("why-create-dialog-what-search");
  var whatSelect = document.getElementById("why-create-dialog-what");
  var whatChosen = document.getElementById("why-create-dialog-what-chosen");
  var errorBox = document.getElementById("why-create-dialog-error");
  var saveButton = document.getElementById("why-create-dialog-save");

  var options = null;          // {groups, whats, whys} once loaded
  var loading = null;
  var pending = {};

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  function normalized(text) { return (text || "").trim().replace(/\s+/g, " ").toLowerCase(); }

  function groupName(id) {
    var group = (options.groups || []).filter(function (g) { return String(g.id) === String(id); })[0];
    return group ? group.name : "";
  }

  function load() {
    if (options) { return Promise.resolve(options); }
    if (loading) { return loading; }
    loading = fetch(overlay.dataset.optionsUrl, { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : { groups: [], whats: [], whys: [] }; })
      .then(function (data) {
        options = data || { groups: [], whats: [], whys: [] };
        groupSelect.innerHTML = "";
        groupSelect.appendChild(new Option("— choose WHY group —", ""));
        options.groups.forEach(function (g) { groupSelect.appendChild(new Option(g.name, g.id)); });
        renderWhats();
        return options;
      });
    return loading;
  }

  // The WHAT list is searchable: the search filters the visible choices,
  // and the one already chosen always stays in the list.
  function renderWhats() {
    var term = normalized(whatSearch.value);
    var chosen = whatSelect.value;
    whatSelect.innerHTML = "";
    (options.whats || []).forEach(function (what) {
      if (term && normalized(what.label).indexOf(term) === -1 && String(what.id) !== chosen) { return; }
      whatSelect.appendChild(new Option(what.label, what.id, false, String(what.id) === chosen));
    });
    syncWhatChosen();
  }

  function syncWhatChosen() {
    var option = whatSelect.options[whatSelect.selectedIndex];
    whatChosen.textContent = option && whatSelect.value
      ? "Chosen: " + option.textContent
      : "Optional, for bookkeeping later. Not needed to reconcile.";
    whatChosen.classList.toggle("is-chosen", !!whatSelect.value);
  }

  function existingNamed(name) {
    var wanted = normalized(name);
    if (!wanted || !options) { return null; }
    return (options.whys || []).filter(function (w) { return normalized(w.name) === wanted; })[0] || null;
  }

  // A name that already is a WHY: Save reuses it, so group and WHAT are not asked.
  function syncExisting() {
    var known = existingNamed(nameInput.value);
    existingNote.hidden = !known;
    existingNote.textContent = known
      ? "Existing WHY found: “" + known.name + "” (" + (groupName(known.group_id) || "no group") + " · "
        + known.what + "). Save reuses it — nothing is created twice."
      : "";
    groupField.hidden = !!known;
    whatField.hidden = !!known;
  }

  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      showError("");
      form.reset();
      whoInput.value = pending.whoId ? String(pending.whoId) : "";
      context.textContent = pending.whoName
        ? "For WHO: " + pending.whoName + " — the new WHY is added to this WHO's possible WHY."
        : "No WHO chosen yet: the WHY is created now and added to the WHO when you confirm or apply.";
      nameInput.value = pending.name || "";
      saveButton.disabled = false;
      saveButton.textContent = "Save";
      load().then(function () {
        whatSearch.value = "";
        whatSelect.value = "";
        renderWhats();
        groupSelect.value = pending.groupId ? String(pending.groupId) : "";
        syncExisting();
      });
    },
    initialFocus: function () { return nameInput; },
  });

  function open(config, trigger) {
    pending = config || {};
    modal.open(trigger);
  }

  window.RFOneWhyCreate = { open: open, isOpen: function () { return modal.isOpen(); } };

  // A message about a field is out of date as soon as the field changes.
  nameInput.addEventListener("input", function () { showError(""); syncExisting(); });
  groupSelect.addEventListener("change", function () { showError(""); });
  whatSearch.addEventListener("input", renderWhats);
  whatSelect.addEventListener("change", function () { showError(""); syncWhatChosen(); });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    var known = existingNamed(nameInput.value);
    if (!nameInput.value.trim()) { showError("Write the WHY Name."); nameInput.focus(); return; }
    if (!known && !groupSelect.value) { showError("Choose the WHY Group."); groupSelect.focus(); return; }
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
        // Known from now on: a second "Create New WHY" with this name reuses it.
        if (!existingNamed(data.why.name)) {
          options.whys.push({ id: data.why.id, name: data.why.name, group_id: data.why.group_id, what: data.why.what });
        }
        var done = pending.onSaved;
        modal.close();
        if (typeof done === "function") { done(data.why, data); }
      })
      .catch(function () {
        showError("The server did not answer. Reload the page to see whether the WHY was saved.");
        saveButton.disabled = false;
        saveButton.textContent = "Save";
      });
  });
})();
