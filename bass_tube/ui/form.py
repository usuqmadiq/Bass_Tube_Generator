"""Разбор полей окна в параметры трубы.

Пустая поправка открытого конца означает формулу 0,6 радиуса канала.
Пустое число прямых или «авто»/auto — автоподбор самой низкой укладки, что входит в габарит.
Пустой радиус разворота — минимум под диаметр трубы и зазор.
Пустой диаметр конца — под отверстие модуля со штатным зазором.
Нота дрона «нет»/none или пусто — один голос.
Пустая длина переходника — конус с половинным углом 15°.
Скорости звука в форме нет: это константа мира.
Запятая в числах считается десятичным разделителем.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace

from bass_tube.acoustics.scales import SCALE_LABELS
from bass_tube.constants import (
    DEFAULT_HOLE_DIAMETER_MM,
    DEFAULT_SCALE,
    DEFAULT_SLIDER_CLEARANCE_MM,
    LAYOUT_BUNDLE,
    LAYOUTS,
    MODULE_HOLE_MM,
    SCALE_IDS,
    SLIDER_KIND_LABELS,
    SLIDER_KINDS,
)
from bass_tube.derived import fit_geometry
from bass_tube.params import ParamsError, TubeParams, resolve_seat_diameter_mm, tube_params
from bass_tube.ui.i18n import (
    current_language,
    is_auto_word,
    is_drone_off_word,
    is_slider_off_word,
    scale_choice_label,
    slider_choice_label,
    t,
)

# Слово в поле числа прямых, означающее автоподбор (русская форма по умолчанию).
STRAIGHT_AUTO = "авто"
# Слово в поле ноты дрона, означающее один голос (русская форма по умолчанию).
DRONE_OFF = "нет"
# Ноты выпадающего списка: басовый диапазон с диезами.
NOTE_CHOICES = tuple(
    f"{name}{octave}"
    for octave in (1, 2, 3)
    for name in ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
)
def straight_choices() -> tuple[str, ...]:
    """Варианты числа прямых для списка окна.

    Ничего не принимает. Первым идёт «авто» на текущем языке, дальше
    нечётные числа. Возвращает кортеж строк.
    """
    return (t("choice.auto"), *(str(count) for count in range(3, 42, 2)))


# Нечётные числа прямых в выпадающем списке после «авто» на русском.
# Окно берёт актуальный язык через straight_choices(); это запас для тестов.
STRAIGHT_CHOICES = (STRAIGHT_AUTO, *(str(count) for count in range(3, 42, 2)))
# Ходовые диаметры дырок и опорные строи для выпадающих списков.
HOLE_DIAMETER_CHOICES = ("6", "7", "8", "9", "10", "12")
A4_CHOICES = ("440", "442", "432", "415")
# Что можно набрать в числовом поле, пока ввод не закончен.
_NUMERIC_TYPING = re.compile(r"^-?\d*[.,]?\d*$")


@dataclass(frozen=True, slots=True)
class FormInput:
    """Сырые строки формы. goal — «note» или «length», укладка всегда вязанка."""

    goal: str
    note: str
    body_length: str
    outer_diameter: str
    wall: str
    seat_outer_diameter: str
    module_hole: str
    seat: str
    transition: str
    max_height: str
    max_width: str
    max_depth: str
    head_reserve: str
    layout: str
    straight_count: str
    turn_radius: str
    gap: str
    floor: str
    trim_semitones: str
    hole_count: str
    scale: str
    hole_diameter: str
    slider_kind: str
    slider_semitones: str
    slider_pairs: str
    slider_clearance: str
    print_splits: str
    drone_note: str
    drone_trim_semitones: str
    delta_head: str
    delta_out: str
    delta_bends: str
    a4: str


def default_form() -> FormInput:
    """Стартовые значения окна для контрольной ноты C2.

    Ничего не принимает. Возвращает форму вязанки: труба 19,5 мм, конец
    пустой (под отверстие модуля 19,63 мм — те же 19,5 мм), стенка 2 мм,
    радиус разворота пустой (самый тесный под диаметр и зазор), зазор 1 мм,
    габарит 250 × 150 × 150 мм — автоподбор даёт шестигранник из 7 прямых.
    Поправка открытого конца, число прямых и переходник пустые: их подставит расчёт.
    Лад дырок по умолчанию — натуральный минор.
    Подстройка по умолчанию — один полутон вниз: корпус на верхнюю ноту, трубка
    печатается отдельно. Ноль в поле — без трубки. Отверстий по умолчанию нет.
    Слайдера по умолчанию нет: его нельзя включать вместе с отверстиями.
    Зазор царги по умолчанию пустой: подставится 0,3 мм со всех сторон.
    Колен U по умолчанию пусто: возьмётся из схемы. Разрезы по умолчанию
    включены: куски стола со стыками «папа — мама» без зазора, собранная труба может
    быть выше области печати. Число прямых — «авто». Дрон по умолчанию
    выключен: нота «нет».
    """
    return FormInput(
        goal="note",
        note="C2",
        body_length="1306",
        outer_diameter="19.5",
        wall="2",
        seat_outer_diameter="",
        module_hole="19.63",
        seat="8",
        transition="",
        max_height="250",
        max_width="150",
        max_depth="150",
        head_reserve="35",
        layout=LAYOUT_BUNDLE,
        straight_count=t("choice.auto"),
        turn_radius="",
        gap="1",
        floor="3",
        trim_semitones="1",
        hole_count="0",
        scale=scale_choice_label(DEFAULT_SCALE),
        hole_diameter="8",
        slider_kind=slider_choice_label(""),
        slider_semitones="",
        slider_pairs="",
        slider_clearance="",
        print_splits=t("choice.yes"),
        drone_note=t("choice.drone_off"),
        drone_trim_semitones="",
        delta_head="0",
        delta_out="",
        delta_bends="0",
        a4="440",
    )


def params_from_form(form: FormInput) -> TubeParams:
    """Собирает параметры из строк формы.

    Принимает FormInput. В режиме ноты длину корпуса не передаёт,
    в режиме длины не передаёт ноту. Пустую поправку открытого конца
    оставляет на формулу 0,6a.     Пустую подстройку считает нулём: трубки нет.
    Пустое число отверстий — без дырок. Лад читается и по ключу, и по русской
    подписи. Пустой диаметр дырки — 8 мм.     Пустой слайдер — без слайдера; схема
    читается по ключу и по русской подписи. Пустой зазор слайдера — 0,3 мм
    со всех сторон. Пустая нота дрона или «нет» — один голос. Пустая
    подстройка дрона при заданной ноте дрона — один полутон вниз. Число
    прямых «авто» — как пустое. Возвращает TubeParams.
    Если строки не числа или набор противоречив, поднимает ParamsError
    со всеми причинами сразу.
    """
    reasons: list[str] = []
    outer = _required_number(form.outer_diameter, t("error.outer"), reasons)
    wall = _required_number(form.wall, t("error.wall"), reasons)
    seat_outer = _optional_number(form.seat_outer_diameter, t("error.seat_outer"), reasons)
    hole = _required_number(form.module_hole, t("error.module_hole"), reasons)
    seat = _required_number(form.seat, t("error.seat"), reasons)
    transition = _optional_number(form.transition, t("error.transition"), reasons)
    height = _required_number(form.max_height, t("error.height"), reasons)
    width = _required_number(form.max_width, t("error.width"), reasons)
    depth = _required_number(form.max_depth, t("error.depth"), reasons)
    reserve = _required_number(form.head_reserve, t("error.reserve"), reasons)
    radius = _optional_number(form.turn_radius, t("error.radius"), reasons)
    gap = _required_number(form.gap, t("error.gap"), reasons)
    floor = _required_number(form.floor, t("error.floor"), reasons)
    trim = _optional_int(form.trim_semitones, t("error.trim"), reasons)
    holes_count = _optional_int(form.hole_count, t("error.holes"), reasons)
    hole_diameter = _optional_number(form.hole_diameter, t("error.hole_diameter"), reasons)
    slider_steps = _optional_int(form.slider_semitones, t("error.slider"), reasons)
    slider_pairs = _optional_int(form.slider_pairs, t("error.slider_pairs"), reasons)
    slider_clearance = _optional_number(form.slider_clearance, t("error.slider_clearance"), reasons)
    drone_trim = _optional_int(form.drone_trim_semitones, t("error.drone_trim"), reasons)
    head = _required_number(form.delta_head, t("error.delta_head"), reasons)
    bends = _required_number(form.delta_bends, t("error.delta_bends"), reasons)
    a4 = _required_number(form.a4, t("error.a4"), reasons)
    count_text = "" if is_auto_word(form.straight_count) else form.straight_count
    count = _optional_int(count_text, t("error.straights"), reasons)
    end_correction = _optional_number(form.delta_out, t("error.delta_out"), reasons)
    if form.layout not in LAYOUTS:
        reasons.append(t("error.layout_bundle_only"))

    note: str | None = None
    body_length: float | None = None
    if form.goal == "note":
        note = form.note.strip()
    elif form.goal == "length":
        body_length = _required_number(form.body_length, t("error.body_length"), reasons)
    else:
        reasons.append(t("error.pick_goal"))
    drone_text = form.drone_note.strip()
    drone_note = None if is_drone_off_word(drone_text) else drone_text
    if drone_note is None:
        drone_trim_value = 0
    else:
        drone_trim_value = 1 if drone_trim is None else drone_trim

    required = (outer, wall, hole, seat, height, width, depth, reserve, gap, floor)
    if reasons or None in (*required, head, bends, a4):
        raise ParamsError(reasons or [t("error.form_incomplete")])

    try:
        return tube_params(
            note=note,
            body_length_mm=body_length,
            outer_diameter_mm=outer,
            seat_outer_diameter_mm=seat_outer,
            wall_thickness_mm=wall,
            module_hole_mm=hole,
            seat_length_mm=seat,
            transition_length_mm=transition,
            max_height_mm=height,
            max_width_mm=width,
            max_depth_mm=depth,
            head_reserve_mm=reserve,
            layout=form.layout,
            straight_count=count,
            turn_radius_mm=radius,
            gap_mm=gap,
            floor_mm=floor,
            trim_semitones=0 if trim is None else trim,
            hole_count=0 if holes_count is None else holes_count,
            scale=_resolve_scale(form.scale),
            hole_diameter_mm=(
                DEFAULT_HOLE_DIAMETER_MM if hole_diameter is None else hole_diameter
            ),
            slider_kind=_resolve_slider_kind(form.slider_kind),
            slider_semitones=0 if slider_steps is None else slider_steps,
            slider_pairs=0 if slider_pairs is None else slider_pairs,
            slider_clearance_mm=(
                DEFAULT_SLIDER_CLEARANCE_MM
                if slider_clearance is None
                else slider_clearance
            ),
            print_splits=(
                True
                if not form.print_splits.strip()
                else form.print_splits
            ),
            drone_note=drone_note,
            drone_trim_semitones=drone_trim_value,
            delta_head_mm=head,
            delta_out_mm=end_correction,
            delta_bends_mm=bends,
            a4_hz=a4,
        )
    except ParamsError as exc:
        raise ParamsError([*reasons, *exc.reasons]) from exc


def format_mm_ui(value: float) -> str:
    """Миллиметры для подписей окна на текущем языке.

    Принимает число. Русский — с запятой, английский — с точкой.
    Возвращает короткую запись без хвостовых нулей.
    """
    text = format_mm(value)
    if current_language() != "ru":
        return text.replace(",", ".")
    return text


def bore_caption(outer_text: str, wall_text: str, label: str | None = None) -> str:
    """Подпись внутреннего канала по наружному диаметру и стенке.

    Принимает две строки из полей и начало подписи («Канал трубы»,
    «Канал конца»). Если подпись не дали, берёт общую «Канал» текущего
    языка. Если это числа и канал положительный, возвращает
    «<подпись>: … мм». Иначе короткую заглушку.
    """
    caption = label if label is not None else t("caption.tube_bore")
    outer = _number(outer_text)
    wall = _number(wall_text)
    if outer is None or wall is None:
        return t("caption.bore_empty").format(label=caption)
    bore = outer - 2.0 * wall
    if bore <= 0.0:
        return t("caption.bore_eaten").format(label=caption)
    return t("caption.bore_value").format(label=caption, mm=format_mm_ui(bore))


def clearance_caption(hole_text: str, outer_text: str) -> str:
    """Подпись зазора между отверстием модуля и концом трубы.

    Принимает строки отверстия и наружного диаметра конца под модуль.
    Возвращает «Зазор пары: … мм», когда оба значения — числа.
    Иначе «Зазор пары: —». Язык подписи — текущий язык окна.
    """
    hole = _number(hole_text)
    outer = _number(outer_text)
    if hole is None or outer is None:
        return t("caption.clearance_empty")
    return t("caption.clearance_value").format(mm=format_mm_ui(hole - outer))


def resolved_seat_text(seat_text: str, hole_text: str) -> str:
    """Диаметр конца под модуль, который реально пойдёт в расчёт.

    Принимает строки поля конца и отверстия модуля. Пустой конец или конец
    не тоньше отверстия заменяет на отверстие минус штатный зазор, как
    расчёт. Если отверстие не число, берёт штатное. Возвращает строку
    с точкой, пригодную для подписей, или исходную строку, если конец
    набран, но это не число.
    """
    hole = _number(hole_text)
    seat = _number(seat_text)
    if seat is None and seat_text.strip():
        return seat_text
    value = resolve_seat_diameter_mm(seat, hole if hole is not None else MODULE_HOLE_MM)
    return format_mm(value).replace(",", ".")


def numeric_text_ok(text: str) -> bool:
    """Можно ли оставить в числовом поле такой набранный текст.

    Принимает текст поля после нажатия клавиши. Пропускает пустое, минус,
    цифры и одну запятую или точку — то есть любое недописанное число.
    Возвращает True, если набор допустим.
    """
    return _NUMERIC_TYPING.fullmatch(text.replace(" ", "")) is not None


def suggested_stem(params: TubeParams) -> str:
    """Имя файла без расширения.

    Принимает параметры. Для режима ноты возвращает «труба-C2»,
    для режима длины — «труба-» и длину корпуса в миллиметрах.
    Если задан дрон, к имени добавляется его нота: «труба-C2-G1».
    """
    if params.note:
        stem = f"труба-{params.note}"
    else:
        stem = f"труба-{format_mm(params.body_length_mm or 0.0)}мм"
    if params.drone_note:
        stem += f"-{params.drone_note}"
    return stem


def format_mm(value: float) -> str:
    """Миллиметры для подписей окна.

    Принимает число. Возвращает запись с запятой: целое без дроби,
    иначе до двух знаков без хвостовых нулей.
    """
    rounded = round(float(value), 2)
    if math.isclose(rounded, round(rounded), abs_tol=1e-9):
        return str(int(round(rounded)))
    return f"{rounded:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def derived_form_updates(
    outer_text: str,
    wall_text: str,
    seat_outer_text: str,
    floor_text: str,
    radius_text: str,
    gap_text: str,
    depth_text: str,
    hole_text: str = "",
) -> dict[str, str]:
    """Какие поля формы подтянуть под наружный диаметр трубы.

    Принимает сырые строки диаметра трубы, стенки, конца, дна, радиуса,
    зазора, глубины и отверстия модуля. Пустой или слишком толстый конец
    берётся под отверстие, как в расчёте. Если диаметры, стенка, дно, зазор
    и глубина — числа и диаметр трубы положительный, подгоняет стенку, дно
    и глубину. Радиус пишет, только если он задан и меньше минимума: пустое
    поле так и значит «самый тесный». Возвращает только те поля, чей текст
    должен измениться: имена как в FormInput.
    """
    outer = _number(outer_text)
    wall = _number(wall_text)
    hole = _number(hole_text)
    seat_outer = resolve_seat_diameter_mm(
        _number(seat_outer_text), hole if hole is not None else MODULE_HOLE_MM
    )
    floor = _number(floor_text)
    gap = _number(gap_text)
    depth = _number(depth_text)
    radius = _number(radius_text)
    if None in (outer, wall, seat_outer, floor, gap, depth) or outer <= 0.0:
        return {}
    fitted = fit_geometry(outer, seat_outer, wall, floor, radius, gap, depth)
    current = {
        "wall": wall,
        "floor": floor,
        "turn_radius": radius,
        "max_depth": depth,
    }
    wanted = {
        "wall": fitted.wall_thickness_mm,
        "floor": fitted.floor_mm,
        "turn_radius": fitted.turn_radius_mm,
        "max_depth": fitted.max_depth_mm,
    }
    if radius is None:
        del wanted["turn_radius"]
    updates: dict[str, str] = {}
    for name, value in wanted.items():
        before = current[name]
        if before is not None and abs(before - value) < 1e-6:
            continue
        updates[name] = format_mm(value).replace(",", ".")
    return updates


def _resolve_scale(text: str) -> str:
    """Идентификатор лада из поля формы.

    Принимает строку: ключ вроде major или русскую подпись. Пустое поле —
    лад по умолчанию (натуральный минор). Возвращает ключ SCALE_STEPS; неизвестное отдаёт как есть,
    проверка параметров его отвергнет.
    """
    cleaned = text.strip()
    if not cleaned:
        return DEFAULT_SCALE
    if cleaned in SCALE_IDS:
        return cleaned
    folded = cleaned.casefold()
    for key, label in SCALE_LABELS.items():
        if label == cleaned or label.casefold() == folded:
            return key
        if scale_choice_label(key, "en").casefold() == folded:
            return key
        if scale_choice_label(key, "ru").casefold() == folded:
            return key
    return cleaned


def _resolve_slider_kind(text: str) -> str:
    """Идентификатор схемы слайдера из поля формы.

    Принимает строку: ключ end/u, русскую подпись или пустое. Пустое и
    «нет» — слайдера нет. Возвращает ключ; неизвестное отдаёт как есть,
    проверка параметров его отвергнет.
    """
    cleaned = text.strip()
    if is_slider_off_word(cleaned):
        return ""
    folded = cleaned.casefold()
    if folded in SLIDER_KINDS:
        return folded
    for key, label in SLIDER_KIND_LABELS.items():
        if label == cleaned or label.casefold() == folded:
            return key
        if slider_choice_label(key, "en").casefold() == folded:
            return key
        if slider_choice_label(key, "ru").casefold() == folded:
            return key
    return cleaned


def with_goal(form: FormInput, goal: str) -> FormInput:
    """Копия формы с другим режимом цели.

    Принимает форму и «note» или «length». Остальные поля не трогает.
    Возвращает новую FormInput.
    """
    return replace(form, goal=goal)


def _required_number(text: str, label: str, reasons: list[str]) -> float | None:
    """Обязательное число из поля.

    Принимает строку, подпись и список причин. Пустое и нечисловое
    дописывает в список. Возвращает float либо None, если строка не годится.
    """
    if not text.strip():
        reasons.append(f"{label}: {t('error.expected_number')}")
        return None
    value = _number(text)
    if value is None:
        reasons.append(f"{label}: {t('error.expected_number')}")
        return None
    return value


def _optional_number(text: str, label: str, reasons: list[str]) -> float | None:
    """Необязательное число. Пустая строка — значение по умолчанию.

    Принимает строку, подпись и список причин. Пустую строку считает
    пропуском и возвращает None. Нечисловое дописывает в причины и
    тоже возвращает None.
    """
    if not text.strip():
        return None
    value = _number(text)
    if value is None:
        reasons.append(f"{label}: {t('error.expected_number')}")
        return None
    return value


def _optional_int(text: str, label: str, reasons: list[str]) -> int | None:
    """Необязательное целое. Пустая строка — автоподбор.

    Принимает строку, подпись и список причин. Пустую строку считает
    пропуском, дробь и нечисловое дописывает в причины.
    Возвращает int либо None.
    """
    value = _optional_number(text, label, reasons)
    if value is None:
        return None
    if not math.isclose(value, round(value), abs_tol=1e-9):
        reasons.append(f"{label}: {t('error.expected_integer')}")
        return None
    return int(round(value))


def _number(text: str) -> float | None:
    """Число из строки с запятой или точкой.

    Принимает строку. Убирает пробелы и меняет запятую на точку.
    Возвращает конечный float либо None, если это не число.
    """
    cleaned = text.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value
