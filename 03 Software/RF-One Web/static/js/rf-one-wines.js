/* Restaurant > Wines page helpers (RESTAURANT_WINES_FIRST_RELEASE_001).

   * `RFOneWines.post(url, form)` — a dialog save sent with fetch. It uses
     the shared busy indicator (`rf-one-busy.js`, RFOneBusy.start/stop:
     wait cursor at once, spinner after one second) and counts the requests
     still pending, so overlapping requests never clear the indicator
     early. The shared indicator itself is not changed.
   * `RFOneWines.typeCombo(...)` — the searchable Wine type field: the
     person types any name (standard or alternative) and the field resolves
     it to the one type it identifies.
   * `RFOneWines.typeDialog(...)` — the Wine type dialog, used on the Wine
     Types page and, stacked over the wine dialog, from its "+" button.
     Saving a new type never touches the dialog underneath. */

(function (global) {
  "use strict";

  var pending = 0;

  function busyStart() {
    pending += 1;
    if (pending === 1 && global.RFOneBusy) { global.RFOneBusy.start(); }
  }

  function busyStop() {
    pending = Math.max(0, pending - 1);
    if (pending === 0 && global.RFOneBusy) { global.RFOneBusy.stop(); }
  }

  function csrfToken() {
    var field = document.querySelector("input[name=csrf_token]");
    return field ? field.value : "";
  }

  // Resolves to the JSON answer; `keepBusy` leaves the indicator on when
  // the caller is about to navigate (the next page clears it).
  function request(url, init, keepBusy) {
    busyStart();
    var stopped = false;
    function stop() { if (!stopped) { stopped = true; busyStop(); } }
    return fetch(url, init).then(function (response) {
      return response.json().catch(function () {
        return { ok: false, error: "The server answered unexpectedly (" + response.status + ")." };
      });
    }, function () {
      return { ok: false, error: "The server could not be reached. Nothing was saved." };
    }).then(function (data) {
      if (!(data && data.ok && keepBusy)) { stop(); }
      return data;
    });
  }

  function post(url, formData, keepBusy) {
    if (!formData.has("csrf_token")) { formData.append("csrf_token", csrfToken()); }
    return request(url, { method: "POST", body: formData, credentials: "same-origin",
                          headers: { "Accept": "application/json" } }, keepBusy);
  }

  function get(url) {
    return request(url, { credentials: "same-origin", headers: { "Accept": "application/json" } }, false);
  }

  // Same comparison the server makes (accents, case, punctuation ignored).
  function nameKey(text) {
    return String(text || "").normalize("NFKD").replace(/[̀-ͯ]/g, "")
      .toLowerCase().replace(/[^0-9a-z]+/g, " ").trim();
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { node.setAttribute(k, attrs[k]); });
    if (text != null) { node.textContent = text; }
    return node;
  }

  /* Searchable Wine type field.
     input: visible text field; hidden: the wine_type_id field; hint: where
     the resolved type is announced; datalist: suggestions; types: [{id,
     name, aliases}]. */
  function typeCombo(cfg) {
    var byKey = {};
    var types = [];

    function index(type) {
      types = types.filter(function (t) { return t.id !== type.id; }).concat([type]);
      types.sort(function (a, b) { return a.name.localeCompare(b.name); });
      byKey = {};
      types.forEach(function (t) {
        byKey[nameKey(t.name)] = t;
        (t.aliases || []).forEach(function (a) { byKey[nameKey(a)] = t; });
      });
      cfg.datalist.innerHTML = "";
      types.forEach(function (t) {
        cfg.datalist.appendChild(el("option", { value: t.name }));
        (t.aliases || []).forEach(function (a) {
          cfg.datalist.appendChild(el("option", { value: a, label: a + " → " + t.name }));
        });
      });
    }

    function resolve() {
      var text = cfg.input.value;
      var type = byKey[nameKey(text)];
      cfg.hidden.value = type ? String(type.id) : "";
      if (!text.trim()) {
        cfg.hint.textContent = "";
      } else if (!type) {
        cfg.hint.textContent = "Not a known type — pick one from the list or add it with +.";
      } else if (nameKey(type.name) !== nameKey(text)) {
        cfg.hint.textContent = "→ " + type.name;
      } else {
        cfg.hint.textContent = "";
      }
      return type;
    }

    (cfg.types || []).forEach(index);
    cfg.input.addEventListener("input", resolve);
    cfg.input.addEventListener("change", resolve);

    return {
      add: function (type) { index(type); },
      select: function (type) {
        index(type);
        cfg.input.value = type.name;
        resolve();
      },
      setById: function (id) {
        var t = types.filter(function (x) { return x.id === id; })[0];
        cfg.input.value = t ? t.name : "";
        resolve();
      },
      resolve: resolve,
    };
  }

  /* The Wine type dialog. cfg.overlay is the `.org-modal-overlay`;
     cfg.createUrl / cfg.updateUrl(id) are the save addresses; cfg.onSaved
     receives the saved type. */
  function typeDialog(cfg) {
    var overlay = cfg.overlay;
    var form = overlay.querySelector("form");
    var title = overlay.querySelector("[data-type-title]");
    var error = overlay.querySelector("[data-type-error]");
    var editingId = null;
    var modal = global.RFOneModal.create({
      overlay: overlay,
      initialFocus: function () { return form.elements.standard_name; },
    });

    function open(trigger, type, presetName) {
      editingId = type ? type.id : null;
      title.textContent = type ? "Edit wine type" : "New wine type";
      form.elements.standard_name.value = type ? type.name : (presetName || "");
      form.elements.aliases.value = type ? (type.aliases || []).join("\n") : "";
      error.hidden = true;
      modal.open(trigger);
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var url = editingId ? cfg.updateUrl(editingId) : cfg.createUrl;
      post(url, new FormData(form), false).then(function (data) {
        if (!data.ok) {
          error.textContent = data.error;
          error.hidden = false;
          return;
        }
        modal.close();
        cfg.onSaved(data.type, editingId === null);
      });
    });

    return { open: open, close: modal.close };
  }

  global.RFOneWines = {
    post: post, get: get, nameKey: nameKey, typeCombo: typeCombo, typeDialog: typeDialog,
    busyStart: busyStart, busyStop: busyStop,
  };
})(window);
