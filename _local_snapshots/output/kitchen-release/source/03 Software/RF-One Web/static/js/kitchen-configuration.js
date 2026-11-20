document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('.kitchen-config-sections');
  if (!root) return;
  const stateKey = 'kitchen-configuration-return';
  try {
    const saved = JSON.parse(sessionStorage.getItem(stateKey));
    sessionStorage.removeItem(stateKey);
    if (saved && Date.now() - saved.time < 60000) {
      for (const code of saved.open) document.getElementById('config-' + code)?.setAttribute('open', '');
      requestAnimationFrame(() => {
        const row = document.querySelector('[data-rr-key="' + CSS.escape(saved.row) + '"]');
        const target = row?.querySelector('.config-edit,button[type="submit"]');
        if (target && !row.hasAttribute('data-editing')) target.focus({preventScroll:true});
      });
    }
  } catch { sessionStorage.removeItem(stateKey); }
  const editing = (row, active) => {
    const input = row.querySelector('.config-row-name');
    input.readOnly = !active;
    row.querySelector('.config-edit').hidden = active;
    row.querySelector('.config-save').hidden = !active;
    row.querySelector('.config-cancel').hidden = !active;
    const archive = row.querySelector('.config-archive-form');
    if (archive) archive.hidden = active;
    if (active) { row.dataset.editing='true'; input.focus({preventScroll:true}); input.select(); }
    else { delete row.dataset.editing; row.querySelector('.config-edit').focus({preventScroll:true}); }
  };
  root.addEventListener('click', event => {
    const row = event.target.closest('tr[data-rr-key]');
    if (!row) return;
    if (event.target.closest('.config-edit')) editing(row,true);
    if (event.target.closest('.config-cancel')) {
      const input = row.querySelector('.config-row-name'); input.value=input.dataset.original; editing(row,false);
    }
  });
  root.addEventListener('submit', event => {
    const row = event.target.closest('[data-rr-key]');
    sessionStorage.setItem(stateKey, JSON.stringify({time:Date.now(),row:row?.dataset.rrKey,
      open:[...root.querySelectorAll('details[open]')].map(d=>d.dataset.configSection)}));
  });
  root.querySelectorAll('tr[data-editing]').forEach(row=>editing(row,true));
});
