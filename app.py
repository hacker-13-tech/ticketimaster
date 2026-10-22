import os, sqlite3, secrets, json, hmac, hashlib
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort
from werkzeug.security import check_password_hash, generate_password_hash

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DATABASE_PATH', os.path.join(BASE, 'ticketimaster.db'))
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-only-change-me-' + secrets.token_hex(16))
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0') == '1', MAX_CONTENT_LENGTH=2 * 1024 * 1024)

SAMPLE_EVENTS = [
 ("ev-1001", "Neon Nights: Live in Los Angeles", "music", "Los Angeles, CA", "2027-02-12T19:30:00", 79.00, "A high-energy night of live music and special guests.", "https://images.unsplash.com/photo-1459749411175-04bf5292ceea?auto=format&fit=crop&w=1200&q=85"),
 ("ev-1002", "New York Knicks vs. Chicago Bulls", "sports", "New York, NY", "2027-01-23T19:00:00", 115.00, "Catch an electric night of pro basketball.", "https://images.unsplash.com/photo-1504450758481-7338eba7524a?auto=format&fit=crop&w=1200&q=85"),
 ("ev-1003", "Broadway After Dark", "theatre", "New York, NY", "2027-03-08T20:00:00", 64.00, "A dazzling stage production in the heart of Broadway.", "https://images.unsplash.com/photo-1503095396549-807759245b35?auto=format&fit=crop&w=1200&q=85"),
 ("ev-1004", "Desert Sound Festival", "music", "Phoenix, AZ", "2027-04-17T16:00:00", 129.00, "A full-day outdoor festival featuring rising artists.", "https://images.unsplash.com/photo-1470229722913-7c0e2dbbafd3?auto=format&fit=crop&w=1200&q=85"),
 ("ev-1005", "Championship Night: Ice Hockey", "sports", "Chicago, IL", "2027-02-06T18:30:00", 92.00, "Fast-paced action and an unforgettable crowd.", "https://images.unsplash.com/photo-1515703407324-5f753afd8be8?auto=format&fit=crop&w=1200&q=85"),
 ("ev-1006", "Comedy on the Coast", "comedy", "San Diego, CA", "2027-01-30T20:00:00", 38.00, "A stand-up showcase with nationally touring comics.", "https://images.unsplash.com/photo-1585699324551-f6c309eedeca?auto=format&fit=crop&w=1200&q=85"),
]

def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db

