def sort_items(items):
    """Sort items by price (ascending)."""
    items.sort(key=lambda i: i["price"])
    return items
