/* RF-One row return (UI_ROW_RETURN_001 — "UI Rules" §5)

   After an action started from a list row — Edit, Rule, Disable, Confirm,
   a select that saves on change… — the person is brought back to THAT
   record, at the same place on the screen, with focus on the control they
   used. Never back to the top of the list, also when the save reloads the
   page.

   One implementation for every RF-One list. A page opts in by loading this
   file and marking each row with a STABLE identity (never its index):

       <tr data-rr-key="who:39"> … <button>Edit</button> … </tr>

   Optional: a client-side filter (search box) whose value must survive a
   reload carries `data-rr-state` and an `id`. Server-side search, filters,
   sort and page live in the URL, which the page's own redirect keeps.

   How it works
     * A click (or a select change) inside a marked row records, in memory:
       the row key, its neighbours still shown (for a record that is gone
       afterwards), where it sits on screen and in its own scroll
       container, and which control was used.
     * Modal closed with no navigation (Cancel, Esc, ×): back to the row and
       the control at once. A refusal shown inside the modal leaves the
       modal open; the return happens when it is closed.
     * Navigation caused by the action (form post + redirect, fetch +
       reload): the record travels in sessionStorage — this tab only — and
       is used once, by the next load of the same page within a minute.
       A normal opening of a page (a link, a search, another tab) finds
       nothing and is left alone.
     * The record is looked up by its key wherever it now sits (a new sort
       position included). If it is gone (deleted, merged, filtered out)
       the next row that was shown is used, else the previous one; with an
       empty list the list area is shown as it is. Filters are never
       changed to bring a record back.

   It never changes what a page saves or which rows it shows. */

