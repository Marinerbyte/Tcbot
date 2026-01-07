# ======================================================
# FILE: app.py (TITAN ENGINE v13.0 - THE ULTIMATE BEAST)
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

# --- 1. RENDER & SYSTEM PATH PROTECTION ---
# Ye hissa pakka karta hai ki Render server ko saare folders mil jayein
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# UI File Connection
try:
    import ui
except ImportError:
    class UI: HTML_DASHBOARD = "<h1>CRITICAL ERROR: ui.py not found!</h1>"
    ui = UI()

app = Flask(__name__)

# ======================================================
# 2. NEON DATABASE & CONNECTION POOLING (High Stability)
# ======================================================
# Pool use karne se database kabhi "Busy" ya "Too many connections" nahi bolega
NEON_URL = "postgresql://neondb_owner:npg_junx8Gtl3kPp@ep-lucky-sun-a4ef37sy-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"

try:
    # 1 se 20 connections ka pool banaya
    db_pool = pool.SimpleConnectionPool(1, 20, NEON_URL, sslmode='require')
    
    # Tables Check (Startup par hi table bana leta hai)
    _db_conn = db_pool.getconn()
    with _db_conn.cursor() as _cursor:
        # Table 1: Scores save karne ke liye
        _cursor.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, score INTEGER DEFAULT 0)")
        # Table 2: Bot ki memory backup ke liye (Restart safety)
        _cursor.execute("CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, data TEXT)")
    _db_conn.commit()
    db_pool.putconn(_db_conn)
    print(">> [DB_SYSTEM] Neon Pool and Tables are verified and active.")
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

ACTIVE_GAMES = {}   # Har user ka alag dabba (Session memory)
GLOBAL_DATA = {}    # Shared permanent memory (Plugins ke liye)
GAME_MODULES = {}   # Saare loaded plugins ki list
USER_COOLDOWN = {}  # Anti-Spam (Flood control)
LOGS = []           # Live Terminal logs
LOCK = threading.Lock() # THE MASTER PROTECTOR (Race Condition Fix)

