"""
RMCP Order System — Flask Backend
Raj Multi Color Print · Kakinada · ESTD 1983
Database: PostgreSQL

DATABASE TABLES:
===============

1. ORDERS - Main order records with customer details and workflow status
2. STOCK - Inventory management for different card designs
3. COUNTER - Atomic order ID generator (maintains single row: id=1, val=increment)
   ├─ PURPOSE: Generate unique sequential order IDs
   ├─ STRUCTURE: One row (id=1) with incrementing counter (val)
   ├─ CONSTRAINT: CHECK (id = 1) ensures only one row can exist
   ├─ USAGE: When creating an order, read val → use for ID → increment val
   ├─ REASON: Prevents duplicate IDs in concurrent order creation
   ├─ THREAD-SAFE: db_lock mutex protects read-increment-write operation
   └─ EXAMPLE: val=5 creates order "WC10340005", then val becomes 6

4. STOCK_HISTORY - Audit trail for all stock movements (ADD/DEDUCT/CREATE actions)
5. CUSTOMERS - Customer database with contact info and order statistics

CUSTOMER-ORDER SYNC:
====================
When an order is created, the customer is automatically:
1. Added to CUSTOMERS table if new (by phone number)
2. Updated if existing (name, email, address, city)
3. Statistics updated: total_orders, total_spent, last_order_date
"""

import os
import re
import threading
from datetime import date, datetime
from flask import Flask, request, jsonify, send_from_directory
import psycopg2
import psycopg2.extras

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Railway automatically sets DATABASE_URL when you add a PostgreSQL service
DATABASE_URL = os.environ.get('DATABASE_URL', '')
FRONTEND     = os.path.join(os.path.dirname(__file__), 'public')

app = Flask(__name__, static_folder=FRONTEND, static_url_path='')

# ─── MULTI-USER SAFETY ────────────────────────────────────────────────────────
db_lock = threading.Lock()

# ─── CORS ─────────────────────────────────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS,PATCH'
    return response

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return app.make_default_options_response()

