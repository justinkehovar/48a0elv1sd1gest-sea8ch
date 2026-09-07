#!/usr/bin/env python3
"""Refresh bid/retail on digest HTML cards (GitHub Actions friendly)."""
from __future__ import annotations

import concurrent.futures
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = {"User-Agent": "Mozilla/5.0 (compatible; ElvisDigest/1.0)"}


def money(x):
    if x is None:
        return "—"
    if float(x) == int(float(x)):
        return f"${int(float(x))}"
    return f"${float(x):.2f}"


def fetch_price(pid: str):
    for attempt in range(3):
        try:
            req = urllib.request.Request(f"https://nellisauction.com/p/x/{pid}", headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                page = r.read().decode("utf-8", "ignore")
            meta = re.search(r'name="description" content="([^"]+)"', page)
            bid = retail = None
            if meta:
                m = re.search(r"Sold for \$([0-9.]+)\s*\|\s*Retail:\s*\$([0-9.]+)", meta.group(1))
                if m:
                    bid, retail = float(m.group(1)), float(m.group(2))
            return pid, bid, retail
        except Exception:
            time.sleep(0.4 * (attempt + 1))
    return pid, None, None


def page_ids(html: str):
    ids = re.findall(r"nellisauction\.com/p/[^/]+/(\d+)", html)
    out, seen = [], set()
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def apply_prices(html: str, prices: dict) -> str:
    parts = re.split(r'(<a class="card" href="https://nellisauction\.com/p/[^"]+")', html)
    out = [parts[0]]
    i = 1
    while i < len(parts):
        head = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        m = re.search(r'/(\d+)"$', head)
        pid = m.group(1) if m else None
        if pid and pid in prices and prices[pid].get("retail") is not None:
            bid = prices[pid].get("bid")
            retail = prices[pid]["retail"]
            ratio = ""
            if bid is not None and retail:
                ratio = f'<span class="pct">{100 * float(bid) / float(retail):.0f}% of retail</span>'
            body = re.sub(
                r'<div class="prices">.*?</div>',
                f'<div class="prices"><span class="bid">Bid {money(bid)}</span><span class="retail">Retail {money(retail)}</span>{ratio}</div>',
                body,
                count=1,
                flags=re.S,
            )
        out.append(head + body)
        i += 2
    return "".join(out)


def stamp(html: str) -> str:
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    note = f" · bids refreshed {when}"
    if "bids refreshed" in html:
        return re.sub(r" · bids refreshed[^<]*", note, html, count=1)
    return re.sub(
        r'(<p class="subhead">)(.*?)(</p>)',
        lambda m: m.group(1) + m.group(2) + note + m.group(3),
        html,
        count=1,
        flags=re.S,
    )


def main():
    files = [p for p in [ROOT / "index.html", ROOT / "dallas.html"] if p.exists()]
    ids = []
    for f in files:
        ids.extend(page_ids(f.read_text()))
    ids = list(dict.fromkeys(ids))
    print(f"refreshing {len(ids)} lots")
    prices = {}
    ok = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        for pid, bid, retail in ex.map(fetch_price, ids):
            prices[pid] = {"bid": bid, "retail": retail}
            if retail is not None:
                ok += 1
    print(f"priced {ok}/{len(ids)}")
    for f in files:
        html = stamp(apply_prices(f.read_text(), prices))
        f.write_text(html)
        print("updated", f.name)


if __name__ == "__main__":
    main()
