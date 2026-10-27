#!/usr/bin/env node
'use strict';
const fs = require('fs');
const { parseCsv } = require('./parse');
const { totalsByCategory, topCategory } = require('./report');

const file = process.argv[2] || 'data/expenses.csv';
const rows = parseCsv(fs.readFileSync(file, 'utf8'));
console.log(JSON.stringify(totalsByCategory(rows), null, 2));
console.log('top:', topCategory(rows));
