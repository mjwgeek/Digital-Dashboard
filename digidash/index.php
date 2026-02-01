<?php
session_start();

// General Information
$sysopEmail = "admin@wg5eek.com";  // Customize
$logo = "AR Radio Heads Logo.png"; // Path to your logo

// Get external IP
$externalIp = @file_get_contents("https://api.ipify.org");
if ($externalIp === false) {
    $externalIp = "Unavailable";
}

// Attempt reverse DNS
$domain = ($externalIp !== "Unavailable") ? @gethostbyaddr($externalIp) : false;

// Fallback domain
if (!$domain || strpos($domain, 'isp') !== false) {
    $domain = "wg5eek.com";
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Digital Dashboard</title>
  <link href="https://stackpath.bootstrapcdn.com/bootstrap/4.5.2/css/bootstrap.min.css" rel="stylesheet">

  <style>
    body { background-color:#121212; color:#fff; }
    .navbar, footer { background-color:#333; }
    .badge-success { background-color: green; }
    .badge-m17 { background: #0d6efd; }
    .badge-dmr { background: #fd7e14; }
    .badge-p25 { background: #20c997; } /* teal-ish */
    .badge-ysf { background: #a855f7; } /* purple-ish */
    .nowrap { white-space: nowrap; }
    .module-description { margin-right: 20px; }
    .section-divider { height: 1px; background: rgba(255,255,255,0.12); margin: 24px 0; }

    /* --- 2-row navbar layout --- */
    .nav-row2{
      display:flex;
      justify-content:space-between;
      align-items:flex-start;
      gap: 12px;
      width:100%;
    }
    .nav-row2 .modules{
      flex: 1 1 auto;
      min-width: 0;
      white-space: normal;
      font-size: 0.95em;
      opacity: 0.9;
    }
    .nav-row2 .uptime{
      flex: 0 0 auto;
      white-space: nowrap;
      text-align: right;
      font-size: 0.95em;
      opacity: 0.9;
    }
    @media (max-width: 768px){
      .nav-row2{
        flex-direction: column;
        align-items: flex-start;
      }
      .nav-row2 .uptime{
        white-space: normal;
        text-align: left;
      }
      .module-description{
        margin-right: 12px;
        display: inline-block;
      }
    }
  </style>
</head>

<body>

<nav class="navbar navbar-dark" style="display:block;">
  <!-- Row 1: Title -->
  <div class="d-flex align-items-center">
    <a class="navbar-brand mb-0" href="#" style="white-space: normal;">
      <img src="<?= $logo ?>" alt="Logo" style="height: 80px; width: auto; margin-right: 10px;">
      Arkansas Radio Heads Dashboard
    </a>
  </div>

  <!-- Row 2: Sub-title + Modules + Uptime -->
  <div class="nav-row2">
    <div class="navbar-text modules">
      <div>M17-2MC + DMR(TGIF) TG 75309 + P25 TG 24033 + YSF 24033</div>
      <div>
        M17 Module:
        <span class="module-description">D = 2 Meter Crew - Arkansas Radio Heads</span>
      </div>
    </div>

    <div class="navbar-text uptime" id="uptime">Service uptime: Loading...</div>
  </div>
</nav>


<div class="container mt-4">

  <!-- Clients Talking -->
  <h3>Clients Talking (M17 / DMR / P25 / YSF)</h3>
  <table class="table table-dark table-striped">
    <thead>
      <tr>
        <th>#</th>
        <th>Source</th>
        <th>Callsign</th>
        <th>Module / Slot / TG / DGID</th>
        <th>Status</th>
        <th>Start Time</th>
        <th>End Time</th>
      </tr>
    </thead>
    <tbody id="clients-talking-body"></tbody>
  </table>

  <!-- Last Heard -->
  <h3>Last Heard Stations (M17 / DMR / P25 / YSF)</h3>
  <table class="table table-dark table-striped">
    <thead>
      <tr>
        <th>#</th>
        <th>Source</th>
        <th>Callsign</th>
        <th>Protocol / Mode</th>
        <th>Module / TG / DGID</th>
        <th>Timestamp</th>
      </tr>
    </thead>
    <tbody id="last-heard-body"></tbody>
  </table>

  <!-- Peers -->
  <h3>Peers (M17)</h3>
  <table class="table table-dark table-striped">
    <thead>
      <tr>
        <th>#</th>
        <th>Source</th>
        <th>Callsign</th>
        <th>Module</th>
        <th>IP</th>
        <th>Timestamp</th>
      </tr>
    </thead>
    <tbody id="peers-body"></tbody>
  </table>

  <div class="section-divider"></div>

  <!-- DMR / MMDVM_Bridge -->
  <h3>DMR (MMDVM_Bridge)</h3>
  <table class="table table-dark table-striped">
    <thead>
      <tr>
        <th>Master</th>
        <th>Version</th>
        <th>Last TX (when)</th>
        <th>From (src)</th>
        <th>To (dst/TG)</th>
        <th>Slot</th>
        <th>CC</th>
        <th>Metadata</th>
      </tr>
    </thead>
    <tbody id="mmdvm-body">
      <tr><td colspan="8">Loading...</td></tr>
    </tbody>
  </table>

  <!-- P25 -->
  <h3>P25 (P25Reflector)</h3>
  <table class="table table-dark table-striped">
    <thead>
      <tr>
        <th>Last TX (when)</th>
        <th>From (Callsign)</th>
        <th>RID</th>
        <th>To (TG)</th>
      </tr>
    </thead>
    <tbody id="p25-body">
      <tr><td colspan="4">Loading...</td></tr>
    </tbody>
  </table>

  <!-- YSF -->
  <h3>YSF (MMDVM_BridgeYSF)</h3>
  <table class="table table-dark table-striped">
    <thead>
      <tr>
        <th>Last TX (when)</th>
        <th>From (Callsign)</th>
        <th>DG-ID</th>
        <th>Note</th>
        <th>Last Event</th>
      </tr>
    </thead>
    <tbody id="ysf-body">
      <tr><td colspan="5">Loading...</td></tr>
    </tbody>
  </table>

</div>

<footer class="text-white mt-4">
  <div class="container">
    <div class="row">
      <div class="col-md-6">Sysop Email: <?= $sysopEmail ?></div>
      <div class="col-md-6 text-right">Domain: <?= $domain ?> | External IP: <?= $externalIp ?></div>
    </div>
  </div>
</footer>

<script>
let ws;
let uptimeSeconds = 0;
let intervalId;

function formatUptime(seconds) {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  let s = '';
  if (days > 0) s += `${days} day${days !== 1 ? 's' : ''}`;
  if (hours > 0) s += `${s ? ', ' : ''}${hours} hour${hours !== 1 ? 's' : ''}`;
  if (minutes > 0) s += `${s ? ', ' : ''}${minutes} minute${minutes !== 1 ? 's' : ''}`;
  s += `${s ? ', ' : ''}${secs} second${secs !== 1 ? 's' : ''}`;
  return s;
}

function sourceBadge(src) {
  const s = (src || '').toUpperCase();
  if (s === 'DMR') return '<span class="badge badge-dmr">DMR</span>';
  if (s === 'M17') return '<span class="badge badge-m17">M17</span>';
  if (s === 'P25') return '<span class="badge badge-p25">P25</span>';
  if (s === 'YSF') return '<span class="badge badge-ysf">YSF</span>';
  return `<span class="badge badge-secondary">${src || '-'}</span>`;
}

function isTalkingStatus(st) {
  const x = (st || '').toLowerCase();
  return (x === 'talking' || x === 'on' || x === 'tx on');
}

/* Best-effort ordering by "Jan 28 16:51:27" */
function timeKey(ts) {
  if (!ts) return '';
  return ts;
}

function sourcePriority(src) {
  const s = (src || '').toUpperCase();
  if (s === 'YSF') return 4;
  if (s === 'P25') return 3;
  if (s === 'DMR') return 2;
  if (s === 'M17') return 1;
  return 0;
}

function getCombinedClients(data) {
  if (data.combined && Array.isArray(data.combined.clients_talking)) return data.combined.clients_talking;

  // Legacy fallback: M17 clients object -> array
  const out = [];
  if (data.clients) {
    Object.keys(data.clients).forEach((callsign) => {
      const info = data.clients[callsign] || {};
      out.push({
        source: 'M17',
        callsign: callsign,
        module: info.module || '-',
        status: info.status || '-',
        start_time: info.start_time || '-',
        end_time: info.end_time || '-',
      });
    });
  }
  return out;
}

function getCombinedLastHeard(data) {
  if (data.combined && Array.isArray(data.combined.last_heard)) return data.combined.last_heard;

  const out = [];
  if (Array.isArray(data.last_heard)) {
    data.last_heard.forEach((e) => {
      out.push({
        source: e.source || 'M17',
        callsign: e.callsign || '-',
        protocol: e.protocol || '-',
        module_or_tg: e.module || '-',
        timestamp: e.timestamp || '-'
      });
    });
  }
  return out;
}

function getCombinedPeers(data) {
  if (data.combined && Array.isArray(data.combined.peers)) return data.combined.peers;

  const out = [];
  if (Array.isArray(data.peers)) {
    data.peers.forEach((p) => {
      out.push({
        source: 'M17',
        callsign: p.callsign || '-',
        module: p.module || '-',
        ip_or_master: p.ip || '-',
        timestamp: p.timestamp || '-'
      });
    });
  }
  return out;
}

function startWebSocket() {
  ws = new WebSocket('wss://wg5eek.com:8765');

  ws.onopen = function() {
    console.log('WebSocket connection opened');
  };

  ws.onmessage = function(event) {
    const data = JSON.parse(event.data);

    // Uptime
    if (data.uptime_seconds) {
      uptimeSeconds = data.uptime_seconds;

      if (intervalId) clearInterval(intervalId);

      intervalId = setInterval(() => {
        uptimeSeconds += 1;
        document.getElementById('uptime').textContent = 'Service uptime: ' + formatUptime(uptimeSeconds);
      }, 1000);
    }

    // ---- Clients Talking (Combined) ----
    const clientsRaw = getCombinedClients(data);

    const clients = clientsRaw.slice().sort((a, b) => {
      const aTalk = isTalkingStatus(a.status) ? 1 : 0;
      const bTalk = isTalkingStatus(b.status) ? 1 : 0;
      if (aTalk !== bTalk) return bTalk - aTalk;

      const aT = timeKey(a.start_time || '');
      const bT = timeKey(b.start_time || '');
      if (aT < bT) return 1;
      if (aT > bT) return -1;

      const ap = sourcePriority(a.source);
      const bp = sourcePriority(b.source);
      if (ap !== bp) return bp - ap;

      return (a.callsign || '').localeCompare(b.callsign || '');
    });

    let clientsHTML = '';
    if (clients.length > 0) {
      clients.forEach((c, idx) => {
        const statusCell = isTalkingStatus(c.status)
          ? '<span class="badge badge-success">Talking</span>'
          : (c.status || 'Not talking');

        clientsHTML += `<tr>
          <td>${idx + 1}</td>
          <td class="nowrap">${sourceBadge(c.source)}</td>
          <td>${c.callsign || '-'}</td>
          <td>${c.module || '-'}</td>
          <td>${statusCell}</td>
          <td>${c.start_time || '-'}</td>
          <td>${c.end_time || '-'}</td>
        </tr>`;
      });
    } else {
      clientsHTML = '<tr><td colspan="7">No active talkers</td></tr>';
    }
    document.getElementById('clients-talking-body').innerHTML = clientsHTML;

    // ---- Last Heard (Combined) ----
    const lastHeard = getCombinedLastHeard(data);
    let lastHeardHTML = '';
    if (lastHeard.length > 0) {
      lastHeard.forEach((e, idx) => {
        lastHeardHTML += `<tr>
          <td>${idx + 1}</td>
          <td class="nowrap">${sourceBadge(e.source)}</td>
          <td>${e.callsign || '-'}</td>
          <td>${e.protocol || '-'}</td>
          <td>${e.module_or_tg || '-'}</td>
          <td>${e.timestamp || '-'}</td>
        </tr>`;
      });
    } else {
      lastHeardHTML = '<tr><td colspan="6">No recent traffic</td></tr>';
    }
    document.getElementById('last-heard-body').innerHTML = lastHeardHTML;

    // ---- Peers (M17-only from server) ----
    const peers = getCombinedPeers(data);
    let peersHTML = '';
    if (peers.length > 0) {
      peers.forEach((p, idx) => {
        peersHTML += `<tr>
          <td>${idx + 1}</td>
          <td class="nowrap">${sourceBadge(p.source)}</td>
          <td>${p.callsign || '-'}</td>
          <td>${p.module || '-'}</td>
          <td>${p.ip_or_master || '-'}</td>
          <td>${p.timestamp || '-'}</td>
        </tr>`;
      });
    } else {
      peersHTML = '<tr><td colspan="6">No peers</td></tr>';
    }
    document.getElementById('peers-body').innerHTML = peersHTML;

    // ---- MMDVM / DMR Status (NO TX STATE) ----
    let mmdvmHTML = '';
    if (data.mmdvm) {
      const tx = data.mmdvm.last_tx || {};
      mmdvmHTML = `<tr>
        <td>${data.mmdvm.master || '-'}</td>
        <td>${data.mmdvm.version || '-'}</td>
        <td>${tx.timestamp || '-'}</td>
        <td>${tx.src || '-'}</td>
        <td>${tx.dst || '-'}</td>
        <td>${tx.slot || '-'}</td>
        <td>${tx.cc || '-'}</td>
        <td>${tx.metadata || '-'}</td>
      </tr>`;
    } else {
      mmdvmHTML = `<tr><td colspan="8">No MMDVM data yet</td></tr>`;
    }
    document.getElementById('mmdvm-body').innerHTML = mmdvmHTML;

    // ---- P25 Status ----
    let p25HTML = '';
    if (data.p25 && data.p25.last_tx) {
      const tx = data.p25.last_tx || {};
      p25HTML = `<tr>
        <td>${tx.timestamp || '-'}</td>
        <td>${tx.at || '-'}</td>
        <td>${tx.rid || '-'}</td>
        <td>${tx.tg || '-'}</td>
      </tr>`;
    } else {
      p25HTML = `<tr><td colspan="4">No P25 data yet</td></tr>`;
    }
    document.getElementById('p25-body').innerHTML = p25HTML;

    // ---- YSF Status ----
    let ysfHTML = '';
    if (data.ysf) {
      const tx = data.ysf.last_tx || {};
      const ev = data.ysf.last_event || {};
      ysfHTML = `<tr>
        <td>${tx.timestamp || '-'}</td>
        <td>${tx.callsign || '-'}</td>
        <td>${tx.dgid || '-'}</td>
        <td>${tx.note || '-'}</td>
        <td>${ev.msg || '-'}</td>
      </tr>`;
    } else {
      ysfHTML = `<tr><td colspan="5">No YSF data yet</td></tr>`;
    }
    document.getElementById('ysf-body').innerHTML = ysfHTML;
  };

  ws.onerror = function(error) {
    console.log('WebSocket error: ' + (error && error.message ? error.message : error));
  };

  ws.onclose = function() {
    console.log('WebSocket connection closed. Reconnecting...');
    setTimeout(startWebSocket, 3000);
  };
}

startWebSocket();
</script>

</body>
</html>
