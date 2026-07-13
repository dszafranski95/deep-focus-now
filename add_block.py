# -*- coding: utf-8 -*-
"""
Dodawanie/odejmowanie blokowanych stron w Deep Focus Now (config.json).

    python add_block.py tiktok.com          # zablokuj domene w trybie pracy
    python add_block.py "jakas fraza"        # zablokuj slowo kluczowe
    python add_block.py --allow t.me         # dodaj do dozwolonych (jak Telegram)
    python add_block.py --remove youtube.com # przestan blokowac te domene
    python add_block.py --work 50 --break 10 # zmien dlugosci pracy/przerwy (min)
"""
import os
import re
import sys
import json
from urllib.parse import urlparse

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def host_of(s):
    u = s if "://" in s else "http://" + s
    h = urlparse(u).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); return
    with open(PATH, encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("block_domains", [])
    d.setdefault("allow_domains", [])
    d.setdefault("block_keywords", [])

    # zmiana czasow
    if "--work" in args:
        d["work_minutes"] = int(args[args.index("--work") + 1]); print("work_minutes =", d["work_minutes"])
    if "--break" in args:
        d["break_minutes"] = int(args[args.index("--break") + 1]); print("break_minutes =", d["break_minutes"])
    if "--work" in args or "--break" in args:
        json.dump(d, open(PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False); return

    if args[0] == "--allow":
        val = host_of(" ".join(args[1:]))
        if val not in d["allow_domains"]:
            d["allow_domains"].append(val); print("[+] dozwolone:", val)
    elif args[0] == "--remove":
        val = host_of(" ".join(args[1:]))
        d["block_domains"] = [x for x in d["block_domains"] if x != val]
        print("[-] usunieto z blokady:", val)
    else:
        val = " ".join(args).strip()
        if " " not in val and "." in val:
            v = host_of(val)
            if v not in d["block_domains"]:
                d["block_domains"].append(v); print("[+] blokada domeny:", v)
        else:
            if val.lower() not in d["block_keywords"]:
                d["block_keywords"].append(val.lower()); print("[+] blokada slowa:", val.lower())

    json.dump(d, open(PATH, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    print("Uwaga: zmiany listy dzialaja po restarcie Deep Focus Now.")


if __name__ == "__main__":
    main()
