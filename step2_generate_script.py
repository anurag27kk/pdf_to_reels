"""
Step 2: Generate video script from extracted PDF text using Claude API

Takes extracted text + profile (doctor/stockist/retailer) + reel topic
Outputs a structured JSON script with scenes, narration, and visual cues
"""
from __future__ import annotations

import copy
import json
import sys
import os
from anthropic import Anthropic
from config_loader import (
    load_models,
    load_script_system_prompt,
    load_script_user_template,
    load_script_outline_system_prompt,
    load_image_prompt_system_prompt,
    load_image_prompt_user_template,
    load_profile_context,
    load_topic_prompt,
)

SYSTEM_PROMPT = load_script_system_prompt()
OUTLINE_SYSTEM_PROMPT = load_script_outline_system_prompt()
IMAGE_PROMPT_SYSTEM = load_image_prompt_system_prompt()
IMAGE_PROMPT_USER_TEMPLATE = load_image_prompt_user_template()
USER_PROMPT_TEMPLATE = load_script_user_template()
MODELS = load_models()


def get_profile_context(profile: str) -> str:
    return load_profile_context(profile)


def get_reel_topic_prompt(topic: str, analysis: dict | None = None) -> str:
    base_prompt = load_topic_prompt(topic)

    # If we have analysis from step 1b, add source section hints
    if analysis:
        for t in analysis.get("available_topics", []):
            if t["topic_id"] == topic and t.get("source_sections"):
                sections = ", ".join(t["source_sections"])
                base_prompt += f"\nHINT: The relevant content is likely in these sections of the document: {sections}\n"
                if t.get("content_summary"):
                    base_prompt += f"Content available: {t['content_summary']}\n"
                break

    return base_prompt


def generate_script(pdf_text: str, profile: str, topic: str, analysis: dict | None = None, guidance: str = "") -> dict:
    """Generate complete script with image_prompts (monolithic, single-pass)."""
    cfg = MODELS["script_generation"]

    profile_context = get_profile_context(profile)
    topic_prompt = get_reel_topic_prompt(topic, analysis)

    guidance_block = ""
    if guidance and guidance.strip():
        guidance_block = f"CREATIVE DIRECTION FROM CLIENT:\n{guidance.strip()}\nUse this to guide the tone, focus, and emphasis of the script."

    user_prompt = USER_PROMPT_TEMPLATE.format(
        pdf_content=pdf_text,
        profile_context=profile_context,
        topic_prompt=topic_prompt,
        guidance=guidance_block,
    )

    text = _call_claude(SYSTEM_PROMPT, user_prompt, cfg)
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    """Extract JSON from Claude response text, handling markdown fences, trailing text, and trailing commas."""
    import re
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
        text = text.strip()

    def _try_parse(s: str) -> dict | None:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        # Remove trailing commas before } or ] (common LLM mistake)
        cleaned = re.sub(r',\s*([}\]])', r'\1', s)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None

    result = _try_parse(text)
    if result is not None:
        return result

    # Try to find the outermost JSON object
    start = text.index("{")
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                result = _try_parse(text[start:i + 1])
                if result is not None:
                    return result
    raise json.JSONDecodeError("Could not extract valid JSON", text, 0)


