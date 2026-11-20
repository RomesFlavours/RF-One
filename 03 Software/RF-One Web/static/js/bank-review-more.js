(() => {
  const link = document.getElementById('review-more');
  const body = document.querySelector('#review-body, #rp-body');
  link.addEventListener('click', async event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (link.getAttribute('aria-busy') === 'true') return;
    link.setAttribute('aria-busy', 'true');
    const url = link.href;
    try {
      const response = await fetch(url, {headers: {'X-Bank-Review': 'rows'}});
      if (!response.ok) throw new Error();
      const result = await response.json();
      const batch = document.createElement('tbody');
      batch.innerHTML = result.rows;
      const rows = Array.from(batch.children).filter(row => row.id && !document.getElementById(row.id));
      body.append(...rows);
      history.replaceState(history.state, '', url);
      document.querySelectorAll('input[name="return_to"]').forEach(input => {
        input.value = location.pathname + location.search;
      });
      document.dispatchEvent(new CustomEvent('bank-review-rows', {detail: rows}));
      if (result.next_url) link.href = result.next_url;
      else link.hidden = true;
    } catch {
      location.assign(url);
    } finally {
      link.removeAttribute('aria-busy');
    }
  });
})();
