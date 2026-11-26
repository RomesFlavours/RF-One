'use strict';
// The pass tablet: one place to send dishes out. Every release goes through the
// same release API the kitchen screen follows, so all screens agree within seconds.
const pass = document.querySelector('#pass');
if (pass) {
  const it = pass.dataset.locale === 'it';
  const T = (en, itText) => (it ? itText : en);
  const location_id = pass.dataset.location;
  const csrf = pass.dataset.csrf;
  const grid = document.querySelector('#pass-tickets');
  const recent = document.querySelector('#pass-recent');
  const status = document.querySelector('#pass-status');
  const selected = new Map();  // order_id -> Set of line ids chosen on this tablet
  let busy = false, lastSignature = '';

  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const say = (text, warning) => { status.textContent = text; status.classList.toggle('warning', Boolean(warning)); };
  const minutes = iso => Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 60000));
  const qty = line => (line.quantity == null ? '' : `${line.quantity} × `);

  async function post(path, body) {
    const response = await fetch(path, {method: 'POST', cache: 'no-store', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf}, body: JSON.stringify(body),
      signal: AbortSignal.timeout(8000)});
    if (response.status === 401) { window.location.assign('/login?next=' + encodeURIComponent(window.location.pathname)); throw new Error('signed out'); }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Object.assign(new Error(data.error || 'failed'), {status: response.status});
    return data;
  }

  async function release(order, lineIds) {
    if (busy) return;
    busy = true;
    try {
      const body = {released_by: 'Pass'};
      if (lineIds) body.line_ids = lineIds;
      await post(`/api/locations/${location_id}/orders/${encodeURIComponent(order.order_id)}/release`, body);
      selected.delete(order.order_id);
      say(lineIds ? T(`${order.title}: ${lineIds.length} dish(es) sent out.`, `${order.title}: ${lineIds.length} piatto/i usciti.`)
                  : T(`${order.title}: all out.`, `${order.title}: tutto uscito.`));
    } catch (error) {
      say(error.status === 409 ? T('That ticket changed meanwhile. Check it and try again.', 'Il foglio è cambiato nel frattempo. Controlla e riprova.')
                               : T('Not sent: connection problem. Try again.', 'Non inviato: problema di collegamento. Riprova.'), true);
    } finally { busy = false; lastSignature = ''; refresh(); }
  }

  async function undo(ticket) {
    if (busy) return;
    busy = true;
    try {
      await post(`/api/locations/${location_id}/orders/${encodeURIComponent(ticket.order_id)}/undo-release`, {undone_by: 'Pass'});
      say(T(`${ticket.title}: back on the kitchen screen.`, `${ticket.title}: di nuovo sullo schermo cucina.`));
    } catch (error) {
      say(error.status === 409 ? T('Too late to undo, or the kitchen already has an addition for this order.', 'Troppo tardi per annullare, oppure esiste già un’aggiunta per questo ordine.')
                               : T('Undo failed: connection problem. Try again.', 'Annullamento non riuscito: problema di collegamento. Riprova.'), true);
    } finally { busy = false; lastSignature = ''; refresh(); }
  }

  function flags(order) {
    const out = [];
    if (order.deleted_in_clover) out.push(T('✖ DELETED IN CLOVER: STOP', '✖ CANCELLATO IN CLOVER: FERMA'));
    out.push(order.addition ? T(`ADDITION ${order.addition}`, `AGGIUNTA ${order.addition}`) : T('ORDER', 'ORDINE'));
    if ((order.changes || {}).at) out.push(T('CHANGED', 'MODIFICATO'));
    const already = (order.released_line_ids || []).length;
    if (already) out.push(T(`${already} ALREADY OUT`, `${already} GIÀ USCITI`));
    if (order.allergy) out.push(T('⚠ ALLERGY', '⚠ ALLERGIA'));
    return out;
  }

  function card(order) {
    const chosen = selected.get(order.order_id) || new Set();
    const ids = order.lines.map(line => line.id);
    for (const id of [...chosen]) if (!ids.includes(id)) chosen.delete(id);
    const box = el('article', null, 'pass-ticket');
    box.classList.toggle('deleted', Boolean(order.deleted_in_clover));
    box.classList.toggle('allergy', Boolean(order.allergy));
    box.append(el('p', flags(order).join(' · '), 'pass-flags'));
    box.append(el('h3', order.title));
    box.append(el('p', [order.local_time, `${minutes(order.created_at)} min`, order.server].filter(Boolean).join(' · '), 'pass-meta'));
    if (order.note) box.append(el('p', order.note, 'pass-note'));
    const changes = order.changes || {};
    const list = el('div', null, 'pass-lines');
    for (const line of order.lines) {
      const label = [line.service_timing && line.service_timing.join(' + '), line.guest].filter(Boolean).join(' · ');
      const button = el('button', null, 'pass-line');
      button.type = 'button';
      button.setAttribute('aria-pressed', chosen.has(line.id) ? 'true' : 'false');
      const isNew = (changes.new || []).includes(line.id), isChanged = (changes.changed || []).includes(line.id);
      const mark = isNew ? T('NEW: ', 'NUOVO: ') : isChanged ? T('CHANGED: ', 'MODIFICATO: ') : '';
      if (label) button.append(el('small', label));
      button.append(el('span', mark + qty(line) + line.name, 'pass-dish'));
      if (line.note) button.append(el('span', line.note, 'pass-note'));
      for (const mod of line.modifiers || []) button.append(el('span', `+ ${mod}`, 'pass-mod'));
      if (line.allergy) button.append(el('span', T('⚠ ALLERGY: check before cooking', '⚠ ALLERGIA: controlla prima di cucinare'), 'pass-allergy'));
      button.addEventListener('click', () => {
        const set = selected.get(order.order_id) || new Set();
        set.has(line.id) ? set.delete(line.id) : set.add(line.id);
        if (set.size) selected.set(order.order_id, set); else selected.delete(order.order_id);
        button.setAttribute('aria-pressed', set.has(line.id) ? 'true' : 'false');
        update();
      });
      list.append(button);
    }
    for (const gone of changes.removed || []) {
      list.append(el('p', T('REMOVED: ', 'TOLTO: ') + qty(gone) + gone.name, 'pass-removed'));
    }
    box.append(list);
    const actions = el('div', null, 'pass-actions');
    const some = el('button', null, 'pass-some'); some.type = 'button';
    const all = el('button', order.deleted_in_clover || !order.lines.length ? T('Clear from screen', 'Togli dallo schermo') : T('All out', 'Tutto esce'), 'pass-all');
    all.type = 'button';
    const update = () => {
      const n = (selected.get(order.order_id) || new Set()).size;
      some.textContent = n ? T(`Send out ${n} selected`, `Escono ${n} selezionati`) : T('Tap dishes to send part', 'Tocca i piatti per farne uscire una parte');
      some.disabled = !n;
    };
    update();
    some.addEventListener('click', () => {
      const ids = [...(selected.get(order.order_id) || [])];
      if (!ids.length) return;
      release(order, ids.length === order.lines.length ? null : ids);
    });
    all.addEventListener('click', () => release(order, null));
    actions.append(some, all);
    box.append(actions);
    return box;
  }

  function recentItem(ticket) {
    const item = el('li');
    const what = ticket.part ? T(`part ${ticket.part}`, `parte ${ticket.part}`) : T('whole ticket', 'foglio intero');
    item.append(el('span', `${ticket.title} · ${what} · ${ticket.lines.length} ${T('dish(es)', 'piatto/i')} · ${minutes(ticket.released_at)} min ${T('ago', 'fa')}`));
    const button = el('button', T('Undo', 'Annulla'), 'pass-undo'); button.type = 'button';
    button.addEventListener('click', () => undo(ticket));
    item.append(button);
    return item;
  }

  async function refresh() {
    try {
      const [orders, released] = await Promise.all([
        fetch(`/api/locations/${location_id}/orders`, {cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(8000)}),
        fetch(`/api/locations/${location_id}/released`, {cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(8000)}),
      ]);
      if (orders.status === 401 || released.status === 401) { window.location.assign('/login?next=' + encodeURIComponent(window.location.pathname)); return; }
      if (!orders.ok || !released.ok) throw new Error('unavailable');
      const data = await orders.json(), past = await released.json();
      // Redraw only when something changed, so a tap is never lost mid-redraw.
      const signature = JSON.stringify([data.orders, past.released.map(t => t.order_id), Math.floor(Date.now() / 30000)]);
      if (signature !== lastSignature && !busy) {
        lastSignature = signature;
        grid.replaceChildren(...data.orders.map(card));
        recent.replaceChildren(...past.released.map(recentItem));
        document.querySelector('#open-count').textContent = `(${data.orders.length})`;
        document.querySelector('#pass-empty').hidden = data.orders.length !== 0;
      }
      if (data.sync_error || data.stale) {
        say(data.sync_message || T('Clover is not updating right now. Check the paper ticket for recent changes.', 'Clover non si aggiorna in questo momento. Controlla il foglio per le ultime modifiche.'), true);
      } else if (status.classList.contains('warning') && !busy) {
        say(T('Connected · automatic updates', 'Collegato · aggiornamento automatico'));
      }
    } catch (_) {
      say(T('Connection interrupted. Retrying automatically.', 'Collegamento interrotto. Nuovo tentativo automatico.'), true);
    }
  }
  // One polling loop; a release or undo only asks for an extra refresh.
  async function loop() { await refresh(); setTimeout(loop, 2000); }
  say(T('Connected · automatic updates', 'Collegato · aggiornamento automatico'));
  loop();
}
