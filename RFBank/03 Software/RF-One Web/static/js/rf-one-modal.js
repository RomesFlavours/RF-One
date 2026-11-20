/* RF-One shared modal controller
   (BANK_SETTLEMENT_UI_AND_MODAL_REPAIR_001)

   One controller for every RF-One dialog, because the defects this
   replaces were behavioural, not cosmetic, and fixing them once is the
   only way they stay fixed:

     * the overlay was toggled with the `hidden` attribute while its class
       set `display: flex`, so it never actually hid — a full-screen
       backdrop stayed over the page and swallowed every click. The CSS
       now carries a `[hidden] { display: none !important }` guard, and
       this controller additionally sets `aria-hidden` so assistive
       technology agrees with what is painted;
     * Escape was bound to the overlay, so it only worked while focus
       happened to be inside it. It is bound to the document here, and
       only the TOPMOST open dialog reacts;
     * nothing restored focus or page scroll, so closing a dialog left the
       reader somewhere else on the page.

   Usage:  RFOneModal.create({ overlay, panel, onOpen, onClose })
   The returned handle exposes `open(trigger)`, `close()` and `isOpen()`.
   Repeated open/close is explicitly supported: no state is left behind. */

(function (global) {
  "use strict";

  var openStack = [];

  function focusableWithin(root) {
    var selector = [
      "a[href]", "button:not([disabled])", "input:not([disabled]):not([type=hidden])",
      "select:not([disabled])", "textarea:not([disabled])", "[tabindex]:not([tabindex='-1'])",
    ].join(",");
    return Array.prototype.filter.call(
      root.querySelectorAll(selector),
      function (element) { return element.offsetParent !== null || element === document.activeElement; }
    );
  }

  function create(config) {
    var overlay = config.overlay;
    var panel = config.panel || overlay.querySelector(".org-modal-panel") || overlay;
    if (!overlay) { return null; }

    var lastTrigger = null;
    var handle = {};

    function isOpen() {
      return !overlay.hasAttribute("hidden");
    }

    function open(trigger) {
      if (isOpen()) { return; }
      lastTrigger = trigger || document.activeElement;
      overlay.removeAttribute("hidden");
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("modal-open");
      openStack.push(handle);
      if (typeof config.onOpen === "function") { config.onOpen(trigger); }
      var target = config.initialFocus ? config.initialFocus() : focusableWithin(panel)[0];
      if (target) { target.focus(); }
    }

    function close() {
      if (!isOpen()) { return; }
      overlay.setAttribute("hidden", "");
      overlay.setAttribute("aria-hidden", "true");
      var index = openStack.indexOf(handle);
      if (index !== -1) { openStack.splice(index, 1); }
      // Only the last dialog releases the page: nested dialogs must not
      // unlock scrolling for the one still open underneath.
      if (!openStack.length) { document.body.classList.remove("modal-open"); }
      if (typeof config.onClose === "function") { config.onClose(); }
      // Focus goes back where it came from, so closing never teleports the
      // reader to the top of the document.
      if (lastTrigger && typeof lastTrigger.focus === "function" && document.contains(lastTrigger)) {
        lastTrigger.focus();
      }
      lastTrigger = null;
    }

    // A click that STARTS and ENDS on the backdrop closes. Using mouseup as
    // well as mousedown avoids closing when a drag-select inside the panel
    // happens to release over the backdrop.
    var pressedOnBackdrop = false;
    overlay.addEventListener("mousedown", function (event) {
      pressedOnBackdrop = event.target === overlay;
    });
    overlay.addEventListener("mouseup", function (event) {
      if (pressedOnBackdrop && event.target === overlay) { close(); }
      pressedOnBackdrop = false;
    });

    Array.prototype.forEach.call(
      overlay.querySelectorAll("[data-modal-close]"),
      function (button) {
        button.addEventListener("click", function (event) {
          event.preventDefault();
          close();
        });
      }
    );

    handle.open = open;
    handle.close = close;
    handle.isOpen = isOpen;
    handle.overlay = overlay;
    handle.panel = panel;

    // Start closed and consistent, whatever the server rendered.
    overlay.setAttribute("hidden", "");
    overlay.setAttribute("aria-hidden", "true");
    return handle;
  }

  // Escape and focus trapping are bound ONCE, at document level, and act
  // on the topmost open dialog only.
  document.addEventListener("keydown", function (event) {
    if (!openStack.length) { return; }
    var top = openStack[openStack.length - 1];
    if (event.key === "Escape") {
      event.preventDefault();
      top.close();
      return;
    }
    if (event.key === "Tab") {
      var focusable = focusableWithin(top.panel);
      if (!focusable.length) { return; }
      var first = focusable[0];
      var last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });

  global.RFOneModal = { create: create, openCount: function () { return openStack.length; } };
})(window);
