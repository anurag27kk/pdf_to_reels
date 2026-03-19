"""
SwishX — Pharma AI Video Reel Generator
Product demo page
"""

import os
import json
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

def _img_b64(path):
    """Read an image file and return base64 string."""
    return base64.b64encode(Path(path).read_bytes()).decode()

BASE_DIR      = Path(__file__).parent
PDFS_DIR      = BASE_DIR / "pdfs"
DEMOS_DIR     = BASE_DIR / "demos"
LOGO_PATH     = BASE_DIR / "assets" / "Swish_X_black_logo_02.png"
HERO_FRAME    = BASE_DIR / "assets" / "hero_frame.jpg"
COMPANIES_DIR = BASE_DIR / "companies"

# ── Company preset (URL param: ?company=slug) ──────────────────────────────
_company_param  = st.query_params.get("company", "")
_company_config: dict = {}
if _company_param:
    _cfg_path = COMPANIES_DIR / "companies.json"
    if _cfg_path.exists():
        _all = json.loads(_cfg_path.read_text())
        _company_config = _all.get(_company_param, {})

PRESET_COMPANY_NAME = _company_config.get("name", "")
PRESET_LOGO_PATH    = (
    COMPANIES_DIR / _company_config["logo"]
    if _company_config.get("logo") else None
)

DEMO_VIDEOS = [
    {"file": "AllerDuo_intro.mp4",        "drug": "AllerDuo",    "topic": "Intro",
     "composition": "Bilastine + Montelukast", "pdf_thumb": "assets/pdf_thumb_AllerDuo.png", "pages": 9},
    {"file": "Tibrolin_intro.mp4",         "drug": "Tibrolin",    "topic": "Intro",
     "composition": "Trypsin + Bromelain + Rutoside", "pdf_thumb": "assets/pdf_thumb_Tibrolin.png", "pages": 4},
    {"file": "Rexulti_intro.mp4",          "drug": "Rexulti",     "topic": "Intro",
     "composition": "Brexpiprazole", "pdf_thumb": "assets/pdf_thumb_Rexulti.png", "pages": 9},
    {"file": "Subneuro-NT_intro.mp4",      "drug": "Subneuro-NT", "topic": "Intro",
     "composition": "Methylcobalamin + Pregabalin + Nortriptyline", "pdf_thumb": "assets/pdf_thumb_Subneuro-NT.png", "pages": 4},
    {"file": "AllerDuo_mechanism.mp4",     "drug": "AllerDuo",    "topic": "Mechanism",
     "composition": "Bilastine + Montelukast", "pdf_thumb": "assets/pdf_thumb_AllerDuo.png", "pages": 9},
    {"file": "AllerDuo_dosage_safety.mp4", "drug": "AllerDuo",    "topic": "Dosage & Safety",
     "composition": "Bilastine + Montelukast", "pdf_thumb": "assets/pdf_thumb_AllerDuo.png", "pages": 9},
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
    background-color: #ffffff !important;
}

div[data-testid="stMainBlockContainer"] {
    max-width: 1200px;
    padding: 1.5rem 2rem 4rem;
}

/* Fonts */
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
label { font-family: 'Inter', sans-serif !important; }

::-webkit-scrollbar       { width: 4px; }
::-webkit-scrollbar-track { background: #ffffff; }
::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 2px; }

/* ── Phone mockup ── */
.phone-mockup {
    width: 280px;
    background: #000;
    border-radius: 28px;
    padding: 10px 8px;
    box-shadow: 0 24px 80px rgba(0,0,0,.12), 0 0 0 1px rgba(0,0,0,.08);
    transition: transform .3s ease;
}
.phone-mockup:hover { transform: scale(1.02); }
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
    width: 56px; height: 56px;
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
    border-width: 10px 0 10px 16px;
    border-color: transparent transparent transparent #fff;
    margin-left: 3px;
}
.hero-slide {
    position: absolute;
    top: 0; left: 0;
    width: 100%; height: 100%;
    object-fit: cover;
    opacity: 0;
    animation: heroSlide 12s ease-in-out infinite;
}
.hero-slide:nth-child(1) { animation-delay: 0s; }
.hero-slide:nth-child(2) { animation-delay: 3s; }
.hero-slide:nth-child(3) { animation-delay: 6s; }
.hero-slide:nth-child(4) { animation-delay: 9s; }

