# ======================================================
# games/mines.py - FIXED WITH UPLOADER
# ======================================================

import random
import io
import string
import requests
from PIL import Image, ImageDraw, ImageFont
from requests_toolbelt.multipart.encoder import MultipartEncoder  # REQUIRED FOR UPLOAD

TRIGGER = "mines"

# --- CONFIG FROM TANVAR.PY ---
FILE_UPLOAD_URL = "https://cdn.talkinchat.com/post.php"
BOT_ID = "docker"  # Tanvar.py se liya gaya default ID

# --- HELPER FUNCTIONS ---

def gen_random_str(length):
    return ''.join(random.choice(string.ascii_lowercase + string.digits) for i in range(length))

def upload_image_to_server(img_buffer, room_name="american"):
    """
    Tanvar.py se inspire hokar banaya gaya upload function.
    Ye BytesIO image ko server par bhejta hai aur URL return karta hai.
    """
    try:
        # Buffer position reset
        img_buffer.seek(0)
        
        multipart_data = MultipartEncoder(
            fields={
                'file': ('mines_grid.png', img_buffer, 'image/png'),
                'jid': BOT_ID,
                'is_private': 'no',
                'room': room_name,
                'device_id': "android-" + gen_random_str(12)
            }
        )
        
        headers = {'Content-Type': multipart_data.content_type}
        response = requests.post(FILE_UPLOAD_URL, data=multipart_data, headers=headers)
        
        # Response check
        if response.status_code == 200 and "http" in response.text:
            return response.text.strip() # Returns the URL
        else:
            print(f"Upload Failed: {response.text}")
            return None
    except Exception as e:
        print(f"Upload Error: {e}")
        return None

# Cache font
CACHED_FONT = None
def get_font():
    global CACHED_FONT
    if CACHED_FONT: return CACHED_FONT
    try:
        url = "https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Bold.ttf"
        r = requests.get(url, timeout=5)
        CACHED_FONT = ImageFont.truetype(io.BytesIO(r.content), 60)
    except:
        CACHED_FONT = ImageFont.load_default()
    return CACHED_FONT

def generate_grid_image(bombs, eaten, reveal=False, exploded=None):
    cell_size = 120
    padding = 10
    grid_w = cell_size * 3 + padding * 4
    
    img = Image.new('RGB', (grid_w, grid_w), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    font = get_font()

    for row in range(3):
        for col in range(3):
            pos = row * 3 + col + 1
            x1 = padding + col * (cell_size + padding)
            y1 = padding + row * (cell_size + padding)
            x2 = x1 + cell_size
            y2 = y1 + cell_size
            
            fill = (30, 58, 138)
            outline = (96, 165, 250)
            text = "?"
            txt_col = "white"

            if reveal:
                if pos in bombs:
                    fill = (220, 38, 38)
                    text = "💣"
                    if pos == exploded: outline = "yellow"
                elif pos in eaten:
                    fill = (16, 185, 129)
                    text = str(pos)
                else:
                    fill = (71, 85, 105)
                    text = ""
            elif pos in eaten:
                fill = (16, 185, 129)
                text = str(pos)

            draw.rectangle([x1, y1, x2, y2], fill=fill, outline=outline, width=4)
            
            # Simple Text Drawing
            w, h = draw.textsize(text, font=font) if hasattr(draw, 'textsize') else (40, 40)
            draw.text(((x1 + x2 - w) / 2, (y1 + y2 - h) / 2 - 5), text, fill=txt_col, font=font)

    img_buffer = io.BytesIO()
    img.save(img_buffer, format='PNG')
    return img_buffer

# --- MAIN HANDLER ---

def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, 
           db_get_global_top, global_data, plugin_log, send_image, 
           db_update_stat, db_get_user_stats, db_get_game_top):
    
    # Try to find room name in state, otherwise default
    current_room = state.get("room_name", "american") 
    
    if "mines_data" not in state: state["mines_data"] = {}
    msg_clean = msg.lower().strip()
    
    # helper to send uploaded image
    def send_game_image(caption, buffer):
        url = upload_image_to_server(buffer, current_room)
        if url:
            send_image(caption, url) # Ab ye URL bhejega, jo sahi hai
        else:
            send_text("⚠️ Image Upload Failed. Server Error.")

    if msg_clean == TRIGGER:
        bombs = random.sample(range(1, 10), 2)
        state["mines_data"][user] = {"active": True, "bombs": bombs, "eaten": []}
        
        img = generate_grid_image(bombs, [])
        send_game_image(f"💣 Minesweeper: {user}\nType: !eat 1-9", img)
        return state
    
    elif msg_clean.startswith("!eat ") or msg_clean.startswith("eat "):
        user_game = state["mines_data"].get(user)
        if not user_game or not user_game["active"]:
            send_text("Start game with: !mines")
            return state
        
        try: num = int(msg_clean.split()[-1])
        except: return state

        if num < 1 or num > 9 or num in user_game["eaten"]: return state
        
        if num in user_game["bombs"]:
            user_game["active"] = False
            img = generate_grid_image(user_game["bombs"], user_game["eaten"], True, num)
            send_game_image(f"💥 BOOM! {user} Lost.", img)
            del state["mines_data"][user]
        else:
            user_game["eaten"].append(num)
            if len(user_game["eaten"]) >= 4:
                user_game["active"] = False
                try: db_set_score(user, 50)
                except: pass
                img = generate_grid_image(user_game["bombs"], user_game["eaten"], True)
                send_game_image(f"🎉 WINNER: {user} (+50)", img)
                del state["mines_data"][user]
            else:
                img = generate_grid_image(user_game["bombs"], user_game["eaten"])
                send_game_image(f"✅ Safe ({len(user_game['eaten'])}/4)", img)
        
        return state

    return state
