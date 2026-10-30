#!/usr/bin/env python3
"""AjeetTV watchdog: verify the stream chain end-to-end and auto-fix.

Runs via cron. Fetches a real manifest using the current token with NO
Referer (CDN rejects any Referer). On failure it re-runs the channel
refresher once and retests. Writes /var/www/ajeet-tv/status.json.
"""

import json
import subprocess
import sys
import time
import urllib.request

CH = "/var/www/ajeet-tv/channels.json"
STATUS = "/var/www/ajeet-tv/status.json"
LOG = "/home/thunder/ajeet-tv/refresh.log"
REFRESH = "/home/thunder/ajeet-tv/refresh_channels.py"


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} HEALTH {msg}\n")


def manifest_ok(url, tok):
    req = urllib.request.Request(url + "?" + tok)
    # no Referer header on purpose
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status == 200 and b"<MPD" in r.read(4096)
    except Exception:
        return False


def write_status(ok, detail):
    tmp = STATUS + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"ok": ok, "detail": detail, "checked": int(time.time())}, f)
    import os
    os.replace(tmp, STATUS)


def main():
    try:
        d = json.load(open(CH))
    except Exception as e:
        write_status(False, f"channels.json unreadable: {e}")
        subprocess.run([sys.executable, REFRESH])
        log("channels.json unreadable -> ran refresh")
        return

    # sample a jiotvmblive channel (so3 if present)
    ch = next((c for c in d["channels"] if c["id"] == "so3"), d["channels"][0])
    tok = d["hdnea"]

    if manifest_ok(ch["url"], tok):
        write_status(True, "manifest 200")
        log(f"OK {ch['id']}")
        return

    # probably a rotated/dead token — refresh immediately and retest
    subprocess.run([sys.executable, REFRESH], timeout=90)
    try:
        d = json.load(open(CH))
    except Exception:
        write_status(False, "refresh produced no json")
        log("refresh produced no json")
        return
    tok = d["hdnea"]

    ok = manifest_ok(ch["url"], tok)
    write_status(ok, "manifest 200 after refresh" if ok else "manifest still failing")
    log(f"{'OK-after-refresh' if ok else 'STILL-FAILING'} {ch['id']}")


if __name__ == "__main__":
    main()
