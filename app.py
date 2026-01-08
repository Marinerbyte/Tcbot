# ======================================================
# FILE: app.py (TITAN ENGINE v19.0 - ULTIMATE PLUGIN CORE)
# ======================================================
# ALL FEATURES LOCKED: No more app.py changes needed!
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
from dotenv import load_dotenv  # pip install python-dotenv

# --- 0. LOAD ENV CONFIG (NO CODE CHANGE NEEDED) ---
load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>FATAL ERROR: ui.py file missing!</h1>"
    ui = UI()

app = Flask(__name__)

# ======================================================
# 1. CONFIG FROM ENV (FUTURE-PROOF) 
# ======================================================
NEON_URL = os.getenv("NEON_URL", "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require")
POOL_MIN = int(os.getenv("POOL_MIN", "1"))
POOL_MAX = int(os.getenv("POOL_MAX", "20"))
INACTIVITY_TIMEOUT = int(os.getenv("INACTIVITY_TIMEOUT", "90"))
BACKUP_INTERVAL = int(os.getenv("BACKUP_INTERVAL", "120"))

# ======================================================
# 2. NEON DATABASE POOL + TABLES (ENHANCED)
# ======================================================
LOGIC_LOCK = threading.Lock()
DB_LOCK = threading.Lock()
GLOBAL_DATA = {
    "per_room": {},
    "per_plugin": {},
    "flags": {"db_error": False}
}

def create_db_pool():
    try:
        return pool.ThreadedConnectionPool(POOL_MIN, POOL_MAX, NEON_URL, sslmode='require')
    except Exception as e:
        print(f"Pool Creation Failed: {e}")
        return None

db_pool = create_db_pool()

# Initialize Tables (ENHANCED with indexes)
try:
    conn = db_pool.getconn()
    with conn.cursor() as cur:
        # Tables
        cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        cur.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS game_stats (username TEXT, game_name TEXT, score INTEGER DEFAULT 0, PRIMARY KEY(username, game_name))")
        # Indexes for speed
        cur.execute("CREATE INDEX IF NOT EXISTS idx_game_stats_user ON game_stats(username)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_game_stats_game ON game_stats(game_name)")
    conn.commit()
    db_pool.putconn(conn)
    print(">> [DATABASE] Tables + Indexes Ready.")
except Exception as e:
    print(f">> [DB_ERROR] {e}")

# ======================================================
# 3. ENHANCED DB SAFE EXECUTOR + GLOBAL FLAGS
# ======================================================
def execute_db_safe(query, params=(), fetch=False):
    """Auto-healing DB with global error flag"""
    global db_pool, GLOBAL_DATA
    if not db_pool:
        GLOBAL_DATA["flags"]["db_error"] = True
        return [] if fetch else False
    
    with DB_LOCK:
        for attempt in range(2):
            conn = None
            try:
                conn = db_pool.getconn()
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    if fetch:
                        res = cur.fetchall()
                        db_pool.putconn(conn)
                        GLOBAL_DATA["flags"]["db_error"] = False
                        return res
                conn.commit()
                db_pool.putconn(conn)
                GLOBAL_DATA["flags"]["db_error"] = False
                return True
            except (OperationalError, InterfaceError, Exception) as e:
                if conn:
                    try: db_pool.putconn(conn, close=True)
                    except: pass
                if attempt == 0:
                    time.sleep(1)
                    continue
                else:
                    GLOBAL_DATA["flags"]["db_error"] = True
                    add_log(f"DB CRITICAL FAIL: {e}", "err")
                    return [] if fetch else False

# DB Helpers (SAFE WITH ERROR FLAGS)
def db_safe_call(func, *args, **kwargs):
    """Wrapper for DB functions when error flag is on"""
    if GLOBAL_DATA["flags"]["db_error"]:
        return None
    return func(*args, **kwargs)

def db_set_score(user, pts):
    query = "INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s"
    return execute_db_safe(query, (user, pts, pts))

def db_get_score(user):
    query = "SELECT score FROM users WHERE username = %s"
    res = execute_db_safe(query, (user,), fetch=True)
    return res[0][0] if res else 0

