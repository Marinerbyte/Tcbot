# ======================================================
# FILE: app.py (TITAN ENGINE v16.0 - THE ULTIMATE CORE)
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

# --- 1. SYSTEM PATH SECURITY ---
# Ye Render server par folder structure ko pathar jaisa pakka karta hai
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Dashboard UI Connection
try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>FATAL ERROR: ui.py file missing!</h1>"
    ui = UI()

app = Flask(__name__)

# ======================================================
# 2. NEON DATABASE CONFIGURATION (THREADED POOLING)
# ======================================================
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

# DO ALAG LOCKS: Ek logic ke liye, ek database ke SSL connection ke liye
LOGIC_LOCK = threading.Lock()
DB_LOCK = threading.Lock()

try:
    # 20 concurrent connections ka pool (High performance)
    db_pool = pool.ThreadedConnectionPool(1, 20, NEON_URL, sslmode='require')
    
    # Tables check and initialization
    _startup_conn = db_pool.getconn()
    with _startup_conn.cursor() as _cur:
        # Table 1: Scores
        _cur.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        # Table 2: Persistent State (Restart Backup)
        _cur.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    _startup_conn.commit()
    db_pool.putconn(_startup_conn)
    print(">> [DATABASE] Multi-thread Pool initialized and tables verified.")
except Exception as e:
    print(f">> [DATABASE_ERROR] {e}")

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

ACTIVE_GAMES = {}   # Sessions RAM (Dabbe)
GLOBAL_DATA = {}    # Shared Persistent Memory (Plugins ke liye)
GAME_MODULES = {}   # Loaded Plugins List
USER_COOLDOWN = {}  # Anti-Spam (Rate Limiter)
LOGS = []           # Live Dashboard Logs

