"""
SwishX — Pharma AI Video Reel Generator
"""

import os
import time
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from pipeline import PipelineConfig, run_pipeline

BASE_DIR = Path(__file__).parent
PDFS_DIR = BASE_DIR / "pdfs"
DEMOS_DIR = BASE_DIR / "demos"
SWISHX_LOGO = BASE_DIR / "assets" / "swishx_logo.png"

DEMO_VIDEOS = [
    {"file": "AllerDuo_intro.mp4",         "drug": "AllerDuo",     "topic": "Intro",           "composition": "Bilastine + Montelukast"},
    {"file": "AllerDuo_mechanism.mp4",      "drug": "AllerDuo",     "topic": "Mechanism",       "composition": "Bilastine + Montelukast"},
    {"file": "AllerDuo_dosage_safety.mp4",  "drug": "AllerDuo",     "topic": "Dosage & Safety", "composition": "Bilastine + Montelukast"},
    {"file": "Tibrolin_intro.mp4",          "drug": "Tibrolin",     "topic": "Intro",           "composition": "Trypsin + Bromelain + Rutoside"},
    {"file": "Subneuro-NT_intro.mp4",       "drug": "Subneuro-NT",  "topic": "Intro",           "composition": "Methylcobalamin + Pregabalin + Nortriptyline"},
    {"file": "Rexulti_intro.mp4",           "drug": "Rexulti",      "topic": "Intro",           "composition": "Brexpiprazole"},
]

