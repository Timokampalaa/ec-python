import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from functools import wraps
from math import isfinite
from pathlib import Path
from urllib.parse import urlparse

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from catalog import CATALOG_ITEMS


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get('DATABASE_PATH', BASE_DIR / 'store.db'))
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'local-development-key-change-me'),
    DATABASE=str(DATABASE_PATH),
)
CSRFProtect(app)


@contextmanager
def database():
    connection = sqlite3.connect(app.config['DATABASE'])
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with database() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                sku TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL,
                price REAL NOT NULL CHECK (price >= 0),
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0),
                reorder_level INTEGER NOT NULL DEFAULT 5 CHECK (reorder_level >= 0),
                image_url TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                total REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER NOT NULL REFERENCES products(id),
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price REAL NOT NULL CHECK (unit_price >= 0)
            );
            """
        )
        columns = {row['name'] for row in db.execute('PRAGMA table_info(products)')}
        if 'is_active' not in columns:
            db.execute(
                'ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1'
            )
        if not db.execute('SELECT id FROM users LIMIT 1').fetchone():
            db.execute(
                'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                (
                    os.environ.get('ADMIN_USERNAME', 'admin'),
                    generate_password_hash(
                        os.environ.get('ADMIN_PASSWORD', 'admin123')
                    ),
                ),
            )
        has_photo_catalog = db.execute(
            "SELECT 1 FROM products WHERE image_url LIKE '/images/%' LIMIT 1"
        ).fetchone()
        if not has_photo_catalog:
            db.execute('UPDATE products SET is_active = 0')
            db.executemany(
                """INSERT INTO products
                   (name, sku, category, price, stock, reorder_level, image_url, created_at)
                   VALUES (?, ?, ?, ?, 10, 2, ?, ?)""",
                [
                    (
                        name,
                        f'P{index:03d}',
                        category,
                        price,
                        f'/images/{filename}',
                        datetime.now().isoformat(timespec='seconds'),
                    )
                    for index, (filename, name, category, price) in enumerate(
                        CATALOG_ITEMS, 1
                    )
                ],
            )


@app.get('/images/<path:filename>')
def product_image(filename):
    return send_from_directory(BASE_DIR / 'images', filename)


def login_required(view):
    @wraps(view)
    def wrapped(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.path))
        return view(**kwargs)

    return wrapped


def money(value):
    return f'NGN {value:,.0f}'


app.jinja_env.filters['money'] = money


@app.context_processor
def inject_shell_data():
    low_stock = 0
    if 'user_id' in session:
        with database() as db:
            low_stock = db.execute(
                'SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock <= reorder_level'
            ).fetchone()[0]
    return {
        'current_year': date.today().year,
        'current_date': date.today().strftime('%A, %B %d'),
        'active_page': request.endpoint or '',
        'nav_low_stock': low_stock,
    }


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        with database() as db:
            user = db.execute(
                'SELECT * FROM users WHERE username = ?', (username,)
            ).fetchone()
        if user and check_password_hash(
            user['password_hash'], request.form.get('password', '')
        ):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            next_url = request.args.get('next', '')
            if urlparse(next_url).netloc or not next_url.startswith('/'):
                next_url = url_for('dashboard')
            return redirect(next_url)
        flash('That username and password did not match.', 'error')
    return render_template('login.html')


@app.post('/logout')
@login_required
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    with database() as db:
        metrics = db.execute(
            """SELECT (SELECT COUNT(*) FROM orders) AS order_count,
                      (SELECT COALESCE(SUM(total), 0) FROM orders WHERE status != 'Cancelled') AS revenue,
                      (SELECT COUNT(*) FROM products WHERE is_active = 1) AS product_count,
                      (SELECT COUNT(*) FROM products WHERE is_active = 1 AND stock <= reorder_level) AS low_stock_count"""
        ).fetchone()
        recent = db.execute(
            'SELECT * FROM orders ORDER BY created_at DESC, id DESC LIMIT 6'
        ).fetchall()
        low_stock = db.execute(
            'SELECT * FROM products WHERE is_active = 1 AND stock <= reorder_level ORDER BY stock LIMIT 5'
        ).fetchall()
        sales = db.execute(
            """SELECT date(created_at) AS day, SUM(total) AS revenue FROM orders
               WHERE status != 'Cancelled' AND created_at >= date('now', '-6 days')
               GROUP BY date(created_at) ORDER BY day"""
        ).fetchall()
        categories = db.execute(
            'SELECT category, COUNT(*) AS count FROM products WHERE is_active = 1 GROUP BY category ORDER BY count DESC LIMIT 5'
        ).fetchall()
    return render_template(
        'dashboard.html',
        metrics=metrics,
        recent_orders=recent,
        low_stock=low_stock,
        sales=sales,
        categories=categories,
    )


@app.route('/products')
@login_required
def products():
    search = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    query, params = 'SELECT * FROM products WHERE is_active = 1', []
    if search:
        query += ' AND (name LIKE ? OR sku LIKE ?)'
        params.extend((f'%{search}%', f'%{search}%'))
    if category:
        query += ' AND category = ?'
        params.append(category)
    query += ' ORDER BY name COLLATE NOCASE'
    with database() as db:
        items = db.execute(query, params).fetchall()
        categories = [
            row['category']
            for row in db.execute(
                'SELECT DISTINCT category FROM products WHERE is_active = 1 ORDER BY category'
            )
        ]
    return render_template(
        'products.html',
        products=items,
        categories=categories,
        search=search,
        selected_category=category,
    )


def product_values():
    name = request.form.get('name', '').strip()
    sku = request.form.get('sku', '').strip().upper()
    category = request.form.get('category', '').strip()
    image_url = request.form.get('image_url', '').strip()
    try:
        price = float(request.form.get('price', ''))
        stock = int(request.form.get('stock', ''))
        reorder = int(request.form.get('reorder_level', ''))
    except ValueError:
        raise ValueError('Price and stock values must be valid numbers.') from None
    if not name or not sku or not category:
        raise ValueError('Name, SKU, and category are required.')
    if not isfinite(price) or price < 0 or stock < 0 or reorder < 0:
        raise ValueError('Price and stock values cannot be negative.')
    return name, sku, category, price, stock, reorder, image_url


def save_product(product_id=None):
    try:
        values = product_values()
        with database() as db:
            if product_id is None:
                db.execute(
                    """INSERT INTO products (name, sku, category, price, stock, reorder_level, image_url, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (*values, datetime.now().isoformat(timespec='seconds')),
                )
            else:
                db.execute(
                    'UPDATE products SET name=?, sku=?, category=?, price=?, stock=?, reorder_level=?, image_url=? WHERE id=?',
                    (*values, product_id),
                )
        flash(
            'Product added to your catalog.'
            if product_id is None
            else 'Product details updated.',
            'success',
        )
        return redirect(url_for('products'))
    except ValueError as error:
        flash(str(error), 'error')
    except sqlite3.IntegrityError:
        flash('That SKU is already in use.', 'error')
    return None


