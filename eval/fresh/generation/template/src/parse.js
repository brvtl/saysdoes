'use strict';
// Parse a CSV line of the form: date,category,amount,currency
function parseLine(line) {
  const parts = line.split(',');
  if (parts.length !== 4) throw new Error('bad line: ' + line);
  const [date, category, amount, currency] = parts.map((p) => p.trim());
  return { date, category: category.toLowerCase(), amount: parseInt(amount, 10), currency };
}

function parseCsv(text) {
  return text.split('\n').slice(1).filter(Boolean).map(parseLine);
}

module.exports = { parseLine, parseCsv };
