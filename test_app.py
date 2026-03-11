import os
import sqlite3
from app import app, init_db

# Initialize database
init_db()

# Create test client
client = app.test_client()

print("--- Testing App ---")

# Test 1: Home and Events
print("1. Testing Home and Events Pages...")
response = client.get('/')
assert b'Event Registration System' in response.data
response = client.get('/events')
assert b'Upcoming Events' in response.data
print("   Pages load successfully.")

# Test 2: Admin Login
print("2. Testing Admin Login...")
response = client.post('/admin/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
assert b'Admin Dashboard' in response.data
print("   Admin login successful.")

# Test 3: Add Event
print("3. Testing Event Creation...")
response = client.post('/admin/event/add', data={
    'name': 'Test Integration Event',
    'date': '2026-05-15',
    'time': '14:00',
    'location': 'Testing Lab'
}, follow_redirects=True)
assert b'Test Integration Event' in response.data
print("   Event created successfully.")

# Find the Event ID
with app.app_context():
    db = sqlite3.connect('database.db')
    event_id = db.execute('SELECT id FROM events WHERE name = "Test Integration Event"').fetchone()[0]

# Test 4: Course Registration
print("4. Testing Event Registration...")
response = client.post(f'/register/{event_id}', data={
    'name': 'Test User',
    'email': 'testuser@example.com',
    'phone': '9876543210'
}, follow_redirects=True)
assert b'Successfully registered!' in response.data
print("   Registration successful.")

# Test 5: Verify Registration in Admin Dashboard
print("5. Verifying Registration...")
response = client.get('/admin/registrations')
assert b'testuser@example.com' in response.data
assert b'Test Integration Event' in response.data
print("   Registration verified in Admin Dashboard.")

print("\nAll backend integration tests passed successfully!")
