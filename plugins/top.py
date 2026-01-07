# ======================================================
# FILE: plugins/top.py (TITAN v17.0 LEADERBOARD)
# ======================================================

TRIGGER = "!top"

def handle(user, msg, state, send_text, send_raw, db_set_score, db_get_score, db_get_top, global_data, add_log, send_image, db_update_stat, db_get_user_stats, db_get_game_top):
    
    msg_clean = msg.lower().strip()

    if msg_clean.startswith(TRIGGER):
        parts = msg_clean.split()
        
        # --- CASE 1: Game Specific Leaderboard (e.g., !top mines) ---
        if len(parts) > 1:
            game_name = parts[1].capitalize()
            # Engine tool 'db_get_game_top' ka istemal kiya
            leaderboard = db_get_game_top(game_name)
            title = f"🏆 --- TOP 10 {game_name.upper()} --- 🏆"
        
        # --- CASE 2: Global Leaderboard (Total Points) ---
        else:
            # Engine tool 'db_get_top' (Global) ka istemal kiya
            leaderboard = db_get_top()
            title = "🏆 --- GLOBAL TOP 10 --- 🏆"

        if not leaderboard:
            send_text(f"⚠️ @{user}, abhi is list mein koi nahi hai!")
            state["active"] = False
            return state

        # Leaderboard Formatting
        msg_out = f"{title}\n"
        rank = 1
        for p_name, p_score in leaderboard:
            # Medals for top 3
            medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
            msg_out += f"{medal} {p_name}: {p_score} pts\n"
            rank += 1
        
        # Chat mein leaderboard bhejo
        send_text(msg_out)
        
        # Dashboard log update
        add_log(f"Leaderboard requested by {user}")
        
        # Kaam khatam, dabba turant saaf
        state["active"] = False

    return state
