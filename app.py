# ======================================================
# FILE: app.py (THE ULTIMATE MASTER ENGINE - COMPLETE)
# ======================================================
import os, json, time, threading, websocket, psycopg2, importlib, requests, io, sys
from flask import Flask, render_template_string, request, jsonify, send_file
from psycopg2 import pool
from datetime import datetime

# --- RENDER PATH FIX ---
sys.path.append(os.getcwd())
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Dashboard design file import
try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>ui.py missing!</h1>"
    ui = UI()

app = Flask(__name__)

# --- 1. SETTINGS & NEON DB POOL ---
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    # 1 se 15 connections ka pool (Safe & Fast)
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 15, NEON_URL, sslmode='require')
    conn = db_pool.getconn()
    with conn.cursor() as c:
        # User scores table
        c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        # Game backup table (Restart safety)
        c.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    conn.commit()
    db_pool.putconn(conn)
except Exception as e:
    print(f">> DB Setup Error: {e}")

BOT_STATE = {"ws": None, "connected": False, "user": "", "pass": "", "room": "", "reconnect": True}
ACTIVE_GAMES = {}   # Master Almari
GAME_MODULES = {}   # Plug-in list
USER_COOLDOWN = {}  # Anti-Spam
LOGS = []
LOCK = threading.Lock() # Race Condition Lock

def add_log(msg, log_type="sys"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# --- 2. RECOVERY SYSTEM (Neon Backup) ---
def save_state_to_db():
    """Har 2 minute mein chal rahe games ka backup Neon mein save karna"""
    while True:
        time.sleep(120)
        with LOCK:
            if ACTIVE_GAMES:
                try:
                    state_data = json.dumps(ACTIVE_GAMES)
                    conn = db_pool.getconn()
                    with conn.cursor() as c:
                        c.execute("INSERT INTO bot_state (key, data) VALUES ('active_games', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (state_data, state_data))
                    conn.commit()
                    db_pool.putconn(conn)
                except: pass

def load_state_from_db():
    """Restart ke baad games wapas Neon se RAM mein load karna"""
    global ACTIVE_GAMES
    try:
        conn = db_pool.getconn()
        with conn.cursor() as c:
            c.execute("SELECT data FROM bot_state WHERE key = 'active_games'")
            res = c.fetchone()
            if res:
                ACTIVE_GAMES = json.loads(res[0])
                add_log(f"RECOVERY: Restored {len(ACTIVE_GAMES)} game sessions.", "sys")
        db_pool.putconn(conn)
    except Exception as e:
        print(f"Recovery Error: {e}")

# --- 3. THE PLUG-AND-PLAY LOADER ---
def load_all_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    folders = ['games', 'plugins']
    for folder in folders:
        full_path = os.path.join(os.getcwd(), folder)
        if not os.path.exists(full_path):
            os.makedirs(full_path)
            with open(os.path.join(full_path, "__init__.py"), "w") as f: f.write("")
        
        add_log(f"Scanning folder: {folder}...", "sys")
        try:
            files = [f for f in os.listdir(full_path) if f.endswith(".py") and f != "__init__.py"]
            for file in files:
                module_name = file[:-3]
                module_path = f"{folder}.{module_name}"
                try:
                    if module_path in sys.modules:
                        importlib.reload(sys.modules[module_path])
                    mod = importlib.import_module(module_path)
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ LOADED: {mod.TRIGGER}", "sys")
                    else:
                        add_log(f"⚠️ SKIP: {file} (No TRIGGER)", "err")
                except Exception as e:
                    add_log(f"❌ CRASH in {file}: {str(e)}", "err")
        except Exception as e:
            add_log(f"Folder Access Error: {e}", "err")

# --- 4. ENGINE CORE ---
def update_score_neon(user, pts):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (user, pts, pts))
        conn.commit()
    finally:
        db_pool.putconn(conn)

def send_msg(room, text):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            BOT_STATE["ws"].send(json.dumps({
                "handler": "room_message", "id": str(time.time()), 
                "room": room, "type": "text", "body": text
            }))
        except: pass

def on_message(ws, message):
    try:
        data = json.loads(message)
        # AUTO-REJOIN (Kick Fix)
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

            # --- THE SECURE LOCK BLOCK ---
            with LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time()
                
                msg_clean = msg.lower().strip()
                cmd = msg_clean.split()[0] if msg_clean else ""

                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_s = handler.handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                            if not new_s["active"]: 
                                if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
                            else: ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Game Error ({user}): {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except: pass

# Cleanup Loop (Memory Protection)
def cleanup():
    while True:
        time.sleep(60); now = time.time()
        with LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del: del ACTIVE_GAMES[u]

threading.Thread(target=cleanup, daemon=True).start()
threading.Thread(target=save_state_to_db, daemon=True).start()

# --- 5. WEBSOCKET LOOP & ROUTES ---
def connect_ws():
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server",
                on_open=lambda w: [BOT_STATE.update({"connected":True}), w.send(json.dumps({"handler":"login","username":BOT_STATE["user"],"password":BOT_STATE["pass"]})), [w.send(json.dumps({"handler":"room_join","name":r.strip()})) for r in BOT_STATE["room"].split(",")]],
                on_message=on_message, on_close=lambda w,c,m: BOT_STATE.update({"connected":False}))
            BOT_STATE["ws"] = ws
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except: time.sleep(5)

@app.route('/')
def index(): return render_template_string(ui.HTML_DASHBOARD)

@app.route('/status')
def status():
    return jsonify({
        "connected": BOT_STATE["ws"] is not None and BOT_STATE["connected"],
        "sessions": len(ACTIVE_GAMES),
        "plugins": len(GAME_MODULES),
        "logs": LOGS
    })

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
def health(): return "I AM ALIVE", 200

if __name__ == '__main__':
    load_all_plugins()
    load_state_from_db() # Recovery on start
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)