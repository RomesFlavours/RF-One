/* Browser-only layout preferences; no operational records are changed. */
(() => {
  const container = document.getElementById('configuration-blocks');
  const key = 'rfone.selection.configuration.blocks.v1';
  const blocks = () => Array.from(container.children);
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(key)) || {}; } catch (_) {}
  if (Array.isArray(saved.order)) saved.order.forEach(id => {
    const block = blocks().find(b => b.dataset.configurationBlock === id);
    if (block) container.append(block);
  });
  function update() {
    const rows = blocks();
    rows.forEach((block, index) => {
      block.querySelector('[data-move="up"]').disabled = index === 0;
      block.querySelector('[data-move="down"]').disabled = index === rows.length - 1;
    });
  }
  function persist() {
    const rows = blocks();
    const expanded = {};
    rows.forEach(b => { expanded[b.dataset.configurationBlock] = b.querySelector('.configuration-toggle').getAttribute('aria-expanded') === 'true'; });
    try { localStorage.setItem(key, JSON.stringify({order: rows.map(b => b.dataset.configurationBlock), expanded})); } catch (_) {}
  }
  blocks().forEach(block => {
    const toggle = block.querySelector('.configuration-toggle');
    const body = document.getElementById(toggle.getAttribute('aria-controls'));
    if (saved.expanded && saved.expanded[block.dataset.configurationBlock] === false) {
      toggle.setAttribute('aria-expanded', 'false'); body.hidden = true;
    }
    toggle.addEventListener('click', () => {
      body.hidden = !body.hidden;
      toggle.setAttribute('aria-expanded', String(!body.hidden)); persist();
    });
    block.querySelectorAll('[data-move]').forEach(button => button.addEventListener('click', () => {
      if (button.dataset.move === 'up' && block.previousElementSibling) container.insertBefore(block, block.previousElementSibling);
      else if (button.dataset.move === 'down' && block.nextElementSibling) container.insertBefore(block.nextElementSibling, block);
      update(); persist();
      if (button.disabled) toggle.focus(); else button.focus();
    }));
  });
  // A returned edited row must remain visible even if its block was collapsed.
  if (location.hash.startsWith('#role-')) {
    const toggle = container.querySelector('[aria-controls="roles-content"]');
    toggle.setAttribute('aria-expanded', 'true'); document.getElementById('roles-content').hidden = false;
  }
  update();
})();
