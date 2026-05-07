"""
RMCP Order System — Flask Backend
Raj Multi Color Print · Kakinada · ESTD 1983
Database: PostgreSQL
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

    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id          TEXT PRIMARY KEY,
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
            created     TEXT     DEFAULT (to_char(NOW(), 'YYYY-MM-DD"T"HH24:MI:SS'))
        )
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

    orders = [
        ('WC10310001','Siddha Venkateswara Rao','99999 99999','Readymade','R103',100,22,2200,1000,'Cash',
         date_off(2),'Urgent','Brother 1','Telugu + English, Gold Acrylic plate',
         'Bride: Priya, Groom: Siddha Venkateswara Rao. Parents: Suresh & Lakshmi. Wedding: 25 April 2025. Venue: Sri Kalyana Mandapam.',
         'Delivery on 25th morning 9 AM sharp','Printing'),
        ('WC10150002','Thummala Babu','88888 88888','Semi-custom','R101',500,18,9000,5000,'PhonePe',
         date_off(5),'Normal','Brother 2','Two different matters, each 250 cards',
         'Matter 1: Bride: Anitha, Groom: Raju. Matter 2: Bride: Swathi, Groom: Kumar.',
         '','Proof Sent'),
        ('MC150003','Uppalapati Rudra Raju','77777 77777','Fully customised','Customised',1500,65,97500,50000,'Cash',
         date_off(12),'Normal','Brother 1','9×9 size, Box Cover, Title with gold foil, Inner two sheets S/S',
         'Full Telugu matter to be provided separately.',
         'Agreed to deliver 2 days early if possible','Design'),
        ('WC10340004','Lakshmi Prasad','99112233445','Readymade','R103',400,22,8800,3000,'PhonePe',
         date_off(-1),'Urgent','Brother 2','','','','Ready'),
    ]
    for o in orders:
        c.execute('''
            INSERT INTO orders
              (id,name,phone,type,model,qty,price,amount,advance,payment,
               delivery,priority,handler,req,matter,commitments,status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
        ''', o)

    c.execute('UPDATE counter SET val = 5 WHERE id = 1')
    conn.commit()
    c.close()
    conn.close()
    print('✅ Demo data seeded')

# ─── HELPERS ──────────────────────────────────────────────────────────────────
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
        c.execute('SELECT val FROM counter WHERE id=1')
        counter  = c.fetchone()['val']
        order_id = data.get('id') or gen_id(
            data.get('type',''), data.get('model',''), data.get('qty',0), counter
        )
        c.execute('UPDATE counter SET val = val + 1 WHERE id = 1')
        c.execute('''
            INSERT INTO orders
              (id,name,phone,type,model,qty,price,amount,advance,payment,
               delivery,priority,handler,req,matter,commitments,status,created)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (
            order_id,
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
        c.execute('''
            UPDATE orders SET
              name=%s, phone=%s, type=%s, model=%s, qty=%s, price=%s,
              amount=%s, advance=%s, payment=%s, delivery=%s, priority=%s,
              handler=%s, req=%s, matter=%s, commitments=%s, status=%s
            WHERE id=%s
        ''', (
            data.get('name'),
            data.get('phone'),
            data.get('type'),
            data.get('model'),
            int(data.get('qty', 0)),
            float(data.get('price', 0)),
            float(data.get('amount', 0)),
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
        c.execute('DELETE FROM orders WHERE id=%s', (order_id,))
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
        c.execute('SELECT num FROM stock WHERE num=%s', (num,))
        existing = c.fetchone()
        if existing:
            c.execute('''
                UPDATE stock
                SET arrived=arrived+%s, current=current+%s,
                    dealer=%s, sell=%s, nop=%s, vendor=%s
                WHERE num=%s
            ''', (qty, qty, dealer, sell, nop, vendor, num))
        else:
            c.execute('''
                INSERT INTO stock (num,arrived,current,dealer,sell,nop,vendor)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            ''', (num, qty, qty, dealer, sell, nop, vendor))
        conn.commit()
        c.execute('SELECT * FROM stock WHERE num=%s', (num,))
        row = c.fetchone()
        c.close()
        conn.close()
    return jsonify(row_to_dict(row)), 201

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
    if secret != os.environ.get('EXPORT_KEY', 'rmcp2024'):
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
    if secret != os.environ.get('EXPORT_KEY', 'rmcp2024'):
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
if __name__ == '__main__':
    if not DATABASE_URL:
        print('❌  ERROR: DATABASE_URL environment variable is not set.')
        print('   For local use, set it in a .env file or run:')
        print('   set DATABASE_URL=postgresql://user:password@localhost:5432/rmcp')
        exit(1)
    init_db()
    seed_db()
    port = int(os.environ.get('PORT', 5050))
    print(f'\n✅  RMCP Backend running at http://localhost:{port}')
    print(f'   Database : PostgreSQL')
    print(f'   App URL  : http://localhost:{port}/')
    print(f'   API base : http://localhost:{port}/api/\n')
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)