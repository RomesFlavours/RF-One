/* Native contextual help owns its keyboard events while above a profile modal. */
(function () {
  'use strict';
  var help = document.getElementById('rf-help');
  if (help) {
    help.addEventListener('keydown', function (event) {
      // Keep the native dialog's Escape/Tab behavior from reaching the underlying
      // custom modal controller. Closing Help must retain the profile draft.
      event.stopPropagation();
    });
  }
})();
