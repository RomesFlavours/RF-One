/* The simple WHO Rule modal (BANK_SIMPLE_WHO_RULE_001).

   One script for the one modal in `_bank_who_rule_modal.html`, used by
   Bank > Classification and Bank > Review Transactions. It never decides
   anything: it lets the operator pick a WHO, write the sentence, tick the
   possible WHY, and sends them to the one Apply route. A refusal comes
   back as text and is shown in the modal, next to the sentence.

   Opening: any `.who-rule-open` element (data-who-id, data-who-name,
   data-subject, data-transaction-id), or `RFOneWhoRule.open({...})`. */

(function () {
  "use strict";

  var overlay = document.getElementById("who-rule-modal");
  if (!overlay || !window.RFOneModal) { return; }

  var form = document.getElementById("who-rule-form");
  var subject = document.getElementById("who-rule-subject");
  var whoId = document.getElementById("who-rule-occurrence-id");
  var newWhoName = document.getElementById("who-rule-new-who-name");
  var newBadge = document.getElementById("who-rule-who-new");
  var transactionId = document.getElementById("who-rule-transaction-id");
  var whoName = document.getElementById("who-rule-who-name");
  var whoSearch = document.getElementById("who-rule-who-search");
  var whoResults = document.getElementById("who-rule-who-results");
  var existing = document.getElementById("who-rule-existing");
  var instruction = document.getElementById("who-rule-instruction");
  var whySearch = document.getElementById("who-rule-why-search");
  var whyLabels = Array.prototype.slice.call(overlay.querySelectorAll(".who-rule-why"));
  var whyGroups = Array.prototype.slice.call(overlay.querySelectorAll(".who-rule-why-group"));
  var whyEmpty = document.getElementById("who-rule-why-empty");
  var whyList = document.getElementById("who-rule-why-list");
  var whyCreate = document.getElementById("who-rule-why-create");
  var whyCount = document.getElementById("who-rule-why-count");
  var errorBox = document.getElementById("who-rule-error");
  var applyButton = document.getElementById("who-rule-apply");
  var optionsUrl = overlay.dataset.optionsUrl;
  var whoUrlTemplate = overlay.dataset.whoUrlTemplate;
  var searchTimer = null;
  var pending = {};

  function showError(message) {
    errorBox.textContent = message || "";
    errorBox.hidden = !message;
  }

  // Each group heading says how many of its WHY are ticked, so an
  // association is visible even in a collapsed group.
  function refreshWhyCounts() {
    var total = 0;
    whyGroups.forEach(function (group) {
      var meta = group.querySelector(".who-rule-why-group-meta");
      var ticked = group.querySelectorAll("input:checked").length;
      total += ticked;
      meta.textContent = ticked ? ticked + " selected · " + meta.dataset.total : meta.dataset.total;
      group.classList.toggle("has-selected", ticked > 0);
    });
    whyCount.textContent = total ? "(" + total + " selected)" : "";
  }

  function setWhyChecked(ids) {
    var wanted = (ids || []).map(String);
    whyLabels.forEach(function (label) {
      var box = label.querySelector("input");
      box.checked = wanted.indexOf(box.value) !== -1;
      label.classList.toggle("is-checked", box.checked);
    });
    refreshWhyCounts();
  }

  // One search across every group: a group stays visible (and opens) only
  // while it holds a match, so every result keeps its group heading.
  function filterWhy() {
    var term = whySearch.value.trim().toLowerCase();
    var any = false;
    whyGroups.forEach(function (group) {
      var visible = 0;
      group.querySelectorAll(".who-rule-why").forEach(function (label) {
        label.hidden = !!term && (label.dataset.haystack || "").indexOf(term) === -1;
        if (!label.hidden) { visible += 1; }
      });
      group.hidden = visible === 0;
      if (term && visible) { group.open = true; }
      any = any || visible > 0;
    });
    whyEmpty.hidden = any;
  }

  // ---------------------------------------------------- Create New WHY
  // The ONE shared flow (bank-why-create.js), opened on top of this modal
  // for the chosen WHO. The WHY it hands back (new, or the existing one of
  // that name) is put in its group, alphabetically — the group itself is
  // added, alphabetically, when it had no WHY to show yet — and TICKED as a
  // Possible WHY. Nothing else in the modal changes: the WHO, the Rule
  // sentence and the other ticks stay as they were. A Possible WHY is a WHO
  // association only; Apply never gives it to a transaction.
  function byText(a, b) { return a.localeCompare(b, undefined, { sensitivity: "base" }); }

  function reindexWhy() {
    whyLabels = Array.prototype.slice.call(overlay.querySelectorAll(".who-rule-why"));
    whyGroups = Array.prototype.slice.call(overlay.querySelectorAll(".who-rule-why-group"));
  }

  function groupFor(why) {
    var name = why.group_name || "Other";
    var found = whyGroups.filter(function (g) {
      return why.group_id != null ? g.dataset.groupId === String(why.group_id) : g.dataset.group === "Other";
    })[0];
    if (found) { return found; }
    var group = document.createElement("details");
    group.className = "who-rule-why-group";
    group.open = true;
    group.dataset.group = name;
    group.dataset.groupId = why.group_id != null ? String(why.group_id) : "";
    var summary = document.createElement("summary");
    var title = document.createElement("span");
    title.className = "who-rule-why-group-name";
    title.textContent = name;
    var meta = document.createElement("span");
    meta.className = "who-rule-why-group-meta";
    meta.dataset.total = "0";
    summary.appendChild(title);
    summary.appendChild(document.createTextNode(" "));
    summary.appendChild(meta);
    var items = document.createElement("div");
    items.className = "who-rule-why-items";
    group.appendChild(summary);
    group.appendChild(items);
    // Alphabetical among the groups; "Other" (WHY in no group) stays last.
    var before = whyGroups.filter(function (g) {
      return g.dataset.group === "Other" || (name !== "Other" && byText(g.dataset.group, name) > 0);
    })[0];
    whyList.insertBefore(group, before || whyEmpty);
    return group;
  }

  function boxFor(why) {
    var box = whyList.querySelector('input[name="transaction_reason_id"][value="' + String(why.id) + '"]');
    if (box) { return box.closest(".who-rule-why"); }
    var group = groupFor(why);
    var label = document.createElement("label");
    label.className = "who-rule-why";
    label.dataset.haystack = (why.name + " " + (why.code || "") + " " + group.dataset.group).toLowerCase();
    var input = document.createElement("input");
    input.type = "checkbox";
    input.name = "transaction_reason_id";
    input.value = String(why.id);
    var text = document.createElement("span");
    text.textContent = why.name;
    label.appendChild(input);
    label.appendChild(document.createTextNode(" "));
    label.appendChild(text);
    var items = group.querySelector(".who-rule-why-items");
    var after = Array.prototype.slice.call(items.querySelectorAll(".who-rule-why")).filter(function (l) {
      return byText(l.textContent.trim(), why.name) > 0;
    })[0];
    items.insertBefore(label, after || null);
    var meta = group.querySelector(".who-rule-why-group-meta");
    meta.dataset.total = String(Number(meta.dataset.total || 0) + 1);
    reindexWhy();
    return label;
  }

  function openCreate() {
    if (!window.RFOneWhyCreate) { showError("Create New WHY is not available on this page."); return; }
    var name = whoId.value ? whoName.textContent : (newWhoName.value || "");
    window.RFOneWhyCreate.open({
      whoId: whoId.value || "",
      whoName: name && name !== "—" ? name : "",
      name: whySearch.value.trim(),
      onSaved: function (why) {
        var label = boxFor(why);
        whySearch.value = "";
        filterWhy();
        var box = label.querySelector("input");
        box.checked = true;
        label.classList.add("is-checked");
        var group = label.closest(".who-rule-why-group");
        if (group) { group.open = true; }
        refreshWhyCounts();
        if (label.scrollIntoView) { label.scrollIntoView({ block: "nearest" }); }
      },
    }, whyCreate);
  }

  // A Manual Only WHO takes no WHO Rule (BANK_WHO_MANUAL_ONLY_001): the
  // modal says so and Apply stays off; the server refuses it anyway.
  function setManualOnly(isManual, name) {
    applyButton.disabled = !!isManual;
    if (isManual) {
      showError("“" + name + "” is Manual Only: it is reconciled by hand and takes no WHO Rule.");
    } else if (errorBox.dataset.manual) {
      showError("");
    }
    errorBox.dataset.manual = isManual ? "1" : "";
  }

  function chooseWho(id, name) {
    whoId.value = id ? String(id) : "";
    newWhoName.value = "";
    newBadge.hidden = true;
    whoName.textContent = name || "—";
    whoResults.hidden = true;
    whoResults.innerHTML = "";
    whoSearch.value = "";
    existing.hidden = true;
    setWhyChecked([]);
    setManualOnly(false);
    if (!id) { return; }
    // What this WHO already has: its possible WHY are pre-ticked, so Apply
    // only ever adds to them; its rules are named so nothing is duplicated
    // unknowingly.
    fetch(whoUrlTemplate.replace("/who/0", "/who/" + encodeURIComponent(id)), { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (data) {
        if (!data || String(data.id) !== whoId.value) { return; }
        whoName.textContent = data.name;
        // An empty Rule is proposed from the WHO's own name — editable, never
        // applied without Apply — so choosing a WHO never leaves a form that
        // cannot be sent (BANK_MANUAL_WHO_WHY_001).
        if (!instruction.value.trim()) {
          instruction.value = "Dove nella descrizione trovi " + data.name + " il WHO è " + data.name;
        }
        setWhyChecked(data.possible_why_ids);
        setManualOnly(data.manual_only, data.name);
        if (data.rules && data.rules.length) {
          existing.textContent = "Already recognised when the description " + data.rules.join("; ") + ".";
          existing.hidden = false;
        }
      })
      .catch(function () { /* the modal still works without the summary */ });
  }

  // A WHO that does not exist yet: nothing is created here. Apply creates
  // it, in the same transaction as its rule and its possible WHY.
  function chooseNewWho(name) {
    chooseWho("", name);
    newWhoName.value = name;
    newBadge.hidden = false;
  }

  function optionButton(option, note) {
    var button = document.createElement("button");
    button.type = "button";
    button.className = "who-option";
    button.setAttribute("role", "option");
    button.dataset.occurrenceId = option.id;
    var name = document.createElement("span");
    name.className = "who-option-name";
    name.textContent = option.name;
    button.appendChild(name);
    if (note) {
      var type = document.createElement("span");
      type.className = "who-option-type";
      type.textContent = note;
      button.appendChild(type);
    }
    return button;
  }

  function heading(text) {
    var label = document.createElement("p");
    label.className = "cell-note who-rule-combo-heading";
    label.textContent = text;
    return label;
  }

  // The creatable combo: existing WHO first, then the names that only look
  // alike (offered, never chosen), then "Create" when the typed name is new.
  // A typed name that already IS an existing WHO (same identity or alias)
  // offers that WHO and no Create, so no duplicate can be made from here.
  function renderOptions(data) {
    whoResults.innerHTML = "";
    var shown = {};
    if (data.identity) {
      whoResults.appendChild(heading("Existing WHO"));
      whoResults.appendChild(optionButton(data.identity, "This name is already this WHO"));
      shown[data.identity.id] = true;
    }
    var matches = (data.matches || []).filter(function (o) { return !shown[o.id]; });
    if (matches.length) {
      if (!data.identity) { whoResults.appendChild(heading("Existing WHO")); }
      matches.forEach(function (o) { whoResults.appendChild(optionButton(o)); shown[o.id] = true; });
    }
    var similar = (data.similar || []).filter(function (o) { return !shown[o.id]; });
    if (similar.length) {
      whoResults.appendChild(heading("Similar existing WHO — choose one only if it is the same counterparty"));
      similar.forEach(function (o) { whoResults.appendChild(optionButton(o)); });
    }
    if (data.create) {
      whoResults.appendChild(heading("Create new"));
      var create = document.createElement("button");
      create.type = "button";
      create.className = "who-option who-option-create";
      create.setAttribute("role", "option");
      create.dataset.createName = data.create;
      var label = document.createElement("span");
      label.className = "who-option-name";
      label.textContent = "Create “" + data.create + "”";
      create.appendChild(label);
      whoResults.appendChild(create);
    } else if (data.held) {
      whoResults.appendChild(heading("This name cannot be created: " + data.held + "."));
    }
    whoResults.hidden = false;
  }

  function searchWho() {
    var term = whoSearch.value.trim();
    if (!term) { whoResults.hidden = true; whoResults.innerHTML = ""; return; }
    fetch(optionsUrl + "?q=" + encodeURIComponent(term), { credentials: "same-origin" })
      .then(function (response) { return response.ok ? response.json() : {}; })
      .then(function (data) {
        if (whoSearch.value.trim() === term) { renderOptions(data || {}); }
      })
      .catch(function () { renderOptions({}); });
  }

  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      showError("");
      form.reset();
      whyLabels.forEach(function (label) { label.hidden = false; });
      whyGroups.forEach(function (group) { group.hidden = false; group.open = true; });
      whyEmpty.hidden = true;
      subject.textContent = pending.subject || "";
      subject.hidden = !pending.subject;
      transactionId.value = pending.transactionId || "";
      applyButton.disabled = false;
      applyButton.textContent = "Apply";
      chooseWho(pending.whoId, pending.whoName);
    },
    initialFocus: function () { return instruction; },
  });

  function open(options, trigger) {
    pending = options || {};
    modal.open(trigger);
  }

  window.RFOneWhoRule = { open: open };

  // A Review row names its transaction in its own cells; reading them
  // keeps every row's Rule button down to two small attributes.
  function rowSubject(trigger) {
    var row = trigger.closest("tr");
    if (!row) { return ""; }
    var date = row.querySelector(".col-date");
    var description = row.querySelector(".col-description");
    return [date, description].filter(Boolean).map(function (cell) {
      return cell.textContent.trim();
    }).join(" · ");
  }

  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".who-rule-open");
    if (!trigger) { return; }
    event.preventDefault();
    open({
      whoId: trigger.dataset.whoId || "",
      whoName: trigger.dataset.whoName || "",
      subject: trigger.dataset.subject || rowSubject(trigger),
      transactionId: trigger.dataset.transactionId || "",
    }, trigger);
  });

  whoSearch.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchWho, 200);
  });

  whoResults.addEventListener("click", function (event) {
    var option = event.target.closest(".who-option");
    if (!option) { return; }
    if (option.dataset.createName) {
      chooseNewWho(option.dataset.createName);
    } else {
      var named = option.querySelector(".who-option-name");
      chooseWho(option.dataset.occurrenceId, named ? named.textContent : "");
    }
    instruction.focus();
  });

  whySearch.addEventListener("input", filterWhy);
  if (whyCreate) { whyCreate.addEventListener("click", openCreate); }

  overlay.querySelector("#who-rule-why-list").addEventListener("change", function (event) {
    var label = event.target.closest(".who-rule-why");
    if (label) { label.classList.toggle("is-checked", event.target.checked); }
    refreshWhyCounts();
  });

  // Back to the page the modal was opened from, at its anchor (Classification:
  // #who-classification). The same page is RELOADED — assigning the same URL
  // with only a fragment would scroll without showing the Apply result.
  function goBack(url) {
    var target = new URL(url, window.location.href);
    if (target.pathname === window.location.pathname && target.search === window.location.search) {
      if (target.hash && target.hash !== window.location.hash) {
        window.history.replaceState(null, "", target.hash);
      }
      window.location.reload();
    } else {
      window.location.assign(target.href);
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    if (!whoId.value && !newWhoName.value) {
      showError("Choose the WHO this rule recognises, or create it.");
      whoSearch.focus();
      return;
    }
    if (!instruction.value.trim()) { showError("Write the rule."); instruction.focus(); return; }
    applyButton.disabled = true;
    applyButton.textContent = "Applying…";
    fetch(form.action, {
      method: "POST", body: new FormData(form), credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" },
    })
      .then(function (response) {
        return response.json().catch(function () {
          return { ok: false, error: "The rule could not be applied (HTTP " + response.status + "). Reload the page and try again." };
        });
      })
      .then(function (data) {
        if (data && data.ok) {
          goBack(data.redirect);
          return;
        }
        showError((data && data.error) || "The rule could not be applied.");
        applyButton.disabled = false;
        applyButton.textContent = "Apply";
      })
      .catch(function () {
        showError("The server did not answer. Reload the page to see whether the rule was applied.");
        applyButton.disabled = false;
        applyButton.textContent = "Apply";
      });
  });
})();
