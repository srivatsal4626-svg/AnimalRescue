import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, session, g, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super_secret_key_change_in_production'
DATABASE = 'database.db'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    cursor.execute('SELECT * FROM admin WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute('INSERT INTO admin (username, password) VALUES (?, ?)', ('admin', hashed_pw))

    db.commit()
    db.close()


# Initialize database when app starts
with app.app_context():
    init_db()


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


@app.route('/report', methods=['GET', 'POST'])
def report():
    if request.method == 'POST':
        animal_type = request.form['animal_type']
        location = request.form['location']
        description = request.form['description']
        contact = request.form['contact']

        db = get_db()
        db.execute(
            'INSERT INTO reports (animal_type, location, description, contact, status) VALUES (?, ?, ?, ?, ?)',
            (animal_type, location, description, contact, 'pending')
        )
        db.commit()

        flash('Animal reported successfully! Our team will act shortly.', 'success')
        return redirect(url_for('report'))

    return render_template('report.html')


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


@app.route('/adopt_action/<int:animal_id>', methods=['POST'])
def adopt_action(animal_id):
    db = get_db()
    db.execute('UPDATE reports SET status="adopted" WHERE id=?', (animal_id,))
    db.commit()

    flash('Thank you for giving this animal a forever home!', 'success')
    return redirect(url_for('adopt'))


@app.route('/donate', methods=['GET', 'POST'])
def donate():
    if request.method == 'POST':
        donor_name = request.form['donor_name']
        amount = request.form['amount']

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

        except ValueError:
            flash('Invalid amount. Please enter a valid number.', 'danger')

    return render_template('donate.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        admin = db.execute(
            'SELECT * FROM admin WHERE username=?',
            (username,)
        ).fetchone()

        if admin and check_password_hash(admin['password'], password):
            session['admin_logged_in'] = True
            flash('Logged in successfully!', 'success')
            return redirect(url_for('admin'))

        flash('Invalid username or password', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))


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


@app.route('/admin/delete_report/<int:report_id>', methods=['POST'])
def delete_report(report_id):
    if 'admin_logged_in' not in session:
        abort(403)

    db = get_db()
    db.execute('DELETE FROM reports WHERE id=?', (report_id,))
    db.commit()

    flash('Report deleted.', 'success')
    return redirect(url_for('admin'))


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


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)
