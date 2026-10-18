# Capture protocol — how to photograph a garment for our pipeline

Goal: give the model one clean top-down view that already *looks like* a flat-lay, plus close-ups
that pin down colour, fabric and details. Anyone with a phone can do this in about 3 minutes per
garment. No studio equipment is needed.

## 1. Set-up (once)

* **Surface:** a plain, light, matte surface — a white table, a sheet of white paper/cardboard, or a
  clean light floor. Avoid patterns, wood grain and anything shiny.
* **Light:** daylight from a window or even room light. Switch the phone flash **off**. Make sure
  your own body does not cast a shadow on the garment (stand with the light in front of you, or to
  the side).
* **Phone:** main (1×) camera, HDR off if possible, no filters, no portrait mode. Wipe the lens.

## 2. Lay the garment (the step that matters most)

1. Lay it flat, front side up, collar/waistband at the top.
2. Smooth it with both hands from the centre outwards. Pull the hem straight. If a sleeve or leg
   is twisted, lift it and lay it down again rather than dragging it.
3. Make it symmetric: fold the sleeves slightly away from the body at the same angle on both
   sides; align the side seams; centre the placket/zip.
4. Close buttons and zips. Flatten pockets and collar. Straighten any tag or label you want shown.
5. Heavy wrinkles: press with your hands or roll a bottle over the fabric; a few seconds of steam
   or a quick iron helps a lot on cotton and linen. Thin/slippery fabrics (silk, satin): smooth with
   flat palms, do not pull.

The model reproduces the lay it sees. A crooked or wrinkled lay comes back crooked or wrinkled.

## 3. Shots to take (per garment)

| # | Shot | How |
|---|---|---|
| 1 | **Front, top-down** (`gXX_front_1.jpg`) | Stand over the garment, phone parallel to the surface, garment filling ~80 % of the frame with margin on all sides, centred. Take 2–3 and keep the straightest. |
| 2 | **Close-ups** (`gXX_detail_1.jpg` …) | 3–6 photos from ~20–30 cm: collar/neck label, any logo/print/badge, buttons or zip, a pocket, a patch of plain fabric showing the weave. Sharp focus, no shadow. |
| 3 | **Back** (`gXX_back_1.jpg`, optional) | Flip the garment, same as shot 1. Used only as extra reference for colour. |

Check before moving on: the front shot is in focus, the whole garment is inside the frame, no
shadow of the photographer, colours look like the real garment on the phone screen.

## 4. Naming and folders

```
captures/day1_clean/g07/g07_front_1.jpg
captures/day1_clean/g07/g07_detail_1.jpg
captures/day1_clean/g07/g07_detail_2.jpg
captures/day1_clean/g07/g07_back_1.jpg
captures/day1_clean/best_fronts.csv      # folder,best_front  e.g.  g07,g07_front_2.jpg
```

Then `python make_ours_manifest.py --captures ../captures --out ../captures/ours_all.jsonl --details 8`
builds the manifest the pipeline reads: the best front first, then the close-ups, then at most one
back view.

## 5. Why this works (what we observed)

* The model copies the lay literally: an amateur flat-lay with a straight, symmetric garment gives
  the best shape score; worn or hanging garments give the worst.
* Close-ups decide the details. Without them logos were paraphrased, prints simplified and colours
  drifted; with them they are reproduced. The front photo is used for shape, the close-ups for
  colour/texture/print.
* Colour: the model's colour is closer to the studio reference than the phone's own white balance,
  so we do **not** colour-correct towards the phone photo. A neutral light surface and no flash
  keep the phone's error small enough.
* The organisers' quick snapshots of the same 15 garments (worn, on a hanger, on a patterned floor)
  gave pictures that scored ~20 points lower on our fidelity check than pictures from protocol shots.