# ─── DATABASE CONNECTION ──────────────────────────────────────────────────────
def get_db():
    """Get a fresh PostgreSQL connection."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn

def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    c = conn.cursor()

    # Create customers table FIRST (no dependencies)
    c.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id          SERIAL PRIMARY KEY,
            phone       TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            email       TEXT,
            address     TEXT,
            city        TEXT,
            total_orders INTEGER DEFAULT 0,
            total_spent REAL DEFAULT 0,
            last_order_date TEXT,
            created     TEXT DEFAULT (to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')),
            updated     TEXT DEFAULT (to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'))
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id          TEXT PRIMARY KEY,
            customer_id INTEGER,
            name        TEXT NOT NULL,
            phone       TEXT NOT NULL,
            type        TEXT NOT NULL,
            model       TEXT,
            qty         INTEGER  DEFAULT 0,
            price       REAL     DEFAULT 0,
            amount      REAL     DEFAULT 0,
            advance     REAL     DEFAULT 0,
            payment     TEXT,
            delivery    TEXT,
            priority    TEXT     DEFAULT 'Normal',
            handler     TEXT,
            req         TEXT,
            matter      TEXT,
            commitments TEXT,
            status      TEXT     DEFAULT 'New',
            created     TEXT     DEFAULT (to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')),
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL
        )
    ''')

    c.execute('ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_id INTEGER')
    c.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'orders_customer_id_fkey'
            ) THEN
                ALTER TABLE orders
                    ADD CONSTRAINT orders_customer_id_fkey
                    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL;
            END IF;
        END
        $$;
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS stock (
            num     TEXT PRIMARY KEY,
            arrived INTEGER DEFAULT 0,
            current INTEGER DEFAULT 0,
            dealer  REAL    DEFAULT 0,
            sell    REAL    DEFAULT 0,
            nop     REAL    DEFAULT 0,
            vendor  TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS counter (
            id  INTEGER PRIMARY KEY,
            val INTEGER DEFAULT 1,
            CONSTRAINT counter_one_row CHECK (id = 1)
        )
    ''')
    c.execute('INSERT INTO counter (id, val) VALUES (1, 1) ON CONFLICT (id) DO NOTHING')

    c.execute('''
        CREATE TABLE IF NOT EXISTS stock_history (
            id          SERIAL PRIMARY KEY,
            num         TEXT NOT NULL,
            action      TEXT NOT NULL,
            old_qty     INTEGER,
            new_qty     INTEGER,
            qty_change  INTEGER,
            notes       TEXT,
            created     TEXT DEFAULT (to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')),
            FOREIGN KEY (num) REFERENCES stock(num)
        )
    ''')

    conn.commit()
    c.close()
    conn.close()
    print('✅ Database tables ready')

def seed_db():
    """Seed demo data only if orders table is empty."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM orders')
    count = c.fetchone()['count']
    if count > 0:
        c.close()
        conn.close()
        return

    def date_off(days):
        from datetime import timedelta
        return (date.today() + timedelta(days=days)).isoformat()

    stock_rows = [
        ('R100', 1000, 100,  8, 18, 13, 'Novelty, Delhi'),
        ('R101', 1000, 500,  8, 18, 13, 'Novelty, Delhi'),
        ('R102', 1200, 800,  9, 20, 15, 'Novelty, Delhi'),
        ('R103', 1000, 900, 10, 22, 18, 'Novelty, Delhi'),
        ('B501',  800, 800, 14, 48, 35, 'Charla'),
        ('B502', 1000, 800, 14, 48, 35, 'Charla'),
        ('P701', 1000, 1000,40, 88, 65, 'Shubham Cards'),
    ]
    for row in stock_rows:
        c.execute('''
            INSERT INTO stock (num,arrived,current,dealer,sell,nop,vendor)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (num) DO NOTHING
        ''', row)

    customer_rows = [
        ('99999 99999', 'Siddha Venkateswara Rao', 'siddha@example.com', '12 Temple Rd', 'Kakinada'),
        ('88888 88888', 'Thummala Babu', 'thummala@example.com', '4 River St', 'Kakinada'),
        ('77777 77777', 'Uppalapati Rudra Raju', 'uppalapati@example.com', '9 Hillside Ln', 'Kakinada'),
        ('99112233445', 'Lakshmi Prasad', 'lakshmi@example.com', '27 Main Rd', 'Kakinada'),
    ]
    for row in customer_rows:
        c.execute('''
            INSERT INTO customers (phone, name, email, address, city, updated)
            VALUES (%s, %s, %s, %s, %s, to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'))
            ON CONFLICT (phone) DO NOTHING
        ''', row)

    orders = [
        ('WC10310001','99999 99999','Siddha Venkateswara Rao','99999 99999','Readymade','R103',100,22,2200,1000,'Cash',
         date_off(2),'Urgent','Brother 1','Telugu + English, Gold Acrylic plate',
         'Bride: Priya, Groom: Siddha Venkateswara Rao. Parents: Suresh & Lakshmi. Wedding: 25 April 2025. Venue: Sri Kalyana Mandapam.',
         'Delivery on 25th morning 9 AM sharp','Printing'),
        ('WC10150002','88888 88888','Thummala Babu','88888 88888','Semi-custom','R101',500,18,9000,5000,'PhonePe',
         date_off(5),'Normal','Brother 2','Two different matters, each 250 cards',
         'Matter 1: Bride: Anitha, Groom: Raju. Matter 2: Bride: Swathi, Groom: Kumar.',
         '','Proof Sent'),
        ('MC150003','77777 77777','Uppalapati Rudra Raju','77777 77777','Fully customised','Customised',1500,65,97500,50000,'Cash',
         date_off(12),'Normal','Brother 1','9×9 size, Box Cover, Title with gold foil, Inner two sheets S/S',
         'Full Telugu matter to be provided separately.',
         'Agreed to deliver 2 days early if possible','Design'),
        ('WC10340004','99112233445','Lakshmi Prasad','99112233445','Readymade','R103',400,22,8800,3000,'PhonePe',
         date_off(-1),'Urgent','Brother 2','','','','Ready'),
    ]
    for o in orders:
        c.execute('''
            INSERT INTO orders
              (id,customer_id,name,phone,type,model,qty,price,amount,advance,payment,
               delivery,priority,handler,req,matter,commitments,status)
            VALUES (%s,(SELECT id FROM customers WHERE phone=%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        ''', o)

    c.execute('UPDATE counter SET val = 5 WHERE id = 1')

    # Sync customer statistics to match the seeded orders.
    # Each tuple is (phone, total_orders, total_spent, last_order_date).
    # These values are computed directly from the orders list above so that
    # customers who placed multiple demo orders are correctly aggregated.
    # last_order_date uses NOW() so it always reflects a recent date in dev.
    seed_stats = [
        ('99999 99999', 1, 2200),
        ('88888 88888', 1, 9000),
        ('77777 77777', 1, 97500),
        ('99112233445', 1, 8800),
    ]
    for phone, total_orders, total_spent in seed_stats:
        c.execute('''
            UPDATE customers SET
                total_orders    = %s,
                total_spent     = %s,
                last_order_date = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'),
                updated         = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
            WHERE phone = %s
        ''', (total_orders, total_spent, phone))

    conn.commit()
    c.close()
    conn.close()
    print('✅ Demo data seeded')

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def log_stock_movement(conn, num, action, old_qty, new_qty, notes=''):
    """Log stock movement to history table."""
    c = conn.cursor()
    qty_change = new_qty - old_qty if old_qty is not None else new_qty
    c.execute('''
        INSERT INTO stock_history (num, action, old_qty, new_qty, qty_change, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
    ''', (num, action, old_qty, new_qty, qty_change, notes))
    c.close()

