# ======================================================
# games/mines.py - IMAGE-BASED MINESWEEPER v19 (FIXED)
# ======================================================
import random
import io
import requests
from PIL import Image, ImageDraw, ImageFont

TRIGGER = "mines"
CELL_SIZE = 120
GRID_SIZE = 3

def get_font(size=60):
    """Fallback font loader"""
    try:
        # Attempt to get a font from Google or system
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

def upload_to_catbox(img_buffer):
    """Uploads the generated buffer to a temporary URL for the engine to send"""
    try:
        img_buffer.seek(0)
        files = {'fileToUpload': ('mines.png', img_buffer, 'image/png')}
        data = {'reqtype': 'fileupload', 'userhash': ''}
        res = requests.post("https://catbox.moe/user/api.php", data=data, files=files, timeout=5)
        return res.text if res.status_code == 200 else None
    except:
        return None

def generate_grid_image(bombs, eaten, reveal=False, exploded=None):
    """Generates the 3x3 grid"""
    img = Image.new('RGB', (GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), color=(20, 30, 50))
    draw = ImageDraw.Draw(img)
    font = get_font(70)
    
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            pos = row * 3 + col + 1
            x, y = col * CELL_SIZE, row * CELL_SIZE
            
            # Cell Box
            draw.rectangle([x+5, y+5, x+CELL_SIZE-5, y+CELL_SIZE-5], outline="white", width=2)
            
            # Icon Logic
            if reveal and pos == exploded:
                icon, color = "💥", (255, 0, 0)
            elif reveal and pos in bombs:
                icon, color = "💣", (255, 255, 255)
            elif pos in eaten:
                icon, color = "✅", (0, 255, 0)
            else:
                icon, color = str(pos), (100, 150, 255)
            
            draw.text((x+35, y+25), icon, fill=color, font=font)
    
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf

def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, 
           db_get_global_top, global_data, plugin_log, send_image, 
           db_update_stat, db_get_user_stats, db_get_game_top):
    
    # Engine title requirement
    state["title"] = "🧹 Minesweeper"
    cmd = msg.lower().strip()

    # 1. START GAME
    if cmd == TRIGGER:
        state.update({
            "active": True,
            "game_type": TRIGGER,
            "bombs": random.sample(range(1, 10), 2),
            "eaten": []
        })
        
        buf = generate_grid_image(state["bombs"], state["eaten"])
        url = upload_to_catbox(buf)
        if url:
            send_image(f"@{user} Mines Started!\nPick 4 safe spots.\nUse: !eat 1-9", url)
        else:
            send_text("Error generating game board image!")
        return state

    # 2. GAMEPLAY
    if cmd.startswith("!eat ") or cmd.startswith("eat "):
        if not state.get("active"): return state
        
        try:
            num = int(cmd.split()[-1])
            if num < 1 or num > 9 or num in state["eaten"]: raise ValueError
        except:
            send_text(f"@{user} Invalid! Pick 1-9 (not already picked).")
            return state

        bombs = state["bombs"]
        eaten = state["eaten"]

        if num in bombs:
            # LOSE
            state["active"] = False
            buf = generate_grid_image(bombs, eaten, reveal=True, exploded=num)
            url = upload_to_catbox(buf)
            send_image(f"💥 BOOM! @{user} hit a bomb at {num}!", url)
            return None # Deletes session in engine
        
        else:
            # SAFE
            eaten.append(num)
            if len(eaten) >= 4:
                # WIN
                state["active"] = False
                prize = 50
                db_set_score(user, prize) #
                db_update_stat(user, "mines", prize) #
                
                buf = generate_grid_image(bombs, eaten, reveal=True)
                url = upload_to_catbox(buf)
                send_image(f"🎉 WINNER @{user}!\n+{prize} Points added.", url)
                return None
            else:
                # CONTINUE
                buf = generate_grid_image(bombs, eaten)
                url = upload_to_catbox(buf)
                send_image(f"✅ Safe! {len(eaten)}/4 found.\nKeep going!", url)
                return state

    return state
                