TOPIC_COLORS = {
    "Intro":           "#fd4816",
    "Mechanism":       "#7c3aed",
    "Dosage & Safety": "#059669",
    "Indications":     "#2563eb",
    "Interactions":    "#d97706",
    "Side Effects":    "#db2777",
}

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SwishX — Pharma AI Video Reels",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;900&family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* Background */
.stApp { background-color: #0d0d0d !important; }

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer    { visibility: hidden; }
header    { visibility: hidden; }

/* Scrollbar */
::-webkit-scrollbar       { width: 4px; }
::-webkit-scrollbar-track { background: #111; }
::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

/* Headings */
h1, h2, h3, h4 { font-family: 'Montserrat', sans-serif !important; }

/* ── Hero ── */
.hero-eyebrow {
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 700;
    letter-spacing: 3px; text-transform: uppercase;
    color: #fd4816; margin-bottom: 14px;
}
.hero-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 2.8rem; font-weight: 900; line-height: 1.1;
    color: #ffffff; margin: 0 0 14px 0;
}
.hero-title .accent { color: #fd4816; }
.hero-sub { font-size: 1rem; color: #777; line-height: 1.7; margin-bottom: 2rem; }

/* ── Metrics strip ── */
.metrics-strip {
    display: flex; gap: 2.5rem;
    padding: 1.5rem 0;
    border-top: 1px solid #1c1c1c;
    border-bottom: 1px solid #1c1c1c;
    margin-bottom: 2rem;
}
.m-num  { font-family:'Montserrat',sans-serif; font-size:1.6rem; font-weight:900; color:#fd4816; line-height:1; }
.m-desc { font-size:11px; color:#555; text-transform:uppercase; letter-spacing:.5px; margin-top:3px; }

/* ── Divider ── */
.swx-hr { border:none; border-top:1px solid #1c1c1c; margin:0; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: transparent; gap: 0;
    border-bottom: 1px solid #1c1c1c; padding: 0;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Montserrat', sans-serif;
    font-weight: 600; font-size: 13px; color: #555;
    background: transparent; border: none;
    border-bottom: 2px solid transparent;
    padding: 12px 24px;
}
.stTabs [aria-selected="true"] {
    color: #ffffff !important;
    border-bottom-color: #fd4816 !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab-panel"] { padding: 2rem 0 0 0; }

/* ── Demo cards ── */
.demo-meta {
    background: #141414; border: 1px solid #1e1e1e;
    border-radius: 10px 10px 0 0; padding: 12px 14px 10px;
}
.demo-drug  { font-family:'Montserrat',sans-serif; font-weight:700; font-size:14px; color:#fff; }
.demo-comp  { font-size:11px; color:#555; margin:2px 0 8px; }
.t-badge    { display:inline-block; padding:2px 10px; border-radius:20px; font-size:11px; font-weight:600; font-family:'Montserrat',sans-serif; }

/* ── Section labels ── */
.sec-label {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: #fd4816; margin-bottom: 10px;
}
.sec-head { font-family:'Montserrat',sans-serif; font-weight:700; font-size:1.4rem; color:#fff; margin-bottom:4px; }
.sec-sub  { font-size:13px; color:#666; margin-bottom:1.5rem; }

/* ── Generate button ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg,#fd4816 0%,#d93d0f 100%) !important;
    color: #fff !important; border: none !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 700 !important; font-size: 14px !important;
    letter-spacing: .5px !important;
    padding: 14px 32px !important; border-radius: 8px !important;
    width: 100% !important; transition: opacity .2s !important;
}
.stButton > button[kind="primary"]:hover { opacity: .88 !important; }
.stButton > button[kind="primary"]:disabled { opacity: .35 !important; }

/* ── Inputs ── */
.stSelectbox  [data-baseweb="select"] > div { background:#141414 !important; border-color:#2a2a2a !important; }
.stTextArea   textarea                       { background:#141414 !important; border-color:#2a2a2a !important; color:#ccc !important; }
.stFileUploader > div                        { background:#141414 !important; border-color:#2a2a2a !important; border-style:dashed !important; }
.stRadio label                               { color:#aaa !important; }

/* ── Progress steps ── */
.p-step { font-size:13px; padding:5px 0; }
.p-step.waiting { color:#444; }
.p-step.active  { color:#fd4816; }
.p-step.done    { color:#22c55e; }

/* ── Download button ── */
.stDownloadButton > button {
    background: #141414 !important; color: #fd4816 !important;
    border: 1px solid #fd4816 !important; border-radius: 8px !important;
    font-family: 'Montserrat', sans-serif !important; font-weight: 600 !important;
    width: 100% !important;
}

/* ── Footer ── */
.swx-footer { text-align:center; font-size:11px; color:#333; padding:3rem 0 1.5rem; letter-spacing:.5px; }
.swx-footer .accent { color:#fd4816; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────

hcol1, hcol2 = st.columns([6, 1])
with hcol1:
    if SWISHX_LOGO.exists():
        st.image(str(SWISHX_LOGO), width=110)
    else:
        st.markdown(
            '<div style="font-family:Montserrat,sans-serif;font-size:1.6rem;'
            'font-weight:900;color:#fd4816;padding:10px 0 6px;">SwishX</div>',
            unsafe_allow_html=True,
        )
with hcol2:
    st.markdown(
        '<div style="text-align:right;padding-top:18px;font-size:10px;'
        'color:#444;font-family:Montserrat,sans-serif;letter-spacing:1.5px;'
        'text-transform:uppercase;">Pharma L&D</div>',
        unsafe_allow_html=True,
    )

st.markdown('<hr class="swx-hr">', unsafe_allow_html=True)

# ── Hero ─────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="padding:2.5rem 0 1.5rem;">
  <div class="hero-eyebrow">AI-Native Commercial Excellence · Pharma L&D</div>
  <div class="hero-title">
    Turn any drug PDF into<br>a <span class="accent">60-second video reel</span>
  </div>
  <div class="hero-sub">
    Upload a pharmaceutical monograph — get a narrated educational video with<br>
    quiz questions, gamification, and Indian English voiceover. Ready in minutes.
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="metrics-strip">
  <div><div class="m-num">60-120s</div><div class="m-desc">Reel length</div></div>
  <div><div class="m-num">6</div><div class="m-desc">Topic types</div></div>
  <div><div class="m-num">3</div><div class="m-desc">Audience profiles</div></div>
  <div><div class="m-num">~$0.30</div><div class="m-desc">Per video</div></div>
  <div><div class="m-num">8-12 min</div><div class="m-desc">Generation time</div></div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_demo, tab_gen = st.tabs(["▶  Watch Demos", "⚡  Generate New"])

# ── Tab: Demo Gallery ─────────────────────────────────────────────────────────

with tab_demo:
    st.markdown('<div class="sec-head">Demo Gallery</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-sub">Pre-generated reels across 4 drugs · No API key required</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3, gap="medium")
    for i, demo in enumerate(DEMO_VIDEOS):
        video_path = DEMOS_DIR / demo["file"]
        if not video_path.exists():
            continue
        color = TOPIC_COLORS.get(demo["topic"], "#fd4816")
        with cols[i % 3]:
            st.markdown(f"""
            <div class="demo-meta">
              <div class="demo-drug">{demo["drug"]}</div>
              <div class="demo-comp">{demo["composition"]}</div>
              <span class="t-badge" style="background:{color}1a;color:{color};border:1px solid {color}40;">{demo["topic"]}</span>
            </div>
            """, unsafe_allow_html=True)
            st.video(str(video_path))
            st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)

# ── Tab: Generate ─────────────────────────────────────────────────────────────

with tab_gen:
    st.markdown('<div class="sec-head">Generate a New Reel</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-sub">Upload a drug PDF and configure your reel · Requires API keys in environment</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="sec-label">① PDF Source</div>', unsafe_allow_html=True)
        existing_pdfs = (
            sorted(PDFS_DIR.glob("*.pdf")) + sorted(PDFS_DIR.glob("*.PDF"))
            if PDFS_DIR.exists() else []
        )
        pdf_source = st.radio(
            "PDF source", ["Upload new PDF", "Use a sample"],
            horizontal=True, label_visibility="collapsed",
        )
        pdf_path = None
        if pdf_source == "Upload new PDF":
            uploaded = st.file_uploader("Drop PDF here", type=["pdf"], label_visibility="collapsed")
            if uploaded:
                PDFS_DIR.mkdir(exist_ok=True)
                save_path = PDFS_DIR / uploaded.name
                save_path.write_bytes(uploaded.getbuffer())
                pdf_path = str(save_path)
                st.success(f"✓ {uploaded.name}")
        else:
            if existing_pdfs:
                selected = st.selectbox(
                    "Sample", existing_pdfs,
                    format_func=lambda p: p.stem,
                    label_visibility="collapsed",
                )
                pdf_path = str(selected)
            else:
                st.warning("No sample PDFs found in pdfs/")

        st.markdown("<div style='height:1.2rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec-label">③ Creative Direction (optional)</div>', unsafe_allow_html=True)
        guidance = st.text_area(
            "Direction", label_visibility="collapsed",
            placeholder="e.g. Focus on how this helps elderly patients manage chronic pain",
            height=100,
        )

    with right:
        st.markdown('<div class="sec-label">② Settings</div>', unsafe_allow_html=True)

        profile = st.selectbox(
            "Audience Profile", ["sales_executive", "stockist", "retailer", "doctor", "all"],
            format_func=lambda x: {
                "sales_executive": "🤝  Sales Executive (MR)",
                "stockist":        "📦  Stockist",
                "retailer":        "🏪  Retailer / Chemist",
                "doctor":          "👨‍⚕️  Doctor",
                "all":             "👥  All Profiles",
            }[x],
        )
        topic = st.selectbox(
            "Topic", ["intro", "indications", "mechanism", "dosage_safety", "interactions", "side_effects"],
            format_func=lambda x: {
                "intro":         "Intro",
                "indications":   "Indications",
                "mechanism":     "Mechanism of Action",
                "dosage_safety": "Dosage & Safety",
                "interactions":  "Drug Interactions",
                "side_effects":  "Side Effects",
            }[x],
        )
        voice_map = {
            "Gaurav — Professional, Calm": "gaurav",
            "Raj — Professional":          "raj",
            "Viraj — Smooth, Gentle":      "viraj",
            "Ruhaan — Clear, Cheerful":    "ruhaan",
            "Jeevan — Expressive":         "jeevan",
        }
        voice = voice_map[st.selectbox("Voice", list(voice_map.keys()))]
        tts = st.selectbox(
            "TTS Engine", ["elevenlabs", "gemini"],
            format_func=lambda x: {
                "elevenlabs": "ElevenLabs  (recommended)",
                "gemini":     "Gemini TTS",
            }[x],
        )
        include_quiz = st.checkbox("Include quiz + gamification", value=True)
        mode = "demo" if include_quiz else "production"

    st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)

    generate = st.button(
        "⚡  Generate Video Reel",
        type="primary",
        disabled=(pdf_path is None),
        use_container_width=True,
    )

    if generate:
        config = PipelineConfig(
            pdf_path=pdf_path,
            profile=profile,
            topic=topic,
            voice=voice,
            tts=tts,
            mode=mode,
            guidance=guidance,
        )

        steps = {
            "extract":   "Extract text from PDF",
            "analyze":   "Analyse content structure",
            "script":    "Generate script with Claude",
            "media":     "Generate frames + voiceover",
            "stitch":    "Stitch video",
            "subtitles": "Burn subtitles",
        }

        st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
        progress_bar = st.progress(0)
        st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)

        scol1, scol2 = st.columns(2)
        step_statuses = {}
        for j, (key, label) in enumerate(steps.items()):
            col = scol1 if j < 3 else scol2
            with col:
                step_statuses[key] = st.empty()
                step_statuses[key].markdown(
                    f'<div class="p-step waiting">· {label}</div>',
                    unsafe_allow_html=True,
                )

        current_step = [None]
        step_start   = [time.time()]

        def on_progress(step: str, message: str, pct: float):
            if current_step[0] and current_step[0] != step and current_step[0] in step_statuses:
                elapsed = time.time() - step_start[0]
                lbl = steps.get(current_step[0], current_step[0])
                step_statuses[current_step[0]].markdown(
                    f'<div class="p-step done">✓ {lbl} <span style="color:#333;font-size:11px">({elapsed:.0f}s)</span></div>',
                    unsafe_allow_html=True,
                )
            current_step[0] = step
            step_start[0]   = time.time()
            progress_bar.progress(min(pct, 1.0))
            if step in step_statuses:
                lbl = steps.get(step, step)
                step_statuses[step].markdown(
                    f'<div class="p-step active">⟳ {lbl}…</div>',
                    unsafe_allow_html=True,
                )

        result = run_pipeline(config, on_progress=on_progress)

        # Finalise last step
        if current_step[0] and current_step[0] in step_statuses:
            elapsed = time.time() - step_start[0]
            lbl = steps.get(current_step[0], current_step[0])
            step_statuses[current_step[0]].markdown(
                f'<div class="p-step done">✓ {lbl} <span style="color:#333;font-size:11px">({elapsed:.0f}s)</span></div>',
                unsafe_allow_html=True,
            )
        progress_bar.progress(1.0)

        st.markdown('<hr class="swx-hr" style="margin:1.5rem 0;">', unsafe_allow_html=True)

        if result.get("error"):
            st.error(f"Pipeline error: {result['error']}")
        elif result.get("video_path") and os.path.exists(result["video_path"]):
            st.success(f"✓ Generated in {result['duration']:.0f}s")
            st.video(result["video_path"])
            vid_bytes = Path(result["video_path"]).read_bytes()
            st.download_button(
                "⬇  Download MP4",
                data=vid_bytes,
                file_name=Path(result["video_path"]).name,
                mime="video/mp4",
            )
        else:
            st.error("Pipeline completed but no video was produced.")

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="swx-footer">
  Claude · Gemini · ElevenLabs · FFmpeg &nbsp;·&nbsp;
  <span class="accent">SwishX</span> © 2026
</div>
""", unsafe_allow_html=True)
