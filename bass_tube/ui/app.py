"""Окно генератора: параметры, отчёт, предпросмотр и сохранение."""

from __future__ import annotations

import tkinter as tk
from dataclasses import fields
from pathlib import Path
from tkinter import filedialog, ttk

from bass_tube.acoustics.holes import HoleError
from bass_tube.acoustics.slider import SliderError
from bass_tube.acoustics.trim import TrimError
from bass_tube.acoustics.tuning import TuningError
from bass_tube.body.tube import BodyError, TubeBody, export_tube_body
from bass_tube.constants import SCALE_IDS, SLIDER_KINDS
from bass_tube.design import Design
from bass_tube.layout.centerline import CenterlineError
from bass_tube.layout.coil import LayoutError
from bass_tube.pair import VoicePair, build_instrument, export_pair, preview_instrument
from bass_tube.params import ParamsError
from bass_tube.ui.chrome import LanguageToggle, ScrollArea, SegmentedControl, TubeMark
from bass_tube.ui.form import (
    A4_CHOICES,
    HOLE_DIAMETER_CHOICES,
    NOTE_CHOICES,
    FormInput,
    bore_caption,
    clearance_caption,
    default_form,
    derived_form_updates,
    format_mm_ui,
    numeric_text_ok,
    params_from_form,
    resolved_seat_text,
    straight_choices,
    suggested_stem,
    _resolve_slider_kind,
)
from bass_tube.ui.i18n import (
    LANG_RU,
    current_language,
    is_auto_word,
    is_drone_off_word,
    load_saved_language,
    save_language,
    scale_choice_label,
    set_current_language,
    slider_choice_label,
    t,
    yes_no_choices,
)
from bass_tube.ui.preview import ModelPreview
from bass_tube.ui.report import format_design_report, format_pair_report
from bass_tube.ui.theme import ACCENT, BORDER, CARD, TEXT, apply_theme, try_dark_titlebar


