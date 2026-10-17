#!/usr/bin/env python3
"""Post-processing experiment on the exam set: does any cheap image operation raise the official score?

Variants applied to each AI picture (predictions/<team>/<id>/front.png), scored against the real
references with the official scorer:
  raw         unchanged
  flat_s05    remove 50% of the low-frequency shading inside the garment (texture kept)
  flat_s10    remove 100% of it
  flat_wide   same, with a wider blur (only the broadest light gradients)
  whitebg     force the background to pure white outside the garment mask
  unsharp     mild unsharp mask

  .venv/bin/python post_experiment.py --pairs holdout/val.jsonl --preds predictions --team hosted_p2
"""
from __future__ import annotations
import argparse, json, tempfile, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from skimage import color as skcolor
from scipy import ndimage
from sartiq_score.api import score_pair
from sartiq_score.segment import segment


def flatfield(arr, sigma_frac=0.08, strength=1.0):
    m = segment(arr) > 0.5
    if m.sum() < 500:
        return arr
    lab = skcolor.rgb2lab(arr / 255.0)
    L = lab[..., 0]
    sig = sigma_frac * max(arr.shape[:2])
    num = ndimage.gaussian_filter(L * m, sig)
    den = ndimage.gaussian_filter(m.astype(float), sig) + 1e-6
    low = num / den
    lab[..., 0] = np.clip(L + strength * m * (L[m].mean() - low), 0, 100)
    return np.clip(skcolor.lab2rgb(lab) * 255 + 0.5, 0, 255).astype(np.uint8)


def whitebg(arr):
    m = np.clip(segment(arr), 0, 1)[..., None]
    return np.clip(arr * m + 255 * (1 - m) + 0.5, 0, 255).astype(np.uint8)


def unsharp(arr):
    return np.asarray(Image.fromarray(arr).filter(ImageFilter.UnsharpMask(radius=3, percent=60, threshold=2)))


VARIANTS = {
    "raw": lambda a: a,
    "flat_s05": lambda a: flatfield(a, 0.08, 0.5),
    "flat_s10": lambda a: flatfield(a, 0.08, 1.0),
    "flat_wide": lambda a: flatfield(a, 0.15, 0.5),
    "whitebg": whitebg,
    "unsharp": unsharp,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="holdout/val.jsonl")
    ap.add_argument("--dataset", default="../sartiq_neural_wave_2026")
    ap.add_argument("--preds", default="predictions")
    ap.add_argument("--team", default="hosted_p2")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--variants", default=",".join(VARIANTS))
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.pairs) if l.strip()][: a.limit]
    names = a.variants.split(",")
    res = {k: [] for k in names}
    subs = {k: [] for k in names}
    with tempfile.TemporaryDirectory() as tmp:
        for i, r in enumerate(rows):
            src = Path(a.preds) / a.team / r["pair_id"] / "front.png"
            if not src.exists():
                continue
            arr = np.asarray(Image.open(src).convert("RGB"))
            ref = Path(a.dataset) / r["target"]
            line = [r["pair_id"]]
            for k in names:
                p = Path(tmp) / f"{k}.png"
                Image.fromarray(VARIANTS[k](arr)).save(p)
                rep = score_pair(str(ref), str(p))
                res[k].append(rep.score); subs[k].append(rep.subscores)
                line.append(f"{k}={rep.score:.1f}")
            print(f"  [{i+1}/{len(rows)}] " + "  ".join(line), flush=True)
    print(f"\n{'variant':<12}{'SCORE':>7}{'colour':>8}{'lpips':>7}{'clip':>7}{'shape':>7}{'ssim':>7}   (n={len(res[names[0]])})")
    for k in names:
        m = {s: float(np.mean([x[s] for x in subs[k]])) for s in ("colour", "lpips", "clip", "geometry", "ssim")}
        print(f"{k:<12}{np.mean(res[k]):7.2f}{m['colour']:8.3f}{m['lpips']:7.3f}{m['clip']:7.3f}{m['geometry']:7.3f}{m['ssim']:7.3f}")
    json.dump({"scores": res, "subscores": subs}, open("post_experiment.json", "w"))


if __name__ == "__main__":
    main()
