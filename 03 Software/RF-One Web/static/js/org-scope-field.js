/* Structured Position Scope input (TASK_ORG_CHART_ADMIN_PAGE §5): the
 * user never types a free-text Scope description. Depending on the chosen
 * scope_type, exactly one of the following becomes visible and named
 * appropriately: a Restaurant dropdown, an Operational Unit (Location)
 * dropdown, a Legal Entity dropdown, a Process Phase dropdown, a generic
 * numeric id (for the scope kinds with no table of their own yet), or a
 * generic string key (for Domain/Module/Process). No JS framework — plain
 * DOM, matching this app's existing convention.
 *
 * OPERATIONAL_UNIT has its own dropdown (TASK_ORG_RUNTIME_CONSISTENCY_
 * FIXES §1) rather than sharing RESTAURANT's id space or the generic
 * numeric-id group: it is presented against `Location`, kept independently
 * scoped from RESTAURANT (a real, documented distinction — see the
 * scope-constants comment in `models.py`).
 */
(function () {
  const ID_KINDS = ["CORPORATE", "BRAND", "OPERATIONAL_AREA"];
  const KEY_KINDS = ["DOMAIN", "MODULE", "PROCESS"];

  function wireScopeField(container) {
    const typeSelect = container.querySelector("select[name='scope_type']");
    if (!typeSelect) return;
    const groups = container.querySelectorAll("[data-scope-value-for]");

    function update() {
      const kind = typeSelect.value;
      let visibleKey = kind;
      if (ID_KINDS.includes(kind)) visibleKey = "GENERIC_ID";
      else if (KEY_KINDS.includes(kind)) visibleKey = "GENERIC_KEY";
      else if (kind === "GLOBAL") visibleKey = "NONE";

      groups.forEach(function (el) {
        const matches = el.getAttribute("data-scope-value-for") === visibleKey;
        el.hidden = !matches;
        el.querySelectorAll("input, select").forEach(function (field) {
          field.disabled = !matches;
        });
      });
    }

    typeSelect.addEventListener("change", update);
    update();
  }

  document.querySelectorAll(".scope-field").forEach(wireScopeField);
})();
