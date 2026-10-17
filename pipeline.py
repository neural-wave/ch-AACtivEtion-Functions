#!/usr/bin/env python3
"""Final pipeline: phone capture(s) of a garment -> studio flat-lay packshot.

For every garment in a manifest:
  1. send the FRONT photo plus up to --max-inputs extra photos (detail / back shots) to the
     hosted edit model with a packshot prompt;
  2. do that --candidates times (independent generations);
  3. keep the candidate whose garment colour is closest to the group's median colour
     (random colour drift of the generator cancels out);
  4. write <out>/<team>/<garment_id>/front.png.
Garments missing from the manifest can be filled from another submission folder
(--fill-from), so every id gets a picture.

Candidates are kept in <out>/_candidates/<team>/<id>/cand_<k>.png and are never regenerated
if they already exist, so a rerun never pays twice.

  .venv/bin/python pipeline.py --manifest ../captures/ours.jsonl --dataset ../captures \
      --out submissions_final --team aactivetion_function --candidates 3 --max-inputs 3 \
      --fill-from submissions/aactivetion_function --fill-ids ../sartiq_neural_wave_2026/test/inputs.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "baselines"))
sys.path.insert(0, str(HERE))

from baseline_nanobanana import (  # noqa: E402  (the organisers' provider code, reused)
    DEFAULT_FAL_MODEL, FAL_QUEUE_BASE, TransientError, _save_png, api_key,
    fal_generate, redact,
)

PROMPT = (
    "Create a professional e-commerce flat-lay packshot of this exact garment. "
    "Lay it perfectly flat on a pure white background, photographed straight from above, "
    "centred, collar at the top, sleeves spread slightly away from the body, symmetric, "
    "no wrinkles, hem straight. Keep the garment's exact colour, brightness, fabric texture, "
    "print, logo and proportions; do not change, add or remove any detail. Remove the person, "
    "hanger, mannequin, floor, table, paper and background. Even soft studio light, no shadows, "
    "sharp focus on the fabric weave. Output only the packshot."
)
PROMPT_MULTI = (
    " The first image is the front view to reproduce; the other images are close-ups or other "
    "views of the same garment: use them only to get the colour, fabric texture, print and logo "
    "exactly right."
)


def load_rows(manifest: Path) -> list[dict]:
    rows = [json.loads(l) for l in open(manifest) if l.strip()]
    for r in rows:
        r["id"] = r.get("garment_id") or r.get("pair_id")
    return rows


def prep_uri(path: Path, max_side: int = 2048) -> str:
    """Phone photo -> upright, at most max_side px, JPEG data URI (keeps uploads small)."""
    import base64
    import io
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=92)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def generate_one(images: list[Path], prompt: str, key: str, model: str, timeout: float,
                 retries: int) -> bytes:
    payload = {"prompt": prompt, "image_urls": [prep_uri(p) for p in images]}
    # Nano Banana 2.1 options: thinking level minimal|medium|high (default medium).
    if os.environ.get("NB_THINKING"):
        payload["thinking_level"] = os.environ["NB_THINKING"]
    body = json.dumps(payload).encode("utf-8")
    url = f"{FAL_QUEUE_BASE}/{model}"
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return fal_generate(url, body, key, timeout)
        except TransientError as e:
            last = e
            print(f"    transient error, retry {attempt + 1}/{retries}: {redact(e, [key])}", file=sys.stderr)
            time.sleep(3)
    raise RuntimeError(str(last))


def _shape_quality(mask: np.ndarray) -> tuple[float, float]:
    """(left-right symmetry 0..1, tilt in degrees) of a garment mask."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 200:
        return 0.0, 0.0
    cx = int(round(xs.mean()))
    half = min(cx, mask.shape[1] - cx - 1)
    left = mask[:, cx - half:cx][:, ::-1]
    right = mask[:, cx + 1:cx + 1 + half]
    sym = float((left & right).sum() / max(1, (left | right).sum()))
    x, y = xs - xs.mean(), ys - ys.mean()
    w, v = np.linalg.eigh(np.cov(np.stack([x, y])))
    ax = v[:, np.argmax(w)]
    tilt = float(((np.degrees(np.arctan2(ax[0], ax[1])) + 90) % 180) - 90)
    if abs(tilt) > 45:          # major axis horizontal (wide garment): measure against horizontal
        tilt = tilt - 90 if tilt > 0 else tilt + 90
    return sym, tilt


