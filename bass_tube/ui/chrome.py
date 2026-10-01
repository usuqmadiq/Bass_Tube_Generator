"""Шапка, переключатель языка и прокручиваемая колонка формы."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from bass_tube.ui.i18n import LANG_EN, LANG_RU, t
from bass_tube.ui.theme import ACCENT, ACCENT_TEXT, BORDER, HEADER, MUTED, SURFACE


class SegmentedControl(tk.Frame):
    """Горизонтальные сегменты: выбранный залит медью.

    Подходит для цели «нота / длина» и похожих пар, где обычный
    радиокнопочный индикатор ttk на тёмной теме не читается.
    """

    def __init__(
        self,
        master: tk.Misc,
        items: list[tuple[str, str]],
        current: str,
        on_pick,
        *,
        bg: str,
    ) -> None:
        """Собирает сегменты по списку (значение, ключ подписи).

        Принимает родителя, пары значение-ключ, текущее значение, колбэк
        и цвет фона вокруг рамки. Ничего не возвращает.
        """
        super().__init__(master, bg=bg, highlightthickness=0)
        self._on_pick = on_pick
        self._bg = bg
        self._items = list(items)
        self._buttons: dict[str, tk.Label] = {}
        self._current = current if current in {item[0] for item in items} else items[0][0]
        shell = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        shell.pack()
        inner = tk.Frame(shell, bg=bg)
        inner.pack()
        for index, (value, key) in enumerate(self._items):
            label = tk.Label(
                inner,
                text=t(key),
                padx=12,
                pady=4,
                cursor="hand2",
                font=("Segoe UI Semibold", 9),
            )
            label.grid(row=0, column=index)
            label.bind("<Button-1>", lambda _event, code=value: self._pick(code))
            self._buttons[value] = label
        self._paint()

    def set_value(self, value: str) -> None:
        """Подсвечивает сегмент, не вызывая колбэк.

        Принимает значение из списка. Неизвестное игнорирует.
        Ничего не возвращает.
        """
        if value not in self._buttons:
            return
        self._current = value
        self._paint()

    def apply_language(self) -> None:
        """Обновляет подписи сегментов под текущий язык.

        Ничего не принимает и не возвращает.
        """
        for value, key in self._items:
            self._buttons[value].configure(text=t(key))

    def _pick(self, value: str) -> None:
        """Нажатие сегмента: подсветка и колбэк.

        Принимает значение. Повторный щелчок по выбранному ничего не делает.
        Ничего не возвращает.
        """
        if value == self._current:
            return
        self._current = value
        self._paint()
        self._on_pick(value)

    def _paint(self) -> None:
        """Красит активный сегмент медью, остальные — фоном карточки.

        Ничего не принимает и не возвращает.
        """
        for value, label in self._buttons.items():
            if value == self._current:
                label.configure(bg=ACCENT, fg=ACCENT_TEXT)
            else:
                label.configure(bg=self._bg, fg=MUTED)


class LanguageToggle(tk.Frame):
    """Сегмент RU | EN в шапке. Активный язык залит медью."""

    def __init__(self, master: tk.Misc, current: str, on_pick) -> None:
        """Собирает две кнопки и вешает выбор языка.

        Принимает родителя, текущий код языка и колбэк, который получит
        «ru» или «en». Ничего не возвращает.
        """
        super().__init__(master, bg=HEADER, highlightthickness=0)
        self._on_pick = on_pick
        self._buttons: dict[str, tk.Label] = {}
        self._current = current if current in (LANG_RU, LANG_EN) else LANG_RU
        shell = tk.Frame(self, bg=BORDER, padx=1, pady=1)
        shell.pack()
        inner = tk.Frame(shell, bg=HEADER)
        inner.pack()
        for index, lang in enumerate((LANG_RU, LANG_EN)):
            label = tk.Label(
                inner,
                text=t(f"lang.{lang}"),
                width=4,
                pady=4,
                cursor="hand2",
                font=("Segoe UI Semibold", 9),
            )
            label.grid(row=0, column=index)
            label.bind("<Button-1>", lambda _event, code=lang: self._pick(code))
            self._buttons[lang] = label
        self._paint()

    def set_language(self, lang: str) -> None:
        """Подсвечивает выбранный язык, не вызывая колбэк.

        Принимает «ru» или «en». Нужно, когда язык поставили снаружи.
        Ничего не возвращает.
        """
        if lang not in self._buttons:
            return
        self._current = lang
        self._paint()

    def _pick(self, lang: str) -> None:
        """Нажатие сегмента: подсветка и колбэк.

        Принимает код языка. Повторный щелчок по уже выбранному ничего
        не делает. Ничего не возвращает.
        """
        if lang == self._current:
            return
        self._current = lang
        self._paint()
        self._on_pick(lang)

    def _paint(self) -> None:
        """Красит активный сегмент медью, второй — в цвет шапки.

        Ничего не принимает и не возвращает.
        """
        for lang, label in self._buttons.items():
            if lang == self._current:
                label.configure(bg=ACCENT, fg=ACCENT_TEXT)
            else:
                label.configure(bg=HEADER, fg=MUTED)


class TubeMark(tk.Canvas):
    """Значок сечения трубы: два кольца меди на шапке."""

    def __init__(self, master: tk.Misc, size: int = 36) -> None:
        """Рисует круглое сечение.

        Принимает родителя и размер стороны в пикселях. Ничего не возвращает.
        """
        super().__init__(
            master,
            width=size,
            height=size,
            bg=HEADER,
            highlightthickness=0,
            bd=0,
        )
        pad = 3
        self.create_oval(pad, pad, size - pad, size - pad, outline=ACCENT, width=2.5)
        inner = size * 0.28
        self.create_oval(
            size / 2 - inner,
            size / 2 - inner,
            size / 2 + inner,
            size / 2 + inner,
            outline=ACCENT,
            width=1.6,
        )


class ScrollArea(ttk.Frame):
    """Колонка с вертикальной прокруткой под карточки формы."""

    def __init__(self, master: tk.Misc) -> None:
        """Создаёт холст и внутренний фрейм.

        Принимает родителя. Колёсико крутит список, пока курсор над ним.
        Ничего не возвращает.
        """
        super().__init__(master, style="Surface.TFrame")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            self, highlightthickness=0, bg=SURFACE, width=380, bd=0
        )
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        self.inner = ttk.Frame(self.canvas, style="Surface.TFrame")
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._fit_scroll)
        self.canvas.bind("<Configure>", self._fit_width)

    def bind_descendants(self) -> None:
        """Вешает колёсико на форму и все её поля.

        Ничего не принимает. Пока курсор над формой, колёсико её листает,
        в том числе над списками и счётчиками — их значения оно не меняет.
        Уход курсора снимает эту привязку, и колёсико над моделью меняет масштаб.
        Ничего не возвращает.
        """
        self._bind_wheel_target(self)

    def _bind_wheel_target(self, widget: tk.Misc) -> None:
        """Подписывает виджет и его детей на вход и уход курсора.

        Принимает виджет. Вход включает прокрутку, уход её снимает.
        Ничего не возвращает.
        """
        widget.bind("<Enter>", self._bind_wheel, add="+")
        widget.bind("<Leave>", self._unbind_wheel, add="+")
        if isinstance(widget, (ttk.Combobox, ttk.Spinbox)):
            widget.bind("<MouseWheel>", self._wheel_instead_of_value)
        for child in widget.winfo_children():
            self._bind_wheel_target(child)

    def _fit_scroll(self, _event: tk.Event) -> None:
        """Растягивает область прокрутки по содержимому.

        Принимает событие Configure. Ничего не возвращает.
        """
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _fit_width(self, event: tk.Event) -> None:
        """Держит форму на ширине видимой колонки.

        Принимает событие холста. Ничего не возвращает.
        """
        self.canvas.itemconfigure(self._window, width=event.width)

    def _bind_wheel(self, _event: tk.Event) -> None:
        """Включает прокрутку колёсиком, пока курсор над формой.

        Принимает событие входа. Ничего не возвращает.
        """
        self.canvas.bind_all("<MouseWheel>", self._wheel)

    def _unbind_wheel(self, _event: tk.Event) -> None:
        """Выключает прокрутку формы, чтобы колёсико досталось модели.

        Принимает событие ухода. Ничего не возвращает.
        """
        self.canvas.unbind_all("<MouseWheel>")

    def _wheel(self, event: tk.Event) -> None:
        """Листает форму на один шаг колёсика.

        Принимает событие. На Windows величина шага сидит в delta.
        Ничего не возвращает.
        """
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _wheel_instead_of_value(self, event: tk.Event) -> str:
        """Листает форму вместо смены значения в списке или счётчике.

        Принимает событие колёсика над списком или счётчиком. Без этого
        колёсико при прокрутке формы молча меняло бы выбранное значение.
        Возвращает «break», чтобы список не получил колёсико.
        """
        self._wheel(event)
        return "break"
