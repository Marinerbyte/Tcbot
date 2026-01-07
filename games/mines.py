# ======================================================
# FILE: games/mines.py (COMPATIBLE WITH TITAN ENGINE v16.0)
# ======================================================
import random

# 1. TRIGGER: Is shabd se game start hoga
TRIGGER = "!mines"

def render_grid(bombs, eaten, reveal=False, exploded=None):
    """Grid banane ka logic (Emojis used for better UI)"""
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    txt = ""
    for i in range(1, 10):
        # Agar bomb phata hai (Game Over)
        if reveal and i == exploded:
            txt += "💥 "
        # Agar bomb dikhana hai (Reveal at end)
        elif reveal and i in bombs:
            txt += "💣 "
        # Agar aaloo/chip kha liya hai
        elif i in eaten:
            txt += "🥔 "
        # Normal number icon
        else:
            txt += icons[i-1] + " "
        
        # Har 3 number ke baad nayi line
        if i % 3 == 0 and i != 9:
            txt += "\n"
    return txt

# 2. HANDLE FUNCTION: v16.0 Engine exactly ye 11 arguments bhejta hai
def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, db_get_top, global_data, add_log, send_image):
    
    # Message ko saaf karo
    msg_clean = msg.lower().strip()

    # --- BLOCK A: GAME START LOGIC ---
    if msg_clean == TRIGGER:
        # Check: Kya user pehle se game mein hai?
        if state.get("active") == True:
            send_text(f"⚠️ @{user}, aapka game pehle se chalu hai! !eat <number> likho.")
            return state

        # Naya game setup karo
        state.update({
            "active": True, 
            "game_type": TRIGGER,
            "bombs": random.sample(range(1, 10), 2), # 2 Random bombs
            "eaten": []
        })
        
        # Dashboard par message bhejo
        add_log(f"Mines game started by {user}")
        
        grid = render_grid(state["bombs"], [])
        send_text(f"💣 MINES STARTED! @{user}\nGoal: Eat 4 Chips 🥔 | Avoid 2 Bombs 💣\nIdle 90s = Auto Reset\nType: !eat <1-9>\n\n{grid}")
        return state

    # --- BLOCK B: GAMEPLAY LOGIC (!eat) ---
    elif msg_clean.startswith("!eat"):
        # Check: Kya game active hai?
        if not state.get("active"): 
            return state
        
        # Number nikalo message se
        try:
            num = int(msg_clean.split()[1])
        except:
            return state # Invalid input, ignore karo

        # Range check aur Duplicate check
        if num < 1 or num > 9 or num in state["eaten"]:
            return state

        # Check: Kya bomb par pair rakh diya?
        if num in state["bombs"]:
            state["active"] = False # Game Over, dabba saaf hoga
            grid = render_grid(state["bombs"], state["eaten"], reveal=True, exploded=num)
            send_text(f"💥 BOOM! @{user} hit a bomb at #{num}!\n💀 GAME OVER.\n\n{grid}")
            add_log(f"Game Over: {user} hit a bomb.")
            
        else:
            # Safe Move
            state["eaten"].append(num)
            
            # WIN CONDITION: 4 safe chips kha liye
            if len(state["eaten"]) == 4:
                state["active"] = False # Winner, dabba saaf
                prize = 50
                
                # Neon DB mein points save karo
                db_set_score(user, prize)
                
                grid = render_grid(state["bombs"], state["eaten"], reveal=True)
                send_text(f"🎉 WINNER! @{user} ate 4 chips!\n💰 +{prize} Points added to your balance!\n\n{grid}")
                add_log(f"Victory: {user} won {prize} pts")
            else:
                # Game chalta rahega
                grid = render_grid(state["bombs"], state["eaten"])
                send_text(f"🥔 SAFE! ({len(state['eaten'])}/4)\n{grid}")

    # Hamesha updated state wapas karo app.py ko
    return state
