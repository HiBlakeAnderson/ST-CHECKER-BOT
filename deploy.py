#!/usr/bin/env python3
"""
deploy.py — Push latest code from Replit to EC2 and restart the bot.
Usage:  python3 deploy.py
"""

import os
import sys
import requests
import base64
import paramiko

EC2_HOST = "13.52.104.120"
EC2_USER = "ubuntu"
KEY_FILE  = os.path.join(os.path.dirname(__file__), "ec2_key.pem")
EC2_DIR   = "/home/ubuntu/st-checker-bot"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = "HiBlakeAnderson/ST-CHECKER-BOT"

FILES = [
    "main.py", "file1.py", "database.py", "gatet.py",
    "keep_alive.py", "setup.sh", "requirements.txt", ".gitignore"
]

def push_to_github():
    """Push updated files to GitHub via API."""
    print("📤 Pushing files to GitHub...")
    BASE = f"https://api.github.com/repos/{REPO}"
    HEAD = {"Authorization": f"token {GITHUB_TOKEN}", "Content-Type": "application/json"}
    workspace = os.path.dirname(os.path.abspath(__file__))
    ok = True
    for fname in FILES:
        fpath = os.path.join(workspace, fname)
        if not os.path.exists(fpath):
            print(f"   ⚠️  Skip (not found): {fname}")
            continue
        with open(fpath, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        r = requests.get(f"{BASE}/contents/{fname}", headers=HEAD)
        payload = {"message": f"Deploy: update {fname}", "content": content}
        if r.status_code == 200:
            payload["sha"] = r.json()["sha"]
        r2 = requests.put(f"{BASE}/contents/{fname}", headers=HEAD, json=payload)
        if r2.status_code in (200, 201):
            print(f"   ✅ {fname}")
        else:
            print(f"   ❌ {fname}: {r2.json().get('message', 'error')}")
            ok = False
    return ok

def ssh_update():
    """SSH into EC2 and pull latest code + restart bot."""
    print(f"\n🔗 Connecting to EC2 ({EC2_HOST})...")
    if not os.path.exists(KEY_FILE):
        print(f"❌ Key file not found: {KEY_FILE}")
        return False

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=EC2_HOST,
            username=EC2_USER,
            key_filename=KEY_FILE,
            timeout=30
        )
        print("   ✅ Connected!")

        commands = [
            f"cd {EC2_DIR} && git pull --rebase origin main",
            "sudo systemctl restart st-checker-bot",
            "sudo systemctl status st-checker-bot --no-pager -l | tail -5"
        ]

        for cmd in commands:
            print(f"\n   $ {cmd}")
            stdin, stdout, stderr = client.exec_command(cmd)
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if out:
                for line in out.splitlines():
                    print(f"     {line}")
            if err:
                for line in err.splitlines():
                    print(f"     ⚠️  {line}")

        client.close()
        print("\n✅ EC2 updated and bot restarted!")
        return True

    except Exception as e:
        print(f"❌ SSH error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("  ST-CHECKER-BOT Deploy Script")
    print("=" * 50)

    # Step 1: Push to GitHub
    if GITHUB_TOKEN:
        github_ok = push_to_github()
    else:
        print("⚠️  GITHUB_TOKEN not set — skipping GitHub push")
        github_ok = True

    # Step 2: SSH update EC2
    ec2_ok = ssh_update()

    print("\n" + "=" * 50)
    if github_ok and ec2_ok:
        print("🎉 Deploy complete!")
    else:
        print("⚠️  Deploy completed with some errors (see above)")
    print("=" * 50)
