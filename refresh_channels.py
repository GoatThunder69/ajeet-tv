#!/usr/bin/env python3
"""Scrape fresh __hdnea__ token + ClearKey pairs from the upstream site
and write /var/www/ajeet-tv/channels.json for AjeetTV."""

import json
import re
import sys
import time
import urllib.request

SRC = "https://ctvlive.pages.dev/sl"
OUT = "/var/www/ajeet-tv/channels.json"
LOG = "/home/thunder/ajeet-tv/refresh.log"

FIELD = {
    "name":     r'name:\s*"([^"]+)"',
    "streamUrl": r'streamUrl:\s*"([^"]+)"',
    "cookie":   r'cookie:\s*"([^"]*)"',
    "keyId":    r'keyId:\s*"([^"]+)"',
    "key":      r'key:\s*"([^"]+)"',
}


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    with open(LOG, "a") as f:
        f.write(line)


def main():
    req = urllib.request.Request(SRC, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")

    channels = []
    hdnea = ""
    for m in re.finditer(r'"(so\d+)"\s*:\s*\{(.*?)\}', html, re.S):
        cid, block = m.group(1), m.group(2)
        fields = {}
        for name, pat in FIELD.items():
            fm = re.search(pat, block)
            fields[name] = fm.group(1) if fm else ""
        if not (fields["streamUrl"] and fields["keyId"] and fields["key"]):
            continue
        if not hdnea and fields["cookie"].startswith("__hdnea__="):
            hdnea = fields["cookie"]
        channels.append({
            "id": cid,
            "name": fields["name"] or cid,
            "url": fields["streamUrl"],
            "keyId": fields["keyId"],
            "key": fields["key"],
        })

    if not channels or not hdnea:
        log(f"FAIL: parsed {len(channels)} channels, hdnea={'yes' if hdnea else 'no'}")
        sys.exit(1)

    exp = re.search(r"exp=(\d+)", hdnea)
    if exp and int(exp.group(1)) < time.time() + 300:
        log(f"FAIL: token already expired (exp={exp.group(1)})")
        sys.exit(1)

    payload = {"hdnea": hdnea, "channels": channels, "updated": int(time.time())}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    import os
    os.replace(tmp, OUT)
    log(f"OK: {len(channels)} channels, token exp={exp.group(1) if exp else '?'}")


if __name__ == "__main__":
    main()
