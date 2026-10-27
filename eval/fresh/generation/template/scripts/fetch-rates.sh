#!/bin/sh
# Refresh currency rates into config/settings.json (needs network).
set -e
curl -s https://api.exchangerate.example/latest?base=USD -o /tmp/rates.json
node -e "const s=require('./config/settings.json');s.rates=require('/tmp/rates.json').rates;require('fs').writeFileSync('config/settings.json',JSON.stringify(s,null,2))"
