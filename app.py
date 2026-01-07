# ======================================================
# FILE: app.py (TITAN ENGINE v7.5 - THE FINAL DESTINY)
# ======================================================
import os, json, time, threading, websocket, psycopg2, importlib.util, requests, io, sys
from flask import Flask, render_template_string, request, jsonify, send_file
from psycopg2 import pool
from datetime import datetime

# --- 1. RENDER & PATH SECURITY ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

import ui # ui.py link

app = Flask(__name__)

# --- 2. CONFIGURATION & NEON DB POOL ---
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    # Pool connection for high performance
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, NEON_URL, sslmode='require')
    _conn = db_pool.getconn()
    with _conn.cursor() as _c:
        _c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        _c.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    _conn.commit()
    db_pool.putconn(_conn)
except Exception as e:
    print(f">> DB Critical Error: {e}")

# Global States
BOT_STATE = {"ws": None, "connected": False, "user": "", "pass": "", "room": "", "reconnect": True}
ACTIVE_GAMES = {}   # Master Memory
GAME_MODULES = {}   # Plug-in list
USER_COOLDOWN = {}  # Anti-Spam
LOGS = []
LOCK = threading.Lock()

def add_log(msg, log_type="sys"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    # Logs capping (50) to save RAM on Render
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# --- 3. THE PLUG-IN ENGINE ---
def load_all_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    for folder in ['games', 'plugins']:
        path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path)
            with open(os.path.join(path, "__init__.py"), "w") as f: f.write("")
        
        add_log(f"Initializing {folder}...", "sys")
        try:
            for filename in os.listdir(path):
                if filename.endswith(".py") and filename != "__init__.py":
                    file_path = os.path.join(path, filename)
                    module_name = filename[:-3]
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, file_path)
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                            GAME_MODULES[mod.TRIGGER.lower()] = mod
                            add_log(f"✅ READY: {mod.TRIGGER}", "sys")
                    except Exception as e:
                        add_log(f"❌ CRASH in {filename}: {str(e)}", "err")
        except Exception as e:
            add_log(f"Path Error: {e}", "err")

# --- 4. PERSISTENCE (Restart Safety) ---
def save_persistent_state():
    while True:
        time.sleep(120) # Backup every 2 minutes
        with LOCK:
            if ACTIVE_GAMES:
                try:
                    state_json = json.dumps(ACTIVE_GAMES)
                    conn = db_pool.getconn()
                    with conn.cursor() as c:
                        c.execute("INSERT INTO bot_state (key, data) VALUES ('active_games', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (state_json, state_json))
                    conn.commit()
                    db_pool.putconn(conn)
                except: pass

def load_persistent_state():
    global ACTIVE_GAMES
    try:
        conn = db_pool.getconn()
        with conn.cursor() as c:
            c.execute("SELECT data FROM bot_state WHERE key = 'active_games'")
            res = c.fetchone()
            if res:
                ACTIVE_GAMES = json.loads(res[0])
                add_log(f"Restored {len(ACTIVE_GAMES)} game sessions.", "sys")
        db_pool.putconn(conn)
    except: pass

# --- 5. CORE FUNCTIONS ---
def update_score_neon(user, pts):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (user, pts, pts))
        conn.commit()
    except Exception as e:
        add_log(f"DB Error: {e}", "err")
    finally:
        db_pool.putconn(conn)

def send_msg(room, text):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            packet = {
                "handler": "room_message", "id": str(time.time()), 
                "room": room, "type": "text", "body": str(text),
                "url": "", "length": "0"
            }
            BOT_STATE["ws"].send(json.dumps(packet))
        except: pass

def on_message(ws, message):
    try:
        data = json.loads(message)
        
        # Filter out useless packets
        if data.get("handler") == "receipt_ack": return

        # Auto-Rejoin logic
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam (0.8s)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}"

            with LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time()
                
                cmd = msg.split()[0].lower() if msg else ""

                # Route to Plugin
                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_s = handler.handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                            if not new_s.get("active"):
                                if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
                            else:
                                ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Error in {state['game_type']}: {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except: pass

# --- 6. BACKGROUND PROCESSES ---
def cleanup_loop():
    while True:
        time.sleep(60)
        now = time.time()
        with LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del: del ACTIVE_GAMES[u]

threading.Thread(target=cleanup_loop, daemon=True).start()
threading.Thread(target=save_persistent_state, daemon=True).start()

# --- 7. WS & ROUTES ---
def on_open(ws):
    add_log("Connecting to Core...", "sys")
    ws.send(json.dumps({"handler": "login", "id": str(time.time()), "username": BOT_STATE["user"], "password": BOT_STATE["pass"]}))
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server",
                on_open=on_open, on_message=on_message,
                on_close=lambda w,c,m: BOT_STATE.update({"connected":False}))
            BOT_STATE["ws"] = ws
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except: time.sleep(5)

@app.route('/')
def index(): return render_template_string(ui.HTML_DASHBOARD)
@app.route('/status')
def status(): return jsonify({"connected": BOT_STATE["connected"],"sessions": len(ACTIVE_GAMES),"plugins": len(GAME_MODULES),"logs": LOGS})
@app.route('/connect', methods=['POST'])
def connect():
    d = request.json
    BOT_STATE.update({"user":d['u'], "pass":d['p'], "room":d['r'], "reconnect":True})
    threading.Thread(target=connect_ws, daemon=True).start()
    return jsonify({"status": "ok"})
@app.route('/disconnect', methods=['POST'])
def disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    return jsonify({"status": "ok"})
@app.route('/health')
def health(): return "OK", 200

# --- STARTUP ---
print(">> TITAN OS BOOTING...")
load_all_plugins()
load_persistent_state()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
