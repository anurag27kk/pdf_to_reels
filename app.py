"""
SwishX — Pharma AI Video Reel Generator
"""

import os
import time
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# On Streamlit Cloud, secrets are in st.secrets — inject into env so pipeline picks them up
try:
    import streamlit as _st
    for _key in ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY"]:
        if _key in _st.secrets and not os.environ.get(_key):
            os.environ[_key] = _st.secrets[_key]
except Exception:
    pass

from pipeline import PipelineConfig, run_pipeline

BASE_DIR  = Path(__file__).parent
PDFS_DIR  = BASE_DIR / "pdfs"
DEMOS_DIR = BASE_DIR / "demos"
LOGO_PATH = BASE_DIR / "assets" / "swishx_logo.png"

DEMO_VIDEOS = [
    {"file": "AllerDuo_intro.mp4",        "drug": "AllerDuo",    "topic": "Intro",           "composition": "Bilastine + Montelukast"},
    {"file": "AllerDuo_mechanism.mp4",     "drug": "AllerDuo",    "topic": "Mechanism",       "composition": "Bilastine + Montelukast"},
    {"file": "AllerDuo_dosage_safety.mp4", "drug": "AllerDuo",    "topic": "Dosage & Safety", "composition": "Bilastine + Montelukast"},
    {"file": "Tibrolin_intro.mp4",         "drug": "Tibrolin",    "topic": "Intro",           "composition": "Trypsin + Bromelain + Rutoside"},
    {"file": "Subneuro-NT_intro.mp4",      "drug": "Subneuro-NT", "topic": "Intro",           "composition": "Methylcobalamin + Pregabalin + Nortriptyline"},
    {"file": "Rexulti_intro.mp4",          "drug": "Rexulti",     "topic": "Intro",           "composition": "Brexpiprazole"},
]

TOPIC_COLORS = {
    "Intro":           "#fd4816",
    "Mechanism":       "#7c3aed",
    "Dosage & Safety": "#059669",
    "Indications":     "#2563eb",
    "Interactions":    "#d97706",
    "Side Effects":    "#db2777",
}

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SwishX — Pharma AI Video Reels",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;900&family=Inter:wght@400;500;600&display=swap');

/* ── Global ── */
*, *::before, *::after { box-sizing: border-box; }

section[data-testid="stSidebar"]    { display: none !important; }
div[data-testid="stToolbar"]        { display: none !important; }
div[data-testid="stDecoration"]     { display: none !important; }
div[data-testid="stStatusWidget"]   { display: none !important; }
#MainMenu, footer, header           { visibility: hidden !important; }

.stApp,
.stApp > div,
div[data-testid="stAppViewContainer"],
div[data-testid="stMain"],
div[data-testid="stVerticalBlock"] {
    background-color: #0d0d0d !important;
}

/* Block container max-width + padding */
div[data-testid="stMainBlockContainer"] {
    max-width: 1100px;
    padding: 2rem 2rem 4rem;
}

/* Fonts — target Streamlit's actual rendered elements */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
label, .stSelectbox label, .stRadio label, .stCheckbox label {
    font-family: 'Inter', sans-serif !important;
}

/* Scrollbar */
::-webkit-scrollbar       { width: 4px; }
::-webkit-scrollbar-track { background: #0d0d0d; }
::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }

/* ── Header ── */
.swx-logo-text {
    font-family: 'Montserrat', sans-serif;
    font-size: 1.7rem; font-weight: 900;
    color: #fd4816; line-height: 1;
    padding: 8px 0;
}
.swx-divider { border: none; border-top: 1px solid #1e1e1e; margin: 0.75rem 0 0; }

/* ── Hero ── */
.hero-eyebrow {
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 700;
    letter-spacing: 3px; text-transform: uppercase;
    color: #fd4816; margin-bottom: 16px;
}
.hero-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 2.6rem; font-weight: 900; line-height: 1.1;
    color: #fff; margin: 0 0 16px;
}
.hero-title .accent { color: #fd4816; }
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 1rem; color: #777; line-height: 1.7;
    max-width: 560px;
}

/* ── Metrics ── */
.metrics-row {
    display: flex; flex-wrap: wrap; gap: 2rem;
    padding: 1.4rem 0;
    border-top: 1px solid #1e1e1e;
    border-bottom: 1px solid #1e1e1e;
    margin: 1.8rem 0 2.2rem;
}
.metric { min-width: 80px; }
.metric-num  {
    font-family: 'Montserrat', sans-serif;
    font-size: 1.5rem; font-weight: 900;
    color: #fd4816; line-height: 1;
}
.metric-lbl {
    font-family: 'Inter', sans-serif;
    font-size: 10px; color: #555;
    text-transform: uppercase; letter-spacing: .6px;
    margin-top: 4px;
}

/* ── Tabs ── */
div[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid #1e1e1e !important;
    gap: 0 !important;
}
button[data-baseweb="tab"] {
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 600 !important; font-size: 13px !important;
    color: #555 !important;
    background: transparent !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 22px !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #fff !important;
    border-bottom-color: #fd4816 !important;
}
div[data-baseweb="tab-panel"] { padding-top: 1.8rem !important; }

