/* "Select WHO / WHY" (BANK_MANUAL_WHO_WHY_001, BANK_WHY_NAVIGATION_GROUPS_001).

   One script for the one popup in `_bank_who_why_modal.html`, used by
   Review > To Reconcile and Review > Reconciled. It decides nothing: the
   operator picks a WHO, browses the WHY GROUPS, picks ANY active WHY (or
   creates a new one), and Confirm sends WHO + WHY to the one route that
   records them for this transaction.

   Three columns:
     WHO        every active WHO, alphabetical; search covers aliases, the
                choice is always the canonical WHO.
     WHY GROUP  the navigation groups (`BankReasonGroup`), alphabetical,
                each with its number of WHY and — once a WHO is
                chosen — how many of them that WHO already uses.
     WHY        the WHY of the selected group, alphabetical, each with its
                WHAT; the WHO's own WHY are marked, never the only ones
                offered. The search covers the WHOLE catalog and shows each
                hit's group; choosing a hit selects its group.

   Loading is on demand, never a WHO x WHY matrix:
     * the active WHO list and the grouped WHY catalog — once per page;
     * the WHY already associated with the chosen WHO — when it is chosen
       (and cached), only to mark them;
     * "+ Create New WHY" opens the ONE shared dialog (bank-why-create.js,
       also used by the WHO Rule modal): the WHY is saved there and comes
       back SELECTED here, already added to the chosen WHO.

   A WHY is never selected for the operator, not even when the WHO has only
   one: Confirm stays disabled until a WHO AND a WHY are chosen. */

