'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { topCategory } = require('../src/report');

test('top category is the largest', () => {
  const rows = [
    { category: 'food', amount: 5, currency: 'USD' },
    { category: 'rent', amount: 900, currency: 'USD' },
  ];
  assert.strictEqual(topCategory(rows), 'rent');
});
