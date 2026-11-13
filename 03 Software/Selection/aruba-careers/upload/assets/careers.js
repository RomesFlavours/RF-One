/* RF-One · careers page on Aruba (SELECTION_ARUBA_IDENTITY_001).
   Optional comfort only — every step also works without JavaScript:
   - the confirmed identity is handed to Selection at once (otherwise the
     "Continue to your application" button does it);
   - a form shows it is working and cannot be sent twice;
   - the code field keeps digits only. */
(function () {
  var handoff = document.getElementById('handoff');
  if (handoff) {
    handoff.submit();
    return;
  }
  document.querySelectorAll('form.busy-form').forEach(function (form) {
    form.addEventListener('submit', function (event) {
      if (form.dataset.sent) { event.preventDefault(); return; }
      form.dataset.sent = '1';
      var pressed = event.submitter;
      if (pressed) {
        // The pressed button's value must still reach the server once the buttons are disabled.
        var keep = document.createElement('input');
        keep.type = 'hidden'; keep.name = pressed.name; keep.value = pressed.value;
        form.appendChild(keep);
        if (pressed.value !== 'cancel') { pressed.classList.add('waiting'); }
      }
      setTimeout(function () {
        form.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
      }, 0);
    });
  });
  var code = document.getElementById('code');
  if (code) {
    code.addEventListener('input', function () { code.value = code.value.replace(/\D/g, '').slice(0, 5); });
  }
})();
