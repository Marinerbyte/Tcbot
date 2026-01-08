HTML_DASHBOARD = """
<!DOCTYPE html>
<html>
<head><title>TITAN v19.0 Dashboard</title></head>
<body>
<h1>TITAN ENGINE v19.0 - Status</h1>
<div id="status"></div>
<button onclick="connectBot()">Connect Bot</button>
<button onclick="disconnectBot()">Disconnect</button>
<pre id="logs"></pre>
<script>
async function updateStatus() {
    const res = await fetch('/status');
    const data = await res.json();
    document.getElementById('status').innerHTML = `
        WS: ${data.connected ? '🟢' : '🔴'} | DB: ${data.db_ok ? '🟢' : '🔴'} | 
        Sessions: ${data.sessions} | Plugins: ${data.plugins}
    `;
    document.getElementById('logs').textContent = data.logs.map(l => `[${l.time}] ${l.msg}`).join('\
');
}
setInterval(updateStatus, 2000);
updateStatus();

async function connectBot() {
    await fetch('/connect', {method:'POST', headers:{'Content-Type':'application/json'}, 
        body:JSON.stringify({u:'your_bot_user', p:'your_bot_pass', r:'room1,room2'})});
}
async function disconnectBot() {
    await fetch('/disconnect', {method:'POST'});
}
</script>
</body>
</html>
"""
