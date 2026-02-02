DigiDash – Multi-Mode Digital Radio Dashboard & WebSocket Server

A real-time dashboard backend for monitoring M17, DMR, P25, and YSF digital voice activity using journald, exposed over secure WebSockets for live dashboards.

This project was built to correctly represent RF activity vs local bridge activity, avoiding false “ghost” talkers caused by digital cross-mode bridging.

✨ Features

📡 Live monitoring of:

M17 (mrefd), DMR (MMDVM_Bridge), P25 (P25Reflector), YSF (MMDVM_Bridge YSF)


🚫 Accurate suppression of local-origin transmissions, 🕒 Last-Heard tracking with de-duplication, 🔄 No polling files, reads directly from journald

🐍 Python 3.5 compatible (HamVOIP / legacy systems) and Allstarlink 3

🧠 Design Philosophy (Important)
Local vs External Callsigns

Bridge echo traffic does not generate ASL entries

🔁 ASL (AllStarLink Bridge) Rollup Logic

ASL is not a protocol — it’s inferred behavior.

ASL is shown only when all of the following are true:

No external RF station is active

Two or more digital modes are keyed simultaneously

All activity is local-origin (base callsign)

The activity persists long enough to be meaningful

When this happens:

A single ASL row is shown in Clients Talking

A single ASL entry is pushed to Last Heard only when it ends

What ASL Will Never Do

❌ Appear when only one mode is keyed, ❌ Appear due to bridge echo, ❌ Duplicate itself across key-ups


📊 Output Data Structure

Local-origin callsigns are suppressed

ASL appears only when appropriate


📁 Requirements

Linux system using systemd / journald

Services:

mrefd.service (for M17), mmdvm_bridge.service (for DMR), p25reflector.service (for P25), mmdvm_bridgeysf.service (For YSF or equivalent)

Python 3.5+

Python modules:

websockets

asyncio (standard)

Valid TLS certificate & key

🔐 TLS Configuration

Edit these paths at the top of the script:

fullchain_cert = "/etc/ssl/domain/domain.cert.pem"

private_key   = "/etc/ssl/private/private.key.pem"


⚙️ Configuration Options
ASL_BASE_CALLSIGN = "CALLSIGN"

ASL_LABEL_SOURCE  = "ASL"

ASL_LABEL_CALL   = "ASL-Bridge xxxxxx (Node Id Number)"

ENABLE_M17 = True

ENABLE_DMR = True

ENABLE_P25 = True

ENABLE_YSF = True

If True: if a service unit doesn't exist on this machine, auto-disable that mode.

AUTO_DISABLE_MISSING_UNITS = True

ASL_MIN_MODES_FOR_ROLLUP = 2

SUPPRESS_ASL_WHEN_EXTERNAL_TALKING = True


These allow you to tailor behavior for:

Different callsigns, Different bridge policies, More or less aggressive ASL detection

🚀 Running the Server
python3 websocket_server.py or via included websocket_server.service systemd file


The server listens on:

wss://0.0.0.0:8765
or
ws://0.0.0.0:8675 (for non SSL systems)


Intended to be run as a systemd service.

🛠 Debugging

When DEBUG = True, the server logs:

Mode start/end events

ASL state transitions

Journald follower health

WebSocket send errors

All logs go to stdout, making them visible via:

journalctl -u websocket_server -f

If anyone wants to help add NXDN or another mode, I will take Pull Requests.


<img width="1916" height="749" alt="image" src="https://github.com/user-attachments/assets/db6bd1b4-56ba-490a-aeb3-a753ee28d43b" />
