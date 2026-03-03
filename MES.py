import os
import base64
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session
from werkzeug.utils import secure_filename
from datetime import datetime
app = Flask(__name__)
app.secret_key = "mes_secret_key"

# ---------------- DATABASE INITIALIZATION ----------------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Production table
    c.execute("""
        CREATE TABLE IF NOT EXISTS production (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            operator_name TEXT,
            good_qty INTEGER,
            reject_qty INTEGER
        )
    """)

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    
    #Inventory table
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT,
            quantity INTEGER,
            min_stock INTEGER
        )   
    """)

    # Inventory movement table
    c.execute("""
        CREATE TABLE IF NOT EXISTS inventory_movement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT,
            movement_type TEXT,
            quantity INTEGER,
            reference TEXT,
            date TEXT
        )
    """)

    # Insert default admin
    c.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "admin123"))

    conn.commit()
    conn.close()


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()

        if user:
            session['user'] = username
            return redirect(url_for('index'))
        else:
            error = "Invalid Credentials ❌"

    return render_template('login.html', error=error)


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


# ---------------- HOME ----------------
@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', user=session['user'])


# ---------------- CREATE PRODUCTION ENTRY ----------------
@app.route('/create', methods=['GET', 'POST'])
def create():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        order_id = request.form['order_id']
        operator = request.form['operator']
        good = request.form['good']
        reject = request.form['reject']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        c.execute("""
            INSERT INTO production (order_id, operator_name, good_qty, reject_qty)
            VALUES (?, ?, ?, ?)
        """, (order_id, operator, good, reject))
        conn.commit()
        conn.close()

        return redirect(url_for('dashboard'))

    return render_template('inventory/create_order.html', user=session['user'])


# ---------------- DASHBOARD ----------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM production")
    data = c.fetchall()

    c.execute("SELECT SUM(good_qty) FROM production")
    total_good = c.fetchone()[0] or 0

    c.execute("SELECT SUM(reject_qty) FROM production")
    total_reject = c.fetchone()[0] or 0

    total_orders = len(data)

    conn.close()

    return render_template(
        'inventory/dashboard.html',
        data=data,
        total_good=total_good,
        total_reject=total_reject,
        total_orders=total_orders,
        user=session['user']
    )

# ----------------------Inventory---------------------------
@app.route('/inventory')
def inventory():

    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row   # ✅ IMPORTANT
    cursor = conn.cursor()

    search = request.args.get('search')

    # 🔍 Search Filter
    if search:
        cursor.execute("SELECT * FROM inventory WHERE item_name LIKE ?", ('%' + search + '%',))
    else:
        cursor.execute("SELECT * FROM inventory")

    inventory_data = cursor.fetchall()

    # 📦 Inventory KPIs
    cursor.execute("SELECT COUNT(*) FROM inventory")
    total_items = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(quantity) FROM inventory")
    total_quantity = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM inventory WHERE quantity < min_stock")
    low_stock_count = cursor.fetchone()[0]

    # 📊 Production KPIs
    cursor.execute("SELECT COUNT(*) FROM production")
    total_orders = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(good_qty) FROM production")
    total_good = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(reject_qty) FROM production")
    total_reject = cursor.fetchone()[0] or 0

    # 🏭 Recent Production
    cursor.execute("""
        SELECT order_id, operator_name, good_qty, reject_qty
        FROM production
        ORDER BY id DESC
        LIMIT 5
    """)
    recent_production = cursor.fetchall()

    # 📈 Movement History
    cursor.execute("""
        SELECT * FROM inventory_movement
        ORDER BY id DESC
        LIMIT 10
    """)
    history = cursor.fetchall()

    conn.close()

    return render_template(
        "inventory/inventory.html",
        inventory=inventory_data,
        total_items=total_items,
        low_stock_count=low_stock_count,
        total_quantity=total_quantity,
        total_orders=total_orders,
        total_good=total_good,
        total_reject=total_reject,
        recent_production=recent_production,
        history=history
    )
#-----------------Stock IN (GRN)-----------------------
@app.route('/stock_in/<int:item_id>', methods=['POST'])
def stock_in(item_id):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("UPDATE inventory SET quantity = quantity + 10 WHERE id = ?", (item_id,))
    
    c.execute("SELECT item_name FROM inventory WHERE id = ?", (item_id,))
    item_name = c.fetchone()[0]

    reference = "GRN-" + datetime.now().strftime("%H%M%S")

    c.execute("""
        INSERT INTO inventory_movement (item_name, movement_type, quantity, reference, date)
        VALUES (?, ?, ?, ?, ?)
    """, (item_name, "Stock In", 10, reference, datetime.now().strftime("%Y-%m-%d %H:%M")))

    conn.commit()
    conn.close()

    return redirect(url_for('inventory'))

#---------------Stock OUT (Issue Slip)------------------
@app.route('/stock_out/<int:item_id>', methods=['POST'])
def stock_out(item_id):

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("UPDATE inventory SET quantity = quantity - 5 WHERE id = ?", (item_id,))
    
    c.execute("SELECT item_name FROM inventory WHERE id = ?", (item_id,))
    item_name = c.fetchone()[0]

    reference = "ISS-" + datetime.now().strftime("%H%M%S")

    c.execute("""
        INSERT INTO inventory_movement (item_name, movement_type, quantity, reference, date)
        VALUES (?, ?, ?, ?, ?)
    """, (item_name, "Stock Out", 5, reference, datetime.now().strftime("%Y-%m-%d %H:%M")))

    conn.commit()
    conn.close()

    return redirect(url_for('inventory'))

# ---------------- ASSEMBLY MAIN PAGE ----------------
@app.route('/assembly')
def assembly():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('assembly/assembly.html')


# ---------------- UPLOAD CONFIG ----------------
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


# ==============================
# BRAKE ASSEMBLY (Single Step)
# ==============================
@app.route('/assembly/brake', methods=['GET', 'POST'])
def brake_assembly():

    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        # File Upload
        if 'photo' in request.files and request.files['photo'].filename != '':
            file = request.files['photo']
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Live Camera Capture
        elif 'photo_data' in request.form and request.form['photo_data'] != '':
            photo_data = request.form['photo_data']
            header, encoded = photo_data.split(",", 1)
            data = base64.b64decode(encoded)

            filename = "brake_assembly.png"
            with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), "wb") as f:
                f.write(data)

        return redirect(url_for('assembly_success'))

    return render_template('assembly/brake_assembly.html')


@app.route('/assembly/success')
def assembly_success():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('assembly/assembly_success.html')


# ==============================
# TYRE ASSEMBLY (Single Step)
# ==============================
@app.route('/assembly/tyre', methods=['GET', 'POST'])
def tyre_assembly():

    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        # File Upload
        if 'photo' in request.files and request.files['photo'].filename != '':
            file = request.files['photo']
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Live Camera Capture
        elif 'photo_data' in request.form and request.form['photo_data'] != '':
            photo_data = request.form['photo_data']
            header, encoded = photo_data.split(",", 1)
            data = base64.b64decode(encoded)

            filename = "tyre_assembly.png"         
            with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), "wb") as f:
                f.write(data)

        return redirect(url_for('assembly_success'))

    return render_template('assembly/tyre_assembly.html')


# ==============================
# WHEEL ASSEMBLY (Single Step)
# ==============================
@app.route('/assembly/wheel', methods=['GET', 'POST'])
def wheel_assembly():

    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        # File Upload
        if 'photo' in request.files and request.files['photo'].filename != '':
            file = request.files['photo']
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        # Live Camera Capture
        elif 'photo_data' in request.form and request.form['photo_data'] != '':
            photo_data = request.form['photo_data']
            header, encoded = photo_data.split(",", 1)
            data = base64.b64decode(encoded)

            filename = "wheel_assembly.png"
            with open(os.path.join(app.config['UPLOAD_FOLDER'], filename), "wb") as f:
                f.write(data)

        return redirect(url_for('assembly_success'))

    return render_template('assembly/wheel_assembly.html')


# ---------------- QUALITY ----------------
@app.route('/quality')
def quality():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Create table if not exists (safe check)
    c.execute("""
        CREATE TABLE IF NOT EXISTS quality_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            status TEXT,
            remarks TEXT,
            created_at TEXT
        )
    """)

    # Fetch logs
    c.execute("SELECT * FROM quality_logs ORDER BY id DESC")
    logs = c.fetchall()

    conn.close()

    return render_template('quality.html', logs=logs)

# ---------------- LOG DEFECT ----------------
@app.route('/log_defect', methods=['POST'])
def log_defect():
    if 'user' not in session:
        return redirect(url_for('login'))

    item = request.form.get('item')
    status = request.form.get('status', 'Fail')  # Default Fail if not passed
    remarks = request.form.get('remarks')

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS quality_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            status TEXT,
            remarks TEXT,
            created_at TEXT
        )
    """)

    c.execute("""
        INSERT INTO quality_logs (item, status, remarks, created_at)
        VALUES (?, ?, ?, ?)
    """, (item, status, remarks, datetime.now().strftime("%Y-%m-%d %H:%M")))

    conn.commit()
    conn.close()

    return redirect(url_for('quality'))

# ---------------- PLANT OVERVIEW ----------------
@app.route('/plant')
def plant():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM production")
    total_orders = c.fetchone()[0] or 0

    c.execute("SELECT SUM(good_qty) FROM production")
    total_good = c.fetchone()[0] or 0

    c.execute("SELECT SUM(reject_qty) FROM production")
    total_reject = c.fetchone()[0] or 0

    conn.close()

    # Simulated OEE
    oee = 92

    return render_template(
        "plant/plant.html",
        total_orders=total_orders,
        total_good=total_good,
        total_reject=total_reject,
        oee=oee
    )
#-----------------------Plant overview (downtime,uptime,predictive,quality pages)-----------
@app.route("/production-trends")
def production_trends():
    return render_template("plant/production_trends.html")

@app.route("/downtime-analysis")
def downtime_analysis():
    return render_template("plant/downtime_analysis.html")

@app.route("/quality-report")
def quality_report():
    return render_template("plant/quality_report.html")

@app.route("/predictive-insights")
def predictive_insights():
    return render_template("plant/predictive_insights.html")

#-----------------------assembly operation-----------
@app.route('/assembly/operations')
def assembly_operations():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('assembly_operations.html')

# ---------------- RUN APP ----------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)