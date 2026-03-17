"""
Autonomous Video Reel Agent — Duolingo for Pharma

Generates educational video reels from drug PDF monographs using Claude's
tool_use API. The agent orchestrates the full pipeline with adaptive
self-correction: tracks production state, rewrites low-quality scripts,
combines thin topics, and switches frame strategies mid-run.

Uses the raw Anthropic API (tool_use) — no MCP server, no SDK subprocess,
no transport layer. This is the most robust approach for long-running tools
(Claude API calls, ElevenLabs TTS, Gemini image gen, FFmpeg) that can take
10s-5min each.

Usage:
  python video_agent.py "<pdf_path>" [--profile doctor|stockist|retailer|all] [--topic intro|mechanism|...]
  python video_agent.py "<pdf_path>" --all-topics
  python video_agent.py  (interactive — agent asks what to do)

Required env vars:
  ANTHROPIC_API_KEY   — Claude API key
  GOOGLE_API_KEY      — Google API key (for Nano Banana 2 frame generation)
  ELEVENLABS_API_KEY  — ElevenLabs API key (for voiceover)
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
from config_loader import load_models, load_agent_system_prompt

# --- Pipeline imports ---
from step1_extract import extract_pdf as _extract_pdf
from step1b_analyze_content import analyze_content as _analyze_content
from step2_generate_script import (
    generate_script as _generate_script,
    filter_quiz_scenes,
    get_profile_context,
    get_reel_topic_prompt,
    SYSTEM_PROMPT as SCRIPT_SYSTEM_PROMPT,
)
from validate_script import validate_script as _validate_script
from step3_generate_frames import (
    TEMPLATE_RENDERERS,
    render_leaderboard,
    render_content_fallback,
    generate_frame_ai,
    build_content_prompt,
)
from step4_stitch_video import create_video
from burn_subtitles import (
    enrich_drug_names,
    build_subtitle_events,
    build_box_ranges,
    generate_overlay_video,
    burn_onto_video,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODELS = load_models()
AGENT_CFG = MODELS["agent"]

BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
DRUG_PDFS_DIR = BASE_DIR / "pdfs"

SYSTEM_PROMPT = load_agent_system_prompt()


# ═══════════════════════════════════════════════════════════════════
#  PRODUCTION STATE
# ═══════════════════════════════════════════════════════════════════

class ProductionState:
    def __init__(self):
        self.reels_completed = []
        self.reels_failed = []
        self.reels_skipped = []
        self.ai_frame_failures = 0
        self.ai_frame_attempts = 0
        self.total_validation_retries = 0
        self.frame_mode = "ai_with_fallback"
        self.notes = []

    def record_frame_result(self, scenes: list, error_count: int):
        content_count = sum(1 for s in scenes if s.get("scene_type", "content") == "content")
        self.ai_frame_attempts += max(content_count, 1)
        self.ai_frame_failures += error_count

    @property
    def ai_failure_rate(self) -> float:
        if self.ai_frame_attempts == 0:
            return 0.0
        return self.ai_frame_failures / self.ai_frame_attempts

    def to_dict(self) -> dict:
        return {
            "reels_completed": self.reels_completed,
            "reels_failed": self.reels_failed,
            "reels_skipped": self.reels_skipped,
            "ai_frame_failures": self.ai_frame_failures,
            "ai_frame_attempts": self.ai_frame_attempts,
            "ai_failure_rate": round(self.ai_failure_rate, 2),
            "frame_mode": self.frame_mode,
            "total_validation_retries": self.total_validation_retries,
            "notes": self.notes,
        }


STATE = ProductionState()
AGENT_MODE = "demo"  # Set from CLI: "demo" (full) or "production" (content only)


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _parse_json_robust(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        start = text.index("{")
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])
    except (ValueError, json.JSONDecodeError):
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
#  TOOL FUNCTIONS
# ═══════════════════════════════════════════════════════════════════

def tool_list_available_pdfs(args: dict) -> dict:
    pdfs = []
    if DRUG_PDFS_DIR.exists():
        pdfs = [f.name for f in DRUG_PDFS_DIR.glob("*.pdf")]
    return {"pdf_dir": str(DRUG_PDFS_DIR), "pdfs": pdfs}


def tool_extract_pdf(args: dict) -> dict:
    _ensure_output_dir()
    pdf_path = args["pdf_path"]
    drug_name = Path(pdf_path).stem
    md_path = OUTPUT_DIR / f"{drug_name}.md"
    txt_path = OUTPUT_DIR / f"{drug_name}.txt"

    if md_path.exists():
        text = md_path.read_text()
        return {"status": "success", "method": "cached", "output_path": str(md_path),
                "text_preview": text[:500], "text_length": len(text)}

    text, method = _extract_pdf(pdf_path)
    md_path.write_text(text)
    txt_path.write_text(text)
    return {"status": "success", "method": method, "output_path": str(md_path),
            "text_preview": text[:500], "text_length": len(text)}


def tool_analyze_content(args: dict) -> dict:
    text_path = args["text_path"]
    drug_name = Path(text_path).stem
    analysis_path = OUTPUT_DIR / f"{drug_name}_analysis.json"

    if analysis_path.exists():
        analysis = json.loads(analysis_path.read_text())
        return {"status": "success", "cached": True, "analysis_path": str(analysis_path),
                "topics": analysis.get("recommended_reel_order", []),
                "topic_details": analysis.get("available_topics", []),
                "analysis": analysis}

    content = Path(text_path).read_text()
    analysis = _analyze_content(content)
    analysis_path.write_text(json.dumps(analysis, indent=2))
    return {"status": "success", "cached": False, "analysis_path": str(analysis_path),
            "topics": analysis.get("recommended_reel_order", []),
            "topic_details": analysis.get("available_topics", []),
            "analysis": analysis}


def tool_generate_script(args: dict) -> dict:
    text_path = args["text_path"]
    profile = args["profile"]
    topic = args["topic"]
    analysis_path = args.get("analysis_path", "")
    avoid_claims_raw = args.get("avoid_claims", "")

    drug_name = Path(text_path).stem
    script_path = OUTPUT_DIR / f"{drug_name}_{profile}_{topic}_script.json"

    if script_path.exists():
        script = json.loads(script_path.read_text())
        return {"status": "success", "cached": True, "script_path": str(script_path),
                "scene_count": len(script.get("scenes", [])),
                "estimated_duration": script.get("estimated_duration_seconds"),
                "total_words": sum(len(s.get("narration", "").split()) for s in script.get("scenes", []))}

    pdf_text = Path(text_path).read_text()

    if avoid_claims_raw:
        try:
            claims = json.loads(avoid_claims_raw) if isinstance(avoid_claims_raw, str) else avoid_claims_raw
        except (json.JSONDecodeError, TypeError):
            claims = [c.strip() for c in str(avoid_claims_raw).split(",") if c.strip()]
        if claims:
            pdf_text += "\n\nIMPORTANT — Do NOT include these claims (they are not in the source):\n"
            for claim in claims:
                pdf_text += f"- {claim}\n"

    analysis = None
    if analysis_path and Path(analysis_path).exists():
        analysis = json.loads(Path(analysis_path).read_text())

    guidance = args.get("guidance", "")
    script = _generate_script(pdf_text, profile, topic, analysis, guidance=guidance)

    if AGENT_MODE == "production":
        full_path = script_path.with_name(script_path.stem + "_full.json")
        full_path.write_text(json.dumps(script, indent=2))
        script = filter_quiz_scenes(script)

    script_path.write_text(json.dumps(script, indent=2))

    total_words = sum(len(s.get("narration", "").split()) for s in script.get("scenes", []))
    return {"status": "success", "cached": False, "script_path": str(script_path),
            "scene_count": len(script.get("scenes", [])),
            "estimated_duration": script.get("estimated_duration_seconds"),
            "total_words": total_words, "product_name": script.get("product_name", "")}


def tool_rewrite_script(args: dict) -> dict:
    script_path = args["script_path"]
    source_text_path = args["source_text_path"]
    feedback = args["feedback"]

    old_script = json.loads(Path(script_path).read_text())
    source_text = Path(source_text_path).read_text()

    client = Anthropic()
    rewrite_prompt = f"""Here is the source document:

