import sqlite3
import time
import functools
from google.genai import types
from app.models import CreateTask, ListTasks, UpdateTask, DeleteTask
from typing import Any

from app.db import DB_PATH
from app.llms.gemini import get_gemini_client
from app.settings import settings


class ToolExecutionError(Exception):
    pass


def trace_tool(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        print(f"\n--> [TOOL CALL] {func.__name__} | Payload: {kwargs}")
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        print(f"<-- [TOOL OUT] ({elapsed:.1f}ms) | {result}")
        return result

    return wrapper


def _next_task_id(conn: sqlite3.Connection) -> str:
    rows = conn.execute("SELECT task_id FROM tasks").fetchall()
    numbers = [
        int(task_id[4:])
        for (task_id,) in rows
        if isinstance(task_id, str)
        and task_id.startswith("TSK-")
        and task_id[4:].isdigit()
    ]
    return f"TSK-{(max(numbers) if numbers else 100) + 1}"


def _due_date(value: Any) -> str:
    if hasattr(value, "date"):
        return value.date().isoformat()
    return str(value)


class TaskRepository:
    def __init__(self) -> None:
        self._pending_confirmations: dict[str, dict[str, Any]] = {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT task_id, title, description, priority, due_date, status, owner_id
                FROM tasks
                WHERE task_id = ? AND is_deleted = 0
                """,
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(row)

    @trace_tool
    def create_task(self, task: CreateTask, owner_id: int) -> dict[str, Any]:
        """Persist a validated task. The application assigns the task id."""
        from app.db import get_user_details

        if get_user_details(owner_id) is None:
            raise ToolExecutionError(f"No user found with id {owner_id}")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            task_id = _next_task_id(conn)
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, title, description, priority, due_date, status, owner_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task.title.strip(),
                    task.description.strip(),
                    task.priority,
                    _due_date(task.due_date),
                    task.status,
                    owner_id,
                ),
            )
        return {
            "status": "TASK_SAVED",
            "task_id": task_id,
            "title": task.title,
            "owner_id": owner_id,
        }

    @trace_tool
    def list_tasks(self, args: ListTasks) -> dict[str, Any]:
        query = """
            SELECT task_id, title, description, priority, due_date, status, owner_id
            FROM tasks
            WHERE is_deleted = 0
        """
        params: list[Any] = []
        if args.owner_id is not None:
            query += " AND owner_id = ?"
            params.append(args.owner_id)
        if args.priority is not None:
            query += " AND priority = ?"
            params.append(args.priority)
        if args.status_filter != "all":
            query += " AND status = ?"
            params.append(args.status_filter)
        if args.description:
            query += " AND description LIKE ?"
            params.append(f"%{args.description}%")
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return {
            "status": "TASKS_LISTED",
            "tasks": [dict(row) for row in rows],
        }

    @trace_tool
    def update_task(self, task: UpdateTask, owner_id: int) -> dict[str, Any]:
        existing = self.get_task(task.task_id)
        if existing is None:
            raise ToolExecutionError(f"Task with ID {task.task_id} not found")
        status = task.new_status or existing["status"]
        priority = task.new_priority or existing["priority"]
        description = (
            task.description
            if task.description is not None
            else existing["description"]
        )
        due_date = (
            _due_date(task.due_date)
            if task.due_date is not None
            else existing["due_date"]
        )
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET description = ?, priority = ?, due_date = ?, status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
                """,
                (description, priority, due_date, status, task.task_id),
            )
        return {
            "status": "TASK_UPDATED",
            "task_id": task.task_id,
            "owner_id": owner_id,
            "new_status": status,
            "new_priority": priority,
        }

    @trace_tool
    def delete_task(
        self, task: DeleteTask, owner_id: int, reason: str | None = None
    ) -> dict[str, Any]:
        delete_reason = (reason if reason is not None else task.reason).strip()
        if not delete_reason:
            raise ToolExecutionError("Reason is required to delete a task")
        if self.get_task(task.task_id) is None:
            raise ToolExecutionError(f"Task with ID {task.task_id} not found")
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                UPDATE tasks
                SET is_deleted = 1,
                    delete_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = ?
                """,
                (delete_reason, task.task_id),
            )
        return {
            "status": "TASK_DELETED",
            "task_id": task.task_id,
            "owner_id": owner_id,
            "is_deleted": True,
            "reason": delete_reason,
        }


def run_gemini_demo() -> None:
    client = get_gemini_client()
    user_prompt = """
Register Vikram Nair (vikram.nair@fintech.in) based in Noida.
Add two tasks for him:
- Complete PCI-DSS compliance audit (High priority, deadline 30th Nov 2026)
- Update API rate-limiting documentation (Low priority)
"""
    response = client.models.generate_content(
        model=settings.gemini.model_name,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a database orchestration agent. Extract structured entities matching the Pydantic schemas. "
                "Save the user first to retrieve their user_id, then save all their tasks."
            ),
            tools=[save_user_to_db, save_task_to_db],
            temperature=0.0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=False, maximum_remote_calls=5
            ),
        ),
    )
    print("\n=== FINAL RESPONSE ===")
    print(response.text)


if __name__ == "__main__":
    run_gemini_demo()
