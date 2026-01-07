# ======================================================
# FILE: app.py (TITAN ENGINE v17.0 - THE ULTIMATE CORE)
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

# Dashboard UI Connection
try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>FATAL ERROR: ui.py missing!</h1>"
    ui = UI()

app = Flask(__name__)

# ======================================================
# 2. NEON DATABASE - THREADED POOL & DOUBLE LOCKING
# ======================================================
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# DO ALAG LOCKS: Ek Logic (RAM) ke liye, ek Database (SSL) ke liye
LOGIC_LOCK = threading.Lock()
DB_LOCK = threading.Lock()

try:
    # 20 concurrent connections ka threaded pool
    db_pool = pool.ThreadedConnectionPool(1, 20, NEON_URL, sslmode='require')
    
    # Initialize Core Tables (Global + Game Stats)
    _startup_conn = db_pool.getconn()
    with _startup_conn.cursor() as _cur:
        # Table 1: Global Score
        _cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        # Table 2: Persistent State Backup
        _cur.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
        # Table 3: Game-wise Statistics
        _cur.execute("CREATE TABLE IF NOT EXISTS game_stats (username TEXT, game_name TEXT, score INTEGER DEFAULT 0, PRIMARY KEY(username, game_name))")
    _startup_conn.commit()
    db_pool.putconn(_startup_conn)
    print(">> [DATABASE] Multi-threaded Pool and Tables are synchronized.")
except Exception as e:
    print(f">> [DB_CRITICAL_ERROR] {e}")

# ======================================================
# 3. GLOBAL MEMORY & STATE STRUCTURES
# ======================================================
BOT_STATE = {
    "ws": None, 
    "connected": False, 
    "user": "", 
    "pass": "", 
    "room": "", 
    "reconnect": True
}

ACTIVE_GAMES = {}   # Individual Session Memory
GLOBAL_DATA = {}    # Shared Persistent Memory (Bans, Settings, etc.)
GAME_MODULES = {}   # Loaded Plugins List
USER_COOLDOWN = {}  # Anti-Spam (0.8s)
LOGS = []           # Live Terminal logs

