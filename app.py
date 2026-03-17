"""
SwishX — Pharma AI Video Reel Generator
Product demo page
"""

import os
import time
import base64
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
from config_loader import load_topic_map

BASE_DIR  = Path(__file__).parent
PDFS_DIR  = BASE_DIR / "pdfs"
DEMOS_DIR = BASE_DIR / "demos"
LOGO_PATH   = BASE_DIR / "assets" / "swishx_logo.png"
HERO_FRAME  = BASE_DIR / "assets" / "hero_frame.jpg"

DEMO_VIDEOS = [
    {"file": "AllerDuo_intro.mp4",        "drug": "AllerDuo",    "topic": "Intro",           "composition": "Bilastine + Montelukast"},
    {"file": "Tibrolin_intro.mp4",         "drug": "Tibrolin",    "topic": "Intro",           "composition": "Trypsin + Bromelain + Rutoside"},
    {"file": "Rexulti_intro.mp4",          "drug": "Rexulti",     "topic": "Intro",           "composition": "Brexpiprazole"},
    {"file": "Subneuro-NT_intro.mp4",      "drug": "Subneuro-NT", "topic": "Intro",           "composition": "Methylcobalamin + Pregabalin + Nortriptyline"},
    {"file": "AllerDuo_mechanism.mp4",     "drug": "AllerDuo",    "topic": "Mechanism",       "composition": "Bilastine + Montelukast"},
    {"file": "AllerDuo_dosage_safety.mp4", "drug": "AllerDuo",    "topic": "Dosage & Safety", "composition": "Bilastine + Montelukast"},
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
    page_title="SwishX — Pharma Video Reels",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700;900&family=Inter:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; }
html, body, [data-testid="stAppViewContainer"] { scroll-behavior: smooth !important; }

/* ── Reset Streamlit chrome ── */
section[data-testid="stSidebar"]  { display: none !important; }
div[data-testid="stToolbar"]      { display: none !important; }
div[data-testid="stDecoration"]   { display: none !important; }
div[data-testid="stStatusWidget"] { display: none !important; }
#MainMenu, footer, header         { visibility: hidden !important; }

.stApp,
.stApp > div,
div[data-testid="stAppViewContainer"],
div[data-testid="stMain"],
div[data-testid="stVerticalBlock"] {
    background-color: #0a0a0a !important;
}

div[data-testid="stMainBlockContainer"] {
    max-width: 1080px;
    padding: 1.5rem 2rem 4rem;
}

/* Fonts */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
label { font-family: 'Inter', sans-serif !important; }

