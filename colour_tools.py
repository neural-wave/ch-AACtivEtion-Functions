#!/usr/bin/env python3
"""Colour tools for the Sartiq challenge: diagnose, calibrate, apply, select.

All commands find the garment with the scorer's own segmenter (rembg u2net) and
work in Lab colour space (L = brightness, a = green/red, b = blue/yellow).

  diagnose   measure the garment colour of AI pictures vs the true shop photos
             -> a CSV with one line per pair: median L, a, b of both, and the gap
  calibrate  turn a diagnose CSV into a correction (the AI's systematic bias)
             -> calibration.json
  apply      shift the garment colour of every AI picture by a correction
             (from calibration.json or a manual --shift), background untouched
  combine    learn how to predict the true colour from the AI picture AND the
             phone photo (two noisy measurements), write a per-garment shift
  select     among several candidate pictures per garment, keep the one whose
             colour is closest to the group's median (random drift cancels out)

Run from the repo root with the challenge Python, e.g.
  .venv/bin/python colour_tools.py diagnose --manifest holdout/val.jsonl --preds predictions --team hosted --out val_out/diag_hosted.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps
from skimage import color as skcolor

from sartiq_score.segment import segment

WORK_SIDE = 768


# ----------------------------------------------------------------------------- helpers
def load_rgb(path: Path) -> np.ndarray:
    return np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("RGB"))


def small(arr: np.ndarray, side: int = WORK_SIDE) -> np.ndarray:
    h, w = arr.shape[:2]
    s = side / max(h, w)
    if s >= 1:
        return arr
    return np.asarray(Image.fromarray(arr).resize((max(1, int(w * s)), max(1, int(h * s))), Image.LANCZOS))


def garment_median_lab(arr: np.ndarray) -> tuple[np.ndarray, float]:
    """Median (L, a, b) of the garment pixels, and the garment's share of the image."""
    a = small(arr)
    m = segment(a) > 0.5
    if m.sum() < 200:
        return np.array([np.nan] * 3), float(m.mean())
    lab = skcolor.rgb2lab(a / 255.0)[m]
    return np.median(lab, axis=0), float(m.mean())


def find_pred(root: Path, team: str, gid: str, view: str = "front") -> Path | None:
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = root / team / gid / f"{view}.{ext}"
        if p.exists():
            return p
    return None


def read_rows(manifest: Path) -> list[dict]:
    rows = [json.loads(l) for l in open(manifest) if l.strip()]
    for r in rows:
        r["id"] = r.get("garment_id") or r.get("pair_id")
    return rows


def shift_garment(arr: np.ndarray, dL: float, da: float, db: float) -> np.ndarray:
    """Add (dL, da, db) to the garment pixels only, with a soft edge."""
    mask = segment(arr) if max(arr.shape[:2]) <= 2048 else np.asarray(
        Image.fromarray((segment(small(arr, 2048)) * 255).astype(np.uint8)).resize(
            (arr.shape[1], arr.shape[0]), Image.BILINEAR)) / 255.0
    lab = skcolor.rgb2lab(arr / 255.0)
    lab += np.clip(mask, 0, 1)[..., None] * np.array([dL, da, db], dtype=np.float64)
    return np.clip(skcolor.lab2rgb(lab) * 255.0 + 0.5, 0, 255).astype(np.uint8)


# ----------------------------------------------------------------------------- diagnose
def cmd_diagnose(a: argparse.Namespace) -> None:
    data, preds = Path(a.dataset), Path(a.preds)
    rows = read_rows(Path(a.manifest))
    out_rows = []
    for r in rows:
        p = find_pred(preds, a.team, r["id"])
        if p is None:
            continue
        ai, frac_ai = garment_median_lab(load_rgb(p))
        phone, _ = garment_median_lab(load_rgb(data / r["inputs"][0]))
        if "target" in r:
            truth, frac_t = garment_median_lab(load_rgb(data / r["target"]))
        else:                                    # dev/test: no truth available
            truth, frac_t = np.array([np.nan] * 3), np.nan
        d = ai - truth
        out_rows.append({"id": r["id"], "ai_L": ai[0], "ai_a": ai[1], "ai_b": ai[2],
                         "true_L": truth[0], "true_a": truth[1], "true_b": truth[2],
                         "phone_L": phone[0], "phone_a": phone[1], "phone_b": phone[2],
                         "dL": d[0], "da": d[1], "db": d[2], "mask_ai": frac_ai, "mask_true": frac_t})
        if "target" in r:
            print(f"  {r['id']}: AI - truth  L {d[0]:+5.1f}  a {d[1]:+5.1f}  b {d[2]:+5.1f}")
        else:
            print(f"  {r['id']}: AI L {ai[0]:5.1f} a {ai[1]:+5.1f} b {ai[2]:+5.1f} | phone L {phone[0]:5.1f} a {phone[1]:+5.1f} b {phone[2]:+5.1f}")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)
    D = np.array([[r["dL"], r["da"], r["db"]] for r in out_rows])
    D = D[~np.isnan(D).any(1)]
    print(f"\n{len(out_rows)} pairs measured -> {a.out}")
    if len(D) == 0:
        return
    print("AI minus truth, median bias :  L %+.1f   a %+.1f   b %+.1f" % tuple(np.median(D, 0)))
    print("AI minus truth, typical size:  L %5.1f   a %5.1f   b %5.1f   (mean absolute)" % tuple(np.abs(D).mean(0)))
    print("Reading: a positive L bias means the AI makes garments too bright; positive b = too yellow;"
          " positive a = too red.")


