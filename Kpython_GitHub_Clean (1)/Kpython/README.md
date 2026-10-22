# UK used & Second hands Goods E-commerce Manager

A Python course project for managing a small online store. It runs as a local Flask web app and stores data in SQLite, so no separate database server is needed.

## What it does

- Store dashboard with sales totals, recent orders, and low-stock reminders
- Product catalog with search, category filtering, add/edit, and safe deletion
- Inventory view with reorder thresholds and stock health indicators
- Order creation with customer details, line items, totals, and automatic stock deduction
- Order status progression, detail pages, and stock restoration when an order is cancelled
- Account registration and sign-in with hashed passwords, session protection, and CSRF protection
- 73 products are loaded from the local photos in `images/` on first startup
- Existing catalog items are hidden during the upgrade; saved orders and their item snapshots are preserved

## Run on Windows

The project uses Python 3.10 or newer.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The server runs at http://127.0.0.1:5000. Open that address in Chrome, Edge, or another browser. In VS Code, you can also run **Terminal > Run Task > Run Common Goods Flask app**, then press F5 and choose **Chrome: Common Goods**.

For a new database, sign in with `admin` / `admin123`. Existing databases keep their current accounts.

Catalog prices and stock counts are sample values for demonstration and can be edited in the app. Prices are shown in NGN.

The app uses a single local store. Existing databases keep their saved accounts.

For another device on your Wi-Fi, set `HOST` to `0.0.0.0` before starting the app, then open `http://<your-computer-ip>:5000` on that device. Windows Firewall may ask you to allow Python on your private network. Do not expose the demo account to the internet.

## Put it on the public web

Deploy to a Python host that supports Flask and persistent storage. Set `SECRET_KEY` to a long random value, set `ADMIN_USERNAME` and `ADMIN_PASSWORD`, and set `DATABASE_PATH` to a persistent writable database path before the first deployment. Use the host's production WSGI server and HTTPS; do not use Flask's development server or enable `FLASK_DEBUG` in production. SQLite data can be lost on hosts with temporary filesystems, so use persistent storage or migrate to a managed database before relying on the hosted store. Changing the admin environment variables later does not update an account that already exists in the database.

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests use temporary SQLite databases and do not modify the demo store database.

## Project layout

```text
Kpython/
├── app.py                 Flask routes, database setup, and store workflows
├── catalog.py             Simple product list for the photo catalog
├── images/                Product photos shown in the catalog
├── requirements.txt       Python dependencies
├── templates/             Jinja pages
├── static/css/             Responsive dashboard styling
├── static/js/              Navigation and order-summary interactions
├── tests/                  Workflow tests
└── store.db                Created automatically at first launch
```

## Data model

- `users`: administrator username and password hash
- `products`: SKU, category, price, available stock, and reorder level
- `orders`: customer details, current status, total, and creation time
- `order_items`: a snapshot of each purchased product name and price

Order creation checks stock and writes the order, its line items, and stock deductions in one SQLite transaction. Cancelling a non-cancelled order restores the quantities once. Completed or shipped orders cannot be moved backwards, and cancelled orders cannot be reopened.
