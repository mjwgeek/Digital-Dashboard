#!/usr/bin/env python3
# Python 3.5 compatible websocket server (SSL/TLS)
# Reads directly from journald and logs activity to journald (stdout)

import asyncio
import websockets
import ssl
import re
import json
import time
import threading
import subprocess
from datetime import datetime
from collections import deque

# -----------------------------
# CONFIG (TLS)
# -----------------------------
fullchain_cert = "/etc/ssl/domain/domain.cert.pem"
private_key    = "/etc/ssl/private/private.key.pem"

# -----------------------------
# MODE ENABLE/DISABLE
# -----------------------------
ENABLE_M17 = True
ENABLE_DMR = True
ENABLE_P25 = True
ENABLE_YSF = True

# If True: if a service unit doesn't exist on this machine, auto-disable that mode.
AUTO_DISABLE_MISSING_UNITS = True

M17_UNIT = "mrefd.service"
DMR_UNIT = "mmdvm_bridge.service"
P25_UNIT = "p25reflector.service"
YSF_UNIT = "mmdvm_bridgeysf.service"

ASL_BASE_CALLSIGN = "CALLSIGN"
ASL_LABEL_SOURCE  = "ASL"
ASL_LABEL_CALL    = "ASL-Bridge NODEID"
SUPPRESS_ASL_WHEN_EXTERNAL_TALKING = True

EXPIRE_SECONDS = 300
LAST_HEARD_DEDUP_SECONDS = 3
MAX_QUEUE = 2000
DEBUG = True
HEARTBEAT_SECONDS = 10

# Require >=2 bridged modes to show ASL (keeps it from showing on single-mode blips)
ASL_MIN_MODES_FOR_ROLLUP = 2

# Note:  If you change the port here, you will have to change it in index.php as well.
WS_BIND = "0.0.0.0"
WS_PORT = 8765

# -----------------------------
# Logging helper
# -----------------------------
def log_flush(msg):
    if not DEBUG:
        return
    try:
        print("[websocket_server] {}".format(msg))
        try:
            import sys
            sys.stdout.flush()
        except Exception:
            pass
    except Exception:
        pass

