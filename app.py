# --- FILE: app.py ---
import os, json, time, threading, websocket, psycopg2, importlib, pkgutil, requests
from flask import Flask, render_template_string, request, jsonify
from psycopg2 import pool
from datetime import datetime
import ui

app = Flask(__name__)

# --- 1. NEON CONFIGURATION (Restart-Safe Backup Included) ---
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 15, NEON_URL, sslmode='require')
    conn = db_pool.getconn()
    with conn.cursor() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        c.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    conn.commit()
    db_pool.putconn(conn)
except Exception as e: print(f"Init Error: {e}")

BOT_STATE = {"ws": None, "connected": False, "user": "", "pass": "", "room": "", "reconnect": True}
ACTIVE_GAMES = {}
GAME_MODULES = {}
USER_COOLDOWN = {}
LOGS = []
LOCK = threading.Lock()

def add_log(msg, type="sys"):
    LOGS.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": str(msg), "type": type})
    if len(LOGS) > 50: LOGS.pop(0)

# --- 2. THE RECOVERY SYSTEM (Neon DB Backup) ---
def save_persistent_state():
    """Chalte hue games ka backup DB mein save karta hai har 2 min mein"""
    while True:
        time.sleep(120)
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
    """Restart ke baad games wapas load karta hai"""
    global ACTIVE_GAMES
    try:
        conn = db_pool.getconn()
        with conn.cursor() as c:
            c.execute("SELECT data FROM bot_state WHERE key = 'active_games'")
            res = c.fetchone()
            if res: ACTIVE_GAMES = json.loads(res[0])
        db_pool.putconn(conn)
        add_log(f"Recovery: Loaded {len(ACTIVE_GAMES)} sessions from Neon DB.", "sys")
    except: pass

# --- 3. PLUG-AND-PLAY ENGINE ---
def load_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    for folder in ['games', 'plugins']:
        if not os.path.exists(folder): os.makedirs(folder)
        if not os.path.exists(f"{folder}/__init__.py"): open(f"{folder}/__init__.py", "w").close()
        pkg = importlib.import_module(folder)
        for _, name, _ in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"{folder}.{name}")
            if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                GAME_MODULES[mod.TRIGGER.lower()] = mod
    add_log(f"Engine Ready. {len(GAME_MODULES)} Plug-ins loaded.", "sys")

# --- 4. ENGINE CORE ---
def update_score_neon(user, pts):
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (user, pts, pts))
        conn.commit()
    finally: db_pool.putconn(conn)

def send_msg(room, text):
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try: BOT_STATE["ws"].send(json.dumps({"handler":"room_message","room":room,"type":"text","body":text}))
        except: pass

def on_message(ws, message):
    try:
        data = json.loads(message)
        # AUTO-REJOIN (Kick/Idle/Timeout Protection)
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # Anti-Spam Guard (0.8s Rate Limit)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            ctx_key = f"{room}_{user}" # Multi-Room Context

            # --- THE SECURE RACE CONDITION LOCK ---
            with LOCK:
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time()
                cmd = msg.split()[0].lower()

                # SMART ROUTING
                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            # Isolation: Ek game crash ho to bot na ruke
                            new_s = handler.handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                            if not new_s["active"]: del ACTIVE_GAMES[ctx_key]
                            else: ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Plugin Error: {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except Exception as e: print(f"Global Error: {e}")

# Cleanup Loop (Memory Protection)
def cleanup():
    while True:
        time.sleep(60); now = time.time()
        with LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del: del ACTIVE_GAMES[u]

threading.Thread(target=cleanup, daemon=True).start()
threading.Thread(target=save_persistent_state, daemon=True).start()

# --- 5. WS CONNECTION & FLASK ---
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
def status(): return jsonify({"connected":BOT_STATE["connected"],"sessions":len(ACTIVE_GAMES),"plugins":len(GAME_MODULES),"logs":LOGS})
@app.route('/connect', methods=['POST'])
def connect():
    d = request.json
    BOT_STATE.update({"user":d['u'],"pass":d['p'],"room":d['r'],"reconnect":True})
    threading.Thread(target=connect_ws, daemon=True).start()
    return jsonify({"status":"ok"})
@app.route('/disconnect', methods=['POST'])
def disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]: BOT_STATE["ws"].close()
    return jsonify({"status":"ok"})

if __name__ == '__main__':
    load_plugins()
    load_persistent_state() # Restart recovery
    app.run(host='0.0.0.0', port=os.environ.get("PORT", 5000))
