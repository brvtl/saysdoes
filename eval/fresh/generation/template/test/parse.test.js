'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parseLine } = require('../src/parse');

test('parses a simple line', () => {
  assert.deepStrictEqual(parseLine('2026-01-02,Food,12,USD'),
    { date: '2026-01-02', category: 'food', amount: 12, currency: 'USD' });
});

test('keeps cents', () => {
  assert.strictEqual(parseLine('2026-01-03,Travel,12.50,USD').amount, 12.5);
});