def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, city TEXT NOT NULL, starts_at TEXT NOT NULL, price REAL NOT NULL, description TEXT NOT NULL, image_url TEXT NOT NULL, inventory INTEGER NOT NULL DEFAULT 100, active INTEGER NOT NULL DEFAULT 1, source TEXT NOT NULL DEFAULT 'demo');
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, email TEXT NOT NULL, event_id TEXT NOT NULL REFERENCES events(id), quantity INTEGER NOT NULL, total REAL NOT NULL, status TEXT NOT NULL, provider TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tickets(id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), event_id TEXT NOT NULL REFERENCES events(id), code_hash TEXT NOT NULL UNIQUE, used INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admins(username TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
        ''')
        if db.execute('SELECT COUNT(*) FROM events').fetchone()[0] == 0:
            db.executemany('INSERT INTO events(id,title,category,city,starts_at,price,description,image_url,inventory,source) VALUES(?,?,?,?,?,?,?,?,?,?)', [(*e, 100, 'demo') for e in SAMPLE_EVENTS])
        user = os.environ.get('ADMIN_USERNAME', 'admin')
        password = os.environ.get('ADMIN_PASSWORD', 'change-this-before-deploy')
        db.execute('INSERT OR IGNORE INTO admins(username,password_hash) VALUES(?,?)', (user, generate_password_hash(password)))

init_db()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin'): return redirect(url_for('admin_login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def get_event(event_id):
    with connect() as db: return db.execute('SELECT * FROM events WHERE id=? AND active=1', (event_id,)).fetchone()

@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'DENY'
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if os.environ.get('COOKIE_SECURE','0') == '1': resp.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return resp

@app.route('/')
def index():
    q = request.args.get('q','').strip()[:100]
    category = request.args.get('category','').strip()[:30]
    city = request.args.get('city','').strip()[:60]
    sql = 'SELECT * FROM events WHERE active=1'; params=[]
    if q: sql += ' AND (title LIKE ? OR description LIKE ? OR city LIKE ?)'; params += [f'%{q}%']*3
    if category: sql += ' AND category=?'; params.append(category)
    if city: sql += ' AND city LIKE ?'; params.append(f'%{city}%')
    sql += ' ORDER BY starts_at LIMIT 60'
    with connect() as db: events = db.execute(sql, params).fetchall()
    return render_template('index.html', events=events, q=q, category=category, city=city)

@app.route('/event/<event_id>')
def event_detail(event_id):
    event=get_event(event_id)
    if not event: abort(404)
    return render_template('event.html', event=event)

@app.route('/checkout/<event_id>', methods=['GET','POST'])
def checkout(event_id):
    event=get_event(event_id)
    if not event: abort(404)
    if request.method == 'GET': return render_template('checkout.html', event=event)
    email=request.form.get('email','').strip().lower()[:254]
    try: quantity=int(request.form.get('quantity','1'))
    except ValueError: quantity=0
    if '@' not in email or '.' not in email.split('@')[-1] or quantity < 1 or quantity > 8:
        flash('Enter a valid email and choose 1–8 tickets.', 'error'); return redirect(url_for('checkout', event_id=event_id))
    provider=request.form.get('provider','demo')
    if quantity > event['inventory']:
        flash('Sorry, not enough tickets are currently available.', 'error'); return redirect(url_for('event_detail', event_id=event_id))
    # Without configured payment credentials, only a clearly-labelled test order is possible.
    if provider == 'stripe' and os.environ.get('STRIPE_SECRET_KEY'):
        try:
            import stripe
            stripe.api_key=os.environ['STRIPE_SECRET_KEY']
            order_id=secrets.token_urlsafe(12)
            with connect() as db:
                db.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?)',(order_id,email,event_id,quantity,round(event['price']*quantity,2),'pending','stripe',datetime.now(timezone.utc).isoformat()))
                db.execute('UPDATE events SET inventory=inventory-? WHERE id=?',(quantity,event_id))
            checkout_session=stripe.checkout.Session.create(mode='payment', customer_email=email, line_items=[{'price_data':{'currency':'usd','product_data':{'name':event['title']},'unit_amount':int(round(event['price']*100))},'quantity':quantity}], success_url=url_for('payment_success',order_id=order_id,_external=True)+'?session_id={CHECKOUT_SESSION_ID}', cancel_url=url_for('event_detail',event_id=event_id,_external=True), metadata={'order_id':order_id})
            with connect() as db: db.execute('UPDATE orders SET status=? WHERE id=?',('awaiting_payment:'+checkout_session.id,order_id))
            return redirect(checkout_session.url, code=303)
        except Exception:
            app.logger.exception('Stripe checkout failed')
            flash('Payment could not be started. Please try again later.', 'error'); return redirect(url_for('checkout',event_id=event_id))
    if provider == 'paypal':
        flash('PayPal is not configured yet. Add PayPal REST credentials and enable the server-side order/capture integration before accepting payments.', 'error')
        return redirect(url_for('checkout',event_id=event_id))
    # Test mode is deliberately not a real paid order and does not issue valid tickets.
    session['demo_checkout']={'event_id':event_id,'email':email,'quantity':quantity}
    return render_template('demo_payment.html', event=event, email=email, quantity=quantity, total=round(event['price']*quantity,2))

@app.route('/demo-confirm', methods=['POST'])
def demo_confirm():
    if not app.config.get('TESTING') and os.environ.get('ALLOW_DEMO_CHECKOUT','1') != '1': abort(403)
    data=session.pop('demo_checkout',None)
    if not data: return redirect(url_for('index'))
    flash('Demo only: no payment was taken and no valid ticket was issued. Configure a payment provider to enable real purchases.', 'error')
    return redirect(url_for('event_detail',event_id=data['event_id']))

@app.route('/payment/success')
def payment_success():
    order_id=request.args.get('order_id','')
    with connect() as db: order=db.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone()
    if not order: abort(404)
    # Stripe success redirect alone is not proof of payment. Webhook must mark paid and issue tickets.
    return render_template('payment_status.html', order=order)

@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    secret=os.environ.get('STRIPE_WEBHOOK_SECRET')
    if not secret: abort(503)
    try:
        import stripe
        event=stripe.Webhook.construct_event(request.get_data(), request.headers.get('Stripe-Signature',''), secret)
    except Exception:
        return 'invalid signature',400
    if event['type']=='checkout.session.completed':
        obj=event['data']['object']; order_id=(obj.get('metadata') or {}).get('order_id')
        if order_id and obj.get('payment_status')=='paid': issue_tickets(order_id, 'stripe')
    return jsonify(received=True)

def issue_tickets(order_id, provider):
    with connect() as db:
        order=db.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone()
        if not order or order['status']=='paid': return
        db.execute('UPDATE orders SET status=?,provider=? WHERE id=?',('paid',provider,order_id))
        for _ in range(order['quantity']):
            raw=secrets.token_urlsafe(24); tid=secrets.token_urlsafe(10)
            db.execute('INSERT INTO tickets(id,order_id,event_id,code_hash,created_at) VALUES(?,?,?,?,?)',(tid,order_id,order['event_id'],hashlib.sha256(raw.encode()).hexdigest(),datetime.now(timezone.utc).isoformat()))
            # Raw codes are intentionally not logged; production email delivery should send a signed ticket URL.

@app.route('/ticket/validate', methods=['POST'])
@admin_required
def validate_ticket():
    code=request.form.get('code','').strip()
    digest=hashlib.sha256(code.encode()).hexdigest()
    with connect() as db:
        t=db.execute('SELECT tickets.*,events.title FROM tickets JOIN events ON events.id=tickets.event_id WHERE code_hash=?',(digest,)).fetchone()
        if not t: return jsonify(ok=False,message='Ticket not found'),404
        if t['used']: return jsonify(ok=False,message='Ticket already used'),409
        db.execute('UPDATE tickets SET used=1 WHERE id=?',(t['id'],))
    return jsonify(ok=True,message='Ticket validated',event=t['title'])

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method=='POST':
        username=request.form.get('username','')[:100]; password=request.form.get('password','')
        with connect() as db: admin=db.execute('SELECT * FROM admins WHERE username=?',(username,)).fetchone()
        if admin and check_password_hash(admin['password_hash'],password):
            session.clear(); session['admin']=username; return redirect(request.args.get('next') or url_for('admin_dashboard'))
        flash('Invalid login details.', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.clear(); return redirect(url_for('index'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    with connect() as db:
        events=db.execute('SELECT * FROM events ORDER BY starts_at').fetchall()
        orders=db.execute('SELECT orders.*,events.title FROM orders JOIN events ON events.id=orders.event_id ORDER BY created_at DESC LIMIT 100').fetchall()
        totals=db.execute("SELECT COUNT(*) AS orders, COALESCE(SUM(CASE WHEN status='paid' THEN total ELSE 0 END),0) AS revenue FROM orders").fetchone()
    return render_template('admin.html',events=events,orders=orders,totals=totals)

@app.route('/admin/events/new', methods=['POST'])
@admin_required
def admin_new_event():
    title=request.form.get('title','').strip()[:160]; category=request.form.get('category','music')[:30]; city=request.form.get('city','').strip()[:100]
    starts=request.form.get('starts_at',''); desc=request.form.get('description','').strip()[:1000]; image=request.form.get('image_url','').strip()[:500]
    try: price=float(request.form.get('price','0')); inventory=int(request.form.get('inventory','0'))
    except ValueError: price=-1; inventory=-1
    if not title or not city or not desc or price<0 or price>100000 or inventory<0 or inventory>1000000:
        flash('Check the event details and numeric values.', 'error'); return redirect(url_for('admin_dashboard'))
    event_id='ev-'+secrets.token_hex(6)
    with connect() as db: db.execute('INSERT INTO events(id,title,category,city,starts_at,price,description,image_url,inventory,source) VALUES(?,?,?,?,?,?,?,?,?,?)',(event_id,title,category,city,starts,price,desc,image or 'https://images.unsplash.com/photo-1492684223066-81342ee5ff30?auto=format&fit=crop&w=1200&q=85',inventory,'admin'))
    flash('Event created.', 'success'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/events/<event_id>/toggle', methods=['POST'])
@admin_required
def admin_toggle_event(event_id):
    with connect() as db: db.execute('UPDATE events SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?',(event_id,))
    return redirect(url_for('admin_dashboard'))

@app.route('/health')
def health(): return jsonify(status='ok')

@app.errorhandler(404)
def not_found(e): return render_template('404.html'),404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT','5000')), debug=False)