# ----------------------------------------------------------------------------- calibrate
def cmd_calibrate(a: argparse.Namespace) -> None:
    rows = list(csv.DictReader(open(a.diag)))
    D = np.array([[float(r["dL"]), float(r["da"]), float(r["db"])] for r in rows])
    D = D[~np.isnan(D).any(1)]
    bias = np.median(D, 0)                       # robust to a few bad pairs
    shift = (-bias * a.strength).tolist()        # correction = minus the bias
    calib = {"n_pairs": int(len(D)), "bias_L_a_b": bias.tolist(), "strength": a.strength,
             "shift_L_a_b": shift, "source": a.diag}
    json.dump(calib, open(a.out, "w"), indent=2)
    print(f"learned from {len(D)} pairs: AI bias L {bias[0]:+.1f}  a {bias[1]:+.1f}  b {bias[2]:+.1f}")
    print(f"correction to apply (x{a.strength}):  L {shift[0]:+.1f}  a {shift[1]:+.1f}  b {shift[2]:+.1f}  -> {a.out}")


# ----------------------------------------------------------------------------- apply
def cmd_apply(a: argparse.Namespace) -> None:
    per_id: dict[str, tuple[float, float, float]] = {}
    if a.calib:
        dL, da, db = json.load(open(a.calib))["shift_L_a_b"]
    elif a.shifts_csv:
        for r in csv.DictReader(open(a.shifts_csv)):
            per_id[r["id"]] = (float(r["dL"]), float(r["da"]), float(r["db"]))
        dL = da = db = 0.0
    else:
        dL, da, db = (float(x) for x in a.shift.split(","))
    preds, out = Path(a.preds), Path(a.out)
    rows = read_rows(Path(a.manifest))
    n = 0
    for r in rows:
        p = find_pred(preds, a.team, r["id"])
        dst = out / a.team_out / r["id"] / "front.png"
        dst.parent.mkdir(parents=True, exist_ok=True)
        if p is None:
            print(f"  {r['id']}: no picture, skipped")
            continue
        sL, sa, sb = per_id.get(r["id"], (dL, da, db))
        try:
            Image.fromarray(shift_garment(load_rgb(p), sL, sa, sb)).save(dst)
            if per_id:
                print(f"  {r['id']}: L {sL:+.1f} a {sa:+.1f} b {sb:+.1f}")
        except Exception as e:           # never lose a garment
            shutil.copy(p, dst.with_suffix(p.suffix))
            print(f"  {r['id']}: error, copied unchanged ({str(e)[:80]})")
        n += 1
    if per_id:
        print(f"{n} pictures shifted (per garment) -> {out / a.team_out}")
    else:
        print(f"{n} pictures shifted by L {dL:+.1f} a {da:+.1f} b {db:+.1f} -> {out / a.team_out}")


# ----------------------------------------------------------------------------- select
def cmd_select(a: argparse.Namespace) -> None:
    preds, out = Path(a.preds), Path(a.out)
    rows = read_rows(Path(a.manifest))
    teams = a.teams.split(",")
    for r in rows:
        cands = [(t, find_pred(preds, t, r["id"])) for t in teams]
        cands = [(t, p) for t, p in cands if p is not None]
        dst_dir = out / a.team_out / r["id"]
        dst_dir.mkdir(parents=True, exist_ok=True)
        if not cands:
            print(f"  {r['id']}: no candidates")
            continue
        labs = []
        for t, p in cands:
            lab, _ = garment_median_lab(load_rgb(p))
            labs.append(lab)
        L = np.array(labs)
        centre = np.nanmedian(L, 0)
        dist = np.sqrt(np.nansum((L - centre) ** 2, 1))
        best = int(np.nanargmin(dist))
        t, p = cands[best]
        shutil.copy(p, dst_dir / f"front{p.suffix}")
        print(f"  {r['id']}: kept {t}  (distance to group median {dist[best]:.1f}; others "
              + ", ".join(f"{c[0]}={d:.1f}" for c, d in zip(cands, dist) if c[0] != t) + ")")
    print(f"-> {out / a.team_out}")


