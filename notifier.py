"""Показ уведомлений: системные уведомления Windows 10 или всплывающее окно.

Приложение пытается использовать win10toast, затем plyer, а если ни один из
них не установлен — показывает всплывающее окно поверх всех окон на tkinter.
"""

import threading
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk

APP_NAME = "Напоминалка"

# Через сколько миллисекунд всплывающее окно закроется само
POPUP_TIMEOUT_MS = 60_000

_BACKEND_LABELS = {
    "win10toast": "Системные уведомления Windows (win10toast)",
    "plyer": "Системные уведомления Windows (plyer)",
    "popup": "Всплывающее окно поверх всех окон (tkinter)",
}


def detect_backend() -> str:
    """Определяет доступный способ показа уведомлений."""
    try:
        import win10toast  # noqa: F401

        return "win10toast"
    except Exception:
        pass

    try:
        from plyer import notification  # noqa: F401

        return "plyer"
    except Exception:
        pass

    return "popup"


class Notifier:
    """Отправляет уведомления о сработавших напоминаниях."""

    def __init__(
        self,
        root: Optional[tk.Misc] = None,
        app_name: str = APP_NAME,
        backend: Optional[str] = None,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        self.root = root
        self.app_name = app_name
        self.backend = backend or detect_backend()
        self.on_close = on_close
        self._toaster = None

        if self.backend == "win10toast":
            try:
                from win10toast import ToastNotifier

                self._toaster = ToastNotifier()
            except Exception:
                self.backend = "popup"

    @property
    def backend_name(self) -> str:
        return _BACKEND_LABELS.get(self.backend, self.backend)

    def notify(self, title: str, message: str) -> None:
        """Показывает уведомление, не блокируя интерфейс."""
        if self.backend == "win10toast":
            threading.Thread(
                target=self._notify_win10toast,
                args=(title, message),
                daemon=True,
            ).start()
        elif self.backend == "plyer":
            threading.Thread(
                target=self._notify_plyer, args=(title, message), daemon=True
            ).start()
        else:
            self._schedule_popup(title, message)

    # --- конкретные реализации -------------------------------------------

    def _notify_win10toast(self, title: str, message: str) -> None:
        try:
            self._toaster.show_toast(
                title,
                message,
                duration=10,
                threaded=False,
            )
        except Exception:
            self._schedule_popup(title, message)

    def _notify_plyer(self, title: str, message: str) -> None:
        try:
            from plyer import notification

            notification.notify(
                title=title,
                message=message,
                app_name=self.app_name,
                timeout=10,
            )
        except Exception:
            self._schedule_popup(title, message)

    # --- всплывающее окно tkinter ----------------------------------------

    def _schedule_popup(self, title: str, message: str) -> None:
        """Планирует показ окна в главном потоке tkinter (потокобезопасно)."""
        if self.root is not None:
            try:
                self.root.after(0, lambda: self._show_popup(title, message))
                return
            except Exception:
                pass
        # Нет главного окна — создаём собственное окно в отдельном потоке
        threading.Thread(
            target=self._popup_in_new_root, args=(title, message), daemon=True
        ).start()

    def _popup_in_new_root(self, title: str, message: str) -> None:
        root = tk.Tk()
        root.withdraw()
        self._build_popup(root, title, message)
        root.mainloop()

    def _show_popup(self, title: str, message: str) -> None:
        if self.root is None:
            return
        self._build_popup(self.root, title, message)

    def _build_popup(self, parent: tk.Misc, title: str, message: str) -> None:
        popup = tk.Toplevel(parent)
        popup.title(self.app_name)
        popup.attributes("-topmost", True)
        popup.resizable(False, False)
        popup.configure(padx=0, pady=0)

        container = ttk.Frame(popup, padding=16)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text=title,
            font=("Segoe UI", 12, "bold"),
            wraplength=340,
            justify="left",
        ).pack(anchor="w")

        if message:
            ttk.Label(
                container,
                text=message,
                wraplength=340,
                justify="left",
            ).pack(anchor="w", pady=(8, 0))

        def close() -> None:
            try:
                popup.destroy()
            finally:
                if self.on_close is not None:
                    self.on_close()

        buttons = ttk.Frame(container)
        buttons.pack(anchor="e", pady=(14, 0))
        ttk.Button(buttons, text="Понятно", command=close).pack(side="right")

        popup.protocol("WM_DELETE_WINDOW", close)
        popup.after(POPUP_TIMEOUT_MS, close)

        # Размещаем окно в правом нижнем углу экрана
        popup.update_idletasks()
        width = popup.winfo_reqwidth()
        height = popup.winfo_reqheight()
        screen_w = popup.winfo_screenwidth()
        screen_h = popup.winfo_screenheight()
        popup.geometry(f"+{screen_w - width - 40}+{screen_h - height - 80}")

        popup.lift()
        try:
            popup.bell()
        except Exception:
            pass