def upsert_customer(conn, phone, name, email='', address='', city=''):
    """Add or update customer in customers table. Returns customer id."""
    c = conn.cursor()
    c.execute('''
        INSERT INTO customers (phone, name, email, address, city, updated)
        VALUES (%s, %s, %s, %s, %s, to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'))
        ON CONFLICT (phone) DO UPDATE SET
            name = EXCLUDED.name,
            email = COALESCE(NULLIF(EXCLUDED.email, ''), customers.email),
            address = COALESCE(NULLIF(EXCLUDED.address, ''), customers.address),
            city = COALESCE(NULLIF(EXCLUDED.city, ''), customers.city),
            updated = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
        RETURNING id
    ''', (phone, name, email, address, city))
    result = c.fetchone()
    customer_id = result['id'] if result else None
    c.close()
    return customer_id

def update_customer_order_stats(conn, phone, amount):
    """
    Increment order statistics on the customer row identified by `phone`.

    Behaviour by customer type
    ──────────────────────────
    Existing customer:
        total_orders    → incremented by 1
        total_spent     → current order amount added to running total
        last_order_date → updated to now

    New customer (just inserted by upsert_customer with defaults 0/0/NULL):
        The same UPDATE applies.  The row was inserted with
        total_orders=0, total_spent=0, last_order_date=NULL, so after
        this call the values become total_orders=1, total_spent=<amount>,
        last_order_date=<now> — exactly right for a first order.

    Threading note
    ──────────────
    Must always be called inside the same db_lock block as
    upsert_customer() and INSERT INTO orders so all three writes are
    committed atomically in create_order().
    """
    c = conn.cursor()
    c.execute('''
        UPDATE customers SET
            total_orders    = total_orders + 1,
            total_spent     = total_spent  + %s,
            last_order_date = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'),
            updated         = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
        WHERE phone = %s
    ''', (amount, phone))
    c.close()

def gen_id(type_, card, qty, counter):
    prefix    = {'Readymade': 'WC', 'Semi-custom': 'SC'}.get(type_, 'MC')
    card_part = re.sub(r'\D', '', str(card or ''))[:3]
    qty_part  = str(qty or '')[:3]
    return f"{prefix}{card_part}{qty_part}{str(counter).zfill(2)}"

def row_to_dict(row):
    return dict(row) if row else None

def rows_to_list(rows):
    return [dict(r) for r in rows]

