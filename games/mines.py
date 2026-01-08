# ======================================================
# games/mines.py - FIXED & OPTIMIZED
# ======================================================

import random
import io
from PIL import Image, ImageDraw, ImageFont
import requests

TRIGGER = "mines"

# Cache font to avoid downloading every time
CACHED_FONT = None

def get_font():
    """Download font once and keep in memory"""
    global CACHED_FONT
    if CACHED_FONT:
        return CACHED_FONT
    
    try:
        # Using a reliable bold font URL
        url = "https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Bold.ttf"
        response = requests.get(url, timeout=5)
        CACHED_FONT = ImageFont.truetype(io.BytesIO(response.content), 60)
    except:
        # Fallback to default if download fails
        CACHED_FONT = ImageFont.load_default()
    
    return CACHED_FONT

def generate_grid_image(bombs, eaten, reveal=False, exploded=None):
    """Generates grid using Shapes instead of Emojis for 100% compatibility"""
    
    cell_size = 120
    padding = 10
    grid_w = cell_size * 3 + padding * 4
    
    # Create dark background image
    img = Image.new('RGB', (grid_w, grid_w), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    font = get_font()

    for row in range(3):
        for col in range(3):
            pos = row * 3 + col + 1
            
            # Calculate coordinates
            x1 = padding + col * (cell_size + padding)
            y1 = padding + row * (cell_size + padding)
            x2 = x1 + cell_size
            y2 = y1 + cell_size
            
            # DEFAULT STATE (Not clicked)
            fill_color = (30, 58, 138)  # Dark Blue
            outline_color = (96, 165, 250) # Light Blue
            text = "?"
            text_color = (255, 255, 255)

            # LOGIC: What to show?
            if reveal:
                if pos in bombs:
                    fill_color = (220, 38, 38) # Red (Bomb)
                    text = "💣" # Will show as text or generic shape depending on font
                    # Or draw an X if emoji fails
                    if pos == exploded:
                        outline_color = (255, 255, 0) # Yellow highlight
                elif pos in eaten:
                    fill_color = (16, 185, 129) # Green (Safe)
                    text = str(pos)
                else:
                    fill_color = (71, 85, 105) # Gray (Unclicked safe)
                    text = ""
            
            elif pos in eaten:
                fill_color = (16, 185, 129) # Green
                text = str(pos)
            
            # DRAW CELL (Rectangle)
            draw.rectangle([x1, y1, x2, y2], fill=fill_color, outline=outline_color, width=4)
            
            # DRAW TEXT/ICON
            if pos in bombs and reveal:
                # Manually draw a Bomb Circle because Font Emojis fail
                draw.ellipse([x1+30, y1+30, x2-30, y2-30], fill=(0,0,0))
                draw.line([x1+40, y1+40, x2-40, y2-40], fill="white", width=3)
                draw.line([x1+40, y2-40, x2-40, y1+40], fill="white", width=3)
            else:
                # Center text logic
                try:
                    bbox = draw.textbbox((0, 0), text, font=font)
                    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    draw.text(((x1 + x2 - w) / 2, (y1 + y2 - h) / 2 - 10), text, fill=text_color, font=font)
                except:
                    # Fallback for very old Pillow versions
                    draw.text((x1+40, y1+40), text, fill=text_color)

    # Save to buffer
    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    img_buffer.name = "mines_grid.png"  # <--- VERY IMPORTANT FOR SOME BOTS
    
    return img_buffer

def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, 
           db_get_global_top, global_data, plugin_log, send_image, 
           db_update_stat, db_get_user_stats, db_get_game_top):
    
    # Ensure state keys exist
    if "mines_data" not in state:
        state["mines_data"] = {}

    msg_clean = msg.lower().strip()
    
    # --- START GAME ---
    if msg_clean == TRIGGER:
        # Reset game for user
        bombs = random.sample(range(1, 10), 2)
        state["mines_data"][user] = {
            "active": True,
            "bombs": bombs,
            "eaten": []
        }
        
        plugin_log(f"Mines started by {user}")
        
        try:
            grid_img = generate_grid_image(bombs, [])
            send_image("💣 **Minesweeper Started!**\nEat 4 safe spots to win.\n\nType: `!eat 1-9`", grid_img)
        except Exception as e:
            send_text(f"Error generating image: {e}")
            print(f"Mines Error: {e}")
        
        return state
    
    # --- PLAY GAME ---
    elif msg_clean.startswith("!eat ") or msg_clean.startswith("eat "):
        
        # Check if user has active game
        user_game = state["mines_data"].get(user)
        
        if not user_game or not user_game["active"]:
            send_text(f"{user}, you don't have an active game. Say '!mines'")
            return state
        
        try:
            num = int(msg_clean.split()[-1])
        except:
            send_text("Please use a number: !eat 5")
            return state

        if num < 1 or num > 9:
            send_text("Number must be between 1-9")
            return state

        if num in user_game["eaten"]:
            send_text("Already eaten! Pick another.")
            return state
        
        # HIT BOMB
        if num in user_game["bombs"]:
            user_game["active"] = False
            try:
                grid_img = generate_grid_image(user_game["bombs"], user_game["eaten"], reveal=True, exploded=num)
                send_image(f"💥 **BOOM!** {user} hit a bomb!\nGame Over.", grid_img)
            except Exception as e:
                send_text("Game Over (Image failed)")
            
            del state["mines_data"][user] # Cleanup
            
        # SAFE EAT
        else:
            user_game["eaten"].append(num)
            
            # WIN CONDITION (Total 9 cells - 2 bombs = 7 safe cells. Winning at 4 is generous)
            if len(user_game["eaten"]) >= 4:
                user_game["active"] = False
                prize = 50
                
                # DB Updates (Safely handled)
                try:
                    db_set_score(user, prize)
                    db_update_stat(user, "mines", prize)
                except:
                    pass

                grid_img = generate_grid_image(user_game["bombs"], user_game["eaten"], reveal=True)
                send_image(f"🎉 **WINNER!**\n{user} found 4 safe spots!\nWon: ${prize}", grid_img)
                del state["mines_data"][user]
            else:
                # Continue
                grid_img = generate_grid_image(user_game["bombs"], user_game["eaten"])
                send_image(f"✅ Safe! ({len(user_game['eaten'])}/4)\nNext move: `!eat 1-9`", grid_img)
        
        return state

    return state
