import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from shop.paginate import page, page_count


class TestPaginate(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page(list(range(10)), 1, 3), [0, 1, 2])

    def test_last_page(self):
        self.assertEqual(page(list(range(10)), 4, 3), [9])

    def test_count(self):
        self.assertEqual(page_count(list(range(10)), 3), 4)


if __name__ == "__main__":
    unittest.main()
