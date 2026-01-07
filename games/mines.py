# --- FILE: games/mines.py ---
import random

# Ye Trigger batayega ki kab game shuru karna hai
TRIGGER = "!mines"

def render_grid(bombs, eaten, reveal=False, exploded=None):
    """Grid banane ka logic (Standard Design)"""
    icons = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    txt = ""
    for i in range(1, 10):
        if reveal and i == exploded: txt += "💥 "
        elif reveal and i in bombs: txt += "💣 "
        elif i in eaten: txt += "🥔 "
        else: txt += icons[i-1] + " "
        
        if i % 3 == 0 and i != 9: txt += "\n"
    return txt

def handle(user, msg, state, send_func, db_func):
    """Main Game Handler - app.py ise call karega"""
    msg = msg.lower().strip()

    # 1. GAME START
    if msg == TRIGGER:
        state["active"] = True
        state["game_type"] = TRIGGER
        state["bombs"] = random.sample(range(1, 10), 2) # 2 Bombs
        state["eaten"] = []
        
        grid = render_grid(state["bombs"], [])
        send_func(f"💣 MINES STARTED! @{user}\nAvoid 2 Bombs! Eat 4 Chips to Win.\nType: !eat <1-9>\n\n{grid}")
        return state

    # 2. GAMEPLAY (Input)
    elif msg.startswith("!eat"):
        if not state.get("active"): return state
        
        try:
            num = int(msg.split()[1])
        except:
            return state # Invalid Input

        if num < 1 or num > 9 or num in state["eaten"]:
            return state # Galat number ya already kha liya

        # Check Bomb
        if num in state["bombs"]:
            state["active"] = False # Game Over
            grid = render_grid(state["bombs"], state["eaten"], reveal=True, exploded=num)
            send_func(f"💥 BOOM! @{user} hit a bomb!\n💀 GAME OVER.\n\n{grid}")
        else:
            state["eaten"].append(num)
            
            # Win Check (4 Chips)
            if len(state["eaten"]) == 4:
                state["active"] = False
                prize = 50 # 50 Points jeetne par
                db_func(user, prize) # Neon DB mein save hoga
                
                grid = render_grid(state["bombs"], state["eaten"], reveal=True)
                send_func(f"🎉 WINNER! @{user} ate 4 chips!\n💰 +{prize} Points added to your Neon Vault!\n\n{grid}")
            else:
                grid = render_grid(state["bombs"], state["eaten"])
                send_func(f"🥔 SAFE! ({len(state['eaten'])}/4)\n{grid}")

    return state # Dabba wapas app.py ko de diya