# ─── ROUTES: ORDERS ───────────────────────────────────────────────────────────
@app.route('/api/orders', methods=['GET'])
def list_orders():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders ORDER BY created DESC')
    rows = c.fetchall()
    c.close()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        
        # Upsert customer data and capture linked customer ID
        customer_id = upsert_customer(conn, 
            phone=data.get('phone',''),
            name=data.get('name',''),
            email=data.get('email', ''),
            address=data.get('address', ''),
            city=data.get('city', '')
        )
        
        c.execute('SELECT val FROM counter WHERE id=1')
        counter  = c.fetchone()['val']
        order_id = data.get('id') or gen_id(
            data.get('type',''), data.get('model',''), data.get('qty',0), counter
        )
        c.execute('UPDATE counter SET val = val + 1 WHERE id = 1')
        c.execute('''
            INSERT INTO orders
              (id,customer_id,name,phone,type,model,qty,price,amount,advance,payment,
               delivery,priority,handler,req,matter,commitments,status,created)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (
            order_id,
            customer_id,
            data.get('name',''),
            data.get('phone',''),
            data.get('type',''),
            data.get('model',''),
            int(data.get('qty', 0)),
            float(data.get('price', 0)),
            float(data.get('amount', 0)),
            float(data.get('advance', 0)),
            data.get('payment', 'Cash'),
            data.get('delivery', ''),
            data.get('priority', 'Normal'),
            data.get('handler', ''),
            data.get('req', ''),
            data.get('matter', ''),
            data.get('commitments', ''),
            data.get('status', 'New'),
            data.get('created', datetime.now().isoformat()),
        ))
        
        # Update customer order statistics
        update_customer_order_stats(conn, data.get('phone',''), float(data.get('amount', 0)))
        
        conn.commit()
        c.execute('SELECT * FROM orders WHERE id=%s', (order_id,))
        row = c.fetchone()
        c.close()
        conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE id=%s', (order_id,))
    row = c.fetchone()
    c.close()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row_to_dict(row))

@app.route('/api/orders/<order_id>', methods=['PUT'])
def update_order(order_id):
    data = request.get_json()
    with db_lock:
        conn = get_db()
        c = conn.cursor()

        # BUG FIX: fetch the current order so we can adjust customer stats correctly.
        # We need the old phone (customer may change) and the old amount.
        c.execute('SELECT phone, amount FROM orders WHERE id=%s', (order_id,))
        old_order = c.fetchone()
        old_phone  = old_order['phone']  if old_order else None
        old_amount = float(old_order['amount']) if old_order else 0.0

        new_phone  = data.get('phone', '')
        new_amount = float(data.get('amount', 0))

        customer_id = upsert_customer(conn,
            phone=new_phone,
            name=data.get('name',''),
            email=data.get('email',''),
            address=data.get('address',''),
            city=data.get('city','')
        )
        c.execute('''
            UPDATE orders SET
              customer_id=%s, name=%s, phone=%s, type=%s, model=%s, qty=%s, price=%s,
              amount=%s, advance=%s, payment=%s, delivery=%s, priority=%s,
              handler=%s, req=%s, matter=%s, commitments=%s, status=%s
            WHERE id=%s
        ''', (
            customer_id,
            data.get('name'),
            new_phone,
            data.get('type'),
            data.get('model'),
            int(data.get('qty', 0)),
            float(data.get('price', 0)),
            new_amount,
            float(data.get('advance', 0)),
            data.get('payment'),
            data.get('delivery'),
            data.get('priority'),
            data.get('handler'),
            data.get('req'),
            data.get('matter'),
            data.get('commitments'),
            data.get('status'),
            order_id,
        ))

        # BUG FIX: keep customer stats in sync when the order amount or phone changes.
        if old_phone and old_phone != new_phone:
            # Customer reassigned: undo the order on the old customer, credit new one.
            c.execute('''
                UPDATE customers SET
                    total_orders = GREATEST(total_orders - 1, 0),
                    total_spent  = GREATEST(total_spent  - %s, 0),
                    updated      = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
                WHERE phone = %s
            ''', (old_amount, old_phone))
            # Add to the new customer (they may be brand-new via upsert_customer above,
            # so total_orders starts at 0 — incrementing gives the correct value of 1).
            c.execute('''
                UPDATE customers SET
                    total_orders    = total_orders + 1,
                    total_spent     = total_spent  + %s,
                    last_order_date = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'),
                    updated         = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
                WHERE phone = %s
            ''', (new_amount, new_phone))
        elif old_phone and old_amount != new_amount:
            # Same customer, only the amount changed — adjust the running total.
            c.execute('''
                UPDATE customers SET
                    total_spent = GREATEST(total_spent - %s + %s, 0),
                    updated     = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
                WHERE phone = %s
            ''', (old_amount, new_amount, new_phone))

        conn.commit()
        c.execute('SELECT * FROM orders WHERE id=%s', (order_id,))
        row = c.fetchone()
        c.close()
        conn.close()
    return jsonify(row_to_dict(row))

@app.route('/api/orders/<order_id>/status', methods=['PATCH'])
def patch_status(order_id):
    data   = request.get_json()
    status = data.get('status')
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE orders SET status=%s WHERE id=%s', (status, order_id))
        conn.commit()
        c.execute('SELECT * FROM orders WHERE id=%s', (order_id,))
        row = c.fetchone()
        c.close()
        conn.close()
    return jsonify(row_to_dict(row))

@app.route('/api/orders/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    with db_lock:
        conn = get_db()
        c = conn.cursor()

        # BUG FIX: capture the order's phone and amount BEFORE deleting so we
        # can subtract them from the customer's running totals.
        c.execute('SELECT phone, amount FROM orders WHERE id=%s', (order_id,))
        order = c.fetchone()

        c.execute('DELETE FROM orders WHERE id=%s', (order_id,))

        if order:
            phone  = order['phone']
            amount = float(order['amount'] or 0)
            # Decrement stats; GREATEST(..., 0) prevents going negative from
            # any historical data inconsistency.
            c.execute('''
                UPDATE customers SET
                    total_orders = GREATEST(total_orders - 1, 0),
                    total_spent  = GREATEST(total_spent  - %s, 0),
                    updated      = to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
                WHERE phone = %s
            ''', (amount, phone))

        conn.commit()
        c.close()
        conn.close()
    return jsonify({'deleted': order_id})

# ─── ROUTES: STOCK ────────────────────────────────────────────────────────────
@app.route('/api/stock', methods=['GET'])
def list_stock():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM stock ORDER BY num')
    rows = c.fetchall()
    c.close()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/stock', methods=['POST'])
def upsert_stock():
    data   = request.get_json()
    num    = data.get('num','').strip()
    qty    = int(data.get('qty', 0))
    dealer = float(data.get('dealer', 0))
    sell   = float(data.get('sell', 0))
    nop    = float(data.get('nop', 0))
    vendor = data.get('vendor','').strip()
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT num, current FROM stock WHERE num=%s', (num,))
        existing = c.fetchone()
        if existing:
            old_qty = existing['current']
            new_qty = old_qty + qty
            c.execute('''
                UPDATE stock
                SET arrived=arrived+%s, current=current+%s,
                    dealer=%s, sell=%s, nop=%s, vendor=%s
                WHERE num=%s
            ''', (qty, qty, dealer, sell, nop, vendor, num))
            log_stock_movement(conn, num, 'ADD', old_qty, new_qty, f'Added {qty} units')
        else:
            c.execute('''
                INSERT INTO stock (num,arrived,current,dealer,sell,nop,vendor)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            ''', (num, qty, qty, dealer, sell, nop, vendor))
            log_stock_movement(conn, num, 'CREATE', None, qty, 'Initial entry')
        conn.commit()
        c.execute('SELECT * FROM stock WHERE num=%s', (num,))
        row = c.fetchone()
        c.close()
        conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/api/stock/<num>/deduct', methods=['PATCH'])
def deduct_stock(num):
    data = request.get_json()
    qty = int(data.get('qty', 0))
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT current FROM stock WHERE num=%s', (num,))
        row = c.fetchone()
        if not row:
            c.close(); conn.close()
            return jsonify({'error': 'Stock item not found'}), 404
        old_qty = row['current']
        new_current = max(0, old_qty - qty)
        c.execute('UPDATE stock SET current=%s WHERE num=%s', (new_current, num))
        log_stock_movement(conn, num, 'DEDUCT', old_qty, new_current, f'Deducted {qty} units')
        conn.commit()
        c.execute('SELECT * FROM stock WHERE num=%s', (num,))
        updated = c.fetchone()
        c.close(); conn.close()
    return jsonify(row_to_dict(updated))

@app.route('/api/stock/<num>', methods=['DELETE'])
def delete_stock(num):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('DELETE FROM stock WHERE num=%s', (num,))
        conn.commit()
        c.close()
        conn.close()
    return jsonify({'deleted': num})

@app.route('/api/stock/<num>/history', methods=['GET'])
def get_stock_history(num):
    """Get stock movement history for a specific item."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM stock_history WHERE num=%s ORDER BY created DESC', (num,))
    rows = c.fetchall()
    c.close()
    conn.close()
    return jsonify(rows_to_list(rows))

# ─── ROUTES: CUSTOMERS ────────────────────────────────────────────────────────
@app.route('/api/customers', methods=['GET'])
def list_customers():
    """List all customers sorted by last order date."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM customers ORDER BY last_order_date DESC NULLS LAST')
    rows = c.fetchall()
    c.close()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/customers/<phone>', methods=['GET'])
def get_customer(phone):
    """Get customer details by phone."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM customers WHERE phone=%s', (phone,))
    row = c.fetchone()
    c.close()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row_to_dict(row))

@app.route('/api/customers', methods=['POST'])
def add_customer():
    """Add or update customer manually."""
    data = request.get_json()
    with db_lock:
        conn = get_db()
        upsert_customer(conn, 
            phone=data.get('phone',''),
            name=data.get('name',''),
            email=data.get('email', ''),
            address=data.get('address', ''),
            city=data.get('city', '')
        )
        conn.commit()
        c = conn.cursor()
        c.execute('SELECT * FROM customers WHERE phone=%s', (data.get('phone'),))
        row = c.fetchone()
        c.close()
        conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/api/customers/<phone>', methods=['PUT'])
def update_customer(phone):
    """Update customer details."""
    data = request.get_json()
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            UPDATE customers SET
                name=%s, email=%s, address=%s, city=%s,
                updated=to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS')
            WHERE phone=%s
        ''', (data.get('name'), data.get('email'), data.get('address'), 
              data.get('city'), phone))
        conn.commit()
        c.execute('SELECT * FROM customers WHERE phone=%s', (phone,))
        row = c.fetchone()
        c.close()
        conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row_to_dict(row))

