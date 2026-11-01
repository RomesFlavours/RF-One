/* Evidence links reveal and focus the original answer, including deep links. */
(() => {
  'use strict';
  const conversation = document.getElementById('results-conversation');
  if (!conversation) return;
  function reveal(hash) {
    if (hash !== '#results-conversation' && !/^#message-\d+$/.test(hash)) return;
    const target = document.getElementById(hash.slice(1));
    if (!target) return;
    conversation.open = true;
    target.scrollIntoView({ block: 'center' });
    if (target.hasAttribute('tabindex')) target.focus({ preventScroll: true });
  }
  document.querySelectorAll('[data-open-transcript]').forEach(link => {
    link.addEventListener('click', event => {
      event.preventDefault();
      history.replaceState(null, '', link.hash);
      reveal(link.hash);
    });
  });
  reveal(window.location.hash);
  window.addEventListener('hashchange', () => reveal(window.location.hash));
})();
