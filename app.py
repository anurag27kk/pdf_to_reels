"""
Streamlit Demo App — Pharma Video Reel Generator

Upload a drug PDF, choose settings, and watch a 60-120s educational
video reel get generated in real-time.
"""

import os
import time
import shutil
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from pipeline import PipelineConfig, run_pipeline

BASE_DIR = Path(__file__).parent
PDFS_DIR = BASE_DIR / "pdfs"
LOGO_PATH = BASE_DIR / "assets" / "jagsonpal_logo.jpg"

# --- Page config ---
st.set_page_config(
    page_title="JagsonPal Pharma — Video Reel Generator",
    page_icon="💊",
    layout="centered",
)

# --- Header ---
col1, col2 = st.columns([4, 1])
with col1:
    st.title("Pharma Video Reel Generator")
    st.caption("Upload a drug PDF → Get an educational video reel in minutes")
with col2:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=80)

st.divider()

# --- Sidebar: existing PDFs ---
existing_pdfs = sorted(PDFS_DIR.glob("*.pdf")) + sorted(PDFS_DIR.glob("*.PDF")) if PDFS_DIR.exists() else []

# --- PDF source ---
pdf_source = st.radio("PDF source", ["Upload new", "Use existing"], horizontal=True)

pdf_path = None
if pdf_source == "Upload new":
    uploaded = st.file_uploader("Upload a drug PDF", type=["pdf"])
    if uploaded:
        PDFS_DIR.mkdir(exist_ok=True)
        save_path = PDFS_DIR / uploaded.name
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())
        pdf_path = str(save_path)
        st.success(f"Saved: {uploaded.name}")
else:
    if existing_pdfs:
        selected = st.selectbox(
            "Choose a PDF",
            existing_pdfs,
            format_func=lambda p: p.stem,
        )
        pdf_path = str(selected)
    else:
        st.warning("No PDFs found in pdfs/ directory")

# --- Settings ---
st.subheader("Settings")
col1, col2 = st.columns(2)

with col1:
    profile = st.selectbox("Profile", ["doctor", "stockist", "retailer", "all"], index=0)
    topic = st.selectbox("Topic", [
        "intro", "indications", "mechanism",
        "dosage_safety", "interactions", "side_effects",
    ], index=0)

with col2:
    voice_options = {
        "Gaurav (Professional, Calm)": "gaurav",
        "Raj (Professional)": "raj",
        "Viraj (Smooth, Gentle)": "viraj",
        "Ruhaan (Clear, Cheerful)": "ruhaan",
        "Jeevan (Expressive)": "jeevan",
    }
    voice_label = st.selectbox("Voice", list(voice_options.keys()))
    voice = voice_options[voice_label]

    tts = st.selectbox("TTS Engine", ["elevenlabs", "gemini"], index=0)

include_quiz = st.checkbox("Include quiz questions", value=True)
mode = "demo" if include_quiz else "production"

guidance = st.text_area(
    "Creative direction (optional)",
    placeholder="e.g. Focus on how this helps elderly patients with chronic pain",
    height=80,
)

# --- Generate ---
st.divider()

if st.button("Generate Video", type="primary", disabled=pdf_path is None):
    if pdf_path is None:
        st.error("Please select or upload a PDF first")
        st.stop()

    config = PipelineConfig(
        pdf_path=pdf_path,
        profile=profile,
        topic=topic,
        voice=voice,
        tts=tts,
        mode=mode,
        guidance=guidance,
    )

    # Progress tracking
    steps = {
        "extract": "Extract text",
        "analyze": "Analyze content",
        "script": "Generate script",
        "media": "Frames + voiceover",
        "stitch": "Stitch video",
        "subtitles": "Burn subtitles",
        "done": "Complete",
    }
    step_order = list(steps.keys())

    progress_bar = st.progress(0)
    status_container = st.container()
    step_statuses = {}

    # Create status placeholders
    with status_container:
        for key, label in steps.items():
            if key == "done":
                continue
            step_statuses[key] = st.empty()
            step_statuses[key].markdown(f"⏳ {label}")

    step_times = {}
    current_step = [None]
    step_start = [time.time()]

    def on_progress(step: str, message: str, pct: float):
        # Mark previous step as done
        if current_step[0] and current_step[0] != step and current_step[0] in step_statuses:
            elapsed = time.time() - step_start[0]
            step_times[current_step[0]] = elapsed
            label = steps.get(current_step[0], current_step[0])
            step_statuses[current_step[0]].markdown(f"✅ {label} — {elapsed:.0f}s")

        # Update current step
        current_step[0] = step
        step_start[0] = time.time()
        progress_bar.progress(min(pct, 1.0))

        if step in step_statuses:
            label = steps.get(step, step)
            step_statuses[step].markdown(f"🔄 {label}...")

    # Run pipeline
    result = run_pipeline(config, on_progress=on_progress)

    # Finalize last step
    if current_step[0] and current_step[0] in step_statuses:
        elapsed = time.time() - step_start[0]
        label = steps.get(current_step[0], current_step[0])
        step_statuses[current_step[0]].markdown(f"✅ {label} — {elapsed:.0f}s")

    progress_bar.progress(1.0)

    # --- Result ---
    st.divider()

    if result.get("error"):
        st.error(f"Pipeline error: {result['error']}")
    elif result.get("video_path") and os.path.exists(result["video_path"]):
        st.success(f"Video generated in {result['duration']:.0f}s")

        # Video player
        st.video(result["video_path"])

        # Download button
        video_bytes = Path(result["video_path"]).read_bytes()
        video_name = Path(result["video_path"]).name
        st.download_button(
            label="Download MP4",
            data=video_bytes,
            file_name=video_name,
            mime="video/mp4",
        )
    else:
        st.error("Pipeline completed but no video was produced")
