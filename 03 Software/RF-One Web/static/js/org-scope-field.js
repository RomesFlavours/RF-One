/* Structured Position Scope input (TASK_ORG_CHART_ADMIN_PAGE §5): the
 * user never types a free-text Scope description. Depending on the chosen
 * scope_type, exactly one of the following becomes visible and named
 * appropriately: a Restaurant dropdown, a Legal Entity dropdown, a
 * Process Phase dropdown, a generic numeric id (for the scope kinds with
 * no table of their own yet), or a generic string key (for Domain/Module/
 * Process). No JS framework — plain DOM, matching this app's existing
 * convention.
 */
(function () {
  const ID_KINDS = ["CORPORATE", "BRAND", "OPERATIONAL_UNIT", "OPERATIONAL_AREA"];
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