def db_update_stat(user, game, pts):
    query = "INSERT INTO game_stats (username, game_name, score) VALUES (%s, %s, %s) ON CONFLICT (username, game_name) DO UPDATE SET score = game_stats.score + %s"
    return execute_db_safe(query, (user, game, pts, pts))

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
# 4. GLOBAL MEMORY + LOGS
# ======================================================
BOT_STATE = {"ws": None, "connected": False, "user": "", "pass": "", "room": "", "reconnect": True}
ACTIVE_GAMES = {}
GAME_MODULES = {}
USER_COOLDOWN = {}
LOGS = []

def add_log(msg, log_type="sys"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 100: LOGS.pop(0)

# ======================================================
# 5. PERSISTENCE (ENHANCED)
# ======================================================
def save_persistence_task():
    while True:
        time.sleep(BACKUP_INTERVAL)
        with LOGIC_LOCK:
            try:
                bundle = json.dumps({"sessions": ACTIVE_GAMES, "global": GLOBAL_DATA})
                execute_db_safe("INSERT INTO bot_state (key, data) VALUES ('v19_master', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (bundle, bundle))
            except Exception as e:
                add_log(f"Backup Error: {e}", "err")

def load_persistence_task():
    global ACTIVE_GAMES, GLOBAL_DATA
    res = execute_db_safe("SELECT data FROM bot_state WHERE key = 'v19_master'", (), fetch=True)
    if res:
        try:
            data = json.loads(res[0][0])
            ACTIVE_GAMES = data.get("sessions", {})
            GLOBAL_DATA.update(data.get("global", {}))
            add_log(f"RECOVERY: Loaded {len(ACTIVE_GAMES)} sessions.", "sys")
        except: pass

# ======================================================
# 6. PLUGIN LOADER (STABLE API)
# ======================================================
def load_all_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    for folder in ['games', 'plugins']:
        path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path)
            with open(os.path.join(path, "__init__.py"), "w") as f: f.write("#")
        
        add_log(f"Loading {folder}...", "sys")
        for filename in os.listdir(path):
            if filename.endswith(".py") and filename != "__init__.py":
                file_path = os.path.join(path, filename)
                spec = importlib.util.spec_from_file_location(filename[:-3], file_path)
                mod = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ LOADED: {mod.TRIGGER} ({filename})", "sys")
                except Exception as e:
                    add_log(f"❌ PLUGIN CRASH {filename}: {e}", "err")

# ======================================================
# 7. COMMUNICATION + HELPERS (ENHANCED)
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
# 8. MASTER ROUTER + PLUGIN API (LOCKED FOREVER)
# ======================================================
# FIXED PLUGIN API (14 args + extras for future):
# handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, db_get_global_top, global_data, plugin_log, send_image, db_update_stat, db_get_user_stats, db_get_game_top)
def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("handler") == "receipt_ack": return

        # Auto Rejoin on kick/idle
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam (0.8s cooldown)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}"

            with LOGIC_LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {
                    "active": False, 
                    "game_type": None, 
                    "title": "Unknown", 
                    "last_act": now
                })
                state["last_act"] = now
                
                parts = msg.split()
                cmd = parts[0].lower() if parts else ""

                # FIXED PLUGIN API ARGS (14 + extras)
                args = (
                    user, msg, state,                          # 1-3
                    lambda t: send_chat_text(room, t),         # 4 send_text
                    send_raw_payload,                          # 5 send_raw
                    lambda u,p: db_safe_call(db_set_score, u, p),  # 6 db_set_score (safe)
                    lambda u: db_safe_call(db_get_score, u),   # 7 db_get_score (safe)
                    db_get_global_top,                         # 8
                    GLOBAL_DATA,                               # 9 global_data (structured!)
                    lambda m: add_log(f"Plugin: {m}", "plugin"), # 10 plugin_log
                    lambda t,u: send_chat_image(room, t, u),   # 11 send_image
                    lambda u,g,p: db_safe_call(db_update_stat, u, g, p), # 12 (safe)
                    lambda u: db_safe_call(db_get_user_stats, u), # 13 (safe)
                    lambda g: db_safe_call(db_get_game_top, g) # 14 (safe)
                )

                # Plugin dispatch logic
                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    handler = GAME_MODULES[cmd]
                    try:
                        new_state = handler.handle(*args)
                        if new_state and new_state.get("active"):
                            ACTIVE_GAMES[ctx_key] = new_state
                        else:
                            del ACTIVE_GAMES[ctx_key]
                    except Exception as e:
                        add_log(f"PLUGIN START CRASH {cmd}: {e}", "err")
                        send_chat_text(room, f"{state['title']} failed to start. Try again!")
                        del ACTIVE_GAMES[ctx_key]

                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_state = handler.handle(*args)
                            if new_state and new_state.get("active"):
                                ACTIVE_GAMES[ctx_key] = new_state
                            else:
                                del ACTIVE_GAMES[ctx_key]
                        except Exception as e:
                            add_log(f"PLUGIN CRASH {state['game_type']} {ctx_key}: {e}", "err")
                            send_chat_text(room, f"{state['title']} crashed! Please start a new game.")
                            del ACTIVE_GAMES[ctx_key]

    except Exception as e:
        add_log(f"ROUTER ERROR: {e}", "err")

