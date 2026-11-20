/* RF1 Compensation: per-person incomplete details, using the shared modal. */
(function () {
  "use strict";
  var overlay = document.getElementById("compensation-check-dialog");
  if (!overlay) return;
  var modal = RFOneModal.create({ overlay: overlay });
  var title = document.getElementById("compensation-check-title");
  var content = document.getElementById("compensation-check-content");
  document.querySelectorAll("[data-compensation-check]").forEach(function (button) {
    button.addEventListener("click", function () {
      var template = document.getElementById("compensation-check-" + button.dataset.compensationCheck);
      if (!template) return;
      title.textContent = button.dataset.personName + " · Items to check";
      content.replaceChildren(template.content.cloneNode(true));
      modal.open(button);
    });
  });
})();
