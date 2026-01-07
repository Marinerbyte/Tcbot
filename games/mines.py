# ======================================================
# FILE: games/mines.py (TITAN v17.0 COMPATIBLE)
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

# HANDLE FUNCTION: Isme ab pure 14 Arguments hain (v17.0 Standard)
def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, db_get_top, global_data, add_log, send_image, db_update_stat, db_get_user_stats, db_get_game_top):
    
    msg_clean = msg.lower().strip()

    # --- 1. START LOGIC ---
    if msg_clean == TRIGGER:
        # Self-healing: Agar dabba corrupt hai toh reset karo
        is_corrupt = state.get("active") and ("eaten" not in state or "bombs" not in state)
        if state.get("active") == True and not is_corrupt:
            send_text(f"⚠️ @{user}, aapka game pehle se chalu hai! !eat <number> likho.")
            return state

        state.update({
            "active": True, 
            "game_type": TRIGGER, 
            "bombs": random.sample(range(1, 10), 2), 
            "eaten": []
        })
        
        add_log(f"Mines started by {user}")
        grid = render_grid(state["bombs"], [])
        send_text(f"💣 MINES! @{user}\nGoal: 4 safe chips | 90s idle = Reset\n!eat <1-9>\n\n{grid}")
        return state

    # --- 2. GAMEPLAY LOGIC ---
    elif msg_clean.startswith("!eat"):
        # Check if active
        if not state.get("active") or "eaten" not in state:
            return state

        try:
            num = int(msg_clean.split()[1])
        except: return state

        if num < 1 or num > 9 or num in state["eaten"]:
            return state

        if num in state["bombs"]:
            state["active"] = False
            grid = render_grid(state["bombs"], state["eaten"], True, num)
            send_text(f"💥 BOOM! @{user} hit a bomb!\n💀 GAME OVER.\n\n{grid}")
            add_log(f"Mines: {user} hit a bomb.")
        else:
            state["eaten"].append(num)
            
            # WIN CONDITION
            if len(state["eaten"]) == 4:
                state["active"] = False
                prize = 50
                
                # --- POWER OF v17.0 ---
                # 1. Global Balance badhao
                db_set_score(user, prize)
                # 2. Mines ka alag se record badhao
                db_update_stat(user, "Mines", prize)
                
                grid = render_grid(state["bombs"], state["eaten"], True)
                send_text(f"🎉 WINNER! @{user} ate 4 chips!\n💰 +{prize} Global & Mines points added!\n\n{grid}")
                add_log(f"Mines Win: {user} +{prize}")
            else:
                grid = render_grid(state["bombs"], state["eaten"])
                send_text(f"🥔 SAFE! ({len(state['eaten'])}/4)\n{grid}")

    return state
