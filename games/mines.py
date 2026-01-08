# ======================================================
# games/mines.py - IMAGE-BASED MINESWEEPER v19
# ======================================================
# Auto-generates 3x3 grid images with stylish fonts!
# ======================================================

import random
import io
from PIL import Image, ImageDraw, ImageFont
import requests
from urllib.parse import urlparse

TRIGGER = "mines"

# Pre-defined emoji/number mapping for grid
GRID_ICONS = {
    0: "🔵", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "💣"
}

# Default stylish font URL (Google Fonts - auto-download)
DEFAULT_FONT_URL = "https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Mu4mxKKTU1Kg.woff2"
CELL_SIZE = 120
GRID_SIZE = 3

def download_font(url, fallback_size=48):
    """Auto-download stylish font or use system fallback"""
    try:
        response = requests.get(url, timeout=5)
        font = ImageFont.truetype(io.BytesIO(response.content), fallback_size)
        return font
    except:
        # Fallback to system fonts
        try:
            return ImageFont.truetype("arial.ttf", fallback_size) or ImageFont.load_default()
        except:
            return ImageFont.load_default()

def generate_grid_image(bombs, eaten, reveal=False, exploded=None, custom_bg_url=None):
    """Generate 3x3 Minesweeper grid image with numbers"""
    
    # Create blank image (540x540 for 3x3 grid)
    img = Image.new('RGB', (GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), color=(20, 30, 50))
    draw = ImageDraw.Draw(img)
    
    # Stylish font (auto-download)
    font = download_font(DEFAULT_FONT_URL, 80)
    
    # Optional: Custom background image
    if custom_bg_url:
        try:
            bg_response = requests.get(custom_bg_url, timeout=5)
            bg_img = Image.open(io.BytesIO(bg_response.content)).resize((GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE))
            img.paste(bg_img, (0, 0))
        except:
            pass  # Use default dark bg
    
    # Draw 3x3 grid
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            pos = row * 3 + col + 1  # 1-9 positions
            
            x = col * CELL_SIZE + 20
            y = row * CELL_SIZE + 20
            
            # Cell border
            draw.rectangle([x-10, y-10, x+CELL_SIZE-10, y+CELL_SIZE-10], 
                          outline="white", width=3)
            
            # Logic for what to show
            if reveal and pos in bombs:
                icon = "💣"
                color = (255, 0, 0)
            elif reveal and pos == exploded:
                icon = "💥"
                color = (255, 100, 0)
            elif pos in eaten:
                icon = str(pos)
                color = (0, 255, 0)
            else:
                icon = "🔵"
                color = (100, 150, 255)
            
            # Draw icon/number with shadow
            draw.text((x+10, y+10), icon, fill=(0,0,0), font=font)  # Shadow
            draw.text((x+8, y+8), icon, fill=color, font=font)     # Main text
    
    # Save to BytesIO for sending
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer

def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, 
           db_get_global_top, global_data, plugin_log, send_image, 
           db_update_stat, db_get_user_stats, db_get_game_top):
    
    state["title"] = "🧹 Minesweeper"  # Auto-notification ke liye
    
    msg_clean = msg.lower().strip()
    
    # START GAME
    if msg_clean == TRIGGER:
        if state.get("active") and "bombs" in state and "eaten" in state:
            send_text(f"{user}, game already active! Say !eat 1-9")
            return state
        
        # New game: 2 random bombs in 9 cells
        state.update({
            "active": True,
            "game_type": TRIGGER,
            "bombs": random.sample(range(1, 10), 2),
            "eaten": [],
            "safe_count": 0
        })
        
        plugin_log(f"Mines started by {user}")
        
        # Send first image
        grid_img = generate_grid_image(state["bombs"], state["eaten"])
        send_image("🧹 Minesweeper Started!
Eat 4 safe chips (90s idle reset)
!eat 1-9", grid_img)
        
        return state
    
    # GAMEPLAY: !eat 1-9
    elif msg_clean.startswith("!eat ") or msg_clean.startswith("eat "):
        if not state.get("active") or "bombs" not in state:
            send_text("Start with !mines")
            return state
        
        try:
            num = int(msg_clean.split()[-1])
            if num < 1 or num > 9 or num in state["eaten"]:
                send_text("Invalid! Say !eat 1-9 (not eaten)")
                return state
        except:
            send_text("Number only! !eat 5")
            return state
        
        # Check bomb hit
        if num in state["bombs"]:
            state["active"] = False
            grid_img = generate_grid_image(state["bombs"], state["eaten"], reveal=True, exploded=num)
            send_image(f"💥 BOOM! {user} hit bomb!
Game Over!", grid_img)
            plugin_log(f"Mines {user} hit bomb")
        else:
            state["eaten"].append(num)
            state["safe_count"] += 1
            
            # WIN CONDITION (4 safe chips)
            if len(state["eaten"]) == 4:
                state["active"] = False
                prize = 50
                db_set_score(user, prize)
                db_update_stat(user, "mines", prize)
                
                grid_img = generate_grid_image(state["bombs"], state["eaten"], reveal=True)
                send_image(f"🎉 WINNER {user}!
+{prize} Global Points
Mines Record Updated!", grid_img)
                plugin_log(f"Mines WIN {user} +{prize}")
            else:
                # Continue game
                grid_img = generate_grid_image(state["bombs"], state["eaten"])
                send_image(f"✅ Safe! {len(state['eaten'])}/4 chips eaten
!eat 1-9", grid_img)
        
        return state
    
    return state