@app.route('/products/new', methods=['GET', 'POST'])
@login_required
def new_product():
    if request.method == 'POST':
        response = save_product()
        if response:
            return response
    return render_template('product_form.html', product=None)


@app.route('/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    with database() as db:
        product = db.execute(
            'SELECT * FROM products WHERE id = ? AND is_active = 1', (product_id,)
        ).fetchone()
    if product is None:
        abort(404)
    if request.method == 'POST':
        response = save_product(product_id)
        if response:
            return response
    return render_template('product_form.html', product=product)


@app.post('/products/<int:product_id>/delete')
@login_required
def delete_product(product_id):
    with database() as db:
        used = db.execute(
            'SELECT 1 FROM order_items WHERE product_id = ? LIMIT 1', (product_id,)
        ).fetchone()
        if used:
            flash(
                'This product is part of an order and cannot be deleted. You can set its stock to zero instead.',
                'error',
            )
        else:
            db.execute('DELETE FROM products WHERE id = ?', (product_id,))
            flash('Product removed from your catalog.', 'success')
    return redirect(url_for('products'))


@app.route('/inventory')
@login_required
def inventory():
    with database() as db:
        items = db.execute(
            'SELECT * FROM products WHERE is_active = 1 ORDER BY (stock <= reorder_level) DESC, stock ASC'
        ).fetchall()
    return render_template('inventory.html', products=items)


@app.route('/orders')
@login_required
def orders():
    status = request.args.get('status', '').strip()
    query, params = 'SELECT * FROM orders', []
    if status:
        query += ' WHERE status = ?'
        params.append(status)
    with database() as db:
        items = db.execute(
            query + ' ORDER BY created_at DESC, id DESC', params
        ).fetchall()
    return render_template('orders.html', orders=items, selected_status=status)


@app.route('/orders/new', methods=['GET', 'POST'])
@login_required
def new_order():
    with database() as db:
        available = db.execute(
            'SELECT * FROM products WHERE is_active = 1 AND stock > 0 ORDER BY name'
        ).fetchall()
    if request.method == 'POST':
        customer = request.form.get('customer_name', '').strip()
        email = request.form.get('customer_email', '').strip()
        try:
            requested = {}
            for key, value in request.form.items():
                if key.startswith('quantity_'):
                    quantity = int(value or 0)
                    if quantity > 0:
                        requested[int(key.removeprefix('quantity_'))] = quantity
        except ValueError:
            flash('Quantities must be whole numbers.', 'error')
            return render_template('order_form.html', products=available)
        if not customer or '@' not in email:
            flash('Enter a customer name and valid email address.', 'error')
        elif not requested:
            flash('Add at least one item to the order.', 'error')
        else:
            try:
                with database() as db:
                    db.execute('BEGIN IMMEDIATE')
                    selected = []
                    for product_id, quantity in requested.items():
                        product = db.execute(
                            'SELECT * FROM products WHERE id = ? AND is_active = 1',
                            (product_id,),
                        ).fetchone()
                        if product is None or product['stock'] < quantity:
                            raise ValueError(
                                'One or more items are no longer available in the requested quantity.'
                            )
                        selected.append((product, quantity))
                    total = sum(
                        product['price'] * quantity for product, quantity in selected
                    )
                    cursor = db.execute(
                        'INSERT INTO orders (customer_name, customer_email, total, created_at) VALUES (?, ?, ?, ?)',
                        (
                            customer,
                            email,
                            total,
                            datetime.now().isoformat(timespec='seconds'),
                        ),
                    )
                    for product, quantity in selected:
                        db.execute(
                            'INSERT INTO order_items (order_id, product_id, product_name, quantity, unit_price) VALUES (?, ?, ?, ?, ?)',
                            (
                                cursor.lastrowid,
                                product['id'],
                                product['name'],
                                quantity,
                                product['price'],
                            ),
                        )
                        db.execute(
                            'UPDATE products SET stock = stock - ? WHERE id = ?',
                            (quantity, product['id']),
                        )
                flash('Order created and inventory updated.', 'success')
                return redirect(url_for('orders'))
            except ValueError as error:
                flash(str(error), 'error')
    return render_template('order_form.html', products=available)


@app.post('/orders/<int:order_id>/status')
@login_required
def update_order_status(order_id):
    status = request.form.get('status', '')
    transitions = {
        'Pending': {'Pending', 'Processing', 'Cancelled'},
        'Processing': {'Processing', 'Shipped', 'Cancelled'},
        'Shipped': {'Shipped', 'Delivered'},
        'Delivered': {'Delivered'},
        'Cancelled': {'Cancelled'},
    }
    if status not in transitions:
        abort(400)
    with database() as db:
        order = db.execute(
            'SELECT * FROM orders WHERE id = ?', (order_id,)
        ).fetchone()
        if order is None:
            abort(404)
        if status not in transitions[order['status']]:
            flash('That status change is not available for this order.', 'error')
        elif status == 'Cancelled' and order['status'] != 'Cancelled':
            items = db.execute(
                'SELECT product_id, quantity FROM order_items WHERE order_id = ?',
                (order_id,),
            ).fetchall()
            for item in items:
                db.execute(
                    'UPDATE products SET stock = stock + ? WHERE id = ?',
                    (item['quantity'], item['product_id']),
                )
            db.execute(
                'UPDATE orders SET status = ? WHERE id = ?', (status, order_id)
            )
            flash('Order cancelled and items returned to inventory.', 'success')
        else:
            db.execute(
                'UPDATE orders SET status = ? WHERE id = ?', (status, order_id)
            )
            flash('Order status updated.', 'success')
    return redirect(url_for('order_detail', order_id=order_id))


@app.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    with database() as db:
        order = db.execute(
            'SELECT * FROM orders WHERE id = ?', (order_id,)
        ).fetchone()
        if order is None:
            abort(404)
        items = db.execute(
            'SELECT * FROM order_items WHERE order_id = ?', (order_id,)
        ).fetchall()
    return render_template('order_detail.html', order=order, items=items)


init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG') == '1')
