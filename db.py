"""Слой доступа к базе данных SQLite3."""

import os
import sqlite3
import threading
from typing import List, Optional, Sequence

from models import (
    ACTIVE_STATUSES,
    STATUS_OVERDUE,
    STATUS_PENDING,
    Reminder,
    format_db_dt,
)

# Путь к файлу базы данных по умолчанию (рядом с исходным кодом)
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "reminders.db"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    description     TEXT    NOT NULL DEFAULT '',
    due_at          TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'Ожидает',
    notified        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL,
    repeat_interval TEXT,
    repeat_end      TEXT
);

CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders (due_at);
CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders (status);
"""


class Database:
    """Обёртка над соединением SQLite3 с методами для напоминаний."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.create_tables()

    # --- служебные методы -------------------------------------------------

    def create_tables(self) -> None:
        """Создаёт таблицы и индексы, если их ещё нет."""
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        self._migrate()

    def _migrate(self) -> None:
        """Добавляет новые колонки в уже существующую таблицу напоминаний."""
        with self._lock:
            existing = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(reminders)")
            }
            if "repeat_interval" not in existing:
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN repeat_interval TEXT"
                )
            if "repeat_end" not in existing:
                self._conn.execute(
                    "ALTER TABLE reminders ADD COLUMN repeat_end TEXT"
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _write(self, sql: str, params: Sequence = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def _read(self, sql: str, params: Sequence = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # --- CRUD -------------------------------------------------------------

    def add_reminder(
        self,
        title: str,
        description: str,
        due_at: str,
        status: str = STATUS_PENDING,
        created_at: Optional[str] = None,
        repeat_interval: Optional[str] = None,
        repeat_end: Optional[str] = None,
    ) -> int:
        """Добавляет напоминание и возвращает его id."""
        from datetime import datetime

        created_at = created_at or format_db_dt(datetime.now())
        cursor = self._write(
            """
            INSERT INTO reminders
                (title, description, due_at, status, notified, created_at,
                 repeat_interval, repeat_end)
            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
            """,
            (
                title,
                description,
                due_at,
                status,
                created_at,
                repeat_interval,
                repeat_end,
            ),
        )
        return int(cursor.lastrowid)

    def delete_reminder(self, reminder_id: int) -> bool:
        """Удаляет напоминание. Возвращает True, если запись была найдена."""
        cursor = self._write("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        return cursor.rowcount > 0

    def update_status(self, reminder_id: int, status: str) -> bool:
        """Меняет статус напоминания."""
        cursor = self._write(
            "UPDATE reminders SET status = ? WHERE id = ?", (status, reminder_id)
        )
        return cursor.rowcount > 0

    def mark_notified(self, reminder_id: int) -> bool:
        """Помечает, что уведомление по напоминанию уже показано."""
        cursor = self._write(
            "UPDATE reminders SET notified = 1 WHERE id = ?", (reminder_id,)
        )
        return cursor.rowcount > 0

    def reschedule(
        self, reminder_id: int, due_at: str, status: str = STATUS_PENDING
    ) -> bool:
        """Переносит время срабатывания и сбрасывает флаг уведомления."""
        cursor = self._write(
            "UPDATE reminders SET due_at = ?, status = ?, notified = 0 WHERE id = ?",
            (due_at, status, reminder_id),
        )
        return cursor.rowcount > 0

    def get_reminder(self, reminder_id: int) -> Optional[Reminder]:
        rows = self._read("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        return Reminder.from_row(rows[0]) if rows else None

    def get_reminders(self, status: Optional[str] = None) -> List[Reminder]:
        """Возвращает напоминания (опционально — только с указанным статусом)."""
        if status:
            rows = self._read(
                "SELECT * FROM reminders WHERE status = ? ORDER BY due_at ASC",
                (status,),
            )
        else:
            rows = self._read("SELECT * FROM reminders ORDER BY due_at ASC")
        return [Reminder.from_row(row) for row in rows]

    def get_unnotified_due(self, now: str) -> List[Reminder]:
        """Напоминания, время которых наступило, но уведомление ещё не показано."""
        placeholders = ", ".join("?" for _ in ACTIVE_STATUSES)
        rows = self._read(
            f"""
            SELECT * FROM reminders
            WHERE notified = 0
              AND due_at <= ?
              AND status IN ({placeholders})
            ORDER BY due_at ASC
            """,
            (now, *ACTIVE_STATUSES),
        )
        return [Reminder.from_row(row) for row in rows]

    def mark_overdue(self, now: str) -> int:
        """Переводит просроченные напоминания в статус 'Просрочено'."""
        cursor = self._write(
            "UPDATE reminders SET status = ? WHERE status = ? AND due_at < ?",
            (STATUS_OVERDUE, STATUS_PENDING, now),
        )
        return cursor.rowcount