def _call_claude(system: str, user: str, cfg: dict) -> str:
    """Call Claude API with streaming, return text block content."""
    client = Anthropic()
    stream_kwargs = {
        "model": cfg["model"],
        "max_tokens": cfg["max_tokens"],
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    if cfg.get("thinking"):
        stream_kwargs["thinking"] = cfg["thinking"]

    with client.messages.stream(**stream_kwargs) as stream:
        response = stream.get_final_message()

    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            break
    if not text:
        raise ValueError("Claude returned no text block — likely max_tokens too low for adaptive thinking")
    return text


def generate_script_outline(pdf_text: str, profile: str, topic: str, analysis: dict | None = None, guidance: str = "") -> dict:
    """Generate script without image_prompt fields (Phase 1 of two-phase generation)."""
    cfg = MODELS["script_outline"]
    profile_context = get_profile_context(profile)
    topic_prompt = get_reel_topic_prompt(topic, analysis)

    guidance_block = ""
    if guidance and guidance.strip():
        guidance_block = f"CREATIVE DIRECTION FROM CLIENT:\n{guidance.strip()}\nUse this to guide the tone, focus, and emphasis of the script."

    user_prompt = USER_PROMPT_TEMPLATE.format(
        pdf_content=pdf_text,
        profile_context=profile_context,
        topic_prompt=topic_prompt,
        guidance=guidance_block,
    )

    text = _call_claude(OUTLINE_SYSTEM_PROMPT, user_prompt, cfg)
    return _extract_json(text)


def generate_image_prompts(script_outline: dict, pdf_text: str) -> dict:
    """Generate image prompts for content scenes (Phase 2 of two-phase generation).

    Returns dict mapping scene_number (str) to image_prompt string.
    """
    cfg = MODELS["image_prompt_generation"]

    # Build outline summary: only content scenes' narration/visual_description/on_screen_text
    content_scenes = []
    for scene in script_outline["scenes"]:
        if scene.get("scene_type", "content") == "content":
            content_scenes.append({
                "scene_number": scene["scene_number"],
                "narration": scene.get("narration", ""),
                "visual_description": scene.get("visual_description", ""),
                "on_screen_text": scene.get("on_screen_text", []),
            })

    user_prompt = IMAGE_PROMPT_USER_TEMPLATE.format(
        pdf_content=pdf_text,
        script_outline=json.dumps(content_scenes, indent=2),
    )

    text = _call_claude(IMAGE_PROMPT_SYSTEM, user_prompt, cfg)
    result = _extract_json(text)
    return result.get("image_prompts", result)


def merge_image_prompts(script: dict, image_prompts: dict) -> dict:
    """Merge image_prompt fields into matching content scenes. Returns new dict."""
    merged = copy.deepcopy(script)
    for scene in merged["scenes"]:
        sn = str(scene["scene_number"])
        if sn in image_prompts and scene.get("scene_type", "content") == "content":
            scene["image_prompt"] = image_prompts[sn]
    return merged


QUIZ_SCENE_TYPES = {"quiz_intro", "quiz", "quiz_answer", "score", "cta", "leaderboard"}


def filter_quiz_scenes(script: dict) -> dict:
    """Remove quiz and gamification scenes from a script. Returns a new dict."""
    filtered = [s for s in script["scenes"] if s.get("scene_type", "content") not in QUIZ_SCENE_TYPES]
    for i, scene in enumerate(filtered, 1):
        scene["scene_number"] = i
    return {
        **script,
        "scenes": filtered,
        "mode": "production",
        "total_word_count": sum(len(s.get("narration", "").split()) for s in filtered),
        "estimated_duration_seconds": sum(s.get("duration_seconds", 0) for s in filtered),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python step2_generate_script.py <text_file> [profile] [topic] [analysis_file] [--mode demo|production]")
        print("  profile: doctor (default), stockist, retailer")
        print("  topic: intro (default), indications, mechanism, dosage_safety, interactions, side_effects")
        print("  --mode: demo (default, includes quiz/gamification) or production (content only)")
        sys.exit(1)

    # Parse flags from argv
    mode = "demo"
    guidance = ""
    argv = list(sys.argv[1:])
    if "--mode" in argv:
        idx = argv.index("--mode")
        mode = argv[idx + 1]
        argv = argv[:idx] + argv[idx + 2:]
    if "--guidance" in argv:
        idx = argv.index("--guidance")
        guidance = argv[idx + 1]
        argv = argv[:idx] + argv[idx + 2:]

    text_file = argv[0]
    profile = argv[1] if len(argv) > 1 else "doctor"
    topic = argv[2] if len(argv) > 2 else "intro"
    analysis_file = argv[3] if len(argv) > 3 else None

    with open(text_file) as f:
        pdf_text = f.read()

    analysis = None
    if analysis_file and os.path.exists(analysis_file):
        with open(analysis_file) as f:
            analysis = json.load(f)
        print(f"Using content analysis from {analysis_file}")

    print(f"Generating script: product from {text_file}, profile={profile}, topic={topic}, mode={mode}")
    if guidance:
        print(f"  Creative direction: {guidance[:80]}{'...' if len(guidance) > 80 else ''}")
    script = generate_script(pdf_text, profile, topic, analysis, guidance=guidance)

    os.makedirs("output", exist_ok=True)
    base_name = os.path.splitext(os.path.basename(text_file))[0]
    out_path = f"output/{base_name}_{profile}_{topic}_script.json"

    if mode == "production":
        # Save full script separately, then filter
        full_path = f"output/{base_name}_{profile}_{topic}_script_full.json"
        with open(full_path, "w") as f:
            json.dump(script, f, indent=2)
        print(f"Full script (with quiz) -> {full_path}")
        script = filter_quiz_scenes(script)

    with open(out_path, "w") as f:
        json.dump(script, f, indent=2)

    total_words = sum(len(s.get("narration", "").split()) for s in script["scenes"])
    total_duration = sum(s.get("duration_seconds", 0) for s in script["scenes"])

    print(f"Generated {len(script['scenes'])} scenes, ~{total_words} words, ~{total_duration}s")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