<source>
{source_text}
</source>

Here is the current video script:

<current_script>
{json.dumps(old_script, indent=2)}
</current_script>

FEEDBACK — rewrite the script based on this feedback:
{feedback}

Rules:
- Keep the EXACT same JSON structure as the current script.
- ONLY use facts from the source document.
- Apply the feedback while maintaining medical accuracy.
- Keep all scene types (content, quiz, quiz_answer, score, cta, leaderboard) unless mode is production.
- Include an image_prompt for every content scene.

Return ONLY valid JSON, no markdown fences."""

    response = client.messages.create(
        model=MODELS["script_generation"]["model"],
        max_tokens=MODELS["script_generation"]["max_tokens"],
        system=SCRIPT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": rewrite_prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    new_script = _parse_json_robust(text)
    if new_script is None:
        return {"status": "error", "error": "Failed to parse rewritten script JSON"}

    if AGENT_MODE == "production":
        new_script = filter_quiz_scenes(new_script)

    Path(script_path).write_text(json.dumps(new_script, indent=2))

    old_words = sum(len(s.get("narration", "").split()) for s in old_script.get("scenes", []))
    new_words = sum(len(s.get("narration", "").split()) for s in new_script.get("scenes", []))
    return {"status": "success", "script_path": script_path,
            "scene_count": len(new_script.get("scenes", [])),
            "word_count": new_words, "previous_word_count": old_words,
            "word_count_change": new_words - old_words, "feedback_applied": feedback}


def tool_generate_combined_script(args: dict) -> dict:
    text_path = args["text_path"]
    profile = args["profile"]
    combined_title = args["combined_title"]
    analysis_path = args.get("analysis_path", "")

    topics_raw = args["topics"]
    if isinstance(topics_raw, list):
        topics = topics_raw
    else:
        try:
            topics = json.loads(topics_raw)
        except (json.JSONDecodeError, TypeError):
            topics = [t.strip() for t in str(topics_raw).split(",") if t.strip()]

    pdf_text = Path(text_path).read_text()
    analysis = None
    if analysis_path and Path(analysis_path).exists():
        analysis = json.loads(Path(analysis_path).read_text())

    profile_context = get_profile_context(profile)
    topic_descriptions = [get_reel_topic_prompt(t, analysis).strip() for t in topics]

    combined_topic_prompt = f"""