(function (global) {
  "use strict";

  var STORE = "rfone-row-return";
  var MAX_AGE_MS = 60000;   // from leaving the page to the next load
  var GRACE_MS = 2000;      // a dialog closed right before the page reloads
  var NEIGHBOURS = 40;
  var CONTROLS = "button, a[href], input[type=submit], input[type=button], select";

  var pending = null;
  var navigating = false;

  function storage() { try { return global.sessionStorage; } catch (e) { return null; } }
  function shown(el) { return !!el && !el.hidden && el.getClientRects().length > 0; }
  function rowOf(el) { return el && el.closest ? el.closest("[data-rr-key]") : null; }
  function keyOf(row) { return row.getAttribute("data-rr-key"); }
  function inDialog(el) { return !!(el.closest && el.closest("[role=dialog], dialog")); }
  function dialogOpen() {
    return Array.prototype.some.call(document.querySelectorAll("[role=dialog], dialog"), shown);
  }
  function rowsIn(list) {
    return Array.prototype.filter.call(list.children, function (r) { return r.hasAttribute("data-rr-key") && shown(r); });
  }
  function findRow(key) {
    var all = document.querySelectorAll("[data-rr-key]");
    for (var i = 0; i < all.length; i++) { if (keyOf(all[i]) === key && shown(all[i])) { return all[i]; } }
    return null;
  }
  function scroller(el) {
    for (var n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      var style = global.getComputedStyle(n);
      if (/(auto|scroll)/.test(style.overflowY) && n.scrollHeight > n.clientHeight + 1) { return n; }
    }
    return null;
  }
  function controlsOf(row) { return Array.prototype.slice.call(row.querySelectorAll(CONTROLS)); }
  function labelOf(el) {
    return (el.getAttribute("data-action") || "") + "|" + (el.getAttribute("aria-label") || el.textContent || el.value || "").trim();
  }
  function anchorOf(list) {
    for (var n = list; n && n !== document.body; n = n.parentElement) { if (n.id) { return n.id; } }
    return null;
  }

  // ------------------------------------------------------------ record
  function capture(control) {
    var row = rowOf(control);
    var list = row.parentElement;
    var rows = rowsIn(list);
    var at = rows.indexOf(row);
    var box = scroller(row);
    var rect = row.getBoundingClientRect();
    var state = {};
    Array.prototype.forEach.call(document.querySelectorAll("[data-rr-state][id]"), function (input) {
      state[input.id] = input.value;
    });
    pending = {
      key: keyOf(row),
      path: global.location.pathname,
      next: rows.slice(at + 1, at + 1 + NEIGHBOURS).map(keyOf),
      prev: rows.slice(Math.max(0, at - NEIGHBOURS), Math.max(0, at)).reverse().map(keyOf),
      list: anchorOf(list),
      viewTop: rect.top,
      boxTop: box ? rect.top - box.getBoundingClientRect().top : null,
      boxLeft: box ? box.scrollLeft : null,
      x: global.scrollX, y: global.scrollY,
      control: { index: controlsOf(row).indexOf(control), label: labelOf(control) },
      state: state,
      closed: 0,
    };
  }

  // ------------------------------------------------------------ return
  function place(p, row) {
    var box = scroller(row);
    if (box && p.boxTop != null) {
      box.scrollTop += (row.getBoundingClientRect().top - box.getBoundingClientRect().top) - p.boxTop;
      if (p.boxLeft != null) { box.scrollLeft = p.boxLeft; }
    }
    global.scrollBy(0, row.getBoundingClientRect().top - p.viewTop);
    var rect = row.getBoundingClientRect();
    if (rect.bottom <= 0 || rect.top >= global.innerHeight) { row.scrollIntoView({ block: "nearest" }); }
  }

  function focusControl(p, row) {
    var controls = controlsOf(row);
    var match = controls.filter(function (c) { return labelOf(c) === p.control.label; })[0] || controls[p.control.index];
    if (match && shown(match) && !match.disabled && typeof match.focus === "function") {
      try { match.focus({ preventScroll: true }); } catch (e) { match.focus(); }
    }
  }

  function restore(p, afterLoad) {
    if (afterLoad) {
      Object.keys(p.state || {}).forEach(function (id) {
        var input = document.getElementById(id);
        if (input && input.value !== p.state[id]) {
          input.value = p.state[id];
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
      global.scrollTo(p.x, p.y);
    }
    var row = findRow(p.key);
    var same = !!row;
    if (!row) {
      var candidates = (p.next || []).concat(p.prev || []);
      for (var i = 0; i < candidates.length && !row; i++) { row = findRow(candidates[i]); }
    }
    if (!row) {
      // Empty list: show where it is, filters and search untouched.
      var area = p.list && document.getElementById(p.list);
      if (area) {
        var r = area.getBoundingClientRect();
        if (r.bottom <= 0 || r.top >= global.innerHeight) { area.scrollIntoView({ block: "nearest" }); }
      }
      return null;
    }
    place(p, row);
    if (same && !dialogOpen()) { focusControl(p, row); }
    return { row: row, same: same };
  }

  // ------------------------------------------------------------ events
  document.addEventListener("click", function (event) {
    var control = event.target.closest && event.target.closest(CONTROLS);
    if (!control || inDialog(control)) { return; }
    if (rowOf(control)) {
      if (control.tagName !== "SELECT") { capture(control); }
      return;
    }
    // A link outside the rows is a normal opening of a page, not a return.
    if (control.matches("a[href]")) { pending = null; }
  }, true);

  document.addEventListener("change", function (event) {
    var control = event.target;
    if (control.matches && control.matches("select") && rowOf(control) && !inDialog(control)) { capture(control); }
  }, true);

  document.addEventListener("submit", function (event) {
    // A search/filter form outside the rows reopens the list on purpose.
    var form = event.target;
    if ((form.method || "").toLowerCase() === "get" && !rowOf(form) && !inDialog(form)) { pending = null; }
  }, true);

  global.addEventListener("beforeunload", function () {
    navigating = true;
    var store = storage();
    if (!store) { return; }
    if (pending && (!pending.closed || Date.now() - pending.closed < GRACE_MS)) {
      pending.at = Date.now();
      try { store.setItem(STORE, JSON.stringify(pending)); } catch (e) { /* optional */ }
    }
  });
  // Back from the bfcache: the page is not reloaded, nothing pending.
  global.addEventListener("pageshow", function (event) { if (event.persisted) { navigating = false; } });

  function onDialogClosed() {
    if (!pending || navigating) { return; }
    var p = pending;
    p.closed = Date.now();
    setTimeout(function () {
      if (pending !== p || navigating) { return; }
      restore(p, false);
      setTimeout(function () { if (pending === p) { pending = null; } }, GRACE_MS);
    }, 0);
  }

  function watchDialogs() {
    var wasOpen = dialogOpen();
    new MutationObserver(function () {
      var open = dialogOpen();
      if (wasOpen && !open) { onDialogClosed(); }
      wasOpen = open;
    }).observe(document.documentElement, {
      subtree: true, attributes: true, attributeFilter: ["hidden", "open", "class", "style"],
    });
  }

  // ------------------------------------------------------------ on load
  var saved = null;
  var store = storage();
  if (store) {
    try { saved = JSON.parse(store.getItem(STORE) || "null"); } catch (e) { saved = null; }
    try { store.removeItem(STORE); } catch (e) { /* optional */ }
  }
  if (saved && (saved.path !== global.location.pathname || !(Date.now() - saved.at < MAX_AGE_MS))) { saved = null; }
  if (saved) { try { global.history.scrollRestoration = "manual"; } catch (e) { /* optional */ } }

  function afterLoad() {
    watchDialogs();
    if (!saved) { return; }
    var p = saved;
    var touched = false;
    ["wheel", "touchstart", "keydown", "mousedown"].forEach(function (name) {
      global.addEventListener(name, function () { touched = true; }, { once: true, passive: true });
    });
    setTimeout(function () {
      global.requestAnimationFrame(function () {
        var result = restore(p, true);
        // A modal reopened by the page itself (e.g. ?edit=): the return
        // completes when that modal is closed.
        if (dialogOpen()) { p.closed = 0; pending = p; }
        // Late layout (fonts, a list drawn by script): settle once more,
        // unless the person has already moved.
        setTimeout(function () {
          if (!touched && result) {
            var row = findRow(keyOf(result.row)) || result.row;
            if (Math.abs(row.getBoundingClientRect().top - p.viewTop) > 2) { place(p, row); }
          }
        }, 350);
      });
    }, 0);
  }
  if (document.readyState === "complete") { afterLoad(); }
  else { global.addEventListener("load", afterLoad); }

  global.RFOneRowReturn = {
    pending: function () { return pending; },
  };
})(window);