def add_log(msg, log_type="sys"):
    """Dashboard par message bhejta hai aur RAM manage karta hai"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# ======================================================
# 4. DATABASE MASTER TOOLS (Plugins can use these)
# ======================================================
def db_set_score(target, pts):
    """Database mein score update karta hai (Thread-safe)"""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (target, pts, pts))
            conn.commit()
        finally:
            db_pool.putconn(conn)

def db_get_score(target):
    """Kisi bhi user ka score database se mangta hai"""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT score FROM users WHERE username = %s", (target,))
                res = c.fetchone()
                return res[0] if res else 0
        finally:
            db_pool.putconn(conn)

def db_get_top_10():
    """Top 10 players ki list mangta hai"""
    with DB_LOCK:
        conn = db_pool.getconn()
        try:
            with conn.cursor() as c:
                c.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
                return c.fetchall()
        finally:
            db_pool.putconn(conn)

# ======================================================
# 5. PERSISTENCE & RECOVERY (Render-Restart Safe)
# ======================================================
def save_persistence_task():
    """Background task: Har 2 min mein RAM ka snapshot database mein save karna"""
    while True:
        time.sleep(120)
        with LOGIC_LOCK: # RAM Lock
            with DB_LOCK:    # DB Lock
                if ACTIVE_GAMES or GLOBAL_DATA:
                    try:
                        bundle = {"sessions": ACTIVE_GAMES, "global": GLOBAL_DATA}
                        serialized = json.dumps(bundle)
                        conn = db_pool.getconn()
                        with conn.cursor() as c:
                            c.execute("INSERT INTO bot_state (key, data) VALUES ('master_state_v16', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (serialized, serialized))
                        conn.commit()
                        db_pool.putconn(conn)
                    except Exception as e:
                        print(f"Backup Error: {e}")

def load_persistence_task():
    """Bot restart hone par purana data cloud se wapas load karna"""
    global ACTIVE_GAMES, GLOBAL_DATA
    with DB_LOCK:
        try:
            conn = db_pool.getconn()
            with conn.cursor() as c:
                c.execute("SELECT data FROM bot_state WHERE key = 'master_state_v16'")
                res = c.fetchone()
                if res:
                    recovered = json.loads(res[0])
                    ACTIVE_GAMES = recovered.get("sessions", {})
                    GLOBAL_DATA = recovered.get("global", {})
                    add_log(f"RECOVERY: {len(ACTIVE_GAMES)} sessions restored.", "sys")
            db_pool.putconn(conn)
        except Exception as e:
            print(f"Recovery Error: {e}")

# ======================================================
# 6. DYNAMIC PLUG-IN ENGINE (No Import Needed)
# ======================================================
def load_all_plugins():
    """Folder scan karke games aur plugins ko auto-load karna"""
    global GAME_MODULES
    GAME_MODULES = {}
    
    for folder in ['games', 'plugins']:
        folder_path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
            with open(os.path.join(folder_path, "__init__.py"), "w") as f: f.write("# Init")
        
        add_log(f"Syncing folder: {folder}", "sys")
        
        for filename in os.listdir(folder_path):
            if filename.endswith(".py") and filename != "__init__.py":
                file_full_path = os.path.join(folder_path, filename)
                module_name = filename[:-3]
                
                try:
                    # Linux-safe path based loading
                    spec = importlib.util.spec_from_file_location(module_name, file_full_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ READY: {mod.TRIGGER}", "sys")
                except Exception as e:
                    add_log(f"❌ CRASH in {filename}: {e}", "err")

# ======================================================
# 7. COMMUNICATION TOOLS (For Text, Images, and Raw)
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
# 8. THE MASTER ROUTER (on_message - The Brain)
# ======================================================
def on_message(ws, message):
    try:
        data = json.loads(message)
        if data.get("handler") == "receipt_ack": return # Noise filter

        # 1. AUTO-REJOIN (Anti-Kick / Anti-Idle)
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        # 2. MESSAGE PROCESSOR
        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam (Cooldown: 0.8s)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}"

            # --- THE MASTER LOCK BLOCK ---
            with LOGIC_LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time() # Timer refresh
                
                parts = msg.split()
                cmd = parts[0].lower() if parts else ""

                # Tools for the plugin (11 Arguments)
                args = (
                    user, msg, state,
                    lambda t: send_chat_text(room, t), # send_text
                    send_raw_payload,                  # send_raw
                    db_set_score,                     # db_set_score
                    db_get_score,                     # db_get_score
                    db_get_top_10,                    # db_get_top
                    GLOBAL_DATA,                      # global_data
                    lambda m: add_log(f"Plugin: {m}"),# add_log
                    lambda t, u: send_chat_image(room, t, u) # send_image
                )

                # ROUTING ENGINE
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
                            add_log(f"Crash in {ctx_key}: {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except Exception as e:
        print(f"Engine Error: {e}")

# ======================================================
# 9. 90-SECOND MEMORY CLEANUP
# ======================================================
def memory_cleanup_task():
    while True:
        time.sleep(10) # 10 sec mein scan karo
        now = time.time()
        with LOGIC_LOCK:
            # Jo banda 90 sec se shant hai, dabba delete
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 90]
            for u in to_del:
                del ACTIVE_GAMES[u]
                add_log(f"Vacuum: Session {u} cleared.", "sys")

# Background threads launch
threading.Thread(target=memory_cleanup_task, daemon=True).start()
threading.Thread(target=save_persistence_task, daemon=True).start()

# ======================================================
# 10. WEBSOCKET & SERVER LOGIC
# ======================================================
def on_open(ws):
    add_log("TITAN ENGINE: Handshake complete. Authenticating...", "sys")
    ws.send(json.dumps({"handler":"login","id":str(time.time()),"username":BOT_STATE["user"],"password":BOT_STATE["pass"]}))
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws_loop():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server", on_open=on_open, on_message=on_message, on_close=lambda w,c,m: BOT_STATE.update({"connected": False}), on_error=lambda w,e: add_log(f"Socket Error: {e}", "err"))
            BOT_STATE["ws"] = ws
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except: time.sleep(5)

@app.route('/')
def index(): return render_template_string(ui.HTML_DASHBOARD)

@app.route('/status')
def get_status():
    return jsonify({"connected": BOT_STATE["connected"], "sessions": len(ACTIVE_GAMES), "plugins": len(GAME_MODULES), "logs": LOGS})

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
def health(): return "ACTIVE", 200

# ======================================================
# 11. BOOT SEQUENCE
# ======================================================
print(">> TITAN MASTER CORE v16.0 FINAL INITIALIZING...")
load_all_plugins()
load_persistence_task()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