# ----------------------------------------------------------------------------- combine
def _fit_channel(train: list[dict], ch: str, ridge: float = 1.0) -> np.ndarray:
    """Least squares: true = w0 + w1*ai + w2*phone, per channel (small ridge for stability)."""
    X = np.array([[1.0, float(r[f"ai_{ch}"]), float(r[f"phone_{ch}"])] for r in train])
    y = np.array([float(r[f"true_{ch}"]) for r in train])
    ok = ~np.isnan(X).any(1) & ~np.isnan(y)
    X, y = X[ok], y[ok]
    R = np.eye(3) * ridge
    R[0, 0] = 0.0
    return np.linalg.solve(X.T @ X + R, X.T @ y)


def cmd_combine(a: argparse.Namespace) -> None:
    train = list(csv.DictReader(open(a.fit)))
    target = list(csv.DictReader(open(a.diag)))
    W = {ch: _fit_channel(train, ch) for ch in "Lab"}
    for ch in "Lab":
        w = W[ch]
        print(f"channel {ch}: true = {w[0]:+.2f} + {w[1]:.2f} * AI + {w[2]:.2f} * phone")
    # how good is the combination on the fitting pairs? (optimistic, but informative)
    for name, pick in (("AI alone", lambda r, ch: float(r[f"ai_{ch}"])),
                       ("phone alone", lambda r, ch: float(r[f"phone_{ch}"])),
                       ("combined", lambda r, ch: float(np.dot(W[ch], [1, float(r[f"ai_{ch}"]), float(r[f"phone_{ch}"])])))):
        errs = []
        for r in train:
            try:
                errs.append([abs(pick(r, ch) - float(r[f"true_{ch}"])) for ch in "Lab"])
            except ValueError:
                pass
        e = np.nanmean(np.array(errs), 0)
        print(f"  mean abs error on fitting pairs, {name:<12} L {e[0]:4.1f}  a {e[1]:4.1f}  b {e[2]:4.1f}")
    out_rows = []
    for r in target:
        row = {"id": r["id"]}
        for ch, key in zip("Lab", ("dL", "da", "db")):
            ai, ph = float(r[f"ai_{ch}"]), float(r[f"phone_{ch}"])
            if np.isnan(ai) or np.isnan(ph):
                row[key] = 0.0
                continue
            pred = float(np.dot(W[ch], [1, ai, ph]))
            row[key] = a.strength * (pred - ai)
        out_rows.append(row)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["id", "dL", "da", "db"])
        w.writeheader()
        w.writerows(out_rows)
    print(f"per-garment shifts for {len(out_rows)} garments -> {a.out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose")
    d.add_argument("--manifest", required=True, help="a manifest WITH targets (holdout val or train)")
    d.add_argument("--dataset", default="../sartiq_neural_wave_2026")
    d.add_argument("--preds", required=True)
    d.add_argument("--team", required=True)
    d.add_argument("--out", required=True, help="CSV to write")
    d.set_defaults(fn=cmd_diagnose)

    c = sub.add_parser("calibrate")
    c.add_argument("--diag", required=True, help="CSV from diagnose (use TRAIN pairs, not the exam set)")
    c.add_argument("--strength", type=float, default=1.0, help="1 = remove the full bias, 0.5 = half")
    c.add_argument("--out", default="calibration.json")
    c.set_defaults(fn=cmd_calibrate)

    p = sub.add_parser("apply")
    p.add_argument("--manifest", required=True)
    p.add_argument("--preds", required=True)
    p.add_argument("--team", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--team-out", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--calib", help="calibration.json from calibrate")
    g.add_argument("--shift", help="manual 'dL,da,db', e.g. '-3,0,-2'")
    g.add_argument("--shifts-csv", help="per-garment shifts: columns id,dL,da,db (from 'combine')")
    p.set_defaults(fn=cmd_apply)

    k = sub.add_parser("combine", help="predict each garment's true colour from AI + phone, write per-garment shifts")
    k.add_argument("--fit", required=True, help="diagnose CSV WITH truth (training pairs) to learn the weights")
    k.add_argument("--diag", required=True, help="diagnose CSV of the pictures to correct (truth may be missing)")
    k.add_argument("--strength", type=float, default=1.0)
    k.add_argument("--out", required=True, help="shifts CSV for 'apply --shifts-csv'")
    k.set_defaults(fn=cmd_combine)

    s = sub.add_parser("select")
    s.add_argument("--manifest", required=True)
    s.add_argument("--preds", required=True)
    s.add_argument("--teams", required=True, help="comma-separated candidate team folders")
    s.add_argument("--out", required=True)
    s.add_argument("--team-out", required=True)
    s.set_defaults(fn=cmd_select)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
