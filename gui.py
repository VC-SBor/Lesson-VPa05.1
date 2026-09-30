"""Графический интерфейс приложения-напоминалки (tkinter)."""

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import List, Optional

from models import (
    ALL_STATUSES,
    INPUT_DATE_FORMAT,
    INPUT_DT_FORMAT,
    LABEL_TO_REPEAT,
    REPEAT_LABELS,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_OVERDUE,
    STATUS_PENDING,
    parse_input_date,
    parse_input_dt,
)
from notifier import Notifier
from reminders import ReminderService, ValidationError

try:  # DateEntry из tkcalendar (опциональная зависимость)
    from tkcalendar import DateEntry
except ImportError:  # если библиотека не установлена — используем обычное поле
    DateEntry = None

# Период проверки сработавших напоминаний
CHECK_INTERVAL_MS = 5_000

FILTER_ALL = "Все"

# Теги раскраски строк таблицы: статус -> имя тега
STATUS_TAG = {
    STATUS_OVERDUE: "overdue",
    STATUS_DONE: "done",
    STATUS_CANCELLED: "cancelled",
}


class AddReminderDialog(tk.Toplevel):
    """Диалог создания нового напоминания."""

    def __init__(self, master: tk.Misc, service: ReminderService) -> None:
        super().__init__(master)
        self.service = service
        self.result: Optional[int] = None

        self.title("Новое напоминание")
        self.transient(master)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._build()
        self.grab_set()
        self.title_entry.focus_set()

    # --- построение интерфейса -------------------------------------------

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Заголовок:").grid(row=0, column=0, sticky="nw", pady=4)
        self.title_entry = ttk.Entry(frame, width=44)
        self.title_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Описание:").grid(row=1, column=0, sticky="nw", pady=4)
        self.desc_text = tk.Text(frame, width=44, height=4, wrap="word")
        self.desc_text.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Дата (ДД.ММ.ГГГГ):").grid(
            row=2, column=0, sticky="w", pady=4
        )
        default_due = datetime.now() + timedelta(minutes=5)
        self.date_var = tk.StringVar(value=default_due.strftime("%d.%m.%Y"))
        ttk.Entry(frame, textvariable=self.date_var, width=16).grid(
            row=2, column=1, sticky="w", pady=4
        )

        ttk.Label(frame, text="Время (ЧЧ:ММ):").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self.time_var = tk.StringVar(value=default_due.strftime("%H:%M"))
        ttk.Entry(frame, textvariable=self.time_var, width=16).grid(
            row=3, column=1, sticky="w", pady=4
        )

        ttk.Label(frame, text="Повтор:").grid(row=4, column=0, sticky="w", pady=4)
        self.repeat_var = tk.StringVar(value=REPEAT_LABELS[None])
        self.repeat_box = ttk.Combobox(
            frame,
            textvariable=self.repeat_var,
            values=list(REPEAT_LABELS.values()),
            state="readonly",
            width=16,
        )
        self.repeat_box.grid(row=4, column=1, sticky="w", pady=4)
        self.repeat_box.bind(
            "<<ComboboxSelected>>", lambda _event: self._sync_repeat_state()
        )

        ttk.Label(frame, text="Дата окончания:").grid(
            row=5, column=0, sticky="w", pady=4
        )
        self._repeat_end_var = tk.StringVar()
        if DateEntry is not None:
            self.repeat_end_entry = DateEntry(
                frame, width=14, date_pattern="dd.mm.yyyy"
            )
        else:
            self.repeat_end_entry = ttk.Entry(
                frame, textvariable=self._repeat_end_var, width=16
            )
        self.repeat_end_entry.grid(row=5, column=1, sticky="w", pady=4)

        ttk.Label(
            frame,
            text="Пусто — повтор без ограничения по дате",
            foreground="#7f8c8d",
        ).grid(row=6, column=1, sticky="w")

        quick = ttk.Frame(frame)
        quick.grid(row=7, column=1, sticky="w", pady=(6, 8))
        for label, delta in (
            ("+5 минут", timedelta(minutes=5)),
            ("+1 час", timedelta(hours=1)),
            ("+1 день", timedelta(days=1)),
        ):
            ttk.Button(
                quick, text=label, width=10, command=lambda d=delta: self._set_offset(d)
            ).pack(side="left", padx=(0, 6))

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e", pady=(6, 0))
        ttk.Button(buttons, text="Сохранить", command=self._on_save).pack(
            side="right", padx=(6, 0)
        )
        ttk.Button(buttons, text="Отмена", command=self._on_cancel).pack(side="right")

        self._sync_repeat_state()

    # --- управление повтором ---------------------------------------------

    def _sync_repeat_state(self) -> None:
        """Включает поле даты окончания только при выбранном повторе."""
        enabled = LABEL_TO_REPEAT.get(self.repeat_var.get()) is not None
        self.repeat_end_entry.configure(state="normal" if enabled else "disabled")

    def _read_repeat_end(self) -> Optional[date]:
        """Читает дату окончания повтора (None, если поле пустое)."""
        if DateEntry is not None:
            return self.repeat_end_entry.get_date()
        raw = self._repeat_end_var.get().strip()
        if not raw:
            return None
        return parse_input_date(raw)

    # --- обработчики ------------------------------------------------------

    def _set_offset(self, delta: timedelta) -> None:
        moment = datetime.now() + delta
        self.date_var.set(moment.strftime("%d.%m.%Y"))
        self.time_var.set(moment.strftime("%H:%M"))

    def _on_save(self) -> None:
        title = self.title_entry.get().strip()
        description = self.desc_text.get("1.0", "end").strip()
        raw = f"{self.date_var.get().strip()} {self.time_var.get().strip()}"

        try:
            due_at = parse_input_dt(raw)
        except ValueError:
            messagebox.showerror(
                "Ошибка",
                "Неверная дата или время.\nОжидаемый формат: ДД.ММ.ГГГГ и ЧЧ:ММ",
                parent=self,
            )
            return

        repeat_interval = LABEL_TO_REPEAT.get(self.repeat_var.get())
        repeat_end: Optional[date] = None
        if repeat_interval is not None:
            try:
                repeat_end = self._read_repeat_end()
            except ValueError:
                messagebox.showerror(
                    "Ошибка",
                    "Неверная дата окончания.\n"
                    f"Ожидаемый формат: {INPUT_DATE_FORMAT}",
                    parent=self,
                )
                return

        try:
            self.result = self.service.add_reminder(
                title, description, due_at, repeat_interval, repeat_end
            )
        except ValidationError as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)
            return

        self.grab_release()
        self.destroy()

    def _on_cancel(self) -> None:
        self.grab_release()
        self.destroy()


