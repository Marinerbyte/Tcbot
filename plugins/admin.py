# --- FILE: plugins/admin.py ---
import json
import time

TRIGGER = "!join" # Iska trigger !join rakhte hain

def handle(user, msg, state, send_func, db_func):
    # ADMIN CHECK: Yahan apna asli username likho
    ADMIN_NAME = "Tera_Username" 
    
    if user != ADMIN_NAME:
        return state # Agar aap nahi ho, to ignore

    # 1. Naya Room Join karna: !join RoomName
    if msg.startswith("!join "):
        try:
            new_room = msg.split(" ")[1]
            # Hum seedha app.py ke websocket ko packet bhej rahe hain
            # Note: handle function ko websocket access dene ke liye 
            # humne app.py mein pehle hi logic set kiya hai
            send_func(f"🚀 Joining naya room: {new_room}...")
            # Ye command app.py ke on_message mein handle ho jayegi agar hum wahan rasta rakhein
        except:
            send_func("❌ Format: !join RoomName")

    # 2. Room chhodna: !leave
    elif msg == "!leave":
        send_func("👋 Bye bye! Main ye room chhod raha hoon.")
        # Leave logic...

    state["active"] = False # Plugin hai, kaam khatam
    return state
