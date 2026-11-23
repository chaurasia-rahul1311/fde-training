# FDE Training

Hands-on exercises for building generative AI applications with Google Gemini. Each numbered folder is its own Python project, managed with [uv](https://docs.astral.sh/uv/).

| Folder | What it covers |
| --- | --- |
| `01_model_selection` | Gemini client setup and model configuration |
| `02_prompting_techniques` | Prompt versions compared against recruiter test cases |
| `03_tools_workflow` | A task assistant that calls tools through an orchestrator |
| `04_recrutier_assistant` | A recruiter assistant that scores candidates against job descriptions |

## Setup

Requires Python 3.12 or newer and uv. Work inside one module at a time:

```sh
cd 01_model_selection
uv sync
```

Create a `.env` in that folder and set `GEMINI__API_KEY`. Settings use nested environment variables with `__` as the separator. `APP__DEBUG` and `APP__ENVIRONMENT` are optional; `GEMINI__MODEL_NAME` defaults to `gemini-3.8-flash`.

Repeat `uv sync` and add a `.env` in any other module you run. Each folder has its own dependencies and README.

## Run

From the module directory:

```sh
uv run python main.py
```

`01_model_selection` is a library-style integration. Run it with `uv run python -m app.llms.gemini` from that folder. See each module README for the endpoints and scripts that module exposes.