class TubeApp:
    """Главное окно. Поля слева, модель справа, отчёт снизу."""

    def __init__(self, visible: bool = True, language: str | None = None) -> None:
        """Собирает окно со стартовой формой C2.

        Принимает visible: при False окно не показывается на экране,
        но виджеты и построение модели работают. language — «ru» или «en»;
        пустое при видимом окне читает прошлый выбор, в тестах без языка
        остаётся русский. Ничего не возвращает.
        """
        if language is None:
            language = load_saved_language() if visible else LANG_RU
        set_current_language(language)
        self.root = tk.Tk()
        self.root.title(t("app.title"))
        self.root.minsize(1080, 720)
        self.root.geometry("1280x820")
        apply_theme(self.root)
        self._design: Design | None = None
        self._pair: VoicePair | None = None
        self._built_signature: tuple[str, ...] | None = None
        self._busy = False
        self._fitting = False
        self._texts: list[tuple[tk.Misc, str]] = []
        self._combos: dict[str, ttk.Combobox] = {}
        self._vars = _string_vars(default_form())
        self._numbers_only = (self.root.register(numeric_text_ok), "%P")
        self._build_widgets()
        self._refresh_derived()
        for variable in self._vars.values():
            variable.trace_add("write", self._on_field_changed)
        self._vars["slider_kind"].trace_add("write", self._on_slider_kind_changed)
        self._toggle_goal()
        self._sync_trim_with_slider()
        if visible:
            try_dark_titlebar(self.root)
        else:
            self.root.withdraw()

    def run(self) -> None:
        """Запускает цикл окна.

        Ничего не принимает. Возвращает None после закрытия окна.
        """
        self.root.mainloop()

    def destroy(self) -> None:
        """Закрывает окно.

        Ничего не принимает и не возвращает.
        """
        self.root.destroy()

    def set_language(self, lang: str, persist: bool = True) -> None:
        """Переключает язык подписей, списков и отчёта.

        Принимает «ru» или «en» и persist: писать ли выбор в файл.
        Поля с числами не трогает, локализованные списки переводит
        по смыслу. Если модель уже построена, отчёт переписывается,
        сохранение не сбрасывается. Ничего не возвращает.
        """
        had_model = self._built_signature is not None
        self._fitting = True
        try:
            set_current_language(lang)
            if persist:
                save_language(lang)
            self.root.title(t("app.title"))
            self._title_label.configure(text=t("app.title"))
            self._subtitle_label.configure(text=t("app.subtitle"))
            for widget, key in self._texts:
                widget.configure(text=t(key))
            self.build_button.configure(text=t("action.build"))
            self.save_button.configure(text=t("action.save"))
            self.lang_toggle.set_language(current_language())
            self.goal_toggle.apply_language()
            self._remap_choices()
            self.preview.apply_language()
            self._refresh_derived()
            if self._pair is not None:
                self._set_report(format_pair_report(self._pair))
            elif self._design is not None:
                self._set_report(format_design_report(self._design))
            if had_model:
                self._built_signature = self.signature()
        finally:
            self._fitting = False
        if self._design is None and self._pair is None:
            if self.report_text():
                self._set_status(t("status.reject"))
            else:
                self._set_status(t("status.start"))
            return
        self._refresh_staleness()

    def build_model(self) -> None:
        """Считает трубу по полям и показывает деталь.

        Ничего не принимает. Сперва подтягивает зависимые поля, как при
        уходе из поля. При ошибке пишет причины в отчёт и убирает
        прошлую модель. После успеха включает сохранение.
        Ничего не возвращает.
        """
        if self._busy:
            return
        self.commit_dependents()
        self._busy = True
        self.root.configure(cursor="watch")
        self._set_status(t("status.busy"))
        self.root.update()
        try:
            try:
                result = build_instrument(params_from_form(self.form_input()))
            except (
                ParamsError,
                TuningError,
                TrimError,
                SliderError,
                HoleError,
                LayoutError,
                CenterlineError,
                BodyError,
            ) as exc:
                self._reject(str(exc))
                return
            if isinstance(result, VoicePair):
                self._pair = result
                self._design = None
                self._built_signature = self.signature()
                self._set_report(format_pair_report(result))
            else:
                self._pair = None
                self._design = result
                self._built_signature = self.signature()
                self._set_report(format_design_report(result))
            try:
                self.preview.show_shape(preview_instrument(result))
            except Exception as exc:
                self.save_button.state(["!disabled"])
                self._set_status(t("status.preview_fail").format(exc=exc))
                return
            self.save_button.state(["!disabled"])
            self._set_status(t("status.ready"))
        finally:
            self._busy = False
            self.root.configure(cursor="")

    def save_model(self) -> None:
        """Спрашивает путь и пишет STEP и STL.

        Ничего не принимает. STL кладёт рядом с STEP, с тем же именем.
        Если есть трубка подстройки, рядом пишет ещё пару файлов с суффиксом
        «-подстройка». Если есть слайдер, рядом пишет пару с суффиксом
        «-слайдер». Если включены разрезы и деталь выше стола, пишет куски
        «-корпус-1», «-слайдер-2» со стыками «папа — мама». Если есть дрон, пишет одну
        деталь с двумя каналами (или её куски), трубку подстройки мелодии и
        «-подстройка-дрон». Если модели нет или параметры уже другие,
        ничего не пишет. Ничего не возвращает.
        """
        design = self._design
        pair = self._pair
        if (design is None and pair is None) or self.signature() != self._built_signature:
            self._set_status(t("status.build_first"))
            return
        chosen = filedialog.asksaveasfilename(
            title=t("dialog.save_title"),
            defaultextension=".step",
            filetypes=[("STEP", "*.step"), ("STEP", "*.stp")],
            initialfile=f"{suggested_stem(pair.params if pair is not None else design.params)}.step",
        )
        if not chosen:
            return
        step_path = Path(chosen)
        if step_path.suffix.lower() not in {".step", ".stp"}:
            step_path = step_path.with_suffix(".step")
        stl_path = step_path.with_suffix(".stl")
        try:
            if pair is not None:
                saved = export_pair(pair, step_path, stl_path)
            else:
                saved = _export_design(design, step_path, stl_path)
        except BodyError as exc:
            self._set_status(str(exc))
            return
        self._set_status(t("status.saved").format(paths=", ".join(str(path) for path in saved)))

    def form_input(self) -> FormInput:
        """Снимает текущие строки полей.

        Ничего не принимает. Возвращает FormInput в порядке полей формы.
        """
        values = {name: variable.get() for name, variable in self._vars.items()}
        return FormInput(**values)

    def signature(self) -> tuple[str, ...]:
        """Отпечаток полей, чтобы не сохранить устаревшую модель.

        Ничего не принимает. Возвращает кортеж строк в стабильном порядке.
        """
        form = self.form_input()
        return tuple(getattr(form, item.name) for item in fields(FormInput))

    def report_text(self) -> str:
        """Текст нижнего отчёта.

        Ничего не принимает. Возвращает всё содержимое поля отчёта.
        """
        return self.report.get("1.0", "end").strip()

    def _build_widgets(self) -> None:
        """Раскладывает шапку, форму, предпросмотр, отчёт и статус.

        Ничего не принимает и не возвращает.
        """
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell = ttk.Frame(self.root, style="Shell.TFrame")
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        header = ttk.Frame(shell, style="Header.TFrame", padding=(20, 14, 20, 12))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        TubeMark(header).grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 14))
        self._title_label = ttk.Label(header, text=t("app.title"), style="HeaderTitle.TLabel")
        self._title_label.grid(row=0, column=1, sticky="w")
        self._subtitle_label = ttk.Label(
            header, text=t("app.subtitle"), style="HeaderSub.TLabel"
        )
        self._subtitle_label.grid(row=1, column=1, sticky="w")
        self.lang_toggle = LanguageToggle(header, current_language(), self.set_language)
        self.lang_toggle.grid(row=0, column=2, rowspan=2, sticky="e")

        copper = tk.Frame(shell, bg=ACCENT, height=2, highlightthickness=0)
        copper.grid(row=1, column=0, sticky="ew")

        body = ttk.Frame(shell, style="Shell.TFrame", padding=(18, 14, 18, 12))
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        form_column = ttk.Frame(body, style="Surface.TFrame")
        form_column.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        form_column.rowconfigure(0, weight=1)
        form_column.columnconfigure(0, weight=1)
        scroll = ScrollArea(form_column)
        scroll.grid(row=0, column=0, sticky="nsew")
        self._fill_form(scroll.inner)
        scroll.bind_descendants()
        buttons = ttk.Frame(form_column, style="Surface.TFrame")
        buttons.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(0, weight=1)
        buttons.columnconfigure(1, weight=1)
        self.build_button = ttk.Button(
            buttons, text=t("action.build"), command=self.build_model, style="Accent.TButton"
        )
        self.build_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.save_button = ttk.Button(
            buttons, text=t("action.save"), command=self.save_model, style="Ghost.TButton"
        )
        self.save_button.grid(row=0, column=1, sticky="ew")
        self.save_button.state(["disabled"])

        preview_shell = tk.Frame(body, bg=BORDER, highlightthickness=0)
        preview_shell.grid(row=0, column=1, sticky="nsew")
        preview_inner = ttk.Frame(preview_shell, style="Surface.TFrame", padding=1)
        preview_inner.pack(fill="both", expand=True)
        preview_inner.columnconfigure(0, weight=1)
        preview_inner.rowconfigure(0, weight=1)
        self.preview = ModelPreview(preview_inner)
        self.preview.grid(row=0, column=0, sticky="nsew")

        self.report = tk.Text(
            body,
            height=9,
            wrap="word",
            relief="flat",
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            highlightthickness=0,
            bd=0,
            font=("Segoe UI", 10),
            padx=12,
            pady=10,
        )
        self.report.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        self.report.configure(state="disabled")
        self.status = tk.StringVar(value=t("status.start"))
        ttk.Label(body, textvariable=self.status, style="Status.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )

    def _fill_form(self, parent: ttk.Frame) -> None:
        """Кладёт группы полей в прокручиваемую колонку.

        Принимает внутренний фрейм прокрутки. Ничего не возвращает.
        """
        goal = self._group(parent, "group.goal")
        self.goal_toggle = SegmentedControl(
            goal,
            [("note", "goal.note"), ("length", "goal.length")],
            self._vars["goal"].get(),
            self._pick_goal,
            bg=CARD,
        )
        self.goal_toggle.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.note_entry = self._choice_field(
            goal, 1, "field.note", "note", NOTE_CHOICES, editable=True, numeric=False
        )
        self.length_entry = self._field(goal, 2, "field.body_length", "body_length")

        section = self._group(parent, "group.tube")
        self._field(section, 0, "field.outer_diameter", "outer_diameter")
        self._field(section, 1, "field.wall", "wall")
        self.bore_label = ttk.Label(section, text="", style="Caption.TLabel")
        self.bore_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._hint(section, 3, "hint.diameter_master")

        joint = self._group(parent, "group.joint")
        self._field(joint, 0, "field.seat_outer", "seat_outer_diameter")
        self.seat_bore_label = ttk.Label(joint, text="", style="Caption.TLabel")
        self.seat_bore_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self._field(joint, 2, "field.module_hole", "module_hole")
        self._field(joint, 3, "field.seat", "seat")
        self.clearance_label = ttk.Label(joint, text="", style="Caption.TLabel")
        self.clearance_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 4))
        self._field(joint, 5, "field.transition", "transition")
        self._hint(joint, 6, "hint.joint")

        envelope = self._group(parent, "group.envelope")
        self._field(envelope, 0, "field.max_height", "max_height")
        self._field(envelope, 1, "field.max_width", "max_width")
        self._field(envelope, 2, "field.max_depth", "max_depth")
        self._field(envelope, 3, "field.head_reserve", "head_reserve")
        self._choice_field(envelope, 4, "field.print_splits", "print_splits", yes_no_choices())
        self._hint(envelope, 5, "hint.splits")

        layout = self._group(parent, "group.layout")
        self._hint(layout, 0, "hint.bundle")
        self._choice_field(layout, 1, "field.straight_count", "straight_count", straight_choices())
        self._hint(layout, 2, "hint.straights")
        self._field(layout, 3, "field.turn_radius", "turn_radius")
        self._hint(layout, 4, "hint.radius")
        self._field(layout, 5, "field.gap", "gap")
        self._field(layout, 6, "field.floor", "floor")
        self.trim_entry = self._spin_field(layout, 7, "field.trim", "trim_semitones", 0, 12)
        self._hint(layout, 8, "hint.trim")

        holes = self._group(parent, "group.holes")
        self._spin_field(holes, 0, "field.hole_count", "hole_count", 0, 8)
        self._hint(holes, 1, "hint.holes")
        self._choice_field(
            holes, 2, "field.scale", "scale", [scale_choice_label(key) for key in SCALE_IDS]
        )
        self._hint(holes, 3, "hint.scale")
        self._choice_field(
            holes, 4, "field.hole_diameter", "hole_diameter", HOLE_DIAMETER_CHOICES, editable=True
        )

        slider = self._group(parent, "group.slider")
        self._choice_field(
            slider,
            0,
            "field.slider_kind",
            "slider_kind",
            [slider_choice_label(key) for key in ("",) + SLIDER_KINDS],
        )
        self._spin_field(slider, 1, "field.slider_semitones", "slider_semitones", 1, 12)
        self._spin_field(slider, 2, "field.slider_pairs", "slider_pairs", 1, 12)
        self._field(slider, 3, "field.slider_clearance", "slider_clearance")
        self._hint(slider, 4, "hint.slider")

        drone = self._group(parent, "group.drone")
        self._choice_field(
            drone,
            0,
            "field.drone_note",
            "drone_note",
            (t("choice.drone_off"), *NOTE_CHOICES),
            editable=True,
            numeric=False,
        )
        self._spin_field(drone, 1, "field.drone_trim", "drone_trim_semitones", 0, 12)
        self._hint(drone, 2, "hint.drone")

        corrections = self._group(parent, "group.corrections")
        self._field(corrections, 0, "field.delta_head", "delta_head")
        self._field(corrections, 1, "field.delta_out", "delta_out")
        self._hint(corrections, 2, "hint.delta_out")
        self._field(corrections, 3, "field.delta_bends", "delta_bends")

        reference = self._group(parent, "group.reference")
        self._choice_field(reference, 0, "field.a4", "a4", A4_CHOICES, editable=True)
        self._hint(reference, 1, "hint.speed")

    def _group(self, parent: ttk.Frame, title_key: str) -> ttk.Frame:
        """Добавляет карточку с заголовком в конец колонки.

        Принимает родителя и ключ заголовка. Возвращает внутреннюю рамку
        для полей.
        """
        row = parent.grid_size()[1]
        card = ttk.Frame(parent, style="Card.TFrame", padding=(12, 10))
        card.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        parent.columnconfigure(0, weight=1)
        title = ttk.Label(card, text=t(title_key), style="CardTitle.TLabel")
        title.grid(row=0, column=0, sticky="w")
        self._texts.append((title, title_key))
        ttk.Separator(card, orient="horizontal").grid(
            row=1, column=0, sticky="ew", pady=(6, 8)
        )
        body = ttk.Frame(card, style="Card.TFrame")
        body.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(0, minsize=210)
        body.columnconfigure(1, weight=1)
        return body

    def _hint(self, group: ttk.Frame, row: int, key: str) -> ttk.Label:
        """Кладёт приглушённую подсказку на всю ширину карточки.

        Принимает рамку полей, строку и ключ текста. Возвращает подпись.
        """
        label = ttk.Label(group, text=t(key), style="Hint.TLabel", wraplength=360)
        label.grid(row=row, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._texts.append((label, key))
        return label

    def _field(self, group: ttk.Frame, row: int, key: str, name: str) -> ttk.Entry:
        """Кладёт подпись и числовое поле ввода в строку группы.

        Принимает группу, номер строки, ключ подписи и имя переменной. В поле
        набираются только цифры, минус и одна запятая или точка.
        Возвращает поле ввода.
        """
        entry = ttk.Entry(group, textvariable=self._vars[name], width=16)
        return self._place(group, row, key, entry, numeric=True)

    def _spin_field(
        self, group: ttk.Frame, row: int, key: str, name: str, low: int, high: int
    ) -> ttk.Spinbox:
        """Кладёт подпись и счётчик целых со стрелками.

        Принимает группу, строку, ключ подписи, имя переменной и границы стрелок.
        Число можно и набрать; пустое поле остаётся пустым, пока не нажата
        стрелка. Возвращает счётчик.
        """
        spin = ttk.Spinbox(
            group, textvariable=self._vars[name], from_=low, to=high, increment=1, width=14
        )
        return self._place(group, row, key, spin, numeric=True)

    def _choice_field(
        self,
        group: ttk.Frame,
        row: int,
        key: str,
        name: str,
        values,
        editable: bool = False,
        numeric: bool = True,
    ) -> ttk.Combobox:
        """Кладёт подпись и выпадающий список.

        Принимает группу, строку, ключ подписи, имя переменной, варианты,
        editable — можно ли вписать своё значение, numeric — пускать ли
        в вписанное только число. Без editable выбирается только из списка.
        Возвращает список.
        """
        box = ttk.Combobox(
            group,
            textvariable=self._vars[name],
            values=list(values),
            state="normal" if editable else "readonly",
            width=14,
        )
        box.bind("<<ComboboxSelected>>", self.commit_dependents, add="+")
        self._combos[name] = box
        return self._place(group, row, key, box, numeric=editable and numeric)

    def _place(self, group: ttk.Frame, row: int, key: str, widget, numeric: bool):
        """Ставит подпись и виджет в строку и вешает общие привязки.

        Принимает группу, строку, ключ подписи, виджет и флаг числового фильтра.
        Уход из поля и Enter подтягивают зависимые поля. Возвращает виджет.
        """
        label = ttk.Label(group, text=t(key), style="Field.TLabel")
        label.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        self._texts.append((label, key))
        widget.grid(row=row, column=1, sticky="ew", pady=3)
        if numeric:
            widget.configure(validate="key", validatecommand=self._numbers_only)
        widget.bind("<FocusOut>", self.commit_dependents, add="+")
        widget.bind("<Return>", self.commit_dependents, add="+")
        return widget

    def _remap_choices(self) -> None:
        """Переводит значения списков при смене языка.

        Ничего не принимает. Числа и ноты оставляет, «да/авто/нет» и
        подписи лада со слайдером ставит на новый язык по позиции в списке.
        Ничего не возвращает.
        """
        self._remap_combo("print_splits", list(yes_no_choices()))
        self._remap_combo("scale", [scale_choice_label(key) for key in SCALE_IDS])
        self._remap_combo(
            "slider_kind", [slider_choice_label(key) for key in ("",) + SLIDER_KINDS]
        )
        auto = t("choice.auto")
        box = self._combos["straight_count"]
        current = self._vars["straight_count"].get()
        box.configure(values=list(straight_choices()))
        if is_auto_word(current):
            self._vars["straight_count"].set(auto)
        drone_off = t("choice.drone_off")
        drone_box = self._combos["drone_note"]
        drone_now = self._vars["drone_note"].get()
        drone_box.configure(values=(drone_off, *NOTE_CHOICES))
        if is_drone_off_word(drone_now):
            self._vars["drone_note"].set(drone_off)

    def _remap_combo(self, name: str, new_values: list[str]) -> None:
        """Ставит новые подписи списка и переводит выбранное по индексу.

        Принимает имя поля и новый список значений. Если текущая строка
        была в старом списке, берёт ту же позицию. Ничего не возвращает.
        """
        box = self._combos[name]
        old_values = list(box.cget("values"))
        current = self._vars[name].get()
        box.configure(values=new_values)
        if current in old_values:
            self._vars[name].set(new_values[old_values.index(current)])
            return
        if current in new_values:
            return

    def _pick_goal(self, value: str) -> None:
        """Переключает режим цели с сегмента нота / длина.

        Принимает «note» или «length». Пишет в переменную формы и гасит
        ненужное поле. Ничего не возвращает.
        """
        self._vars["goal"].set(value)
        self._toggle_goal()

    def _toggle_goal(self) -> None:
        """Включает поле выбранного режима и гасит другое.

        Ничего не принимает и не возвращает. Нота и длина не активны вместе.
        """
        note_mode = self._vars["goal"].get() == "note"
        self.note_entry.state(["!disabled"] if note_mode else ["disabled"])
        self.length_entry.state(["disabled"] if note_mode else ["!disabled"])

    def _sync_trim_with_slider(self) -> None:
        """Гасит трубку подстройки, когда выбран слайдер.

        Ничего не принимает. Если схема слайдера не «нет», ставит подстройку
        в ноль и выключает поле: слайдер уже меняет длину, отдельно трубку
        выключать не нужно. Пустое число полутонов при выбранной схеме
        становится единицей, чтобы деталь слайдера реально появилась. Без
        слайдера поле полутонов очищается, подстройку снова можно править.
        Ничего не возвращает.
        """
        kind = _resolve_slider_kind(self._vars["slider_kind"].get())
        if kind:
            if not self._vars["slider_semitones"].get().strip():
                self._vars["slider_semitones"].set("1")
            if self._vars["trim_semitones"].get().strip() not in ("", "0"):
                self._vars["trim_semitones"].set("0")
            self.trim_entry.state(["disabled"])
            return
        if self._vars["slider_semitones"].get().strip() not in ("", "0"):
            self._vars["slider_semitones"].set("")
        self.trim_entry.state(["!disabled"])

    def _on_field_changed(self, *_args: object) -> None:
        """Обновляет подписи и помечает модель устаревшей на каждое нажатие.

        Принимает служебные аргументы trace. Другие поля здесь не трогает,
        чтобы недописанное число не переписывало соседей. Пока идёт
        подгонка, вход отбрасывается. Ничего не возвращает.
        """
        if self._fitting:
            return
        self._refresh_derived()
        self._refresh_staleness()

    def _on_slider_kind_changed(self, *_args: object) -> None:
        """Гасит или возвращает трубку подстройки при смене схемы слайдера.

        Принимает служебные аргументы trace. Ничего не возвращает.
        """
        if self._fitting:
            return
        self._sync_trim_with_slider()

    def commit_dependents(self, _event: tk.Event | None = None) -> None:
        """Подтягивает стенку, дно, радиус и глубину под наружный диаметр.

        Принимает необязательное событие ухода из поля, Enter или выбора
        в списке. Зовётся, когда ввод закончен, а не на каждое нажатие.
        Пишет только поля, которые реально изменились. Ничего не возвращает.
        """
        if self._fitting:
            return
        self._fitting = True
        try:
            updates = derived_form_updates(
                self._vars["outer_diameter"].get(),
                self._vars["wall"].get(),
                self._vars["seat_outer_diameter"].get(),
                self._vars["floor"].get(),
                self._vars["turn_radius"].get(),
                self._vars["gap"].get(),
                self._vars["max_depth"].get(),
                self._vars["module_hole"].get(),
            )
            for name, text in updates.items():
                self._vars[name].set(text)
        finally:
            self._fitting = False
        self._refresh_derived()
        self._refresh_staleness()

    def _refresh_staleness(self) -> None:
        """Включает или гасит сохранение по совпадению полей с моделью.

        Ничего не принимает и не возвращает.
        """
        if self._built_signature is None:
            return
        if self.signature() == self._built_signature:
            self.save_button.state(["!disabled"])
            self._set_status(t("status.fresh"))
            return
        self.save_button.state(["disabled"])
        self._set_status(t("status.stale"))

    def _refresh_derived(self) -> None:
        """Обновляет подписи каналов трубы и конца и зазора пары.

        Ничего не принимает. Конец берётся таким, каким его возьмёт расчёт:
        пустой или толще отверстия — под отверстие модуля; тогда в подписи
        канала конца стоит и сам подобранный диаметр. Ничего не возвращает.
        """
        wall = self._vars["wall"].get()
        hole = self._vars["module_hole"].get()
        typed = self._vars["seat_outer_diameter"].get()
        seat = resolved_seat_text(typed, hole)
        self.bore_label.configure(
            text=bore_caption(self._vars["outer_diameter"].get(), wall, t("caption.tube_bore"))
        )
        seat_caption = bore_caption(seat, wall, t("caption.seat_bore"))
        if seat != typed and seat != typed.strip().replace(",", "."):
            seat_caption += t("caption.seat_resolved").format(mm=format_mm_ui(float(seat)))
        self.seat_bore_label.configure(text=seat_caption)
        self.clearance_label.configure(text=clearance_caption(hole, seat))

    def _reject(self, text: str) -> None:
        """Показывает отказ и прячет прошлую деталь.

        Принимает текст причин. Сохранение выключает. Ничего не возвращает.
        """
        self._design = None
        self._pair = None
        self._built_signature = None
        self.preview.clear()
        self._set_report(text)
        self.save_button.state(["disabled"])
        self._set_status(t("status.reject"))

    def _set_report(self, text: str) -> None:
        """Заменяет текст отчёта.

        Принимает новый текст. Ничего не возвращает.
        """
        self.report.configure(state="normal")
        self.report.delete("1.0", "end")
        self.report.insert("1.0", text)
        self.report.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        """Пишет короткую строку состояния.

        Принимает текст. Ничего не возвращает.
        """
        self.status.set(text)


def _export_design(design: Design, step_path: Path, stl_path: Path) -> list[Path]:
    """Пишет корпус, куски разрезов, трубку подстройки и слайдер одной трубы.

    Принимает Design и пути STEP/STL корпуса. Если включены разрезы и деталь
    выше стола, вместо целого корпуса пишет куски «-корпус-N». Трубка
    подстройки — суффикс «-подстройка», слайдер — «-слайдер» или куски
    «-слайдер-N». Возвращает список записанных путей.
    """
    saved: list[Path] = []
    if design.body_slices:
        for piece in design.body_slices:
            piece_step = step_path.with_name(
                f"{step_path.stem}-{piece.name}{step_path.suffix}"
            )
            piece_stl = stl_path.with_name(f"{stl_path.stem}-{piece.name}.stl")
            export_tube_body(
                _slice_as_body(design.body, piece.solid),
                piece_step,
                piece_stl,
            )
            saved.extend((piece_step, piece_stl))
    else:
        export_tube_body(design.body, step_path, stl_path)
        saved.extend((step_path, stl_path))
    if design.tuner is not None:
        tuner_step = step_path.with_name(f"{step_path.stem}-подстройка{step_path.suffix}")
        tuner_stl = stl_path.with_name(f"{stl_path.stem}-подстройка.stl")
        export_tube_body(design.tuner, tuner_step, tuner_stl)
        saved.extend((tuner_step, tuner_stl))
    if design.slider_slices:
        for piece in design.slider_slices:
            piece_step = step_path.with_name(
                f"{step_path.stem}-{piece.name}{step_path.suffix}"
            )
            piece_stl = stl_path.with_name(f"{stl_path.stem}-{piece.name}.stl")
            export_tube_body(
                _slice_as_body(design.slider_body, piece.solid),
                piece_step,
                piece_stl,
            )
            saved.extend((piece_step, piece_stl))
    elif design.slider_body is not None:
        slider_step = step_path.with_name(f"{step_path.stem}-слайдер{step_path.suffix}")
        slider_stl = stl_path.with_name(f"{stl_path.stem}-слайдер.stl")
        export_tube_body(design.slider_body, slider_step, slider_stl)
        saved.extend((slider_step, slider_stl))
    return saved


def _slice_as_body(template: TubeBody | None, solid) -> TubeBody:
    """Собирает TubeBody для экспорта одного куска разреза.

    Принимает целую деталь-шаблон (диаметры, длины) и солид куска.
    Возвращает TubeBody. Без шаблона поднимает BodyError.
    """
    if template is None:
        raise BodyError("Нет шаблона детали для куска разреза.")
    return TubeBody(
        solid=solid,
        axis_length_mm=template.axis_length_mm,
        outer_diameter_mm=template.outer_diameter_mm,
        bore_diameter_mm=template.bore_diameter_mm,
        seat_outer_diameter_mm=template.seat_outer_diameter_mm,
        seat_bore_diameter_mm=template.seat_bore_diameter_mm,
        base_height_mm=template.base_height_mm,
    )


def _string_vars(form: FormInput) -> dict[str, tk.StringVar]:
    """Делает переменные tkinter по полям формы.

    Принимает начальную форму. Возвращает словарь имя поля → StringVar.
    """
    return {item.name: tk.StringVar(value=getattr(form, item.name)) for item in fields(FormInput)}
