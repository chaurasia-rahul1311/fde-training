import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.genai import types

from app.settings import settings

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.llms.gemini import GeminiError, get_gemini_client
from prompt_loader import load_prompt_files, load_text, prompt_request

MODEL_NAME = settings.gemini.model_name
TESTS_DIR = ROOT / "test_cases"
EVALS_DIR = ROOT / "evaluations"
CASES = (
    (
        "senior_backend_partial_injection",
        "jd_senior_backend.txt",
        "rahul_profile_partial_match_injection.txt",
    ),
    (
        "senior_backend_strong_match",
        "jd_senior_backend.txt",
        "rahul_profile_partial_match_injection.txt",
    ),
    (
        "data_analyst_partial",
        "jd_data_analyst.txt",
        "rahul_profile_partial_match_injection.txt",
    ),
)


def run_comparison() -> None:
    model_name = MODEL_NAME
    client = get_gemini_client()
    results = []

    for case_name, jd_name, candidate_name in CASES:
        jd_text = load_text(TESTS_DIR / jd_name)
        candidate_text = load_text(TESTS_DIR / candidate_name)

        for prompt_file in load_prompt_files():
            import code

            code.interact(local=dict(globals(), **locals()))
            version_name = prompt_file.stem
            print(f"Running {version_name} on {case_name}...")

            system_prompt, user_message = prompt_request(
                load_text(prompt_file), jd_text, candidate_text
            )
            config_kwargs = {
                "temperature": 0,
                "response_mime_type": "application/json",
            }
            if system_prompt:
                config_kwargs["system_instruction"] = system_prompt
            response = client.models.generate_content(
                model=model_name,
                contents=user_message,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            raw_text = response.text or ""
            try:
                parsed_output = json.loads(raw_text)
            except json.JSONDecodeError:
                parsed_output = {"raw_text": raw_text, "json_error": True}

            results.append(
                {
                    "case": case_name,
                    "version": version_name,
                    "model": model_name,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "output": parsed_output,
                }
            )

    EVALS_DIR.mkdir(exist_ok=True)
    output_file = EVALS_DIR / "comparison_results.json"
    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nDone! Results saved to {output_file}")


if __name__ == "__main__":
    try:
        run_comparison()
    except (GeminiError, FileNotFoundError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
