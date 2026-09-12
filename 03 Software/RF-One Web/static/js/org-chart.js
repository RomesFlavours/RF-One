/* Interactive Organizational Chart (TASK_ORG_CHART_ADMIN_PAGE §2/§17).
 * The hierarchy is derived from the database on every load
 * (/admin/organization/graph-data.json) — this file only renders it and
 * handles click-to-expand/collapse and click-to-edit. No JS framework, no
 * build step, matching this app's existing convention. No graphical
 * coordinate is ever the source of truth — only Position/parent_id.
 */
(function () {
  const container = document.getElementById("org-tree-root");
  const modal = document.getElementById("org-modal");
  const modalBody = document.getElementById("org-modal-body");
  const modalClose = document.getElementById("org-modal-close");

  function openModal(positionId) {
    modalBody.innerHTML = "<p class=\"empty\">Loading…</p>";
    modal.hidden = false;
    fetch("/admin/organization/positions/" + positionId + "/fragment")
      .then(function (r) { return r.text(); })
      .then(function (html) { modalBody.innerHTML = html; })
      .catch(function () { modalBody.innerHTML = "<p class=\"error\">Could not load this Position.</p>"; });
    history.replaceState(null, "", "#position-" + positionId);
  }

  function closeModal() {
    modal.hidden = true;
    history.replaceState(null, "", location.pathname);
  }

  modalClose.addEventListener("click", closeModal);
  modal.addEventListener("click", function (event) {
    if (event.target === modal) closeModal(); // backdrop click only
  });

  function buildNode(node, childrenByParent) {
    const li = document.createElement("li");

    const box = document.createElement("div");
    box.className = "org-node" + (node.gap_warning ? " org-node-warn" : "") + (node.is_active ? "" : " org-node-inactive");
    box.tabIndex = 0;
    box.setAttribute("role", "button");
    box.setAttribute("data-position-id", node.id);

    const nameEl = document.createElement("div");
    nameEl.className = "org-node-name";
    nameEl.textContent = node.name;
    box.appendChild(nameEl);

    const occupantEl = document.createElement("div");
    occupantEl.className = "org-node-occupant" + (node.vacant ? " org-node-vacant" : "");
    occupantEl.textContent = node.vacant ? "VACANT" : node.occupant_name;
    box.appendChild(occupantEl);

    const scopeEl = document.createElement("div");
    scopeEl.className = "org-node-scope";
    scopeEl.textContent = node.scope_summary;
    box.appendChild(scopeEl);

    if (node.backup_summary) {
      const backupEl = document.createElement("div");
      backupEl.className = "org-node-badge";
      backupEl.textContent = "Backup: " + node.backup_summary;
      box.appendChild(backupEl);
    }
    if (node.coverage_summary) {
      const coverageEl = document.createElement("div");
      coverageEl.className = "org-node-badge org-node-badge-warn";
      coverageEl.textContent = "Covered by: " + node.coverage_summary;
      box.appendChild(coverageEl);
    }
    if (node.gap_warning) {
      const warnEl = document.createElement("div");
      warnEl.className = "org-node-badge org-node-badge-warn";
      warnEl.textContent = "⚠ Coverage gap";
      box.appendChild(warnEl);
    }
    if (node.missing_required_backup) {
      const warnEl = document.createElement("div");
      warnEl.className = "org-node-badge org-node-badge-warn";
      warnEl.textContent = "⚠ Backup required, none set";
      box.appendChild(warnEl);
    }

    box.addEventListener("click", function () { openModal(node.id); });
    box.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openModal(node.id); }
    });

    li.appendChild(box);

    const children = childrenByParent[node.id] || [];
    if (children.length > 0) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "org-node-toggle";
      toggle.textContent = "−";
      toggle.setAttribute("aria-label", "Collapse/expand subordinate Positions");
      box.appendChild(toggle);

      const childUl = document.createElement("ul");
      children.forEach(function (child) { childUl.appendChild(buildNode(child, childrenByParent)); });
      li.appendChild(childUl);

      toggle.addEventListener("click", function (event) {
        event.stopPropagation();
        const collapsed = childUl.hidden;
        childUl.hidden = !collapsed;
        toggle.textContent = collapsed ? "−" : "+";
      });
    }

    return li;
  }

  function render(positions) {
    const byId = {};
    const childrenByParent = {};
    positions.forEach(function (p) { byId[p.id] = p; });
    positions.forEach(function (p) {
      if (p.parent_id != null && byId[p.parent_id]) {
        (childrenByParent[p.parent_id] = childrenByParent[p.parent_id] || []).push(p);
      }
    });
    const roots = positions.filter(function (p) { return p.parent_id == null || !byId[p.parent_id]; });

    container.innerHTML = "";
    if (roots.length === 0) {
      container.innerHTML = "<p class=\"empty\">No Position configured yet.</p>";
      return;
    }
    const topUl = document.createElement("ul");
    topUl.className = "org-tree";
    roots.forEach(function (root) { topUl.appendChild(buildNode(root, childrenByParent)); });
    container.appendChild(topUl);
  }

  function loadAndRender() {
    fetch("/admin/organization/graph-data.json")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        render(data.positions);
        const hash = location.hash;
        if (hash && hash.indexOf("#position-") === 0) {
          openModal(hash.replace("#position-", ""));
        }
      })
      .catch(function () {
        container.innerHTML = "<p class=\"error\">Could not load the organization graph.</p>";
      });
  }

  loadAndRender();
})();
