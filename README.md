# AACtivEtion Function — Sartiq Neural Wave 2026

Phone photo of a garment in → studio flat-lay packshot out.
Team **aactivetion_function** (GitHub: `neural-wave/ch-AACtivEtion-Functions`), Neural Wave hackathon, USI Lugano, 16–18 October 2026.

| | |
|---|---|
| Dev leaderboard | **70.79** (rank 1 at the last scoring round before the freeze) |
| Final pictures | `submissions/aactivetion_function/` — 15 on-site garments `g01–g15` + 27 dev garments `d001–d027` |
| Report & video | `deliverables/` |
| Capture protocol | `docs/CAPTURE_PROTOCOL.md` |
| Demo UI | `ui/` |

## Team

| Name | Role |
|---|---|
| Mohammadmahdi Ameridaragheh | Code, pipeline runs, sensitivity analysis of the parameters, submissions, photography, report |
| Qi An | UI design and implementation, photography, image comparison, report |
| Arianna Silvestri | Image optimisation experiments (curvature, pixel fixes), photography, image comparison, video |
| Eduardo Trabattoni | Model tuning, photography, video |
| Andrea Gemetti | Ideas and brainstorming (day 1) |

## What we built, in one paragraph

We treat the problem as *capture + edit + select* rather than as a model-training problem. A short
capture protocol (`docs/CAPTURE_PROTOCOL.md`) produces one clean top-down front photo plus 3–6
close-ups of every garment. A hosted image-editing model (Google Nano Banana 2.1 via fal.ai,
`google/nano-banana-2.1/edit`) receives the front photo **and** the close-ups in one request with a
fixed packshot prompt, so colour, fabric texture, prints and logos are copied from the real garment
instead of being invented. We ask for several candidates per garment and pick the one whose garment
colour agrees best with the other candidates (colour consensus) and whose silhouette is the most
symmetric and upright; a human can override the pick by eye. No training, no GPU: the whole pipeline
runs on a laptop in a few minutes.

## Where everything is

```
pipeline.py               the pipeline (generate K candidates per garment, select one)
make_ours_manifest.py     builds the manifest of our own on-site photos (front + close-ups)
colour_tools.py           colour diagnostics / calibration experiments (not used in the final run)
post_experiment.py        post-processing experiments (none helped; documented in the report)
garment_notes.json        per-garment detail descriptions appended to the prompt (test set)
dev_notes.json            same for the dev set
manual_picks.csv          garments where we overrode the automatic candidate choice
final_choice.csv          per test garment: picture from our photos ("ours") or the organisers' ("theirs")
notebooks/day2_final_pipeline_v2.ipynb   the notebook we actually ran, cell by cell
submissions/aactivetion_function/        THE HAND-IN: one front.png per garment
deliverables/             report (PDF + Markdown) and the 2-minute video
docs/CAPTURE_PROTOCOL.md  how to photograph a garment so the pipeline works
ui/                       Gradio demo: before/after slider and magnifier for the jury
scorer/, scripts/, docs/, baselines/   the organisers' starter material, unchanged
```

## How to run it (cold start)

```bash
git clone <this repo> && cd NW_26_aactivetion_function
python3 -m venv .venv && source .venv/bin/activate
pip install -e scorer            # official scorer (needed for selection + validation)
pip install pillow numpy scikit-image rembg
export FAL_KEY=<your fal.ai key>   # never written to a file
```

1. Photograph the garments following `docs/CAPTURE_PROTOCOL.md` and put them in
   `../captures/day1_clean/<gid>/` (one folder per garment; the best front shot is listed in
   `best_fronts.csv`).
2. Build the manifest of our photos:
   ```bash
   python make_ours_manifest.py --captures ../captures --out ../captures/ours_all.jsonl --details 8
   ```
3. Generate 3 candidates per garment from the front + close-ups and select one:
   ```bash
   python pipeline.py --manifest ../captures/ours_all.jsonl --dataset ../captures \
       --out submissions_final --team aactivetion_function --candidates 3 --max-inputs 8 \
       --notes garment_notes.json --picks manual_picks.csv \
       --fill-from submissions_theirs/aactivetion_function --fill-ids ../sartiq_neural_wave_2026/test/inputs.jsonl
   ```
   `--fill-from` supplies a picture generated from the organisers' photos for any garment we did not
   photograph ourselves, so every id is always submitted.
4. Dev set (organisers' photos only, same prompt and selection):
   ```bash
   python pipeline.py --manifest ../sartiq_neural_wave_2026/dev/inputs.jsonl \
       --dataset ../sartiq_neural_wave_2026 --out submissions_dev_v2 --team aactivetion_function \
       --candidates 3 --max-inputs 8
   ```
5. Assemble and validate the hand-in (also done by notebook cell 10):
   ```bash
   python scripts/make_submission.py --submissions submissions --team aactivetion_function \
       --dataset ../sartiq_neural_wave_2026
   ```

`pipeline.py --help` lists every option (`--candidates`, `--max-inputs`, `--notes`, `--picks`,
`--only`, `--tag`, `--workers`, `--dry-run`). Candidates are cached under
`<out>/_candidates/<team>/<gid>/` and never regenerated, so re-running only selects.
Setting `NB_THINKING=high` passes a higher "thinking level" to the model (experiment; the final
pictures use the default).

## What we measured (details in the report)

* Our own 38-pair holdout from `train/` (official scorer): hosted baseline 60.55 → our prompt
  61.01 → + 3-candidate consensus **61.04**. Colour post-correction towards the phone photo made
  things *worse* (59.06): the phone photo's colour is less reliable than the model's.
* Post-processing (flat-field, white-balance, unsharp) never beat the raw model output.
* Dev leaderboard: 68.31 with the organisers' photos and one candidate → **70.79** with the final
  prompt + 3 candidates + consensus selection.
* On the 15 on-site garments, scoring each result against our *own* clean photo as a stand-in
  reference, pictures generated from our protocol photos score ~72 vs ~50 for pictures generated
  from the organisers' quick snapshots of the same garments. Capture quality is the biggest lever.

## Rules we followed

* Every output comes from our pipeline and the garment's own photos. No retrieved product images,
  no copies of the example targets.
* The dataset and the fal.ai key are not in this repository.
