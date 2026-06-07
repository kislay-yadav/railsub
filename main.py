import os
import time
import sqlite3
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- CONFIGURATION ---
DB_FILE = "database.db"
API_SECRET = os.environ.get("API_SECRET", "admin_secure_123")

def get_db():
    """Establish a direct local connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create local tables if they don't exist yet."""
    with get_db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS channels (channel_id TEXT PRIMARY KEY)')
        conn.execute('CREATE TABLE IF NOT EXISTS verified_users (user_id TEXT PRIMARY KEY)')
        conn.commit()

# Initialize the database immediately
init_db()

def is_authenticated(req):
    """Verify admin secret key."""
    return req.args.get('secret') == API_SECRET

# --- RAILWAY AUTO-PING WORKER ---
def railway_ping_worker():
    """
    Dedicated Railway worker. It automatically fetches the RAILWAY_PUBLIC_DOMAIN
    so you don't have to set any manual URL variables in the dashboard.
    """
    time.sleep(20) # Wait for the Flask server to start
    
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    
    if not railway_domain:
        print("[Railway Auto-Ping] RAILWAY_PUBLIC_DOMAIN not detected. Running in local mode.")
        return

    # Railway provides the domain without https://, so we construct the full URL
    target_url = f"https://{railway_domain}"
    print(f"[Railway Auto-Ping] Active and targeting: {target_url}")
    
    while True:
        try:
            response = requests.get(target_url, timeout=10)
            print(f"[Railway Auto-Ping] Status Code: {response.status_code} - Server awake.")
        except Exception as e:
            print(f"[Railway Auto-Ping] Ping cycle failed: {e}")
        
        # Ping every 10 minutes to prevent sleep
        time.sleep(600)

# --- API ENDPOINTS ---

@app.route('/')
def home():
    """Root route serving as the auto-ping target."""
    return jsonify({
        "status": "online",
        "message": "Railway Alpha Store Backend is operational!"
    })

@app.route('/channels')
def get_channels():
    """Fetch all force-subscription channel IDs."""
    with get_db() as conn:
        cursor = conn.execute('SELECT channel_id FROM channels')
        channels = [row['channel_id'] for row in cursor.fetchall()]
    return jsonify({"status": "success", "channels": channels})

@app.route('/channels/add')
def add_channel():
    """Admin only: Save a channel ID."""
    if not is_authenticated(request): 
        return jsonify({"error": "Unauthorized"}), 401
    
    channel_id = request.args.get('channel_id')
    if not channel_id: 
        return jsonify({"error": "Missing channel_id"}), 400
    
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO channels (channel_id) VALUES (?)', (channel_id,))
            conn.commit()
        return jsonify({"status": "success", "message": f"Channel `{channel_id}` stored on Railway."})
    except sqlite3.IntegrityError:
        return jsonify({"status": "error", "message": "Channel already exists."})

@app.route('/channels/remove')
def remove_channel():
    """Admin only: Remove a channel ID."""
    if not is_authenticated(request): 
        return jsonify({"error": "Unauthorized"}), 401
    
    channel_id = request.args.get('channel_id')
    if not channel_id:
        return jsonify({"error": "Missing channel_id"}), 400
        
    with get_db() as conn:
        cursor = conn.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
        changes = cursor.rowcount
        conn.commit()
        
    if changes > 0:
        return jsonify({"status": "success", "message": f"Channel `{channel_id}` removed."})
    return jsonify({"status": "error", "message": "Channel not found."})

@app.route('/users/request')
def user_request():
    """Log a user ID instantly when a join request is registered."""
    if not is_authenticated(request): 
        return jsonify({"error": "Unauthorized"}), 401
    
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400
        
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO verified_users (user_id) VALUES (?)', (user_id,))
            conn.commit()
    except sqlite3.IntegrityError:
        pass 
        
    return jsonify({"status": "success", "message": "User request registered on Railway."})

@app.route('/users/check')
def user_check():
    """Verify if a user exists in our records."""
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"status": "error", "message": "Missing user_id"}), 400
        
    with get_db() as conn:
        cursor = conn.execute('SELECT user_id FROM verified_users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
    if result:
        e_code = f"E-{str(user_id)[-4:]}-ALPHA" if len(str(user_id)) >= 4 else "E-CODE-ALPHA"
        return jsonify({"status": "success", "verified": True, "e_code": e_code})
        
    return jsonify({"status": "success", "verified": False})

if __name__ == '__main__':
    # Start the Railway specific auto-ping thread
    ping_thread = threading.Thread(target=railway_ping_worker, daemon=True)
    ping_thread.start()
    
    # Railway passes the PORT via environment variables automatically
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
  