# ─── ROUTES: STATS ────────────────────────────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE status != 'Delivered'")
    active        = c.fetchall()
    total_amount  = sum(r['amount']  or 0 for r in active)
    total_advance = sum(r['advance'] or 0 for r in active)
    stats = {
        'active':   len(active),
        'urgent':   sum(1 for r in active if r['priority'] == 'Urgent'),
        'design':   sum(1 for r in active if r['status'] in ('Design', 'Proof Sent')),
        'printing': sum(1 for r in active if r['status'] == 'Printing'),
        'ready':    sum(1 for r in active if r['status'] == 'Ready'),
        'balance':  total_amount - total_advance,
    }
    c.close()
    conn.close()
    return jsonify(stats)

# ─── ROUTES: COUNTER ──────────────────────────────────────────────────────────
@app.route('/api/counter', methods=['GET'])
def get_counter():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT val FROM counter WHERE id=1')
    val = c.fetchone()['val']
    c.close()
    conn.close()
    return jsonify({'counter': val})

# ─── ROUTES: EXPORT ───────────────────────────────────────────────────────────
@app.route('/api/export/orders.csv')
def export_orders_csv():
    secret = request.args.get('key','')
    # BUG FIX: no fallback default — if EXPORT_KEY is not set, deny all requests
    # rather than silently accepting the old hardcoded password.
    export_key = os.environ.get('EXPORT_KEY', '')
    if not export_key or secret != export_key:
        return jsonify({'error': 'Unauthorized'}), 401
    import csv, io
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders ORDER BY created DESC')
    rows = c.fetchall()
    c.close()
    conn.close()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['ID','Name','Phone','Type','Model','Qty','Price','Amount',
                     'Advance','Payment','Delivery','Priority','Handler',
                     'Requirements','Matter','Commitments','Status','Created'])
    for r in rows:
        writer.writerow([
            r['id'], r['name'], r['phone'], r['type'], r['model'],
            r['qty'], r['price'], r['amount'], r['advance'], r['payment'],
            r['delivery'], r['priority'], r['handler'], r['req'],
            r['matter'], r['commitments'], r['status'], r['created']
        ])
    output = si.getvalue()
    return app.response_class(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=rmcp_orders.csv'}
    )

