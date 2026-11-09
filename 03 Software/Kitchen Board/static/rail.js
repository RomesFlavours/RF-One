'use strict';
// Measure the actual rendered font, width and available screen height. Each
// segment is a complete column; no item depends on a hidden scroll area.
window.KitchenRail = class KitchenRail {
  constructor(rail, it, makeTicket) {
    this.rail = rail; this.it = it; this.makeTicket = makeTicket;
    this.segments = []; this.columns = 5;
  }
  layout(orders, columns, fontSize = 20, options = {}) {
    document.body.style.setProperty('--ticket-font',fontSize+'px');
    const family={arial:'Arial, sans-serif',segoe:'"Segoe UI", sans-serif',verdana:'Verdana, sans-serif'}[options.font_family] || 'Arial, sans-serif';
    document.body.style.setProperty('--ticket-family',family);
    const rows=options.row_count || 1;
    this.capacity=columns*rows;
    this.rail.style.setProperty('--rows',rows);
    this.columns = columns; this.rail.style.setProperty('--columns', columns);
    const gap = parseFloat(getComputedStyle(this.rail).columnGap) || 0;
    const width = (this.rail.clientWidth-gap*(columns-1))/columns;
    const height = (this.rail.clientHeight-gap*(rows-1))/rows;
    const probe = document.createElement('div');
    probe.className = 'rail-probe'; probe.style.width = width+'px'; probe.style.height = height+'px';
    document.body.append(probe); this.segments = [];
    if(options.layout==='cards') {
      for(const order of orders.slice(0,this.capacity)) {
        const card=this.makeTicket(order); let size=fontSize;
        card.style.fontSize=size+'px';
        card.style.setProperty('--order-color',`hsl(${[...order.order_id].reduce((a,c)=>a+c.charCodeAt(0),0)*47%360} 45% 45%)`);
        probe.replaceChildren(card);
        while(card.scrollHeight>card.clientHeight && size>6) { size--; card.style.fontSize=size+'px'; }
        this.segments.push(card);
      }
      probe.remove(); this.rail.replaceChildren(...this.segments); return;
    }
    for (const order of orders) {
      const original = this.makeTicket(order);
      const heading = [...original.children].slice(0,3);
      const content = [...original.children].slice(3);
      let card, body, footer, part = 0, guest = '', timing = '';
      const fits = () => card.scrollHeight <= card.clientHeight;
      const start = () => {
        card = document.createElement('article'); card.className = 'ticket'; card.dataset.orderId = order.order_id;
        heading.forEach(node => card.append(node.cloneNode(true)));
        const flag = document.createElement('strong'); flag.className = 'continuation';
        flag.textContent = part ? (this.it ? '← CONTINUAZIONE · ' : '← CONTINUED · ')+(part+1) : '';
        card.append(flag); body = document.createElement('div'); body.className = 'ticket-body'; card.append(body);
        footer = document.createElement('strong'); footer.className = 'continues'; footer.textContent = '\u00a0'; card.append(footer);
        card.style.setProperty('--order-color', `hsl(${[...order.order_id].reduce((a,c)=>a+c.charCodeAt(0),0)*47%360} 45% 45%)`);
        probe.replaceChildren(card); this.segments.push(card);
        if(part && timing) { const label=document.createElement('h3'); label.className='timing'; label.textContent=timing; body.append(label); }
        if (part && guest) { const label = document.createElement('h3'); label.className='guest'; label.textContent=guest; body.append(label); }
      };
      const advance = () => {
        while (body.lastElementChild?.matches('.guest,.timing')) body.lastElementChild.remove();
        footer.textContent = this.it ? 'CONTINUA A DESTRA →' : 'CONTINUES TO THE RIGHT →';
        part++; start();
      };
      start();
      for (const node of content) {
        if(node.classList.contains('timing')) { timing=node.textContent; guest=''; body.append(node.cloneNode(true)); continue; }
        if (node.classList.contains('guest')) { guest = node.textContent; continue; }
        const group = guest;
        if (group && body.lastElementChild?.dataset.guest !== group) {
          const label = document.createElement('h3'); label.className='guest'; label.textContent=group; body.append(label);
        }
        const copy = node.cloneNode(true); copy.dataset.guest = group; body.append(copy);
        if (fits()) continue;
        copy.remove();
        if (body.querySelector('.line, .note')) advance();
        body.append(copy);
        if (fits()) continue;
        copy.remove();
        // An exceptional single item with very long notes/modifiers also flows
        // across columns, retaining every character instead of clipping text.
        for (const leaf of (node.children.length ? [...node.children] : [node])) {
          let text = leaf.textContent;
          while (text.length) {
            const piece = leaf.cloneNode(false); piece.dataset.guest = group; body.append(piece);
            let lo=0, hi=text.length;
            while (lo<hi) {
              const mid=Math.ceil((lo+hi)/2); piece.textContent=text.slice(0,mid);
              if (fits()) lo=mid; else hi=mid-1;
            }
            if (!lo) {
              piece.remove();
              if (!body.querySelector('p')) throw new Error('Screen too small for a ticket');
              advance(); continue;
            }
            let cut=lo;
            if (lo<text.length) { const space=text.lastIndexOf(' ',lo); if (space>0) cut=space+1; }
            piece.textContent=text.slice(0,cut); text=text.slice(cut);
            if (text.length) advance();
          }
        }
      }
    }
    probe.remove();
    const firstCount=this.segments.filter(card=>card.dataset.orderId===orders[0]?.order_id).length;
    if(firstCount>this.capacity && fontSize>6) return this.layout(orders,columns,Math.max(6,fontSize-2),options);
    this.segments.forEach((card,index)=>{
      if((index+1)%columns===0 && this.segments[index+1]?.dataset.orderId===card.dataset.orderId) {
        card.querySelector('.continues').textContent=this.it?'CONTINUA NELLA RIGA SOTTO ↙':'CONTINUES IN ROW BELOW ↙';
      }
    });
    this.show();
  }
  show() {
    const visible=[];
    for(let index=0;index<this.segments.length;) {
      let end=index+1;
      while(end<this.segments.length && this.segments[end].dataset.orderId===this.segments[index].dataset.orderId) end++;
      if(visible.length+end-index>this.capacity) break;
      visible.push(...this.segments.slice(index,end)); index=end;
    }
    this.rail.replaceChildren(...visible);
  }
};
