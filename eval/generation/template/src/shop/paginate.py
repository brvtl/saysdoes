def page(items, n, size):
    """Return page n (1-based) of items, `size` items per page."""
    start = n * size          # BUG: should be (n - 1) * size
    return items[start:start + size]


def page_count(items, size):
    return (len(items) + size - 1) // size
