<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN v19.0 Control Center</title>
    <style>
        :root {
            --bg-dark: #0f172a;
            --bg-panel: #1e293b;
            --accent-primary: #3b82f6; /* Blue */
            --accent-hover: #2563eb;
            --accent-danger: #ef4444; /* Red */
            --accent-success: #10b981; /* Green */
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --font-mono: 'Courier New', Courier, monospace;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* HEADER */
        header {
            background: var(--bg-panel);
            padding: 1rem 2rem;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }

        h1 { font-size: 1.5rem; letter-spacing: 1px; color: var(--accent-primary); text-transform: uppercase; }
        .status-indicators { display: flex; gap: 15px; font-size: 0.9rem; }
        .badge { padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
        .badge.on { background: rgba(16, 185, 129, 0.2); color: var(--accent-success); border: 1px solid var(--accent-success); }
        .badge.off { background: rgba(239, 68, 68, 0.2); color: var(--accent-danger); border: 1px solid var(--accent-danger); }

        /* MAIN GRID */
        .dashboard-grid {
            display: grid;
            grid-template-columns: 350px 1fr;
            grid-template-rows: 1fr 300px; /* Top section, Terminal section */
            gap: 1rem;
            padding: 1rem;
            height: calc(100vh - 70px);
        }

        /* CARD STYLES */
        .card {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
        }
        .card-header { font-size: 1.1rem; margin-bottom: 1rem; border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; font-weight: 600; color: var(--text-muted); }

        /* CONTROL PANEL (Left) */
        .control-panel { grid-row: 1; grid-column: 1; }
        
        .form-group { margin-bottom: 1rem; }
        label { display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.9rem; }
        input {
            width: 100%;
            padding: 10px;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-radius: 4px;
            color: var(--text-main);
            outline: none;
            transition: border 0.2s;
        }
        input:focus { border-color: var(--accent-primary); }

        .btn-group { display: flex; gap: 10px; margin-top: 1rem; }
        button {
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: bold;
            transition: opacity 0.2s;
        }
        .btn-login { background: var(--accent-primary); color: white; }
        .btn-logout { background: var(--bg-dark); border: 1px solid var(--accent-danger); color: var(--accent-danger); }
        button:hover { opacity: 0.9; }
        button:active { transform: scale(0.98); }

        /* PLUGINS LIST (Right) */
        .plugins-panel { grid-row: 1; grid-column: 2; overflow-y: auto; }
        
        .plugin-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; }
        .plugin-item {
            background: var(--bg-dark);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 10px;
            position: relative;
        }
        .plugin-item.failed { border-left: 3px solid var(--accent-danger); }
        .plugin-item.loaded { border-left: 3px solid var(--accent-success); }
        
        .p-name { font-weight: bold; display: block; margin-bottom: 5px; }
        .p-status { font-size: 0.8rem; display: flex; justify-content: space-between; }
        .p-detail { font-size: 0.75rem; color: var(--text-muted); margin-top: 5px; display: block; word-break: break-all;}

        /* TERMINAL (Bottom, Spans both cols) */
        .terminal-panel { grid-row: 2; grid-column: 1 /span 2; display: flex; flex-direction: column; }
        
        .terminal-window {
            flex: 1;
            background: #000;
            border: 1px solid var(--border);
            border-radius: 4px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
            padding: 10px;
            overflow-y: auto;
            color: #d4d4d4;
        }

        /* TERMINAL LOG COLORS */
        .log-entry { margin-bottom: 4px; border-bottom: 1px solid #1a1a1a; padding-bottom: 2px; }
        .log-time { color: #569cd6; margin-right: 10px; }
        .log-info { color: #d4d4d4; }
        .log-error { color: #f48771; font-weight: bold; }
        .log-payload { color: #ce9178; display: block; margin-top: 2px; padding-left: 20px; white-space: pre-wrap; }
        .tag { display: inline-block; padding: 0 4px; border-radius: 2px; margin-right: 5px; font-size: 0.75rem; }
        .tag.sys { background: #264f78; color: #fff; }
        .tag.bot { background: #6a9955; color: #fff; }

        /* SCROLLBAR */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-dark); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

    </style>
</head>
<body>

    <header>
        <h1>TITAN ENGINE <span style="font-size: 0.5em; vertical-align: super;">v19.0</span></h1>
        <div class="status-indicators" id="headerStatus">
            <span>WS: <span id="ws-status" class="badge off">DISCONNECTED</span></span>
            <span>DB: <span id="db-status" class="badge off">OFFLINE</span></span>
            <span>Active Sessions: <b id="session-count" style="color:var(--accent-primary)">0</b></span>
        </div>
    </header>

    <div class="dashboard-grid">
        
        <!-- LOGIN / CONTROLS -->
        <div class="card control-panel">
            <div class="card-header">Bot Configuration</div>
            
            <div class="form-group">
                <label for="botId">Bot ID / Username</label>
                <input type="text" id="botId" placeholder="Enter Bot ID">
            </div>

            <div class="form-group">
                <label for="botPass">Password</label>
                <input type="password" id="botPass" placeholder="••••••••">
            </div>

            <div class="form-group">
                <label for="botRooms">Target Rooms</label>
                <input type="text" id="botRooms" placeholder="room1, room2, room3">
                <small style="color:var(--text-muted); font-size: 0.75rem;">Separate multiple rooms with commas</small>
            </div>

            <div class="btn-group">
                <button class="btn-login" onclick="connectBot()">Connect Engine</button>
                <button class="btn-logout" onclick="disconnectBot()">Terminate</button>
            </div>
        </div>

        <!-- PLUGINS MONITOR -->
        <div class="card plugins-panel">
            <div class="card-header">
                Plugin Registry 
                <span style="float:right; font-size:0.8rem">
                    Loaded: <span id="pl-loaded" style="color:var(--accent-success)">0</span> | 
                    Failed: <span id="pl-failed" style="color:var(--accent-danger)">0</span>
                </span>
            </div>
            <div id="plugin-container" class="plugin-list">
                <div style="color: var(--text-muted); padding: 10px;">Waiting for connection...</div>
            </div>
        </div>

        <!-- DEBUG TERMINAL -->
        <div class="card terminal-panel">
            <div class="card-header">
                Payload Debug Terminal
                <button onclick="clearLogs()" style="float:right; background:transparent; border:1px solid var(--border); color:var(--text-muted); padding:2px 8px; font-size:0.7rem;">Clear Logs</button>
            </div>
            <div id="terminal" class="terminal-window">
                <div class="log-entry"><span class="log-time">[SYSTEM]</span> Ready to initialize Titan v19.0...</div>
            </div>
        </div>
    </div>

<script>
    // --- MOCK DATA GENERATOR (Only for UI Demo) ---
    // In real use, fetch this from your '/status' endpoint
    
    function logToTerminal(type, msg, payload = null) {
        const term = document.getElementById('terminal');
        const time = new Date().toLocaleTimeString('en-US', {hour12: false});
        
        let colorClass = 'log-info';
        let tagHtml = '<span class="tag sys">SYS</span>';

        if(type === 'error') {
            colorClass = 'log-error';
            tagHtml = '<span class="tag" style="background:#8b0000">ERR</span>';
        } else if (type === 'bot') {
            tagHtml = '<span class="tag bot">BOT</span>';
        }

        let html = `
            <div class="log-entry">
                <span class="log-time">[${time}]</span>
                ${tagHtml}
                <span class="${colorClass}">${msg}</span>
        `;

        if (payload) {
            // Pretty print JSON
            const prettyPayload = JSON.stringify(payload, null, 2);
            html += `<span class="log-payload">${prettyPayload}</span>`;
        }

        html += `</div>`;
        
        term.innerHTML += html;
        term.scrollTop = term.scrollHeight; // Auto scroll
    }

    function clearLogs() {
        document.getElementById('terminal').innerHTML = '';
    }

    function renderPlugins(plugins) {
        const container = document.getElementById('plugin-container');
        container.innerHTML = '';
        
        let loadedCount = 0;
        let failedCount = 0;

        plugins.forEach(p => {
            if(p.status === 'ok') loadedCount++; else failedCount++;
            
            const item = document.createElement('div');
            item.className = `plugin-item ${p.status === 'ok' ? 'loaded' : 'failed'}`;
            item.innerHTML = `
                <span class="p-name">${p.name}</span>
                <div class="p-status">
                    <span>${p.status === 'ok' ? 'Active' : 'Failed'}</span>
                    <span style="opacity:0.7">${p.ver}</span>
                </div>
                ${p.error ? `<span class="p-detail" style="color:#f48771">Err: ${p.error}</span>` : `<span class="p-detail">${p.desc}</span>`}
            `;
            container.appendChild(item);
        });

        document.getElementById('pl-loaded').innerText = loadedCount;
        document.getElementById('pl-failed').innerText = failedCount;
    }

    // --- MAIN LOGIC ---

    async function updateStatus() {
        try {
            const res = await fetch('/status');
            const data = await res.json();
            
            // Update Headers
            const wsBadge = document.getElementById('ws-status');
            wsBadge.className = data.connected ? 'badge on' : 'badge off';
            wsBadge.innerText = data.connected ? 'CONNECTED' : 'DISCONNECTED';

            const dbBadge = document.getElementById('db-status');
            dbBadge.className = data.db_ok ? 'badge on' : 'badge off';
            dbBadge.innerText = data.db_ok ? 'ONLINE' : 'OFFLINE';

            document.getElementById('session-count').innerText = data.sessions;

            // Render Plugins (Assuming data.plugins_list exists in response)
            if(data.plugins_list) {
                renderPlugins(data.plugins_list);
            }

            // Handle Logs
            if(data.logs && data.logs.length > 0) {
                // Clear old logs in UI if needed, or append new ones. 
                // For this demo, let's assume logs come as a fresh stream
                data.logs.forEach(l => {
                    logToTerminal(l.type, l.msg, l.payload);
                });
            }

        } catch (e) {
            // Silent catch for UI demo so it doesn't crash if backend is missing
            // console.log("Backend not connected");
        }
    }

    async function connectBot() {
        const u = document.getElementById('botId').value;
        const p = document.getElementById('botPass').value;
        const r = document.getElementById('botRooms').value;

        if(!u || !p || !r) {
            logToTerminal('error', 'Validation Failed: Missing ID, Password, or Rooms');
            return;
        }

        // Show loading in terminal
        logToTerminal('bot', `Initiating connection for user: ${u}`);
        logToTerminal('bot', `Targeting rooms: [${r}]`);

        try {
            await fetch('/connect', {
                method:'POST', 
                headers:{'Content-Type':'application/json'}, 
                body:JSON.stringify({u, p, r})
            });
            logToTerminal('sys', 'Connection request sent to Engine.');
        } catch(e) {
            logToTerminal('error', 'Network Error: Could not reach backend.');
        }
    }

    async function disconnectBot() {
        logToTerminal('sys', 'Sending terminate signal...');
        try {
            await fetch('/disconnect', {method:'POST'});
        } catch(e) {}
    }

    // --- DEMO SIMULATION (REMOVE THIS IN PRODUCTION) ---
    // This part simulates what happens when you click buttons so you can see the UI effects
    // without the Python backend running.
    setTimeout(() => {
        // Simulate loading plugins
        renderPlugins([
            {name: 'Auth Module', ver: 'v1.0', status: 'ok', desc: 'Authentication handler loaded'},
            {name: 'Chat Logger', ver: 'v2.1', status: 'ok', desc: 'Writing to DB...'},
            {name: 'Auto-Mod', ver: 'v0.9', status: 'err', error: 'Config file missing exception'},
            {name: 'Welcome Bot', ver: 'v1.1', status: 'ok', desc: 'Greeting enabled'}
        ]);
        
        // Simulate a log entry
        logToTerminal('sys', 'System initialized. Waiting for user input.');
    }, 1000);

    setInterval(updateStatus, 2000);

</script>
</body>
</html>
