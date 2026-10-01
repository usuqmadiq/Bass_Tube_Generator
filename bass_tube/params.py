"""Общий объект входных параметров трубы и проверка набора до расчёта.

Режим один: нота с октавой либо длина корпуса. Конец трубы входит в готовый
модуль мембраны. Диаметр этого конца задаётся отдельно от диаметра трубы:
если они разные, между ними стоит конический переходник. Канал везде следует
из наружного диаметра и одной и той же стенки. Все длины — миллиметры.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bass_tube.acoustics.notes import NoteNameError, parse_note_name
from bass_tube.derived import fit_geometry
from bass_tube.constants import (
    A4_HZ,
    DEFAULT_FLOOR_MM,
    DEFAULT_HOLE_COUNT,
    DEFAULT_HOLE_DIAMETER_MM,
    DEFAULT_LAYOUT,
    DEFAULT_SCALE,
    DEFAULT_DRONE_TRIM_SEMITONES,
    DEFAULT_PRINT_SPLITS,
    DEFAULT_SLIDER_CLEARANCE_MM,
    DEFAULT_SLIDER_KIND,
    DEFAULT_SLIDER_PAIRS,
    DEFAULT_SLIDER_SEMITONES,
    DEFAULT_TRIM_SEMITONES,
    MIN_SLIDER_CLEARANCE_MM,
    DEFAULT_WALL_THICKNESS_MM,
    LAYOUT_BUNDLE,
    LAYOUTS,
    MAX_HOLES,
    MIN_SEAT_LENGTH_MM,
    SLIDER_KIND_LABELS,
    SLIDER_KINDS,
    MODULE_HOLE_MM,
    OPEN_END_CORRECTION_FACTOR,
    OUTER_DIAMETER_MM,
    PRINT_JOINT_MIN_WALL_MM,
    SCALE_IDS,
    SEAT_FIT_CLEARANCE_MM,
    SEAT_OUTER_DIAMETER_MM,
    SPEED_OF_SOUND_M_S,
    TRANSITION_HALF_ANGLE_DEG,
    TRIM_MIN_WALL_MM,
)


class ParamsError(ValueError):
    """Набор параметров трубы отвергнут.

    reasons — список причин по-русски. Строка исключения — те же причины,
    каждая с новой строки.
    """

    def __init__(self, reasons: list[str]) -> None:
        """Запоминает причины отказа.

        Принимает непустой список текстов. Сохраняет его в reasons и
        передаёт склейку в ValueError. Возвращает None.
        Пустой список не принимается: отказ без причины не имеет смысла.
        """
        if not reasons:
            raise ValueError("ParamsError без причин.")
        self.reasons = list(reasons)
        super().__init__("\n".join(self.reasons))


@dataclass(frozen=True, slots=True)
class TubeParams:
    """Проверенные параметры одной трубы.

    Цель — note либо body_length_mm. outer_diameter_mm — наружный диаметр
    трубы, seat_outer_diameter_mm — конца, который входит в модуль.
    transition_length_mm — длина конуса между ними, ноль при равных диаметрах.
    layout — только «bundle» (вязанка).
    straight_count — число прямых, только нечётное (выход в дне);
    None значит подбор по габариту.
    trim_semitones — ход подстройки вниз от ноты корпуса, ноль если трубки нет.
    slider_kind — «end», «u», «uu» или «uauto»; пустая строка — слайдера нет.
    slider_semitones — диапазон слайдера вниз.
    slider_pairs — число U-колен; ноль значит взять из схемы (u=1, uu=2)
    или подобрать при «U авто».
    slider_clearance_mm — радиальный зазор между каналом корпуса и царгой
    со всех сторон, не меньше 0,3 мм. print_splits — резать корпус и царгу
    на куски стола со стыками «папа — мама» без зазора; собранная высота
    может быть выше области печати. Стенка при разрезах не тоньше 1,6 мм. Если слайдер включён, трубка подстройки
    сама выключается: слайдер уже меняет длину. Слайдер нельзя задать
    вместе с отверстиями.
    hole_count — игровые дырки, до восьми; scale — лад от той же ноты.
    drone_note — нота второй трубы (дрон); None если голос один.
    drone_trim_semitones — подстройка дрона вниз, только у дрона: мелодия
    свои отверстия и слайдер не отдаёт. Насадка на две мембраны не входит
    в модель, шаг осей входов задаётся константой 48 мм при сборке пары.
    Наружный диаметр трубы главный: стенка, дно, радиус разворота и глубина
    габарита подгоняются под него, если иначе канал, колено или дно не сойдутся.
    floor_mm — материал цоколя между столом и нижней точкой канала.
    Высота под модуль мембраны (head_reserve_mm) в канал не входит.
    До калибровки головки delta_head_mm остаётся нулём.
    """

    note: str | None
    body_length_mm: float | None
    outer_diameter_mm: float
    seat_outer_diameter_mm: float
    wall_thickness_mm: float
    module_hole_mm: float
    seat_length_mm: float
    transition_length_mm: float
    max_height_mm: float
    max_width_mm: float
    max_depth_mm: float
    head_reserve_mm: float
    layout: str
    straight_count: int | None
    turn_radius_mm: float
    gap_mm: float
    floor_mm: float
    trim_semitones: int
    hole_count: int
    scale: str
    hole_diameter_mm: float
    slider_kind: str
    slider_semitones: int
    slider_pairs: int
    slider_clearance_mm: float
    print_splits: bool
    drone_note: str | None
    drone_trim_semitones: int
    delta_head_mm: float
    delta_out_mm: float
    delta_bends_mm: float
    speed_of_sound_m_s: float
    a4_hz: float

    def __post_init__(self) -> None:
        """Приводит ноты мелодии и дрона к виду C2 и отвергает набор.

        Ничего не принимает сверх полей объекта. Если запись ноты разобралась,
        заменяет note и drone_note на канонические. Пустой дрон снимает
        вторую трубу. Если набор невалиден, поднимает ParamsError, и объект
        не создаётся. При успехе возвращает None.
        """
        note_reason: str | None = None
        if self.note is not None:
            if not isinstance(self.note, str):
                note_reason = "Нота должна быть строкой вида C2."
            else:
                try:
                    spelling = parse_note_name(self.note).spelling
                except NoteNameError as exc:
                    note_reason = str(exc)
                else:
                    object.__setattr__(self, "note", spelling)

        drone_reason: str | None = None
        if self.drone_note is not None:
            if not isinstance(self.drone_note, str):
                drone_reason = "Нота дрона должна быть строкой вида C2."
            elif not self.drone_note.strip():
                object.__setattr__(self, "drone_note", None)
            else:
                try:
                    spelling = parse_note_name(self.drone_note).spelling
                except NoteNameError as exc:
                    drone_reason = f"Дрон: {exc}"
                else:
                    object.__setattr__(self, "drone_note", spelling)

        reasons = _collect_reasons(self, note_reason, drone_reason)
        if reasons:
            raise ParamsError(reasons)

    @property
    def bore_diameter_mm(self) -> float:
        """Внутренний диаметр канала трубы, мм.

        Ничего не принимает. Вычитает две стенки из наружного диаметра трубы.
        Возвращает диаметр канала. Отдельного поля канала нет.
        """
        return self.outer_diameter_mm - 2.0 * self.wall_thickness_mm

    @property
    def inner_radius_mm(self) -> float:
        """Внутренний радиус канала трубы a, мм.

        Ничего не принимает. Берёт половину bore_diameter_mm.
        Возвращает радиус, от которого зависит поправка открытого конца.
        """
        return self.bore_diameter_mm / 2.0

    @property
    def seat_bore_diameter_mm(self) -> float:
        """Канал внутри конца, который входит в модуль, мм.

        Ничего не принимает. Вычитает две стенки из диаметра конца.
        Возвращает диаметр канала у мембраны.
        """
        return self.seat_outer_diameter_mm - 2.0 * self.wall_thickness_mm

    @property
    def joint_clearance_mm(self) -> float:
        """Зазор пары по диаметру, мм.

        Ничего не принимает. Вычитает диаметр конца из отверстия модуля.
        Возвращает положительный зазор: конец входит в отверстие.
        """
        return self.module_hole_mm - self.seat_outer_diameter_mm

    @property
    def has_transition(self) -> bool:
        """Нужен ли переходник между концом и трубой.

        Ничего не принимает. Возвращает True, если длина конуса больше нуля.
        """
        return self.transition_length_mm > 0.0

    @property
    def joint_length_mm(self) -> float:
        """Длина стыка от мембраны: посадка и переходник, мм.

        Ничего не принимает. Весь стык лежит на первой прямой.
        Возвращает сумму длины посадки и конуса.
        """
        return self.seat_length_mm + self.transition_length_mm

    @property
    def has_drone(self) -> bool:
        """Нужна ли вторая труба (дрон) рядом с мелодией.

        Ничего не принимает. Возвращает True, если задана нота дрона.
        """
        return self.drone_note is not None


def tube_params(
    *,
    note: str | None = None,
    body_length_mm: float | None = None,
    outer_diameter_mm: float = OUTER_DIAMETER_MM,
    seat_outer_diameter_mm: float | None = None,
    wall_thickness_mm: float = DEFAULT_WALL_THICKNESS_MM,
    module_hole_mm: float = MODULE_HOLE_MM,
    seat_length_mm: float = MIN_SEAT_LENGTH_MM,
    transition_length_mm: float | None = None,
    max_height_mm: float,
    max_width_mm: float,
    max_depth_mm: float,
    head_reserve_mm: float,
    layout: str = DEFAULT_LAYOUT,
    straight_count: int | None = None,
    turn_radius_mm: float | None = None,
    gap_mm: float,
    floor_mm: float = DEFAULT_FLOOR_MM,
    trim_semitones: int = DEFAULT_TRIM_SEMITONES,
    hole_count: int = DEFAULT_HOLE_COUNT,
    scale: str = DEFAULT_SCALE,
    hole_diameter_mm: float = DEFAULT_HOLE_DIAMETER_MM,
    slider_kind: str = DEFAULT_SLIDER_KIND,
    slider_semitones: int = DEFAULT_SLIDER_SEMITONES,
    slider_pairs: int = DEFAULT_SLIDER_PAIRS,
    slider_clearance_mm: float = DEFAULT_SLIDER_CLEARANCE_MM,
    print_splits: bool = DEFAULT_PRINT_SPLITS,
    drone_note: str | None = None,
    drone_trim_semitones: int = DEFAULT_DRONE_TRIM_SEMITONES,
    delta_head_mm: float = 0.0,
    delta_out_mm: float | None = None,
    delta_bends_mm: float = 0.0,
    speed_of_sound_m_s: float = SPEED_OF_SOUND_M_S,
    a4_hz: float = A4_HZ,
) -> TubeParams:
    """Собирает и проверяет входные параметры трубы.

    Принимает цель (нота с октавой или длина корпуса), сечение трубы и конца,
    габарит, укладку, стык, дно и три поправки. Наружный диаметр трубы главный:
    стенка, дно, радиус разворота и глубина габарита подгоняются под него.
    Конец под модуль подгоняется под отверстие: пустой или не входящий в
    отверстие берётся как отверстие минус штатный зазор пары, переходник к
    трубе любого диаметра строится сам.
    Пустой радиус разворота берёт минимум под диаметр и зазор. Если
    delta_out_mm не задан, подставляет 0,6 внутреннего радиуса трубы. Если
    transition_length_mm не задан или ноль при разных диаметрах, считает
    длину конуса по половине угла 15°. При равных диаметрах переходника нет.
    Высота head_reserve_mm резервируется под модуль и в канал не входит.
    trim_semitones — сколько полутонов вниз можно уйти выдвижной трубкой;
    ноль, если подстройки нет. Если задан слайдер, подстройка сама становится
    нулём: слайдер уже меняет длину, поле трубки гасить не нужно.
    slider_kind, slider_semitones и slider_pairs — слайдер: выдвижной конец,
    одно или несколько U-колен, «U авто» подбирает число колен по прямым;
    не вместе с дырками. slider_clearance_mm — зазор вокруг царги со всех
    сторон, не меньше 0,3 мм. print_splits — разрезы на куски стола со
    стыками «папа — мама» без зазора; собранная вязанка может быть выше
    области печати, стенка при этом не тоньше 1,6 мм.
    hole_count — игровые отверстия, до восьми; нота корпуса — тоника лада
    scale. drone_note — нота дрона; пустая — один голос. Дрон считается
    отдельной трубой: без отверстий и слайдера мелодии, со своей подстройкой
    drone_trim_semitones (ноль — трубки у дрона нет). Насадку на две
    мембраны генератор не строит. Скорость звука по умолчанию — константа
    мира, окно её не отдаёт.

    Возвращает неизменяемый TubeParams. Невалидный набор поднимает ParamsError
    с текстом причины: короткая посадка, нулевая стенка, нота без октавы,
    одновременно нота и длина.
    """
    seat_outer_diameter_mm = resolve_seat_diameter_mm(seat_outer_diameter_mm, module_hole_mm)
    fitted = None
    if (
        _is_number(outer_diameter_mm)
        and _is_number(seat_outer_diameter_mm)
        and _is_number(wall_thickness_mm)
        and _is_number(floor_mm)
        and _is_number(gap_mm)
        and _is_number(max_depth_mm)
        and float(outer_diameter_mm) > 0.0
        and (turn_radius_mm is None or _is_number(turn_radius_mm))
    ):
        fitted = fit_geometry(
            float(outer_diameter_mm),
            float(seat_outer_diameter_mm),
            float(wall_thickness_mm),
            float(floor_mm),
            None if turn_radius_mm is None else float(turn_radius_mm),
            float(gap_mm),
            float(max_depth_mm),
        )
        wall_thickness_mm = fitted.wall_thickness_mm
        floor_mm = fitted.floor_mm
        turn_radius_mm = fitted.turn_radius_mm
        max_depth_mm = fitted.max_depth_mm
    elif turn_radius_mm is None:
        turn_radius_mm = 0.0

    if delta_out_mm is None:
        delta_out_mm = _default_open_end_correction_mm(
            outer_diameter_mm,
            wall_thickness_mm,
        )
    transition = _resolve_transition_mm(
        transition_length_mm,
        outer_diameter_mm,
        seat_outer_diameter_mm,
    )

    kind = _as_slider_kind(slider_kind)
    steps = _as_slider_semitones(slider_semitones)
    pairs = _as_slider_pairs(slider_pairs)
    splits = _as_print_splits(print_splits)
    clearance = _as_slider_clearance(slider_clearance_mm)
    trim_value = _as_trim_semitones(trim_semitones)
    if kind and steps > 0:
        trim_value = 0
    drone = _as_drone_note(drone_note)
    drone_trim = _as_drone_trim_semitones(drone_trim_semitones)
    if drone is None:
        drone_trim = 0

    return TubeParams(
        note=note,
        body_length_mm=body_length_mm,
        outer_diameter_mm=outer_diameter_mm,
        seat_outer_diameter_mm=seat_outer_diameter_mm,
        wall_thickness_mm=wall_thickness_mm,
        module_hole_mm=module_hole_mm,
        seat_length_mm=seat_length_mm,
        transition_length_mm=transition,
        max_height_mm=max_height_mm,
        max_width_mm=max_width_mm,
        max_depth_mm=max_depth_mm,
        head_reserve_mm=head_reserve_mm,
        layout=layout,
        straight_count=straight_count,
        turn_radius_mm=turn_radius_mm,
        gap_mm=gap_mm,
        floor_mm=floor_mm,
        trim_semitones=trim_value,
        hole_count=_as_hole_count(hole_count),
        scale=str(scale).strip() if isinstance(scale, str) else scale,
        hole_diameter_mm=hole_diameter_mm,
        slider_kind=kind,
        slider_semitones=steps,
        slider_pairs=pairs,
        slider_clearance_mm=clearance,
        print_splits=splits,
        drone_note=drone,
        drone_trim_semitones=drone_trim,
        delta_head_mm=delta_head_mm,
        delta_out_mm=delta_out_mm,
        delta_bends_mm=delta_bends_mm,
        speed_of_sound_m_s=speed_of_sound_m_s,
        a4_hz=a4_hz,
    )


def resolve_seat_diameter_mm(
    seat_outer_diameter_mm: float | None,
    module_hole_mm: float,
) -> float | None:
    """Наружный диаметр конца, который реально войдёт в модуль.

    Принимает заданный диаметр конца (None — не задан) и отверстие модуля.
    Пустой конец и конец не тоньше отверстия заменяет на отверстие минус
    штатный зазор пары SEAT_FIT_CLEARANCE_MM: переходник к трубе потом
    строится сам. Нечисловые значения отдаёт как есть — их отвергнет
    проверка. Возвращает миллиметры или исходное значение.
    """
    if not _is_number(module_hole_mm):
        return SEAT_OUTER_DIAMETER_MM if seat_outer_diameter_mm is None else seat_outer_diameter_mm
    fitted = float(module_hole_mm) - SEAT_FIT_CLEARANCE_MM
    if fitted <= 0.0:
        return SEAT_OUTER_DIAMETER_MM if seat_outer_diameter_mm is None else seat_outer_diameter_mm
    if seat_outer_diameter_mm is None:
        return fitted
    if _is_number(seat_outer_diameter_mm) and float(seat_outer_diameter_mm) >= float(module_hole_mm):
        return fitted
    return seat_outer_diameter_mm


def _default_open_end_correction_mm(
    outer_diameter_mm: float,
    wall_thickness_mm: float,
) -> float:
    """Считает стартовую поправку открытого конца.

    Принимает наружный диаметр трубы и толщину стенки в миллиметрах.
    Возвращает 0,6 внутреннего радиуса. Если канал из этих чисел не
    получается, возвращает 0: набор всё равно отвергнется проверкой сечения,
    и этот нуль вызывающему коду не отдаётся.
    """
    if not _is_number(outer_diameter_mm) or not _is_number(wall_thickness_mm):
        return 0.0
    bore = float(outer_diameter_mm) - 2.0 * float(wall_thickness_mm)
    if not math.isfinite(bore) or bore <= 0.0:
        return 0.0
    return OPEN_END_CORRECTION_FACTOR * bore / 2.0


def _resolve_transition_mm(
    transition_length_mm: float | None,
    outer_diameter_mm: float,
    seat_outer_diameter_mm: float,
) -> float:
    """Длина переходника от конца к трубе.

    Принимает заданную длину или None и два наружных диаметра.
    При равных диаметрах возвращает 0: конуса нет. Если длина не задана
    или ноль, а диаметры разные, берёт разницу радиусов, делённую на
    тангенс 15°: нулевой переходник при ступеньке не оставляем. Заданное
    ненулевое число возвращает как есть, его проверит _check_joint.
    Нечисловые диаметры дают 0: набор и так отвергнется.
    """
    if not _is_number(outer_diameter_mm) or not _is_number(seat_outer_diameter_mm):
        return 0.0
    step = abs(float(outer_diameter_mm) - float(seat_outer_diameter_mm)) / 2.0
    if not math.isfinite(step) or step < 1e-9:
        return 0.0
    if transition_length_mm is None or (
        _is_number(transition_length_mm) and abs(float(transition_length_mm)) < 1e-9
    ):
        return step / math.tan(math.radians(TRANSITION_HALF_ANGLE_DEG))
    return float(transition_length_mm)


def _is_number(value: object) -> bool:
    """Число ли это, без булевых значений.

    Принимает сырое значение. Возвращает True для int и float.
    """
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _collect_reasons(
    params: TubeParams,
    note_reason: str | None,
    drone_reason: str | None = None,
) -> list[str]:
    """Собирает все причины, по которым набор параметров нельзя считать.

    Принимает уже собранный объект, ошибку имени ноты мелодии и ошибку
    имени ноты дрона, если они есть. Каждое число, включая три поправки,
    читается один раз; знак поправки не ограничивается. Затем проверяются
    цель, сечение, стык, габарит, укладка, дрон и опорный строй.
    Возвращает список текстов; пустой список означает, что набор годится.
    """
    reasons: list[str] = []
    numbers = _parse_numbers(params, reasons)
    _check_goal(params, reasons, note_reason, numbers)
    _check_section(reasons, numbers)
    _check_print_joint(params, reasons, numbers)
    _check_joint(reasons, numbers)
    _check_envelope(reasons, numbers)
    _check_layout(params, reasons, numbers)
    _check_slider(params, reasons, numbers)
    _check_drone(params, reasons, drone_reason, numbers)
    _check_reference(numbers, reasons)
    return reasons


def _parse_numbers(params: TubeParams, reasons: list[str]) -> dict[str, float | None]:
    """Читает числовые поля один раз.

    Принимает параметры и список причин. Длину корпуса пропускает, если её
    нет: это режим ноты, а не ошибка. Возвращает словарь конечных чисел;
    у отвергнутого поля значение None, причина уже лежит в списке.
    """
    fields = (
        ("outer_diameter_mm", "Наружный диаметр трубы", params.outer_diameter_mm),
        ("seat_outer_diameter_mm", "Диаметр конца под модуль", params.seat_outer_diameter_mm),
        ("wall_thickness_mm", "Толщина стенки", params.wall_thickness_mm),
        ("module_hole_mm", "Отверстие модуля", params.module_hole_mm),
        ("seat_length_mm", "Длина посадки", params.seat_length_mm),
        ("transition_length_mm", "Длина переходника", params.transition_length_mm),
        ("max_height_mm", "Максимальная высота", params.max_height_mm),
        ("max_width_mm", "Максимальная ширина", params.max_width_mm),
        ("max_depth_mm", "Максимальная глубина", params.max_depth_mm),
        ("head_reserve_mm", "Резерв высоты под модуль", params.head_reserve_mm),
        ("turn_radius_mm", "Радиус разворота", params.turn_radius_mm),
        ("gap_mm", "Зазор между трубами", params.gap_mm),
        ("floor_mm", "Дно под каналом", params.floor_mm),
        ("trim_semitones", "Подстройка", params.trim_semitones),
        ("hole_count", "Число отверстий", params.hole_count),
        ("slider_semitones", "Слайдер", params.slider_semitones),
        ("slider_pairs", "Колен слайдера", params.slider_pairs),
        ("slider_clearance_mm", "Зазор слайдера", params.slider_clearance_mm),
        ("drone_trim_semitones", "Подстройка дрона", params.drone_trim_semitones),
        ("hole_diameter_mm", "Диаметр отверстия", params.hole_diameter_mm),
        ("delta_head_mm", "Поправка головки", params.delta_head_mm),
        ("delta_out_mm", "Поправка открытого конца", params.delta_out_mm),
        ("delta_bends_mm", "Поправка изгибов", params.delta_bends_mm),
        ("speed_of_sound_m_s", "Скорость звука", params.speed_of_sound_m_s),
        ("a4_hz", "Частота A4", params.a4_hz),
    )
    numbers: dict[str, float | None] = {
        key: _as_finite(label, value, reasons) for key, label, value in fields
    }
    if params.body_length_mm is None:
        numbers["body_length_mm"] = None
    else:
        numbers["body_length_mm"] = _as_finite(
            "Длина корпуса", params.body_length_mm, reasons
        )
    return numbers


def _check_goal(
    params: TubeParams,
    reasons: list[str],
    note_reason: str | None,
    numbers: dict[str, float | None],
) -> None:
    """Проверяет, что цель ровно одна: нота либо длина корпуса.

    Принимает параметры, список причин, ошибку разбора ноты и уже
    прочитанные числа. Дописывает причины в список. Ничего не возвращает.
    """
    has_note = params.note is not None or note_reason is not None
    has_length = params.body_length_mm is not None

    if has_note and has_length:
        reasons.append(
            "Одновременно заданы нота и длина корпуса. "
            "Нужен один режим: либо нота с октавой, либо длина корпуса."
        )
    elif not has_note and not has_length:
        reasons.append(
            "Не задана цель: укажите ноту с октавой либо длину корпуса."
        )

    if note_reason is not None:
        reasons.append(note_reason)

    length = numbers["body_length_mm"]
    seat = numbers["seat_length_mm"]
    if length is None:
        return
    if length <= 0.0:
        reasons.append("Длина корпуса должна быть больше нуля.")
        return
    if seat is not None and length < seat:
        reasons.append(
            f"Длина корпуса {_format_mm(length)} мм короче посадки "
            f"{_format_mm(seat)} мм."
        )


def _check_section(reasons: list[str], numbers: dict[str, float | None]) -> None:
    """Проверяет диаметры трубы и конца вместе со стенкой.

    Принимает список причин и уже прочитанные числа. Нулевая и отрицательная
    стенка отвергаются, как и стенка, съедающая канал трубы или конца.
    Ничего не возвращает.
    """
    outer = numbers["outer_diameter_mm"]
    seat_outer = numbers["seat_outer_diameter_mm"]
    wall = numbers["wall_thickness_mm"]

    for label, value in (("Наружный диаметр трубы", outer), ("Диаметр конца под модуль", seat_outer)):
        if value is not None and value <= 0.0:
            reasons.append(f"{label} должен быть больше нуля.")

    if wall is None:
        return
    if wall == 0.0:
        reasons.append("Толщина стенки равна нулю.")
        return
    if wall < 0.0:
        reasons.append(f"Толщина стенки отрицательная ({_format_mm(wall)} мм).")
        return
    for label, value in (("трубы", outer), ("конца", seat_outer)):
        if value is not None and value > 0.0 and value - 2.0 * wall <= 0.0:
            reasons.append(
                f"Стенка {_format_mm(wall)} мм не оставляет канала внутри "
                f"диаметра {label} {_format_mm(value)} мм."
            )


def _check_print_joint(
    params: TubeParams,
    reasons: list[str],
    numbers: dict[str, float | None],
) -> None:
    """Проверяет, что стенку можно разделить на стык «папа — мама».

    Принимает параметры, список причин и уже прочитанные числа. При
    включённых разрезах стенка тоньше PRINT_JOINT_MIN_WALL_MM отвергается:
    папа и мама получают по полстенки и ломаются при сборке. Ничего не
    возвращает.
    """
    wall = numbers["wall_thickness_mm"]
    if not params.print_splits or wall is None or wall <= 0.0:
        return
    if wall < PRINT_JOINT_MIN_WALL_MM - 1e-9:
        reasons.append(
            f"Стенка {_format_mm(wall)} мм тоньше {_format_mm(PRINT_JOINT_MIN_WALL_MM)} мм: "
            "при разрезах на печать стык делит её пополам, и папа с мамой "
            "сломаются при сборке. Сделайте стенку толще или выключите разрезы."
        )


def _check_joint(reasons: list[str], numbers: dict[str, float | None]) -> None:
    """Проверяет посадку конца в отверстие модуля и переходник.

    Принимает список причин и уже прочитанные числа. Посадка короче 8 мм
    отвергается. Конец, который не входит в отверстие, сюда не доходит:
    его уже ужала resolve_seat_diameter_mm. Нулевой переходник при разных
    диаметрах тоже не доходит: его заменяет конус 15°. Диаметр самой трубы
    с отверстием модуля не сравнивается: для этого есть переходник.
    Ничего не возвращает.
    """
    hole = numbers["module_hole_mm"]
    seat = numbers["seat_length_mm"]
    seat_outer = numbers["seat_outer_diameter_mm"]
    outer = numbers["outer_diameter_mm"]
    transition = numbers["transition_length_mm"]

    if seat is not None and seat < MIN_SEAT_LENGTH_MM:
        reasons.append(
            f"Длина посадки {_format_mm(seat)} мм короче минимума "
            f"{_format_mm(MIN_SEAT_LENGTH_MM)} мм."
        )

    if hole is not None and hole <= 0.0:
        reasons.append("Отверстие модуля должно быть больше нуля.")

    if transition is None or outer is None or seat_outer is None:
        return
    if transition < 0.0:
        reasons.append("Длина переходника отрицательная.")
    elif abs(outer - seat_outer) > 1e-9 and transition == 0.0:
        reasons.append(
            "Диаметры трубы и конца разные, а переходник нулевой длины: "
            "в канале получилась бы ступенька."
        )


def _check_envelope(reasons: list[str], numbers: dict[str, float | None]) -> None:
    """Проверяет габарит и резерв высоты под модуль мембраны.

    Принимает список причин и уже прочитанные числа. Резерв в канал не входит,
    поэтому он должен оставлять положительную высоту под трубу.
    Ничего не возвращает.
    """
    height = numbers["max_height_mm"]
    width = numbers["max_width_mm"]
    depth = numbers["max_depth_mm"]
    reserve = numbers["head_reserve_mm"]

    for label, value in (
        ("Максимальная высота", height),
        ("Максимальная ширина", width),
        ("Максимальная глубина", depth),
    ):
        if value is not None and value <= 0.0:
            reasons.append(f"{label} должна быть больше нуля.")

    if reserve is not None and reserve < 0.0:
        reasons.append("Резерв высоты под модуль мембраны отрицательный.")

    if (
        height is not None
        and reserve is not None
        and height > 0.0
        and reserve >= height
    ):
        reasons.append(
            "Резерв высоты под модуль мембраны не оставляет места каналу."
        )


def _check_layout(
    params: TubeParams,
    reasons: list[str],
    numbers: dict[str, float | None],
) -> None:
    """Проверяет вид укладки, число прямых, радиус, зазор, дно и подстройку.

    Принимает параметры, список причин и уже прочитанные числа.
    Влезает ли укладка в габарит, здесь не решается. Дно и радиус разворота
    подгоняются под диаметр трубы до этой проверки; условия остаются
    страховкой, если подгонка не сработала. Число прямых, если задано,
    только нечётное: выход всегда в дне. Подстройка — целое число
    полутонов вниз, ноль если трубки нет. Ничего не возвращает.
    """
    if params.layout not in LAYOUTS:
        reasons.append(
            f"Укладка «{params.layout}» не известна: "
            f"есть «{LAYOUT_BUNDLE}»."
        )

    count = params.straight_count
    if count is not None:
        if isinstance(count, bool) or not isinstance(count, int):
            reasons.append("Число прямых должно быть целым.")
        elif count < 1:
            reasons.append(f"Число прямых {count} меньше 1.")
        elif count % 2 == 0:
            reasons.append(
                "Выход должен открываться в дне: нужно нечётное число прямых."
            )

    radius = numbers["turn_radius_mm"]
    gap = numbers["gap_mm"]
    floor = numbers["floor_mm"]
    wall = numbers["wall_thickness_mm"]

    if radius is not None and radius <= 0.0:
        reasons.append("Радиус разворота должен быть больше нуля.")
    if gap is not None and gap < 0.0:
        reasons.append("Зазор между соседними трубами отрицательный.")
    if floor is not None and wall is not None and wall > 0.0 and floor <= wall:
        reasons.append(
            f"Дно под каналом {_format_mm(floor)} мм не толще стенки "
            f"{_format_mm(wall)} мм: нижний разворот вылезет под стол."
        )
    trim = numbers["trim_semitones"]
    if trim is not None:
        if trim < 0.0:
            reasons.append("Подстройка в полутонах отрицательная.")
        elif abs(trim - round(trim)) > 1e-9:
            reasons.append("Подстройка в полутонах должна быть целым числом.")
    count = numbers["hole_count"]
    if count is not None:
        if count < 0.0:
            reasons.append("Число отверстий отрицательное.")
        elif abs(count - round(count)) > 1e-9:
            reasons.append("Число отверстий должно быть целым.")
        elif round(count) > MAX_HOLES:
            reasons.append(f"Отверстий больше {MAX_HOLES}: пальцев не хватает.")
    if params.hole_count > 0:
        if not isinstance(params.scale, str) or params.scale not in SCALE_IDS:
            known = ", ".join(SCALE_IDS)
            reasons.append(f"Лад «{params.scale}» не известен: есть {known}.")
        diameter = numbers["hole_diameter_mm"]
        bore = None
        outer = numbers["outer_diameter_mm"]
        wall = numbers["wall_thickness_mm"]
        if outer is not None and wall is not None:
            bore = outer - 2.0 * wall
        if diameter is not None:
            if diameter <= 0.0:
                reasons.append("Диаметр отверстия должен быть больше нуля.")
            elif bore is not None and bore > 0.0 and diameter >= bore:
                reasons.append(
                    f"Диаметр отверстия {_format_mm(diameter)} мм не меньше "
                    f"канала {_format_mm(bore)} мм."
                )


def _check_slider(
    params: TubeParams,
    reasons: list[str],
    numbers: dict[str, float | None],
) -> None:
    """Проверяет схему слайдера, зазор царги и что он не смешан с дырками.

    Принимает параметры, список причин и уже прочитанные числа. Две схемы
    слайдера в одном наборе задать нельзя: поле схемы одно. Слайдер с
    отверстиями отвергается. Число U-колен — целое не меньше нуля; ноль
    значит взять из схемы или подобрать. Зазор вокруг царги не меньше 0,3 мм
    со всех сторон; при включённом слайдере внутри вставки ещё должен
    остаться канал. Трубка подстройки при слайдере уже выключена в
    tube_params, здесь её не проверяют. Ничего не возвращает.
    """
    kind = params.slider_kind
    if kind and kind not in SLIDER_KINDS:
        known = ", ".join(SLIDER_KIND_LABELS[item] for item in SLIDER_KINDS)
        reasons.append(f"Схема слайдера «{kind}» не известна: есть {known}.")
    steps = numbers["slider_semitones"]
    if steps is not None:
        if steps < 0.0:
            reasons.append("Слайдер в полутонах отрицательный.")
        elif abs(steps - round(steps)) > 1e-9:
            reasons.append("Слайдер в полутонах должен быть целым числом.")
    has_slider = bool(kind) and params.slider_semitones > 0
    if params.slider_semitones > 0 and not kind:
        reasons.append(
            "Задан ход слайдера, но не выбрана схема: "
            "выдвижной конец, U-колено, двойное U или U авто."
        )
    pairs = numbers["slider_pairs"]
    if pairs is not None:
        if pairs < 0.0:
            reasons.append("Число колен слайдера отрицательное.")
        elif abs(pairs - round(pairs)) > 1e-9:
            reasons.append("Число колен слайдера должно быть целым.")
        elif kind == "end" and round(pairs) > 0:
            reasons.append("Выдвижному концу число U-колен не нужно.")
    if has_slider and params.hole_count > 0:
        reasons.append(
            "Слайдер и отверстия одновременно нельзя: выберите одно управление."
        )
    clearance = numbers["slider_clearance_mm"]
    if clearance is not None:
        if clearance < MIN_SLIDER_CLEARANCE_MM:
            reasons.append(
                f"Зазор слайдера {_format_mm(clearance)} мм меньше минимума "
                f"{_format_mm(MIN_SLIDER_CLEARANCE_MM)} мм со всех сторон."
            )
        elif has_slider:
            outer = numbers["outer_diameter_mm"]
            wall = numbers["wall_thickness_mm"]
            if outer is not None and wall is not None:
                bore = outer - 2.0 * wall
                tenon = bore - 2.0 * clearance
                inner = tenon - 2.0 * min(wall, TRIM_MIN_WALL_MM)
                if tenon <= 0.0 or inner <= 0.0:
                    reasons.append(
                        "Зазор слайдера слишком большой: "
                        "внутри царги не остаётся канала."
                    )


def _check_drone(
    params: TubeParams,
    reasons: list[str],
    drone_reason: str | None,
    numbers: dict[str, float | None],
) -> None:
    """Проверяет ноту дрона и его подстройку.

    Принимает параметры, список причин, ошибку разбора ноты дрона и уже
    прочитанные числа. Пустой дрон — один голос, подстройка дрона тогда
    не смотрится. Нота дрона та же запись, что у мелодии. Подстройка —
    целое число полутонов вниз, ноль если трубки у дрона нет.
    Ничего не возвращает.
    """
    if drone_reason is not None:
        reasons.append(drone_reason)
    if params.drone_note is None and drone_reason is None:
        return
    trim = numbers["drone_trim_semitones"]
    if trim is None:
        return
    if trim < 0.0:
        reasons.append("Подстройка дрона в полутонах отрицательная.")
    elif abs(trim - round(trim)) > 1e-9:
        reasons.append("Подстройка дрона в полутонах должна быть целым числом.")


def _check_reference(numbers: dict[str, float | None], reasons: list[str]) -> None:
    """Проверяет частоту ля и скорость звука, если её передали снаружи.

    Принимает уже прочитанные числа и список причин. Скорость звука в окне
    не задаётся — константа мира; здесь она проверяется только если набор
    собрали вручную. A4 должна быть положительной. Ничего не возвращает.
    """
    speed = numbers["speed_of_sound_m_s"]
    a4 = numbers["a4_hz"]
    if speed is not None and speed <= 0.0:
        reasons.append("Скорость звука должна быть больше нуля.")
    if a4 is not None and a4 <= 0.0:
        reasons.append("Частота A4 должна быть больше нуля.")


def _as_finite(label: str, value: object, reasons: list[str]) -> float | None:
    """Проверяет, что значение — конечное число.

    Принимает подпись поля, сырое значение и список причин.
    Если значение не число или не конечное, дописывает причину.
    Возвращает float либо None, когда значение отвергнуто.
    """
    if not _is_number(value):
        reasons.append(f"{label}: ожидалось число.")
        return None
    number = float(value)
    if not math.isfinite(number):
        reasons.append(f"{label}: нужно конечное число.")
        return None
    return number


def _as_drone_note(value: object) -> str | None:
    """Нота дрона или её отсутствие.

    Принимает сырое значение. None, пустая строка и пробелы — дрона нет,
    возвращает None. Нестроковое поднимает ParamsError. Непустую строку
    отдаёт как есть: каноническую запись и ошибку октавы проверит
    конструктор TubeParams. Возвращает строку или None.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ParamsError(["Нота дрона должна быть строкой вида C2."])
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned


