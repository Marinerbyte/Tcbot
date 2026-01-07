# --- FILE: app.py ---
import os, json, time, threading, websocket, psycopg2, importlib, pkgutil, requests
from flask import Flask, render_template_string, request, jsonify
from psycopg2 import pool
from datetime import datetime
import ui

app = Flask(__name__)

# --- 1. SETTINGS & NEON POOL ---
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    db_pool = psycopg2.pool.SimpleConnectionPool(1, 10, NEON_URL, sslmode='require')
    conn = db_pool.getconn()
    with conn.cursor() as c:
        c.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
    conn.commit()
    db_pool.putconn(conn)
except Exception as e: print(f"DB Pool Error: {e}")

BOT_STATE = {"ws": None, "connected": False, "user": "", "pass": "", "room": "", "reconnect": True}
ACTIVE_GAMES = {}
GAME_MODULES = {}
USER_COOLDOWN = {}
LOGS = []
LOCK = threading.Lock()

def add_log(msg, type="sys"):
    LOGS.append({"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "type": type})
    if len(LOGS) > 50: LOGS.pop(0)

# --- 2. PLUG-AND-PLAY LOADER ---
def load_plugins():
    global GAME_MODULES
    GAME_MODULES = {}
    for folder in ['games', 'plugins']:
        if not os.path.exists(folder): os.makedirs(folder)
        pkg = importlib.import_module(folder)
        for _, name, _ in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"{folder}.{name}")
            if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                GAME_MODULES[mod.TRIGGER.lower()] = mod
    add_log(f"Engine Ready. {len(GAME_MODULES)} Plugins Loaded.", "sys")

# --- 3. CORE LOGIC ---
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
        # AUTO-REJOIN (Kick/Idle Fix)
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
                cmd = msg.split()[0].lower()

                # Routing
                if cmd in GAME_MODULES and not state["active"]:
                    state.update({"active": True, "game_type": cmd})
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                elif state["active"]:
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            new_s = handler.handle(user, msg, state, lambda t: send_msg(room, t), update_score_neon)
                            if not new_s["active"]: del ACTIVE_GAMES[ctx_key]
                            else: ACTIVE_GAMES[ctx_key] = new_s
                        except: del ACTIVE_GAMES[ctx_key]
    except Exception as e: print(e)

# Cleanup Thread
def cleanup():
    while True:
        time.sleep(60); now = time.time()
        with LOCK:
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del: del ACTIVE_GAMES[u]
threading.Thread(target=cleanup, daemon=True).start()

# --- 4. WEBSOCKET & ROUTES ---
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
    app.run(host='0.0.0.0', port=os.environ.get("PORT", 5000))
