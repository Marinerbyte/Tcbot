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
import base64
import os

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
    
    # Generate minefield logic
    grid = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    bomb_positions = []
    
    # Place bombs
    for _ in range(bombs):
        while True:
            x, y = random.randint(0, GRID_SIZE-1), random.randint(0, GRID_SIZE-1)
            if (x, y) not in bomb_positions:
                bomb_positions.append((x, y))
                grid[x][y] = 9
                break
    
    # Calculate numbers
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            if grid[i][j] == 9:
                continue
            count = 0
            for di in [-1, 0, 1]:
                for dj in [-1, 0, 1]:
                    ni, nj = i + di, j + dj
                    if 0 <= ni < GRID_SIZE and 0 <= nj < GRID_SIZE and grid[ni][nj] == 9:
                        count += 1
            grid[i][j] = count
    
    # Draw cells
    for i in range(GRID_SIZE):
        for j in range(GRID_SIZE):
            x = j * CELL_SIZE
            y = i * CELL_SIZE
            
            # Cell border
            draw.rectangle([x, y, x+CELL_SIZE, y+CELL_SIZE], outline=(100, 150, 200), width=4)
            
            # Content
            if reveal or (i, j) in eaten:
                icon = GRID_ICONS[grid[i][j]]
                # Center text
                bbox = draw.textbbox((0, 0), icon, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                draw.text((x + (CELL_SIZE - text_width)/2, y + (CELL_SIZE - text_height)/2), 
                         icon, fill=(255, 255, 255), font=font)
            
            # Explosion effect
            if exploded and (i, j) == exploded:
                draw.ellipse([x+20, y+20, x+CELL_SIZE-20, y+CELL_SIZE-20], 
                           fill=(255, 100, 0), outline=(255, 200, 0), width=8)
    
    # Save to bytes
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    
    return img_bytes.getvalue()

def handle_mines(chat, user, message):
    """Main minesweeper handler"""
    
    # Parse command
    parts = message.split()
    if len(parts) < 2:
        chat.send_message("🧹 **Minesweeper**: `mines start 3` | `mines [pos]` (1-9)")
        return
    
    cmd = parts[1].lower()
    
    # Game state (use your bot's storage)
    game_state = get_game_state(chat.id) or {}
    
    if cmd == "start":
        bombs = int(parts[2]) if len(parts) > 2 else 3
        if bombs < 1 or bombs > 6:
            chat.send_message("❌ Bombs: 1-6")
            return
            
        game_state = {
            "bombs": bombs,
            "eaten": [],
            "grid": None,
            "stage": "playing"
        }
        set_game_state(chat.id, game_state)
        
        grid_img = generate_grid_image(bombs, [])
        chat.send_image("🧹 Minesweeper Started!", grid_img)
        plugin_log("Mines START {} {}".format(user, bombs))
        
    elif cmd.isdigit() and len(cmd) == 1:
        pos = int(cmd) - 1
        if pos < 0 or pos > 8:
            chat.send_message("❌ Position 1-9")
            return
            
        if game_state.get("stage") != "playing":
            chat.send_message("❌ Game over! `mines start 3`")
            return
        
        row, col = divmod(pos, 3)
        eaten_pos = (row, col)
        
        if eaten_pos in game_state["eaten"]:
            chat.send_message("✅ Already clicked!")
            return
        
        game_state["eaten"].append(eaten_pos)
        
        # Check win/lose
        total_cells = GRID_SIZE * GRID_SIZE
        safe_cells = total_cells - game_state["bombs"]
        
        if len(game_state["eaten"]) >= safe_cells:
            # WIN
            prize = game_state["bombs"] * 10
            chat.send_message("🎉 **WINNER!** +{} coins".format(prize))
            plugin_log("Mines WIN {} +{}".format(user, prize))
            del game_state[chat.id]
            return
        
        grid_img = generate_grid_image(game_state["bombs"], game_state["eaten"])
        chat.send_image("Click 1-9:", grid_img)
        
        # Check bomb
        if (row, col) in [(r,c) for r in range(3) for c in range(3) if generate_grid_image(game_state["bombs"], game_state["eaten"], reveal=True)[row][col] == 9]:
            exploded_img = generate_grid_image(game_state["bombs"], game_state["eaten"], 
                                             reveal=True, exploded=(row, col))
            chat.send_image("💥 **BOOM! GAME OVER**", exploded_img)
            plugin_log("Mines LOSE {}".format(user))
            del game_state[chat.id]
            return
        
        set_game_state(chat.id, game_state)
        
    else:
        chat.send_message("❌ `mines start 3` ya `mines 5`")

# Register handler
register_handler(TRIGGER, handle_mines)