def _as_drone_trim_semitones(value: object) -> int:
    """Целое число полутонов подстройки дрона вниз.

    Принимает сырое значение. Ноль — трубки у дрона нет. Отрицательное,
    нецелое и нечисловое поднимает ParamsError. Возвращает int.
    """
    if isinstance(value, bool) or not _is_number(value):
        raise ParamsError(["Подстройка дрона в полутонах: ожидалось число."])
    number = float(value)
    if not math.isfinite(number):
        raise ParamsError(["Подстройка дрона в полутонах: нужно конечное число."])
    if number < 0.0:
        raise ParamsError(["Подстройка дрона в полутонах отрицательная."])
    if abs(number - round(number)) > 1e-9:
        raise ParamsError(["Подстройка дрона в полутонах должна быть целым числом."])
    return int(round(number))


def _as_trim_semitones(value: object) -> int:
    """Целое число полутонов подстройки вниз.

    Принимает сырое значение. Ноль — трубки нет. Отрицательное, нецелое
    и нечисловое поднимает ParamsError. Возвращает int.
    """
    if isinstance(value, bool) or not _is_number(value):
        raise ParamsError(["Подстройка в полутонах: ожидалось число."])
    number = float(value)
    if not math.isfinite(number):
        raise ParamsError(["Подстройка в полутонах: нужно конечное число."])
    if number < 0.0:
        raise ParamsError(["Подстройка в полутонах отрицательная."])
    if abs(number - round(number)) > 1e-9:
        raise ParamsError(["Подстройка в полутонах должна быть целым числом."])
    return int(round(number))


