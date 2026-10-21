/* Bank > Review Transactions — column filters (BANK_REVIEW_COLUMN_FILTERS_001), To Reconcile and Reconciled.

   Under each data column title: "Search" opens one dialog ("Search <column>", the current filter's text, focus in
   the field); OK or Enter reloads the list with THAT column's filter (`f_<column>`) changed and every other filter,
   the search and the sort kept; Cancel or Esc closes it and changes nothing. On "Account / Card · For Whom" two
   radio buttons choose where to look (`f_instrument_in`). "All" removes only that column's filter (a link built by
   the server). The server filters every movement the other filters keep, before the 500-row limit.

   The page keeps its vertical position across these reloads (this tab only, used once, within a minute), and a row
   changed but not saved (Reconciled: tr[data-unsaved]) is never lost silently: the person is asked first. */
(function () {
  "use strict";

  var STORE = "rfone-review-column-filters-scroll";
  var MAX_AGE_MS = 60000;
  var overlay = document.getElementById("col-filter-modal");
  if (!overlay) { return; }
  var panel = overlay.querySelector("[role=dialog]");
  var form = document.getElementById("col-filter-form");
  var title = document.getElementById("col-filter-title");
  var field = document.getElementById("col-filter-text");
  var targets = document.getElementById("col-filter-targets");
  var inAccount = document.getElementById("col-filter-in-account");
  var inForWhom = document.getElementById("col-filter-in-for-whom");
  var cancel = document.getElementById("col-filter-cancel");
  var current = null;   // the column the dialog was opened from

  function storage() { try { return window.sessionStorage; } catch (e) { return null; } }

  // --- the page keeps its place ------------------------------------------
  (function restore() {
    var store = storage();
    var saved = null;
    try { saved = store && JSON.parse(store.getItem(STORE) || "null"); } catch (e) { saved = null; }
    if (store) { try { store.removeItem(STORE); } catch (e) { /* nothing to clean */ } }
    if (!saved || saved.path !== window.location.pathname || Date.now() - saved.at > MAX_AGE_MS) { return; }
    function place() { window.scrollTo(0, saved.y); }
    place();
    if (document.readyState === "complete") { place(); } else { window.addEventListener("load", place); }
  })();

  function rememberPlace() {
    var store = storage();
    if (!store) { return; }
    try { store.setItem(STORE, JSON.stringify({ path: window.location.pathname, y: window.scrollY, at: Date.now() })); }
    catch (e) { /* the page simply opens at the top */ }
  }

  // --- never lose a change silently ---------------------------------------
  function mayLeave() {
    var unsaved = document.querySelectorAll("tr[data-unsaved]").length;
    if (!unsaved) { return true; }
    return window.confirm(unsaved + " row(s) changed and not saved. Searching reloads the list and these changes " +
                          "are lost. Continue?");
  }

  function go(url) {
    if (!mayLeave()) { return false; }
    rememberPlace();
    window.location.assign(url);
    return true;
  }

  // --- the dialog ----------------------------------------------------------
  var modal = window.RFOneModal ? window.RFOneModal.create({ overlay: overlay, panel: panel }) : null;

  function open(link) {
    current = { key: link.getAttribute("data-col-filter"), label: link.getAttribute("data-col-label") };
    title.textContent = "Search " + current.label;
    field.value = link.getAttribute("data-col-value") || "";
    var instrument = current.key === "instrument";
    targets.hidden = !instrument;
    if (instrument) {
      (link.getAttribute("data-col-target") === "for_whom" ? inForWhom : inAccount).checked = true;
    }
    if (modal) { modal.open(link); } else { overlay.hidden = false; }
    window.setTimeout(function () { field.focus(); field.select(); }, 0);
  }

  function close() {
    if (modal) { modal.close(); } else { overlay.hidden = true; }
    current = null;
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("[data-col-filter]");
    if (link) {
      event.preventDefault();
      open(link);
      return;
    }
    var nav = event.target.closest && event.target.closest("a[data-col-nav]");
    if (nav && !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey) {
      event.preventDefault();
      go(nav.href);
    }
  });

  cancel.addEventListener("click", close);

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!current) { return; }
    var url = new URL(window.location.href);
    var text = field.value.trim();
    var name = "f_" + current.key;
    if (text) { url.searchParams.set(name, text); } else { url.searchParams.delete(name); }
    if (current.key === "instrument") {
      if (text && inForWhom.checked) { url.searchParams.set("f_instrument_in", "for_whom"); }
      else { url.searchParams.delete("f_instrument_in"); }
    }
    var target = url.toString();
    close();
    go(target);
  });
})();
