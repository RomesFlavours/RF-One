(() => {
  'use strict';
  const select = document.getElementById('person_id');
  if (!select) return;
  function updatePerson() {
    const selected = select.selectedOptions[0];
    const link = document.getElementById('interview-person-link');
    const login = document.getElementById('interview-person-login');
    link.hidden = !selected?.dataset.recordUrl;
    if (!link.hidden) link.href = selected.dataset.recordUrl;
    login.textContent = selected?.dataset.login ? ` · RF-One access: ${selected.dataset.login}` : '';
  }
  select.addEventListener('change', updatePerson);
  updatePerson();
})();
