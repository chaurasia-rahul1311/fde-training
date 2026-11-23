from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROMPTS_DIR = ROOT / "app" / "prompts"


def load_text(file_path: Path) -> str:
    if not file_path.is_file():
        raise FileNotFoundError(f"Missing file: {file_path}")
    return file_path.read_text(encoding="utf-8").strip()


def load_prompt_files() -> list[Path]:
    prompt_files = sorted(PROMPTS_DIR.glob("*.md"))
    if not prompt_files:
        raise FileNotFoundError(f"No prompt files in {PROMPTS_DIR}")
    return prompt_files


def render_prompt(template: str, jd_text: str, candidate_text: str) -> str:
    """Fill the prompt file. Unfilled placeholders would be sent to the model as-is."""
    return template.replace("{{JOB_DESCRIPTION}}", jd_text).replace(
        "{{CANDIDATE_PROFILE}}", candidate_text
    )


def build_user_payload(jd_text: str, candidate_text: str) -> str:
    """Used only when a prompt file has no placeholders of its own."""
    return f"""Analyze the following candidate against the job description.

<job_description>
{jd_text}
</job_description>

<candidate_profile>
{candidate_text}
</candidate_profile>"""


def prompt_request(
    template: str, jd_text: str, candidate_text: str
) -> tuple[str | None, str]:
    """Load the prompt file and return the system prompt and user message."""
    if "{{JOB_DESCRIPTION}}" in template or "{{CANDIDATE_PROFILE}}" in template:
        return None, render_prompt(template, jd_text, candidate_text)
    return template, build_user_payload(jd_text, candidate_text)
