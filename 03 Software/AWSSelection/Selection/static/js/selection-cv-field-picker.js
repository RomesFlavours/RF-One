/* Insert a field reference into the current draft; never send or save it. */
(() => {
  const opener = document.getElementById('open-cv-fields');
  const modal = document.getElementById('cv-field-modal');
  const input = document.getElementById('rule-message');
  const confirm = document.getElementById('cv-field-confirm');
  const error = document.getElementById('cv-field-error');
  let caret = 0;
  opener.addEventListener('click', event => {
    event.preventDefault();
    if (input.disabled) return;
    caret = input.selectionStart;
    modal.querySelectorAll('[name="cv-field"]').forEach(radio => { radio.checked = false; });
    confirm.disabled = true; error.hidden = true;
    modal.showModal(); modal.scrollTop = 0;
  });
  modal.addEventListener('change', event => {
    if (event.target.name === 'cv-field') { confirm.disabled = false; error.hidden = true; }
  });
  function cancel() { modal.close(); opener.focus(); }
  document.getElementById('cv-field-close').addEventListener('click', cancel);
  document.getElementById('cv-field-cancel').addEventListener('click', cancel);
  modal.addEventListener('cancel', event => { event.preventDefault(); cancel(); });
  modal.addEventListener('keydown', event => { if (event.key === 'Escape') event.stopPropagation(); });
  document.getElementById('cv-field-help').addEventListener('click', () => {
    document.getElementById('selection-page-help').showModal();
    document.getElementById('cv-field-picker-guide').scrollIntoView();
  });
  confirm.addEventListener('click', () => {
    const choice = modal.querySelector('[name="cv-field"]:checked');
    if (!choice || input.disabled) return;
    const before = input.value.slice(0, caret), after = input.value.slice(caret);
    const reference = (before && !/\n$/.test(before) ? '\n' : '') +
      'Campo del CV: ' + choice.value + '.\n';
    if (input.maxLength > 0 && input.value.length + reference.length > input.maxLength) {
      error.textContent = 'La bozza è troppo lunga per aggiungere il campo. Riduci il testo e riprova.';
      error.hidden = false; return;
    }
    input.value = before + reference + after;
    input.dispatchEvent(new Event('input', {bubbles: true}));
    modal.close(); input.focus();
    input.setSelectionRange(before.length + reference.length, before.length + reference.length);
  });
})();