# ======================================================
# 9. ENHANCED 90-SECOND VACUUM (AUTO NOTIFY)
# ======================================================
def memory_cleanup_task():
    while True:
        time.sleep(10)
        now = time.time()
        with LOGIC_LOCK:
            to_del = []
            for ctx_key, state in ACTIVE_GAMES.items():
                if now - state.get('last_act', 0) > INACTIVITY_TIMEOUT:
                    to_del.append(ctx_key)
            
            for ctx_key in to_del:
                state = ACTIVE_GAMES[ctx_key]
                room, user = ctx_key.rsplit("_", 1)  # Split room_user
                game_name = state.get("title") or state.get("game_type") or "Unknown game"
                
                # AUTO NOTIFICATION (GENERIC FOR ALL GAMES)
                send_chat_text(room, f"🧹 {game_name} session for {user} auto-closed after {INACTIVITY_TIMEOUT}s inactivity.")
                add_log(f"VACUUM: {game_name} for {ctx_key} ({user}@{room})", "sys")
                
                del ACTIVE_GAMES[ctx_key]

# ======================================================
# 10. WEBSOCKET + FLASK ROUTES (ENHANCED STATUS)
# ======================================================
def on_open(ws):
    add_log("TITAN v19.0: Online!", "sys")
    ws.send(json.dumps({"handler":"login","id":str(time.time()),"username":BOT_STATE["user"],"password":BOT_STATE["pass"]}))
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws_loop():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server", 
                                      on_open=on_open, 
                                      on_message=on_message, 
                                      on_close=lambda w,c,m: BOT_STATE.update({"connected": False}))
            BOT_STATE["ws"] = ws
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except Exception as e:
            add_log(f"WS RECONNECT FAIL: {e}", "err")
            time.sleep(5)

@app.route('/')
def index(): return render_template_string(ui.HTML_DASHBOARD)

@app.route('/status')
def status():
    return jsonify({
        "connected": BOT_STATE["connected"],
        "db_ok": not GLOBAL_DATA["flags"]["db_error"],
        "sessions": len(ACTIVE_GAMES),
        "plugins": len(GAME_MODULES),
        "logs": LOGS[-20:],  # Last 20 logs
        "pool_min": POOL_MIN,
        "pool_max": POOL_MAX,
        "timeout": INACTIVITY_TIMEOUT
    })

@app.route('/connect', methods=['POST'])
def bot_connect():
    d = request.json
    BOT_STATE.update({"user": d['u'], "pass": d['p'], "room": d['r'], "reconnect": True})
    threading.Thread(target=connect_ws_loop, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route('/disconnect', methods=['POST'])
def bot_disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    return jsonify({"status": "ok"})

@app.route('/health')
def health(): 
    return jsonify({"status": "ACTIVE v19.0", "db_ok": not GLOBAL_DATA["flags"]["db_error"]})

# ======================================================
# 11. BOOT SEQUENCE
# ======================================================
print(">> TITAN ENGINE v19.0 - PERMANENT CORE BOOTING...")
load_all_plugins()
load_persistence_task()

# Start daemon threads
threading.Thread(target=memory_cleanup_task, daemon=True).start()
threading.Thread(target=save_persistence_task, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
