"""Бизнес-логика работы с напоминаниями."""

from datetime import date, datetime
from typing import List, Optional

from db import Database
from models import (
    REPEAT_INTERVALS,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_PENDING,
    Reminder,
    format_db_date,
    format_db_dt,
)


class ValidationError(ValueError):
    """Ошибка проверки данных, введённых пользователем."""


class ReminderService:
    """Операции над напоминаниями поверх слоя базы данных."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def add_reminder(
        self,
        title: str,
        description: str,
        due_at: datetime,
        repeat_interval: Optional[str] = None,
        repeat_end: Optional[date] = None,
    ) -> int:
        """Создаёт новое напоминание со статусом 'Ожидает'.

        Для повторяющегося напоминания в базу пишется одна запись с текущим
        временем срабатывания и выбранным интервалом в поле repeat_interval.
        """
        title = (title or "").strip()
        if not title:
            raise ValidationError("Заголовок не может быть пустым.")
        if not isinstance(due_at, datetime):
            raise ValidationError("Некорректная дата и время срабатывания.")

        if repeat_interval is not None and repeat_interval not in REPEAT_INTERVALS:
            raise ValidationError("Некорректный интервал повтора.")

        if repeat_interval is None:
            # Без повтора дата окончания не имеет смысла
            repeat_end = None
        elif repeat_end is not None:
            if not isinstance(repeat_end, date):
                raise ValidationError("Некорректная дата окончания повтора.")
            if repeat_end < due_at.date():
                raise ValidationError(
                    "Дата окончания повтора не может быть раньше первого срабатывания."
                )

        description = (description or "").strip()
        return self.db.add_reminder(
            title,
            description,
            format_db_dt(due_at),
            repeat_interval=repeat_interval,
            repeat_end=format_db_date(repeat_end) if repeat_end else None,
        )

    def process_completed_recurring(self, reminder_id: int) -> bool:
        """Обрабатывает отметку 'Готово' для напоминания.

        Для повторяющегося напоминания вычисляет следующее время срабатывания
        и переносит его в ту же запись со статусом 'Ожидает'. Если новое время
        выходит за repeat_end (или напоминание не повторяется), ставит 'Готово'.
        """
        reminder = self.db.get_reminder(reminder_id)
        if reminder is None:
            return False

        if not reminder.is_recurring:
            self.db.update_status(reminder_id, STATUS_DONE)
            return True

        next_time = reminder.get_next_trigger_time()
        if next_time is not None and reminder.is_within_repeat_end(next_time):
            self.db.reschedule(
                reminder_id, format_db_dt(next_time), STATUS_PENDING
            )
        else:
            self.db.update_status(reminder_id, STATUS_DONE)
        return True

    def delete_reminder(self, reminder_id: int) -> bool:
        return self.db.delete_reminder(reminder_id)

    def mark_done(self, reminder_id: int) -> bool:
        return self.db.update_status(reminder_id, STATUS_DONE)

    def mark_cancelled(self, reminder_id: int) -> bool:
        return self.db.update_status(reminder_id, STATUS_CANCELLED)

    def mark_pending(self, reminder_id: int) -> bool:
        """Возвращает напоминание в статус 'Ожидает'."""
        return self.db.update_status(reminder_id, STATUS_PENDING)

    def refresh_overdue(self, now: Optional[datetime] = None) -> int:
        """Автоматически помечает просроченные напоминания. Возвращает их число."""
        now = now or datetime.now()
        return self.db.mark_overdue(format_db_dt(now))

    def list_reminders(self, status: Optional[str] = None) -> List[Reminder]:
        """Список напоминаний с фильтром по статусу (None — все)."""
        return self.db.get_reminders(status)

    def pop_due_notifications(self, now: Optional[datetime] = None) -> List[Reminder]:
        """Возвращает сработавшие напоминания и помечает их как уведомлённые."""
        now = now or datetime.now()
        due = self.db.get_unnotified_due(format_db_dt(now))
        for reminder in due:
            self.db.mark_notified(reminder.id)
        return due
