"""
Validate generated script against source PDF content.

For each factual claim in the script narration, checks whether it can be
traced back to the source document. Flags unsupported claims.

Usage:
  python validate_script.py <script.json> <source_text_file>

Output: a _validation.json file with per-scene validation results.
"""

import json
import sys
import os
from anthropic import Anthropic
from config_loader import load_models, load_validate_system_prompt, load_validate_user_template

SYSTEM_PROMPT = load_validate_system_prompt()
USER_PROMPT_TEMPLATE = load_validate_user_template()
MODELS = load_models()


def validate_script(script_path: str, source_path: str) -> dict:
    with open(script_path) as f:
        script = json.load(f)

    with open(source_path) as f:
        source_text = f.read()

    script_json = json.dumps(script, indent=2)

    client = Anthropic()

    cfg = MODELS["validation"]
    with client.messages.stream(
        model=cfg["model"],
        max_tokens=cfg["max_tokens"],
        thinking=cfg.get("thinking"),
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                source_text=source_text,
                script_json=script_json,
            ),
        }],
    ) as stream:
        response = stream.get_final_message()

    text = ""
    for block in response.content:
        if block.type == "text":
            text = block.text.strip()
            break
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
        text = text.strip()

    # Handle case where model adds extra text after the JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to extract just the JSON object
        start = text.index("{")
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(text[start:i + 1])
        raise


def main():
    if len(sys.argv) < 3:
        print("Usage: python validate_script.py <script.json> <source_text_file>")
        sys.exit(1)

    script_path = sys.argv[1]
    source_path = sys.argv[2]

    base_name = os.path.splitext(os.path.basename(script_path))[0]
    print(f"Validating: {base_name}")
    print(f"  Script: {script_path}")
    print(f"  Source: {source_path}")

    result = validate_script(script_path, source_path)

    os.makedirs("output", exist_ok=True)
    out_path = f"output/{base_name}_validation.json"

    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    # Print summary
    accuracy = result.get("overall_accuracy", "unknown")
    score = result.get("overall_score", 0)
    total = result.get("total_claims", 0)
    supported = result.get("supported", 0)
    unsupported = result.get("unsupported", 0)
    flags = result.get("flags", [])

    print(f"\n  Accuracy: {accuracy} ({score:.0%})")
    print(f"  Claims: {total} total, {supported} supported, {unsupported} unsupported")

    if flags:
        print(f"\n  Flags ({len(flags)}):")
        for flag in flags:
            print(f"    - {flag}")
    else:
        print(f"\n  No flags — all claims supported by source")

    print(f"\n  Saved -> {out_path}")

    # Exit with error code if accuracy is low
    if unsupported > 0 and score < 0.8:
        print(f"\n  WARNING: Accuracy below 80% — script may need revision")
        sys.exit(2)


if __name__ == "__main__":
    main()
