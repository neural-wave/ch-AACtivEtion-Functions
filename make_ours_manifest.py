#!/usr/bin/env python3
"""Build a manifest of OUR on-site photos from captures/day1_clean/best_fronts.csv.

One line per garment, same schema as the organisers' manifests, paths relative to the
captures folder: {"garment_id": "g02", "view": "front", "inputs": ["day1_clean/g02/g02_front_1.jpg", ...]}
The best front comes first, then up to --details detail shots (close-ups help the model with
colour, texture and logos). Garments whose folder name is not g01..g15 (x01, x02 ...) are skipped
unless mapped with --alias x01=g11.

  .venv/bin/python make_ours_manifest.py --captures ../captures --out ../captures/ours.jsonl --details 2
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--captures", default="../captures")
    ap.add_argument("--clean", default="day1_clean", help="subfolder with one folder per garment")
    ap.add_argument("--out", default="../captures/ours.jsonl")
    ap.add_argument("--details", type=int, default=8, help="max extra close-up/back shots per garment")
    ap.add_argument("--alias", nargs="*", default=[], help="folder=garment, e.g. x01=g11")
    a = ap.parse_args()

    cap = Path(a.captures)
    clean = cap / a.clean
    alias = dict(kv.split("=") for kv in a.alias)
    rows = list(csv.DictReader(open(clean / "best_fronts.csv")))
    out_rows = []
    for r in rows:
        folder = r["folder"].strip()
        gid = alias.get(folder, folder)
        if not re.fullmatch(r"g\d{2}", gid):
            print(f"  {folder}: not a test id, skipped (use --alias {folder}=gXX to include it)")
            continue
        front = clean / folder / r["best_front"].strip()
        if not front.exists():
            print(f"  {folder}: best front {front.name} not found, skipped")
            continue
        details = sorted(p for p in (clean / folder).glob("*.jpg") if "detail" in p.name.lower())
        backs = sorted(p for p in (clean / folder).glob("*.jpg") if "back" in p.name.lower() and "detail" not in p.name.lower())
        inputs = [front] + (details + backs[:1])[: a.details]     # close-ups first, then at most one back view
        out_rows.append({"garment_id": gid, "view": "front",
                         "inputs": [str(p.relative_to(cap)).replace("\\", "/") for p in inputs]})
        print(f"  {gid}: {front.name} + {len(inputs) - 1} extra")
    out_rows.sort(key=lambda x: x["garment_id"])
    Path(a.out).write_text("".join(json.dumps(x) + "\n" for x in out_rows))
    print(f"\n{len(out_rows)} garments -> {a.out}")


if __name__ == "__main__":
    main()
