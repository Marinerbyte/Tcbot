# ======================================================
# FILE: app.py (TITAN ENGINE v12.0 - THE GOD ENGINE)
# ======================================================
import os
import json
import time
import threading
import websocket
import psycopg2
import importlib.util
import requests
import io
import sys
from flask import Flask, render_template_string, request, jsonify, send_file
from psycopg2 import pool
from datetime import datetime

# --- 1. SYSTEM ENVIRONMENT & PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Import Dashboard Design
try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>CRITICAL: ui.py is missing!</h1>"
    ui = UI()

app = Flask(__name__)

# ======================================================
# 2. DATABASE CONFIGURATION (NEON CLOUD POOL)
# ======================================================
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    # Creating a Connection Pool for stability
    db_pool = pool.SimpleConnectionPool(1, 20, NEON_URL, sslmode='require')
    
    # Initialize Core Tables
    _init_conn = db_pool.getconn()
    with _init_conn.cursor() as _c:
        # Table for User Scores
        _c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        # Table for Persistent Memory (Saves everything on restart)
        _c.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    _init_conn.commit()
    db_pool.putconn(_init_conn)
    print(">> [DATABASE] Neon Pool & Tables Synchronized.")
except Exception as e:
    print(f">> [CRITICAL DB ERROR] {e}")

# ======================================================
# 3. GLOBAL MEMORY & STATE MANAGEMENT
# ======================================================
BOT_STATE = {
    "ws": None, 
    "connected": False, 
    "user": "", 
    "pass": "", 
    "room": "", 
    "reconnect": True
}

ACTIVE_GAMES = {}   # Sessions Memory
GLOBAL_DATA = {}    # Shared Persistent Memory (Bans, Config, etc.)
GAME_MODULES = {}   # Loaded Plugins Dictionary
USER_COOLDOWN = {}  # Anti-Spam (Rate Limiting)
LOGS = []           # System Logs for Dashboard
LOCK = threading.Lock() # THE MASTER PROTECTION LOCK

def add_log(msg, log_type="sys"):
    """Adds a log entry to the dashboard with RAM capping."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# ======================================================
# 4. UNIVERSAL DATABASE TOOLS (For Plugins)
# ======================================================
def db_set_score(target_user, points):
    """Adds or removes points from a user (Atomic SQL)."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (target_user, points, points))
        conn.commit()
    finally:
        db_pool.putconn(conn)

def db_get_score(target_user):
    """Fetches points of a specific user."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT score FROM users WHERE username = %s", (target_user,))
            res = c.fetchone()
            return res[0] if res else 0
    finally:
        db_pool.putconn(conn)

def db_get_top_10():
    """Fetches the top 10 players by score."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
            return c.fetchall()
    finally:
        db_pool.putconn(conn)

# ======================================================
# 5. RECOVERY & PERSISTENCE (Anti-Restart System)
# ======================================================
def save_persistence_task():
    """Background task to save memory to Neon DB every 2 minutes."""
    while True:
        time.sleep(120)
        with LOCK:
            try:
                # Combining sessions and global memory
                master_dump = {"sessions": ACTIVE_GAMES, "global": GLOBAL_DATA}
                dump_json = json.dumps(master_dump)
                
                conn = db_pool.getconn()
                with conn.cursor() as c:
                    c.execute("INSERT INTO bot_state (key, data) VALUES ('master_state', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (dump_json, dump_json))
                conn.commit()
                db_pool.putconn(conn)
            except Exception as e:
                print(f"Persistence Save Error: {e}")

def load_persistence_task():
    """Restores sessions and global memory after bot restart."""
    global ACTIVE_GAMES, GLOBAL_DATA
    try:
        conn = db_pool.getconn()
        with conn.cursor() as c:
            c.execute("SELECT data FROM bot_state WHERE key = 'master_state'")
            res = c.fetchone()
            if res:
                data = json.loads(res[0])
                ACTIVE_GAMES = data.get("sessions", {})
                GLOBAL_DATA = data.get("global", {})
                add_log(f"RECOVERY: Restored {len(ACTIVE_GAMES)} game sessions.", "sys")
        db_pool.putconn(conn)
    except Exception as e:
        print(f"Recovery Load Error: {e}")

# ======================================================
# 6. DYNAMIC PLUG-IN LOADER (Plug-and-Play)
# ======================================================
def load_all_plugins():
    """Automatically scans and loads games/plugins from folders."""
    global GAME_MODULES
    GAME_MODULES = {}
    
    for folder in ['games', 'plugins']:
        path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path)
            with open(os.path.join(path, "__init__.py"), "w") as f: f.write("# Init")
        
        add_log(f"Scanning folder: {folder}...", "sys")
        
        for filename in os.listdir(path):
            if filename.endswith(".py") and filename != "__init__.py":
                file_path = os.path.join(path, filename)
                try:
                    spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ READY: {mod.TRIGGER}", "sys")
                except Exception as e:
                    add_log(f"❌ CRASH in {filename}: {e}", "err")

