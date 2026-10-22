#!/usr/bin/env python3
"""Refresh AjeetTV channels.json.

Sources:
  1. ctvlive.pages.dev/sl  -> shared __hdnea__ token (acl=/*, rotates ~6h)
  2. sixpg/zeyo jtv.m3u    -> full JioTV catalog (urls, clearkeys, logos,
                              per-channel cookies, also a token source)

Writes /var/www/ajeet-tv/channels.json:
  {"hdnea": <freshest acl=/* token>, "channels": [...], "updated": ts}
"""

import json
import re
import sys
import time
import urllib.request

CTV = "https://ctvlive.pages.dev/sl"
M3U = "https://raw.githubusercontent.com/sixpg/zeyo/refs/heads/main/jtv.m3u"
OUT = "/var/www/ajeet-tv/channels.json"
LOG = "/home/thunder/ajeet-tv/refresh.log"
MBLIVE = "jiotvmblive.cdn.jio.com"

UA = {"User-Agent": "Mozilla/5.0"}


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "replace")


def exp_of(token):
    m = re.search(r"exp=(\d+)", token or "")
    return int(m.group(1)) if m else 0


def block_field(block, name):
    m = re.search(name + r':\s*"([^"]*)"', block)
    return m.group(1) if m else ""


def scrape_ctvlive(html):
    """Return (hdnea, [{id,name,url,keyId,key}]) from the /sl page."""
    hdnea, channels = "", []
    for m in re.finditer(r'"(so\d+)"\s*:\s*\{(.*?)\}', html, re.S):
        cid, block = m.group(1), m.group(2)
        url = block_field(block, "streamUrl")
        kid = block_field(block, "keyId")
        key = block_field(block, "key")
        ck = block_field(block, "cookie")
        if not hdnea and ck.startswith("__hdnea__="):
            hdnea = ck
        if url and kid and key:
            channels.append({"id": cid, "name": block_field(block, "name") or cid,
                             "url": url, "keyId": kid, "key": key})
    return hdnea, channels


def parse_m3u(text):
    """Parse the jtv.m3u into channel dicts + best token seen."""
    entries, cur, best_tok = [], {}, ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTINF"):
            g = re.search(r'group-title="([^"]*)"', line)
            l = re.search(r'tvg-logo="([^"]*)"', line)
            n = line.rsplit(",", 1)[-1]
            tid = re.search(r'tvg-id="([^"]*)"', line)
            cur = {"name": n, "group": g.group(1) if g else "",
                   "logo": l.group(1) if l else "",
                   "tvgid": tid.group(1) if tid else ""}
        elif line.startswith("#KODIPROP:inputstream.adaptive.license_key="):
            kv = line.split("=", 1)[1]
            if ":" in kv:
                cur["keyId"], cur["key"] = kv.split(":", 1)
        elif line.startswith("#EXTHTTP:"):
            m = re.search(r'(__hdnea__=[^"}]+)', line)
            if m:
                cur["cookie"] = m.group(1)
                if MBLIVE in (cur.get("url") or "") or "acl=/*" in cur["cookie"]:
                    if exp_of(cur["cookie"]) > exp_of(best_tok):
                        best_tok = cur["cookie"]
        elif line.startswith("http"):
            cur["url"] = line.split("?")[0]
            if exp_of(cur.get("cookie")) > exp_of(best_tok) and MBLIVE in cur["url"]:
                best_tok = cur["cookie"]
            entries.append(cur)
            cur = {}
    return entries, best_tok


def main():
    errors = []
    try:
        ctv_tok, so_chans = scrape_ctvlive(fetch(CTV))
    except Exception as e:
        ctv_tok, so_chans = "", []
        errors.append(f"ctvlive: {e}")

    try:
        entries, m3u_tok = parse_m3u(fetch(M3U))
    except Exception as e:
        entries, m3u_tok = [], ""
        errors.append(f"m3u: {e}")

    # Shared token = freshest acl=/* token from either source.
    hdnea = max([ctv_tok, m3u_tok], key=exp_of)
    if exp_of(hdnea) < time.time() + 300:
        log("FAIL: all tokens expired")
        sys.exit(1)

    so_by_url = {c["url"].split("?")[0]: c for c in so_chans}
    seen_urls, channels = set(), []

    def add(ch, cid):
        u = ch["url"].split("?")[0]
        if u in seen_urls:
            return
        seen_urls.add(u)
        channels.append({**ch, "id": cid, "url": u})

    # so* channels first (keep stable ids for ?id=so3 links).
    for c in so_chans:
        add(c, c["id"])

    # Then the full JioTV catalog (any host — carries its own cookie).
    for e in entries:
        url = e.get("url", "")
        if not (url and e.get("keyId") and e.get("key")):
            continue
        base = url.split("?")[0]
        so = so_by_url.get(base)
        if so:
            # enrich the so* entry with logo/group
            for ch in channels:
                if ch["id"] == so["id"]:
                    ch.update({"name": e["name"], "group": e["group"], "logo": e["logo"]})
            continue
        cid = "z" + (e.get("tvgid") or str(len(channels)))
        ch = {"id": cid, "name": e["name"], "url": base,
              "keyId": e["keyId"], "key": e["key"],
              "group": e.get("group", ""), "logo": e.get("logo", "")}
        if MBLIVE not in base and e.get("cookie"):
            ch["cookie"] = e["cookie"]  # per-host token needed
        channels.append(ch)
        seen_urls.add(base)

    if not channels:
        log("FAIL: 0 channels")
        sys.exit(1)

    payload = {"hdnea": hdnea, "channels": channels, "updated": int(time.time())}
    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    import os
    os.replace(tmp, OUT)
    log(f"OK: {len(channels)} channels ({len(so_chans)} sony), token exp={exp_of(hdnea)}, "
        f"errors={len(errors)} {';'.join(errors)}")


if __name__ == "__main__":
    main()
