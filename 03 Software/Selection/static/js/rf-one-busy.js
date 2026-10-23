/* RF-One busy indicator (COMPENSATION_PERIOD_SUMMARY_001)

   The behaviour every server action should have: the moment a form is
   submitted (or a link marked `data-rf-busy` is followed) the WHOLE page
   shows the wait cursor; if the server has not answered after one second,
   a spinner appears as well. Both disappear when the page is shown again
   (including a return through the browser's back/forward cache).

   One implementation for every page that loads it — no page keeps its own
   copy. Pages opt in by loading this file; nothing else is required. The
   style is injected here so the file is self-contained. */

(function (global) {
  "use strict";

  var SPINNER_DELAY_MS = 1000;
  var timer = null;
  var spinner = null;

  function injectStyle() {
    if (document.getElementById("rf-busy-style")) { return; }
    var style = document.createElement("style");
    style.id = "rf-busy-style";
    style.textContent =
      "html.rf-busy, html.rf-busy * { cursor: wait !important; }" +
      ".rf-busy-spinner { position: fixed; inset: 0; display: flex; align-items: center;" +
      " justify-content: center; background: rgba(255,255,255,.35); z-index: 9999; }" +
      ".rf-busy-spinner[hidden] { display: none !important; }" +
      ".rf-busy-spinner span { width: 42px; height: 42px; border-radius: 50%;" +
      " border: 4px solid rgba(0,0,0,.15); border-top-color: rgba(0,0,0,.6);" +
      " animation: rf-busy-spin .8s linear infinite; }" +
      "@keyframes rf-busy-spin { to { transform: rotate(360deg); } }";
    document.head.appendChild(style);
  }

  function ensureSpinner() {
    if (spinner) { return spinner; }
    spinner = document.createElement("div");
    spinner.className = "rf-busy-spinner";
    spinner.setAttribute("role", "status");
    spinner.setAttribute("aria-label", "Working…");
    spinner.hidden = true;
    spinner.appendChild(document.createElement("span"));
    document.body.appendChild(spinner);
    return spinner;
  }

  function start() {
    document.documentElement.classList.add("rf-busy");
    clearTimeout(timer);
    timer = setTimeout(function () { ensureSpinner().hidden = false; }, SPINNER_DELAY_MS);
  }

  function stop() {
    clearTimeout(timer);
    timer = null;
    document.documentElement.classList.remove("rf-busy");
    if (spinner) { spinner.hidden = true; }
  }

  injectStyle();

  // Capture phase, and only when no other handler cancelled the submit
  // (checked on the next tick), so a validation that blocks the submit
  // never leaves the page looking busy.
  document.addEventListener("submit", function (event) {
    setTimeout(function () { if (!event.defaultPrevented) { start(); } }, 0);
  }, true);

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-rf-busy]");
    if (link && !event.defaultPrevented && event.button === 0 && !event.metaKey && !event.ctrlKey) {
      start();
    }
  });

  global.addEventListener("pageshow", stop);

  global.RFOneBusy = { start: start, stop: stop };
})(window);
