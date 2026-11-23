import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import httpx
from google import genai
from google.genai import errors, types

try:
    import httpx2
except ImportError:
    httpx2 = None

_REQUEST_ERRORS: tuple[type[BaseException], ...] = (
    httpx.HTTPError,
    TimeoutError,
    ConnectionError,
)
if httpx2 is not None:
    _REQUEST_ERRORS = (*_REQUEST_ERRORS, httpx2.HTTPError)

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.settings import settings

DEFAULT_SYSTEM_INSTRUCTION = (
    "You are a helpful assistant. Answer clearly and concisely."
)


@dataclass(frozen=True)
class TokenUsage:

    prompt_token_count: int
    candidates_token_count: int
    thoughts_token_count: int
    total_token_count: int


@dataclass(frozen=True)
class ChatReply:

    text: str
    usage: TokenUsage


class GeminiError(Exception):

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


def _token_usage(response: types.GenerateContentResponse) -> TokenUsage:
    usage = response.usage_metadata
    if usage is None:
        return TokenUsage(0, 0, 0, 0)
    return TokenUsage(
        prompt_token_count=usage.prompt_token_count or 0,
        candidates_token_count=usage.candidates_token_count or 0,
        thoughts_token_count=usage.thoughts_token_count or 0,
        total_token_count=usage.total_token_count or 0,
    )


def _build_gemini_client() -> genai.Client:
    """Create a Gemini client. Importing the app does not require a secret."""
    api_key = settings.gemini.api_key
    if api_key is None or not api_key.get_secret_value().strip():
        raise GeminiError(
            "GEMINI__API_KEY is required to use the Gemini integration"
        )
    return genai.Client(api_key=api_key.get_secret_value())


@lru_cache(maxsize=1)
def _cached_gemini_client() -> genai.Client:
    return _build_gemini_client()


def get_gemini_client() -> genai.Client:
    """Return a Gemini client.

    Set GEMINI__CACHE_CLIENT=true to reuse one client for the process.
    The default creates a new client per call. Keep the returned client
    referenced until generate_content finishes; dropping it closes the
    HTTP connection.
    """
    if settings.gemini.cache_client:
        return _cached_gemini_client()
    return _build_gemini_client()


def _response_text(response: types.GenerateContentResponse) -> str:
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason:
        detail = feedback.block_reason_message or feedback.block_reason
        raise GeminiError(f"Gemini blocked the prompt: {detail}")

    candidate = response.candidates[0] if response.candidates else None
    if candidate is None or candidate.content is None or not response.text:
        reason = candidate.finish_reason if candidate is not None else None
        if reason:
            raise GeminiError(f"Gemini returned no text ({reason})")
        raise GeminiError("Gemini returned an empty text response")
    return response.text


class GeminiChat:
    """Multi-turn Gemini chat. History and per-request usage stay on the instance."""

    def __init__(
        self,
        history: list[types.Content] | None = None,
        system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION,
    ) -> None:
        self.history: list[types.Content] = list(history or [])
        self.usages: list[TokenUsage] = []
        self.system_instruction = system_instruction

    def send(self, prompt: str) -> ChatReply:
        if not prompt or not prompt.strip():
            raise GeminiError("Prompt is empty")

        user_turn = types.Content(role="user", parts=[types.Part(text=prompt)])
        client = get_gemini_client()
        try:
            response = client.models.generate_content(
                model=settings.gemini.model_name,
                contents=[*self.history, user_turn],
                config=types.GenerateContentConfig(
                    temperature=1,
                    system_instruction=self.system_instruction,
                ),
            )
        except errors.APIError as exc:
            detail = exc.message or str(exc)
            raise GeminiError(
                f"Gemini request failed ({exc.code} {exc.status}): {detail}",
                status_code=exc.code,
            ) from exc
        except _REQUEST_ERRORS as exc:
            raise GeminiError(
                f"Gemini request could not be sent: {exc}"
            ) from exc

        text = _response_text(response)
        self.history.append(user_turn)
        self.history.append(response.candidates[0].content)
        usage = _token_usage(response)
        self.usages.append(usage)
        return ChatReply(text=text, usage=usage)


if __name__ == "__main__":
    chat = GeminiChat()
    prompts = [
        """Q: Roger has 5 tennis balls. He buys 2 more cans of tennis balls. Each can has 3 tennis balls. How many tennis balls does he have now?
A: The answer is 11.
Q: A cafeteria had 23 apples. If they used 20 to make lunch and bought 6 more, how many apples do they have?
A: """
    ]
    try:
        for prompt in prompts:
            reply = chat.send(prompt)
            print(f"user: {prompt}")
            print(f"model: {reply.text}")
            print(
                "tokens:"
                f" prompt={reply.usage.prompt_token_count}"
                f" reply={reply.usage.candidates_token_count}"
                f" thoughts={reply.usage.thoughts_token_count}"
                f" total={reply.usage.total_token_count}"
            )
            print()
    except GeminiError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(f"turns stored: {len(chat.history)}")
    print(f"requests tracked: {len(chat.usages)}")