def pick_consensus(cands: list[Path]) -> tuple[Path, list[str]]:
    """Colour-consistent AND straight: candidates near the group's median colour, best symmetry wins."""
    from colour_tools import garment_median_lab, load_rgb, small
    from sartiq_score.segment import segment
    labs, syms, tilts = [], [], []
    for p in cands:
        rgb = load_rgb(p)
        labs.append(garment_median_lab(rgb)[0])
        sym, tilt = _shape_quality(segment(small(rgb)) > 0.5)
        syms.append(sym)
        tilts.append(tilt)
    labs = np.array(labs)
    dist = np.sqrt(np.nansum((labs - np.nanmedian(labs, 0)) ** 2, 1))
    # penalty: colour distance (Lab units) + lack of symmetry + tilt; weights chosen so 3 Lab ~ 0.03 sym ~ 3 deg
    penalty = dist / 3.0 + (1.0 - np.array(syms)) / 0.03 + np.abs(tilts) / 3.0
    best = int(np.nanargmin(penalty))
    notes = [f"{p.name}: colour {d:.1f}, symmetry {s:.3f}, tilt {t:+.1f}deg" for p, d, s, t in zip(cands, dist, syms, tilts)]
    return cands[best], notes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--dataset", required=True, help="root the manifest's paths are relative to")
    ap.add_argument("--out", required=True)
    ap.add_argument("--team", required=True)
    ap.add_argument("--candidates", type=int, default=3)
    ap.add_argument("--max-inputs", type=int, default=3, help="photos per garment sent to the model (front first)")
    ap.add_argument("--model", default=DEFAULT_FAL_MODEL)
    ap.add_argument("--prompt", default=None, help="override the built-in prompt")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--retries", type=int, default=2)
    ap.add_argument("--limit", type=int, default=None, help="only the first N garments")
    ap.add_argument("--workers", type=int, default=4, help="parallel requests to the model (4 is safe)")
    ap.add_argument("--notes", default=None, help="JSON {garment_id: extra instruction} appended to the prompt per garment")
    ap.add_argument("--only", default=None, help="comma-separated garment ids to process (others untouched)")
    ap.add_argument("--tag", default="", help="candidate name prefix, e.g. r -> cand_r0.png (keeps earlier candidates)")
    ap.add_argument("--picks", default=None, help="CSV gid,file: force this candidate file instead of the automatic pick")
    ap.add_argument("--fill-from", default=None, help="submission folder to copy missing garments from")
    ap.add_argument("--fill-ids", default=None, help="manifest listing every id that must exist (dev/test inputs.jsonl)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be sent, call nothing")
    a = ap.parse_args()

    data, out = Path(a.dataset), Path(a.out)
    rows = load_rows(Path(a.manifest))
    if a.only:
        keep = {x.strip() for x in a.only.split(",")}
        rows = [r for r in rows if r["id"] in keep]
    if a.limit:
        rows = rows[: a.limit]
    notes = json.load(open(a.notes)) if a.notes else {}
    picks = {}
    if a.picks and Path(a.picks).exists():
        import csv as _csv
        picks = {r["gid"].strip(): r["file"].strip() for r in _csv.DictReader(open(a.picks)) if r.get("gid")}
    key = None if a.dry_run else api_key("fal")
    cand_root = out / "_candidates" / a.team
    out.mkdir(parents=True, exist_ok=True)
    log = open(out / "_pipeline_log.jsonl", "a") if not a.dry_run else None

    # ---- phase 1: generate every missing candidate, several requests in parallel
    jobs = []           # (gid, k, images, prompt, dst)
    skipped = set()
    for r in rows:
        gid = r["id"]
        images = [data / p for p in r["inputs"]][: max(1, a.max_inputs)]
        missing = [p for p in images if not p.exists()]
        if missing:
            print(f"  {gid}: missing input {missing[0]}, skipped")
            skipped.add(gid)
            continue
        prompt = a.prompt or (PROMPT + (PROMPT_MULTI if len(images) > 1 else ""))
        if notes.get(gid):
            prompt += " Specific instructions for this garment: " + notes[gid].strip()
        cdir = cand_root / gid
        cdir.mkdir(parents=True, exist_ok=True)
        print(f"  {gid}: {len(images)} input(s): " + ", ".join(p.name for p in images))
        for k in range(a.candidates):
            dst = cdir / f"cand_{a.tag}{k}.png"
            if not dst.exists():
                jobs.append((gid, k, images, prompt, dst))
    if a.dry_run:
        print(f"\n{len(jobs)} candidates would be generated")
        return

    def _job(j):
        gid, k, images, prompt, dst = j
        t0 = time.time()
        try:
            png = generate_one(images, prompt, key, a.model, a.timeout, a.retries)
            _save_png(png, dst)
            return gid, k, None, time.time() - t0
        except Exception as e:
            return gid, k, redact(e, [key])[:200], time.time() - t0

    if jobs:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        print(f"\ngenerating {len(jobs)} candidates with {a.workers} parallel requests ...")
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            for fut in as_completed([ex.submit(_job, j) for j in jobs]):
                gid, k, err, secs = fut.result()
                if err:
                    print(f"  {gid} candidate {k} FAILED: {err}")
                    log.write(json.dumps({"id": gid, "cand": k, "error": err}) + "\n")
                else:
                    print(f"  {gid} candidate {k} ok ({secs:.0f}s)")
                    log.write(json.dumps({"id": gid, "cand": k, "model": a.model, "seconds": round(secs, 1)}) + "\n")
                log.flush()

    # ---- phase 2: pick one candidate per garment (colour consensus + straightness)
    print("\nselecting ...")
    done = 0
    for r in rows:
        gid = r["id"]
        if gid in skipped:
            continue
        cands = sorted((cand_root / gid).glob("cand_*.png"))
        if not cands:
            print(f"  {gid}: no candidate succeeded")
            continue
        if gid in picks and (cand_root / gid / picks[gid]).exists():
            best, why = cand_root / gid / picks[gid], [f"manual pick from {a.picks}"]
        else:
            best, why = (cands[0], ["single candidate"]) if len(cands) == 1 else pick_consensus(cands)
        final = out / a.team / gid / "front.png"
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(best, final)
        done += 1
        print(f"  {gid}: kept {best.name}")
        for n in why:
            print("      " + n)

    if a.fill_from and a.fill_ids and not a.dry_run:
        need = [x["id"] for x in load_rows(Path(a.fill_ids))]
        filled = 0
        for gid in need:
            final_dir = out / a.team / gid
            if any(final_dir.glob("front.*")):
                continue
            src = None
            for ext in ("png", "jpg", "jpeg", "webp"):
                p = Path(a.fill_from) / gid / f"front.{ext}"
                if p.exists():
                    src = p
                    break
            if src is None:
                print(f"  {gid}: NOT in manifest and nothing to fill from -> will score 0!")
                continue
            final_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, final_dir / src.name)
            filled += 1
            print(f"  {gid}: filled from {a.fill_from}")
        print(f"\n{done} garments generated, {filled} filled from fallback -> {out / a.team}")
    else:
        print(f"\n{done} garments generated -> {out / a.team}")


if __name__ == "__main__":
    main()
