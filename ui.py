HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TITAN ENGINE v19.0 - Command Center</title>
    <style>
        :root {
            --bg-dark: #0b0f19;
            --bg-panel: #151b2b;
            --primary: #3b82f6;
            --primary-dim: rgba(59, 130, 246, 0.1);
            --success: #10b981;
            --danger: #ef4444;
            --text-main: #e2e8f0;
            --text-muted: #64748b;
            --border: #1e293b;
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
        .header {
            height: 60px;
            background: var(--bg-panel);
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            padding: 0 20px;
            justify-content: space-between;
        }
        .header h1 { font-size: 1.2rem; letter-spacing: 1px; color: var(--primary); text-transform: uppercase; }
        .status-bar { display: flex; gap: 15px; font-size: 0.85rem; font-family: var(--font-mono); }
        .indicator { padding: 4px 8px; border-radius: 4px; border: 1px solid transparent; }
        .indicator.on { background: rgba(16, 185, 129, 0.1); color: var(--success); border-color: var(--success); }
        .indicator.off { background: rgba(239, 68, 68, 0.1); color: var(--danger); border-color: var(--danger); }

        /* LAYOUT GRID */
        .main-container {
            flex: 1;
            display: grid;
            grid-template-columns: 320px 1fr; /* Sidebar | Plugins */
            grid-template-rows: 1fr 300px;    /* Top Area | Terminal */
            gap: 10px;
            padding: 10px;
            height: calc(100vh - 60px);
        }

        /* PANELS */
        .panel {
            background: var(--bg-panel);
            border: 1px solid var(--border);
            border-radius: 6px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .panel-header {
            padding: 10px 15px;
            background: rgba(0,0,0,0.2);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            font-size: 0.9rem;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
        }

        /* LOGIN BOX (Top Left) */
        .auth-box { grid-column: 1; grid-row: 1; padding: 15px; }
        
        .input-group { margin-bottom: 15px; }
        label { display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 5px; }
        input {
            width: 100%;
            background: var(--bg-dark);
            border: 1px solid var(--border);
            padding: 10px;
            color: var(--text-main);
            border-radius: 4px;
            outline: none;
            transition: 0.2s;
        }
        input:focus { border-color: var(--primary); }
        .hint { font-size: 0.7rem; color: var(--text-muted); margin-top: 3px; }

        .btn-row { display: flex; gap: 10px; margin-top: 20px; }
        button {
            flex: 1;
            padding: 10px;
            border: none;
            border-radius: 4px;
            font-weight: bold;
            cursor: pointer;
            transition: 0.2s;
        }
        .btn-connect { background: var(--primary); color: white; }
        .btn-connect:hover { background: #2563eb; }
        .btn-dc { background: transparent; border: 1px solid var(--danger); color: var(--danger); }
        .btn-dc:hover { background: rgba(239, 68, 68, 0.1); }

        /* PLUGINS (Top Right) */
        .plugins-box { grid-column: 2; grid-row: 1; }
        .plugins-content { padding: 15px; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
        
        .plugin-card {
            background: var(--bg-dark);
            border: 1px solid var(--border);
            padding: 10px;
            border-radius: 4px;
            position: relative;
        }
        .plugin-card.loaded { border-left: 3px solid var(--success); }
        .plugin-card.failed { border-left: 3px solid var(--danger); }
        
        .p-name { font-weight: bold; font-size: 0.9rem; }
        .p-stat { font-size: 0.75rem; float: right; text-transform: uppercase; }
        .p-desc { font-size: 0.75rem; color: var(--text-muted); margin-top: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .p-err { color: var(--danger); font-size: 0.75rem; margin-top: 5px; }

        /* TERMINAL (Bottom, Full Width) */
        .terminal-box { grid-column: 1 / -1; grid-row: 2; }
        .terminal {
            flex: 1;
            background: #000;
            padding: 10px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            overflow-y: auto;
            color: #ccc;
        }
        
        .log-line { margin-bottom: 4px; border-bottom: 1px solid #111; padding-bottom: 2px; }
        .ts { color: #555; margin-right: 10px; }
        .type-sys { color: var(--primary); }
        .type-err { color: var(--danger); font-weight: bold; }
        .type-bot { color: var(--success); }
        .payload {
            display: block;
            margin-left: 20px;
            color: #d69e2e; /* Yellowish for JSON */
            white-space: pre-wrap;
            font-size: 0.75rem;
        }

        /* SCROLLBAR */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: var(--bg-dark); }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
    </style>
</head>
<body>

    <div class="header">
        <h1>TITAN v19.0</h1>
        <div class="status-bar">
            <span id="ws-badge" class="indicator off">WS: DISCONNECTED</span>
            <span id="db-badge" class="indicator off">DB: OFFLINE</span>
            <span>Sessions: <b id="sess-count" style="color:white">0</b></span>
        </div>
    </div>

    <div class="main-container">
        
        <!-- LOGIN PANEL -->
        <div class="panel auth-box">
            <div class="panel-header" style="margin: -15px -15px 15px -15px;">AUTHENTICATION</div>
            
            <div class="input-group">
                <label>USER ID</label>
                <input type="text" id="uid" placeholder="Enter Bot ID">
            </div>

            <div class="input-group">
                <label>PASSWORD</label>
                <input type="password" id="upass" placeholder="••••••••">
            </div>

            <div class="input-group">
                <label>TARGET ROOMS</label>
                <input type="text" id="urooms" placeholder="room1, room2">
                <div class="hint">Comma separated (e.g. Chat1, MusicRoom)</div>
            </div>

            <div class="btn-row">
                <button class="btn-connect" onclick="connectBot()">LOGIN</button>
                <button class="btn-dc" onclick="disconnectBot()">LOGOUT</button>
            </div>
        </div>

        <!-- PLUGINS PANEL -->
        <div class="panel plugins-box">
            <div class="panel-header">
                ACTIVE PLUGINS
                <span style="font-size:0.75rem">
                    OK: <span id="cnt-ok" style="color:var(--success)">0</span> | 
                    FAIL: <span id="cnt-fail" style="color:var(--danger)">0</span>
                </span>
            </div>
            <div id="plugin-list" class="plugins-content">
                <div style="color:var(--text-muted)">Waiting for engine...</div>
            </div>
        </div>

        <!-- DEBUG TERMINAL -->
        <div class="panel terminal-box">
            <div class="panel-header">
                PAYLOAD DEBUG TERMINAL
                <button onclick="document.getElementById('term').innerHTML=''" style="background:none; border:none; color:var(--text-muted); cursor:pointer;">Clear</button>
            </div>
            <div id="term" class="terminal"></div>
        </div>

    </div>

<script>
    // UTILS
    function log(type, msg, payload=null) {
        const term = document.getElementById('term');
        const ts = new Date().toLocaleTimeString('en-GB');
        let html = `<div class="log-line"><span class="ts">[${ts}]</span>`;
        
        if(type==='error') html += `<span class="type-err">ERR:</span> ${msg}`;
        else if(type==='bot') html += `<span class="type-bot">BOT:</span> ${msg}`;
        else html += `<span class="type-sys">SYS:</span> ${msg}`;

        if(payload) {
            html += `<span class="payload">${typeof payload === 'object' ? JSON.stringify(payload, null, 2) : payload}</span>`;
        }
        
        html += `</div>`;
        term.innerHTML += html;
        term.scrollTop = term.scrollHeight;
    }

    // API CALLS
    async function updateStatus() {
        try {
            const res = await fetch('/status');
            const data = await res.json();
            
            // Header Stats
            const ws = document.getElementById('ws-badge');
            ws.className = `indicator ${data.connected ? 'on' : 'off'}`;
            ws.innerText = data.connected ? 'WS: CONNECTED' : 'WS: DISCONNECTED';
            
            const db = document.getElementById('db-badge');
            db.className = `indicator ${data.db_ok ? 'on' : 'off'}`;
            db.innerText = data.db_ok ? 'DB: ONLINE' : 'DB: OFFLINE';

            document.getElementById('sess-count').innerText = data.sessions || 0;

            // Plugins Logic
            if(data.plugins_list) renderPlugins(data.plugins_list);

            // Logs Logic
            if(data.logs && data.logs.length) {
                data.logs.forEach(l => log(l.type, l.msg, l.payload));
            }

        } catch (e) {
            // console.error("Poll failed");
        }
    }

    function renderPlugins(list) {
        const container = document.getElementById('plugin-list');
        container.innerHTML = '';
        let ok = 0, fail = 0;

        list.forEach(p => {
            if(p.status === 'ok') ok++; else fail++;
            const isErr = p.status !== 'ok';
            
            const div = document.createElement('div');
            div.className = `plugin-card ${isErr ? 'failed' : 'loaded'}`;
            div.innerHTML = `
                <div class="p-name">${p.name} <span class="p-stat" style="color:${isErr ? 'var(--danger)' : 'var(--success)'}">${p.status}</span></div>
                ${isErr ? `<div class="p-err">${p.error}</div>` : `<div class="p-desc">${p.desc || 'Loaded successfully'}</div>`}
            `;
            container.appendChild(div);
        });

        document.getElementById('cnt-ok').innerText = ok;
        document.getElementById('cnt-fail').innerText = fail;
    }

    async function connectBot() {
        const u = document.getElementById('uid').value;
        const p = document.getElementById('upass').value;
        const r = document.getElementById('urooms').value;

        if(!u || !p) return log('error', 'Username and Password required');

        log('sys', 'Sending Login Request...');
        try {
            await fetch('/connect', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ u, p, r })
            });
        } catch(e) { log('error', 'Fetch failed'); }
    }

    async function disconnectBot() {
        log('sys', 'Disconnecting...');
        await fetch('/disconnect', {method:'POST'});
    }

    // Start Polling
    setInterval(updateStatus, 2000);
    updateStatus();
    log('sys', 'Titan Dashboard v19.0 Initialized.');

</script>
</body>
</html>
"""
