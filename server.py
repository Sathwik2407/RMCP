"""
RMCP Order System — Flask Backend
Raj Multi Color Print · Kakinada · ESTD 1983
"""

import sqlite3
import os
import re
from datetime import date, datetime
from flask import Flask, request, jsonify, send_from_directory

# ─── CONFIG ───────────────────────────────────────────────────────────────────
# Uses /data/rmcp.db on Railway (persistent volume), falls back to local file
DB_PATH  = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'rmcp.db'))
FRONTEND = os.path.join(os.path.dirname(__file__), 'public')

app = Flask(__name__, static_folder=FRONTEND, static_url_path='')

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

# ─── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    # Make sure the directory exists (important for /data volume on Railway)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = get_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            phone       TEXT NOT NULL,
            type        TEXT NOT NULL,
            model       TEXT,
            qty         INTEGER DEFAULT 0,
            price       REAL    DEFAULT 0,
            amount      REAL    DEFAULT 0,
            advance     REAL    DEFAULT 0,
            payment     TEXT,
            delivery    TEXT,
            priority    TEXT    DEFAULT 'Normal',
            handler     TEXT,
            req         TEXT,
            matter      TEXT,
            commitments TEXT,
            status      TEXT    DEFAULT 'New',
            created     TEXT    DEFAULT (datetime('now'))
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
            id  INTEGER PRIMARY KEY CHECK (id = 1),
            val INTEGER DEFAULT 1
        )
    ''')
    c.execute('INSERT OR IGNORE INTO counter (id, val) VALUES (1, 1)')

    conn.commit()
    conn.close()

def seed_db():
    """Seed demo data only if tables are empty."""
    conn = get_db()
    c = conn.cursor()
    if c.execute('SELECT COUNT(*) FROM orders').fetchone()[0] > 0:
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
    c.executemany(
        'INSERT OR IGNORE INTO stock (num,arrived,current,dealer,sell,nop,vendor) VALUES (?,?,?,?,?,?,?)',
        stock_rows
    )

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
    c.executemany(
        '''INSERT OR IGNORE INTO orders
           (id,name,phone,type,model,qty,price,amount,advance,payment,delivery,priority,handler,req,matter,commitments,status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        orders
    )
    c.execute('UPDATE counter SET val = 5 WHERE id = 1')
    conn.commit()
    conn.close()

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def gen_id(type_, card, qty, counter):
    prefix = {'Readymade': 'WC', 'Semi-custom': 'SC'}.get(type_, 'MC')
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
    rows = conn.execute('SELECT * FROM orders ORDER BY created DESC').fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()

    counter = c.execute('SELECT val FROM counter WHERE id=1').fetchone()['val']
    order_id = data.get('id') or gen_id(data.get('type',''), data.get('model',''), data.get('qty',0), counter)
    c.execute('UPDATE counter SET val = val + 1 WHERE id = 1')

    c.execute('''
        INSERT INTO orders
          (id,name,phone,type,model,qty,price,amount,advance,payment,
           delivery,priority,handler,req,matter,commitments,status,created)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
    row = c.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/api/orders/<order_id>', methods=['GET'])
def get_order(order_id):
    conn = get_db()
    row = conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(row_to_dict(row))

@app.route('/api/orders/<order_id>', methods=['PUT'])
def update_order(order_id):
    data = request.get_json()
    conn = get_db()
    c = conn.cursor()
    c.execute('''
        UPDATE orders SET
          name=?, phone=?, type=?, model=?, qty=?, price=?, amount=?, advance=?,
          payment=?, delivery=?, priority=?, handler=?, req=?, matter=?,
          commitments=?, status=?
        WHERE id=?
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
    row = c.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))

@app.route('/api/orders/<order_id>/status', methods=['PATCH'])
def patch_status(order_id):
    data = request.get_json()
    status = data.get('status')
    conn = get_db()
    conn.execute('UPDATE orders SET status=? WHERE id=?', (status, order_id))
    conn.commit()
    row = conn.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))

@app.route('/api/orders/<order_id>', methods=['DELETE'])
def delete_order(order_id):
    conn = get_db()
    conn.execute('DELETE FROM orders WHERE id=?', (order_id,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': order_id})

# ─── ROUTES: STOCK ────────────────────────────────────────────────────────────
@app.route('/api/stock', methods=['GET'])
def list_stock():
    conn = get_db()
    rows = conn.execute('SELECT * FROM stock ORDER BY num').fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))

@app.route('/api/stock', methods=['POST'])
def upsert_stock():
    data = request.get_json()
    num    = data.get('num','').strip()
    qty    = int(data.get('qty', 0))
    dealer = float(data.get('dealer', 0))
    sell   = float(data.get('sell', 0))
    nop    = float(data.get('nop', 0))
    vendor = data.get('vendor','').strip()

    conn = get_db()
    c = conn.cursor()
    existing = c.execute('SELECT * FROM stock WHERE num=?', (num,)).fetchone()
    if existing:
        c.execute('''
            UPDATE stock
            SET arrived=arrived+?, current=current+?, dealer=?, sell=?, nop=?, vendor=?
            WHERE num=?
        ''', (qty, qty, dealer, sell, nop, vendor, num))
    else:
        c.execute('''
            INSERT INTO stock (num,arrived,current,dealer,sell,nop,vendor)
            VALUES (?,?,?,?,?,?,?)
        ''', (num, qty, qty, dealer, sell, nop, vendor))
    conn.commit()
    row = c.execute('SELECT * FROM stock WHERE num=?', (num,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201

@app.route('/api/stock/<num>', methods=['DELETE'])
def delete_stock(num):
    conn = get_db()
    conn.execute('DELETE FROM stock WHERE num=?', (num,))
    conn.commit()
    conn.close()
    return jsonify({'deleted': num})

# ─── ROUTES: STATS ────────────────────────────────────────────────────────────
@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    c = conn.cursor()
    active = c.execute("SELECT * FROM orders WHERE status != 'Delivered'").fetchall()
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
    conn.close()
    return jsonify(stats)

# ─── ROUTES: COUNTER ──────────────────────────────────────────────────────────
@app.route('/api/counter', methods=['GET'])
def get_counter():
    conn = get_db()
    val = conn.execute('SELECT val FROM counter WHERE id=1').fetchone()['val']
    conn.close()
    return jsonify({'counter': val})

# ─── SERVE FRONTEND ───────────────────────────────────────────────────────────
@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(FRONTEND, path)

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    seed_db()
    port = int(os.environ.get('PORT', 5050))
    print(f'\n✅  RMCP Backend running at http://localhost:{port}')
    print(f'   Database location: {DB_PATH}')
    print(f'   Frontend served at: http://localhost:{port}/')
    print(f'   API base:           http://localhost:{port}/api/\n')
    app.run(host='0.0.0.0', port=port, debug=False)