/* Course card banners: simple original illustrations, one per course, in the
   RF One palette. Each returns an SVG string sized to fill the card top. */
window.RF_BANNERS = (function () {
  const O = "#5d6d2f", O2 = "#7c8f52", CREAM = "#f3ecd8", T = "#b23a26", G = "#e2b33c", INK = "#2f3a1f", SKY = "#dfe8d3", W = "#ffffff";
  const wrap = (bg, body) => `<svg viewBox="0 0 400 150" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><rect width="400" height="150" fill="${bg}"/>${body}</svg>`;
  function arches(x, y, n, w, h, fill) {
    let s = "";
    for (let i = 0; i < n; i++) s += `<path d="M${x + i * w + 3} ${y + h} v-${h - w / 2} a${w / 2 - 3} ${w / 2 - 3} 0 0 1 ${w - 6} 0 v${h - w / 2} z" fill="${fill}"/>`;
    return s;
  }
  return {
    m1: wrap(SKY,
      `<circle cx="310" cy="58" r="34" fill="${G}" opacity=".85"/>` +
      `<path d="M0 118 Q120 96 220 112 T400 104 V150 H0z" fill="${O2}" opacity=".5"/>` +
      `<path d="M95 120 V62 Q170 40 250 50 L262 64 V120z" fill="${CREAM}"/>` +
      `<path d="M250 50 L262 64 V120 H236 V70z" fill="#e6dcc1"/>` +
      arches(104, 66, 6, 24, 22, O) + arches(104, 92, 6, 24, 26, O) +
      `<rect x="0" y="120" width="400" height="30" fill="${O}"/>`),
    m2: wrap("#e7efe4",
      `<circle cx="70" cy="40" r="10" fill="${G}" opacity=".6"/><circle cx="340" cy="112" r="14" fill="${O2}" opacity=".35"/>` +
      `<path d="M200 22 L252 40 V78 Q252 112 200 130 Q148 112 148 78 V40z" fill="${O}"/>` +
      `<path d="M200 34 L240 48 V78 Q240 104 200 118z" fill="${O2}"/>` +
      `<path d="M178 76 l16 16 l30 -32" fill="none" stroke="${W}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>` +
      `<path d="M300 40 q18 -14 30 6 q-20 10 -30 -6z" fill="${O2}"/><path d="M90 104 q-18 -12 -30 6 q20 10 30 -6z" fill="${O2}"/>`),
    m3: wrap("#f4ead6",
      `<rect x="0" y="108" width="400" height="42" fill="${T}" opacity=".9"/>` +
      `<path d="M0 108 h400" stroke="${CREAM}" stroke-width="3" stroke-dasharray="14 10"/>` +
      `<ellipse cx="160" cy="98" rx="74" ry="16" fill="${W}"/><path d="M90 96 Q160 150 230 96z" fill="${W}"/>` +
      `<path d="M112 92 q14 -20 30 -4 q12 -22 30 -2 q14 -18 28 0" fill="none" stroke="${G}" stroke-width="7" stroke-linecap="round"/>` +
      `<circle cx="138" cy="86" r="6" fill="${T}"/><circle cx="176" cy="84" r="5" fill="${T}"/><path d="M150 80 q6 -8 12 0" stroke="${O}" stroke-width="4" fill="none"/>` +
      `<path d="M286 40 h36 q0 34 -18 40 q-18 -6 -18 -40z" fill="#7a1f2b"/><path d="M286 40 h36" stroke="${INK}" stroke-width="2"/>` +
      `<path d="M304 80 v26 M290 108 h28" stroke="${INK}" stroke-width="4" stroke-linecap="round"/>`),
    m4: wrap("#e9ede0",
      `<rect x="0" y="0" width="400" height="20" fill="${O}" opacity=".25"/>` +
      `<ellipse cx="200" cy="104" rx="130" ry="26" fill="${W}" stroke="${O2}" stroke-width="3"/>` +
      `<circle cx="140" cy="100" r="13" fill="${CREAM}" stroke="${O}" stroke-width="3"/><circle cx="200" cy="108" r="13" fill="${CREAM}" stroke="${O}" stroke-width="3"/><circle cx="260" cy="100" r="13" fill="${CREAM}" stroke="${O}" stroke-width="3"/>` +
      `<path d="M200 30 q10 14 0 28 q-10 -14 0 -28z" fill="${G}"/><rect x="195" y="56" width="10" height="34" fill="${W}" stroke="${O}" stroke-width="2"/>` +
      `<circle cx="60" cy="62" r="14" fill="${O}"/><path d="M40 118 q20 -46 40 0z" fill="${O}"/>` +
      `<circle cx="340" cy="62" r="14" fill="${T}"/><path d="M320 118 q20 -46 40 0z" fill="${T}"/>`),
    m5: wrap("#f6e7e1",
      `<circle cx="330" cy="40" r="22" fill="${G}" opacity=".5"/>` +
      `<rect x="96" y="30" width="150" height="70" rx="16" fill="${W}" stroke="${T}" stroke-width="3"/><path d="M130 100 l-6 24 l26 -24z" fill="${W}" stroke="${T}" stroke-width="3" stroke-linejoin="round"/>` +
      `<text x="171" y="78" font-family="Georgia,serif" font-size="34" fill="${T}" text-anchor="middle">A A A</text>` +
      `<path d="M262 120 q30 -30 60 0z" fill="${O}"/><path d="M276 108 l10 -40 l10 40" fill="none" stroke="${O}" stroke-width="4"/>` +
      `<rect x="0" y="126" width="400" height="24" fill="${O}" opacity=".85"/>`),
    m6: wrap("#e6ecdf",
      `<rect x="0" y="118" width="400" height="32" fill="${O}"/>` +
      [[110, O2], [170, T], [230, O], [290, G]].map(([x, c]) =>
        `<circle cx="${x}" cy="66" r="16" fill="${c}"/><path d="M${x - 24} 118 q24 -58 48 0z" fill="${c}"/>`).join("") +
      `<path d="M126 86 h28 M186 86 h28 M246 86 h28" stroke="${INK}" stroke-width="4" stroke-linecap="round" opacity=".5"/>`),
    // The welcome: an open arched door with warm light, and the podium.
    m7: wrap("#efe9da",
      `<rect x="0" y="122" width="400" height="28" fill="${O}"/>` +
      `<path d="M120 122 V62 a50 50 0 0 1 100 0 V122z" fill="${CREAM}" stroke="${O}" stroke-width="4"/>` +
      `<path d="M134 122 V64 a36 36 0 0 1 72 0 V122z" fill="${G}" opacity=".55"/>` +
      `<path d="M206 122 V64 L232 74 V128z" fill="${O2}"/>` +
      `<rect x="268" y="74" width="46" height="48" rx="3" fill="${O}"/><rect x="262" y="66" width="58" height="10" rx="3" fill="${INK}" opacity=".8"/>` +
      `<rect x="280" y="84" width="22" height="28" rx="2" fill="${W}"/><path d="M285 92 h12 M285 98 h12 M285 104 h8" stroke="${O2}" stroke-width="2"/>` +
      `<circle cx="70" cy="44" r="12" fill="${T}" opacity=".6"/><circle cx="356" cy="36" r="8" fill="${G}" opacity=".7"/>`),
    // Our menu: a pizza on a board and a plate of pasta.
    m8: wrap("#f4ead6",
      `<rect x="0" y="116" width="400" height="34" fill="${O}" opacity=".9"/>` +
      `<rect x="70" y="88" width="160" height="22" rx="11" fill="#c9a06a"/><rect x="226" y="94" width="34" height="10" rx="5" fill="#c9a06a"/>` +
      `<ellipse cx="150" cy="86" rx="70" ry="22" fill="#e9c37a"/><ellipse cx="150" cy="84" rx="58" ry="16" fill="${T}"/>` +
      `<circle cx="126" cy="82" r="6" fill="${W}"/><circle cx="160" cy="88" r="6" fill="${W}"/><circle cx="176" cy="78" r="5" fill="${W}"/><circle cx="140" cy="76" r="5" fill="${W}"/>` +
      `<path d="M118 90 q4 -6 8 0 M168 74 q4 -6 8 0 M150 80 q4 -6 8 0" stroke="${O}" stroke-width="3" fill="none"/>` +
      `<ellipse cx="300" cy="100" rx="56" ry="13" fill="${W}"/><path d="M246 98 Q300 140 354 98z" fill="${W}"/>` +
      `<path d="M266 96 q10 -18 22 -4 q10 -18 22 -2 q10 -16 22 0" fill="none" stroke="${G}" stroke-width="6" stroke-linecap="round"/>` +
      `<path d="M300 40 l4 30 M312 40 l-2 30" stroke="${INK}" stroke-width="3" stroke-linecap="round" opacity=".6"/>`),
    // Guest questions: a question bubble and a wedge of cheese.
    m9: wrap("#e8eee2",
      `<rect x="0" y="124" width="400" height="26" fill="${O}"/>` +
      `<rect x="80" y="26" width="120" height="72" rx="18" fill="${W}" stroke="${O}" stroke-width="3"/><path d="M112 98 l-8 22 l26 -22z" fill="${W}" stroke="${O}" stroke-width="3" stroke-linejoin="round"/>` +
      `<text x="140" y="80" font-family="Georgia,serif" font-size="50" fill="${O}" text-anchor="middle">?</text>` +
      `<path d="M240 122 L330 122 L330 84 L240 104z" fill="${G}"/><path d="M240 104 L330 84 L312 72 z" fill="#f0cf6a"/>` +
      `<circle cx="270" cy="108" r="5" fill="#c99a22"/><circle cx="300" cy="104" r="7" fill="#c99a22"/><circle cx="316" cy="114" r="4" fill="#c99a22"/>` +
      `<circle cx="350" cy="44" r="12" fill="${T}" opacity=".5"/>`),
    // Italian wine: a bottle, a glass and a bunch of grapes.
    m10: wrap("#f1e6e4",
      `<rect x="0" y="122" width="400" height="28" fill="${O}"/>` +
      `<path d="M150 24 h20 v24 q16 12 16 30 v44 h-52 v-44 q0 -18 16 -30z" fill="#5a1a26"/><rect x="148" y="18" width="24" height="10" rx="2" fill="${T}"/>` +
      `<rect x="138" y="80" width="44" height="26" rx="3" fill="${CREAM}"/><path d="M146 90 h28 M146 97 h20" stroke="${O}" stroke-width="2"/>` +
      `<path d="M214 56 h40 q0 34 -20 40 q-20 -6 -20 -40z" fill="#7a1f2b" opacity=".9"/><path d="M214 56 h40" stroke="${INK}" stroke-width="2"/>` +
      `<path d="M234 96 v20 M220 120 h28" stroke="${INK}" stroke-width="4" stroke-linecap="round"/>` +
      [[300, 60], [318, 60], [336, 60], [309, 76], [327, 76], [318, 92]].map(([x, y]) => `<circle cx="${x}" cy="${y}" r="9" fill="${O2}"/>`).join("") +
      `<path d="M318 50 q4 -14 16 -18" stroke="${O}" stroke-width="3" fill="none"/><path d="M330 34 q14 -6 22 4 q-14 8 -22 -4z" fill="${O}"/>`),
    // Taking the order: an order pad with a pencil, and a ticket.
    m11: wrap("#e9ede0",
      `<rect x="0" y="126" width="400" height="24" fill="${O}"/>` +
      `<rect x="120" y="22" width="96" height="112" rx="6" fill="${W}" stroke="${O}" stroke-width="3"/><rect x="120" y="22" width="96" height="16" rx="4" fill="${O}"/>` +
      [52, 68, 84, 100, 116].map((y, i) => `<text x="132" y="${y + 4}" font-family="Arial" font-size="11" font-weight="700" fill="${T}">${i + 1}</text><path d="M146 ${y} h56" stroke="${O2}" stroke-width="3" stroke-linecap="round" opacity=".6"/>`).join("") +
      `<path d="M236 112 l52 -76 l12 8 l-52 76 l-16 6z" fill="${G}"/><path d="M288 36 l12 8 l6 -9 l-12 -8z" fill="${T}"/>` +
      `<rect x="300" y="58" width="56" height="70" fill="${CREAM}" stroke="${O}" stroke-width="2"/><path d="M308 72 h40 M308 82 h30 M308 92 h40 M308 102 h24" stroke="${O}" stroke-width="2"/>`),
    // Serving the table: a place setting, glasses above the plate on the right.
    m12: wrap("#eef0e6",
      `<rect x="0" y="118" width="400" height="32" fill="${O}" opacity=".85"/>` +
      `<ellipse cx="200" cy="96" rx="58" ry="20" fill="${W}" stroke="${O2}" stroke-width="3"/><ellipse cx="200" cy="96" rx="36" ry="12" fill="none" stroke="${O2}" stroke-width="2" opacity=".6"/>` +
      `<path d="M120 76 v40 M114 76 v12 q6 6 12 0 v-12" stroke="${INK}" stroke-width="3" stroke-linecap="round" fill="none" opacity=".7"/>` +
      `<path d="M280 76 v40" stroke="${INK}" stroke-width="3" stroke-linecap="round" opacity=".7"/><path d="M280 76 q8 10 0 22" fill="${INK}" opacity=".5"/>` +
      `<path d="M238 30 h24 q0 22 -12 26 q-12 -4 -12 -26z" fill="#dfe8f0" stroke="${O}" stroke-width="2"/><path d="M250 56 v14 M242 72 h16" stroke="${O}" stroke-width="2"/>` +
      `<path d="M270 34 h26 q0 24 -13 28 q-13 -4 -13 -28z" fill="#7a1f2b" opacity=".85"/><path d="M283 62 v12 M274 76 h18" stroke="${INK}" stroke-width="2"/>` +
      `<circle cx="60" cy="40" r="12" fill="${G}" opacity=".7"/>`),
  };
})();
