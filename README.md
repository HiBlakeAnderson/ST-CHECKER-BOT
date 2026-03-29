<div align="center">

# 🤖 ST-CHECKER-BOT

[![Python](https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python)](https://python.org)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram)](https://core.telegram.org/bots)
[![Platform](https://img.shields.io/badge/Platform-Replit%20%7C%20AWS%20EC2-orange?style=for-the-badge)](https://replit.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

**A powerful Telegram bot for checking credit card validity across multiple payment gateways — with VIP plans, proxy support, BIN lookup, and one-click cloud deployment.**

</div>

---

<details>
<summary><b>✨ Features</b></summary>
<br>

- 💳 **Multi-Gateway Checking** — PayPal, Braintree 3DS (VBV), Stripe Charge, Stripe Checkout, SK checker, External API
- 📦 **Mass Card Checking** — Bulk check up to 100 cards from a file or inline
- 🌐 **Triple Checkout Commands** — `/co` (pure Python, direct Stripe), `/xco` (external API), and `/h` (gold-newt hitter.php) — all support single card, multi-card, and txt file reply modes
- 🔍 **BIN Lookup** — Instant card brand, type, bank, and country info
- 🎰 **Card Generator** — Generate valid Luhn-correct card numbers from any BIN
- 🛡️ **Proxy Support** — Per-user HTTP/SOCKS4/SOCKS5 proxy configuration
- 👥 **User Plans** — FREE and VIP tier management with redeem codes
- 📊 **Live Statistics** — Real-time usage stats, daily breakdowns, gateway performance
- ⚡ **Uptime System** — Auto-restart watchdog + Flask keep-alive server (port 8099)
- 🔐 **Admin Panel** — Full admin controls, DB export, backup, and user management
- 🚀 **Easy Deployment** — One-click AWS EC2 setup with systemd auto-start

</details>

---

<details>
<summary><b>📸 Preview</b></summary>
<br>

```
Bot Start On ✅
Admin ID: xxxxxxxxxx

/ping  → 🏓 Pong! Latency: 42ms
/status → 🤖 Bot Online | Uptime: 2h 15m | Mode: Polling
/stats  → 📊 Total Users: 120 | Checks Today: 540 | Live: 38
```

</details>

---

<details>
<summary><b>🚀 Quick Start</b></summary>
<br>

### 1. Clone the Repository

```bash
git clone https://github.com/hiaistudent-jpg/ST-CHECKER-BOT.git
cd ST-CHECKER-BOT
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Environment Variables

```bash
export BOT_TOKEN="your_bot_token_here"
export ADMIN_ID="your_telegram_user_id"
```

> 💡 Get your **BOT_TOKEN** from [@BotFather](https://t.me/BotFather)
> Get your **ADMIN_ID** from [@userinfobot](https://t.me/userinfobot)

### 4. Run the Bot

```bash
python3 main.py
```

</details>

---

<details>
<summary><b>🤖 Commands</b></summary>
<br>

### 🔵 General (FREE)
| Command | Description |
|---------|-------------|
| `/start` | Welcome message and plan info |
| `/cmds` / `/help` | Full list of all commands |
| `/myid` | Show your Telegram user ID |
| `/ping` | Check bot response latency |
| `/history` | Your last 10 card checks |

### 💳 Card Checking (FREE)
| Command | Description | Usage |
|---------|-------------|-------|
| `/chk` | Single card check | `/chk 4111111111111111\|12\|25\|123` |
| `/chkm` | Mass card check (up to 50) | `/chkm card1\ncard2` or reply to file |

### 💰 Payment Gateways (VIP)
| Command | Description | Usage |
|---------|-------------|-------|
| `/pp` | PayPal gateway | `/pp 4111...\|12\|25\|123` |
| `/vbv` | Braintree 3DS check | `/vbv 4111...\|12\|25\|123` |
| `/vbvm` | Braintree 3DS mass check | `/vbvm card1\ncard2` |
| `/st` | Stripe charge $1 | `/st 4111...\|12\|25\|123` |
| `/sa` | Stripe auth only | `/sa 4111...\|12\|25\|123` |
| `/stm` | Stripe mass checker | `/stm card1\ncard2` |
| `/co` | Stripe checkout — pure Python, direct Stripe API | `/co <url>\n4111...\|12\|25\|123` |
| `/xco` | Stripe checkout — external API | `/xco <url>\n4111...\|12\|25\|123` |
| `/h` | Hitter checker — gold-newt hitter.php API | `/h <url>\n4111...\|12\|25\|123` |
| `/ah` | Auto Hitter — checkout · invoice · billing (session cache) | `/ah <url>\n4111...\|12\|25\|123` |

> `/co`, `/xco`, `/h`, and `/ah` all support **4 modes** in one command:
> - **Single card** → full result with BIN info, merchant, amount, timing
> - **Multiple cards** → live mass checker with 🛑 stop button
> - **TXT file reply** → reply to a `.txt` file with the command + URL
> - **Gen message reply** → reply to a `/gen` output message with the command + URL
>
> `/co` and `/xco` additionally support **BIN auto-gen** → `/co <url>\n411111 30`
>
> `/ah` auto-detects gate from URL: `invoice` → Invoice gate · `billing` → Billing gate · everything else → Checkout

### 🔑 SK Checkers (VIP)
| Command | Description | Usage |
|---------|-------------|-------|
| `/sk` | SK single card checker | `/sk sk_live_xxx\n4111...\|12\|25\|123` |
| `/skm` | SK mass card checker | `/skm sk_live_xxx\ncard1\ncard2` |
| `/skchk` | SK key live/dead check | `/skchk sk_live_xxx` |
| `/msk` | Mass SK live/dead checker | `/msk sk_live_key1\nsk_live_key2` |

### 🃏 Card Tools (FREE)
| Command | Description | Usage |
|---------|-------------|-------|
| `/gen` | Generate cards from BIN | `/gen 411111` or `/gen 411111 50` |
| `/bin` | BIN lookup | `/bin 411111` |
| `/thik` | CC Aligner — raw/messy list → `num\|mm\|yy\|cvv` | `/thik [raw ccs]` or reply to message |

### 🌐 Proxy Tools (FREE)
| Command | Description | Usage |
|---------|-------------|-------|
| `/addproxy` | Set your proxy | `/addproxy ip:port` or `/addproxy user:pass@ip:port` |
| `/setproxy` | Set proxy (alias) | Same as `/addproxy` |
| `/removeproxy` | Remove proxy | `/removeproxy` |
| `/proxycheck` | Test your proxy | `/proxycheck` |
| `/scr` | Scrape fresh proxies | FREE: 50 \| VIP: 500 |
| `/chkpxy` | Bulk proxy checker | Up to 500, 10 threads |

### ⚙️ Settings
| Command | Description | Usage |
|---------|-------------|-------|
| `/setamount` | Set charge amount | `/setamount 2.00` |
| `/setsk` | Set Stripe SK key (VIP) | `/setsk sk_live_xxx` |
| `/mysk` | View SK status (VIP) | `/mysk` |
| `/delsk` | Remove SK key (VIP) | `/delsk` |

### 👑 Admin Only

| Command | Description | Usage |
|---------|-------------|-------|
| `/amadmin` | Verify admin privileges | `/amadmin` |
| `/addvip` | Give VIP — by **ID or @username** (auto-resolved via Telegram API) | `/addvip @user 30` or `/addvip 123456789 7` |
| `/removevip` | Revoke VIP from user | `/removevip @user` or `/removevip 123456789` |
| `/checkvip` | Check user plan and expiry | `/checkvip @user` |
| `/viplist` | Show all active VIP users — ID, username, name, expiry, days left | `/viplist` |
| `/status` | Server status — IP, location, ping, CPU/RAM/Disk | `/status` |
| `/stats` | Bot statistics — all-time, daily, gateway leaderboard | `/stats` |
| `/restart` | Restart bot service (inline confirm/cancel) | `/restart` |
| `/reboot` | Full EC2 reboot (inline confirm/cancel) | `/reboot` |
| `/code` | Generate VIP redeem code | `/code 24` (24h validity) |
| `/dbstats` | Full database statistics | `/dbstats` |
| `/dbexport` | Export database to CSV/JSON | `/dbexport` |
| `/dbbackup` | Send DB backup file | `/dbbackup` |
| `/dbsearch` | Search user in database | `/dbsearch @user` |

> **`/addvip` supports 3 ways:**
> - `/addvip @yadistan 30` — by public @username (works even if user never used the bot)
> - `/addvip 123456789 30` — by numeric Telegram ID
> - `/addvip @yadistan` — omit days to use default (30 days)

</details>

---

<details>
<summary><b>🌐 BotFather Command List</b></summary>
<br>

Copy-paste this into BotFather → `/setcommands`:

```
start - Welcome message and plan info
cmds - Full command list with usage
help - Full command list with usage
myid - Your Telegram user ID
ping - Bot response latency check
history - Your last 10 card checks
chk - Single card checker free
chkm - Mass card checker up to 50 free
gen - Card generator from BIN free
bin - BIN lookup brand bank country free
thik - Align raw messy CC list to num|mm|yy|cvv free
addproxy - Set proxy HTTP SOCKS4 SOCKS5 free
setproxy - Set proxy alias for addproxy free
removeproxy - Remove your proxy free
proxycheck - Test your current proxy free
scr - Scrape fresh proxies 50 free 500 VIP
chkpxy - Bulk proxy checker up to 500 free
pp - PayPal gateway checker VIP
vbv - Braintree 3DS single check VIP
vbvm - Braintree 3DS mass checker VIP
st - Stripe charge direct ultra fast VIP
sa - Stripe auth only no charge VIP
stm - Stripe mass checker VIP
co - Stripe checkout direct API single multi BIN txt VIP
xco - Ext API checkout single multi BIN txt VIP
h - Hitter checker single multi txt reply gen msg VIP
ah - Auto Hitter checkout invoice billing session cache VIP
sk - SK single card checker VIP
skm - SK mass card checker VIP
skchk - SK key live dead balance inspector VIP
msk - Mass SK keys live dead checker VIP
setamount - Set charge amount for gateways
setsk - Set your Stripe SK key VIP
mysk - View your SK key status VIP
delsk - Remove your SK key VIP
redeem - Redeem a VIP code
addvip - Give VIP to user by ID or username admin
removevip - Remove VIP from user by ID or username admin
checkvip - Check user plan and expiry date admin
viplist - Show all active VIP users with expiry status admin
status - Server IP location ping CPU RAM Disk admin
stats - Bot statistics daily breakdown gateway leaderboard admin
restart - Restart bot service with confirmation admin
reboot - Full EC2 reboot with confirmation admin
code - Generate VIP redeem codes admin
dbstats - Full database statistics admin
dbexport - Export database to CSV JSON admin
dbbackup - Send database backup file admin
dbsearch - Search user in database admin
```

</details>

---

<details>
<summary><b>☁️ Deployment</b></summary>
<br>

### 🟢 Replit (Recommended for beginners)

1. Fork this repo or import to [Replit](https://replit.com)
2. Go to **Secrets** and add:
   - `BOT_TOKEN` → your bot token
   - `ADMIN_ID` → your Telegram ID
3. Click **Run** — the bot starts automatically
4. The keep-alive server (port 8099) pings itself every 4.5 minutes to stay online

---

### 🟠 AWS EC2 — Full Setup Guide

#### Step 0 — What you need before starting

| Item | Where to get it |
|------|----------------|
| AWS EC2 instance (Ubuntu 20.04 / 22.04) | [AWS Console](https://console.aws.amazon.com/ec2) |
| Bot Token | [@BotFather](https://t.me/BotFather) → `/newbot` |
| Your Telegram ID | [@userinfobot](https://t.me/userinfobot) |
| SSH access to the instance | Your `.pem` key file |

#### Step 1 — SSH into your EC2 instance

```bash
ssh -i "your-key.pem" ubuntu@YOUR_EC2_IP
```

> Replace `YOUR_EC2_IP` with your instance's public IPv4 address.

#### Step 2 — Clone the repo

```bash
git clone https://github.com/hiaistudent-jpg/ST-CHECKER-BOT.git
cd ST-CHECKER-BOT
```

#### Step 3 — Run the setup script

```bash
bash setup.sh
```

The script will ask for two things:

```
Enter your BOT_TOKEN (from @BotFather): 7xxxxxxxxx:AAxxxxxxxxxxxxxxxxxxxxxxx
Enter your ADMIN_ID (your Telegram user ID): 123456789
```

**What `setup.sh` does automatically:**
- ✅ Updates system packages (`apt-get update && upgrade`)
- ✅ Installs Python 3, pip, git, screen, curl
- ✅ Creates a Python virtual environment (`venv/`)
- ✅ Installs all bot dependencies from `requirements.txt`
- ✅ Creates data files (`data.json`, `user_proxies.json`, `user_amounts.json`)
- ✅ Saves `BOT_TOKEN` and `ADMIN_ID` permanently to `~/.bashrc`
- ✅ Registers a **systemd service** that auto-starts the bot on every reboot
- ✅ Starts the bot immediately

#### Step 4 — Enable `/restart` and `/reboot` commands (optional)

These admin commands need passwordless sudo access. Run:

```bash
sudo visudo
```

Add this line at the bottom (replace `ubuntu` with your EC2 username if different):

```
ubuntu ALL=(ALL) NOPASSWD: /bin/systemctl restart st-checker-bot, /sbin/reboot
```

Save with `Ctrl+X → Y → Enter`.

#### Step 5 — Verify the bot is running

```bash
# Check if service is active (should say "active (running)")
sudo systemctl status st-checker-bot

# Watch live logs
journalctl -u st-checker-bot -f
```

Send `/ping` to your bot on Telegram — it should reply instantly. ✅

#### Daily-use EC2 commands

```bash
# Check bot status
sudo systemctl status st-checker-bot

# View live logs (Ctrl+C to exit)
journalctl -u st-checker-bot -f

# Restart bot manually
sudo systemctl restart st-checker-bot

# Stop bot
sudo systemctl stop st-checker-bot

# Pull latest code & restart
cd ~/st-checker-bot && git pull && sudo systemctl restart st-checker-bot
```

#### Update the bot (after code changes)

```bash
cd ~/st-checker-bot
git pull
sudo systemctl restart st-checker-bot
```

#### Re-run setup (if something breaks or you want to reinstall)

```bash
cd ~/ST-CHECKER-BOT
bash setup.sh
```

The script is safe to re-run — it skips existing files and updates what's needed.

</details>

---

<details>
<summary><b>🔐 Environment Variables</b></summary>
<br>

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ Yes | Telegram bot token from @BotFather |
| `ADMIN_ID` | ✅ Yes | Your Telegram numeric user ID |
| `H_KEY` | ❌ Optional | API key for `/h` hitter.php (default: `TRIALAPI`) |
| `AH_KEY` | ❌ Optional | API key for `/ah` Auto Hitter (hitter1month.replit.app) |
| `CO_EXT_KEY` | ❌ Optional | API key for `/co` stripe.php (gold-newt) |
| `BASE_URL` | ❌ Optional | Custom domain for keep-alive ping |
| `BASE_URL_PORT` | ❌ Optional | Port for keep-alive (default: 80) |

> **Security Tip:** Never hardcode tokens in your code. Always use environment variables or secret managers.

</details>

---

<details>
<summary><b>📁 Project Structure</b></summary>
<br>

```
ST-CHECKER-BOT/
├── main.py              # Watchdog — auto-restarts bot on crash
├── file1.py             # All bot command handlers
├── gatet.py             # Payment gateway functions
├── database.py          # SQLite database layer
├── keep_alive.py        # Flask uptime server (port 8099)
├── requirements.txt     # Python dependencies
├── setup.sh             # One-click AWS EC2 installer
├── data.json            # User plan data (FREE / VIP)
├── user_proxies.json    # Per-user proxy settings
├── user_amounts.json    # Per-user charge amounts
├── combo.txt            # Cards list for bulk check commands
└── telegram_bot.db      # SQLite database (auto-created)
```

</details>

---

<details>
<summary><b>📦 Requirements</b></summary>
<br>

```
pyTelegramBotAPI
flask
requests
urllib3
cloudscraper
faker
fake-useragent
beautifulsoup4
requests-toolbelt
PyJWT
colorama
pysocks
schedule
tele
```

Install all at once:
```bash
pip install -r requirements.txt
```

</details>

---

<details>
<summary><b>🤝 Contributing</b></summary>
<br>

Pull requests are welcome! For major changes, open an issue first.

1. Fork the project
2. Create your feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

</details>

---

<details>
<summary><b>⚠️ Disclaimer</b></summary>
<br>

This project is for **educational and research purposes only**. The author is not responsible for any misuse of this tool. Always comply with the terms of service of any payment gateway you interact with.

</details>

---

<details>
<summary><b>📄 License</b></summary>
<br>

This project is licensed under the [MIT License](LICENSE).

</details>

---

<div align="center">

Made with ❤️ by [hiaistudent-jpg](https://github.com/hiaistudent-jpg)

⭐ **Star this repo if you found it useful!**

</div>
