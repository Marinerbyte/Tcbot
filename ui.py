# --- FILE: ui.py ---
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TITAN OS // CORE CONTROL</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #00f3ff; --bg: #050505; --panel: #0f0f0f; --err: #ff003c; --win: #00ff41; }
        body { background: var(--bg); color: #eee; font-family: 'JetBrains Mono', monospace; margin: 0; overflow: hidden; }
        .header { background: #111; padding: 15px 25px; border-bottom: 2px solid var(--neon); display: flex; justify-content: space-between; align-items: center; }
        .logo { font-family: 'Orbitron', sans-serif; color: var(--neon); letter-spacing: 2px; }
        .stat-bar { display: flex; gap: 20px; font-size: 12px; }
        .stat-bar b { color: var(--neon); }
        .main { display: grid; grid-template-columns: 350px 1fr; height: calc(100vh - 60px); }
        .sidebar { background: var(--panel); border-right: 1px solid #222; padding: 25px; display: flex; flex-direction: column; gap: 15px; }
        input, button { width: 100%; padding: 12px; margin-top: 5px; background: #000; border: 1px solid #333; color: #fff; border-radius: 4px; outline: none; }
        input:focus { border-color: var(--neon); }
        button { background: var(--neon); color: #000; font-family: 'Orbitron', sans-serif; font-weight: bold; cursor: pointer; border: none; }
        button:hover { background: #fff; }
        .terminal { background: #000; display: flex; flex-direction: column; }
        #logs { flex: 1; overflow-y: auto; padding: 20px; font-size: 13px; border-top: 1px solid #222; }
        .log-entry { margin-bottom: 5px; border-left: 2px solid #222; padding-left: 10px; }
        .in { color: var(--neon); } .out { color: #ff00ff; } .err { color: var(--err); } .sys { color: #666; } .win { color: var(--win); background: rgba(0,255,65,0.05); }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">TITAN_OS // MASTER_CORE</div>
        <div class="stat-bar">
            <span>STATUS: <b id="stat">OFFLINE</b></span>
            <span>ACTIVE: <b id="sessions">0</b></span>
            <span>LOADED: <b id="pgs">0</b></span>
        </div>
    </div>
    <div class="main">
        <div class="sidebar">
            <label>BOT ID</label><input type="text" id="u">
            <label>PASSWORD</label><input type="password" id="p">
            <label>ROOM(S) (Comma separated)</label><input type="text" id="r" placeholder="Room1, Room2">
            <button onclick="start()">INITIALIZE</button>
            <button onclick="stop()" style="background:var(--err); color:#fff; margin-top:10px;">TERMINATE</button>
        </div>
        <div class="terminal">
            <div style="padding:10px 20px; font-size:11px; color:#444;">>_ SYSTEM_LOG_STREAM</div>
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
                logDiv.innerHTML = d.logs.map(l => `<div class="log-entry ${l.type}">[${l.time}] ${l.msg}</div>`).join('');
                logDiv.scrollTop = logDiv.scrollHeight;
            });
        }, 1000);
    </script>
</body>
</html>
"""
