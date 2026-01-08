import random
import io
from PIL import Image, ImageDraw, ImageFont
import requests
from urllib.parse import urlparse

TRIGGER = "!mines"

# Emoji mapping 1–9
GRID_ICONS = {
    1: "1️⃣",
    2: "2️⃣",
    3: "3️⃣",
    4: "4️⃣",
    5: "5️⃣",
    6: "6️⃣",
    7: "7️⃣",
    8: "8️⃣",
    9: "9️⃣",
}

# Google fonts URL (fallback if download fail)
DEFAULT_FONT_URL = "https://fonts.gstatic.com/s/roboto/v30/KFOmCnqEu92Fr1Mu4mxKKTU1Kg.woff2"

CELL_SIZE = 120
GRID_SIZE = 3  # 3x3


def download_font(url: str, fallback_size: int = 48):
    """Download TTF/OTF from URL or return system default font."""
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        return ImageFont.truetype(io.BytesIO(resp.content), fallback_size)
    except Exception:
        try:
            # System font fallbacks
            return ImageFont.truetype("arial.ttf", fallback_size)
        except Exception:
            return ImageFont.load_default()


def generate_grid_image(
    bombs,
    eaten,
    reveal: bool = False,
    exploded: int | None = None,
    custom_bg_url: str | None = None,
):
    """
    Generate 3x3 mines grid as PNG BytesIO.
    bombs  : list[int] indexes 1–9
    eaten  : list[int]
    reveal : show bombs if True
    exploded : which cell exploded
    """
    img = Image.new(
        "RGB", (GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE), color=(20, 30, 50)
    )
    draw = ImageDraw.Draw(img)

    font = download_font(DEFAULT_FONT_URL, 80)

    # Optional background image
    if custom_bg_url:
        try:
            r = requests.get(custom_bg_url, timeout=5)
            bg = Image.open(io.BytesIO(r.content)).convert("RGB")
            bg = bg.resize((GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE))
            img.paste(bg, (0, 0))
        except Exception:
            pass

    # Draw cells
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            pos = row * 3 + col + 1  # 1–9
            x = col * CELL_SIZE
            y = row * CELL_SIZE

            # cell border
            draw.rectangle(
                (x + 5, y + 5, x + CELL_SIZE - 5, y + CELL_SIZE - 5),
                outline="white",
                width=3,
            )

            # decide icon & color
            if reveal and exploded is not None and pos == exploded:
                icon = "💥"
                color = (255, 80, 0)
            elif reveal and pos in bombs:
                icon = "💣"
                color = (255, 0, 0)
            elif pos in eaten:
                icon = "🥔"
                color = (0, 255, 0)
            else:
                icon = GRID_ICONS.get(pos, str(pos))
                color = (120, 170, 255)

            # draw text (centre-ish)
            draw.text(
                (x + 25, y + 25),
                icon,
                fill=(0, 0, 0),
                font=font,
            )
            draw.text(
                (x + 22, y + 22),
                icon,
                fill=color,
                font=font,
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def handle(
    user,
    msg,
    state,
    send_text,
    send_raw,
    db_set_score,
    db_get_score,
    db_get_global_top,
    global_data,
    plugin_log,
    send_image,
    db_update_stat,
    db_get_user_stats,
    db_get_game_top,
):
    """
    Main plugin handler for image Mines game.
    Compatible with 14‑arg plugin API.
    """

    state.setdefault("title", "Minesweeper")
    msg_clean = msg.lower().strip()

    # START GAME
    if msg_clean == TRIGGER:
        if state.get("active") and "bombs" in state and "eaten" in state:
            send_text(f"@{user}, game already active! ' !eat 1-9 ' bolo.")
            return state

        state.update(
            {
                "active": True,
                "game_type": TRIGGER,
                "bombs": random.sample(range(1, 10), 2),
                "eaten": [],
                "safe_count": 0,
            }
        )
        plugin_log(f"[Mines] started by {user}")

        grid_img = generate_grid_image(state["bombs"], state["eaten"])
        send_image(
            f"💣 MINES started for @{user}!
Goal: eat 4 safe chips.
Idle >90s = reset.
Use: !eat 1-9",
            grid_img,
        )
        return state

    # GAMEPLAY
    if msg_clean.startswith("!eat") or msg_clean.startswith("eat "):
        if not state.get("active") or "bombs" not in state:
            send_text("Pehle !mines bolo, phir !eat 1-9.")
            return state

        parts = msg_clean.split()
        if len(parts) < 2:
            send_text("Number bhi do, e.g. '!eat 5'.")
            return state

        try:
            num = int(parts[1])
        except ValueError:
            send_text("Sirf number 1-9 allow, e.g. '!eat 5'.")
            return state

        if num < 1 or num > 9 or num in state["eaten"]:
            send_text("Invalid! 1-9 me se koi naya dabba choose karo.")
            return state

        # Bomb hit
        if num in state["bombs"]:
            state["active"] = False
            grid_img = generate_grid_image(
                state["bombs"],
                state["eaten"],
                reveal=True,
                exploded=num,
            )
            send_image(f"💥 BOOM! @{user} hit a bomb! Game Over.", grid_img)
            plugin_log(f"[Mines] {user} hit a bomb.")
            return state

        # Safe
        state["eaten"].append(num)
        state["safe_count"] = len(state["eaten"])

        # Win condition
        if len(state["eaten"]) >= 4:
            state["active"] = False
            prize = 50

            db_set_score(user, prize)
            db_update_stat(user, "Mines", prize)

            grid_img = generate_grid_image(
                state["bombs"],
                state["eaten"],
                reveal=True,
            )
            send_image(
                f"🎉 WINNER @{user}!
+{prize} Global balance & Mines stats updated.",
                grid_img,
            )
            plugin_log(f"[Mines] WIN {user} +{prize}")
            return state

        # Still playing
        grid_img = generate_grid_image(state["bombs"], state["eaten"])
        send_image(
            f"🥔 SAFE! ({len(state['eaten'])}/4 chips eaten). Continue with !eat 1-9.",
            grid_img,
        )
        return state

    # No change
    return state
