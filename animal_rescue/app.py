import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, abort

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_in_production'

# ✅ FIX: Use /tmp for Vercel, normal file for local
if os.environ.get("VERCEL"):
    DATABASE = "/tmp/database.db"
else:
    DATABASE = "database.db"


# ---------------------------
# Database Connection
# ---------------------------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ---------------------------
# Initialize Database
# ---------------------------
def init_db():
    db = sqlite3.connect(DATABASE)
    cursor = db.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            animal_type TEXT NOT NULL,
            location TEXT NOT NULL,
            description TEXT NOT NULL,
            contact TEXT NOT NULL,
            status TEXT DEFAULT 'pending'
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            donor_name TEXT NOT NULL,
            amount REAL NOT NULL
        )
    ''')

    db.commit()
    db.close()


with app.app_context():
    init_db()


# ---------------------------
# Home Page
# ---------------------------
@app.route('/')
def index():
    db = get_db()

    rescued_count = db.execute(
        'SELECT COUNT(*) FROM reports WHERE status="rescued" OR status="adopted"'
    ).fetchone()[0]

    adopted_count = db.execute(
        'SELECT COUNT(*) FROM reports WHERE status="adopted"'
    ).fetchone()[0]

    total_donations = db.execute(
        'SELECT SUM(amount) FROM donations'
    ).fetchone()[0] or 0

    animals = db.execute(
        'SELECT * FROM reports WHERE status IN ("pending", "rescued") ORDER BY id DESC LIMIT 6'
    ).fetchall()

    return render_template(
        'index.html',
        rescued_count=rescued_count,
        adopted_count=adopted_count,
        total_donations=total_donations,
        animals=animals
    )


# ---------------------------
# Report Animal (FIXED)
# ---------------------------
@app.route('/report', methods=['GET', 'POST'])
def report():
    if request.method == 'POST':
        try:
            animal_type = request.form.get('animal_type')
            location = request.form.get('location')
            description = request.form.get('description')
            contact = request.form.get('contact')

            # ✅ validation
            if not all([animal_type, location, description, contact]):
                flash("All fields are required!", "danger")
                return redirect(url_for('report'))

            db = get_db()
            db.execute(
                'INSERT INTO reports (animal_type, location, description, contact, status) VALUES (?, ?, ?, ?, ?)',
                (animal_type, location, description, contact, 'pending')
            )
            db.commit()

            flash('Animal reported successfully! Our team will act shortly.', 'success')
            return redirect(url_for('report'))

        except Exception as e:
            import traceback
            traceback.print_exc()
            flash("Something went wrong. Try again.", "danger")
            return redirect(url_for('report'))

    return render_template('report.html')


# ---------------------------
# Adopt Page
# ---------------------------
@app.route('/adopt')
def adopt():
    db = get_db()
    search_query = request.args.get('search', '')

    if search_query:
        animals = db.execute(
            'SELECT * FROM reports WHERE status IN ("pending","rescued") AND (animal_type LIKE ? OR location LIKE ?)',
            ('%' + search_query + '%', '%' + search_query + '%')
        ).fetchall()
    else:
        animals = db.execute(
            'SELECT * FROM reports WHERE status IN ("pending","rescued")'
        ).fetchall()

    return render_template('adopt.html', animals=animals, search_query=search_query)


# ---------------------------
# Adopt Action
# ---------------------------
@app.route('/adopt_action/<int:animal_id>', methods=['POST'])
def adopt_action(animal_id):
    db = get_db()

    db.execute('UPDATE reports SET status="adopted" WHERE id=?', (animal_id,))
    db.commit()

    flash('Thank you for giving this animal a forever home!', 'success')
    return redirect(url_for('adopt'))


# ---------------------------
# Donate
# ---------------------------
@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if request.method == 'POST':
        donor_name = request.form.get('donor_name')
        amount = request.form.get('amount')

        try:
            amount = float(amount)

            db = get_db()
            db.execute(
                'INSERT INTO donations (donor_name, amount) VALUES (?, ?)',
                (donor_name, amount)
            )
            db.commit()

            flash('Thank you for your generous donation!', 'success')
            return redirect(url_for('donate'))

        except:
            flash('Invalid amount.', 'danger')

    return render_template('donate.html')


# ---------------------------
# Login
# ---------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')

        session['admin_logged_in'] = True
        session['username'] = username

        flash(f'Welcome {username}!', 'success')
        return redirect(url_for('admin'))

    return render_template('login.html')


# ---------------------------
# Logout
# ---------------------------
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


# ---------------------------
# Admin Dashboard
# ---------------------------
@app.route('/admin')
def admin():
    if 'admin_logged_in' not in session:
        return redirect(url_for('login'))

    db = get_db()

    reports = db.execute(
        'SELECT * FROM reports ORDER BY id DESC'
    ).fetchall()

    donations = db.execute(
        'SELECT * FROM donations ORDER BY id DESC'
    ).fetchall()

    return render_template('admin.html', reports=reports, donations=donations)


# ---------------------------
# Delete Report
# ---------------------------
@app.route('/admin/delete_report/<int:report_id>', methods=['POST'])
def delete_report(report_id):
    if 'admin_logged_in' not in session:
        abort(403)

    db = get_db()
    db.execute('DELETE FROM reports WHERE id=?', (report_id,))
    db.commit()

    flash('Report deleted.', 'success')
    return redirect(url_for('admin'))


# ---------------------------
# Update Status
# ---------------------------
@app.route('/admin/update_status/<int:report_id>', methods=['POST'])
def update_status(report_id):
    if 'admin_logged_in' not in session:
        abort(403)

    new_status = request.form.get('status')

    if new_status in ['pending', 'rescued', 'adopted']:
        db = get_db()
        db.execute(
            'UPDATE reports SET status=? WHERE id=?',
            (new_status, report_id)
        )
        db.commit()

        flash('Status updated.', 'success')

    return redirect(url_for('admin'))


# ---------------------------
# 404 Page
# ---------------------------
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


# ---------------------------
# Run App
# ---------------------------
if __name__ == '__main__':
    app.run(debug=True)
