import sqlite3
import uuid
import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, g

app = Flask(__name__)
app.secret_key = 'super_secret_key'  # In a real app, use a secure random key

# Vercel environment detection for ephemeral storage
if os.environ.get('VERCEL'):
    DATABASE = '/tmp/database.db'
else:
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
    with app.app_context():
        db = get_db()
        # Create Events table
        db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                date TEXT NOT NULL,
                time TEXT NOT NULL,
                location TEXT NOT NULL,
                added_by TEXT
            )
        ''')
        # Create Registrations table
        db.execute('''
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                registration_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                event_id INTEGER NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events (id),
                UNIQUE(email, event_id),
                UNIQUE(phone, event_id)
            )
        ''')
        # Create Admins table
        db.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')
        
        # Add default admin if not exists
        admin = db.execute('SELECT * FROM admins WHERE username = "admin"').fetchone()
        if not admin:
            # Using plain text password for simplicity in this demo, hash in production
            db.execute('INSERT INTO admins (username, password) VALUES ("admin", "admin123")')
            
        db.commit()

# Ensure DB is initialized before first request (useful for Vercel)
@app.before_request
def initialize_database():
    app.before_request_funcs[None].remove(initialize_database)
    init_db()

# --- User Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/events')
def events():
    db = get_db()
    events = db.execute('SELECT * FROM events ORDER BY date').fetchall()
    return render_template('events.html', events=events)

@app.route('/register/<int:event_id>', methods=['GET', 'POST'])
def register(event_id):
    db = get_db()
    event = db.execute('SELECT * FROM events WHERE id = ?', (event_id,)).fetchone()
    
    if not event:
        flash('Event not found.', 'danger')
        return redirect(url_for('events'))
        
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        
        # Check for duplicates
        existing = db.execute('SELECT * FROM registrations WHERE (email = ? OR phone = ?) AND event_id = ?', 
                              (email, phone, event_id)).fetchone()
        if existing:
            flash('You are already registered for this event with this email or phone number.', 'warning')
            return redirect(url_for('register', event_id=event_id))
            
        # Generate unique registration ID
        reg_id = 'EVT-' + str(uuid.uuid4())[:8].upper()
        
        try:
            db.execute('INSERT INTO registrations (registration_id, name, email, phone, event_id) VALUES (?, ?, ?, ?, ?)',
                       (reg_id, name, email, phone, event_id))
            db.commit()
            flash(f'Successfully registered! Your Registration ID is {reg_id}', 'success')
            return redirect(url_for('events'))
        except sqlite3.Error as e:
            flash(f'An error occurred: {e}', 'danger')
            
    return render_template('register.html', event=event)

# --- Admin Routes ---

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        db = get_db()
        admin = db.execute('SELECT * FROM admins WHERE username = ? AND password = ?', (username, password)).fetchone()
        
        if admin:
            session['admin_logged_in'] = True
            session['admin_username'] = username
            flash('Logged in successfully.', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
            
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('Logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    db = get_db()
    events = db.execute('SELECT id, name, date, time, location FROM events').fetchall()
    
    # Get registration counts
    counts = {}
    for event in events:
        count = db.execute('SELECT COUNT(*) FROM registrations WHERE event_id = ?', (event['id'],)).fetchone()[0]
        counts[event['id']] = count
        
    return render_template('admin_dashboard.html', events=events, counts=counts)

@app.route('/admin/event/add', methods=['GET', 'POST'])
def add_event():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    if request.method == 'POST':
        name = request.form['name']
        date = request.form['date']
        time = request.form['time']
        location = request.form['location']
        added_by = session['admin_username']
        
        db = get_db()
        db.execute('INSERT INTO events (name, date, time, location, added_by) VALUES (?, ?, ?, ?, ?)',
                   (name, date, time, location, added_by))
        db.commit()
        flash('Event added successfully.', 'success')
        return redirect(url_for('admin_dashboard'))
        
    return render_template('add_event.html')

@app.route('/admin/event/delete/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    db = get_db()
    # Delete registrations for this event first
    db.execute('DELETE FROM registrations WHERE event_id = ?', (event_id,))
    # Delete the event
    db.execute('DELETE FROM events WHERE id = ?', (event_id,))
    db.commit()
    
    flash('Event deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/registrations', methods=['GET'])
def view_registrations():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))
        
    search_query = request.args.get('search', '')
    
    db = get_db()
    if search_query:
        query = '''
            SELECT r.*, e.name as event_name 
            FROM registrations r
            JOIN events e ON r.event_id = e.id
            WHERE r.name LIKE ? OR r.registration_id LIKE ? OR e.name LIKE ?
        '''
        search_term = f'%{search_query}%'
        registrations = db.execute(query, (search_term, search_term, search_term)).fetchall()
    else:
        registrations = db.execute('''
            SELECT r.*, e.name as event_name 
            FROM registrations r
            JOIN events e ON r.event_id = e.id
        ''').fetchall()
        
    return render_template('view_registrations.html', registrations=registrations, search_query=search_query)

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
