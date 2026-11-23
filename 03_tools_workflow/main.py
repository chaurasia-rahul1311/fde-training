import uuid

from google.genai import types

from app.db import get_user_details
from app.orchestrator import TaskManagementOrchestrator
from app.tools import TaskRepository

MAX_ATTEMPTS = 3


def _print_attempt_tokens(tokens: dict[str, int]) -> None:
    print(
        f"[attempt {tokens['attempt']}/{MAX_ATTEMPTS}] "
        f"input_tokens={tokens['input_tokens']} "
        f"output_tokens={tokens['output_tokens']} "
        f"total_tokens={tokens['total_tokens']}"
    )


def _print_token_summary(entries: list[dict[str, int]]) -> None:
    print(
        "[token summary] "
        f"requests={len(entries)} "
        f"input_tokens={sum(item['input_tokens'] for item in entries)} "
        f"output_tokens={sum(item['output_tokens'] for item in entries)} "
        f"total_tokens={sum(item['total_tokens'] for item in entries)}"
    )


def _read_follow_up() -> str:
    follow_up = input("You: ").strip()
    while not follow_up:
        print("Please add the missing detail.")
        follow_up = input("You: ").strip()
    return follow_up


def _read_yes_no() -> bool:
    while True:
        answer = input("Confirm this action? (yes/no): ").strip().lower()
        if answer in {"yes", "y", "Y"}:
            return True
        if answer in {"no", "n", "N"}:
            return False
        print("Enter yes or no.")


def _read_reason() -> str:
    reason = input("Reason: ").strip()
    while not reason:
        print("A reason is required.")
        reason = input("Reason: ").strip()
    return reason


def _finish_ready_plan(assistant, user, result, token_log) -> None:
    """Ask before a destructive plan. Yes needs a reason. No exits."""
    if result.get("status") != "confirmation_required":
        result["token_usage"] = token_log
        print(result)
        _print_token_summary(token_log)
        return

    print(f"Assistant: {result['message']}")
    if not _read_yes_no():
        declined = assistant.decline_action(result["confirmation_token"], user)
        print(declined["message"])
        _print_token_summary(token_log)
        return

    reason = _read_reason()
    confirmed = assistant.confirm_action(
        result["confirmation_token"], user, reason
    )
    confirmed["token_usage"] = token_log
    print(confirmed)
    _print_token_summary(token_log)


def run_with_clarification_retries(assistant, user) -> None:
    """Ask the model up to 3 times, keeping history until a tool is ready."""
    user_prompt = input("Task request: ").strip()
    if not user_prompt:
        print("Prompt is empty")
        return

    trace_id = str(uuid.uuid4())[:8]
    history: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=user_prompt)])
    ]
    token_log: list[dict[str, int]] = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        planned = assistant.request_plan(
            user_prompt, history, user, trace_id, attempt
        )
        token_log.append(planned["tokens"])
        _print_attempt_tokens(planned["tokens"])
        history = planned["history"]

        if planned["status"] == "error":
            print(planned["message"])
            _print_token_summary(token_log)
            return

        if planned["status"] == "ready":
            result = assistant.apply_plan(user, planned["plan"], trace_id)
            _finish_ready_plan(assistant, user, result, token_log)
            return

        print(f"Assistant: {planned['message']}")
        if attempt == MAX_ATTEMPTS:
            print("Stopped after 3 attempts. A tool was not selected.")
            print(
                {
                    "status": "clarification_needed",
                    "message": planned["message"],
                    "token_usage": token_log,
                }
            )
            _print_token_summary(token_log)
            return

        follow_up = _read_follow_up()
        user_prompt = f"{user_prompt}\n{follow_up}"
        history.append(
            types.Content(role="user", parts=[types.Part(text=follow_up)])
        )


if __name__ == "__main__":
    repo = TaskRepository()
    assistant = TaskManagementOrchestrator(repo)
    user_id = 8

    user_details = get_user_details(user_id)
    if user_details is None:
        print("User not found")
        exit(1)

    print(f"Signed in as {user_details.full_name} ({user_details.role})")
    run_with_clarification_retries(assistant, user_details)
