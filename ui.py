# --- ui.py ---
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TITAN OS // MASTER CORE</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #00f3ff; --bg: #050505; --panel: #0f0f0f; --err: #ff003c; --win: #00ff41; }
        body { background: var(--bg); color: #eee; font-family: 'JetBrains Mono', monospace; margin: 0; overflow: hidden; }
        .header { background: #111; padding: 15px 25px; border-bottom: 2px solid var(--neon); display: flex; justify-content: space-between; align-items: center; box-shadow: 0 0 20px rgba(0,243,255,0.2); }
        .logo { font-family: 'Orbitron', sans-serif; color: var(--neon); letter-spacing: 2px; font-size: 1.2rem; }
        .stat-bar { display: flex; gap: 20px; font-size: 11px; }
        .stat-bar b { color: var(--neon); }
        .main { display: grid; grid-template-columns: 350px 1fr; height: calc(100vh - 60px); }
        .sidebar { background: var(--panel); border-right: 1px solid #222; padding: 25px; display: flex; flex-direction: column; gap: 15px; }
        input, button { width: 100%; padding: 12px; margin-top: 5px; background: #000; border: 1px solid #333; color: #fff; border-radius: 4px; outline: none; transition: 0.3s; }
        input:focus { border-color: var(--neon); box-shadow: 0 0 10px rgba(0,243,255,0.1); }
        button { background: var(--neon); color: #000; font-family: 'Orbitron', sans-serif; font-weight: bold; cursor: pointer; border: none; text-transform: uppercase; }
        button:hover { background: #fff; transform: translateY(-2px); }
        .terminal { background: #000; display: flex; flex-direction: column; position: relative; }
        #logs { flex: 1; overflow-y: auto; padding: 20px; font-size: 12px; border-top: 1px solid #222; scroll-behavior: smooth; }
        .log-entry { margin-bottom: 6px; border-left: 2px solid #222; padding-left: 12px; line-height: 1.4; }
        .in { color: var(--neon); } .out { color: #ff00ff; } .err { color: var(--err); } .sys { color: #666; } .win { color: var(--win); background: rgba(0,255,65,0.05); }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-thumb { background: var(--neon); }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">TITAN_OS // CORE_RECOVERY_v6</div>
        <div class="stat-bar">
            <span>STATUS: <b id="stat">OFFLINE</b></span>
            <span>SESSIONS: <b id="sessions">0</b></span>
            <span>PLUGINS: <b id="pgs">0</b></span>
        </div>
    </div>
    <div class="main">
        <div class="sidebar">
            <h3 style="color:var(--neon); font-size:12px; margin:0 0 10px 0;">SYSTEM AUTHENTICATION</h3>
            <label style="font-size:10px; color:#555;">BOT ID</label><input type="text" id="u">
            <label style="font-size:10px; color:#555;">PASSWORD</label><input type="password" id="p">
            <label style="font-size:10px; color:#555;">ROOM(S) (Comma separated)</label><input type="text" id="r" placeholder="Room1, Room2">
            <button onclick="start()">INITIATE BOOT</button>
            <button onclick="stop()" style="background:transparent; border:1px solid var(--err); color:var(--err); margin-top:10px;">TERMINATE</button>
            <div style="margin-top:auto; font-size:10px; color:#333;">
                STATE_PERSISTENCE: ENABLED<br>MEMORY_CLEANUP: ACTIVE
            </div>
        </div>
        <div class="terminal">
            <div style="padding:10px 20px; font-size:10px; color:#444; background:#0a0a0a;">>_ SYSTEM_LOG_STREAM</div>
            <div id="logs"></div>
        </div>
    </div>
    <script>
        function start() {
            const u=document.getElementById('u').value, p=document.getElementById('p').value, r=document.getElementById('r').value;
            fetch('/connect', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({u,p,r})});
        }
        function stop() { fetch('/disconnect', {method:'POST'}); }
        setInterval(() => {
            fetch('/status').then(r=>r.json()).then(d => {
                document.getElementById('stat').innerText = d.connected ? "ONLINE" : "OFFLINE";
                document.getElementById('stat').style.color = d.connected ? "var(--win)" : "var(--err)";
                document.getElementById('sessions').innerText = d.sessions;
                document.getElementById('pgs').innerText = d.plugins;
                const logDiv = document.getElementById('logs');
                const isAtBottom = logDiv.scrollHeight - logDiv.clientHeight <= logDiv.scrollTop + 50;
                logDiv.innerHTML = d.logs.map(l => `<div class="log-entry ${l.type}">[${l.time}] ${l.msg}</div>`).join('');
                if(isAtBottom) logDiv.scrollTop = logDiv.scrollHeight;
            });
        }, 1000);
    </script>
</body>
</html>
"""
