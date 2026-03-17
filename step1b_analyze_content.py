"""
Step 1b: Analyze extracted PDF content to detect structure and plan reels.

Takes the extracted text from step 1 and uses Claude to:
1. Identify what kind of document this is (monograph, leaflet, brochure, etc.)
2. Detect what sections/topics exist in the content
3. Map to available reel topics (intro, mechanism, dosage, etc.)
4. Estimate how many reels this PDF can produce

Output: an analysis JSON that feeds into step 2 (script generation).
"""

import json
import sys
import os
from anthropic import Anthropic
from config_loader import load_models, load_analyze_system_prompt, load_analyze_user_template

SYSTEM_PROMPT = load_analyze_system_prompt()
USER_PROMPT_TEMPLATE = load_analyze_user_template()
MODELS = load_models()


def analyze_content(content: str) -> dict:
    client = Anthropic()

    user_prompt = USER_PROMPT_TEMPLATE.format(content=content)

    cfg = MODELS["content_analysis"]
    with client.messages.stream(
        model=cfg["model"],
        max_tokens=cfg["max_tokens"],
        thinking=cfg.get("thinking"),
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
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

    try:
        return json.loads(text)
    except json.JSONDecodeError:
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
    if len(sys.argv) < 2:
        print("Usage: python step1b_analyze_content.py <extracted_text_file>")
        print("  Input: .md or .txt file from step 1")
        print("  Output: _analysis.json with reel planning info")
        sys.exit(1)

    text_file = sys.argv[1]

    with open(text_file) as f:
        content = f.read()

    base_name = os.path.splitext(os.path.basename(text_file))[0]
    print(f"Analyzing content: {base_name} ({len(content)} chars)")

    analysis = analyze_content(content)

    os.makedirs("output", exist_ok=True)
    out_path = f"output/{base_name}_analysis.json"

    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2)

    # Print summary
    product = analysis.get("product_name", "Unknown")
    doc_type = analysis.get("document_type", "unknown")
    total = analysis.get("total_reels_possible", 0)
    topics = analysis.get("available_topics", [])

    print(f"\nProduct: {product}")
    print(f"Document type: {doc_type}")
    print(f"Reels possible: {total}\n")

    for t in topics:
        status = "YES" if t["can_generate"] else " NO"
        conf = t.get("confidence", "?")
        dur = t.get("estimated_duration_seconds", 0)
        print(f"  [{status}] {t['topic_id']:<16} confidence={conf:<6} ~{dur}s")

    order = analysis.get("recommended_reel_order", [])
    print(f"\nRecommended order: {' -> '.join(order)}")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
