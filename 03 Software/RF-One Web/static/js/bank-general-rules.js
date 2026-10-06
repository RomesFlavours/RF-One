/* General Rules on Bank > Classification (BANK_GENERAL_RULES_001).
   One modal for "+ New General Rule" and "Edit": it only fills the form;
   saving is an ordinary POST to /bank/general-rules/save. */
(function () {
  "use strict";
  var overlay = document.getElementById("general-rule-modal");
  if (!overlay || !window.RFOneModal) { return; }
  var fields = {
    id: document.getElementById("general-rule-id"),
    name: document.getElementById("general-rule-name"),
    start: document.getElementById("general-rule-start"),
    end: document.getElementById("general-rule-end"),
    active: document.getElementById("general-rule-active"),
  };
  var title = document.getElementById("general-rule-modal-title");
  var pending = {};
  var modal = window.RFOneModal.create({
    overlay: overlay,
    onOpen: function () {
      fields.id.value = pending.ruleId || "";
      fields.name.value = pending.name || "";
      fields.start.value = pending.start || "";
      fields.end.value = pending.end || "";
      fields.active.checked = pending.active !== "0";
      title.textContent = pending.ruleId ? "Edit General Rule" : "New General Rule";
    },
    initialFocus: function () { return fields.name; },
  });
  document.addEventListener("click", function (event) {
    var trigger = event.target.closest(".general-rule-open");
    if (!trigger) { return; }
    event.preventDefault();
    pending = { ruleId: trigger.dataset.ruleId, name: trigger.dataset.name, start: trigger.dataset.start,
                end: trigger.dataset.end, active: trigger.dataset.active };
    modal.open(trigger);
  });
})();
