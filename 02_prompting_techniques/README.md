# Model Integrations

A small FastAPI service with an on-demand Google Gemini text-generation integration.

## Setup

Requires Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
cp .env.example .env
```

Set `GEMINI__API_KEY` in `.env`. Settings use nested environment variables with `__` as the separator. `APP__DEBUG` and `APP__ENVIRONMENT` are optional; `GEMINI__MODEL_NAME` defaults to `gemini-3.8-flash`.

## Run

```sh
uv run uvicorn main:app --reload
```

Run an integration module from the project directory with `uv run python -m app.llms.gemini`. Avoid launching it by a path from another working directory; if you use an IDE's file runner, set the working directory to this project.

The service exposes `GET /health`, interactive API documentation at `/docs`, and `POST /api/v1/gemini/generate` with a JSON body such as:

```json
{"prompt": "Explain embeddings in one sentence."}
```

The API key is not needed to start the service or check health. The generation endpoint returns `503` if it is missing.