class ReminderApp(tk.Tk):
    """Главное окно приложения."""

    COLUMNS = (
        ("id", "ID", 50, "center"),
        ("title", "Заголовок", 170, "w"),
        ("description", "Описание", 230, "w"),
        ("due", "Сработает", 140, "center"),
        ("repeat", "Повтор", 110, "center"),
        ("status", "Статус", 120, "center"),
    )

    def __init__(self, service: ReminderService) -> None:
        super().__init__()
        self.service = service
        self.notifier = Notifier(root=self)

        self.title("Напоминалка")
        self.geometry("860x520")
        self.minsize(720, 420)

        self._build_ui()
        self.refresh()
        self.after(CHECK_INTERVAL_MS, self._tick)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # --- построение интерфейса -------------------------------------------

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.pack(fill="x")

        ttk.Label(toolbar, text="Фильтр по статусу:").pack(side="left")
        self.filter_var = tk.StringVar(value=FILTER_ALL)
        filter_box = ttk.Combobox(
            toolbar,
            textvariable=self.filter_var,
            values=(FILTER_ALL, *ALL_STATUSES),
            state="readonly",
            width=16,
        )
        filter_box.pack(side="left", padx=(6, 0))
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh())

        ttk.Button(toolbar, text="Обновить", command=self.refresh).pack(
            side="right"
        )
        ttk.Button(toolbar, text="Удалить", command=self._on_delete).pack(
            side="right", padx=(0, 6)
        )

        table_frame = ttk.Frame(self, padding=(10, 0))
        table_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            table_frame,
            columns=[key for key, *_ in self.COLUMNS],
            show="headings",
            selectmode="extended",
        )
        for key, heading, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=heading)
            self.tree.column(key, width=width, anchor=anchor)
        # Раскрашиваем фон всей строки в зависимости от статуса
        self.tree.tag_configure("overdue", background="#ffcccc", foreground="black")
        self.tree.tag_configure("done", background="#ccffcc", foreground="black")
        self.tree.tag_configure("cancelled", background="#e0e0e0", foreground="black")

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda _event: self._on_mark_done())

        actions = ttk.Frame(self, padding=(10, 8))
        actions.pack(fill="x")
        ttk.Button(actions, text="Добавить", command=self._on_add).pack(side="left")
        ttk.Button(actions, text="Готово", command=self._on_mark_done).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(actions, text="Отменить", command=self._on_mark_cancelled).pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(actions, text="Вернуть в ожидание", command=self._on_mark_pending).pack(
            side="left", padx=(6, 0)
        )

        self.status_var = tk.StringVar()
        status_bar = ttk.Label(
            self, textvariable=self.status_var, padding=(10, 4), anchor="w"
        )
        status_bar.pack(fill="x", side="bottom")

    # --- данные -----------------------------------------------------------

    def _selected_ids(self) -> List[int]:
        return [int(iid) for iid in self.tree.selection()]

    def refresh(self) -> None:
        """Перечитывает напоминания из БД и обновляет таблицу."""
        selected = set(self._selected_ids())

        self.tree.delete(*self.tree.get_children())
        status = self.filter_var.get()
        reminders = self.service.list_reminders(
            None if status == FILTER_ALL else status
        )
        for reminder in reminders:
            item_id = self.tree.insert(
                "",
                "end",
                iid=str(reminder.id),
                values=(
                    reminder.id,
                    reminder.title,
                    reminder.description,
                    reminder.due_display,
                    reminder.repeat_label,
                    reminder.status,
                ),
            )
            status_tag = STATUS_TAG.get(reminder.status)
            if status_tag is not None:
                self.tree.item(item_id, tags=(status_tag,))

        for reminder_id in selected:
            iid = str(reminder_id)
            if self.tree.exists(iid):
                self.tree.selection_add(iid)

        self._update_status_bar()

    def _update_status_bar(self) -> None:
        counts = {status: 0 for status in ALL_STATUSES}
        for reminder in self.service.list_reminders():
            counts[reminder.status] = counts.get(reminder.status, 0) + 1

        summary = "  |  ".join(f"{status}: {counts[status]}" for status in ALL_STATUSES)
        self.status_var.set(
            f"{summary}   Уведомления: {self.notifier.backend_name}"
        )

    # --- циклическая проверка --------------------------------------------

    def _tick(self) -> None:
        """Проверяет сработавшие напоминания и обновляет список."""
        try:
            self._process_due_reminders()
            self.service.refresh_overdue()
            self.refresh()
        finally:
            self.after(CHECK_INTERVAL_MS, self._tick)

    def _process_due_reminders(self) -> None:
        for reminder in self.service.pop_due_notifications():
            message = reminder.description.strip() or "Напоминание сработало"
            self.notifier.notify(reminder.title, f"{reminder.due_display}\n{message}")

    # --- действия пользователя -------------------------------------------

    def _on_add(self) -> None:
        dialog = AddReminderDialog(self, self.service)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.refresh()

    def _on_delete(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Удаление", "Выберите напоминание в списке.", parent=self)
            return

        if not messagebox.askyesno(
            "Удаление",
            f"Удалить выбранные напоминания ({len(ids)} шт.)?",
            parent=self,
        ):
            return

        for reminder_id in ids:
            self.service.delete_reminder(reminder_id)
        self.refresh()

    def _apply_status(self, setter, action: str) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo(action, "Выберите напоминание в списке.", parent=self)
            return

        changed = sum(1 for reminder_id in ids if setter(reminder_id))
        self.refresh()
        if changed:
            self.status_var.set(f"{action}: обновлено записей — {changed}")

    def _on_mark_done(self) -> None:
        # Повторяющиеся напоминания переносятся на следующее время, остальные
        # переводятся в статус «Готово».
        self._apply_status(
            self.service.process_completed_recurring, "Отметить как «Готово»"
        )

    def _on_mark_cancelled(self) -> None:
        self._apply_status(self.service.mark_cancelled, "Отметить как «Отменено»")

    def _on_mark_pending(self) -> None:
        self._apply_status(self.service.mark_pending, "Вернуть в «Ожидает»")


def run(service: ReminderService) -> None:
    """Запускает главное окно приложения."""
    app = ReminderApp(service)
    app.mainloop()
