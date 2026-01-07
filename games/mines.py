# ======================================================
# FILE: games/mines.py (SELF-HEALING & PERSISTENCE SAFE)
# ======================================================
import random
TRIGGER = "!mines"

def render_grid(bombs, eaten, reveal=False, exploded=None):
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    txt = ""
    for i in range(1, 10):
        if reveal and i == exploded: txt += "💥 "
        elif reveal and i in bombs: txt += "💣 "
        elif i in eaten: txt += "🥔 "
        else: txt += icons[i-1] + " "
        if i % 3 == 0 and i != 9: txt += "\n"
    return txt

def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, db_get_top, global_data, add_log, send_image):
    msg_clean = msg.lower().strip()

    # --- 1. START LOGIC ---
    if msg_clean == TRIGGER:
        # Check: Kya dabba corrupt hai? (Active hai par data missing hai)
        is_corrupt = state.get("active") and ("eaten" not in state or "bombs" not in state)
        
        if state.get("active") == True and not is_corrupt:
            send_text(f"⚠️ @{user}, aapka game pehle se chalu hai! !eat <number> likho.")
            return state
        
        # Fresh Setup
        state["active"] = True
        state["game_type"] = TRIGGER
        state["bombs"] = random.sample(range(1, 10), 2)
        state["eaten"] = []
        
        grid = render_grid(state["bombs"], [])
        send_text(f"💣 MINES STARTED! @{user}\nType: !eat <1-9>\n\n{grid}")
        return state

    # --- 2. GAMEPLAY LOGIC ---
    elif msg_clean.startswith("!eat"):
        # 🔥 SELF-HEALING CHECK: Agar memory corrupt hai toh crash mat ho, reset kar do
        if state.get("active") == True:
            if "eaten" not in state or "bombs" not in state:
                add_log(f"Detected corrupt memory for {user}. Resetting.")
                state["active"] = False # Dabba delete karne ka ishara
                send_text(f"⚠️ @{user}, purani memory kharab ho gayi thi. Game reset kar diya hai, dobara !mines likho.")
                return state

        # Normal Gameplay
        if not state.get("active"): return state
        
        try:
            parts = msg_clean.split()
            if len(parts) < 2: return state
            num = int(parts[1])
        except: return state

        if num < 1 or num > 9 or num in state.get("eaten", []): return state

        if num in state.get("bombs", []):
            state["active"] = False
            grid = render_grid(state["bombs"], state["eaten"], True, num)
            send_text(f"💥 BOOM! @{user} hit a bomb!\n💀 GAME OVER.\n\n{grid}")
        else:
            state["eaten"].append(num)
            if len(state["eaten"]) == 4:
                state["active"] = False
                db_set_score(user, 50)
                grid = render_grid(state["bombs"], state["eaten"], True)
                send_text(f"🎉 WINNER! @{user} (+50 pts)\n\n{grid}")
            else:
                grid = render_grid(state["bombs"], state["eaten"])
                send_text(f"🥔 SAFE! ({len(state['eaten'])}/4)\n{grid}")

    return state
