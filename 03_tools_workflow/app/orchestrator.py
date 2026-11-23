import uuid
from pathlib import Path
from typing import Any

from google.genai import types
from pydantic import ValidationError

from app.llms.gemini import get_gemini_client
from app.logger_config import log_audit as log_audit_event
from app.models import AssistantActionPlan, UserContext
from app.settings import settings
from app.tools import TaskRepository, ToolExecutionError

PROMPT_PATH = Path(__file__).resolve().parent / "propmpts.md"


class PermissionDeniedError(Exception):
    pass


def load_system_prompt(user_input: str) -> str:
    template = PROMPT_PATH.read_text()
    return template.replace("{{ USER_INPUT }}", user_input)


def load_user_prompt(user_input: str) -> str:
    return user_input


def get_system_prompt(user_input: str) -> str:
    return load_system_prompt(user_input)


def _empty_token_usage(attempt: int) -> dict[str, int]:
    return {
        "attempt": attempt,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def _token_usage(
    response: types.GenerateContentResponse, attempt: int
) -> dict[str, int]:
    usage = response.usage_metadata
    if usage is None:
        return _empty_token_usage(attempt)
    return {
        "attempt": attempt,
        "input_tokens": usage.prompt_token_count or 0,
        "output_tokens": usage.candidates_token_count or 0,
        "total_tokens": usage.total_token_count or 0,
    }


def _plan_is_ready(plan: AssistantActionPlan) -> bool:
    if plan.tool_name == "none":
        return False
    if plan.clarification_message and plan.clarification_message.strip():
        return False
    args_by_tool = {
        "create_task": plan.create_args,
        "list_tasks": plan.list_args,
        "update_task": plan.update_args,
        "delete_task": plan.delete_args,
    }
    return args_by_tool.get(plan.tool_name) is not None


def _clarification_text(plan: AssistantActionPlan) -> str:
    if plan.clarification_message and plan.clarification_message.strip():
        return plan.clarification_message.strip()
    return "I need more detail before I can choose a task action."


class TaskManagementOrchestrator:

    def __init__(self, repo: TaskRepository) -> None:
        self.repo = repo
        self.client = get_gemini_client()

    def _check_permission(
        self,
        user: UserContext,
        tool_name: str,
        target_task_id: str | None = None,
    ) -> None:
        if not user.is_authenticated or user.user_id is None:
            raise PermissionDeniedError("User is not authenticated")

        allowed = {
            "viewer": {"list_tasks"},
            "editor": {
                "create_task",
                "list_tasks",
                "update_task",
                "delete_task",
            },
            "admin": {
                "create_task",
                "list_tasks",
                "update_task",
                "delete_task",
            },
        }
        if tool_name not in allowed.get(user.role, set()):
            raise PermissionDeniedError(
                f"Role '{user.role}' is not authorized to perform {tool_name}"
            )
        if (
            user.role != "admin"
            and tool_name in {"update_task", "delete_task"}
            and target_task_id
        ):
            task = self.repo.get_task(target_task_id)
            if task is not None and task["owner_id"] != user.user_id:
                raise PermissionDeniedError(
                    f"User '{user.user_id}' cannot modify task owned by '{task['owner_id']}'."
                )

    def is_destructive(self, plan: AssistantActionPlan) -> bool:
        if plan.tool_name == "delete_task":
            return True
        if (
            plan.tool_name == "update_task"
            and plan.update_args
            and plan.update_args.new_status == "cancelled"
        ):
            return True
        return False

    def request_plan(
        self,
        user_prompt: str,
        history: list[types.Content],
        user: UserContext,
        trace_id: str,
        attempt: int,
    ) -> dict[str, Any]:
        """Ask the model once. Append its reply to history and record token use."""
        system_prompt = get_system_prompt(user_prompt)
        try:
            response = self.client.models.generate_content(
                model=settings.gemini.model_name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=AssistantActionPlan,
                ),
            )
        except Exception as exc:
            tokens = _empty_token_usage(attempt)
            log_audit_event(
                trace_id,
                user.user_id,
                "llm_plan",
                "LLM_REQUEST",
                {"attempt": attempt, "error": str(exc), **tokens},
            )
            return {
                "status": "error",
                "message": f"Model request failed: {exc}",
                "plan": None,
                "tokens": tokens,
                "history": history,
            }

        tokens = _token_usage(response, attempt)
        model_text = response.text or ""
        if model_text:
            history.append(
                types.Content(role="model", parts=[types.Part(text=model_text)])
            )

        try:
            plan = AssistantActionPlan.model_validate_json(model_text)
        except ValidationError as exc:
            log_audit_event(
                trace_id,
                user.user_id,
                "parse_intent",
                "VALIDATION_ERROR",
                {"attempt": attempt, "error": str(exc), **tokens},
            )
            return {
                "status": "error",
                "message": "Invalid task arguments extracted.",
                "details": exc.errors(),
                "plan": None,
                "tokens": tokens,
                "history": history,
            }

        log_audit_event(
            trace_id,
            user.user_id,
            "llm_plan",
            "LLM_REQUEST",
            {
                "attempt": attempt,
                "tool_name": plan.tool_name,
                "needs_clarification": not _plan_is_ready(plan),
                **tokens,
            },
        )
        if _plan_is_ready(plan):
            return {
                "status": "ready",
                "plan": plan,
                "tokens": tokens,
                "history": history,
            }
        return {
            "status": "clarification_needed",
            "message": _clarification_text(plan),
            "plan": plan,
            "tokens": tokens,
            "history": history,
        }

    def apply_plan(
        self, user: UserContext, plan: AssistantActionPlan, trace_id: str
    ) -> dict[str, Any]:
        """Run permission checks and the selected tool for a ready plan."""
        # Extract target task ID if applicable
        target_id = None
        if plan.tool_name == "update_task" and plan.update_args:
            target_id = plan.update_args.task_id
        elif plan.tool_name == "delete_task" and plan.delete_args:
            target_id = plan.delete_args.task_id

        # Deterministic Authentication & Permission Checks
        try:
            self._check_permission(user, plan.tool_name, target_id)
        except PermissionDeniedError as e:
            log_audit_event(
                trace_id,
                user.user_id,
                plan.tool_name,
                "DENIED",
                {"reason": str(e)},
            )
            return {"status": "forbidden", "message": str(e)}

        #  Destructive Action Confirmation
        if self.is_destructive(plan):
            confirmation_token = f"CONF-{uuid.uuid4().hex[:6].upper()}"
            self.repo._pending_confirmations[confirmation_token] = {
                "user_id": user.user_id,
                "plan": plan,
            }
            log_audit_event(
                trace_id,
                user.user_id,
                plan.tool_name,
                "PENDING_CONFIRMATION",
                {
                    "token": confirmation_token,
                    "args": plan.model_dump(exclude_none=True),
                },
            )
            return {
                "status": "confirmation_required",
                "confirmation_token": confirmation_token,
                "tool_name": plan.tool_name,
                "message": (
                    f"Destructive action '{plan.tool_name}' needs your confirmation."
                ),
            }

        # Execute Non-Destructive Tool in Application Code
        return self._execute_plan(trace_id, user, plan)

    def handle_user_request(
        self, user_prompt: str, user: UserContext
    ) -> dict[str, Any]:
        """Single model call. The interactive retry loop lives in main.py."""
        trace_id = str(uuid.uuid4())[:8]
        history = [
            types.Content(role="user", parts=[types.Part(text=user_prompt)])
        ]
        planned = self.request_plan(user_prompt, history, user, trace_id, 1)
        if planned["status"] != "ready" or planned["plan"] is None:
            return planned
        result = self.apply_plan(user, planned["plan"], trace_id)
        result["tokens"] = planned["tokens"]
        return result

    def confirm_action(
        self, confirmation_token: str, user: UserContext, reason: str
    ) -> dict[str, Any]:
        """Run a pending destructive plan after the user confirms and gives a reason."""
        trace_id = str(uuid.uuid4())[:8]
        cleaned_reason = reason.strip()
        if not cleaned_reason:
            return {
                "status": "error",
                "message": "A reason is required to confirm this action.",
            }

        pending = self.repo._pending_confirmations.get(confirmation_token)

        if not pending:
            return {
                "status": "error",
                "message": "Invalid or expired confirmation token.",
            }
        if pending["user_id"] != user.user_id:
            log_audit_event(
                trace_id,
                user.user_id,
                "confirm_action",
                "DENIED",
                {"reason": "Token owner mismatch"},
            )
            return {
                "status": "forbidden",
                "message": "You cannot confirm another user's pending action.",
            }

        del self.repo._pending_confirmations[confirmation_token]
        return self._execute_plan(
            trace_id, user, pending["plan"], reason=cleaned_reason
        )

    def decline_action(
        self, confirmation_token: str, user: UserContext
    ) -> dict[str, Any]:
        """Drop a pending destructive plan when the user says no."""
        pending = self.repo._pending_confirmations.pop(confirmation_token, None)
        if pending is None:
            return {
                "status": "error",
                "message": "Invalid or expired confirmation token.",
            }
        plan = pending["plan"]
        log_audit_event(
            str(uuid.uuid4())[:8],
            user.user_id,
            plan.tool_name,
            "DENIED",
            {"reason": "User declined confirmation"},
        )
        return {
            "status": "cancelled",
            "message": "Cancelled. No change was made.",
        }

    def _execute_plan(
        self,
        trace_id: str,
        user: UserContext,
        plan: AssistantActionPlan,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Controlled execution wrapper catching downstream tool/DB errors."""
        try:
            if user.user_id is None:
                raise ToolExecutionError("User id is required")
            if plan.tool_name == "create_task" and plan.create_args:
                result = self.repo.create_task(plan.create_args, user.user_id)
            elif plan.tool_name == "list_tasks" and plan.list_args:
                result = self.repo.list_tasks(plan.list_args)
            elif plan.tool_name == "update_task" and plan.update_args:
                result = self.repo.update_task(plan.update_args, user.user_id)
            elif plan.tool_name == "delete_task" and plan.delete_args:
                result = self.repo.delete_task(
                    plan.delete_args, user.user_id, reason=reason
                )
            else:
                raise ToolExecutionError(
                    f"Missing arguments for tool '{plan.tool_name}'."
                )

            details: dict[str, Any] = {"result": result}
            if reason:
                details["reason"] = reason
            log_audit_event(
                trace_id,
                user.user_id,
                plan.tool_name,
                "SUCCESS",
                details,
            )
            return {"status": "success", "data": result}

        except ToolExecutionError as e:
            log_audit_event(
                trace_id,
                user.user_id,
                plan.tool_name,
                "TOOL_ERROR",
                {"error": str(e)},
            )
            return {"status": "tool_error", "message": str(e)}