def add_log(msg, log_type="sys"):
    """Dashboard terminal par log bhejne ka function"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    # 50 log ki limit taaki RAM na bhare
    LOGS.append({"time": timestamp, "msg": str(msg), "type": log_type})
    if len(LOGS) > 50: LOGS.pop(0)

# ======================================================
# 4. DATABASE UNIVERSAL FUNCTIONS (For Plugins)
# ======================================================
def db_set_score(target_user, points):
    """Bina galti ke kisi ka bhi score badhane ya ghatane ke liye"""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            # SQL Atomic Update: Race condition ko database level par bhi rokta hai
            c.execute("INSERT INTO users (username, score) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET score = users.score + %s", (target_user, points, points))
        conn.commit()
    finally:
        db_pool.putconn(conn)

def db_get_score(target_user):
    """Database se kisi specific bande ka score check karna"""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT score FROM users WHERE username = %s", (target_user,))
            res = c.fetchone()
            return res[0] if res else 0
    finally:
        db_pool.putconn(conn)

def db_get_top_10():
    """Top 10 players ki list mangwana (Leaderboard ke liye)"""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as c:
            c.execute("SELECT username, score FROM users ORDER BY score DESC LIMIT 10")
            return c.fetchall()
    finally:
        db_pool.putconn(conn)

# ======================================================
# 5. RECOVERY & PERSISTENCE (The "Immortal" Logic)
# ======================================================
def save_persistence_task():
    """Background thread: Har 2 min mein saara data Neon mein backup karta hai"""
    while True:
        time.sleep(120)
        with LOCK: # Lock lagaya taaki backup ke waqt data change na ho
            try:
                # Active games aur Global settings ka bundle
                bundle = {"sessions": ACTIVE_GAMES, "global": GLOBAL_DATA}
                serialized_data = json.dumps(bundle)
                
                conn = db_pool.getconn()
                with conn.cursor() as c:
                    c.execute("INSERT INTO bot_state (key, data) VALUES ('master_state', %s) ON CONFLICT (key) DO UPDATE SET data = %s", (serialized_data, serialized_data))
                conn.commit()
                db_pool.putconn(conn)
            except Exception as e:
                print(f"Persistence Save Error: {e}")

def load_persistence_task():
    """Bot restart hone par purana data Neon se wapas laata hai"""
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
                add_log(f"RECOVERY: Restored {len(ACTIVE_GAMES)} sessions from Cloud.", "sys")
        db_pool.putconn(conn)
    except Exception as e:
        print(f"Persistence Load Error: {e}")

# ======================================================
# 6. DYNAMIC PLUG-IN LOADER (Plug-and-Play Engine)
# ======================================================
def load_all_plugins():
    """Folder scan karke plugins ko auto-load karta hai"""
    global GAME_MODULES
    GAME_MODULES = {}
    
    for folder in ['games', 'plugins']:
        path = os.path.join(BASE_DIR, folder)
        # Folder nahi hai toh bana do
        if not os.path.exists(path):
            os.makedirs(path)
            with open(os.path.join(path, "__init__.py"), "w") as f: f.write("#")
        
        add_log(f"Scanning folder: {folder}...", "sys")
        
        for filename in os.listdir(path):
            if filename.endswith(".py") and filename != "__init__.py":
                file_path = os.path.join(path, filename)
                module_name = filename[:-3]
                
                try:
                    # Professional Path-Based Loading (Render/Linux safe)
                    spec = importlib.util.spec_from_file_location(module_name, file_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    
                    # Check if standard plugin variables exist
                    if hasattr(mod, "TRIGGER") and hasattr(mod, "handle"):
                        GAME_MODULES[mod.TRIGGER.lower()] = mod
                        add_log(f"✅ READY: {mod.TRIGGER}", "sys")
                    else:
                        add_log(f"⚠️ SKIP: {filename} (No Trigger/Handle)", "err")
                except Exception as e:
                    add_log(f"❌ CRASH in {filename}: {e}", "err")

# ======================================================
# 7. COMMUNICATION TOOLS (The Messenger)
# ======================================================
def send_text_msg(room, text):
    """Chatroom mein text message bhejta hai (Packet format fixed)"""
    if BOT_STATE["ws"] and BOT_STATE["connected"]:
        try:
            packet = {
                "handler": "room_message", 
                "id": str(time.time()), 
                "room": room, 
                "type": "text", 
                "body": str(text),
                "url": "",      # Mandatory field
                "length": "0"   # Mandatory field
            }
            BOT_STATE["ws"].send(json.dumps(packet))
        except: pass

def send_raw_packet(payload):
    """Server ko raw commands bhejne ke liye (Kick, Ban, Join)"""
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
        
        # Receipt packets ignore karo
        if data.get("handler") == "receipt_ack": return

        # 1. ANTI-KICK / AUTO-REJOIN PROTOCOL
        if data.get("type") == "error" and ("kick" in data.get("reason","").lower() or "idle" in data.get("reason","").lower()):
            add_log("Kick/Idle detected. Rejoining...", "err")
            for r in BOT_STATE["room"].split(","):
                ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
            return

        # 2. MAIN TEXT PROCESSOR
        if data.get("handler") == "room_event" and data.get("type") == "text":
            user, room, msg = data['from'], data['room'], data['body']
            
            # Bot khud ke message par reply nahi karega
            if user.lower() == BOT_STATE["user"].lower(): return
            
            # ANTI-SPAM (0.8s)
            now = time.time()
            if now - USER_COOLDOWN.get(user, 0) < 0.8: return
            USER_COOLDOWN[user] = now

            add_log(f"[{room}] {user}: {msg}", "in")
            
            # UNIQUE KEY: Room + User (Multi-chatroom and Multi-user safety)
            ctx_key = f"{room}_{user}"

            # --- THE CRITICAL LOCK BLOCK (Race Condition Protection) ---
            with LOCK:
                # User ka session dabba nikalo ya naya banao
                state = ACTIVE_GAMES.get(ctx_key, {"active": False, "game_type": None, "last_act": time.time()})
                state["last_act"] = time.time() # Activity timer update
                
                parts = msg.split()
                cmd = parts[0].lower() if parts else ""

                # Decision Engine: Kya naya game hai ya puraana move?
                if cmd in GAME_MODULES and not state["active"]:
                    # NAYA GAME SHURU KARO
                    state.update({"active": True, "game_type": cmd})
                    
                    # 10 ARGUMENTS UNIVERSAL CALL
                    ACTIVE_GAMES[ctx_key] = GAME_MODULES[cmd].handle(
                        user, msg, state, 
                        lambda t: send_text_msg(room, t), # send_text
                        send_raw_packet,                  # send_raw
                        db_set_score,                     # db_set_score
                        db_get_score,                     # db_get_score
                        db_get_top_10,                    # db_get_top
                        GLOBAL_DATA,                      # global_data
                        lambda m: add_log(f"PlugIn: {m}") # add_log
                    )
                
                elif state["active"]:
                    # CHALTE HUYE GAME KA LOGIC
                    handler = GAME_MODULES.get(state["game_type"])
                    if handler:
                        try:
                            # 10 Arguments call
                            new_s = handler.handle(
                                user, msg, state,
                                lambda t: send_text_msg(room, t),
                                send_raw_packet,
                                db_set_score,
                                db_get_score,
                                db_get_top_10,
                                GLOBAL_DATA,
                                lambda m: add_log(f"PlugIn: {m}")
                            )
                            # Cleanup Check: Agar game khatam, toh dabba saaf
                            if not new_s.get("active"):
                                if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
                            else:
                                ACTIVE_GAMES[ctx_key] = new_s
                        except Exception as e:
                            add_log(f"Plugin Error ({user}): {e}", "err")
                            if ctx_key in ACTIVE_GAMES: del ACTIVE_GAMES[ctx_key]
    except Exception as e:
        print(f"Global Router Error: {e}")

# ======================================================
# 9. BACKGROUND MAINTENANCE THREADS
# ======================================================
def memory_cleanup_task():
    """Safai Abhiyan: 10 min purane idle players ko RAM se nikalna"""
    while True:
        time.sleep(60)
        now = time.time()
        with LOCK:
            # List comprehension to find dead sessions
            to_del = [u for u, d in ACTIVE_GAMES.items() if now - d.get('last_act', 0) > 600]
            for u in to_del:
                del ACTIVE_GAMES[u]

# Threads ko Start karna
threading.Thread(target=memory_cleanup_task, daemon=True).start()
threading.Thread(target=save_persistence_task, daemon=True).start()

# ======================================================
# 10. WEBSOCKET LOOP & FLASK ROUTES
# ======================================================
def on_open(ws):
    add_log("TITAN OS: Successfully connected to Server.", "sys")
    # Login process
    ws.send(json.dumps({
        "handler": "login", 
        "id": str(time.time()), 
        "username": BOT_STATE["user"], 
        "password": BOT_STATE["pass"]
    }))
    # Saare rooms join karna jo Dashboard par likhe hain
    for r in BOT_STATE["room"].split(","):
        ws.send(json.dumps({"handler":"room_join", "name": r.strip()}))
    BOT_STATE["connected"] = True

def connect_ws_manager():
    """Auto-Reconnect Loop"""
    while BOT_STATE["reconnect"]:
        try:
            ws = websocket.WebSocketApp(
                "wss://chatp.net:5333/server",
                on_open=on_open,
                on_message=on_message,
                on_close=lambda w,c,m: BOT_STATE.update({"connected": False}),
                on_error=lambda w,e: add_log(f"Connection Error: {e}", "err")
            )
            BOT_STATE["ws"] = ws
            # Keep alive every 25s
            ws.run_forever(ping_interval=25, ping_timeout=10)
        except:
            time.sleep(5)

@app.route('/')
def index():
    return render_template_string(ui.HTML_DASHBOARD)

@app.route('/status')
def get_status():
    """Dashboard ko real-time data dena"""
    return jsonify({
        "connected": BOT_STATE.get("ws") is not None and BOT_STATE["connected"],
        "sessions": len(ACTIVE_GAMES),
        "plugins": len(GAME_MODULES),
        "logs": LOGS
    })

@app.route('/connect', methods=['POST'])
def handle_bot_connect():
    d = request.json
    BOT_STATE.update({"user": d['u'], "pass": d['p'], "room": d['r'], "reconnect": True})
    # Thread mein WebSocket chalu karo taaki Website na ruke
    threading.Thread(target=connect_ws_manager, daemon=True).start()
    return jsonify({"status": "ok"})

@app.route('/disconnect', methods=['POST'])
def handle_bot_disconnect():
    BOT_STATE["reconnect"] = False
    if BOT_STATE["ws"]:
        BOT_STATE["ws"].close()
    return jsonify({"status": "ok"})

@app.route('/health')
def health_ping():
    return "GOD_ENGINE_V13_ONLINE", 200

# ======================================================
# 11. BOOT-UP SEQUENCE (Gunicorn & Manual Ready)
# ======================================================
# YE CODE BAAHAR RAKHA HAI TAAKI DEPLOYMENT PAR TURANT PLUGINS LOAD HON
print(">> TITAN MASTER CORE v13.0 BOOTING...")
load_all_plugins()
load_persistence_task() # Backup wapas RAM mein load karna

if __name__ == '__main__':
    # Render port setting
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)