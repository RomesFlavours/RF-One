document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('enrollment-form');
  if (!form) return;
  const select = form.elements.selection_id;
  const source = document.getElementById('selection-source');
  const update = () => {
    const selection = form.elements.mode.value === 'selection';
    source.hidden = !selection;
    select.disabled = !selection;
    select.required = selection;
  };
  form.querySelectorAll('[name=mode]').forEach(radio => radio.addEventListener('change', update));
  select.addEventListener('change', () => {
    const row = select.selectedOptions[0];
    if (!row?.value) return;
    for (const key of ['name', 'email', 'phone']) form.elements[key].value = row.dataset[key] || '';
  });
  update();
});
