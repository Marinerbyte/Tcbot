# ======================================================
# FILE: app.py (THE ULTIMATE MASTER ENGINE - FINAL)
# ======================================================
import os, json, time, threading, websocket, psycopg2, importlib, pkgutil, requests, io, sys
from flask import Flask, render_template_string, request, jsonify, send_file
from psycopg2 import pool
from datetime import datetime

# Path fix taaki Render plugins ko sahi se dhund sake
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Design file ko import kiya
try:
    import ui
except ImportError:
    # Agar ui.py nahi hai to basic design
    class UI: HTML_DASHBOARD = "<h1>ui.py missing! Please create it.</h1>"
    ui = UI()

app = Flask(__name__)

# --- 1. CONFIGURATION (Neon DB Pool) ---
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 15, NEON_URL, sslmode='require')
    conn = db_pool.getconn()
    with conn.cursor() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    conn.commit()
    db_pool.putconn(conn)
except Exception as e:
    print(f">> DB Pool Error: {e}")

BOT_STATE = {"ws": None, "connected": False, "user": "", "pass": "", "room": "", "reconnect": True}
ACTIVE_GAMES = {}   # Master Almari (Multi-User)
GAME_MODULES = {}   # Loaded Plugins/Games
USER_COOLDOWN = {}  # Anti-Spam (0.8s)
LOGS = []
LOCK = threading.Lock() # Race Condition Fix

def add_log(msg, log_type="sys"):
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# --- 2. THE PLUG-AND-PLAY LOADER (Detailed Diagnostics) ---
def load_all_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    folders = ['games', 'plugins']
    
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
            with open(os.path.join(folder, "__init__.py"), "w") as f: f.write("")
        
        add_log(f"Scanning folder: {folder}...", "sys")
        
        # Folder ke andar ki files check karo
        for file in os.listdir(folder):
            if file.endswith(".py") and file != "__init__.py":
                module_name = file[:-3]
                module_path = f"{folder}.{module_name}"
                try:
                    # Reload if already in memory
                    if module_path in sys.modules:
                        importlib.reload(sys.modules[module_path])
                    
                    mod = importlib.import_module(module_path)
                    
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ Loaded: {mod.TRIGGER}", "sys")
                    else:
                        add_log(f"⚠️ {file} missing TRIGGER or handle", "err")
                except Exception as e:
                    add_log(f"❌ CRASH in {file}: {str(e)}", "err")

    if not GAME_MODULES:
        add_log("🛑 No games/plugins found!", "err")

# --- 3. DATABASE HELPERS ---
def update_score_neon(user, pts):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (user, pts, pts))
        conn.commit()
    except Exception as e:
        add_log(f"DB Update Error: {e}", "err")
    finally:
        db_pool.putconn(conn)

# --- 4. ENGINE CORE (WebSocket Handlers) ---
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
        # 1. AUTO-REJOIN (Kick/Idle Fix)
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        # 2. MESSAGE ROUTING
        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam (0.8s)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}" # Multi-Room User Context

            # --- THE SECURE LOCK BLOCK ---
            with LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time()
                
                # Check for commands
                msg_lower = msg.lower().strip()
                cmd = msg_lower.split()[0] if msg_lower else ""

                # A. PLUGIN START
                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                
                # B. PLUGIN GAMEPLAY
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_s = handler.handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                            if not new_s["active"]:
                                if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
                            else:
                                ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Plugin Error ({user}): {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]

    except Exception as e:
        print(f"Global Message Error: {e}")

# Cleanup Loop (RAM Safai)
def cleanup():
    while True:
        time.sleep(60); now = time.time()
        with LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del: del ACTIVE_GAMES[u]

threading.Thread(target=cleanup, daemon=True).start()

# --- 5. FLASK & WEBSOCKET SETUP ---
def on_open(ws):
    add_log("Server Connected. Authenticating...", "sys")
    ws.send(json.dumps({
        "handler": "login", "id": str(time.time()), 
        "username": BOT_STATE["user"], "password": BOT_STATE["pass"]
    }))
    # Join Rooms
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))

def connect_ws():
    while BOT_STATE["reconnect"]:
        try:
            websocket.enableTrace(False)
            ws = websocket.WebSocketApp("wss://chatp.net:5333/server",
                on_open=on_open,
                on_message=on_message,
                on_close=lambda w,c,m: BOT_STATE.update({"connected":False}),
                on_error=lambda w,e: add_log(f"Connection Error: {e}", "err"))
            BOT_STATE["ws"] = ws
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except: time.sleep(5)

@app.route('/')
def index(): return render_template_string(ui.HTML_DASHBOARD)

@app.route('/status')
def get_status():
    return jsonify({
        "connected": BOT_STATE.get("ws") is not None and BOT_STATE["connected"],
        "sessions": len(ACTIVE_GAMES),
        "plugins": len(GAME_MODULES),
        "logs": LOGS
    })

@app.route('/connect', methods=['POST'])
def do_connect():
    d = request.json
    BOT_STATE.update({"user":d['u'], "pass":d['p'], "room":d['r'], "reconnect":True, "connected":True})
    threading.Thread(target=connect_ws, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route('/disconnect', methods=['POST'])
def do_disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    load_all_plugins()
    # Port fix for Render
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