def _as_hole_count(value: object) -> int:
    """Целое число игровых отверстий.

    Принимает сырое значение. Ноль — дырок нет. Больше восьми, отрицательное
    и нецелое поднимает ParamsError. Возвращает int.
    """
    if isinstance(value, bool) or not _is_number(value):
        raise ParamsError(["Число отверстий: ожидалось число."])
    number = float(value)
    if not math.isfinite(number):
        raise ParamsError(["Число отверстий: нужно конечное число."])
    if number < 0.0:
        raise ParamsError(["Число отверстий отрицательное."])
    if abs(number - round(number)) > 1e-9:
        raise ParamsError(["Число отверстий должно быть целым."])
    count = int(round(number))
    if count > MAX_HOLES:
        raise ParamsError([f"Отверстий больше {MAX_HOLES}: пальцев не хватает."])
    return count


def _as_slider_kind(value: object) -> str:
    """Идентификатор схемы слайдера.

    Принимает сырое значение: ключ end/u, русскую подпись или пустую строку.
    Пустое, «нет» и «none» означают, что слайдера нет. Нестроковое поднимает
    ParamsError. Неизвестный ключ возвращает как есть: его отвергнет проверка
    набора. Возвращает канонический ключ или пустую строку.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ParamsError(["Схема слайдера: ожидалась строка."])
    cleaned = value.strip()
    if not cleaned or cleaned in ("none", "нет"):
        return ""
    if cleaned in SLIDER_KINDS:
        return cleaned
    for key, label in SLIDER_KIND_LABELS.items():
        if label == cleaned:
            return key
    return cleaned


def _as_slider_semitones(value: object) -> int:
    """Целое число полутонов слайдера вниз.

    Принимает сырое значение. Ноль — слайдера нет. Отрицательное, нецелое
    и нечисловое поднимает ParamsError. Возвращает int.
    """
    if isinstance(value, bool) or not _is_number(value):
        raise ParamsError(["Слайдер в полутонах: ожидалось число."])
    number = float(value)
    if not math.isfinite(number):
        raise ParamsError(["Слайдер в полутонах: нужно конечное число."])
    if number < 0.0:
        raise ParamsError(["Слайдер в полутонах отрицательный."])
    if abs(number - round(number)) > 1e-9:
        raise ParamsError(["Слайдер в полутонах должен быть целым числом."])
    return int(round(number))


def _as_slider_pairs(value: object) -> int:
    """Число подвижных U-колен слайдера.

    Принимает сырое значение. Ноль — взять из схемы или подобрать при
    «U авто». Отрицательное, нецелое и нечисловое поднимает ParamsError.
    Возвращает int.
    """
    if isinstance(value, bool) or not _is_number(value):
        raise ParamsError(["Число колен слайдера: ожидалось число."])
    number = float(value)
    if not math.isfinite(number):
        raise ParamsError(["Число колен слайдера: нужно конечное число."])
    if number < 0.0:
        raise ParamsError(["Число колен слайдера отрицательное."])
    if abs(number - round(number)) > 1e-9:
        raise ParamsError(["Число колен слайдера должно быть целым числом."])
    return int(round(number))


def _as_print_splits(value: object) -> bool:
    """Нужны ли разрезы корпуса и царги на куски области печати.

    Принимает bool, число или строку (да/нет, 1/0, true/false). Непонятное
    поднимает ParamsError. Возвращает bool.
    """
    if isinstance(value, bool):
        return value
    if _is_number(value):
        number = float(value)
        if not math.isfinite(number):
            raise ParamsError(["Разрезы на печать: нужно конечное число."])
        return abs(number) > 1e-9
    if not isinstance(value, str):
        raise ParamsError(["Разрезы на печать: ожидалось да или нет."])
    cleaned = value.strip().casefold()
    if cleaned in ("1", "true", "yes", "да", "on"):
        return True
    if cleaned in ("0", "false", "no", "нет", "off", ""):
        return False
    raise ParamsError([f"Разрезы на печать «{value}» не понятны: напишите да или нет."])


def _as_slider_clearance(value: object) -> float:
    """Радиальный зазор вокруг царги слайдера, миллиметры.

    Принимает сырое значение. Это зазор со всех сторон между каналом
    корпуса и наружной стенкой вставки. Меньше 0,3 мм, нечисловое и
    неконечное поднимает ParamsError. Возвращает float.
    """
    if isinstance(value, bool) or not _is_number(value):
        raise ParamsError(["Зазор слайдера: ожидалось число."])
    number = float(value)
    if not math.isfinite(number):
        raise ParamsError(["Зазор слайдера: нужно конечное число."])
    if number < MIN_SLIDER_CLEARANCE_MM:
        raise ParamsError(
            [
                f"Зазор слайдера {_format_mm(number)} мм меньше минимума "
                f"{_format_mm(MIN_SLIDER_CLEARANCE_MM)} мм со всех сторон."
            ]
        )
    return number


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает короткую запись: целое без дроби,
    иначе до трёх знаков после запятой без хвостовых нулей.
    """
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")
