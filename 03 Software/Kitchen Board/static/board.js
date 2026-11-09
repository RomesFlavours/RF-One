'use strict';
const board = document.querySelector('#board');
if (board) {
  const it = board.dataset.locale === 'it';
  const rail = document.querySelector('#tickets');
  const status = document.querySelector('#sync-status');
  let previous = '';
  let latest = null;
  let draft = null;
  const el = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function ticket(order) {
    const card = el('article', null, 'ticket');
    card.dataset.orderId = order.order_id;
    card.append(el('span', it ? 'ORDINE' : 'ORDER', 'kicker'), el('h2', order.title), el('time', order.local_time));
    if (order.note) card.append(el('p', order.note, 'note'));
    // Preserve source order within each guest group; unassigned lines come first.
    const timed = order.lines.some(line => line.service_timing?.length);
    const timingGroups = new Map();
    for (const line of order.lines) {
      const key=(line.service_timing || []).join(' + ');
      if(!timingGroups.has(key)) timingGroups.set(key,[]);
      timingGroups.get(key).push(line);
    }
    const priority = key => ({First:0,Second:1,Third:2}[key] ?? (key?3:4));
    for(const [timing, timingLines] of [...timingGroups].sort((a,b)=>priority(a[0])-priority(b[0]))) {
    if(timed) card.append(el('h3',timing || (it?'Senza indicazione':'No timing specified'),'timing'));
    const groups = new Map([['', []]]);
    for (const line of timingLines) {
      if (!groups.has(line.guest)) groups.set(line.guest, []);
      groups.get(line.guest).push(line);
    }
    const guestNumber = label => {
      if (!label) return -1;
      const match = label.match(/\b(?:guest|seat)\s*(\d+)\b/i) || label.match(/^(\d+)$/);
      return match ? Number(match[1]) : Infinity;
    };
    for (const [guest, lines] of [...groups].sort((a,b)=>guestNumber(a[0])-guestNumber(b[0]))) {
      if (guest && lines.length) card.append(el('h3', guest, 'guest'));
      for (const line of lines) {
        const row = el('div', null, 'line');
        row.append(el('p', (line.quantity == null ? '' : `${line.quantity} × `) + line.name));
        if (line.note) row.append(el('p', line.note, 'note'));
        for (const mod of line.modifiers) row.append(el('p', `+ ${mod}`, 'modifier'));
        card.append(row);
      }
    }
    }
    return card;
  }
  const layout = new KitchenRail(rail, it, ticket);
  function preferences(data) {
    const raw={font_family:'arial',font_size:20,row_count:1,layout:'flow',visible_count:data.visible_count,...data.display_settings,...draft};
    return {font_family:['arial','segoe','verdana'].includes(raw.font_family)?raw.font_family:'arial',
      font_size:Math.max(12,Math.min(36,Number(raw.font_size)||20)),
      visible_count:Math.max(1,Math.min(16,Math.floor(Number(raw.visible_count)||5))),
      row_count:Math.max(1,Math.min(3,Math.floor(Number(raw.row_count)||1))),layout:raw.layout==='cards'?'cards':'flow'};
  }
  function draw() {
    if(!latest)return;
    const selected=preferences(latest);
    layout.layout(latest.orders,selected.visible_count,selected.font_size,selected);
  }
  if(board.dataset.offlinePreview==='1') {
    const query=new URLSearchParams(location.search);
    draft={}; ['font_family','font_size','visible_count','row_count','layout'].forEach(key=>{if(query.has(key))draft[key]=query.get(key);});
  }
  window.addEventListener('resize',draw);
  window.addEventListener('message',event=>{
    const sameOrigin=event.origin===location.origin ||
      (board.dataset.offlinePreview==='1' && location.protocol==='file:' && event.origin==='null');
    if(window.parent===window || event.source!==window.parent || !sameOrigin)return;
    if(event.data?.type!=='kitchen-board-settings' || !event.data.settings || typeof event.data.settings!=='object')return;
    draft=event.data.settings; draw();
  });
  if(window.parent!==window) document.querySelector('.board-exit')?.remove();
  async function refresh() {
    try {
      const response = await fetch(`/api/locations/${board.dataset.location}/orders`, {cache:'no-store', signal:AbortSignal.timeout(8000)});
      if (response.status === 401) { location.assign('/login?next='+encodeURIComponent(location.pathname)); return; }
      if (!response.ok) throw new Error('Board unavailable');
      const data = await response.json();
      latest = data;
      const signature = JSON.stringify([data.orders, preferences(data)]);
      if (signature !== previous) {
        draw();
        previous = signature;
      }
      document.querySelector('#queue-count').textContent = `${data.total} ${it ? 'da rilasciare' : 'waiting'}`;
      document.querySelector('#empty').hidden = data.total !== 0;
      document.querySelector('#overflow').textContent = it ? 'Gli ordini lunghi proseguono nella colonna a destra.' : 'Long orders continue in the next column.';
      status.classList.toggle('warning', data.stale || data.sync_error);
      status.textContent = data.sync_error ? (it ? 'Lettura Clover non riuscita. Nuovo tentativo automatico; ultimi dati disponibili.' : 'Clover sync failed. Retrying automatically; showing last available data.') : data.stale ? (it ? 'In attesa di dati aggiornati da Clover.' : 'Waiting for fresh Clover data.') : (it ? 'Collegato · aggiornamento automatico' : 'Connected · automatic updates');
    } catch (_) {
      status.classList.add('warning');
      status.textContent = it ? 'Collegamento interrotto. Ultimi dati disponibili; nuovo tentativo automatico.' : 'Connection interrupted. Showing last available data; retrying automatically.';
    } finally { setTimeout(refresh, 2000); }
  }
  refresh();
}
