# shop

Tiny inventory/pricing helpers used by the storefront.

- `shop.paginate.page(items, n, size)` returns page `n` (1-based) of `items`.
- `shop.pricing.apply_tax(amount, rate)` adds tax and rounds to cents.
- `shop.store.Store` is an in-memory key/value store.
- `shop.sorting.sort_items(items)` sorts items by price.

Run tests with `python3 -m pytest -q` (or `python3 -m unittest`).
