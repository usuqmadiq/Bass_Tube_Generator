"""Тёмная тема окна: уголь, медь, без системного серого clam.

Цвета совпадают с предпросмотром: фон почти чёрный, деталь — тёплая медь.
На Windows после создания окна шапка окна тоже красится в тёмную.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# Окно и колонки.
BG = "#10151c"
SURFACE = "#151c25"
HEADER = "#121820"
CARD = "#1b2430"
INPUT = "#10161e"
BORDER = "#2c3646"
# Текст и приглушённые подсказки.
TEXT = "#e8eef6"
MUTED = "#8b97a8"
# Медь — акцент кнопок и заголовков групп, как окраска модели.
ACCENT = "#e0a36f"
ACCENT_HOVER = "#edb584"
ACCENT_TEXT = "#1a120c"
DANGER = "#d97a7a"
# Предпросмотр VTK: те же уголь и медь, что у карточек.
PREVIEW_BG = (0.067, 0.082, 0.106)
PREVIEW_MODEL = (0.87, 0.64, 0.43)
PREVIEW_EMPTY_BG = "#151c25"
PREVIEW_EMPTY_FG = "#8b97a8"


def apply_theme(root: tk.Tk) -> ttk.Style:
    """Красит ttk-виджеты в тёмную тему.

    Принимает корень окна. Ставит clam, плоские карточки, медную кнопку
    построения и тёмные поля ввода. Возвращает Style, чтобы окно могло
    донастроить отдельные имена.
    """
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=BG)
    font_ui = ("Segoe UI", 10)
    font_title = ("Segoe UI Semibold", 16)
    font_card = ("Segoe UI Semibold", 9)
    font_hint = ("Segoe UI", 8)
    font_button = ("Segoe UI Semibold", 10)

    style.configure(".", background=BG, foreground=TEXT, font=font_ui)
    style.configure("TFrame", background=BG)
    style.configure("Shell.TFrame", background=BG)
    style.configure("Surface.TFrame", background=SURFACE)
    style.configure("Header.TFrame", background=HEADER)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("HeaderTitle.TLabel", background=HEADER, foreground=TEXT, font=font_title)
    style.configure("HeaderSub.TLabel", background=HEADER, foreground=MUTED, font=("Segoe UI", 9))
    style.configure("CardTitle.TLabel", background=CARD, foreground=ACCENT, font=font_card)
    style.configure("Field.TLabel", background=CARD, foreground=TEXT)
    style.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=font_hint)
    style.configure("Caption.TLabel", background=CARD, foreground=MUTED)
    style.configure("Status.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
    style.configure("PreviewHint.TLabel", background=SURFACE, foreground=MUTED, font=font_hint)

    style.configure("TSeparator", background=BORDER)
    style.configure("Header.TSeparator", background=ACCENT)

    style.configure(
        "TButton",
        background=CARD,
        foreground=TEXT,
        padding=(14, 8),
        font=font_button,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", BORDER), ("disabled", SURFACE)],
        foreground=[("disabled", MUTED)],
    )
    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground=ACCENT_TEXT,
        padding=(16, 9),
        font=font_button,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Accent.TButton",
        background=[("active", ACCENT_HOVER), ("disabled", BORDER)],
        foreground=[("disabled", MUTED)],
    )
    style.configure(
        "Ghost.TButton",
        background=CARD,
        foreground=TEXT,
        padding=(16, 9),
        font=font_button,
        borderwidth=1,
        relief="flat",
    )
    style.map(
        "Ghost.TButton",
        background=[("active", BORDER), ("disabled", SURFACE)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("disabled", BORDER)],
    )

    style.configure(
        "TRadiobutton",
        background=CARD,
        foreground=TEXT,
        font=font_ui,
        indicatorcolor=INPUT,
        padding=2,
    )
    style.map(
        "TRadiobutton",
        background=[("active", CARD), ("selected", CARD)],
        foreground=[("disabled", MUTED)],
        indicatorcolor=[("selected", ACCENT), ("!selected", BORDER)],
    )

    field = dict(
        fieldbackground=INPUT,
        foreground=TEXT,
        background=CARD,
        insertcolor=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=5,
        relief="flat",
        arrowcolor=TEXT,
    )
    style.configure("TEntry", **field)
    style.map(
        "TEntry",
        fieldbackground=[("disabled", SURFACE), ("focus", INPUT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
    )
    style.configure("TCombobox", **field)
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", INPUT), ("disabled", SURFACE), ("focus", INPUT)],
        foreground=[("readonly", TEXT), ("disabled", MUTED)],
        selectbackground=[("readonly", INPUT)],
        selectforeground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT)],
        lightcolor=[("focus", ACCENT)],
        darkcolor=[("focus", ACCENT)],
        arrowcolor=[("disabled", MUTED)],
    )
    style.configure("TSpinbox", **field)
    style.map(
        "TSpinbox",
        fieldbackground=[("disabled", SURFACE), ("focus", INPUT)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", ACCENT)],
        arrowcolor=[("disabled", MUTED)],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=CARD,
        troughcolor=SURFACE,
        bordercolor=SURFACE,
        arrowcolor=MUTED,
        relief="flat",
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", BORDER)],
        arrowcolor=[("active", TEXT)],
    )

    root.option_add("*TCombobox*Listbox.background", INPUT)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ACCENT_TEXT)
    root.option_add("*TCombobox*Listbox.font", font_ui)
    return style


def try_dark_titlebar(root: tk.Tk) -> None:
    """Просит Windows нарисовать заголовок окна тёмным.

    Принимает корень. На других системах и при ошибке DWM ничего не делает.
    Ничего не возвращает.
    """
    try:
        import ctypes

        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = root.winfo_id()
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:
        return