::-webkit-scrollbar       { width: 4px; }
::-webkit-scrollbar-track { background: #0a0a0a; }
::-webkit-scrollbar-thumb { background: #222; border-radius: 2px; }

/* ── Phone mockup ── */
.phone-mockup {
    width: 210px;
    background: #000;
    border-radius: 28px;
    padding: 10px 8px;
    box-shadow: 0 24px 80px rgba(0,0,0,.6), 0 0 0 1px rgba(255,255,255,.06);
}
.phone-screen {
    border-radius: 20px;
    overflow: hidden;
    position: relative;
    aspect-ratio: 1080 / 1540;
}
.play-btn {
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 48px; height: 48px;
    background: rgba(0,0,0,.55);
    border: 2px solid rgba(255,255,255,.85);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    z-index: 10;
    pointer-events: none;
    backdrop-filter: blur(4px);
}
.play-btn::after {
    content: '';
    display: block;
    width: 0; height: 0;
    border-style: solid;
    border-width: 8px 0 8px 14px;
    border-color: transparent transparent transparent #fff;
    margin-left: 3px;
}
.hero-slide {
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    object-fit: cover;
    opacity: 0;
    animation: heroSlide 15s ease-in-out infinite;
}
.hero-slide:nth-child(1) { animation-delay: 0s; }
.hero-slide:nth-child(2) { animation-delay: 3s; }
.hero-slide:nth-child(3) { animation-delay: 6s; }
.hero-slide:nth-child(4) { animation-delay: 9s; }
.hero-slide:nth-child(5) { animation-delay: 12s; }

@keyframes heroSlide {
  0%    { opacity: 0; }
  3%    { opacity: 1; }
  20%   { opacity: 1; }
  23%   { opacity: 0; }
  100%  { opacity: 0; }
}

/* ── Logo ── */
.swx-logo {
    font-family: 'Montserrat', sans-serif;
    font-size: 1.5rem; font-weight: 900;
    color: #fd4816; padding: 6px 0;
}
.top-rule { border: none; border-top: 1px solid #181818; margin: .6rem 0 0; }

/* ── Hero ── */
.hero-eyebrow {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    letter-spacing: 3px; text-transform: uppercase;
    color: #fd4816; margin-bottom: 18px;
}
.hero-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 2.2rem; font-weight: 900; line-height: 1.15;
    color: #fff; margin: 0 0 18px;
}
.hero-title .a { color: #fd4816; }
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 15px; color: #666; line-height: 1.7;
}
.hero-pills {
    display: flex; flex-wrap: wrap; gap: 8px;
    margin-top: 20px;
}
.pill {
    font-family: 'Montserrat', sans-serif;
    font-size: 11px; font-weight: 600;
    color: #fd4816;
    background: rgba(253,72,22,.08);
    border: 1px solid rgba(253,72,22,.2);
    border-radius: 20px;
    padding: 5px 14px;
}
.hero-video-label {
    font-family: 'Inter', sans-serif;
    font-size: 11px; color: #444;
    text-align: center;
    margin-top: 8px;
}

/* ── Hero CTA ── */
.hero-cta {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin-top: 24px;
    margin-bottom: 4px;
    padding: 14px 36px;
    background: transparent;
    color: #fd4816 !important;
    font-family: 'Montserrat', sans-serif;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    border: 1.5px solid rgba(253,72,22,.35);
    border-radius: 40px;
    text-decoration: none !important;
    transition: all 0.3s ease;
}
.hero-cta:hover {
    border-color: #fd4816;
    background: rgba(253,72,22,.08);
    box-shadow: 0 0 20px rgba(253,72,22,.15);
}
.hero-cta .arrow {
    display: inline-block;
    transition: transform 0.3s ease;
}
.hero-cta:hover .arrow {
    transform: translateY(3px);
}

/* ── Section ── */
.section-rule {
    border: none; border-top: 1px solid #181818;
    margin: 3rem 0 2.5rem;
}
.s-eyebrow {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    letter-spacing: 2.5px; text-transform: uppercase;
    color: #fd4816; margin-bottom: 10px;
}
.s-title {
    font-family: 'Montserrat', sans-serif;
    font-size: 1.3rem; font-weight: 700;
    color: #fff; margin-bottom: 6px;
}
.s-sub {
    font-family: 'Inter', sans-serif;
    font-size: 13px; color: #555; margin-bottom: 1.6rem;
}

/* ── Feature cards ── */
.feat-card {
    background: #111;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 1.3rem 1.2rem;
    height: 100%;
    transition: border-color .25s;
}
.feat-card:hover { border-color: #2a2a2a; }
.feat-icon {
    font-size: 1.6rem;
    margin-bottom: 10px;
}
.feat-title {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700; font-size: 14px;
    color: #eee; margin-bottom: 6px;
}
.feat-desc {
    font-family: 'Inter', sans-serif;
    font-size: 12px; color: #555; line-height: 1.6;
}

/* ── Video cards ── */
.vid-meta {
    padding: 8px 2px 0;
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.vid-drug {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700; font-size: 13px; color: #ccc;
}
.vid-comp {
    font-family: 'Inter', sans-serif;
    font-size: 11px; color: #444;
}
.t-badge {
    display: inline-block; padding: 2px 9px;
    border-radius: 20px; font-size: 11px; font-weight: 600;
    font-family: 'Montserrat', sans-serif;
}

/* ── Form ── */
.form-label {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: #fd4816; margin-bottom: 8px; margin-top: 4px;
}
div[data-baseweb="select"] > div {
    background: #111 !important; border-color: #222 !important; color: #ccc !important;
}
div[data-baseweb="select"] svg { fill: #444 !important; }
textarea { background: #111 !important; border-color: #222 !important; color: #bbb !important; }
div[data-testid="stFileUploader"] > div {
    background: #111 !important; border: 1px dashed #222 !important; border-radius: 8px !important;
}
div[data-testid="stFileUploader"] p { color: #444 !important; }
.stRadio > div { gap: 1rem !important; }
.stRadio label p { color: #999 !important; font-size: 13px !important; }
.stCheckbox label p { color: #999 !important; }

/* ── Buttons ── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #fd4816 0%, #d93d0f 100%) !important;
    color: #fff !important; border: none !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 700 !important; font-size: 15px !important;
    padding: 14px 32px !important; border-radius: 8px !important;
    transition: opacity .2s !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover   { opacity: .88 !important; }
div[data-testid="stButton"] > button[kind="primary"]:disabled { opacity: .3 !important; }

div[data-testid="stDownloadButton"] > button {
    background: transparent !important; color: #fd4816 !important;
    border: 1px solid #fd4816 !important; border-radius: 8px !important;
    font-family: 'Montserrat', sans-serif !important; font-weight: 600 !important;
    width: 100% !important;
}

/* ── Progress ── */
div[data-testid="stProgress"] > div > div { background: #fd4816 !important; }
div[data-testid="stProgress"] > div       { background: #1a1a1a !important; }

.p-step         { font-family:'Inter',sans-serif; font-size:13px; padding:4px 0; }
.p-step.waiting { color:#2a2a2a; }
.p-step.active  { color:#fd4816; animation: stepPulse 1.8s ease-in-out infinite; }
.p-step.done    { color:#22c55e; }

@keyframes stepPulse {
  0%,100% { opacity:1; }
  50%     { opacity:.4; }
}
.spin-dot { display:inline-block; animation: spinPulse 2s ease-in-out infinite; }
@keyframes spinPulse {
  0%,100% { transform:scale(1);   opacity:1; }
  50%     { transform:scale(1.15); opacity:.65; }
}



/* ── Loading skeleton ── */
.video-skeleton {
    background: #111;
    border: 1px solid #1a1a1a;
    border-radius: 12px;
    padding: 3rem 1.5rem;
    text-align: center;
    min-height: 320px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    animation: skeletonPulse 2.5s ease-in-out infinite;
}
.video-skeleton .skeleton-icon {
    font-size: 2.5rem;
    margin-bottom: 1rem;
}
.video-skeleton .skeleton-text {
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: #444;
}
@keyframes skeletonPulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* ── Alerts ── */
div[data-testid="stAlert"] { border-radius: 8px !important; }

/* ── Expander ── */
div[data-testid="stExpander"] {
    background: #111 !important;
    border: 1px solid #1a1a1a !important;
    border-radius: 10px !important;
}
div[data-testid="stExpander"] summary {
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 600 !important;
    color: #ddd !important;
}

/* ── Toast notification — top-right ── */
div[data-testid="stToast"] {
    top: 1rem !important;
    bottom: auto !important;
}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════

if LOGO_PATH.exists():
    st.image(str(LOGO_PATH), width=110)
else:
    st.markdown('<div class="swx-logo">SwishX</div>', unsafe_allow_html=True)

st.markdown('<hr class="top-rule">', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HERO — headline left, featured video right
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

hero_left, hero_right = st.columns([3, 1.8], gap="large")

with hero_left:
    st.markdown("""
    <div style="padding-top:.8rem;">
      <div class="hero-eyebrow">Pharma L&D, reimagined</div>
      <div class="hero-title">
        Nobody reads a<br>40-page PDF.<br>
        <span class="a">Make them watch a<br>60-second reel instead.</span>
      </div>
      <p class="hero-sub">
        Turn any drug PDF into a fun, narrated video reel — followed
        by a quick gamified quiz that tests understanding, ranks your
        field team, and gives you learning data at scale.
      </p>
      <a href="#try-it" class="hero-cta">Try it yourself <span class="arrow">&darr;</span></a>
      <div class="hero-pills">
        <span class="pill">AI-Narrated Reels</span>
        <span class="pill">Gamified Quizzes</span>
        <span class="pill">Team Leaderboard</span>
        <span class="pill">Learning Analytics</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

with hero_right:
    slide_dir = BASE_DIR / "assets"
    slide_files = [slide_dir / f"slide_{i}.jpg" for i in range(1, 6)]
    slides_exist = all(f.exists() for f in slide_files)
    if slides_exist:
        imgs_b64 = [base64.b64encode(f.read_bytes()).decode() for f in slide_files]
        slide_tags = "\n".join(
            f'<img class="hero-slide" src="data:image/jpeg;base64,{b}" />'
            for b in imgs_b64
        )
        st.markdown(f"""
        <a href="#demo-reels" style="text-decoration:none; display:flex; justify-content:center; padding-top:0.5rem;">
          <div class="phone-mockup" style="cursor:pointer;">
            <div class="phone-screen">
              {slide_tags}
              <div class="play-btn"></div>
            </div>
          </div>
        </a>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# WHAT'S IN EACH REEL — 4 feature cards
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<hr class="section-rule">', unsafe_allow_html=True)
st.markdown('<div class="s-eyebrow">What each reel includes</div>', unsafe_allow_html=True)
st.markdown('<div class="s-title">Education meets gamification</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="s-sub">Every reel has four parts designed to maximise knowledge retention and engagement</div>',
    unsafe_allow_html=True,
)

FEATURES = [
    ("🎬", "Bite-Sized Video Reels",
     "Your reps watch a 60-second reel instead of skimming a 40-page PDF. Every scene is tailored to their role — so they remember what matters."),
    ("🧠", "Built-In Knowledge Check",
     "Quick questions after each reel that test real understanding — not just recall. You see exactly who gets it and who doesn't."),
    ("🏆", "Streaks That Stick",
     "Daily streaks and instant feedback keep your team coming back. Completion rates go up because it feels like a game, not homework."),
    ("📊", "Live Team Rankings",
     "See who's leading across regions, teams, or roles. A little friendly competition turns training from a chore into a challenge."),
]

fcols = st.columns(4, gap="medium")
for i, (icon, title, desc) in enumerate(FEATURES):
    with fcols[i]:
        st.markdown(f"""
        <div class="feat-card">
          <div class="feat-icon">{icon}</div>
          <div class="feat-title">{title}</div>
          <div class="feat-desc">{desc}</div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE REELS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<hr class="section-rule" id="demo-reels">', unsafe_allow_html=True)
st.markdown('<div class="s-eyebrow">See it in action</div>', unsafe_allow_html=True)
st.markdown('<div class="s-title">Sample reels across 4 drugs</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="s-sub">Each generated from a single PDF — fully automated, no editing needed</div>',
    unsafe_allow_html=True,
)

vcols = st.columns(3, gap="medium")
for i, demo in enumerate(DEMO_VIDEOS):
    video_path = DEMOS_DIR / demo["file"]
    if not video_path.exists():
        continue
    color = TOPIC_COLORS.get(demo["topic"], "#fd4816")
    with vcols[i % 3]:
        st.video(str(video_path))
        st.markdown(f"""
        <div class="vid-meta">
          <span class="t-badge" style="background:{color}12;color:{color};border:1px solid {color}33;">{demo["topic"]}</span>
          <div>
            <div class="vid-drug">{demo["drug"]}</div>
            <div class="vid-comp">{demo["composition"]}</div>
          </div>
        </div>
        <div style="height:1.4rem;"></div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# GENERATE YOUR OWN
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<hr class="section-rule" id="try-it">', unsafe_allow_html=True)
st.markdown('<div class="s-eyebrow">Try it yourself</div>', unsafe_allow_html=True)
st.markdown('<div class="s-title">Generate a reel from any drug PDF</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="s-sub">Pick a sample PDF or upload your own — takes about 5 minutes to generate</div>',
    unsafe_allow_html=True,
)

if "generating" not in st.session_state:
    st.session_state.generating = False
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

is_generating = st.session_state.generating

left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown('<div class="form-label">① Choose a PDF</div>', unsafe_allow_html=True)
    existing_pdfs = (
        sorted(PDFS_DIR.glob("*.pdf")) + sorted(PDFS_DIR.glob("*.PDF"))
        if PDFS_DIR.exists() else []
    )
    pdf_source = st.radio(
        "source", ["Upload new", "Use a sample"],
        horizontal=True, label_visibility="collapsed",
        disabled=is_generating,
    )
    pdf_path = None
    if pdf_source == "Upload new":
        uploaded = st.file_uploader("pdf", type=["pdf"], label_visibility="collapsed", disabled=is_generating)
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
                disabled=is_generating,
            )
            pdf_path = str(selected)
        else:
            st.info("No sample PDFs available")

    st.markdown("<div style='height:.8rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="form-label">③ Focus (optional)</div>', unsafe_allow_html=True)
    guidance = st.text_area(
        "focus", label_visibility="collapsed",
        placeholder="e.g. Emphasise pain relief for elderly patients",
        height=80,
        disabled=is_generating,
    )

with right:
    st.markdown('<div class="form-label">② Configure</div>', unsafe_allow_html=True)

    profile = st.selectbox(
        "Audience",
        ["sales_executive", "stockist", "retailer", "doctor", "all"],
        format_func=lambda x: {
            "sales_executive": "🤝  Sales Executive / MR",
            "stockist":        "📦  Stockist",
            "retailer":        "🏪  Retailer / Chemist",
            "doctor":          "👨‍⚕️  Doctor",
            "all":             "👥  All Profiles",
        }[x],
        disabled=is_generating,
    )
    topic_entries = load_topic_map(profile)
    topic_keys = [t["key"] for t in topic_entries]
    topic_labels = {t["key"]: t["label"] for t in topic_entries}
    topic = st.selectbox(
        "Topic",
        topic_keys,
        format_func=lambda x: topic_labels.get(x, x),
        key=f"topic_{profile}",
        disabled=is_generating,
    )
    voice_map = {
        "Gaurav — Professional, Calm": "gaurav",
        "Raj — Professional":          "raj",
        "Viraj — Smooth, Gentle":      "viraj",
        "Ruhaan — Clear, Cheerful":    "ruhaan",
        "Jeevan — Expressive":         "jeevan",
    }
    voice = voice_map[st.selectbox("Voice", list(voice_map.keys()), disabled=is_generating)]
    include_quiz = st.checkbox("Include quiz + gamification", value=True, disabled=is_generating)
    mode = "demo" if include_quiz else "production"

st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
generate = st.button(
    "⚡  Generating…" if is_generating else "⚡  Generate Video Reel",
    type="primary",
    disabled=(pdf_path is None or is_generating),
    use_container_width=True,
)

if generate and not is_generating:
    st.session_state.generating = True
    st.session_state.pipeline_config = dict(
        pdf_path=pdf_path,
        profile=profile,
        topic=topic,
        voice=voice,
        tts="elevenlabs",
        mode=mode,
        guidance=guidance,
    )
    st.rerun()

if is_generating:
    config = PipelineConfig(**st.session_state.pipeline_config)

    TOTAL_ESTIMATE = 330  # ~5.5 min total pipeline
    STEP_META = {
        "extract":   ("Reading your PDF",          "Extracting all text, drug names, and data from the document…"),
        "analyze":   ("Understanding the content",  "Mapping indications, mechanism, dosage, and safety data…"),
        "script":    ("Writing the script",         "Crafting a narrative tailored to your audience and topic…"),
        "media":     ("Bringing it to life",        "Generating visuals for each scene and recording the voiceover — the longest step…"),
        "stitch":    ("Assembling the video",       "Combining scenes, transitions, audio, and branding…"),
        "subtitles": ("Final touches",              "Adding subtitles and polishing the reel…"),
    }
    STEP_ORDER = list(STEP_META.keys())

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    out_left, out_right = st.columns([1.2, 1], gap="large")

    with out_left:
        video_area = st.empty()
        video_area.markdown("""
        <div class="video-skeleton">
          <div class="skeleton-icon">🎬</div>
          <div class="skeleton-text">Your reel is being crafted…</div>
        </div>
        """, unsafe_allow_html=True)
        download_area = st.empty()

    with out_right:
        status_box = st.empty()
        progress_bar = st.progress(0)
        st.markdown("<div style='height:.5rem'></div>", unsafe_allow_html=True)
        scol1, scol2 = st.columns(2)
        step_ui = {}
        for j, key in enumerate(STEP_ORDER):
            col = scol1 if j < 3 else scol2
            with col:
                step_ui[key] = st.empty()
                step_ui[key].markdown(
                    f'<div class="p-step waiting">· {STEP_META[key][0]}</div>',
                    unsafe_allow_html=True,
                )

    run_start    = time.time()
    cur_step     = [None]
    step_start   = [time.time()]

    def _ft(s):
        s = max(0, int(s))
        return f"{s}s" if s < 60 else f"{s // 60}m {s % 60:02d}s"

    def _render_status(step, pct, message=""):
        meta = STEP_META.get(step, (step, ""))
        label = meta[0]
        desc = message if message else meta[1]
        elapsed = time.time() - run_start
        remaining = max(0, TOTAL_ESTIMATE - elapsed)
        pct_i = int(min(pct, 1.0) * 100)
        status_box.markdown(f"""
        <div style="background:#111; border:1px solid #1e1e1e; border-left:3px solid #fd4816;
                    border-radius:10px; padding:1.1rem 1.3rem; margin-bottom:.3rem;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:.5rem;">
            <div>
              <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:15px; color:#fff; margin-bottom:5px;">
                <span class="spin-dot">⏳</span>&nbsp; {label}
              </div>
              <div style="font-family:'Inter',sans-serif; font-size:13px; color:#666; max-width:460px;">
                {desc}
              </div>
            </div>
            <div style="text-align:right; flex-shrink:0;">
              <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:1.1rem; color:#fd4816;">{pct_i}%</div>
              <div style="font-family:'Inter',sans-serif; font-size:11px; color:#333; margin-top:2px;">{_ft(elapsed)} elapsed</div>
              <div style="font-family:'Inter',sans-serif; font-size:11px; color:#333; margin-top:1px;">~{_ft(remaining)} remaining</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    def on_progress(step, message, pct):
        if cur_step[0] and cur_step[0] != step and cur_step[0] in step_ui:
            el = time.time() - step_start[0]
            lbl = STEP_META.get(cur_step[0], (cur_step[0],))[0]
            step_ui[cur_step[0]].markdown(
                f'<div class="p-step done">✓ {lbl} <span style="color:#222;font-size:11px">({_ft(el)})</span></div>',
                unsafe_allow_html=True,
            )
        if cur_step[0] != step:
            step_start[0] = time.time()
        cur_step[0] = step
        progress_bar.progress(min(pct, 1.0))
        if step in step_ui:
            step_ui[step].markdown(
                f'<div class="p-step active">⟳ {STEP_META.get(step, (step,))[0]}</div>',
                unsafe_allow_html=True,
            )
        _render_status(step, pct, message)

    result = run_pipeline(config, on_progress=on_progress)

    # Finalise progress
    if cur_step[0] and cur_step[0] in step_ui:
        el = time.time() - step_start[0]
        lbl = STEP_META.get(cur_step[0], (cur_step[0],))[0]
        step_ui[cur_step[0]].markdown(
            f'<div class="p-step done">✓ {lbl} <span style="color:#222;font-size:11px">({_ft(el)})</span></div>',
            unsafe_allow_html=True,
        )
    progress_bar.progress(1.0)
    total = time.time() - run_start

    status_box.markdown(f"""
    <div style="background:#0a150d; border:1px solid #153020; border-left:3px solid #22c55e;
                border-radius:10px; padding:1.1rem 1.3rem; margin-bottom:.3rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:.5rem;">
        <div>
          <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:15px; color:#22c55e; margin-bottom:3px;">
            ✓ &nbsp;Your reel is ready
          </div>
          <div style="font-family:'Inter',sans-serif; font-size:13px; color:#444;">
            Generated in {_ft(total)}
          </div>
        </div>
        <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:1.1rem; color:#22c55e;">100%</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.session_state.generating = False
    st.session_state.pipeline_result = result

    if result.get("error"):
        video_area.error(f"Something went wrong: {result['error']}")
    elif result.get("video_path") and os.path.exists(result["video_path"]):
        vid_bytes = Path(result["video_path"]).read_bytes()
        vid_b64 = base64.b64encode(vid_bytes).decode()
        video_area.markdown(
            f'<video controls style="max-height:420px;width:auto;display:block;margin:0 auto;border-radius:8px;">'
            f'<source src="data:video/mp4;base64,{vid_b64}" type="video/mp4"></video>',
            unsafe_allow_html=True,
        )
        download_area.download_button(
            "⬇  Download MP4",
            data=vid_bytes,
            file_name=Path(result["video_path"]).name,
            mime="video/mp4",
        )
        st.toast("Your reel is ready!", icon="🎬")
    else:
        video_area.error("Generation completed but no video was produced.")

elif st.session_state.pipeline_result is not None:
    result = st.session_state.pipeline_result
    if result.get("video_path") and os.path.exists(result["video_path"]):
        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
        out_left, out_right = st.columns([1.2, 1], gap="large")
        with out_left:
            vid_bytes = Path(result["video_path"]).read_bytes()
            vid_b64 = base64.b64encode(vid_bytes).decode()
            st.markdown(
                f'<video controls style="max-height:420px;width:auto;display:block;margin:0 auto;border-radius:8px;">'
                f'<source src="data:video/mp4;base64,{vid_b64}" type="video/mp4"></video>',
                unsafe_allow_html=True,
            )
            st.download_button(
                "⬇  Download MP4",
                data=vid_bytes,
                file_name=Path(result["video_path"]).name,
                mime="video/mp4",
            )
        with out_right:
            st.markdown("""
            <div style="background:#0a150d; border:1px solid #153020; border-left:3px solid #22c55e;
                        border-radius:10px; padding:1.1rem 1.3rem;">
              <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:15px; color:#22c55e; margin-bottom:3px;">
                ✓ &nbsp;Your reel is ready
              </div>
              <div style="font-family:'Inter',sans-serif; font-size:13px; color:#444;">
                Download or generate another reel above.
              </div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div style="text-align:center; padding:3rem 0 1rem; font-size:11px; color:#1e1e1e;
            font-family:'Montserrat',sans-serif; letter-spacing:.5px;">
  SwishX © 2026
</div>
""", unsafe_allow_html=True)