@app.route('/api/export/stock.csv')
def export_stock_csv():
    secret = request.args.get('key','')
    export_key = os.environ.get('EXPORT_KEY', '')
    if not export_key or secret != export_key:
        return jsonify({'error': 'Unauthorized'}), 401
    import csv, io
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM stock ORDER BY num')
    rows = c.fetchall()
    c.close()
    conn.close()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(['Card No.','Arrived','Current Stock','Dealer Price',
                     'Sell Price','Without Printing','Vendor'])
    for r in rows:
        writer.writerow([r['num'], r['arrived'], r['current'],
                         r['dealer'], r['sell'], r['nop'], r['vendor']])
    output = si.getvalue()
    return app.response_class(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=rmcp_stock.csv'}
    )

# ─── SERVE FRONTEND ───────────────────────────────────────────────────────────
@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND, path)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
# BUG FIX: check DATABASE_URL at module level so gunicorn (which never enters
# the __main__ block) also fails fast with a clear message instead of a
# cryptic psycopg2 OperationalError on the first incoming request.
if not DATABASE_URL:
    raise RuntimeError(
        '❌  DATABASE_URL environment variable is not set. '
        'Add a PostgreSQL service in Railway and redeploy.'
    )

init_db()
seed_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print(f'\n✅  RMCP Backend running at http://localhost:{port}')
    print(f'   Database : PostgreSQL')
    print(f'   App URL  : http://localhost:{port}/')
    print(f'   API base : http://localhost:{port}/api/\n')
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)