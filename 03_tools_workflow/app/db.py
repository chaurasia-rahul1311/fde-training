import sqlite3
import time
import functools
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from google import genai
from google.genai import types
from app.models import UserContext


DB_PATH = str(Path(__file__).resolve().parents[1] / "task_manager.db")


def init_db():
    """Initialize the database"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                is_authenticated BOOLEAN NOT NULL DEFAULT FALSE
            )
        """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                priority TEXT NOT NULL,
                due_date DATE,
                status TEXT DEFAULT 'PENDING',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                owner_id INTEGER NOT NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                delete_reason TEXT,
                FOREIGN KEY (owner_id) REFERENCES users(user_id)
            )
        """
        )


init_db()


def save_user_to_db(user: UserContext) -> dict:
    """
    Saves or updates a user profile in SQLite using a validated UserSchema object.
    Always call this first to obtain the user_id before creating tasks.
    """
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO users (full_name, role, is_authenticated)
            VALUES (?, ?, ?)
            """,
            (
                user.full_name.strip(),
                user.role,
                int(user.is_authenticated),
            ),
        )
        user_id = cursor.lastrowid
        cursor.execute(
            """
            SELECT user_id, full_name, role, is_authenticated
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return {
            "status": "USER_SAVED",
            "user_id": row[0],
            "full_name": row[1],
            "role": row[2],
            "is_authenticated": bool(row[3]),
        }


def _user_from_row(row: tuple | None) -> UserContext | None:
    if row is None:
        return None
    return UserContext(
        user_id=row[0],
        full_name=row[1],
        role=row[2],
        is_authenticated=bool(row[3]),
    )


def get_user_details(user_id: int) -> UserContext | None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, full_name, role, is_authenticated
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )
        return _user_from_row(cursor.fetchone())


def find_user_by_name(full_name: str) -> UserContext | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, full_name, role, is_authenticated
            FROM users
            WHERE full_name = ?
            """,
            (full_name,),
        )
        return _user_from_row(cursor.fetchone())
