from pathlib import Path
import base64
import io
import time

import gradio as gr
from PIL import Image, ImageOps


CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap');

:root, .gradio-container {
    --ink: #f1eee8; --muted: #8f8a80; --gold: #c7a779;
    --line: #2c2c2a; --panel: #141413;
    --mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
    --serif: "Cormorant Garamond", "Didot", "Bodoni 72", Georgia, serif;
}
.gradio-container {
    max-width: 1320px !important; margin: auto !important;
    font-family: "Inter", -apple-system, "Helvetica Neue", sans-serif !important;
    color: var(--ink) !important;
    --body-background-fill: #0e0e0d;
    --background-fill-primary: #0e0e0d;
    --background-fill-secondary: #141413;
    --block-background-fill: #141413;
    --block-border-color: #2c2c2a;
    --block-label-background-fill: #0e0e0d;
    --block-label-text-color: #8f8a80;
    --block-title-text-color: #8f8a80;
    --body-text-color: #f1eee8;
    --body-text-color-subdued: #8f8a80;
    --input-background-fill: #121211;
    --input-border-color: #2c2c2a;
    --input-border-color-focus: #c7a779;
    --border-color-primary: #2c2c2a;
    --slider-color: #c7a779;
    --color-accent: #c7a779;
}
body { background: #0e0e0d !important; }
#hero { padding: 56px 0 34px; border-bottom: 1px solid var(--line); margin-bottom: 12px; }
#hero h1 {
    font-family: var(--serif) !important;
    font-size: clamp(64px, 9vw, 128px) !important;
    font-weight: 400 !important; letter-spacing: -.04em !important;
    line-height: .9 !important; margin: 18px 0 14px !important; color: var(--ink);
}
#hero p { font-family: var(--serif); font-style: italic; font-size: 22px; color: var(--muted); margin: 0 0 22px; }
.eyebrow { font-family: var(--mono); color: var(--gold); letter-spacing: .24em; font-size: 10.5px; }
.section-label {
    display: flex; align-items: center; gap: 16px;
    font-family: var(--mono); font-size: 10.5px; letter-spacing: .24em;
    color: var(--gold); padding: 30px 0 14px;
}
.section-label::after { content: ""; flex: 1; height: 1px; background: var(--line); }
.panel { border: 1px solid var(--line) !important; background: var(--panel) !important; border-radius: 2px !important; padding: 18px !important; }
.panel .block, .panel .form { border-color: transparent !important; box-shadow: none !important; }
.gradio-container button { border-radius: 2px !important; text-transform: uppercase; letter-spacing: .18em; font-size: 11px !important; transition: all .2s ease; }
.gradio-container button.primary { background: var(--gold) !important; color: #0e0e0d !important; border: 1px solid var(--gold) !important; font-weight: 500; }
.gradio-container button.primary:hover { background: #e8c78e !important; }
.gradio-container button.secondary { background: transparent !important; color: var(--ink) !important; border: 1px solid #4a4640 !important; }
.gradio-container button.secondary:hover { border-color: var(--gold) !important; color: var(--gold) !important; }
.gradio-container label span, .gradio-container [data-testid="block-info"] {
    font-family: var(--mono) !important; font-size: 10px !important;
    letter-spacing: .2em; text-transform: uppercase; color: var(--muted) !important;
}
.gradio-container textarea, .gradio-container input[type="text"] { font-family: var(--mono) !important; font-size: 12px !important; color: var(--ink) !important; }
.gradio-container input[type="range"] { accent-color: var(--gold); }
.scan-stage, .idle-stage {
    height: 84px; position: relative; overflow: hidden; background: #121211; border: 1px solid var(--line);
    display: flex; align-items: center; justify-content: center; color: var(--gold);
    font-family: var(--mono); font-size: 11px; letter-spacing: .2em; text-align: center;
}
.scan-stage::before, .idle-stage::before, .scan-stage::after, .idle-stage::after {
    content: ""; position: absolute; width: 10px; height: 10px; border: 1px solid var(--gold);
}
.scan-stage::before, .idle-stage::before { top: 6px; left: 6px; border-right: 0; border-bottom: 0; }
.scan-stage::after, .idle-stage::after { bottom: 6px; right: 6px; border-left: 0; border-top: 0; }
.scan-beam { position: absolute; left: 0; top: 0; width: 100%; height: 2px; background: linear-gradient(90deg, transparent, var(--gold), transparent); animation: sweep 1.3s ease-in-out infinite alternate; }
@keyframes sweep { from { top: 0; } to { top: calc(100% - 2px); } }
#output-image img { animation: unveil 1.1s cubic-bezier(.2,.7,.2,1) both; }
@keyframes unveil { from { clip-path: inset(0 100% 0 0); } to { clip-path: inset(0 0 0 0); } }
@media (prefers-reduced-motion: reduce) { .scan-beam { animation: none; top: 50%; } #output-image img { animation: none !important; } }
#input-image { position: relative; overflow: hidden; }
footer { display: none !important; }
#inspect-source img { cursor: crosshair !important; }
#hover-zoom-panel { width: 100%; box-sizing: border-box; }

/* Drag directly on the comparison image. */
.cmp {
    position: relative; width: 100%; height: 420px; --pos: 50%; background: #121211;
    border: 1px solid var(--line); overflow: hidden; cursor: ew-resize;
    touch-action: none; user-select: none;
}
.cmp img {
    position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain;
    pointer-events: none; user-select: none; -webkit-user-drag: none;
}
.cmp .cmp-top { clip-path: inset(0 calc(100% - var(--pos)) 0 0); }
.cmp-handle {
    position: absolute; top: 0; bottom: 0; left: var(--pos); width: 2px; margin-left: -1px;
    background: var(--gold); outline: none; z-index: 2; cursor: ew-resize;
}
.cmp-handle::after {
    content: "‹  ›"; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 42px; height: 42px; border-radius: 50%; background: #0e0e0d; border: 2px solid var(--gold);
    color: var(--gold); display: flex; align-items: center; justify-content: center;
    font-family: var(--mono); font-size: 15px; white-space: pre;
}
.cmp-tag {
    position: absolute; top: 12px; padding: 5px 10px; pointer-events: none; background: rgba(14,14,13,.85);
    color: var(--ink); font-family: var(--mono); font-size: 10px; letter-spacing: .2em; z-index: 3;
}
.cmp-tag.l { left: 12px; } .cmp-tag.r { right: 12px; }
.cmp-empty {
    height: 420px; display: flex; align-items: center; justify-content: center; background: #121211;
    border: 1px solid var(--line); color: var(--gold); font-family: var(--mono); font-size: 11px;
    letter-spacing: .2em; text-align: center;
}
@media (max-width: 700px) { .cmp, .cmp-empty { height: 300px; } }
"""

IDLE_HTML = '<div class="idle-stage">AWAITING GARMENT INPUT</div>'
SCANNING_HTML = r"""
<style>
#input-image::after {
    content: ""; position: absolute; left: 0; width: 100%; height: 70px; top: -70px;
    z-index: 5; pointer-events: none;
    background: linear-gradient(to bottom, transparent, rgba(199,167,121,.28));
    border-bottom: 2px solid #e8c78e; box-shadow: 0 6px 18px rgba(199,167,121,.45);
    animation: img-sweep 1.25s linear infinite;
}
@keyframes img-sweep { from { top: -70px; } to { top: 100%; } }
@media (prefers-reduced-motion: reduce) { #input-image::after { animation: none; display: none; } }
</style>
<div class="scan-stage">SCANNING VISUAL INPUT<div class="scan-beam"></div></div>
"""
READY_HTML = '<div class="idle-stage">INPUT CHECK COMPLETE · AWAITING REAL OUTPUT</div>'


MAGNIFIER_JS = r"""() => {
    if (window.__unveilMagnifier) return;
    window.__unveilMagnifier = true;
    const state = { px: 0.5, py: 0.5, hovering: false };

    const geometry = (img) => {
        const rect = img.getBoundingClientRect();
        if (!img.naturalWidth || !img.naturalHeight) return null;
        const scale = Math.min(rect.width / img.naturalWidth, rect.height / img.naturalHeight);
        const w = img.naturalWidth * scale, h = img.naturalHeight * scale;
        return { w, h, left: rect.left + (rect.width - w) / 2, top: rect.top + (rect.height - h) / 2 };
    };
    const render = () => {
        const img = document.querySelector('#inspect-source img');
        const panel = document.querySelector('#hover-zoom-panel');
        if (!img || !panel || !img.src || !img.naturalWidth) return;
        const slider = document.querySelector('#zoom-control input[type="range"]');
        const factor = Math.max(1, Math.min(4, Number(slider ? slider.value : 2)));
        const g = geometry(img); if (!g) return;
        const bgW = g.w * factor, bgH = g.h * factor;
        const x = panel.clientWidth / 2 - state.px * bgW;
        const y = panel.clientHeight / 2 - state.py * bgH;
        panel.style.backgroundImage = `url("${img.src}")`;
        panel.style.backgroundRepeat = 'no-repeat';
        panel.style.backgroundSize = `${bgW}px ${bgH}px`;
        panel.style.backgroundPosition = `${Math.max(Math.min(0, panel.clientWidth - bgW), Math.min(0, x))}px ${Math.max(Math.min(0, panel.clientHeight - bgH), Math.min(0, y))}px`;
        panel.textContent = '';
    };
    const clear = () => {
        const panel = document.querySelector('#hover-zoom-panel'); if (!panel) return;
        panel.style.backgroundImage = 'none'; panel.textContent = 'HOVER OVER THE IMAGE';
    };
    document.addEventListener('pointermove', (e) => {
        const img = document.querySelector('#inspect-source img');
        if (!img || !img.naturalWidth) return;
        const g = geometry(img); if (!g) return;
        const inside = e.clientX >= g.left && e.clientX <= g.left + g.w && e.clientY >= g.top && e.clientY <= g.top + g.h;
        if (!inside) { if (state.hovering) clear(); state.hovering = false; return; }
        state.px = (e.clientX - g.left) / g.w; state.py = (e.clientY - g.top) / g.h;
        state.hovering = true; render();
    });
    document.addEventListener('input', (e) => { if (e.target.closest && e.target.closest('#zoom-control')) render(); });
    window.addEventListener('resize', render);
}"""

COMPARE_JS = r"""() => {
    if (window.__unveilCompare) return;
    window.__unveilCompare = true;
    const setPos = (el, pct) => {
        pct = Math.max(0, Math.min(100, pct));
        el.style.setProperty('--pos', pct + '%'); el.dataset.pos = String(pct);
        const handle = el.querySelector('.cmp-handle');
        if (handle) handle.setAttribute('aria-valuenow', String(Math.round(pct)));
    };
    const fromEvent = (el, e) => {
        const rect = el.getBoundingClientRect(); if (!rect.width) return;
        setPos(el, ((e.clientX - rect.left) / rect.width) * 100);
    };
    let active = null;
    document.addEventListener('pointerdown', (e) => {
        const el = e.target.closest ? e.target.closest('.cmp') : null;
        if (!el) return;
        active = el; fromEvent(el, e); e.preventDefault();
        if (el.setPointerCapture && e.pointerId !== undefined) { try { el.setPointerCapture(e.pointerId); } catch (_) {} }
    });
    document.addEventListener('pointermove', (e) => { if (active) fromEvent(active, e); });
    const stop = () => { active = null; };
    document.addEventListener('pointerup', stop); document.addEventListener('pointercancel', stop);
    document.addEventListener('keydown', (e) => {
        const handle = e.target.closest ? e.target.closest('.cmp-handle') : null; if (!handle) return;
        const el = handle.closest('.cmp'); const step = e.shiftKey ? 10 : 2; const current = Number(el.dataset.pos || 50);
        if (e.key === 'ArrowLeft') { setPos(el, current - step); e.preventDefault(); }
        if (e.key === 'ArrowRight') { setPos(el, current + step); e.preventDefault(); }
    });
}"""


def open_rgb(path):
    """Open a local image safely and apply its EXIF orientation."""
    if not path:
        return None
    try:
        image_path = Path(path)
        if not image_path.is_file():
            return None
        with Image.open(image_path) as source:
            return ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, ValueError, TypeError):
        return None


def to_data_uri(image, max_side=1400):
    """Convert a PIL image to a browser-displayable JPEG data URI."""
    image = image.copy()
    image.thumbnail((max_side, max_side))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90, optimize=True)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def render_compare(input_path, output_path):
    """Return draggable before/after HTML; reconstruction is revealed from the left."""
    original = open_rgb(input_path)
    reconstructed = open_rgb(output_path)
    if original is None or reconstructed is None:
        return (
            '<div class="cmp-empty">WAITING FOR BOTH IMAGES</div>',
            "Upload an input photo and a real reconstruction to activate the comparison.",
        )

    original_uri = to_data_uri(original)
    reconstructed_uri = to_data_uri(reconstructed)
    html = f"""
<div class="cmp" style="--pos:50%" data-pos="50" role="group" aria-label="Draggable image comparison">
  <img class="cmp-base" src="{original_uri}" alt="Original input" draggable="false">
  <img class="cmp-top" src="{reconstructed_uri}" alt="Uploaded reconstruction" draggable="false">
  <span class="cmp-tag l">INPUT</span>
  <span class="cmp-tag r">RECONSTRUCTION</span>
  <div class="cmp-handle" tabindex="0" role="slider" aria-label="Reveal the reconstruction" aria-valuemin="0" aria-valuemax="100" aria-valuenow="50"></div>
</div>
"""
    return html, "Drag the gold divider directly across the image. Left: original input · Right: reconstruction."


def refresh_views(input_path, output_path, view):
    comparison, message = render_compare(input_path, output_path)
    shown = output_path if view == "RECONSTRUCTION" and output_path else input_path
    if input_path and not output_path:
        message = "Input loaded. Upload the team's real reconstruction to compare both images."
    return output_path or None, comparison, shown or None, message


def scan_image(image_path):
    if not image_path or not Path(image_path).is_file():
        yield (
            "Please upload a garment photo first.",
            "No image received. No model was run and no API was called.",
            IDLE_HTML,
        )
        return
    yield (
        "Scanning uploaded image…",
        "Checking the local input. This animation is not model inference.",
        SCANNING_HTML,
    )
    time.sleep(1.5)
    yield (
        "Input ready · Awaiting reconstruction",
        " ",
        READY_HTML,
    )


def download_input(image_path):
    if image_path and Path(image_path).is_file():
        return image_path, "Original image is ready."
    return None, "Upload an image before downloading."


def reset_demo():
    return (
        None,  # input image
        None,  # uploaded real output
        "Upload a garment photo to begin.",
        "Waiting for input.",
        IDLE_HTML,
        None,  # inspection image
        '<div class="cmp-empty">WAITING FOR BOTH IMAGES</div>',
        "Waiting for both images.",
        2.0,  # zoom level
        None,  # download file
        "No download selected.",
    )


with gr.Blocks(
    title="AACtivEtion Function — Garment Reconstruction",
    theme=gr.themes.Base(primary_hue="orange", neutral_hue="stone", radius_size="sm"),
    css=CSS,
) as demo:
    gr.HTML("""
    <div id="hero">
      <div class="eyebrow">NEURAL WAVE 2026 / SARTIQ</div>
      <h1>AACtivEtion Function<span style="color:#c7a779">.</span></h1>
      <p>From garment image to digital reconstruction.</p>
      <div class="eyebrow">SCAN / REVEAL / INSPECT</div>
    </div>
    """)

    with gr.Row():
        with gr.Column(scale=1):
            gr.HTML('<div class="section-label">01 — SCAN / INPUT</div>')
            with gr.Group(elem_classes=["panel"]):
                input_image = gr.Image(
                    label="GARMENT INPUT", type="filepath", height=350,
                    sources=["upload"], elem_id="input-image",
                )
                with gr.Row():
                    scan_button = gr.Button("SCAN GARMENT ↗", variant="primary")
                    reset_button = gr.Button("RESET", variant="secondary")
                scan_panel = gr.HTML(value=IDLE_HTML)
                download_button = gr.DownloadButton("DOWNLOAD ORIGINAL")
                download_status = gr.Textbox(value="No download selected.", label="DOWNLOAD STATUS", interactive=False, lines=1)

        with gr.Column(scale=1):
            gr.HTML('<div class="section-label">02 — REVEAL / OUTPUT</div>')
            with gr.Group(elem_classes=["panel"]):
                output_image = gr.Image(label="REAL RECONSTRUCTION OUTPUT", height=350, interactive=False, elem_id="output-image")
                status = gr.Textbox(label="SYSTEM STATUS", value="Upload a garment photo to begin.", lines=2, interactive=False)
                with gr.Accordion("LOAD AN EXISTING REAL RECONSTRUCTION", open=False):
                    real_output_input = gr.Image(label="Upload the team's generated output", type="filepath", height=240, sources=["upload"])
                    gr.Markdown("Only load an image actually generated by your team's pipeline. This demo does not generate it.")

    gr.HTML('<div class="section-label">03 — COMPARE / INPUT VS OUTPUT</div>')
    with gr.Group(elem_classes=["panel"]):
        
        comparison_image = gr.HTML(value='<div class="cmp-empty">WAITING FOR BOTH IMAGES</div>')
        compare_status = gr.Textbox(value="Waiting for both images.", label="COMPARISON STATUS", interactive=False, lines=2)

    gr.HTML('<div class="section-label">04 — INSPECT / DETAILS</div>')
    with gr.Group(elem_classes=["panel"]):
        view_choice = gr.Radio(["INPUT", "RECONSTRUCTION"], value="INPUT", label="INSPECT VIEW")
        zoom_slider = gr.Slider(minimum=1, maximum=4, value=2, step=0.5, label="MAGNIFICATION", elem_id="zoom-control", interactive=True)
        with gr.Row():
            inspect_source = gr.Image(interactive=False, height=350, elem_id="inspect-source")
            gr.HTML("""
            <div id="hover-zoom-panel" style="height:350px; min-width:240px; background:#171714; border:1px solid #3a352c; display:flex; align-items:center; justify-content:center; overflow:hidden; color:#c7a779; font-size:12px; letter-spacing:.08em; background-repeat:no-repeat; background-position:center; background-size:contain;">
              HOVER OVER THE IMAGE
            </div>
            """)
        detail = gr.Textbox(label="PROCESSING DETAILS", value="Waiting for input.", interactive=False, lines=2)

    scan_button.click(fn=scan_image, inputs=[input_image], outputs=[status, detail, scan_panel], show_progress="hidden")

    refresh_inputs = [input_image, real_output_input, view_choice]
    refresh_outputs = [output_image, comparison_image, inspect_source, compare_status]
    view_choice.change(fn=refresh_views, inputs=refresh_inputs, outputs=refresh_outputs, show_progress="hidden")
    input_image.change(fn=refresh_views, inputs=refresh_inputs, outputs=refresh_outputs, show_progress="hidden")
    real_output_input.change(fn=refresh_views, inputs=refresh_inputs, outputs=refresh_outputs, show_progress="hidden")

    download_button.click(fn=download_input, inputs=[input_image], outputs=[download_button, download_status], show_progress="hidden")
    reset_button.click(
        fn=reset_demo,
        inputs=[],
        outputs=[input_image, real_output_input, status, detail, scan_panel, inspect_source, comparison_image, compare_status, zoom_slider, download_button, download_status],
        show_progress="hidden",
    )

    # Register browser-side interactions. These scripts only control the UI;
    # they do not run an image model or call an external API.
    demo.load(fn=None, js=MAGNIFIER_JS)
    demo.load(fn=None, js=COMPARE_JS)
    demo.load(fn=None, js="() => document.body.classList.add('dark')")


if __name__ == "__main__":
    demo.queue().launch()
