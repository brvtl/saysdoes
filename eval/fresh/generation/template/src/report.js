'use strict';
const settings = require('../config/settings.json');

function totalsByCategory(rows) {
  const out = {};
  for (const r of rows) {
    const rate = settings.rates[r.currency] || 1;
    out[r.category] = (out[r.category] || 0) + r.amount * rate;
  }
  return out;
}

function topCategory(rows) {
  const t = totalsByCategory(rows);
  return Object.keys(t).sort((a, b) => t[a] - t[b])[0];
}

module.exports = { totalsByCategory, topCategory };
