"""Слайдер длины: выдвижной конец или семейство подвижных U-колен.

Схемы не смешиваются. Верхняя нота задаёт минимальную длину корпуса
(слайдер задвинут). Выдвижение удлиняет путь: у конца примерно на ход x,
у каждого U-колена — на 2x на колено (q = 2 × число колен). Двойное U —
два колена, q = 4; «U авто» берёт все нижние колена укладки, кроме выхода.
Вложенные участки телескопа в длину не считаются дважды. Положения
полутонов по ходу не равномерны: каждый следующий полутон требует большего
смещения, чем предыдущий. С игровыми отверстиями слайдер не сочетается.
Царга уже канала на два радиальных зазора, не меньше 0,3 мм со всех сторон.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from bass_tube.acoustics.notes import (
    NoteNameError,
    midi_number,
    note_from_midi,
    parse_note_name,
    shift_midi,
)
from bass_tube.acoustics.tuning import Tuning, TuningError, resolve_tuning
from bass_tube.constants import (
    PRINT_JOINT_MIN_WALL_MM,
    PRINT_PLUG_MM,
    SLIDER_END,
    SLIDER_KIND_LABELS,
    SLIDER_KINDS,
    SLIDER_U,
    SLIDER_U_FAMILY,
    SLIDER_UAUTO,
    SLIDER_UU,
    TRIM_FLANGE_MM,
    TRIM_MIN_WALL_MM,
    TRIM_OVERLAP_MM,
)
from bass_tube.params import TubeParams


class SliderError(ValueError):
    """Слайдер нельзя посчитать. Текст исключения — причина."""


@dataclass(frozen=True, slots=True)
class SliderStop:
    """Одно положение слайдера на целый полутон вниз от верхней ноты.

    semitones — сколько полутонов вниз от задвинутого конца. extra_length_mm —
    сколько миллиметров пути добавляет это положение (ΔL). travel_mm — ход
    механики: extra / q. У выдвижного конца q = 1, у семейства U
    q = 2 × число колен.
    """

    semitones: int
    note: str
    extra_length_mm: float
    travel_mm: float


@dataclass(frozen=True, slots=True)
class SliderPlan:
    """Размеры слайдера, ноты по краям хода и стопы каждого полутона.

    kind — «end», «u», «uu» или «uauto». pairs — число U-колен (у конца 0).
    q — сколько миллиметров пути даёт миллиметр хода: 1 у конца,
    2 × pairs у семейства U. extra_length_mm — полное удлинение пути на
    нижнюю ноту. travel_mm — полный ход механики. radial_clearance_mm —
    зазор между каналом корпуса и царгой со всех сторон. tenon_length_mm —
    царга: перекрытие плюс ход, чтобы деталь не выпала. flange_mm — высота
    цоколя детали (у конца тонкий фланец, у U — как у трубы). legs — номера
    прямых, в которые входят царги.
    """

    kind: str
    pairs: int
    q: int
    upper_note: str
    lower_note: str
    extra_length_mm: float
    travel_mm: float
    overlap_mm: float
    flange_mm: float
    radial_clearance_mm: float
    tenon_diameter_mm: float
    bore_diameter_mm: float
    flange_diameter_mm: float
    tenon_length_mm: float
    stops: tuple[SliderStop, ...]
    legs: tuple[int, ...]


def is_u_family(kind: str) -> bool:
    """Принадлежит ли схема семейству подвижных U-колен.

    Принимает идентификатор. Возвращает True для u, uu и U авто.
    """
    return kind in SLIDER_U_FAMILY


def default_slider_pairs(kind: str) -> int:
    """Число U-колен по умолчанию для схемы, если поле колен пустое.

    Принимает идентификатор. Выдвижной конец — ноль. Одно U — одно колено,
    двойное — два, U авто — ноль (число выберет укладка). Возвращает целое.
    """
    if kind == SLIDER_UU:
        return 2
    if kind == SLIDER_U:
        return 1
    return 0


def max_u_pairs(straight_count: int) -> int:
    """Сколько нижних U-колен можно отдать слайдеру при данном числе прямых.

    Принимает нечётное число прямых. Каждое колено занимает две прямые,
    выход в дне остаётся. Возвращает максимум колен, не меньше нуля.
    """
    if straight_count < 3 or straight_count % 2 == 0:
        return 0
    return (straight_count - 1) // 2


def slider_q(kind: str, pairs: int | None = None) -> int:
    """Сколько миллиметров пути даёт миллиметр хода выбранной схемы.

    Принимает идентификатор схемы и необязательное число U-колен.
    Возвращает 1 для выдвижного конца и 2 × колен для семейства U.
    Пустые колена подставляет из схемы. Неизвестную схему отвергает SliderError.
    """
    if kind == SLIDER_END:
        return 1
    if not is_u_family(kind):
        raise SliderError(
            f"Схема слайдера «{kind}» не известна: есть "
            f"{', '.join(SLIDER_KIND_LABELS[item] for item in SLIDER_KINDS)}."
        )
    count = default_slider_pairs(kind) if pairs is None or pairs < 1 else pairs
    if count < 1:
        count = 1
    return 2 * count


def slider_kind_label(kind: str) -> str:
    """Русское имя схемы слайдера для окна и отчёта.

    Принимает идентификатор. Возвращает подпись; неизвестный отдаёт как есть.
    """
    return SLIDER_KIND_LABELS.get(kind, kind)


def min_straight_count(kind: str, pairs: int | None = None) -> int:
    """Минимальное нечётное число прямых, при котором схема садится в вязанку.

    Принимает идентификатор схемы и необязательное число U-колен.
    Выдвижному концу хватает одной прямой. Семейству U нужны две прямые
    на колено плюс выход в дне. U авто считает от одного колена — трёх
    прямых. Возвращает целое.
    """
    if kind == SLIDER_END or not kind:
        return 1
    count = default_slider_pairs(kind) if pairs is None else pairs
    if kind == SLIDER_UAUTO and count < 1:
        count = 1
    if count < 1:
        count = 1
    return 2 * count + 1


def slider_leg_indices(
    kind: str,
    straight_count: int,
    pairs: int | None = None,
) -> tuple[int, ...]:
    """Номера прямых, в которые входят царги слайдера.

    Принимает схему, число прямых и необязательное число U-колен.
    Для выдвижного конца — последняя прямая. Для семейства U — 2×колен
    прямых последних нижних разворотов, выход не занимают. Если прямых
    меньше минимума схемы, поднимает SliderError. Возвращает кортеж
    индексов с нуля.
    """
    if kind == SLIDER_END:
        if straight_count < 1 or straight_count % 2 == 0:
            raise SliderError(
                "Выдвижному концу нужно нечётное число прямых: выход в дне."
            )
        return (straight_count - 1,)
    count = default_slider_pairs(kind) if pairs is None else pairs
    if kind == SLIDER_UAUTO and (count is None or count < 1):
        count = max_u_pairs(straight_count)
    if count < 1:
        count = 1
    needed = min_straight_count(kind, count)
    if straight_count < needed or straight_count % 2 == 0:
        raise SliderError(
            f"Схеме «{slider_kind_label(kind)}» нужно минимум {needed} "
            "прямых: ветви слайдера и выход в дне."
        )
    first = straight_count - 2 * count - 1
    return tuple(range(first, first + 2 * count))


def last_bottom_straight_index(straight_count: int) -> int:
    """Номер прямой, после которой стоит последнее нижнее колено.

    Принимает нечётное число прямых. Возвращает индекс с нуля: для трёх
    прямых это входная, для пяти — третья. Если прямых меньше трёх,
    поднимает SliderError: U-колену нужны две ветви и выход в дне.
    """
    return slider_leg_indices(SLIDER_U, straight_count)[0]


def skip_turns_after_straights(
    plan: SliderPlan | None, straight_count: int
) -> tuple[int, ...]:
    """Номера прямых, после которых корпус не печатает нижнее колено слайдера.

    Принимает план слайдера или None и число прямых. Для U — одно последнее
    нижнее колено. Для двойного U — два последних нижних колена; верхнее
    колено между ними остаётся в корпусе. Для выдвижного конца и без
    слайдера — пустой кортеж. Возвращает индексы прямых перед пропущенными
    дугами.
    """
    if plan is None or not is_u_family(plan.kind):
        return ()
    if straight_count < min_straight_count(plan.kind, plan.pairs):
        return ()
    return slider_leg_indices(plan.kind, straight_count, plan.pairs)[::2]


def skip_turn_after_straight(plan: SliderPlan | None, straight_count: int) -> int | None:
    """Номер прямой перед первым пропущенным коленом U-слайдера.

    Принимает план слайдера или None и число прямых. Для одного U возвращает
    тот же индекс, что и раньше. Для двойного U — первое из двух нижних
    колен. Без пропущенных колен — None.
    """
    skipped = skip_turns_after_straights(plan, straight_count)
    if not skipped:
        return None
    return skipped[0]


def resolve_slider(params: TubeParams, upper: Tuning) -> SliderPlan | None:
    """Считает ход слайдера под уже полученный строй верхней ноты.

    Принимает параметры и строй задвинутого положения. Если полутонов
    слайдера нет, возвращает None. Иначе опускает ноту на заданное число
    полутонов, считает корпус каждой ступени тем же строем и берёт разницу
    длин как удлинение пути. Ход механики — удлинение, делённое на q.
    Царга уже канала на два радиальных зазора: по одному со всех сторон,
    не меньше 0,3 мм. Посадка мембраны неподвижна. Возвращает SliderPlan
    со стопами всех полутонов, включая нулевой.

    Если нижняя нота вне C-1…B9, ход не положительный или вставка не
    оставляет канала, поднимает SliderError. Диапазон сам не укорачивает.
    """
    steps = params.slider_semitones
    kind = params.slider_kind
    if steps <= 0 or not kind:
        return None
    q = slider_q(kind, params.slider_pairs)
    pairs = default_slider_pairs(kind)
    if is_u_family(kind) and params.slider_pairs > 0:
        pairs = params.slider_pairs
    if kind == SLIDER_END:
        pairs = 0
    try:
        upper_parsed = parse_note_name(upper.note)
        lower_midi = shift_midi(midi_number(upper_parsed), -steps)
        lower_name = note_from_midi(lower_midi).spelling
    except NoteNameError as exc:
        raise SliderError(
            f"Слайдер на {steps} полутонов вниз от {upper.note} "
            f"выходит за ноты от C-1 до B9: {exc}"
        ) from exc

    stops = _stops(params, upper, steps, q)
    extra = stops[-1].extra_length_mm
    if extra <= 1e-6:
        raise SliderError(
            f"Слайдер на {steps} полутонов не удлиняет корпус: "
            f"верх {upper.body_length_mm:.3f} мм, низ совпадает."
        )
    travel = extra / q
    bore = params.bore_diameter_mm
    clearance = params.slider_clearance_mm
    tenon = bore - 2.0 * clearance
    wall = min(params.wall_thickness_mm, TRIM_MIN_WALL_MM)
    inner = tenon - 2.0 * wall
    if tenon <= 0.0 or inner <= 0.0:
        raise SliderError(
            "Канал трубы слишком узкий для слайдера: "
            "не остаётся отверстия внутри выдвижной вставки."
        )
    overlap = TRIM_OVERLAP_MM
    base_height = (
        TRIM_FLANGE_MM
        if kind == SLIDER_END
        else params.floor_mm + params.turn_radius_mm + params.bore_diameter_mm / 2.0
    )
    return SliderPlan(
        kind=kind,
        pairs=pairs,
        q=q,
        upper_note=upper.note,
        lower_note=lower_name,
        extra_length_mm=extra,
        travel_mm=travel,
        overlap_mm=overlap,
        flange_mm=base_height,
        radial_clearance_mm=clearance,
        tenon_diameter_mm=tenon,
        bore_diameter_mm=inner,
        flange_diameter_mm=params.outer_diameter_mm,
        tenon_length_mm=overlap + travel,
        stops=stops,
        legs=(),
    )


def bind_slider_columns(plan: SliderPlan, straight_count: int) -> SliderPlan:
    """Проставляет номера прямых, на которые садится слайдер.

    Принимает план хода и число прямых укладки. Для выдвижного конца —
    последняя прямая. Для семейства U — ветви выбранных нижних колен.
    Если у плана ещё нет числа колен (U авто), берёт все нижние колена
    этой укладки. Возвращает копию плана. Если схеме не хватает прямых,
    поднимает SliderError.
    """
    pairs = plan.pairs
    if is_u_family(plan.kind) and pairs < 1:
        pairs = max_u_pairs(straight_count)
    return replace(
        plan,
        pairs=pairs,
        legs=slider_leg_indices(plan.kind, straight_count, pairs),
    )


def plan_with_pairs(plan: SliderPlan, pairs: int) -> SliderPlan:
    """Пересчитывает ход и царгу под другое число U-колен.

    Принимает план (уже с ΔL) и число колен. q становится 2 × колен,
    ход и стопы делятся на новый q, царга — перекрытие плюс ход.
    Возвращает новый план. Число колен меньше единицы отвергает SliderError.
    """
    if pairs < 1:
        raise SliderError("Семейству U нужно хотя бы одно колено.")
    q = 2 * pairs
    extra = plan.extra_length_mm
    travel = extra / q
    stops = tuple(
        replace(stop, travel_mm=stop.extra_length_mm / q) for stop in plan.stops
    )
    return replace(
        plan,
        pairs=pairs,
        q=q,
        travel_mm=travel,
        tenon_length_mm=plan.overlap_mm + travel,
        stops=stops,
        legs=(),
    )


def socket_length_mm(plan: SliderPlan) -> float:
    """Какой длины свободный канал нужна царга слайдера.

    Принимает план. Возвращает перекрытие плюс ход: столько трубки всегда
    можно задвинуть в корпус.
    """
    return plan.tenon_length_mm


def printed_slider_height_mm(plan: SliderPlan, turn_radius_mm: float) -> float:
    """Высота отдельной детали слайдера в ориентации модели.

    Принимает план и радиус колена корпуса. Для выдвижного конца это фланец
    плюс царга. Для семейства U — высокий цоколь до центров колен и царга
    вверх; дуга лежит в цоколе и высоту не добавляет. Возвращает миллиметры.
    """
    if plan.kind == SLIDER_END:
        return plan.flange_mm + plan.tenon_length_mm
    return plan.flange_mm + plan.tenon_length_mm


def slider_leg_points(
    plan: SliderPlan,
    turn_radius_mm: float,
    columns: tuple[tuple[float, float], ...] = (),
) -> tuple[tuple[float, float], ...]:
    """Центры царг слайдера в плане, миллиметры.

    Принимает план, радиус колена и необязательные центры прямых укладки.
    Если у плана уже есть ноги и колонки укладки их покрывают, берёт эти
    точки — так двойное U совпадает с гнёздами корпуса. Если ног ещё нет,
    считает их из схемы и числа колонок. Иначе для одного U ставит пару
    на шаге 2R, для двойного — две пары в ряд. Возвращает кортеж (x, y).
    """
    legs = plan.legs
    pair_count = plan.pairs if plan.pairs > 0 else default_slider_pairs(plan.kind)
    if not legs and columns:
        try:
            legs = slider_leg_indices(plan.kind, len(columns), pair_count)
        except SliderError:
            legs = ()
    if legs and columns and max(legs) < len(columns):
        return tuple(columns[index] for index in legs)
    radius = turn_radius_mm
    if is_u_family(plan.kind):
        count = pair_count if pair_count > 0 else 1
        points: list[tuple[float, float]] = []
        start = -((2 * count - 1) * radius)
        for index in range(2 * count):
            points.append((start + 2.0 * radius * index, 0.0))
        return tuple(points)
    return ((0.0, 0.0),)


def printed_slider_bbox_mm(
    plan: SliderPlan,
    turn_radius_mm: float,
    columns: tuple[tuple[float, float], ...] = (),
) -> tuple[float, float, float]:
    """Габарит печатной детали слайдера в ориентации модели.

    Принимает план, радиус колена и необязательные центры прямых. Высота —
    фланец и царга (у U ещё радиус дуги). Ширина и глубина — размах царг
    плюс диаметр фланца. У выдвижного конца все три ребра от фланца и царги.
    Возвращает (высота, ширина, глубина) в миллиметрах.
    """
    height = printed_slider_height_mm(plan, turn_radius_mm)
    flange = plan.flange_diameter_mm
    if plan.kind == SLIDER_END:
        return (height, flange, flange)
    points = slider_leg_points(plan, turn_radius_mm, columns)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (height, max(xs) - min(xs) + flange, max(ys) - min(ys) + flange)


def printed_slider_fits_envelope(
    plan: SliderPlan,
    turn_radius_mm: float,
    max_height_mm: float,
    max_width_mm: float,
    max_depth_mm: float,
    columns: tuple[tuple[float, float], ...] = (),
    print_splits: bool = False,
) -> bool:
    """Влезает ли деталь слайдера в область печати любой стороной.

    Принимает план, радиус колена, три размера стола, необязательные
    центры прямых и флаг разрезов. Без разрезов сортирует рёбра детали
    и стола и сравнивает попарно. С разрезами деталь можно резать по
    длинной стороне на куски со стыками «папа — мама», если стенка вставки
    не тоньше PRINT_JOINT_MIN_WALL_MM: каждый кусок должен влезть на стол.
    Возвращает True, если печатать можно. Высота собранного инструмента
    на полном ходу сюда не входит.
    """
    height, width, depth = printed_slider_bbox_mm(plan, turn_radius_mm, columns)
    bed = (max_height_mm, max_width_mm, max_depth_mm)
    if _edges_fit_bed((height, width, depth), bed):
        return True
    if not print_splits or not slider_can_be_split(plan):
        return False
    return _sliced_part_fits_bed(height, width, depth, bed, PRINT_PLUG_MM)


def slider_wall_mm(plan: SliderPlan) -> float:
    """Стенка выдвижной вставки слайдера.

    Принимает план слайдера. Возвращает половину разницы наружного
    диаметра вставки и её канала, мм.
    """
    return (plan.tenon_diameter_mm - plan.bore_diameter_mm) / 2.0


def slider_can_be_split(plan: SliderPlan) -> bool:
    """Можно ли резать деталь слайдера на куски стыком «папа — мама».

    Принимает план слайдера. Возвращает True, если стенка вставки не
    тоньше PRINT_JOINT_MIN_WALL_MM.
    """
    return slider_wall_mm(plan) >= PRINT_JOINT_MIN_WALL_MM - 1e-9


def _edges_fit_bed(
    part: tuple[float, float, float],
    bed: tuple[float, float, float],
) -> bool:
    """Влезает ли прямоугольный кусок на стол любой ориентацией.

    Принимает рёбра детали и рёбра стола. Сортирует оба набора и сравнивает
    попарно. Возвращает True, если все три ребра не длиннее стола.
    """
    sized = sorted(part, reverse=True)
    box = sorted(bed, reverse=True)
    return all(edge <= limit + 1e-9 for edge, limit in zip(sized, box))


def _sliced_part_fits_bed(
    height_mm: float,
    width_mm: float,
    depth_mm: float,
    bed: tuple[float, float, float],
    plug_mm: float,
) -> bool:
    """Можно ли нарезать деталь по высоте на куски, каждый из которых влезет на стол.

    Принимает габарит детали, стол и длину штекера. Режет самое длинное ребро;
    два других остаются у каждого куска. Верхний кусок без папы сверху,
    у остальных папа входит в длину куска. Возвращает True, если нарезка
    сходится.
    """
    edges = [height_mm, width_mm, depth_mm]
    long_index = edges.index(max(edges))
    length = edges[long_index]
    other = [edges[index] for index in range(3) if index != long_index]
    slice_max = _max_slice_length(other[0], other[1], bed)
    if slice_max <= 1e-9:
        return False
    if length <= slice_max + 1e-9:
        return True
    unique = slice_max - plug_mm
    if unique <= 1e-9:
        return False
    rest = length - slice_max
    pieces = 1
    while rest > 1e-9:
        rest -= unique
        pieces += 1
        if pieces > 40:
            return False
    return True


def _max_slice_length(
    width_mm: float,
    depth_mm: float,
    bed: tuple[float, float, float],
) -> float:
    """Самая длинная нарезка, которая вместе с двумя другими рёбрами влезет на стол.

    Принимает два неизменных ребра куска и размеры стола. Перебирает, какое
    ребро стола отдать нарезке. Возвращает миллиметры, ноль если пара не
    влезает ни в какой ориентации.
    """
    best = 0.0
    limits = sorted(bed)
    others = sorted((width_mm, depth_mm))
    for slot in range(3):
        remain = [limits[index] for index in range(3) if index != slot]
        remain_sorted = sorted(remain)
        if others[0] <= remain_sorted[0] + 1e-9 and others[1] <= remain_sorted[1] + 1e-9:
            best = max(best, limits[slot])
    return best


def _stops(
    params: TubeParams,
    upper: Tuning,
    steps: int,
    q: int,
) -> tuple[SliderStop, ...]:
    """Стопы каждого полутона от задвинутого до полного хода.

    Принимает параметры, строй верхней ноты, число полутонов вниз и q.
    Для каждой ступени считает корпус тем же строем. Возвращает кортеж
    стопов. Если какая-то нота вне диапазона, поднимает SliderError.
    """
    root = midi_number(parse_note_name(upper.note))
    found: list[SliderStop] = []
    for step in range(steps + 1):
        try:
            name = note_from_midi(shift_midi(root, -step)).spelling
        except NoteNameError as exc:
            raise SliderError(
                f"Слайдер на {step} полутонов вниз от {upper.note} "
                f"выходит за ноты от C-1 до B9: {exc}"
            ) from exc
        if step == 0:
            body = upper.body_length_mm
        else:
            lower_params = replace(
                params,
                note=name,
                body_length_mm=None,
                slider_semitones=0,
                slider_kind="",
                trim_semitones=0,
                hole_count=0,
            )
            try:
                body = resolve_tuning(lower_params).body_length_mm
            except TuningError as exc:
                raise SliderError(str(exc)) from exc
        extra = body - upper.body_length_mm
        found.append(
            SliderStop(
                semitones=step,
                note=name,
                extra_length_mm=extra,
                travel_mm=extra / q,
            )
        )
    return tuple(found)
