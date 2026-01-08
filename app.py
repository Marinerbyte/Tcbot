# ======================================================
# FILE: app.py (TITAN ENGINE v18.0 - THE ULTIMATE CORE)
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
from psycopg2 import pool, OperationalError, InterfaceError
from datetime import datetime

# --- 1. SYSTEM ENVIRONMENT & PATHS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Import Dashboard Design from ui.py
try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>FATAL ERROR: ui.py file missing!</h1>"
    ui = UI()

app = Flask(__name__)

# ======================================================
# 2. NEON DATABASE CONFIGURATION (THREADED POOL)
# ======================================================
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# Master Locks
LOGIC_LOCK = threading.Lock()
DB_LOCK = threading.Lock()

def create_db_pool():
    """Neon Pool Setup with Threading Support"""
    try:
        return pool.ThreadedConnectionPool(1, 20, NEON_URL, sslmode='require')
    except Exception as e:
        print(f"Pool Creation Failed: {e}")
        return None

db_pool = create_db_pool()

# Initialize Tables
try:
    _conn = db_pool.getconn()
    with _conn.cursor() as _cur:
        # Table for Users
        _cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        # Table for Persistence (Backup)
        _cur.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
        # Table for Game-wise Statistics
        _cur.execute("CREATE TABLE IF NOT EXISTS game_stats (username TEXT, game_name TEXT, score INTEGER DEFAULT 0, PRIMARY KEY(username, game_name))")
    _conn.commit()
    db_pool.putconn(_conn)
    print(">> [DATABASE] Multi-threaded Pool and Tables Verified.")
except Exception as e:
    print(f">> [DB_ERROR] {e}")

# ======================================================
# 3. GLOBAL MEMORY STRUCTURES
# ======================================================
BOT_STATE = {
    "ws": None, 
    "connected": False, 
    "user": "", 
    "pass": "", 
    "room": "", 
    "reconnect": True
}

ACTIVE_GAMES = {}   # RAM Memory (Dabbe)
GLOBAL_DATA = {}    # Shared Memory (Settings/Bans)
GAME_MODULES = {}   # Loaded Plugins
USER_COOLDOWN = {}  # Anti-Spam
LOGS = []           # Live Terminal