(function () {
  "use strict";

  var overlay = document.getElementById("who-picker");
  if (!overlay || !window.RFOneModal) { return; }

  var form = document.getElementById("who-picker-form");
  var subject = document.getElementById("who-picker-subject");
  var whoHidden = document.getElementById("who-picker-occurrence-id");
  var whyHidden = document.getElementById("who-picker-reason-id");
  var whoSearch = document.getElementById("who-picker-search");
  var whoList = document.getElementById("who-picker-list");
  var whoEmpty = document.getElementById("who-picker-empty");
  var groupSearch = document.getElementById("why-group-search");
  var groupList = document.getElementById("why-group-list");
  var groupEmpty = document.getElementById("why-group-empty");
  var whyGroupLabel = document.getElementById("why-picker-group");
  var whySearch = document.getElementById("why-picker-search");
  var whyList = document.getElementById("why-picker-list");
  var whyNone = document.getElementById("why-picker-none");
  var createButton = document.getElementById("why-picker-create");
  var errorBox = document.getElementById("who-picker-error");
  var summary = document.getElementById("who-picker-summary");
  var confirmButton = document.getElementById("who-picker-confirm");

  var whosUrl = overlay.dataset.whosUrl;
  var whysTemplate = overlay.dataset.whysUrlTemplate;
  var catalogUrl = overlay.dataset.catalogUrl;
  var actionTemplate = overlay.dataset.actionTemplate;

  var OTHER = "other";        // the key of the "Other" entry (WHY in no group)

  var whos = null;            // [{id, name, aliases?}] once loaded
  var whoButtons = [];        // one button per WHO, built once
  var groups = [];            // [{id, name, count}] alphabetical, as the server sends them
  var whys = [];              // [{id, name, what, group_id}]
  var whyById = {};
  var catalogLoaded = null;   // the promise of the one catalog fetch
  var associatedCache = {};   // WHO id -> {WHY id: true}
  var associated = {};        // of the chosen WHO
  var currentGroup = null;    // group key (id as string, or OTHER)
  var pending = {};

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text != null) { node.textContent = text; }
    return node;
  }

  function groupKey(id) { return id == null ? OTHER : String(id); }

  function groupName(key) {
    var group = groups.filter(function (g) { return groupKey(g.id) === key; })[0];
    return group ? group.name : "";
  }

  function showError(message) {
    if (!errorBox) { return; }
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  function whoName(id) {
    var who = (whos || []).filter(function (w) { return String(w.id) === String(id); })[0];
    return who ? who.name : "";
  }

  // The footer says, in words, what Confirm will record.
  function sync() {
    if (!confirmButton) { return; }
    confirmButton.disabled = !(whoHidden.value && whyHidden.value);
    var parts = [];
    parts.push("WHO: " + (whoHidden.value ? whoName(whoHidden.value) : "—"));
    if (whyHidden.value && whyById[whyHidden.value]) {
      var why = whyById[whyHidden.value];
      parts.push("WHY: " + why.name + " (" + groupName(groupKey(why.group_id)) + ")");
      if (whoHidden.value && !associated[why.id]) { parts.push("will be added to this WHO's WHY"); }
    } else {
      parts.push("WHY: —");
    }
    summary.textContent = parts.join(" · ");
  }

  // ---------------------------------------------------------------- WHO
  function buildWhoList() {
    whoList.innerHTML = "";
    whoButtons = whos.map(function (who) {
      var button = el("button", "ww-option who-option");
      button.type = "button";
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", "false");
      button.dataset.occurrenceId = who.id;
      button.dataset.haystack = (who.name + " " + (who.aliases || "")).toLowerCase();
      button.appendChild(el("span", "ww-option-name", who.name));
      if (who.aliases) { button.appendChild(el("span", "ww-option-note", "Also: " + who.aliases)); }
      whoList.appendChild(button);
      return button;
    });
  }

  function filterWhos() {
    var term = whoSearch.value.trim().toLowerCase(), shown = 0;
    whoButtons.forEach(function (button) {
      var match = !term || button.dataset.haystack.indexOf(term) !== -1;
      button.hidden = !match;
      if (match) { shown += 1; }
    });
    whoEmpty.hidden = shown !== 0;
  }

  function markWho(id) {
    whoButtons.forEach(function (button) {
      var on = button.dataset.occurrenceId === String(id);
      button.classList.toggle("is-selected", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function loadWhos() {
    if (whos) { return Promise.resolve(whos); }
    whoList.innerHTML = "";
    whoList.appendChild(el("p", "ww-loading", "Loading WHO…"));
    return fetch(whosUrl, { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : []; })
      .then(function (data) { whos = data || []; buildWhoList(); return whos; });
  }

  function loadAssociated(whoId) {
    if (associatedCache[whoId]) { return Promise.resolve(associatedCache[whoId]); }
    var url = whysTemplate.replace("/whos/0/", "/whos/" + encodeURIComponent(whoId) + "/");
    return fetch(url, { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : []; })
      .then(function (data) {
        var set = {};
        (Array.isArray(data) ? data : []).forEach(function (w) { set[w.id] = true; });
        associatedCache[whoId] = set;
        return set;
      });
  }

  // Choosing a WHO refreshes the marks; the WHY already chosen stays chosen
  // (every WHY is valid for every WHO) and can be changed freely.
  function chooseWho(id, keepWhyId) {
    var who = (whos || []).filter(function (w) { return String(w.id) === String(id); })[0];
    if (!who) { return; }
    whoHidden.value = String(who.id);
    markWho(who.id);
    associated = {};
    sync();
    loadAssociated(who.id).then(function (set) {
      if (whoHidden.value !== String(who.id)) { return; }
      associated = set;
      if (keepWhyId && whyById[keepWhyId]) {
        selectWhy(keepWhyId);
      } else if (!whyHidden.value) {
        // Nothing chosen yet: open the first group this WHO already uses.
        var first = groups.filter(function (g) { return usedIn(groupKey(g.id)) > 0; })[0];
        if (first) { currentGroup = groupKey(first.id); }
      }
      renderGroups();
      renderWhys();
      sync();
    });
  }

  // ---------------------------------------------------------- WHY GROUP
  function usedIn(key) {
    return whys.filter(function (w) { return groupKey(w.group_id) === key && associated[w.id]; }).length;
  }

  function renderGroups() {
    var term = groupSearch.value.trim().toLowerCase(), shown = 0;
    groupList.innerHTML = "";
    groups.forEach(function (group) {
      var key = groupKey(group.id);
      var button = el("button", "ww-option ww-group");
      button.type = "button";
      button.setAttribute("role", "option");
      button.dataset.groupKey = key;
      var on = key === currentGroup;
      button.classList.toggle("is-selected", on);
      button.setAttribute("aria-selected", on ? "true" : "false");
      button.appendChild(el("span", "ww-option-name", group.name));
      var meta = el("span", "ww-group-meta");
      if (whoHidden.value) {
        var used = usedIn(key);
        meta.appendChild(used ? el("span", "ww-used", "● " + used) : el("span", "ww-unused", "—"));
      }
      meta.appendChild(el("span", "ww-count", String(group.count)));
      button.appendChild(meta);
      button.title = group.count + " WHY" + (whoHidden.value ? " · " + usedIn(key) + " used with this WHO" : "");
      button.hidden = !!term && group.name.toLowerCase().indexOf(term) === -1;
      if (!button.hidden) { shown += 1; }
      groupList.appendChild(button);
    });
    groupEmpty.hidden = shown !== 0;
  }

  function selectGroup(key) {
    currentGroup = key;
    whySearch.value = "";
    renderGroups();
    renderWhys();
  }

  // ---------------------------------------------------------------- WHY
  function whyButton(why, withGroup) {
    var button = el("button", "ww-option why-option");
    button.type = "button";
    button.setAttribute("role", "option");
    button.dataset.reasonId = why.id;
    var name = el("span", "ww-option-name", why.name);
    if (associated[why.id]) {
      name.appendChild(el("span", "ww-badge", "used with this WHO"));
    }
    button.appendChild(name);
    button.appendChild(el("span", "ww-option-note",
      (withGroup ? groupName(groupKey(why.group_id)) + " · " : "") + (why.what || "")));
    var on = whyHidden.value === String(why.id);
    button.classList.toggle("is-selected", on);
    button.setAttribute("aria-selected", on ? "true" : "false");
    return button;
  }

  function byName(a, b) { return a.name.localeCompare(b.name, undefined, { sensitivity: "base" }); }

  function renderWhys() {
    var term = whySearch.value.trim().toLowerCase();
    whyList.innerHTML = "";
    var list;
    if (term) {
      // The search covers the whole catalog, not only the selected group.
      list = whys.filter(function (w) {
        return (w.name + " " + (w.what || "") + " " + groupName(groupKey(w.group_id))).toLowerCase().indexOf(term) !== -1;
      });
      whyGroupLabel.textContent = "— search in all groups";
    } else {
      list = whys.filter(function (w) { return groupKey(w.group_id) === currentGroup; });
      whyGroupLabel.textContent = currentGroup ? "— " + groupName(currentGroup) : "";
    }
    list.sort(byName);
    list.forEach(function (why) { whyList.appendChild(whyButton(why, !!term)); });
    whyNone.hidden = list.length !== 0;
  }

  function selectWhy(id) {
    var why = whyById[id];
    if (!why) { return; }
    whyHidden.value = String(why.id);
    // A hit found by the search takes the operator to its group.
    currentGroup = groupKey(why.group_id);
    whySearch.value = "";
    renderGroups();
    renderWhys();
    var chosen = whyList.querySelector(".why-option.is-selected");
    if (chosen && chosen.scrollIntoView) { chosen.scrollIntoView({ block: "nearest" }); }
    var group = groupList.querySelector(".ww-group.is-selected");
    if (group && group.scrollIntoView) { group.scrollIntoView({ block: "nearest" }); }
    showError("");
    sync();
  }

  function loadCatalog() {
    if (catalogLoaded) { return catalogLoaded; }
    groupList.innerHTML = "";
    groupList.appendChild(el("p", "ww-loading", "Loading groups…"));
    catalogLoaded = fetch(catalogUrl, { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : {}; })
      .then(function (data) {
        groups = (data && data.groups) || [];
        whys = (data && data.whys) || [];
        whyById = {};
        whys.forEach(function (w) { whyById[w.id] = w; });
      });
    return catalogLoaded;
  }

  // ------------------------------------------------------ Create New WHY
  // The ONE shared flow (bank-why-create.js). The dialog opens on top of
  // this popup with the chosen WHO and the selected group; on Save the WHY
  // (new, or the existing one of that name) joins this catalog, counts as
  // used with the WHO (the dialog added the association), and is SELECTED
  // in its group — Confirm then records it for this transaction. Cancel
  // leaves this popup exactly as it was.
  function openCreate() {
    if (!window.RFOneWhyCreate) { showError("Create New WHY is not available on this page."); return; }
    showError("");
    window.RFOneWhyCreate.open({
      whoId: whoHidden.value || "",
      whoName: whoHidden.value ? whoName(whoHidden.value) : "",
      groupId: currentGroup && currentGroup !== OTHER ? currentGroup : "",
      name: whySearch.value.trim(),
      onSaved: function (why) {
        if (!whyById[why.id]) {
          var entry = { id: why.id, name: why.name, what: why.what, group_id: why.group_id };
          whys.push(entry);
          whyById[why.id] = entry;
          groups.forEach(function (g) { if (groupKey(g.id) === groupKey(why.group_id)) { g.count += 1; } });
        }
        if (whoHidden.value) {
          associatedCache[whoHidden.value] = associatedCache[whoHidden.value] || {};
          associatedCache[whoHidden.value][why.id] = true;
          associated = associatedCache[whoHidden.value];
        }
        groupSearch.value = "";
        selectWhy(why.id);
      },
    }, createButton);
  }

  // ---------------------------------------------------------- open/close
  function clearWhy() {
    whyHidden.value = "";
    whySearch.value = "";
    groupSearch.value = "";
  }

  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      showError("");
      form.action = actionTemplate.replace("/transactions/0/", "/transactions/" + encodeURIComponent(pending.transactionId) + "/");
      subject.textContent = pending.label || "";
      whoHidden.value = "";
      if (!whoList) { return; }
      whoSearch.value = "";
      associated = {};
      clearWhy();
      Promise.all([loadWhos(), loadCatalog()]).then(function () {
        filterWhos();
        markWho(null);
        var current = pending.whyId && whyById[pending.whyId];
        currentGroup = current ? groupKey(current.group_id) : (groups.length ? groupKey(groups[0].id) : null);
        renderGroups();
        renderWhys();
        sync();
        if (pending.whoId) {
          chooseWho(pending.whoId, pending.whyId);
          var chosen = whoList.querySelector(".who-option.is-selected");
          if (chosen && chosen.scrollIntoView) { chosen.scrollIntoView({ block: "center" }); }
        } else if (current) {
          selectWhy(current.id);
        }
      });
    },
    initialFocus: function () { return whoSearch || overlay.querySelector("[data-modal-close]"); },
  });

  function open(options, trigger) {
    pending = options || {};
    modal.open(trigger);
  }

  window.RFOneWhoWhy = { open: open };

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".who-picker-open");
    if (!trigger) { return; }
    event.preventDefault();
    open({
      transactionId: trigger.dataset.transactionId,
      label: trigger.dataset.transactionLabel || "",
      whoId: trigger.dataset.currentOccurrenceId || "",
      whyId: trigger.dataset.currentReasonId || "",
    }, trigger);
  });

  if (!whoList) { return; }

  whoSearch.addEventListener("input", filterWhos);
  whoList.addEventListener("click", function (event) {
    var option = event.target.closest(".who-option");
    if (option) { chooseWho(option.dataset.occurrenceId, null); }
  });
  groupSearch.addEventListener("input", renderGroups);
  groupList.addEventListener("click", function (event) {
    var option = event.target.closest(".ww-group");
    if (option) { selectGroup(option.dataset.groupKey); }
  });
  whySearch.addEventListener("input", renderWhys);
  whyList.addEventListener("click", function (event) {
    var option = event.target.closest(".why-option");
    if (option) { selectWhy(option.dataset.reasonId); }
  });
  createButton.addEventListener("click", openCreate);

  // Up/Down move between the visible options of a list; Enter picks one.
  [whoList, groupList, whyList].forEach(function (list) {
    list.addEventListener("keydown", function (event) {
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") { return; }
      var shown = Array.prototype.slice.call(list.querySelectorAll(".ww-option")).filter(function (b) { return !b.hidden; });
      if (!shown.length) { return; }
      event.preventDefault();
      var index = shown.indexOf(document.activeElement);
      var next = index === -1 ? shown[0]
        : shown[Math.max(0, Math.min(shown.length - 1, index + (event.key === "ArrowDown" ? 1 : -1)))];
      next.focus();
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    if (!whoHidden.value) { showError("Choose the WHO."); return; }
    if (!whyHidden.value) { showError("Choose the WHY."); return; }
    confirmButton.disabled = true;
    confirmButton.textContent = "Saving…";
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
        if (data && data.ok) {
          // Back on the same page differing only by #row would not reload.
          var target = new URL(data.redirect, window.location.href);
          if (target.pathname + target.search === window.location.pathname + window.location.search) {
            window.location.hash = target.hash;
            window.location.reload();
          } else {
            window.location.assign(target.href);
          }
          return;
        }
        showError((data && data.error) || "Not saved.");
        confirmButton.textContent = "Confirm";
        sync();
      })
      .catch(function () {
        showError("The server did not answer. Reload the page to see whether it was saved.");
        confirmButton.textContent = "Confirm";
        sync();
      });
  });
})();