@keyframes heroSlide {
  0%    { opacity: 0; }
  3%    { opacity: 1; }
  25%   { opacity: 1; }
  28%   { opacity: 0; }
  100%  { opacity: 0; }
}

/* ── Logo ── */
.swx-logo {
    font-family: 'Montserrat', sans-serif;
    font-size: 1.5rem; font-weight: 900;
    color: #fd4816; padding: 6px 0;
}
.top-rule { border: none; border-top: 1px solid #e5e5e5; margin: .6rem 0 0; }

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
    color: #111111; margin: 0 0 18px;
}
.hero-title .a { color: #fd4816; }
.hero-sub {
    font-family: 'Inter', sans-serif;
    font-size: 15px; color: #666666; line-height: 1.7;
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
    font-size: 11px; color: #999999;
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
    box-shadow: 0 0 20px rgba(253,72,22,.1);
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
    border: none; border-top: 1px solid #e5e5e5;
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
    color: #111111; margin-bottom: 6px;
}
.s-sub {
    font-family: 'Inter', sans-serif;
    font-size: 13px; color: #666666; margin-bottom: 1.6rem;
}

/* ── Feature cards ── */
.feat-row {
    display: flex;
    gap: 16px;
    align-items: stretch;
}
.feat-card {
    background: #f7f7f8;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 1.3rem 1.2rem;
    flex: 1 1 0;
    transition: border-color .25s, transform .25s, box-shadow .25s;
}
.feat-card:hover { border-color: #d0d0d0; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(0,0,0,.08); }
.feat-icon {
    font-size: 1.6rem;
    margin-bottom: 10px;
}
.feat-title {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700; font-size: 14px;
    color: #1a1a1a; margin-bottom: 6px;
}
.feat-desc {
    font-family: 'Inter', sans-serif;
    font-size: 12px; color: #666666; line-height: 1.6;
}

/* ── Video cards ── */
.vid-meta {
    padding: 8px 2px 0;
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}
.vid-drug {
    font-family: 'Montserrat', sans-serif;
    font-weight: 700; font-size: 13px; color: #333333;
}
.vid-comp {
    font-family: 'Inter', sans-serif;
    font-size: 11px; color: #777777;
}
.t-badge {
    display: inline-block; padding: 2px 9px;
    border-radius: 20px; font-size: 11px; font-weight: 600;
    font-family: 'Montserrat', sans-serif;
}

.pdf-badge {
    font-family: 'Inter', sans-serif;
    font-size: 10px; font-weight: 500;
    color: #999999; background: #f0f0f0;
    border-radius: 12px; padding: 2px 8px;
    margin-left: auto;
    white-space: nowrap;
}

/* ── PDF → Video demo card ── */
.demo-transform {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.demo-pdf-side {
    flex-shrink: 0;
}
.demo-pdf-img {
    width: 80px; height: 100px;
    object-fit: cover; object-position: top;
    border: 1px solid #e5e5e5;
    border-radius: 4px;
}
.demo-arrow-small {
    font-size: 1.2rem; color: #fd4816;
    font-weight: 700;
}
.demo-pages {
    font-family: 'Inter', sans-serif;
    font-size: 10px; color: #999999;
    margin-top: 3px;
}

/* ── Form ── */
.form-label {
    font-family: 'Montserrat', sans-serif;
    font-size: 10px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: #fd4816; margin-bottom: 8px; margin-top: 4px;
}
div[data-baseweb="select"] > div {
    background: #f7f7f8 !important; border-color: #e5e5e5 !important; color: #333333 !important;
}
div[data-baseweb="select"] svg { fill: #999999 !important; }
textarea { background: #f7f7f8 !important; border-color: #e5e5e5 !important; color: #444444 !important; }
div[data-testid="stFileUploader"] > div {
    background: #f7f7f8 !important; border: 1px dashed #e5e5e5 !important; border-radius: 8px !important;
}
div[data-testid="stFileUploader"] p { color: #999999 !important; }
.stRadio > div { gap: 1rem !important; }
.stRadio label p { color: #444444 !important; font-size: 13px !important; }
.stCheckbox label p { color: #444444 !important; }

/* ── Buttons ── */
div[data-testid="stButton"] > button[kind="primary"] {
    background: linear-gradient(135deg, #fd4816 0%, #d93d0f 100%) !important;
    color: #fff !important; border: none !important;
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 700 !important; font-size: 15px !important;
    padding: 14px 32px !important; border-radius: 8px !important;
    box-shadow: 0 4px 20px rgba(253,72,22,.2) !important;
    transition: opacity .2s, box-shadow .2s !important;
}
div[data-testid="stButton"] > button[kind="primary"]:hover   { opacity: .88 !important; }
div[data-testid="stButton"] > button[kind="primary"]:disabled { opacity: .3 !important; }

div[data-testid="stDownloadButton"] > button {
    background: transparent !important; color: #fd4816 !important;
    border: 1px solid #fd4816 !important; border-radius: 8px !important;
    font-family: 'Montserrat', sans-serif !important; font-weight: 600 !important;
    width: 100% !important;
}

div[data-testid="stButton"] > button[kind="secondary"] {
    background: transparent !important; color: #fd4816 !important;
    border: 1px solid rgba(253,72,22,.4) !important; border-radius: 8px !important;
    font-family: 'Montserrat', sans-serif !important; font-weight: 600 !important;
    transition: all .2s !important;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
    border-color: #fd4816 !important;
    background: rgba(253,72,22,.08) !important;
}

/* ── Progress ── */
div[data-testid="stProgress"] > div > div { background: #fd4816 !important; }
div[data-testid="stProgress"] > div       { background: #e8e8e8 !important; }

.p-step         { font-family:'Inter',sans-serif; font-size:13px; padding:4px 0; }
.p-step.waiting { color:#d0d0d0; }
.p-step.active  { color:#fd4816; animation: stepPulse 1.8s ease-in-out infinite; }
.p-step.done    { color:#16a34a; }

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
    background: #f7f7f8;
    border: 1px solid #e8e8e8;
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
    color: #999999;
}
@keyframes skeletonPulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* ── Video cards ── */
video { border-radius: 10px; }

/* ── Alerts ── */
div[data-testid="stAlert"] { border-radius: 8px !important; }

/* ── Expander ── */
div[data-testid="stExpander"] {
    background: #f7f7f8 !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 10px !important;
}
div[data-testid="stExpander"] summary {
    font-family: 'Montserrat', sans-serif !important;
    font-weight: 600 !important;
    color: #222222 !important;
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
    st.image(str(LOGO_PATH), width=180)
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
        Turn any drug PDF into a narrated video reel in under 5 minutes —
        with every claim verified against the source. Add a gamified quiz that tests
        understanding, ranks your field team, and gives you learning data at scale.
      </p>
      <a href="#try-it" class="hero-cta">Try it yourself <span class="arrow">&darr;</span></a>
      <div class="hero-pills">
        <span class="pill">AI-Narrated Reels</span>
        <span class="pill">Gamified Quizzes</span>
        <span class="pill">Team Leaderboard</span>
        <span class="pill">Learning Analytics</span>
        <span class="pill">Under 5 Minutes</span>
        <span class="pill">Source-Verified Content</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

with hero_right:
    slide_dir = BASE_DIR / "assets"
    slide_files = [slide_dir / f"slide_{i}.jpg" for i in range(1, 5)]
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
    ("🎬", "Bite-Sized Reels",
     "60-second videos tailored to each role — not 40-page PDFs."),
    ("🧠", "Knowledge Checks",
     "Quick questions that test real understanding, not recall."),
    ("🏆", "Streaks & Gamification",
     "Daily streaks and instant feedback keep your team hooked."),
    ("📊", "Leaderboards",
     "Friendly competition across regions, teams, and roles."),
    ("💊", "Sales-Linked Insights",
     "Tie leaderboard scores to primary sales data directly."),
]

cards_html = '<div class="feat-row">' + "".join(
    f'<div class="feat-card"><div class="feat-icon">{ic}</div>'
    f'<div class="feat-title">{t}</div><div class="feat-desc">{d}</div></div>'
    for ic, t, d in FEATURES
) + '</div>'
st.markdown(cards_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SAMPLE REELS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<hr class="section-rule" id="demo-reels">', unsafe_allow_html=True)
st.markdown('<div class="s-eyebrow">See it in action</div>', unsafe_allow_html=True)
st.markdown('<div class="s-title">PDF in, video reel out</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="s-sub">Each reel generated from a single drug PDF — fully automated, zero hallucination</div>',
    unsafe_allow_html=True,
)

for row_start in range(0, len(DEMO_VIDEOS), 3):
    row_demos = DEMO_VIDEOS[row_start:row_start + 3]
    # 3 content cols with spacer cols between: [content, gap, content, gap, content]
    all_cols = st.columns([1, 0.4, 1, 0.4, 1], gap="small")
    demo_cols = [all_cols[0], all_cols[2], all_cols[4]]
    for i, demo in enumerate(row_demos):
        video_path = DEMOS_DIR / demo["file"]
        thumb_path = BASE_DIR / demo.get("pdf_thumb", "")
        if not video_path.exists():
            continue
        topic_color = TOPIC_COLORS.get(demo["topic"], "#fd4816")
        with demo_cols[i]:
            st.markdown(f"""
            <div style="margin-bottom:8px;">
              <span class="vid-drug" style="font-size:14px;">{demo["drug"]}</span>
              <span class="t-badge" style="background:{topic_color}12;color:{topic_color};border:1px solid {topic_color}33;margin-left:6px;font-size:10px;">{demo["topic"]}</span>
            </div>
            """, unsafe_allow_html=True)
            if thumb_path.exists():
                st.markdown(f"""
                <div class="demo-transform">
                  <div class="demo-pdf-side">
                    <img src="data:image/png;base64,{_img_b64(thumb_path)}" class="demo-pdf-img">
                    <div class="demo-pages">{demo.get("pages", "?")}‑page PDF</div>
                  </div>
                  <div class="demo-arrow-small">→</div>
                </div>
                """, unsafe_allow_html=True)
            st.video(str(video_path))
            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# GENERATE YOUR OWN
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<hr class="section-rule" id="try-it">', unsafe_allow_html=True)
st.markdown('<div class="s-eyebrow">Try it yourself</div>', unsafe_allow_html=True)
st.markdown('<div class="s-title">Generate a reel from any drug PDF</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="s-sub">Upload any drug PDF — your reel is ready in under 5 minutes</div>',
    unsafe_allow_html=True,
)

if "generating" not in st.session_state:
    st.session_state.generating = False
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None

# Safety valve: if generation was running but the process was killed (e.g. OOM),
# the flag stays stuck. Reset it so the app doesn't crash-loop.
if st.session_state.generating:
    gen_start = st.session_state.get("gen_start_time", 0)
    if time.time() - gen_start > 600:  # 10 min max — pipeline should never take this long
        st.session_state.generating = False

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
    st.markdown('<div class="form-label">② Focus (optional)</div>', unsafe_allow_html=True)
    guidance = st.text_area(
        "focus", label_visibility="collapsed",
        placeholder="e.g. Emphasise pain relief for elderly patients",
        height=80,
        disabled=is_generating,
    )
    st.markdown("<div style='height:.4rem'></div>", unsafe_allow_html=True)
    st.markdown('<div class="form-label">③ Company Logo (optional)</div>', unsafe_allow_html=True)
    company_logo_path = ""
    if PRESET_LOGO_PATH and PRESET_LOGO_PATH.exists():
        # Auto-loaded from URL param — show preview, hide uploader
        st.image(str(PRESET_LOGO_PATH), width=140)
        if PRESET_COMPANY_NAME:
            st.caption(f"Logo for {PRESET_COMPANY_NAME}")
        company_logo_path = str(PRESET_LOGO_PATH)
    else:
        company_logo_file = st.file_uploader(
            "logo", type=["png", "jpg", "jpeg"],
            label_visibility="collapsed", disabled=is_generating,
        )
        if company_logo_file:
            logo_save = BASE_DIR / "output" / f"company_logo_{company_logo_file.name}"
            logo_save.parent.mkdir(parents=True, exist_ok=True)
            logo_save.write_bytes(company_logo_file.getbuffer())
            company_logo_path = str(logo_save)

with right:
    st.markdown('<div class="form-label">④ Configure</div>', unsafe_allow_html=True)

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
        "Gaurav — Professional, Calm":    "gaurav",
        "Suyash — Calm Explainer":        "suyash",
        "Sridhar — Natural, Professional": "sridhar",
        "Ruhaan — Clear, Cheerful":       "ruhaan",
        "Ishaan — Warm E-Learning":       "ishaan",
    }
    voice = voice_map[st.selectbox("Voice", list(voice_map.keys()), disabled=is_generating)]
    language_label = st.radio("Language", ["English", "Hindi"], horizontal=True, disabled=is_generating)
    language = "hi" if language_label == "Hindi" else "en"
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
    st.session_state.gen_start_time = time.time()
    st.session_state.pipeline_config = dict(
        pdf_path=pdf_path,
        profile=profile,
        topic=topic,
        voice=voice,
        tts="elevenlabs",
        mode=mode,
        guidance=guidance,
        language=language,
        company_logo_path=company_logo_path,
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
        <div style="background:#f7f7f8; border:1px solid #e5e5e5; border-left:3px solid #fd4816;
                    border-radius:10px; padding:1.1rem 1.3rem; margin-bottom:.3rem;">
          <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:.5rem;">
            <div>
              <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:15px; color:#111111; margin-bottom:5px;">
                <span class="spin-dot">⏳</span>&nbsp; {label}
              </div>
              <div style="font-family:'Inter',sans-serif; font-size:13px; color:#777777; max-width:460px;">
                {desc}
              </div>
            </div>
            <div style="text-align:right; flex-shrink:0;">
              <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:1.1rem; color:#fd4816;">{pct_i}%</div>
              <div style="font-family:'Inter',sans-serif; font-size:11px; color:#aaaaaa; margin-top:2px;">{_ft(elapsed)} elapsed</div>
              <div style="font-family:'Inter',sans-serif; font-size:11px; color:#aaaaaa; margin-top:1px;">~{_ft(remaining)} remaining</div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    def on_progress(step, message, pct):
        if cur_step[0] and cur_step[0] != step and cur_step[0] in step_ui:
            el = time.time() - step_start[0]
            lbl = STEP_META.get(cur_step[0], (cur_step[0],))[0]
            step_ui[cur_step[0]].markdown(
                f'<div class="p-step done">✓ {lbl} <span style="color:#cccccc;font-size:11px">({_ft(el)})</span></div>',
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
            f'<div class="p-step done">✓ {lbl} <span style="color:#cccccc;font-size:11px">({_ft(el)})</span></div>',
            unsafe_allow_html=True,
        )
    progress_bar.progress(1.0)
    total = time.time() - run_start

    status_box.markdown(f"""
    <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-left:3px solid #16a34a;
                border-radius:10px; padding:1.1rem 1.3rem; margin-bottom:.3rem;">
      <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:.5rem;">
        <div>
          <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:15px; color:#16a34a; margin-bottom:3px;">
            ✓ &nbsp;Your reel is ready
          </div>
          <div style="font-family:'Inter',sans-serif; font-size:13px; color:#999999;">
            Generated in {_ft(total)}
          </div>
        </div>
        <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:1.1rem; color:#16a34a;">100%</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.session_state.generating = False
    st.session_state.pipeline_result = result
    st.rerun()

elif st.session_state.pipeline_result is not None:
    result = st.session_state.pipeline_result
    if result.get("error"):
        st.error(f"Something went wrong: {result['error']}")
        if st.button("Try Again", use_container_width=True):
            st.session_state.pipeline_result = None
            st.rerun()
    elif result.get("video_path") and os.path.exists(result["video_path"]):
        st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
        _pad_l, out_left, _gap, out_right, _pad_r = st.columns([0.5, 1, 0.3, 1.2, 0.5], gap="small")
        with out_left:
            st.video(result["video_path"])
            st.download_button(
                "⬇  Download MP4",
                data=Path(result["video_path"]).read_bytes(),
                file_name=Path(result["video_path"]).name,
                mime="video/mp4",
            )
        with out_right:
            st.markdown("""
            <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-left:3px solid #16a34a;
                        border-radius:10px; padding:1.1rem 1.3rem;">
              <div style="font-family:'Montserrat',sans-serif; font-weight:700; font-size:15px; color:#16a34a; margin-bottom:3px;">
                ✓ &nbsp;Your reel is ready
              </div>
              <div style="font-family:'Inter',sans-serif; font-size:13px; color:#999999;">
                Download this reel before generating another — it will be replaced.
              </div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
            if st.button("Generate Another Reel", use_container_width=True):
                st.session_state.pipeline_result = None
                st.rerun()
    else:
        st.error("Generation completed but no video was produced.")
        if st.button("Try Again", use_container_width=True):
            st.session_state.pipeline_result = None
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<hr style="border:none; border-top:1px solid #e5e5e5; margin:3rem 0 0;">
<div style="text-align:center; padding:1.5rem 0 1rem; font-size:11px; color:#aaaaaa;
            font-family:'Montserrat',sans-serif; letter-spacing:.5px;">
  SwishX © 2026
</div>
""", unsafe_allow_html=True)