/* ── Section headings ── */
.sec-head {
    font-family: 'Montserrat', sans-serif;
    font-size: 1.25rem; font-weight: 700; color: #fff;
    margin-bottom: 4px;
}
.sec-sub {
    font-family: 'Inter', sans-serif;
    font-size: 13px; color: #555; margin-bottom: 1.4rem;
}

/* ── Demo video cards ── */
.video-label {
    padding: 10px 2px 0;
    display: flex; align-items: center; gap: 10px;
    flex-wrap: wrap;
}
.video-drug {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700; font-size: 13px; color: #ddd;
}
.video-comp {
    font-family: 'Inter', sans-serif;
    font-size: 11px; color: #555;
    margin-top: 1px;
}
.t-badge {
    display: inline-block; padding: 2px 9px;
    border-radius: 20px; font-size: 11px; font-weight: 600;
    font-family: 'Montserrat', sans-serif;
}

/* ── Form section label ── */
.form-label {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: #fd4816; margin-bottom: 8px; margin-top: 4px;
}

/* ── Inputs ── */
div[data-baseweb="select"] > div {
    background-color: #141414 !important;
    border-color: #2a2a2a !important;
    color: #ddd !important;
}
div[data-baseweb="select"] svg { fill: #555 !important; }
textarea {
    background-color: #141414 !important;
    border-color: #2a2a2a !important;
    color: #ccc !important;
}
div[data-testid="stFileUploader"] > div {
    background: #141414 !important;
    border: 1px dashed #2a2a2a !important;
    border-radius: 8px !important;
}
div[data-testid="stFileUploader"] p { color: #555 !important; }
.stRadio > div { gap: 1rem !important; }
.stRadio label p { color: #aaa !important; font-size: 14px !important; }
.stCheckbox label p { color: #aaa !important; }

/* ── Generate button ── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #fd4816 0%, #d93d0f 100%) !important;
    color: #fff !important; border: none !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 700 !important; font-size: 15px !important;
    letter-spacing: .4px !important;
    padding: 14px 32px !important;
    border-radius: 8px !important;
    transition: opacity .2s !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover   { opacity: .88 !important; }
div[data-testid="stButton"] > button[kind="primary"]:disabled { opacity: .3 !important; cursor: not-allowed !important; }

/* ── Download button ── */
div[data-testid="stDownloadButton"] > button {
    background: transparent !important;
    color: #fd4816 !important;
    border: 1px solid #fd4816 !important;
    border-radius: 8px !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 600 !important;
    width: 100% !important;
}

/* ── Progress ── */
div[data-testid="stProgress"] > div > div {
    background: #fd4816 !important;
}
div[data-testid="stProgress"] > div {
    background: #1e1e1e !important;
}

.p-step         { font-family:'Inter',sans-serif; font-size:13px; padding:4px 0; }
.p-step.waiting { color: #333; }
.p-step.active  { color: #fd4816; }
.p-step.done    { color: #22c55e; }

/* ── Alerts ── */
div[data-testid="stAlert"] { border-radius: 8px !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────

hcol, _ = st.columns([5, 1])
with hcol:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), width=120)
    else:
        st.markdown('<div class="swx-logo-text">SwishX</div>', unsafe_allow_html=True)

st.markdown('<hr class="swx-divider">', unsafe_allow_html=True)

# ── Hero ──────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="padding:2.2rem 0 0.5rem;">
  <div class="hero-eyebrow">Pharma L&D · AI-Powered</div>
  <div class="hero-title">
    Turn any drug PDF into<br>a <span class="accent">60-second video reel</span>
  </div>
  <p class="hero-sub">
    Upload a pharmaceutical monograph — get a narrated, educational video
    with quiz questions, gamification, and voiceover. Ready in minutes.
  </p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="metrics-row">
  <div class="metric"><div class="metric-num">60-120s</div><div class="metric-lbl">Reel length</div></div>
  <div class="metric"><div class="metric-num">6</div><div class="metric-lbl">Topic types</div></div>
  <div class="metric"><div class="metric-num">4</div><div class="metric-lbl">Profiles</div></div>
  <div class="metric"><div class="metric-num">~$0.30</div><div class="metric-lbl">Per video</div></div>
  <div class="metric"><div class="metric-num">~5 min</div><div class="metric-lbl">Generation time</div></div>
</div>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_demo, tab_gen = st.tabs(["▶  Watch Demos", "⚡  Generate New"])

# ── Tab: Demo Gallery ─────────────────────────────────────────────────────────

with tab_demo:
    st.markdown('<div class="sec-head">Sample Reels</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-sub">Pre-generated across 4 drugs and multiple topic types</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(3, gap="medium")
    for i, demo in enumerate(DEMO_VIDEOS):
        video_path = DEMOS_DIR / demo["file"]
        if not video_path.exists():
            continue
        color = TOPIC_COLORS.get(demo["topic"], "#fd4816")
        with cols[i % 3]:
            st.video(str(video_path))
            st.markdown(f"""
            <div class="video-label">
              <span class="t-badge" style="background:{color}1a;color:{color};border:1px solid {color}44;">{demo["topic"]}</span>
              <div>
                <div class="video-drug">{demo["drug"]}</div>
                <div class="video-comp">{demo["composition"]}</div>
              </div>
            </div>
            <div style="height:1.6rem;"></div>
            """, unsafe_allow_html=True)

# ── Tab: Generate ─────────────────────────────────────────────────────────────

with tab_gen:
    st.markdown('<div class="sec-head">Generate a New Reel</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sec-sub">Upload a drug PDF, configure your reel, and generate in ~5 minutes</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1], gap="large")

    with left:
        st.markdown('<div class="form-label">① PDF</div>', unsafe_allow_html=True)
        existing_pdfs = (
            sorted(PDFS_DIR.glob("*.pdf")) + sorted(PDFS_DIR.glob("*.PDF"))
            if PDFS_DIR.exists() else []
        )
        pdf_source = st.radio(
            "source", ["Upload new", "Use a sample"],
            horizontal=True, label_visibility="collapsed",
        )
        pdf_path = None
        if pdf_source == "Upload new":
            uploaded = st.file_uploader(
                "pdf", type=["pdf"], label_visibility="collapsed",
            )
            if uploaded:
                PDFS_DIR.mkdir(exist_ok=True)
                save_path = PDFS_DIR / uploaded.name
                save_path.write_bytes(uploaded.getbuffer())
                pdf_path = str(save_path)
                st.success(f"✓ {uploaded.name}")
        else:
            if existing_pdfs:
                selected = st.selectbox(
                    "sample", existing_pdfs,
                    format_func=lambda p: p.stem,
                    label_visibility="collapsed",
                )
                pdf_path = str(selected)
            else:
                st.info("No sample PDFs available")

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        st.markdown('<div class="form-label">③ Focus (optional)</div>', unsafe_allow_html=True)
        guidance = st.text_area(
            "focus", label_visibility="collapsed",
            placeholder="e.g. Emphasise pain relief for elderly patients",
            height=90,
        )

    with right:
        st.markdown('<div class="form-label">② Settings</div>', unsafe_allow_html=True)

        profile = st.selectbox(
            "Audience",
            ["sales_executive", "stockist", "retailer", "doctor", "all"],
            format_func=lambda x: {
                "sales_executive": "🤝  Sales Executive (MR)",
                "stockist":        "📦  Stockist",
                "retailer":        "🏪  Retailer / Chemist",
                "doctor":          "👨‍⚕️  Doctor",
                "all":             "👥  All Profiles",
            }[x],
        )
        topic = st.selectbox(
            "Topic",
            ["intro", "indications", "mechanism", "dosage_safety", "interactions", "side_effects"],
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
        include_quiz = st.checkbox("Include quiz + gamification", value=True)
        mode = "demo" if include_quiz else "production"

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
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
            tts="elevenlabs",
            mode=mode,
            guidance=guidance,
        )

        steps = {
            "extract":   "Extracting text",
            "analyze":   "Analysing content",
            "script":    "Writing script",
            "media":     "Generating visuals + audio",
            "stitch":    "Stitching video",
            "subtitles": "Adding subtitles",
        }

        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
        progress_bar = st.progress(0)
        st.markdown("<div style='height:.3rem'></div>", unsafe_allow_html=True)

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
                    f'<div class="p-step done">✓ {lbl}'
                    f'<span style="color:#2a2a2a;font-size:11px;margin-left:6px">({elapsed:.0f}s)</span></div>',
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

        if current_step[0] and current_step[0] in step_statuses:
            elapsed = time.time() - step_start[0]
            lbl = steps.get(current_step[0], current_step[0])
            step_statuses[current_step[0]].markdown(
                f'<div class="p-step done">✓ {lbl}'
                f'<span style="color:#2a2a2a;font-size:11px;margin-left:6px">({elapsed:.0f}s)</span></div>',
                unsafe_allow_html=True,
            )
        progress_bar.progress(1.0)

        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

        if result.get("error"):
            st.error(f"Something went wrong: {result['error']}")
        elif result.get("video_path") and os.path.exists(result["video_path"]):
            st.success(f"✓ Reel generated in {result['duration']:.0f}s")
            st.video(result["video_path"])
            st.download_button(
                "⬇  Download MP4",
                data=Path(result["video_path"]).read_bytes(),
                file_name=Path(result["video_path"]).name,
                mime="video/mp4",
            )
        else:
            st.error("Pipeline completed but no video was produced.")

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="text-align:center;padding:3rem 0 1rem;font-size:11px;color:#2a2a2a;
            font-family:'Montserrat',sans-serif;letter-spacing:.5px;">
  SwishX © 2026
</div>
""", unsafe_allow_html=True)
