"""Модели данных и константы приложения-напоминалки."""

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional

# Метки статуса напоминания
STATUS_PENDING = "Ожидает"
STATUS_DONE = "Готово"
STATUS_OVERDUE = "Просрочено"
STATUS_CANCELLED = "Отменено"

# Все допустимые статусы (порядок используется в фильтре интерфейса)
ALL_STATUSES = (STATUS_PENDING, STATUS_OVERDUE, STATUS_DONE, STATUS_CANCELLED)

# Статусы, для которых напоминание ещё может сработать
ACTIVE_STATUSES = (STATUS_PENDING, STATUS_OVERDUE)

# Интервалы повтора напоминания (None — без повтора)
REPEAT_DAILY = "daily"
REPEAT_WEEKLY = "weekly"
REPEAT_MONTHLY = "monthly"
REPEAT_INTERVALS = (REPEAT_DAILY, REPEAT_WEEKLY, REPEAT_MONTHLY)

# Подписи интервалов для интерфейса
REPEAT_LABELS = {
    None: "Нет",
    REPEAT_DAILY: "Ежедневно",
    REPEAT_WEEKLY: "Еженедельно",
    REPEAT_MONTHLY: "Ежемесячно",
}
# Обратное соответствие: подпись -> значение интервала
LABEL_TO_REPEAT = {label: value for value, label in REPEAT_LABELS.items()}

# Формат хранения даты и времени в базе данных
DB_DT_FORMAT = "%Y-%m-%d %H:%M:%S"

# Формат хранения даты в базе данных
DB_DATE_FORMAT = "%Y-%m-%d"

# Формат ввода/отображения даты и времени для пользователя
INPUT_DT_FORMAT = "%d.%m.%Y %H:%M"

# Формат ввода/отображения даты для пользователя
INPUT_DATE_FORMAT = "%d.%m.%Y"


def format_db_dt(moment: datetime) -> str:
    """Преобразует datetime в строку для хранения в БД."""
    return moment.strftime(DB_DT_FORMAT)


def parse_db_dt(value: str) -> datetime:
    """Разбирает строку из БД в datetime."""
    return datetime.strptime(value, DB_DT_FORMAT)


def parse_input_dt(value: str) -> datetime:
    """Разбирает введённую пользователем строку вида 'ДД.ММ.ГГГГ ЧЧ:ММ'."""
    return datetime.strptime(value.strip(), INPUT_DT_FORMAT)


def format_db_date(moment: date) -> str:
    """Преобразует дату в строку для хранения в БД."""
    return moment.strftime(DB_DATE_FORMAT)


def parse_db_date(value: str) -> date:
    """Разбирает строку из БД в дату."""
    return datetime.strptime(value, DB_DATE_FORMAT).date()


def parse_input_date(value: str) -> date:
    """Разбирает введённую пользователем строку вида 'ДД.ММ.ГГГГ'."""
    return datetime.strptime(value.strip(), INPUT_DATE_FORMAT).date()


def add_months(moment: datetime, months: int) -> datetime:
    """Прибавляет к дате целое число месяцев (день ограничивается длиной месяца)."""
    month_index = moment.month - 1 + months
    year = moment.year + month_index // 12
    month = month_index % 12 + 1
    day = min(moment.day, calendar.monthrange(year, month)[1])
    return moment.replace(year=year, month=month, day=day)


@dataclass
class Reminder:
    """Одно напоминание."""

    id: int
    title: str
    description: str
    due_at: str
    status: str
    notified: bool
    created_at: str
    repeat_interval: Optional[str] = None
    repeat_end: Optional[date] = None

    @property
    def due_datetime(self) -> datetime:
        return parse_db_dt(self.due_at)

    @property
    def due_display(self) -> str:
        """Дата и время срабатывания в пользовательском формате."""
        return self.due_datetime.strftime(INPUT_DT_FORMAT)

    @property
    def created_display(self) -> str:
        return parse_db_dt(self.created_at).strftime(INPUT_DT_FORMAT)

    @property
    def is_recurring(self) -> bool:
        """Является ли напоминание повторяющимся."""
        return self.repeat_interval in REPEAT_INTERVALS

    @property
    def repeat_label(self) -> str:
        """Человекочитаемая подпись интервала повтора."""
        return REPEAT_LABELS.get(self.repeat_interval, REPEAT_LABELS[None])

    @property
    def repeat_end_display(self) -> str:
        """Дата окончания повтора в пользовательском формате."""
        return self.repeat_end.strftime(INPUT_DATE_FORMAT) if self.repeat_end else ""

    def get_next_trigger_time(
        self, from_time: Optional[datetime] = None
    ) -> Optional[datetime]:
        """Вычисляет следующее время срабатывания на основе текущего.

        Возвращает None, если напоминание не повторяется.
        """
        if not self.is_recurring:
            return None

        base = from_time or self.due_datetime
        if self.repeat_interval == REPEAT_DAILY:
            return base + timedelta(days=1)
        if self.repeat_interval == REPEAT_WEEKLY:
            return base + timedelta(days=7)
        if self.repeat_interval == REPEAT_MONTHLY:
            return add_months(base, 1)
        return None

    def is_within_repeat_end(self, moment: datetime) -> bool:
        """Проверяет, не выходит ли момент за дату окончания повтора."""
        if self.repeat_end is None:
            return True
        return moment.date() <= self.repeat_end

    @classmethod
    def from_row(cls, row: Any) -> "Reminder":
        """Создаёт напоминание из строки результата SQL-запроса."""
        raw_repeat_end = row["repeat_end"]
        return cls(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            due_at=row["due_at"],
            status=row["status"],
            notified=bool(row["notified"]),
            created_at=row["created_at"],
            repeat_interval=row["repeat_interval"],
            repeat_end=parse_db_date(raw_repeat_end) if raw_repeat_end else None,
        )
