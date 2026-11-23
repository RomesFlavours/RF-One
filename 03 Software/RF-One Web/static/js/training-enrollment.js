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
  // Indeed forwarding addresses may never reach the person: ask for the real email.
  const email = form.elements.email;
  const warning = document.createElement('span');
  warning.className = 'error';
  warning.setAttribute('role', 'alert');
  warning.textContent = 'This is an Indeed forwarding address. Ask for their real email.';
  warning.hidden = true;
  warning.style.marginTop = '.5rem';
  // Inside the email box's own grid cell, so it always sits right under it.
  email.after(warning);
  const checkEmail = () => {
    const domain = (email.value.trim().toLowerCase().split('@')[1] || '');
    const forwarding = domain === 'indeedemail.com' || domain.endsWith('.indeedemail.com');
    warning.hidden = !forwarding;
    warning.style.display = forwarding ? 'block' : 'none';
    email.setCustomValidity(forwarding ? warning.textContent : '');
  };
  email.addEventListener('input', checkEmail);
  select.addEventListener('change', checkEmail);
  checkEmail();
  update();
});