def add_log(msg, log_type="sys"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# ======================================================
# 4. AUTO-HEALING DATABASE TOOLS (Fixes SSL Error)
# ======================================================

def execute_db_safe(query, params=(), fetch=False):
    """SSL error aane par connection reset karke dobara try karta hai"""
    global db_pool
    with DB_LOCK:
        for attempt in range(2): # 2 baar koshish
            conn = None
            try:
                conn = db_pool.getconn()
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    if fetch:
                        res = cur.fetchall()
                        db_pool.putconn(conn)
                        return res
                conn.commit()
                db_pool.putconn(conn)
                return True
            except (OperationalError, InterfaceError, Exception) as e:
                # Agar SSL error hai toh connection band karke naya lo
                if conn:
                    try: db_pool.putconn(conn, close=True)
                    except: pass
                if attempt == 0:
                    add_log("DB SSL/Connection Reset. Retrying...", "err")
                    time.sleep(1)
                    continue
                else:
                    add_log(f"DB Critical Fail: {e}", "err")
                    return [] if fetch else False

# --- Universal Tools for Plugins ---

def db_set_score(user, pts):
    query = "INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s"
    execute_db_safe(query, (user, pts, pts))

def db_get_score(user):
    query = "SELECT score FROM users WHERE username = %s"
    res = execute_db_safe(query, (user,), fetch=True)
    return res[0][0] if res else 0

def db_update_stat(user, game, pts):
    query = "INSERT INTO game_stats (username, game_name, score) VALUES (%s, %s, %s) ON CONFLICT (username, game_name) DO UPDATE SET score = game_stats.score + %s"
    execute_db_safe(query, (user, game, pts, pts))

def db_get_user_stats(user):
    query = "SELECT game_name, score FROM game_stats WHERE username = %s"
    return execute_db_safe(query, (user,), fetch=True)

def db_get_game_top(game):
    query = "SELECT username, score FROM game_stats WHERE game_name = %s ORDER BY score DESC LIMIT 10"
    return execute_db_safe(query, (game,), fetch=True)

def db_get_global_top():
    query = "SELECT username, score FROM users ORDER BY score DESC LIMIT 10"
    return execute_db_safe(query, (), fetch=True)

# ======================================================
# 5. PERSISTENCE & RECOVERY (Restart Safe)
# ======================================================

def save_persistence_task():
    while True:
        time.sleep(120) # 2 min backup
        with LOGIC_LOCK:
            try:
                bundle = json.dumps({"sessions": ACTIVE_GAMES, "global": GLOBAL_DATA})
                execute_db_safe("INSERT INTO bot_state (key, data) VALUES ('v18_master', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (bundle, bundle))
            except Exception as e:
                print(f"Backup Error: {e}")

def load_persistence_task():
    global ACTIVE_GAMES, GLOBAL_DATA
    res = execute_db_safe("SELECT data FROM bot_state WHERE key = 'v18_master'", (), fetch=True)
    if res:
        try:
            data = json.loads(res[0][0])
            ACTIVE_GAMES = data.get("sessions", {})
            GLOBAL_DATA = data.get("global", {})
            add_log(f"RECOVERY: Loaded {len(ACTIVE_GAMES)} sessions.", "sys")
        except: pass

# ======================================================
# 6. DYNAMIC PLUG-IN LOADER
# ======================================================

def load_all_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    for folder in ['games', 'plugins']:
        path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path)
            with open(os.path.join(path, "__init__.py"), "w") as f: f.write("#")
        
        add_log(f"Syncing {folder}...", "sys")
        for filename in os.listdir(path):
            if filename.endswith(".py") and filename != "__init__.py":
                file_path = os.path.join(path, filename)
                spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                mod = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ READY: {mod.TRIGGER}")
                except Exception as e:
                    add_log(f"❌ CRASH in {filename}: {e}", "err")

# ======================================================
# 7. COMMUNICATION TOOLS
# ======================================================

def send_chat_text(room, text):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            p = {"handler":"room_message","id":str(time.time()),"room":room,"type":"text","body":str(text),"url":"","length":"0"}
            BOT_STATE["ws"].send(json.dumps(p))
        except: pass

def send_chat_image(room, text, url):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            p = {"handler":"room_message","id":str(time.time()),"room":room,"type":"image","body":str(text),"url":str(url),"length":"0"}
            BOT_STATE["ws"].send(json.dumps(p))
        except: pass

def send_raw_payload(payload):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            if "id" not in payload: payload["id"] = str(time.time())
            BOT_STATE["ws"].send(json.dumps(payload))
        except: pass

# ======================================================
# 8. THE MASTER ROUTER (on_message - 14 ARGS)
# ======================================================

def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("handler") == "receipt_ack": return

        # Auto Rejoin
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}"

            with LOGIC_LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time()
                
                parts = msg.split()
                cmd = parts[0].lower() if parts else ""

                # Tools for Plugins (14 Arguments)
                args = (
                    user, msg, state,
                    lambda t: send_chat_text(room, t), # 4
                    send_raw_payload,                  # 5
                    db_set_score,                     # 6
                    db_get_score,                     # 7
                    db_get_global_top,                # 8
                    GLOBAL_DATA,                      # 9
                    lambda m: add_log(f"Plugin: {m}"), # 10
                    lambda t, u: send_chat_image(room, t, u), # 11
                    db_update_stat,                   # 12
                    db_get_user_stats,                # 13
                    db_get_game_top                   # 14
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
    add_log("TITAN CORE: Online.", "sys")
    ws.send(json.dumps({"handler":"login","id":str(time.time()),"username":BOT_STATE["user"],"password":BOT_STATE["pass"]}))
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws_loop():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server", on_open=on_open, on_message=on_message, on_close=lambda w,c,m: BOT_STATE.update({"connected": False}))
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
@app.route('/disconnect', methods=['POST'])
def bot_disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    return jsonify({"status": "ok"})
@app.route('/health')
def health(): return "ACTIVE", 200

# ======================================================
# 11. BOOT-UP SEQUENCE
# ======================================================
print(">> TITAN MASTER CORE v18.0 FINAL BOOTING...")
load_all_plugins()
load_persistence_task()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
