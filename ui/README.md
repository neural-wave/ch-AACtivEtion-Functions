# Demo UI (Gradio)

Two apps for the jury demo:

* `interface_single.py` — **live**: upload a phone photo, tick the confirmation box, press *Scan garment*;
  it runs `pipeline.py` (3 candidates, consensus pick, ≈ $0.18) and shows the packshot with a
  drag-to-reveal before/after comparison and a hover magnifier up to 4×. Needs `FAL_KEY` in the
  environment. An existing packshot can also be loaded instead of running the model.
* `interface_double.py` — viewer only, two garments side by side (no model call).

```bash
pip install gradio pillow
export FAL_KEY=<your fal.ai key>
python ui/interface_single.py
python ui/interface_double.py
```
Open the printed local URL in a browser. Runs are written to `gradio_runs/` (ignored by git).
