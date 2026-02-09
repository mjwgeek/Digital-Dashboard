<?php
session_start();

/* ============================================================
   USER CONFIGURATION (REQUIRED)
   ============================================================ */

// Public hostname or IP where THIS dashboard is accessed
// Examples:
//   dashboard.example.com
//   radio.mydomain.net
//   192.168.1.50
$DASHBOARD_HOST = "your.domain.or.ip.here";

// Display info
$SYSOP_EMAIL = "admin@example.com";
$LOGO_FILE   = "logo.png";

/* ============================================================
   END USER CONFIGURATION
   ============================================================ */

// WebSocket port used by websocket_server
$WS_PORT = 8765;


// Sanitize host (strip protocol and port if pasted)
$DASHBOARD_HOST = preg_replace('#^https?://#', '', trim($DASHBOARD_HOST));
$DASHBOARD_HOST = preg_replace('/:\d+$/', '', $DASHBOARD_HOST);

if ($DASHBOARD_HOST === '') {
    $DASHBOARD_HOST = 'localhost';
}

$domain = $DASHBOARD_HOST;
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Digital Voice Dashboard</title>

<link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">

<style>
body { background:#121212; color:#fff; }
.navbar, footer { background:#333; }
.badge-success { background:green; }
.badge-m17 { background:#0d6efd; }
.badge-dmr { background:#fd7e14; }
.badge-p25 { background:#20c997; }
.badge-ysf { background:#a855f7; }
.nowrap { white-space:nowrap; }

.section-divider {
  height:1px;
  background:rgba(255,255,255,0.15);
  margin:24px 0;
}

.nav-row2{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:12px;
}

.nav-row2 .modules{ flex:1; font-size:.95em; opacity:.9; }
.nav-row2 .uptime{ white-space:nowrap; font-size:.95em; opacity:.9; }

@media (max-width:768px){
  .nav-row2{ flex-direction:column; align-items:flex-start; }
}
</style>
</head>

<body>

<nav class="navbar navbar-dark" style="display:block;">
  <div class="d-flex align-items-center">
    <span class="navbar-brand mb-0">
      <img src="<?= htmlspecialchars($LOGO_FILE) ?>" style="height:80px;margin-right:10px;">
      Digital Voice Dashboard
    </span>
  </div>

  <div class="nav-row2">
    <div class="navbar-text modules">
      M17 / DMR / P25 / YSF — Live Status
    </div>
    <div class="navbar-text uptime" id="uptime">Service uptime: Loading…</div>
  </div>
</nav>

<div class="container mt-4">

<h3>Clients Talking</h3>
<table class="table table-dark table-striped">
<thead>
<tr>
<th>#</th><th>Source</th><th>Callsign</th><th>Details</th>
<th>Status</th><th>Start</th><th>End</th>
</tr>
</thead>
<tbody id="clients-talking-body"></tbody>
</table>

<h3>Last Heard</h3>
<table class="table table-dark table-striped">
<thead>
<tr>
<th>#</th><th>Source</th><th>Callsign</th>
<th>Protocol</th><th>Target</th><th>Time</th>
</tr>
</thead>
<tbody id="last-heard-body"></tbody>
</table>

<h3>M17 Peers</h3>
<table class="table table-dark table-striped">
<thead>
<tr>
<th>#</th><th>Callsign</th><th>Module</th><th>IP</th><th>Time</th>
</tr>
</thead>
<tbody id="peers-body"></tbody>
</table>

<div class="section-divider"></div>

<h3>DMR (MMDVM_Bridge)</h3>
<table class="table table-dark table-striped">
<thead>
<tr>
<th>Master</th><th>Version</th><th>Last TX</th>
<th>From</th><th>To</th><th>Slot</th><th>CC</th><th>Meta</th>
</tr>
</thead>
<tbody id="mmdvm-body"><tr><td colspan="8">Waiting for data…</td></tr></tbody>
</table>

<h3>P25</h3>
<table class="table table-dark table-striped">
<thead>
<tr><th>Time</th><th>From</th><th>RID</th><th>TG</th></tr>
</thead>
<tbody id="p25-body"><tr><td colspan="4">Waiting for data…</td></tr></tbody>
</table>

<h3>YSF</h3>
<table class="table table-dark table-striped">
<thead>
<tr><th>Time</th><th>Callsign</th><th>DG-ID</th><th>Note</th><th>Event</th></tr>
</thead>
<tbody id="ysf-body"><tr><td colspan="5">Waiting for data…</td></tr></tbody>
</table>

</div>

<footer class="mt-4 text-white">
<div class="container">
<div class="row">
<div class="col-md-6">Sysop: <?= htmlspecialchars($SYSOP_EMAIL) ?></div>
<div class="col-md-6 text-right">Host: <?= htmlspecialchars($domain) ?></div>
</div>
</div>
</footer>

<script>
const WS_HOST = "<?= htmlspecialchars($domain, ENT_QUOTES) ?>";
const WS_PORT = <?= (int)$WS_PORT ?>;

let ws, uptimeSeconds = 0, uptimeTimer;

function badge(src){
  const s=(src||'').toUpperCase();
  if(s==='M17')return'<span class="badge badge-m17">M17</span>';
  if(s==='DMR')return'<span class="badge badge-dmr">DMR</span>';
  if(s==='P25')return'<span class="badge badge-p25">P25</span>';
  if(s==='YSF')return'<span class="badge badge-ysf">YSF</span>';
  return src||'-';
}

function startWS(){
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${WS_HOST}:${WS_PORT}`;
  ws = new WebSocket(url);

  ws.onopen = ()=>console.log("WS connected:",url);

  ws.onclose = ()=>{
    console.warn("WS closed, retrying...");
    setTimeout(startWS,3000);
  };

  ws.onmessage = e=>{
    const d = JSON.parse(e.data);

    if(d.uptime_seconds){
      uptimeSeconds = d.uptime_seconds;
      clearInterval(uptimeTimer);
      uptimeTimer=setInterval(()=>{
        uptimeSeconds++;
        document.getElementById('uptime').innerText =
          "Service uptime: " + uptimeSeconds + "s";
      },1000);
    }

    // Combined sections expected from server
    if(d.combined){
      renderTable('clients-talking-body', d.combined.clients_talking || [], 7, r=>`
        <tr><td>${r.idx}</td><td>${badge(r.source)}</td><td>${r.callsign}</td>
        <td>${r.module||'-'}</td><td>${r.status}</td>
        <td>${r.start_time}</td><td>${r.end_time}</td></tr>`);

      renderTable('last-heard-body', d.combined.last_heard || [], 6, r=>`
        <tr><td>${r.idx}</td><td>${badge(r.source)}</td><td>${r.callsign}</td>
        <td>${r.protocol}</td><td>${r.module_or_tg}</td>
        <td>${r.timestamp}</td></tr>`);

      renderTable('peers-body', d.combined.peers || [], 5, r=>`
        <tr><td>${r.idx}</td><td>${r.callsign}</td><td>${r.module}</td>
        <td>${r.ip_or_master}</td><td>${r.timestamp}</td></tr>`);
    }

    if(d.mmdvm){
      const t=d.mmdvm.last_tx||{};
      document.getElementById('mmdvm-body').innerHTML=`
      <tr><td>${d.mmdvm.master}</td><td>${d.mmdvm.version}</td>
      <td>${t.timestamp}</td><td>${t.src}</td><td>${t.dst}</td>
      <td>${t.slot}</td><td>${t.cc}</td><td>${t.metadata}</td></tr>`;
    }

    if(d.p25?.last_tx){
      const t=d.p25.last_tx;
      document.getElementById('p25-body').innerHTML=`
      <tr><td>${t.timestamp}</td><td>${t.at}</td>
      <td>${t.rid}</td><td>${t.tg}</td></tr>`;
    }

    if(d.ysf){
      const t=d.ysf.last_tx||{}, e2=d.ysf.last_event||{};
      document.getElementById('ysf-body').innerHTML=`
      <tr><td>${t.timestamp}</td><td>${t.callsign}</td>
      <td>${t.dgid}</td><td>${t.note}</td><td>${e2.msg}</td></tr>`;
    }
  };
}

function renderTable(id, rows, cols, fn){
  if(!rows.length){
    document.getElementById(id).innerHTML =
      `<tr><td colspan="${cols}">No data</td></tr>`;
    return;
  }
  document.getElementById(id).innerHTML =
    rows.map((r,i)=>fn({...r,idx:i+1})).join('');
}

startWS();
</script>

</body>
</html>