def add_log(msg, log_type="sys"):
    """Capped logging to prevent RAM spikes on Render."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# ======================================================
# 4. ADVANCED DATABASE TOOLS (Universal Access)
# ======================================================

def db_set_score(user, pts):
    """Updates the Global Score of a user."""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (user, pts, pts))
            conn.commit()
        finally: db_pool.putconn(conn)

def db_get_score(user):
    """Gets the Global Score of a user."""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT score FROM users WHERE username = %s", (user,))
                res = c.fetchone()
                return res[0] if res else 0
        finally: db_pool.putconn(conn)

def db_update_stat(user, game, pts):
    """Updates score for a SPECIFIC game."""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("INSERT INTO game_stats (username, game_name, score) VALUES (%s, %s, %s) ON CONFLICT (username, game_name) DO UPDATE SET score = game_stats.score + %s", (user, game, pts, pts))
            conn.commit()
        finally: db_pool.putconn(conn)

def db_get_user_stats(user):
    """Gets all game scores for a specific user."""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT game_name, score FROM game_stats WHERE username = %s", (user,))
                return c.fetchall()
        finally: db_pool.putconn(conn)

def db_get_game_top(game):
    """Leaderboard for a specific game."""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT username, score FROM game_stats WHERE game_name = %s ORDER BY score DESC LIMIT 10", (game,))
                return c.fetchall()
        finally: db_pool.putconn(conn)

def db_get_global_top():
    """Overall Top 10 players list."""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
                return c.fetchall()
        finally: db_pool.putconn(conn)

# ======================================================
# 5. PERSISTENCE & RECOVERY (Render-Restart Safe)
# ======================================================

def save_persistence_task():
    """Backup RAM to Cloud every 2 minutes."""
    while True:
        time.sleep(120)
        with LOGIC_LOCK:
            with DB_LOCK:
                try:
                    master_state = {"sessions": ACTIVE_GAMES, "global": GLOBAL_DATA}
                    serialized = json.dumps(master_state)
                    conn = db_pool.getconn()
                    with conn.cursor() as c:
                        c.execute("INSERT INTO bot_state (key, data) VALUES ('titan_state_v17', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (serialized, serialized))
                    conn.commit()
                    db_pool.putconn(conn)
                except Exception as e: print(f"Backup Error: {e}")

def load_persistence_task():
    """Restore memory from Cloud on bot startup."""
    global ACTIVE_GAMES, GLOBAL_DATA
    with DB_LOCK:
        try:
            conn = db_pool.getconn()
            with conn.cursor() as c:
                c.execute("SELECT data FROM bot_state WHERE key = 'titan_state_v17'")
                res = c.fetchone()
                if res:
                    recovered = json.loads(res[0])
                    ACTIVE_GAMES = recovered.get("sessions", {})
                    GLOBAL_DATA = recovered.get("global", {})
                    add_log(f"RECOVERY: {len(ACTIVE_GAMES)} game sessions restored.", "sys")
            db_pool.putconn(conn)
        except Exception as e: print(f"Recovery Error: {e}")

# ======================================================
# 6. DYNAMIC PLUG-IN ENGINE (Manual Path Scan)
# ======================================================

def load_all_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    for folder in ['games', 'plugins']:
        path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path)
            with open(os.path.join(path, "__init__.py"), "w") as f: f.write("# Init")
        
        add_log(f"Syncing folder: {folder}", "sys")
        for filename in os.listdir(path):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(module_name, os.path.join(path, filename))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ READY: {mod.TRIGGER}", "sys")
                except Exception as e: add_log(f"❌ CRASH in {filename}: {e}", "err")

# ======================================================
# 7. COMMUNICATION TOOLS
# ======================================================

def send_txt(room, text):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            p = {"handler":"room_message","id":str(time.time()),"room":room,"type":"text","body":str(text),"url":"","length":"0"}
            BOT_STATE["ws"].send(json.dumps(p))
        except: pass

def send_img(room, text, url):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            p = {"handler":"room_message","id":str(time.time()),"room":room,"type":"image","body":str(text),"url":str(url),"length":"0"}
            BOT_STATE["ws"].send(json.dumps(p))
        except: pass

def send_raw(payload):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            if "id" not in payload: payload["id"] = str(time.time())
            BOT_STATE["ws"].send(json.dumps(payload))
        except: pass

# ======================================================
# 8. THE MASTER ROUTER (on_message - 14 ARGS CALL)
# ======================================================

def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("handler") == "receipt_ack": return

        # 1. AUTO-REJOIN (Anti-Kick/Idle)
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        # 2. MESSAGE PROCESSOR
        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam (0.8s)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}"

            # --- THE MASTER LOCK BLOCK ---
            with LOGIC_LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time()
                
                parts = msg.split()
                cmd = parts[0].lower() if parts else ""

                # Tools Bundle (The 14 Professional Weapons)
                args = (
                    user, msg, state,
                    lambda t: send_txt(room, t), # 4. send_text
                    send_raw,                    # 5. send_raw
                    db_set_score,                # 6. db_set_score
                    db_get_score,                # 7. db_get_score
                    db_get_global_top,           # 8. db_get_top
                    GLOBAL_DATA,                 # 9. global_data
                    lambda m: add_log(f"Plugin: {m}"), # 10. add_log
                    lambda t, u: send_img(room, t, u), # 11. send_image
                    db_update_stat,              # 12. db_update_stat
                    db_get_user_stats,           # 13. db_get_user_stats
                    db_get_game_top              # 14. db_get_game_top
                )

                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(*args)
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_s = handler.handle(*args)
                            if not new_s.get("active"): del ACTIVE_GAMES[ctx_key]
                            else: ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Plugin Crash: {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except Exception as e: print(f"Router Error: {e}")

# ======================================================
# 9. 90-SECOND VACUUM CLEANER
# ======================================================
def memory_cleanup_task():
    while True:
        time.sleep(10) # Scanning every 10 sec
        now = time.time()
        with LOGIC_LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 90]
            for u in to_del:
                del ACTIVE_GAMES[u]
                add_log(f"Vacuum: Session {u} cleared.", "sys")

threading.Thread(target=memory_cleanup_task, daemon=True).start()
threading.Thread(target=save_persistence_task, daemon=True).start()

# ======================================================
# 10. WEBSOCKET & SERVER ROUTES
# ======================================================
def on_open(ws):
    add_log("TITAN OS: Successfully connected to Server.", "sys")
    ws.send(json.dumps({"handler":"login","id":str(time.time()),"username":BOT_STATE["user"],"password":BOT_STATE["pass"]}))
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws_loop():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server", on_open=on_open, on_message=on_message, on_close=lambda w,c,m: BOT_STATE.update({"connected": False}), on_error=lambda w,e: add_log(f"Error: {e}", "err"))
            BOT_STATE["ws"] = ws; ws.run_forever(ping_interval=25, ping_timeout=10)
        except: time.sleep(5)

@app.route('/')
def index(): return render_template_string(ui.HTML_DASHBOARD)
@app.route('/status')
def status(): return jsonify({"connected": BOT_STATE["connected"], "sessions": len(ACTIVE_GAMES), "plugins": len(GAME_MODULES), "logs": LOGS})
@app.route('/connect', methods=['POST'])
def bot_connect():
    d = request.json; BOT_STATE.update({"user": d['u'], "pass": d['p'], "room": d['r'], "reconnect": True})
    threading.Thread(target=connect_ws_loop, daemon=True).start(); return jsonify({"status": "ok"})
@app.route('/disconnect', methods=['POST']):
def bot_disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]: BOT_STATE["ws"].close(); return jsonify({"status": "ok"})
@app.route('/health')
def health(): return "ACTIVE", 200

# --- 🚀 BOOT SEQUENCE ---
print(">> TITAN MASTER CORE v17.0 FINAL BOOTING...")
load_all_plugins()
load_persistence_task()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
