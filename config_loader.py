"""
Config loader — loads model settings and prompts from config/ directory.

All prompts and model configs live in config/ so they can be edited
without touching Python code.
"""

import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"
PROMPTS_DIR = CONFIG_DIR / "prompts"


def _load_text(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path} — check config/prompts/ directory")
    return path.read_text()


def _load_json(filename: str) -> dict:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Config file missing: {path} — check config/prompts/ directory")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")


def load_models() -> dict:
    path = CONFIG_DIR / "models.json"
    if not path.exists():
        raise FileNotFoundError(f"Models config missing: {path} — check config/ directory")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}")


# --- Agent ---
def load_agent_system_prompt() -> str:
    return _load_text("agent_system.txt")


# --- Script generation ---
def load_script_system_prompt() -> str:
    return _load_text("script_system.txt")


def load_script_user_template() -> str:
    return _load_text("script_user.txt")


def load_profile_context(profile: str) -> str:
    profiles = _load_json("profiles.json")
    return profiles.get(profile, profiles["doctor"])


def load_topic_prompt(topic: str) -> str:
    topics = _load_json("topics.json")
    return topics.get(topic, topics["intro"])


# --- Script outline (two-phase) ---
def load_script_outline_system_prompt() -> str:
    return _load_text("script_outline_system.txt")


def load_image_prompt_system_prompt() -> str:
    return _load_text("image_prompt_system.txt")


def load_image_prompt_user_template() -> str:
    return _load_text("image_prompt_user.txt")


# --- Content analysis ---
def load_analyze_system_prompt() -> str:
    return _load_text("analyze_system.txt")


def load_analyze_user_template() -> str:
    return _load_text("analyze_user.txt")


# --- Validation ---
def load_validate_system_prompt() -> str:
    return _load_text("validate_system.txt")


def load_validate_user_template() -> str:
    return _load_text("validate_user.txt")


# --- Frame generation ---
def load_frame_style_base() -> str:
    return _load_text("frame_style.txt")


def load_frame_text_guard() -> str:
    return _load_text("frame_text_guard.txt")


# --- TTS ---
def load_tts_gemini_template() -> str:
    return _load_text("tts_gemini.txt")
