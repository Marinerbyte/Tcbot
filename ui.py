# --- FILE: ui.py ---

HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN OS // MASTER CONTROL</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=JetBrains+Mono&display=swap" rel="stylesheet">
    <style>
        :root { --neon: #00f3ff; --bg: #050505; --panel: #0f0f0f; --text: #e0e0e0; --err: #ff003c; --win: #00ff41; }
        * { box-sizing: border-box; }
        body { background: var(--bg); color: var(--text); font-family: 'JetBrains Mono', monospace; margin: 0; overflow: hidden; }
        
        .header { background: #111; padding: 15px 25px; border-bottom: 2px solid var(--neon); display: flex; justify-content: space-between; align-items: center; box-shadow: 0 0 20px rgba(0, 243, 255, 0.2); }
        .logo { font-family: 'Orbitron', sans-serif; font-size: 20px; font-weight: 700; color: var(--neon); letter-spacing: 2px; }
        
        .status-container { display: flex; gap: 20px; font-size: 12px; }
        .stat-item { background: #1a1a1a; padding: 5px 15px; border-radius: 20px; border: 1px solid #333; }
        .stat-item b { color: var(--neon); }

        .container { display: grid; grid-template-columns: 350px 1fr; height: calc(100vh - 60px); }
        
        .sidebar { background: var(--panel); border-right: 1px solid #222; padding: 25px; display: flex; flex-direction: column; gap: 20px; }
        .sidebar h3 { font-family: 'Orbitron', sans-serif; font-size: 14px; margin: 0; color: var(--neon); border-left: 3px solid var(--neon); padding-left: 10px; }
        
        .input-group { display: flex; flex-direction: column; gap: 5px; }
        label { font-size: 10px; color: #666; text-transform: uppercase; }
        input { background: #000; border: 1px solid #333; color: #fff; padding: 12px; border-radius: 4px; outline: none; transition: 0.3s; }
        input:focus { border-color: var(--neon); box-shadow: 0 0 10px rgba(0, 243, 255, 0.2); }
        
        button { background: var(--neon); color: #000; border: none; padding: 15px; font-family: 'Orbitron', sans-serif; font-weight: 700; cursor: pointer; border-radius: 4px; transition: 0.2s; }
        button:hover { background: #fff; transform: translateY(-2px); }
        .btn-stop { background: transparent; border: 1px solid var(--err); color: var(--err); margin-top: -10px; }
        .btn-stop:hover { background: var(--err); color: #fff; }

        .terminal { background: #000; padding: 0; display: flex; flex-direction: column; position: relative; }
        .term-header { background: #111; padding: 10px 20px; font-size: 11px; color: #555; display: flex; justify-content: space-between; border-bottom: 1px solid #222; }
        #logs { flex: 1; overflow-y: auto; padding: 20px; font-size: 13px; scroll-behavior: smooth; }
        
        .log-entry { margin-bottom: 8px; line-height: 1.5; border-left: 2px solid #222; padding-left: 12px; }
        .sys { color: #777; }
        .in { color: var(--neon); }
        .out { color: #ff00ff; }
        .err { color: var(--err); }
        .win { color: var(--win); background: rgba(0, 255, 65, 0.05); }

        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: #000; }
        ::-webkit-scrollbar-thumb { background: #222; }
        ::-webkit-scrollbar-thumb:hover { background: var(--neon); }
    </style>
</head>
<body>
    <div class="header">
        <div class="logo">TITAN_OS // CORE</div>
        <div class="status-container">
            <div class="stat-item">STATUS: <b id="stat">OFFLINE</b></div>
            <div class="stat-item">ACTIVE_SESSIONS: <b id="sessions">0</b></div>
            <div class="stat-item">PLUGINS: <b id="pg_count">0</b></div>
        </div>
    </div>

    <div class="container">
        <div class="sidebar">
            <h3>AUTHENTICATION</h3>
            <div class="input-group">
                <label>Access ID</label>
                <input type="text" id="u" placeholder="Bot Username">
            </div>
            <div class="input-group">
                <label>Security Key</label>
                <input type="password" id="p" placeholder="••••••••">
            </div>
            <div class="input-group">
                <label>Target Room(s)</label>
                <input type="text" id="r" placeholder="Room1, Room2">
            </div>
            <button onclick="connectBot()">INITIALIZE_SYSTEM</button>
            <button class="btn-stop" onclick="disconnectBot()">TERMINATE_ALL</button>
            
            <div style="margin-top:auto">
                <h3>SYSTEM_INFO</h3>
                <p style="font-size:11px; color:#444">
                    - Memory Cleanup: AUTO<br>
                    - Race Condition Lock: ACTIVE<br>
                    - Plug-and-Play: ENABLED
                </p>
            </div>
        </div>
        
        <div class="terminal">
            <div class="term-header">
                <span>>_ LIVE_SYSTEM_LOGS</span>
                <span id="timer">00:00:00</span>
            </div>
            <div id="logs">
                <div class="log-entry sys">System standing by... Ready for initialization.</div>
            </div>
        </div>
    </div>

    <script>
        function connectBot() {
            const u = document.getElementById('u').value, p = document.getElementById('p').value, r = document.getElementById('r').value;
            fetch('/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({u, p, r})
            });
        }
        function disconnectBot() { fetch('/disconnect', {method: 'POST'}); }

        setInterval(() => {
            fetch('/status').then(r => r.json()).then(data => {
                const stat = document.getElementById('stat');
                stat.innerText = data.connected ? "ONLINE" : "OFFLINE";
                stat.style.color = data.connected ? "var(--win)" : "var(--err)";
                document.getElementById('sessions').innerText = data.sessions;
                document.getElementById('pg_count').innerText = data.plugins;
                
                const logDiv = document.getElementById('logs');
                const isAtBottom = logDiv.scrollHeight - logDiv.clientHeight <= logDiv.scrollTop + 50;
                
                logDiv.innerHTML = data.logs.map(l => `<div class="log-entry ${l.type}"><b>[${l.time}]</b> ${l.msg}</div>`).join('');
                if (isAtBottom) logDiv.scrollTop = logDiv.scrollHeight;
            });
            document.getElementById('timer').innerText = new Date().toLocaleTimeString();
        }, 1000);
    </script>
</body>
</html>
"""