# ======================================================
# 7. COMMUNICATION ENGINE
# ======================================================
def send_text_msg(room, text):
    """Sends a standard text message to the chatroom."""
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            packet = {
                "handler": "room_message", 
                "id": str(time.time()), 
                "room": room, 
                "type": "text", 
                "body": str(text),
                "url": "",
                "length": "0"
            }
            BOT_STATE["ws"].send(json.dumps(packet))
        except: pass

def send_raw_packet(payload):
    """Sends a raw JSON payload (For Kick, Join, Leave, etc.)."""
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            if "id" not in payload: payload["id"] = str(time.time())
            BOT_STATE["ws"].send(json.dumps(payload))
        except: pass

# ======================================================
# 8. THE MASTER ROUTER (on_message)
# ======================================================
def on_message(ws, message):
    try:
        data = json.loads(message)
        
        # 1. Skip server acknowledgement packets
        if data.get("handler") == "receipt_ack": return

        # 2. ANTI-KICK / AUTO-REJOIN
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            add_log("Kicked/Idle! Attempting auto-rejoin...", "err")
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        # 3. TEXT MESSAGE HANDLER
        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam Filter (0.8s)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            
            # Multi-Room User Context
            ctx_key = f"{room}_{user}"

            # --- THE MASTER LOCK (Race Condition Protection) ---
            with LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time() # Activity Timer
                
                parts = msg.split()
                cmd = parts[0].lower() if parts else ""

                # PLUG-AND-PLAY LOGIC: Direct Power Injection
                # We pass 10 EXPLICIT ARGUMENTS to the plugin handle
                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(
                        user, msg, state,
                        lambda t: send_text_msg(room, t), # Argument 4
                        send_raw_packet,                  # Argument 5
                        db_set_score,                     # Argument 6
                        db_get_score,                     # Argument 7
                        db_get_top_10,                    # Argument 8
                        GLOBAL_DATA,                      # Argument 9
                        lambda m: add_log(f"Plugin: {m}") # Argument 10
                    )
                
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_s = handler.handle(
                                user, msg, state,
                                lambda t: send_text_msg(room, t),
                                send_raw_packet,
                                db_set_score,
                                db_get_score,
                                db_get_top_10,
                                GLOBAL_DATA,
                                lambda m: add_log(f"Plugin: {m}")
                            )
                            # Cleanup Check
                            if not new_s.get("active"):
                                if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
                            else:
                                ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Plugin Crash ({user}): {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except Exception as e:
        print(f"Engine Runtime Error: {e}")

# ======================================================
# 9. MAINTENANCE THREADS
# ======================================================
def memory_cleanup_task():
    """Deletes idle user sessions (10 mins) from RAM."""
    while True:
        time.sleep(60)
        now = time.time()
        with LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del:
                del ACTIVE_GAMES[u]

threading.Thread(target=memory_cleanup_task, daemon=True).start()
threading.Thread(target=save_persistence_task, daemon=True).start()

# ======================================================
# 10. WEB CONTROL PANEL & WS LOOP
# ======================================================
def on_open(ws):
    add_log("TITAN CORE: Connection established.", "sys")
    ws.send(json.dumps({
        "handler": "login", 
        "id": str(time.time()), 
        "username": BOT_STATE["user"], 
        "password": BOT_STATE["pass"]
    }))
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws_manager():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp(
                "wss://chatp.net:5333/server",
                on_open=on_open,
                on_message=on_message,
                on_close=lambda w,c,m: BOT_STATE.update({"connected": False}),
                on_error=lambda w,e: add_log(f"WS Error: {e}", "err")
            )
            BOT_STATE["ws"] = ws
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except:
            time.sleep(5)

@app.route('/')
def index():
    return render_template_string(ui.HTML_DASHBOARD)

@app.route('/status')
def get_status():
    return jsonify({
        "connected": BOT_STATE.get("ws") is not None and BOT_STATE["connected"],
        "sessions": len(ACTIVE_GAMES),
        "plugins": len(GAME_MODULES),
        "logs": LOGS
    })

@app.route('/connect', methods=['POST'])
def bot_connect():
    d = request.json
    BOT_STATE.update({"user": d['u'], "pass": d['p'], "room": d['r'], "reconnect": True})
    threading.Thread(target=connect_ws_manager, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route('/disconnect', methods=['POST'])
def bot_disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]:
        BOT_STATE["ws"].close()
    return jsonify({"status": "ok"})

@app.route('/health')
def health_ping():
    return "ENGINE_STABLE", 200

# ======================================================
# 11. BOOT-UP SEQUENCE
# ======================================================
print(">> TITAN OS ENGINE v12.0 INITIALIZING...")
load_all_plugins()
load_persistence_from_db()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)