REEL TOPIC: {combined_title}
This reel COMBINES the following topics into a single cohesive video:

{chr(10).join(topic_descriptions)}

Duration target: 90-120 seconds (~225-300 words)
Scenes: 5-7 content scenes + quiz + gamification

IMPORTANT: Weave these topics together naturally. Don't just stitch them sequentially.
"""

    from config_loader import load_script_user_template
    user_prompt = load_script_user_template().format(
        pdf_content=pdf_text, profile_context=profile_context,
        topic_prompt=combined_topic_prompt,
    )

    client = Anthropic()
    response = client.messages.create(
        model=MODELS["script_generation"]["model"],
        max_tokens=MODELS["script_generation"]["max_tokens"],
        system=SCRIPT_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    script = _parse_json_robust(text)
    if script is None:
        return {"status": "error", "error": "Failed to parse combined script JSON"}

    if AGENT_MODE == "production":
        script = filter_quiz_scenes(script)

    drug_name = Path(text_path).stem
    out_path = OUTPUT_DIR / f"{drug_name}_{profile}_{'_'.join(topics)}_script.json"
    out_path.write_text(json.dumps(script, indent=2))

    total_words = sum(len(s.get("narration", "").split()) for s in script.get("scenes", []))
    return {"status": "success", "script_path": str(out_path),
            "combined_topics": topics, "combined_title": combined_title,
            "scene_count": len(script.get("scenes", [])), "word_count": total_words,
            "estimated_duration": sum(s.get("duration_seconds", 0) for s in script.get("scenes", []))}


def tool_validate_script(args: dict) -> dict:
    script_path = args["script_path"]
    source_path = args["source_path"]
    script_stem = Path(script_path).stem
    validation_path = OUTPUT_DIR / f"{script_stem}_validation.json"

    validation = _validate_script(script_path, source_path)
    validation_path.write_text(json.dumps(validation, indent=2))
    STATE.total_validation_retries += 1

    unsupported_claims = [
        c["claim"] for s in validation.get("scenes", [])
        for c in s.get("claims", []) if c.get("status") == "unsupported"
    ]
    return {"status": "success", "validation_path": str(validation_path),
            "overall_score": validation.get("overall_score", 0),
            "total_claims": validation.get("total_claims", 0),
            "supported": validation.get("supported", 0),
            "unsupported": validation.get("unsupported", 0),
            "unsupported_claims": unsupported_claims,
            "flags": validation.get("flags", [])}


def tool_generate_frames(args: dict) -> dict:
    script_path = args["script_path"]
    mode = args.get("mode", "auto")
    script = json.loads(Path(script_path).read_text())
    script_stem = Path(script_path).stem
    frames_dir = OUTPUT_DIR / f"{script_stem}_frames"
    manifest_path = OUTPUT_DIR / f"{script_stem}_frames.json"

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        errors = manifest.get("errors", [])
        return {"status": "success", "cached": True, "manifest_path": str(manifest_path),
                "total_frames": len(manifest.get("frames", [])),
                "errors": errors, "error_count": len(errors), "mode_used": "cached"}

    frames_dir.mkdir(parents=True, exist_ok=True)
    effective_mode = STATE.frame_mode if mode == "auto" else mode
    use_ai = effective_mode != "pillow_only"

    client = None
    if use_ai:
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            from google import genai
            client = genai.Client(api_key=api_key)
        else:
            use_ai = False
            effective_mode = "pillow_only (GOOGLE_API_KEY missing)"

    from concurrent.futures import ThreadPoolExecutor, as_completed

    frame_paths, errors = [], []
    results = {}  # scene_num -> (path, error_info)

    # Template scenes (Pillow, instant)
    for scene in script["scenes"]:
        scene_type = scene.get("scene_type", "content")
        scene_num = scene["scene_number"]
        filename = str(frames_dir / f"scene_{scene_num:02d}_{scene_type}.png")

        if scene_type == "content":
            continue  # handled below in parallel
        elif scene_type == "leaderboard":
            results[scene_num] = (render_leaderboard(scene, filename), None)
        elif scene_type in TEMPLATE_RENDERERS:
            results[scene_num] = (TEMPLATE_RENDERERS[scene_type](scene, filename), None)
        else:
            results[scene_num] = (render_content_fallback(scene, filename), None)

    # AI content scenes — generate in parallel
    ai_scenes = [(s, str(frames_dir / f"scene_{s['scene_number']:02d}_content.png"))
                 for s in script["scenes"] if s.get("scene_type", "content") == "content"]

    def _gen_one(scene, filename):
        sn = scene["scene_number"]
        if use_ai and client:
            prompt = build_content_prompt(scene)
            path = generate_frame_ai(client, prompt, filename)
            if path:
                return sn, path, None
        path = render_content_fallback(scene, filename)
        err = {"scene": sn, "error": "AI failed, Pillow fallback"} if use_ai else None
        return sn, path, err

    if ai_scenes:
        max_workers = min(len(ai_scenes), 4)
        print(f"  Generating {len(ai_scenes)} AI frames in parallel ({max_workers} workers)...")
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_gen_one, s, f): s for s, f in ai_scenes}
            for future in as_completed(futures):
                try:
                    sn, path, err = future.result()
                    results[sn] = (path, err)
                except Exception as e:
                    scene = futures[future]
                    sn = scene["scene_number"]
                    fn = str(frames_dir / f"scene_{sn:02d}_content.png")
                    results[sn] = (render_content_fallback(scene, fn),
                                   {"scene": sn, "error": str(e)})

    # Assemble in scene order
    for scene in script["scenes"]:
        scene_num = scene["scene_number"]
        scene_type = scene.get("scene_type", "content")
        path, err = results.get(scene_num, (None, None))
        if err:
            errors.append(err)
        if path:
            frame_paths.append({"scene": scene_num, "scene_type": scene_type,
                                "path": path, "duration": scene["duration_seconds"]})

    manifest = {"product_name": script.get("product_name", ""),
                "script_path": script_path, "frames": frame_paths}
    if errors:
        manifest["errors"] = errors
    manifest_path.write_text(json.dumps(manifest, indent=2))
    STATE.record_frame_result(script["scenes"], len(errors))

    return {"status": "success", "cached": False, "manifest_path": str(manifest_path),
            "total_frames": len(frame_paths), "errors": errors, "error_count": len(errors),
            "mode_used": effective_mode, "ai_failure_rate": round(STATE.ai_failure_rate, 2)}


def tool_generate_voiceover(args: dict) -> dict:
    script_path = args["script_path"]
    voice = args.get("voice", "gaurav")
    tts = args.get("tts", "elevenlabs")
    script_stem = Path(script_path).stem
    audio_path = OUTPUT_DIR / f"{script_stem}_{voice}.mp3"
    durations_path = OUTPUT_DIR / f"{script_stem}_durations.json"

    if audio_path.exists() and durations_path.exists():
        durations = json.loads(durations_path.read_text())
        total = sum(d.get("duration", 0) for d in durations if isinstance(d, dict))
        return {"status": "success", "cached": True, "audio_path": str(audio_path),
                "durations_path": str(durations_path), "total_duration": round(total, 1),
                "audio_size_mb": round(audio_path.stat().st_size / (1024 * 1024), 2)}

    if tts == "gemini":
        from step3b_generate_voiceover import generate_voiceover as _gen_vo
    else:
        from step3_generate_voiceover import generate_voiceover as _gen_vo

    result_path = _gen_vo(script_path, voice)
    durations = json.loads(durations_path.read_text())
    total = sum(d.get("duration", 0) for d in durations if isinstance(d, dict))
    return {"status": "success", "cached": False, "audio_path": str(result_path),
            "durations_path": str(durations_path), "total_duration": round(total, 1),
            "audio_size_mb": round(audio_path.stat().st_size / (1024 * 1024), 2)}


def tool_stitch_video(args: dict) -> dict:
    suffix = args.get("suffix", "_v1")
    script_stem = Path(args["script_path"]).stem
    expected_path = OUTPUT_DIR / f"{script_stem}{suffix}_video.mp4"

    if expected_path.exists():
        size_mb = expected_path.stat().st_size / (1024 * 1024)
        return {"status": "success", "cached": True, "video_path": str(expected_path),
                "video_size_mb": round(size_mb, 2)}

    result = create_video(
        args["frames_manifest"], audio_path=args["audio_path"],
        script_path=args["script_path"], durations_path=args["durations_path"],
        output_suffix=suffix,
    )

    if result is None or not expected_path.exists():
        return {"status": "error", "error": "Video stitching failed"}

    size_mb = expected_path.stat().st_size / (1024 * 1024)
    return {"status": "success", "cached": False, "video_path": str(expected_path),
            "video_size_mb": round(size_mb, 2)}


def tool_burn_subtitles(args: dict) -> dict:
    video_path = args["video_path"]
    script_path = args["script_path"]
    durations_path = args["durations_path"]
    base = Path(video_path).stem
    output_path = str(OUTPUT_DIR / f"{base}_subtitled.mp4")

    if Path(output_path).exists():
        size_mb = Path(output_path).stat().st_size / (1024 * 1024)
        return {"status": "success", "cached": True, "subtitled_video_path": output_path,
                "video_size_mb": round(size_mb, 2)}

    script = json.loads(Path(script_path).read_text())
    durations = json.loads(Path(durations_path).read_text())
    enrich_drug_names(script)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    video_duration = float(probe.stdout.strip())

    events = build_subtitle_events(script, durations)
    box_ranges = build_box_ranges(script, durations)

    overlay_fd, overlay_path = tempfile.mkstemp(suffix=".mov", prefix="subtitle_overlay_")
    os.close(overlay_fd)

    try:
        result = generate_overlay_video(events, video_duration, overlay_path, box_ranges)
        if not result:
            return {"status": "error", "error": "Failed to generate subtitle overlay"}
        result = burn_onto_video(video_path, overlay_path, output_path)
        if not result:
            return {"status": "error", "error": "Failed to burn subtitles"}
    finally:
        if os.path.exists(overlay_path):
            os.unlink(overlay_path)

    size_mb = Path(output_path).stat().st_size / (1024 * 1024)
    return {"status": "success", "cached": False, "subtitled_video_path": output_path,
            "video_size_mb": round(size_mb, 2)}


def tool_check_video(args: dict) -> dict:
    video_path = args["video_path"]
    if not os.path.exists(video_path):
        return {"valid": False, "error": "File does not exist"}
    size_mb = os.path.getsize(video_path) / (1024 * 1024)
    if size_mb < 0.1:
        return {"valid": False, "error": f"File too small ({size_mb:.2f} MB)"}
    if size_mb > 200:
        return {"valid": False, "error": f"File too large ({size_mb:.1f} MB)"}
    return {"valid": True, "size_mb": round(size_mb, 1)}


def tool_get_production_status(args: dict) -> dict:
    return STATE.to_dict()


def tool_update_strategy(args: dict) -> dict:
    changes = []
    frame_mode = args.get("frame_mode")
    note = args.get("note")
    if frame_mode and frame_mode != STATE.frame_mode:
        old = STATE.frame_mode
        STATE.frame_mode = frame_mode
        changes.append(f"frame_mode: {old} -> {frame_mode}")
    if note:
        STATE.notes.append(note)
        changes.append(f"note: {note}")
    return {"changes": changes, "current_state": STATE.to_dict()}


def tool_check_existing_outputs(args: dict) -> dict:
    drug = args["drug_name"]
    outputs = {}
    if not OUTPUT_DIR.exists():
        return {"drug": drug, "outputs": {}}
    for f in OUTPUT_DIR.iterdir():
        if f.name.startswith(drug) and f.is_file():
            key = f.suffix.lstrip(".")
            if key not in outputs:
                outputs[key] = []
            outputs[key].append({"name": f.name, "size_mb": round(f.stat().st_size / (1024 * 1024), 2)})
    return {"drug": drug, "outputs": outputs}


def tool_delete_cached_output(args: dict) -> dict:
    fp = Path(args["file_path"])
    if not str(fp).startswith(str(OUTPUT_DIR)):
        return {"error": "Can only delete files in the output directory"}
    deleted = []
    if fp.exists():
        fp.unlink()
        deleted.append(str(fp))
    if str(fp).endswith("_frames.json"):
        frames_dir = Path(str(fp).replace("_frames.json", "_frames"))
        if frames_dir.is_dir():
            import shutil
            shutil.rmtree(frames_dir)
            deleted.append(str(frames_dir))
    return {"deleted": deleted}


# ═══════════════════════════════════════════════════════════════════
#  TOOL DEFINITIONS for Claude tool_use API
# ═══════════════════════════════════════════════════════════════════

TOOLS = [
    {"name": "list_available_pdfs", "description": "List all drug PDFs available for video generation",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "extract_pdf", "description": "Step 1: Extract text from a drug PDF. Returns path to extracted text file.",
     "input_schema": {"type": "object", "properties": {"pdf_path": {"type": "string"}}, "required": ["pdf_path"]}},
    {"name": "analyze_content", "description": "Step 1b: Analyze extracted text for available topics with confidence levels.",
     "input_schema": {"type": "object", "properties": {"text_path": {"type": "string"}}, "required": ["text_path"]}},
    {"name": "generate_script", "description": "Step 2: Generate a video script using Claude. Pass avoid_claims as JSON array string to exclude hallucinated claims.",
     "input_schema": {"type": "object", "properties": {
         "text_path": {"type": "string"}, "profile": {"type": "string", "enum": ["sales_executive", "stockist", "retailer", "doctor", "all"]},
         "topic": {"type": "string", "enum": ["intro", "indications", "mechanism", "dosage_safety", "interactions", "side_effects"]},
         "analysis_path": {"type": "string", "description": "Path to analysis JSON (optional)"},
         "avoid_claims": {"type": "array", "items": {"type": "string"}, "description": "Claims to exclude from failed validation"},
         "guidance": {"type": "string", "description": "Optional creative direction to steer script tone/focus"},
     }, "required": ["text_path", "profile", "topic"]}},
    {"name": "rewrite_script", "description": "Rewrite a script based on natural language feedback. Overwrites in place.",
     "input_schema": {"type": "object", "properties": {
         "script_path": {"type": "string"}, "source_text_path": {"type": "string"},
         "feedback": {"type": "string"}, "profile": {"type": "string"},
     }, "required": ["script_path", "source_text_path", "feedback", "profile"]}},
    {"name": "generate_combined_script", "description": "Generate one reel combining multiple thin topics.",
     "input_schema": {"type": "object", "properties": {
         "text_path": {"type": "string"}, "profile": {"type": "string"},
         "topics": {"type": "array", "items": {"type": "string"}},
         "combined_title": {"type": "string"}, "analysis_path": {"type": "string"},
     }, "required": ["text_path", "profile", "topics", "combined_title"]}},
    {"name": "validate_script", "description": "Validate script accuracy against source PDF. Returns score 0-1.",
     "input_schema": {"type": "object", "properties": {
         "script_path": {"type": "string"}, "source_path": {"type": "string"},
     }, "required": ["script_path", "source_path"]}},
    {"name": "generate_frames", "description": "Step 3a: Generate visual frames (AI + Pillow fallback). Takes 2-3 min.",
     "input_schema": {"type": "object", "properties": {
         "script_path": {"type": "string"},
         "mode": {"type": "string", "enum": ["auto", "pillow_only"], "description": "auto respects current strategy"},
     }, "required": ["script_path"]}},
    {"name": "generate_voiceover", "description": "Step 3b: Generate per-scene voiceover audio.",
     "input_schema": {"type": "object", "properties": {
         "script_path": {"type": "string"}, "voice": {"type": "string"},
         "tts": {"type": "string", "enum": ["elevenlabs", "gemini"]},
     }, "required": ["script_path", "voice", "tts"]}},
    {"name": "stitch_video", "description": "Step 4: Stitch frames + audio into MP4 with logo and background music.",
     "input_schema": {"type": "object", "properties": {
         "frames_manifest": {"type": "string"}, "audio_path": {"type": "string"},
         "script_path": {"type": "string"}, "durations_path": {"type": "string"},
         "suffix": {"type": "string"},
     }, "required": ["frames_manifest", "audio_path", "script_path", "durations_path"]}},
    {"name": "burn_subtitles", "description": "Step 5: Burn phrase-based captions with teal drug highlights. ALWAYS run as final step.",
     "input_schema": {"type": "object", "properties": {
         "video_path": {"type": "string"}, "script_path": {"type": "string"},
         "durations_path": {"type": "string"},
     }, "required": ["video_path", "script_path", "durations_path"]}},
    {"name": "check_video", "description": "Verify a video file is valid.",
     "input_schema": {"type": "object", "properties": {"video_path": {"type": "string"}}, "required": ["video_path"]}},
    {"name": "get_production_status", "description": "Get production state: completed/failed reels, AI failure rate, strategy.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "update_strategy", "description": "Switch frame_mode or record a strategic note.",
     "input_schema": {"type": "object", "properties": {
         "frame_mode": {"type": "string", "enum": ["ai_with_fallback", "pillow_only"]},
         "note": {"type": "string"},
     }}},
    {"name": "check_existing_outputs", "description": "Check what outputs exist for a drug.",
     "input_schema": {"type": "object", "properties": {"drug_name": {"type": "string"}}, "required": ["drug_name"]}},
    {"name": "delete_cached_output", "description": "Delete a cached output file to force regeneration.",
     "input_schema": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]}},
]

TOOL_DISPATCH = {
    "list_available_pdfs": tool_list_available_pdfs,
    "extract_pdf": tool_extract_pdf,
    "analyze_content": tool_analyze_content,
    "generate_script": tool_generate_script,
    "rewrite_script": tool_rewrite_script,
    "generate_combined_script": tool_generate_combined_script,
    "validate_script": tool_validate_script,
    "generate_frames": tool_generate_frames,
    "generate_voiceover": tool_generate_voiceover,
    "stitch_video": tool_stitch_video,
    "burn_subtitles": tool_burn_subtitles,
    "check_video": tool_check_video,
    "get_production_status": tool_get_production_status,
    "update_strategy": tool_update_strategy,
    "check_existing_outputs": tool_check_existing_outputs,
    "delete_cached_output": tool_delete_cached_output,
}


# ═══════════════════════════════════════════════════════════════════
#  AGENT LOOP — raw Anthropic tool_use, no MCP, no SDK subprocess
# ═══════════════════════════════════════════════════════════════════

def run_agent(prompt: str, max_turns: int = 50):
    client = Anthropic()
    messages = [{"role": "user", "content": prompt}]

    start_time = time.time()
    iteration = 0

    while iteration < max_turns:
        iteration += 1

        try:
            response = client.messages.create(
                model=AGENT_CFG["model"],
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            print(f"\n  API error (iteration {iteration}): {e}")
            break

        assistant_content = response.content
        has_tool_use = any(block.type == "tool_use" for block in assistant_content)

        # Print agent text
        for block in assistant_content:
            if block.type == "text" and block.text.strip():
                print(f"\n  Agent: {block.text.strip()}\n")

        # Done if no tool calls
        if response.stop_reason == "end_turn" and not has_tool_use:
            break

        if has_tool_use:
            messages.append({"role": "assistant", "content": assistant_content})
            tool_results = []

            for block in assistant_content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input
                tool_id = block.id

                # Log tool call
                label = f"  [{iteration}] {tool_name}"
                if tool_name == "generate_script":
                    label += f" ({tool_input.get('topic', '?')})"
                elif tool_name == "validate_script":
                    label += " (checking accuracy)"
                elif tool_name == "generate_frames":
                    label += f" (mode={tool_input.get('mode', 'auto')})"
                elif tool_name == "generate_voiceover":
                    label += f" ({tool_input.get('tts', '?')}/{tool_input.get('voice', '?')})"
                elif tool_name == "rewrite_script":
                    fb = tool_input.get("feedback", "")
                    label += f" ({fb[:60]}{'...' if len(fb) > 60 else ''})"
                elif tool_name == "generate_combined_script":
                    label += f" ({'+'.join(tool_input.get('topics', []))})"
                elif tool_name == "stitch_video":
                    label += " (assembling)"
                elif tool_name == "burn_subtitles":
                    label += " (final step)"
                elif tool_name == "delete_cached_output":
                    label += f" ({os.path.basename(tool_input.get('file_path', ''))})"
                print(label)

                try:
                    func = TOOL_DISPATCH[tool_name]
                    result = func(tool_input)
                    result_json = json.dumps(result, default=str)

                    # Print key results
                    if tool_name == "extract_pdf":
                        print(f"    -> {result.get('method', '?')}, {result.get('text_length', 0)} chars")
                    elif tool_name == "analyze_content":
                        print(f"    -> topics: {result.get('topics', [])}")
                    elif tool_name == "validate_script":
                        score = result.get("overall_score", 0)
                        icon = "PASS" if score >= 0.9 else "WARN" if score >= 0.8 else "FAIL"
                        print(f"    -> [{icon}] {score:.0%} accuracy ({result.get('unsupported', 0)} unsupported)")
                    elif tool_name == "generate_script":
                        print(f"    -> {result.get('scene_count', 0)} scenes, {result.get('total_words', 0)} words")
                    elif tool_name == "generate_frames":
                        print(f"    -> {result.get('total_frames', 0)} frames, {result.get('error_count', 0)} fallbacks ({result.get('mode_used', '?')})")
                    elif tool_name == "generate_voiceover":
                        print(f"    -> {result.get('total_duration', 0)}s audio")
                    elif tool_name == "stitch_video":
                        print(f"    -> {result.get('video_size_mb', 0)} MB" if result.get("video_path") else "    -> FAILED")
                    elif tool_name == "burn_subtitles":
                        print(f"    -> {result.get('video_size_mb', 0)} MB" if result.get("subtitled_video_path") else "    -> FAILED")
                    elif tool_name == "rewrite_script":
                        print(f"    -> {result.get('word_count', 0)} words ({result.get('word_count_change', 0):+d})")
                    elif tool_name == "check_video":
                        print(f"    -> {'OK' if result.get('valid') else 'INVALID'}")

                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tool_id,
                        "content": result_json,
                    })
                except Exception as e:
                    err_msg = f"{e}\n{traceback.format_exc()[-500:]}"
                    print(f"    -> ERROR: {e}")
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tool_id,
                        "content": json.dumps({"error": err_msg}), "is_error": True,
                    })

            messages.append({"role": "user", "content": tool_results})

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"  Agent finished in {elapsed/60:.1f} minutes ({iteration} iterations)")
    print(f"  State: {json.dumps(STATE.to_dict(), indent=2)}")
    print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Autonomous Video Reel Agent")
    parser.add_argument("pdf_path", nargs="?", help="Path to drug PDF")
    parser.add_argument("--profile", default="sales_executive", choices=["sales_executive", "stockist", "retailer", "doctor", "all"])
    parser.add_argument("--topic", default=None)
    parser.add_argument("--all-topics", action="store_true")
    parser.add_argument("--voice", default="gaurav")
    parser.add_argument("--tts", default="elevenlabs", choices=["elevenlabs", "gemini"])
    parser.add_argument("--mode", default="demo", choices=["demo", "production"])
    parser.add_argument("--max-turns", type=int, default=AGENT_CFG["max_turns"])
    args = parser.parse_args()

    global AGENT_MODE
    AGENT_MODE = args.mode

    if args.pdf_path:
        pdf_path = os.path.abspath(args.pdf_path)
        if args.all_topics:
            prompt = (
                f'Generate ALL available video reels from "{pdf_path}" '
                f'for the {args.profile} profile. TTS: {args.tts}, Voice: {args.voice}. '
                f'Extract, analyze, then generate each reel end-to-end with subtitles.'
            )
        elif args.topic:
            prompt = (
                f'Generate a video reel from "{pdf_path}" '
                f'for the {args.profile} profile, topic: {args.topic}. TTS: {args.tts}, Voice: {args.voice}. '
                f'Run the full pipeline: extract -> analyze -> script -> validate -> frames -> voiceover -> stitch -> burn subtitles.'
            )
        else:
            prompt = (
                f'Generate the intro video reel from "{pdf_path}" '
                f'for the {args.profile} profile. TTS: {args.tts}, Voice: {args.voice}. '
                f'Run the full pipeline: extract -> analyze -> script -> validate -> frames -> voiceover -> stitch -> burn subtitles.'
            )
    else:
        prompt = "List the available drug PDFs and ask me which one to generate a video for."

    # Check env vars
    missing = [v for v in ["ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "ELEVENLABS_API_KEY"] if not os.environ.get(v)]
    if missing:
        print(f"Warning: Missing env vars: {', '.join(missing)}")
        print("Some pipeline steps may fail.\n")

    print(f"\n{'='*60}")
    print(f"  Video Agent (Adaptive)")
    print(f"  PDF: {os.path.basename(args.pdf_path) if args.pdf_path else 'interactive'}")
    print(f"  Profile: {args.profile} | TTS: {args.tts} | Voice: {args.voice} | Mode: {args.mode}")
    print(f"{'='*60}\n")

    run_agent(prompt, max_turns=args.max_turns)


if __name__ == "__main__":
    main()
