# --- FILE: games/mines.py ---
import random

# 1. TRIGGER
TRIGGER = "!mines"

def render_grid(bombs, eaten, reveal=False, exploded=None):
    """Grid banane ka logic"""
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    txt = ""
    for i in range(1, 10):
        if reveal and i == exploded: txt += "💥 "
        elif reveal and i in bombs: txt += "💣 "
        elif i in eaten: txt += "🥔 "
        else: txt += icons[i-1] + " "
        if i % 3 == 0 and i != 9: txt += "\n"
    return txt

# 2. HANDLE FUNCTION (Isme 10 Arguments hain - Bilkul skip mat karna)
def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, db_get_top, global_data, add_log):
    
    msg_clean = msg.lower().strip()

    # --- A. GAME START LOGIC ---
    if msg_clean == TRIGGER:
        state.update({
            "active": True, 
            "game_type": TRIGGER,
            "bombs": random.sample(range(1, 10), 2), 
            "eaten": []
        })
        
        # Dashboard par log bhejo
        add_log(f"Game Started: {user}")
        
        grid = render_grid(state["bombs"], [])
        # Note: yahan sirf text bhejna hai, room ID app.py sambhal lega
        send_text(f"💣 MINES STARTED! @{user}\nGoal: Eat 4 Chips 🥔 | Avoid 2 Bombs 💣\nType: !eat <1-9>\n\n{grid}")
        return state

    # --- B. GAMEPLAY LOGIC (!eat) ---
    elif msg_clean.startswith("!eat"):
        if not state.get("active"): return state
        
        try:
            num = int(msg_clean.split()[1])
        except:
            return state

        if num < 1 or num > 9 or num in state["eaten"]:
            return state

        if num in state["bombs"]:
            state["active"] = False 
            grid = render_grid(state["bombs"], state["eaten"], reveal=True, exploded=num)
            send_text(f"💥 BOOM! @{user} hit a bomb at #{num}!\n💀 GAME OVER.\n\n{grid}")
            add_log(f"Game Over: {user} lost.")
        else:
            state["eaten"].append(num)
            if len(state["eaten"]) == 4:
                state["active"] = False
                prize = 50
                db_set_score(user, prize) # Neon DB Update
                grid = render_grid(state["bombs"], state["eaten"], reveal=True)
                send_text(f"🎉 WINNER! @{user} ate 4 chips!\n💰 +{prize} Points added!\n\n{grid}")
                add_log(f"Victory: {user} won!")
            else:
                grid = render_grid(state["bombs"], state["eaten"])
                send_text(f"🥔 SAFE! ({len(state['eaten'])}/4)\n{grid}")

    return state