# -----------------------------
# Helpers
# -----------------------------
def systemd_unit_exists(unit_name):
    """
    Returns True if systemd knows about the unit.
    Safe if systemctl isn't present (returns False).
    """
    try:
        p = subprocess.Popen(
            ["systemctl", "status", unit_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        p.communicate()
        # 0 = active/running, 3 = inactive/dead, 4 = not-found
        return p.returncode != 4
    except Exception:
        return False

def apply_auto_disable():
    global ENABLE_M17, ENABLE_DMR, ENABLE_P25, ENABLE_YSF

    if not AUTO_DISABLE_MISSING_UNITS:
        return

    if ENABLE_M17 and not systemd_unit_exists(M17_UNIT):
        ENABLE_M17 = False
        log_flush("Auto-disabled M17 (missing unit: {})".format(M17_UNIT))

    if ENABLE_DMR and not systemd_unit_exists(DMR_UNIT):
        ENABLE_DMR = False
        log_flush("Auto-disabled DMR (missing unit: {})".format(DMR_UNIT))

    if ENABLE_P25 and not systemd_unit_exists(P25_UNIT):
        ENABLE_P25 = False
        log_flush("Auto-disabled P25 (missing unit: {})".format(P25_UNIT))

    if ENABLE_YSF and not systemd_unit_exists(YSF_UNIT):
        ENABLE_YSF = False
        log_flush("Auto-disabled YSF (missing unit: {})".format(YSF_UNIT))

def get_uptime_seconds():
    try:
        with open("/proc/uptime", "r") as f:
            return float(f.readline().split()[0])
    except Exception:
        return 0.0

def parse_syslog_time(ts):
    try:
        now = datetime.now()
        dt = datetime.strptime(ts, "%b %d %H:%M:%S")
        dt = dt.replace(year=now.year)
        return dt.timestamp()
    except Exception:
        return None

def now_syslog_ts():
    return datetime.now().strftime("%b %d %H:%M:%S")

def normalize_callsign(val):
    if val is None:
        return None
    return str(val).strip()

def is_local_origin(callsign_or_id):
    if not callsign_or_id:
        return False
    s = str(callsign_or_id).strip().upper()
    return s.startswith(ASL_BASE_CALLSIGN.upper())

def expire_talker(talker_dict, expire_seconds):
    now = time.time()
    if not talker_dict.get("callsign"):
        return
    ref_ts = talker_dict.get("last_event_time") or talker_dict.get("end_time") or talker_dict.get("start_time")
    ref_epoch = parse_syslog_time(ref_ts) if ref_ts else None
    if talker_dict.get("status") != "talking" and ref_epoch is not None and (now - ref_epoch) > expire_seconds:
        talker_dict["callsign"] = None
        talker_dict["module"] = None
        talker_dict["status"] = None
        talker_dict["start_time"] = None
        talker_dict["end_time"] = None
        talker_dict["last_event_time"] = None
        talker_dict["extra"] = {}

# -----------------------------
# Journal follower thread
# -----------------------------
class JournalFollower(object):
    def __init__(self, unit_name, line_queue):
        self.unit_name = unit_name
        self.q = line_queue
        self._stop = False
        self._proc = None
        self._thread = None
        self.last_line_time = None
        self.spawn_count = 0
        self.dead_count = 0
        self.last_error = None

    def start(self):
        t = threading.Thread(target=self._run)
        t.daemon = True
        self._thread = t
        t.start()

    def _spawn(self):
        # IMPORTANT for HamVOIP:
        # --quiet removes the "Logs begin at..." header line(s) that can break parsing.
        cmd = [
            "journalctl", "--no-pager", "--quiet",
            "-u", self.unit_name,
            "-f", "-n", "0",
            "-o", "short"
        ]
        self.spawn_count += 1
        log_flush("Starting follower for {} (spawn #{})".format(self.unit_name, self.spawn_count))
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

    def _run(self):
        while not self._stop:
            try:
                self._spawn()
                while not self._stop:
                    line = self._proc.stdout.readline()
                    if not line:
                        break
                    line = line.rstrip("\n")
                    if line:
                        self.last_line_time = time.time()
                    try:
                        self.q.append(line)
                        if len(self.q) > MAX_QUEUE:
                            self.q.popleft()
                    except Exception:
                        pass
            except Exception as e:
                self.last_error = str(e)
                log_flush("Follower exception [{}]: {}".format(self.unit_name, e))
            self.dead_count += 1
            log_flush("Follower for {} ended (dead #{})".format(self.unit_name, self.dead_count))
            time.sleep(1.0)

# -----------------------------
# Queues
# -----------------------------
m17_q = deque()
dmr_q = deque()
p25_q = deque()
ysf_q = deque()

followers = []

def build_followers():
    global followers
    followers = []
    if ENABLE_M17:
        followers.append(JournalFollower(M17_UNIT, m17_q))
    if ENABLE_DMR:
        followers.append(JournalFollower(DMR_UNIT, dmr_q))
    if ENABLE_P25:
        followers.append(JournalFollower(P25_UNIT, p25_q))
    if ENABLE_YSF:
        followers.append(JournalFollower(YSF_UNIT, ysf_q))

# -----------------------------
# Syslog line splitter
# HamVOIP can use single-digit days and variable spacing.
# Example:
# "Feb  1 22:47:44 HOST prog[pid]: message"
# -----------------------------
syslog_prefix_re = re.compile(
    r"^(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+\S+\s+([^:]+):\s+(.*)$"
)

def split_syslog(line):
    m = syslog_prefix_re.match(line)
    if not m:
        return None, None, None
    return m.group(1), m.group(2), m.group(3)

# -----------------------------
# State
# -----------------------------
external_talking_now = False

last_heard = []
MAX_LAST_HEARD = 200

clients_talking = {}  # M17 per callsign
peers = {}            # M17 peers

mmdvm_status = {"version": None, "master": None, "tx_state": "OFF", "last_tx": None}
p25_status = {"last_tx": None, "linked_count": 0, "linked": []}
ysf_status = {"last_tx": None, "last_event": None}

dmr_talker = {"source":"DMR","callsign":None,"id":None,"module":None,"status":None,"start_time":None,"end_time":None,"last_event_time":None,"extra":{}}
p25_talker = {"source":"P25","callsign":None,"module":None,"status":None,"start_time":None,"end_time":None,"last_event_time":None,"extra":{}}
ysf_talker = {"source":"YSF","callsign":None,"module":None,"status":None,"start_time":None,"end_time":None,"last_event_time":None,"extra":{}}

p25_pending_start = {"active": False, "start_time": None, "who": None}

asl_rollup_state = {
    "talking": False,
    "start_time": None,
    "last_summary": None,
    "external_triggered": False,
}

# -----------------------------
# Last heard push (dedupe)
# -----------------------------
def push_last_heard(entry):
    global external_talking_now
    ts = entry.get("timestamp")
    cs = entry.get("callsign")
    proto = (entry.get("protocol") or "").upper()

    if cs and is_local_origin(cs):
        return

    if cs and proto == "ASL" and external_talking_now and SUPPRESS_ASL_WHEN_EXTERNAL_TALKING:
        return

    new_epoch = parse_syslog_time(ts) if ts else None
    if cs and new_epoch is not None:
        for e in last_heard[:25]:
            if e.get("callsign") != cs:
                continue
            old_epoch = parse_syslog_time(e.get("timestamp")) if e.get("timestamp") else None
            if old_epoch is None:
                continue
            if abs(new_epoch - old_epoch) <= LAST_HEARD_DEDUP_SECONDS:
                return

    last_heard.insert(0, entry)
    if len(last_heard) > MAX_LAST_HEARD:
        del last_heard[MAX_LAST_HEARD:]

# -----------------------------
# Parsers
# -----------------------------
open_stream_pattern = re.compile(r"Opening stream on module (\w) for client (\S+)")
close_stream_pattern = re.compile(r"Closing stream on module (\w)")
connect_packet_pattern = re.compile(r"Connect packet for module (\w) from (\S+).* at (.*)")
disconnect_packet_pattern = re.compile(r"Client (\S+)\s+(\w)\s+keepalive timeout")
droidstar_disconnect_pattern = re.compile(r"Disconnect packet from (\S+)\s+(\w)\s+at (.*)")

def parse_m17_lines():
    while True:
        try:
            line = m17_q.popleft()
        except IndexError:
            break

        sys_ts, _src, msg = split_syslog(line)
        if not sys_ts or not msg:
            continue

        om = open_stream_pattern.search(msg)
        if om:
            module = om.group(1)
            cs = normalize_callsign(om.group(2))
            clients_talking[cs] = {"status":"talking","module":module,"start_time":sys_ts,"end_time":None}
            log_flush("M17 START {} {} ({})".format(cs, module, sys_ts))
            continue

        cm = close_stream_pattern.search(msg)
        if cm:
            module = cm.group(1)
            for cs, info in list(clients_talking.items()):
                if info.get("status") == "talking" and info.get("module") == module:
                    info["status"] = "not talking"
                    info["end_time"] = sys_ts
                    log_flush("M17 END {} {} ({})".format(cs, module, sys_ts))
                    push_last_heard({"timestamp":sys_ts,"callsign":cs,"protocol":"M17","module":module,"source":"M17"})
            continue

        conn = connect_packet_pattern.search(msg)
        if conn:
            module = conn.group(1)
            cs = normalize_callsign(conn.group(2))
            ip = conn.group(3)
            key = "{}_{}_{}".format(cs, module, ip)
            peers[key] = {"timestamp":sys_ts,"callsign":cs,"module":module,"ip":ip}
            continue

        dis = disconnect_packet_pattern.search(msg)
        if dis:
            cs = normalize_callsign(dis.group(1))
            module = dis.group(2)
            remove = []
            for k, v in peers.items():
                if v.get("callsign") == cs and v.get("module") == module:
                    remove.append(k)
            for k in remove:
                peers.pop(k, None)
            continue

        dd = droidstar_disconnect_pattern.search(msg)
        if dd:
            ip = dd.group(3)
            peer_key = None
            for k, v in peers.items():
                if v.get("ip") == ip:
                    peer_key = k
                    break
            if peer_key:
                peers.pop(peer_key, None)
            continue

# ---- DMR (HamVOIP spacing fix: allow "DMR ," as well as "DMR,") ----
mmdvm_tx_state_re  = re.compile(r"\bDMR\s*,\s*TX state\s*=\s*(ON|OFF)\b", re.IGNORECASE)
mmdvm_begin_tx_re  = re.compile(r"\bDMR\s*,\s*Begin TX:\s*src=(\d+)\s+rpt=(\d+)\s+dst=(\d+)\s+slot=(\d+)\s+cc=(\d+)\s+metadata=([^\s]+)\b")
dmr_net_header_re  = re.compile(r"\bDMR Slot (\d+), received network voice header from\s+(.+?)\s+to TG (\d+)\b", re.IGNORECASE)
dmr_net_end_re     = re.compile(r"\bDMR Slot (\d+), received network end of voice transmission\b", re.IGNORECASE)
dmr_talker_alias_re = re.compile(r"\bDMR Talker Alias .*?:\s*'([^']+)'\s*$", re.IGNORECASE)

dmr_last_alias = {"value": None, "time": 0.0}
DMR_ALIAS_WINDOW_SECONDS = 3.0

def _dmr_end(sys_ts):
    if dmr_talker.get("callsign") and dmr_talker.get("status") == "talking":
        dmr_talker["status"] = "not talking"
        dmr_talker["end_time"] = sys_ts
        dmr_talker["last_event_time"] = sys_ts
        log_flush("DMR END {} {} ({})".format(dmr_talker.get("callsign"), dmr_talker.get("module"), sys_ts))
        push_last_heard({"timestamp":sys_ts,"callsign":dmr_talker.get("callsign"),"protocol":"DMR","module":dmr_talker.get("module","-"),"source":"DMR"})

def parse_dmr_lines():
    while True:
        try:
            line = dmr_q.popleft()
        except IndexError:
            break

        sys_ts, _src, msg = split_syslog(line)
        if not sys_ts or not msg:
            continue

        ta = dmr_talker_alias_re.search(msg)
        if ta:
            alias = normalize_callsign(ta.group(1))
            dmr_last_alias["value"] = alias
            dmr_last_alias["time"] = time.time()
            if dmr_talker.get("status") == "talking":
                dmr_talker["callsign"] = alias
                dmr_talker["last_event_time"] = sys_ts
            continue

        nh = dmr_net_header_re.search(msg)
        if nh:
            slot = nh.group(1)
            raw_from = normalize_callsign(nh.group(2))
            tg = nh.group(3)

            callsign = raw_from
            if dmr_last_alias.get("value") and (time.time() - dmr_last_alias.get("time", 0.0)) <= DMR_ALIAS_WINDOW_SECONDS:
                callsign = dmr_last_alias["value"]

            dmr_talker["id"] = None
            dmr_talker["callsign"] = callsign
            dmr_talker["module"] = "S{} / TG {}".format(slot, tg)
            dmr_talker["status"] = "talking"
            dmr_talker["start_time"] = sys_ts
            dmr_talker["end_time"] = None
            dmr_talker["last_event_time"] = sys_ts
            log_flush("DMR NET START {} {} ({})".format(callsign, dmr_talker["module"], sys_ts))
            continue

        ne = dmr_net_end_re.search(msg)
        if ne:
            _dmr_end(sys_ts)
            continue

        btx = mmdvm_begin_tx_re.search(msg)
        if btx:
            src_id = btx.group(1)
            dst_tg = btx.group(3)
            slot = btx.group(4)
            cc = btx.group(5)
            meta = normalize_callsign(btx.group(6))

            mmdvm_status["last_tx"] = {"timestamp":sys_ts,"src":src_id,"dst":dst_tg,"slot":slot,"cc":cc,"metadata":meta}

            dmr_talker["id"] = src_id
            dmr_talker["callsign"] = meta or src_id or "-"
            dmr_talker["module"] = "S{} / TG {}".format(slot, dst_tg)
            dmr_talker["status"] = "talking"
            dmr_talker["start_time"] = sys_ts
            dmr_talker["end_time"] = None
            dmr_talker["last_event_time"] = sys_ts
            continue

        st = mmdvm_tx_state_re.search(msg)
        if st:
            state = st.group(1).upper()
            mmdvm_status["tx_state"] = state
            if state == "OFF":
                _dmr_end(sys_ts)
            continue

# ---- P25 ----
p25_m_prefix_re   = re.compile(r"^M:\s+\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+(.*)$")
p25_tx_started_re = re.compile(r"^Transmission started from\s+(\S+)\s*$")
p25_tx_from_re    = re.compile(r"^Transmission from\s+(\d+)\s+at\s+(.+?)\s+to\s+TG\s+(\d+)\s*$")
p25_tx_end_re     = re.compile(r"^Received end of transmission\s*$")

def _p25_end(sys_ts):
    if p25_talker.get("callsign") and p25_talker.get("status") == "talking":
        p25_talker["status"] = "not talking"
        p25_talker["end_time"] = sys_ts
        p25_talker["last_event_time"] = sys_ts
        push_last_heard({"timestamp":sys_ts,"callsign":p25_talker.get("callsign"),"protocol":"P25","module":p25_talker.get("module","-"),"source":"P25"})
    p25_pending_start["active"] = False
    p25_pending_start["start_time"] = None
    p25_pending_start["who"] = None

def parse_p25_lines():
    while True:
        try:
            line = p25_q.popleft()
        except IndexError:
            break

        sys_ts, _src, msg = split_syslog(line)
        if not sys_ts or not msg:
            continue

        mm = p25_m_prefix_re.match(msg)
        if not mm:
            continue
        payload = mm.group(1).strip()

        ts0 = p25_tx_started_re.match(payload)
        if ts0:
            who = normalize_callsign(ts0.group(1))
            p25_pending_start["active"] = True
            p25_pending_start["start_time"] = sys_ts
            p25_pending_start["who"] = who
            continue

        tx = p25_tx_from_re.match(payload)
        if tx:
            rid = tx.group(1)
            at = normalize_callsign(tx.group(2).strip())
            tg = tx.group(3)

            p25_status["last_tx"] = {"timestamp":sys_ts,"rid":rid,"at":at,"tg":tg}

            p25_talker["callsign"] = at
            p25_talker["module"] = "TG {}".format(tg)
            p25_talker["status"] = "talking"

            if p25_pending_start["active"] and p25_pending_start["start_time"]:
                p25_talker["start_time"] = p25_pending_start["start_time"]
            else:
                p25_talker["start_time"] = p25_talker.get("start_time") or sys_ts

            p25_talker["end_time"] = None
            p25_talker["last_event_time"] = sys_ts

            p25_pending_start["active"] = False
            p25_pending_start["start_time"] = None
            p25_pending_start["who"] = None
            continue

        if p25_tx_end_re.match(payload):
            _p25_end(sys_ts)
            continue

# ---- YSF ----
ysf_net_data_re = re.compile(r"\bYSF,\s+received network data from\s+(.+?)\s+to\s+(.+?)\s+at\s+(.+?)\s*$", re.IGNORECASE)
ysf_net_end_re  = re.compile(r"\bYSF,\s+received network end of transmission,\s+([0-9.]+)\s+seconds\b", re.IGNORECASE)

def _ysf_end(sys_ts):
    if ysf_talker.get("callsign") and ysf_talker.get("status") == "talking":
        ysf_talker["status"] = "not talking"
        ysf_talker["end_time"] = sys_ts
        ysf_talker["last_event_time"] = sys_ts
        push_last_heard({"timestamp":sys_ts,"callsign":ysf_talker.get("callsign"),"protocol":"YSF","module":ysf_talker.get("module","-"),"source":"YSF"})

def parse_ysf_lines():
    while True:
        try:
            line = ysf_q.popleft()
        except IndexError:
            break

        sys_ts, _src, msg = split_syslog(line)
        if not sys_ts or not msg:
            continue

        nd = ysf_net_data_re.search(msg)
        if nd:
            raw_from = normalize_callsign(nd.group(1))
            raw_to   = normalize_callsign(nd.group(2))
            raw_at   = normalize_callsign(nd.group(3))

            ysf_status["last_tx"] = {"timestamp":sys_ts,"callsign":raw_from,"dgid":raw_to,"note":"at {}".format(raw_at)}
            ysf_talker["callsign"] = raw_from
            ysf_talker["module"] = raw_to
            ysf_talker["status"] = "talking"
            ysf_talker["start_time"] = sys_ts
            ysf_talker["end_time"] = None
            ysf_talker["last_event_time"] = sys_ts
            continue

        ne = ysf_net_end_re.search(msg)
        if ne:
            _ysf_end(sys_ts)
            continue

# -----------------------------
# External talker check
# -----------------------------
def any_external_talker_active():
    if ENABLE_M17:
        for cs, info in clients_talking.items():
            if info.get("status") == "talking" and cs and (not is_local_origin(cs)):
                return True

    if ENABLE_DMR:
        if dmr_talker.get("status") == "talking" and dmr_talker.get("callsign") and (not is_local_origin(dmr_talker.get("callsign"))):
            return True

    if ENABLE_P25:
        if p25_talker.get("status") == "talking" and p25_talker.get("callsign") and (not is_local_origin(p25_talker.get("callsign"))):
            return True

    if ENABLE_YSF:
        if ysf_talker.get("status") == "talking" and ysf_talker.get("callsign") and (not is_local_origin(ysf_talker.get("callsign"))):
            return True

    return False

# -----------------------------
# Combined JSON builders
# -----------------------------
def build_combined_clients_talking():
    global asl_rollup_state
    combined = []
    now = time.time()

    external_talking = any_external_talker_active()

    bridged_parts = []
    bridged_start_candidates = []

    # M17
    for callsign, info in list(clients_talking.items()):
        status = info.get("status", "-")
        module = info.get("module", "-")
        start_ts = info.get("start_time")
        end_ts = info.get("end_time")

        if status != "talking":
            ref_ts = end_ts or start_ts
            ref_epoch = parse_syslog_time(ref_ts) if ref_ts else None
            if ref_epoch is not None and (now - ref_epoch) > EXPIRE_SECONDS:
                try:
                    del clients_talking[callsign]
                except Exception:
                    pass
            continue

        cs = normalize_callsign(callsign)

        if cs and is_local_origin(cs):
            bridged_parts.append("M17:{}".format(module))
            if start_ts:
                bridged_start_candidates.append(start_ts)
            continue

        combined.append({
            "source": "M17",
            "callsign": cs,
            "module": module,
            "status": "talking",
            "start_time": start_ts or "-",
            "end_time": "-",
        })

    # DMR
    expire_talker(dmr_talker, EXPIRE_SECONDS)
    if dmr_talker.get("callsign") and dmr_talker.get("status") == "talking":
        cs = normalize_callsign(dmr_talker.get("callsign"))
        mod = dmr_talker.get("module") or "-"
        if cs and is_local_origin(cs):
            bridged_parts.append("DMR:{}".format(mod.replace(" ", "")))
            if dmr_talker.get("start_time"):
                bridged_start_candidates.append(dmr_talker.get("start_time"))
        else:
            combined.append({"source":"DMR","callsign":cs,"module":mod,"status":"talking","start_time":dmr_talker.get("start_time") or "-","end_time":"-"})

    # P25
    expire_talker(p25_talker, EXPIRE_SECONDS)
    if p25_talker.get("callsign") and p25_talker.get("status") == "talking":
        cs = normalize_callsign(p25_talker.get("callsign"))
        mod = p25_talker.get("module") or "-"
        if cs and is_local_origin(cs):
            if mod.strip() and mod.strip() != "-":
                bridged_parts.append("P25:{}".format(mod.replace(" ", "")))
                if p25_talker.get("start_time"):
                    bridged_start_candidates.append(p25_talker.get("start_time"))
        else:
            combined.append({"source":"P25","callsign":cs,"module":mod,"status":"talking","start_time":p25_talker.get("start_time") or "-","end_time":"-"})

    # YSF
    expire_talker(ysf_talker, EXPIRE_SECONDS)
    if ysf_talker.get("callsign") and ysf_talker.get("status") == "talking":
        cs = normalize_callsign(ysf_talker.get("callsign"))
        mod = ysf_talker.get("module") or "-"
        if cs and is_local_origin(cs):
            bridged_parts.append("YSF:{}".format(mod.replace(" ", "")))
            if ysf_talker.get("start_time"):
                bridged_start_candidates.append(ysf_talker.get("start_time"))
        else:
            combined.append({"source":"YSF","callsign":cs,"module":mod,"status":"talking","start_time":ysf_talker.get("start_time") or "-","end_time":"-"})

    if bridged_parts:
        dedup = []
        seen = set()
        for p in bridged_parts:
            if p not in seen:
                seen.add(p)
                dedup.append(p)
        bridged_parts = dedup

    asl_is_talking = ((not external_talking) and (len(bridged_parts) >= ASL_MIN_MODES_FOR_ROLLUP))

    if asl_rollup_state.get("talking") and (not asl_is_talking):
        if not asl_rollup_state.get("external_triggered"):
            ended_ts = now_syslog_ts()
            summary = asl_rollup_state.get("last_summary") or "-"
            push_last_heard({"timestamp": ended_ts, "callsign": ASL_LABEL_CALL, "protocol": "ASL", "module": summary, "source": ASL_LABEL_SOURCE})
        asl_rollup_state["talking"] = False
        asl_rollup_state["start_time"] = None
        asl_rollup_state["last_summary"] = None
        asl_rollup_state["external_triggered"] = False

    if asl_is_talking:
        summary = " | ".join(bridged_parts) if bridged_parts else "-"
        start_time = min(bridged_start_candidates) if bridged_start_candidates else now_syslog_ts()

        if not asl_rollup_state.get("talking"):
            asl_rollup_state["talking"] = True
            asl_rollup_state["start_time"] = start_time
            asl_rollup_state["external_triggered"] = False
        asl_rollup_state["last_summary"] = summary

        combined.insert(0, {"source": ASL_LABEL_SOURCE, "callsign": ASL_LABEL_CALL, "module": summary, "status": "talking", "start_time": asl_rollup_state.get("start_time") or start_time, "end_time": "-"})

    elif asl_rollup_state.get("talking") is False and external_talking and (len(bridged_parts) >= ASL_MIN_MODES_FOR_ROLLUP):
        asl_rollup_state["talking"] = True
        asl_rollup_state["external_triggered"] = True
        asl_rollup_state["last_summary"] = " | ".join(bridged_parts)

    return combined

def build_combined_last_heard(limit_n):
    out = []
    for e in last_heard[:limit_n]:
        out.append({"source": e.get("source", e.get("protocol","-")), "callsign": e.get("callsign","-"), "protocol": e.get("protocol","-"), "module_or_tg": e.get("module","-"), "timestamp": e.get("timestamp","-")})
    return out

def build_combined_peers(limit_n):
    out = []
    vals = list(peers.values())
    for p in vals[:limit_n]:
        out.append({"source":"M17","callsign":p.get("callsign","-"),"module":p.get("module","-"),"ip_or_master":p.get("ip","-"),"timestamp":p.get("timestamp","-")})
    return out

def parse_journal_queues():
    global external_talking_now
    if ENABLE_M17:
        parse_m17_lines()
    if ENABLE_DMR:
        parse_dmr_lines()
    if ENABLE_P25:
        parse_p25_lines()
    if ENABLE_YSF:
        parse_ysf_lines()
    external_talking_now = any_external_talker_active()

# -----------------------------
# TLS (Python 3.5 compatible)
# -----------------------------
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
ssl_context.load_cert_chain(certfile=fullchain_cert, keyfile=private_key)

# -----------------------------
# Websocket handler
# -----------------------------
async def websocket_handler(websocket, path):
    while True:
        parse_journal_queues()

        combined_obj = {
            "clients_talking": build_combined_clients_talking(),
            "last_heard": build_combined_last_heard(10),
            "peers": build_combined_peers(10) if ENABLE_M17 else [],
        }

        data = {
            "uptime_seconds": get_uptime_seconds(),
            "combined": combined_obj,
        }

        if ENABLE_DMR:
            data["mmdvm"] = mmdvm_status
        if ENABLE_P25:
            data["p25"] = p25_status
        if ENABLE_YSF:
            data["ysf"] = ysf_status

        try:
            await websocket.send(json.dumps(data))
        except Exception as e:
            log_flush("Websocket send failed: {}".format(e))
            return

        await asyncio.sleep(1)

# -----------------------------
# Heartbeat thread
# -----------------------------
def heartbeat_loop():
    while True:
        try:
            parts = []
            for f in followers:
                age = None
                if f.last_line_time:
                    age = int(time.time() - f.last_line_time)
                parts.append("{} age={}s q={} spawns={} dead={} err={}".format(
                    f.unit_name,
                    age if age is not None else -1,
                    len(f.q),
                    f.spawn_count,
                    f.dead_count,
                    f.last_error if f.last_error else "-"
                ))
            log_flush("HEARTBEAT: " + " | ".join(parts))
        except Exception as e:
            log_flush("HEARTBEAT error: {}".format(e))
        time.sleep(HEARTBEAT_SECONDS)

# -----------------------------
# Main (TLS)
# -----------------------------
def main():
    log_flush("Starting websocket_server (journald direct) on {}:{} (TLS)".format(WS_BIND, WS_PORT))

    apply_auto_disable()
    build_followers()

    if not followers:
        log_flush("No modes enabled/found. Exiting.")
        return

    for f in followers:
        f.start()

    t = threading.Thread(target=heartbeat_loop)
    t.daemon = True
    t.start()

    start_server = websockets.serve(websocket_handler, WS_BIND, WS_PORT, ssl=ssl_context)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_server)
    log_flush("Websocket server is running (wss) on port {}".format(WS_PORT))
    loop.run_forever()

if __name__ == "__main__":
    main()
