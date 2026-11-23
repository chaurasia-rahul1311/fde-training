from pydantic import BaseModel, Field, field_validator
from typing import Literal
from datetime import datetime
class UserContext(BaseModel):
    user_id: int | None = None
    role: Literal["viewer", "editor", "admin"]
    is_authenticated: bool = True
    full_name: str = ""


class CreateTask(BaseModel):
    title: str = Field(..., description="The title of the task")
    description: str = Field(..., description="The description of the task")
    due_date: datetime = Field(..., description="The due date of the task")
    priority: Literal["low", "medium", "high"] = Field(
        ..., description="The priority of the task"
    )
    status: Literal["pending", "in_progress", "completed"] = Field(
        default="pending", description="The status of the task"
    )

    @field_validator("due_date")
    @classmethod
    def validate_due_date(cls, value: datetime) -> datetime:
        now = datetime.now(value.tzinfo) if value.tzinfo else datetime.now()
        if value < now:
            raise ValueError("Due date must be in the future")
        return value


class ListTasks(BaseModel):
    owner_id: int | None = Field(
        default=None, description="Limit results to this owner"
    )
    priority: Literal["low", "medium", "high"] | None = Field(
        default=None, description="The priority"
    )
    status_filter: Literal["all", "pending", "in_progress", "completed"] = (
        Field(default="all", description="The status filter")
    )
    due_date: datetime | None = Field(default=None, description="The due date")
    description: str | None = None


class UpdateTask(BaseModel):
    task_id: str = Field(
        description="The unique ID of the task (e.g., 'TSK-101')."
    )
    new_status: (
        Literal["open", "in_progress", "completed", "cancelled"] | None
    ) = None
    new_priority: Literal["low", "medium", "high"] | None = None
    description: str | None = None
    due_date: datetime | None = Field(default=None, description="The due date")


class DeleteTask(BaseModel):
    task_id: str = Field(
        description="The unique ID of the task to permanently delete."
    )
    reason: str = Field(
        description="Brief reason why the user wants to delete this task."
    )


class AssistantActionPlan(BaseModel):
    reasoning: str = Field(
        description="Step by step analysis of user intend and extracted fields from the user request"
    )
    tool_name: Literal[
        "create_task", "list_tasks", "update_task", "delete_task", "none"
    ] = Field(default="none", description="The tool to use")
    create_args: CreateTask | None = None
    list_args: ListTasks | None = None
    update_args: UpdateTask | None = None
    delete_args: DeleteTask | None = None
    clarification_message: str | None = Field(
        default=None,
        description="The message to user if tool not selected or any critical information is missing",
    )
