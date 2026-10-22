import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


test_root = tempfile.TemporaryDirectory()
with patch.dict(os.environ, {"DATABASE_PATH": str(Path(test_root.name) / "import.db")}):
    import app as store


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.original_path = store.DATABASE_PATH
        self.original_database = store.app.config["DATABASE"]
        self.temp_dir = tempfile.TemporaryDirectory()
        store.DATABASE_PATH = Path(self.temp_dir.name) / "store.db"
        store.app.config["DATABASE"] = str(store.DATABASE_PATH)
        store.app.config["TESTING"] = True
        store.init_db()

    def tearDown(self):
        store.DATABASE_PATH = self.original_path
        store.app.config["DATABASE"] = self.original_database
        self.temp_dir.cleanup()

    def test_all_photos_are_seeded_as_products(self):
        with store.database() as db:
            products = db.execute(
                "SELECT sku, image_url FROM products WHERE is_active = 1 ORDER BY sku"
            ).fetchall()

        self.assertEqual(len(products), 73)
        self.assertEqual([product["sku"] for product in products], [f"P{i:03d}" for i in range(1, 74)])
        self.assertTrue(all(product["image_url"].startswith("/images/") for product in products))

    def test_product_photo_route_serves_local_image(self):
        response = store.app.test_client().get("/images/IMG-20251106-WA0038.jpg")
        status = response.status_code
        mimetype = response.mimetype
        response.close()

        self.assertEqual(status, 200)
        self.assertEqual(mimetype, "image/jpeg")

    def test_login_page_renders(self):
        response = store.app.test_client().get("/login")

        self.assertEqual(response.status_code, 200)

    def test_products_page_lists_full_catalog(self):
        client = store.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = 1

        response = client.get("/products")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'class="product-card"'), 73)

    def test_catalog_seed_does_not_overwrite_edits(self):
        with store.database() as db:
            db.execute("UPDATE products SET name = 'Presentation Laptop' WHERE sku = 'P001'")

        store.init_db()

        with store.database() as db:
            product = db.execute("SELECT name FROM products WHERE sku = 'P001'").fetchone()
            count = db.execute("SELECT COUNT(*) FROM products WHERE is_active = 1").fetchone()[0]

        self.assertEqual(product["name"], "Presentation Laptop")
        self.assertEqual(count, 73)

    def test_upgrade_archives_old_catalog_and_preserves_order_history(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.executescript(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0,
                reorder_level INTEGER NOT NULL DEFAULT 5,
                image_url TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                total REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL
            );
            INSERT INTO products (name, sku, category, price, created_at)
            VALUES ('Old Jacket', 'OLD-001', 'Apparel', 10, '2026-01-01');
            INSERT INTO orders (customer_name, customer_email, status, total, created_at)
            VALUES ('Demo Customer', 'demo@example.com', 'Pending', 10, '2026-01-01');
            INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price)
            VALUES (1, 1, 'Old Jacket', 1, 10);
            """
        )
        connection.close()
        store.DATABASE_PATH = legacy_path
        store.app.config["DATABASE"] = str(legacy_path)

        store.init_db()

        with store.database() as db:
            old_product = db.execute("SELECT is_active FROM products WHERE sku = 'OLD-001'").fetchone()
            new_count = db.execute("SELECT COUNT(*) FROM products WHERE is_active = 1").fetchone()[0]
            old_order_item = db.execute("SELECT product_name FROM order_items WHERE order_id = 1").fetchone()

        self.assertEqual(old_product["is_active"], 0)
        self.assertEqual(new_count, 73)
        self.assertEqual(old_order_item["product_name"], "Old Jacket")


if __name__ == "__main__":
    unittest.main()