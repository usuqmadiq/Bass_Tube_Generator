"""Привязка отверстий к прямым вязанки: наружу, на прямых, цоколь и вход на месте.

Координата s задаётся акустикой и не подменяется картинкой. Под неё
подбирается укладка: нечётное число прямых и высоты пар (подъём равен
следующему спуску), чтобы ни один разворот не лёг на дырку, а дырки стояли
на прямых, откуда можно смотреть наружу. Все нижние развороты на цоколе,
выход в дне, вход над самым высоким верхним разворотом. Дырка смотрит от
вязанки наружу и довёрнута к общей лицевой стороне, насколько пускают
соседние трубы: так пальцы ложатся с одной стороны.

Из подходящих укладок выбирается удобная пальцам: расстояния по стенке
между соседними по открыванию дырками близки к шагу пальцев, между руками
допускается больше (bass_tube.layout.fingers). Ради этого решатель сам
ставит колено между далёкими дырками и берёт больше прямых.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from bass_tube.acoustics.holes import HoleError, HolePlan, HoleSpec, plan_holes
from bass_tube.acoustics.trim import TrimPlan, socket_length_mm
from bass_tube.acoustics.tuning import Tuning
from bass_tube.derived import min_turn_radius_mm
from bass_tube.layout.centerline import Centerline, Vec3, build_centerline
from bass_tube.layout.clearance import check_channel_clearance
from bass_tube.layout.coil import (
    MAX_STRAIGHTS,
    Coil,
    LayoutError,
    bottom_turn_height_mm,
    bundle_plan,
    coil_from_heights,
    envelope_failures,
    inlet_rise_mm,
)
from bass_tube.constants import PRINT_PLUG_MM
from bass_tube.layout.columns import Point2
from bass_tube.layout.fingers import (
    finger_spacings_mm,
    layout_penalty,
    plan_distances_mm,
    spacing_limits,
)
from bass_tube.layout.hole_fit import FingerModel, FitLimits, PairFit, fit_pair_heights
from bass_tube.layout.print_cuts import PrintCutError, coil_cut_heights
from bass_tube.params import TubeParams

# Сколько кусков стола пробовать под высокую вязанку с дырками.
MAX_PRINT_PIECES = 6
# Штрафы пальцев, отличающиеся от лучшего меньше этого (мм², около 14 мм
# лишней растяжки на одну пару), считаются равными.
_PENALTY_TIE_MM2 = 200.0
# На сколько прямых больше найденной укладки ещё искать удобнее для пальцев.
_EXTRA_STRAIGHTS_TRIED = 8
# Насколько дырку можно довернуть от направления «от центра вязанки».
_MAX_AIM_DEG = 45.0
# Запас между сверлом дырки и соседней трубой, мм.
_AIM_CLEARANCE_MM = 0.5


@dataclass(frozen=True, slots=True)
class PlacedHole:
    """Отверстие на оси после привязки к прямой.

    spec — акустическая дырка. column — номер прямой. outward — единичный
    горизонтальный вектор от оси через стенку наружу. Координата s — из spec.
    """

    spec: HoleSpec
    column: int
    outward: Vec3


def place_holes_in_envelope(
    params: TubeParams,
    tuning: Tuning,
    plan: HolePlan,
    trim: TrimPlan | None,
    stack_height_mm: float | None = None,
) -> tuple[Coil, tuple[PlacedHole, ...]]:
    """Подбирает укладку, на прямых которой снаружи лежат все дырки.

    Принимает параметры, строй, акустический план и подстройку. Перебирает
    нечётное число прямых от трёх вверх; для каждого сначала ищет высоты
    пар с удобным отступом дырок от колен, потом с минимальным. Укладка
    должна войти в габарит и держать стенку между каналами. Берётся первая
    подходящая: меньше колен — проще и крепче. Если в стол не вошло и
    включены разрезы, собранная вязанка может быть выше стола: сначала на
    два куска, потом на три и дальше, и разрезы должны пройти мимо колен,
    дырок и царги. stack_height_mm при разрезах задаёт предел собранной
    высоты вместо стола (пара с дроном просит мелодию выше и уже в плане),
    разрезы по-прежнему по столу. Возвращает укладку и дырки. Если ни одна
    не подошла, поднимает LayoutError с причиной.
    """
    if stack_height_mm is not None and params.print_splits:
        stacked = _search(
            replace(params, max_height_mm=stack_height_mm), tuning, plan, trim, bed=params
        )
        if stacked is None:
            raise LayoutError(
                [f"Под собранную высоту {_format_mm(stack_height_mm)} мм дырки не легли."]
            )
        return stacked
    found = _search(params, tuning, plan, trim)
    if found is None and params.print_splits:
        found = _search_split(params, tuning, plan, trim)
    if found is not None:
        return found
    if not any(_plan_fits(count, params) for count in _counts(params)):
        raise LayoutError(
            ["Мало ширины или глубины: ни одна вязанка под отверстия не входит в план печати."]
        )
    raise LayoutError(_failure_reasons(params, tuning, plan, trim))


def _search_split(
    params: TubeParams,
    tuning: Tuning,
    plan: HolePlan,
    trim: TrimPlan | None,
) -> tuple[Coil, tuple[PlacedHole, ...]] | None:
    """Перебор высоких укладок под дырки, которые режут на куски стола.

    Принимает параметры (высота — стол), строй, план дырок и подстройку.
    Высота собранной вязанки растёт на целый кусок: стол, стол плюс
    (стол − папа стыка) и так до MAX_PRINT_PIECES кусков. Меньше кусков —
    лучше, при равных меньше прямых. Возвращает укладку и дырки или None.
    """
    unique = params.max_height_mm - PRINT_PLUG_MM
    if unique <= 1e-6:
        return None
    for pieces in range(2, MAX_PRINT_PIECES + 1):
        tall = replace(params, max_height_mm=params.max_height_mm + (pieces - 1) * unique)
        found = _search(tall, tuning, plan, trim, bed=params)
        if found is not None:
            return found
    return None


def _search(
    params: TubeParams,
    tuning: Tuning,
    plan: HolePlan,
    trim: TrimPlan | None,
    bed: TubeParams | None = None,
    ergonomic: bool = True,
) -> tuple[Coil, tuple[PlacedHole, ...]] | None:
    """Перебор укладок под дырки.

    Принимает параметры, строй, план дырок, подстройку, необязательные
    параметры стола bed (если они заданы, укладку режут на куски этого
    стола, и разрезы должны пройти мимо колен, дырок и царги) и флаг
    ergonomic. Без него отдаёт первую подошедшую укладку, не глядя на
    пальцы: так быстро проверяется, ложатся ли дырки вообще. Идёт по
    нечётному числу прямых от меньшего; для каждого — удобный и
    минимальный отступ, радиус колена из параметров и самый тесный под
    диаметр и зазор. Сначала проверяется самая низкая раскладка; только
    если она проходит печать, решатель ищет удобную пальцам, а при её
    провале остаётся самая низкая.
    Штрафы растяжки в пределах _PENALTY_TIE_MM2 от лучшего считаются
    равными; среди них берётся удобный отступ, меньше прямых и ниже
    деталь. Как только найдена раскладка без растяжки с удобным
    отступом, лучше уже не будет.
    Возвращает укладку в габарите с целыми каналами и дырки или None.
    """
    holes_s = tuple(spec.s_mm for spec in plan.holes)
    variants = _radius_variants(params)
    limits = {id(item): fit_limits(item, tuning, trim) for item in variants}
    finger_limits = tuple(reversed(spacing_limits(len(holes_s))))
    found: list[tuple[float, tuple, tuple[Coil, tuple[PlacedHole, ...]]]] = []
    for count in _counts(params):
        if not _plan_fits(count, params):
            continue
        if found and count > min(item[1][1] for item in found) + _EXTRA_STRAIGHTS_TRIED:
            break
        for margin_rank, margin in enumerate(_margins(params)):
            for variant in variants:
                columns, _, _ = bundle_plan(count, variant)
                outward = tuple(_outward_vector(columns, index) for index in range(count))
                outer = tuple(
                    outward[index] is not None and _radial_is_free(columns, index, variant)
                    for index in range(count)
                )
                # Без пальцев решатель в разы быстрее; если он ничего не нашёл,
                # с пальцами тоже не найдётся: допустимые высоты у них общие.
                # Самая низкая раскладка проверяется первой: если даже она не
                # проходит габарит, стенки или разрезы, удобную пальцам не ищем.
                lowest_fit = fit_pair_heights(count, outer, holes_s, limits[id(variant)], margin)
                checked = _checked_layout(lowest_fit, count, variant, plan, trim, margin, bed)
                if checked is None:
                    continue
                if not ergonomic:
                    return checked[0], checked[2]
                fingers = FingerModel(
                    plan_distances_mm(columns, outward, variant.outer_diameter_mm / 2.0),
                    finger_limits,
                )
                comfy = fit_pair_heights(
                    count, outer, holes_s, limits[id(variant)], margin, fingers
                )
                checked = (
                    _checked_layout(comfy, count, variant, plan, trim, margin, bed) or checked
                )
                coil, centerline, placed = checked
                penalty = layout_penalty(finger_spacings(centerline, variant, placed))
                key = (margin_rank, count, coil.height_with_head_mm)
                found.append((penalty, key, (coil, placed)))
        if any(item[0] <= 1e-6 and item[1][0] == 0 for item in found):
            break
    if not found:
        return None
    lowest = min(item[0] for item in found)
    close = [item for item in found if item[0] <= lowest + _PENALTY_TIE_MM2]
    return min(close, key=lambda item: item[1])[2]


def _checked_layout(
    fit: PairFit | None,
    count: int,
    params: TubeParams,
    plan: HolePlan,
    trim: TrimPlan | None,
    margin: float,
    bed: TubeParams | None,
) -> tuple[Coil, Centerline, tuple[PlacedHole, ...]] | None:
    """Строит укладку по высотам решателя и прогоняет проверки печати.

    Принимает ответ решателя (или None), число прямых, параметры варианта,
    план дырок, подстройку, отступ и параметры стола для разрезов. Проверяет
    габарит, стенки между каналами, привязку дырок и разрезы, если задан
    стол. Возвращает (укладка, ось, дырки) или None, если что-то не прошло.
    """
    if fit is None:
        return None
    coil = coil_from_heights(count, fit.first_mm, fit.pair_heights_mm, params)
    if envelope_failures(coil, params):
        return None
    try:
        centerline = build_centerline(coil, params.joint_length_mm)
        check_channel_clearance(centerline, params)
        placed = place_holes_on_coil(coil, params, plan, trim, margin)
    except LayoutError:
        return None
    if bed is not None and not _cuts_found(coil, bed, plan, trim):
        return None
    return coil, centerline, placed


def finger_spacings(
    centerline: Centerline,
    params: TubeParams,
    placed: tuple[PlacedHole, ...],
) -> tuple[float, ...]:
    """Расстояния между центрами соседних дырок на стенке, от выхода.

    Принимает ось, параметры и привязанные дырки. Возвращает кортеж мм
    длиной число дырок − 1.
    """
    return finger_spacings_mm(
        centerline,
        params.outer_diameter_mm / 2.0,
        tuple((hole.spec.s_mm, hole.outward) for hole in placed),
    )


def _cuts_found(coil: Coil, bed: TubeParams, plan: HolePlan, trim: TrimPlan | None) -> bool:
    """Находятся ли разрезы высокой укладки мимо колен, дырок и царги.

    Принимает укладку, параметры стола, план дырок и подстройку.
    Возвращает True, если разрезы есть или не нужны.
    """
    try:
        coil_cut_heights(
            coil,
            bed,
            holes=tuple((spec.s_mm, spec.diameter_mm) for spec in plan.holes),
            bottom_keep_mm=socket_length_mm(trim) if trim is not None else 0.0,
        )
    except PrintCutError:
        return False
    return True


def _radius_variants(params: TubeParams) -> tuple[TubeParams, ...]:
    """Параметры с радиусом колена из окна и с самым тесным радиусом.

    Принимает параметры. Если радиус и так минимальный под диаметр и зазор,
    возвращает один вариант. Возвращает кортеж параметров.
    """
    tight = min_turn_radius_mm(params.outer_diameter_mm, params.gap_mm)
    if params.turn_radius_mm <= tight + 1e-6:
        return (params,)
    return (params, replace(params, turn_radius_mm=tight))


def _plan_fits(count: int, params: TubeParams) -> bool:
    """Входит ли план вязанки из count прямых в ширину и глубину.

    Принимает число прямых и параметры. Возвращает True, если входит.
    """
    _, width, depth = bundle_plan(count, params)
    return width <= params.max_width_mm + 1e-9 and depth <= params.max_depth_mm + 1e-9


def _failure_reasons(
    params: TubeParams,
    tuning: Tuning,
    plan: HolePlan,
    trim: TrimPlan | None,
) -> list[str]:
    """Причина отказа с тем, что конкретно поможет.

    Принимает параметры, строй, план дырок и подстройку. Ищет наименьшую
    высоту печати (шаг 10 мм, до +200 мм), при которой дырки ложатся, и
    наибольшее число дырок, которое ложится в текущую высоту. Здесь важно
    только «ложатся ли», поэтому поиск идёт без модели пальцев.
    Возвращает список фраз.
    """
    reasons = [
        f"{len(plan.holes)} дырок не ложатся на прямые снаружи: при высоте "
        f"{_format_mm(params.max_height_mm)} мм нижние колени на цоколе, выход "
        "в дне и вход над коленами с такими промежутками между дырками не сходятся."
    ]
    for extra in range(10, 201, 10):
        taller = replace(params, max_height_mm=params.max_height_mm + extra)
        if _search(taller, tuning, plan, trim, ergonomic=False) is not None:
            reasons.append(
                f"Влезет при высоте печати {_format_mm(taller.max_height_mm)} мм."
            )
            break
    for count in range(len(plan.holes) - 1, 0, -1):
        fewer = replace(params, hole_count=count)
        try:
            smaller = plan_holes(fewer, tuning, exit_keep_mm(fewer, trim))
        except HoleError:
            continue
        if smaller is not None and _search(fewer, tuning, smaller, trim, ergonomic=False) is not None:
            reasons.append(f"В эту высоту влезает {count} дырок этого лада.")
            break
    return reasons


def place_holes_on_coil(
    coil: Coil,
    params: TubeParams,
    plan: HolePlan,
    trim: TrimPlan | None,
    margin_mm: float | None = None,
) -> tuple[PlacedHole, ...]:
    """Привязывает дырки к готовой укладке, ничего в ней не меняя.

    Принимает укладку, параметры, акустический план, подстройку и отступ
    от колен (по умолчанию минимальный). Каждая дырка должна лежать на
    прямой, откуда виден наружный простор, не ближе отступа к коленам,
    посадке, цоколю и царге. Направление довёрнуто к общей лицевой стороне.
    Возвращает дырки. Если какая-то не легла, поднимает LayoutError.
    """
    if not coil.outlet_at_bottom:
        raise LayoutError(["Выход должен открываться в дне: нужно нечётное число прямых."])
    margin = _margins(params)[-1] if margin_mm is None else margin_mm
    keep = exit_keep_mm(params, trim)
    columns: list[int] = []
    for spec in plan.holes:
        kind, index, start, end = _segment_at(
            coil.straight_lengths_mm, coil.turn_length_mm, spec.s_mm
        )
        if kind != "straight":
            raise LayoutError([f"Отверстие {spec.note} попало на разворот {index + 1}."])
        if _outward_vector(coil.columns, index) is None or not _radial_is_free(
            coil.columns, index, params
        ):
            raise LayoutError(
                [f"Отверстие {spec.note} на внутренней прямой {index + 1}: наружу ему не выйти."]
            )
        low = start + margin
        high = end - margin
        if index == 0:
            low = max(low, params.joint_length_mm + margin)
        if index == coil.straight_count - 1:
            high = min(high, coil.axis_length_mm - keep - margin)
        if not low - 1e-9 <= spec.s_mm <= high + 1e-9:
            raise LayoutError(
                [
                    f"Отверстие {spec.note} слишком близко к колену, посадке, "
                    f"цоколю или царге на прямой {index + 1}."
                ]
            )
        columns.append(index)
    directions = _aim_directions(coil.columns, tuple(columns), params)
    return tuple(
        PlacedHole(spec=spec, column=column, outward=direction)
        for spec, column, direction in zip(plan.holes, columns, directions)
    )


def fit_limits(params: TubeParams, tuning: Tuning, trim: TrimPlan | None) -> FitLimits:
    """Пределы решателя высот пар для этих параметров.

    Принимает параметры, строй и подстройку. Вход с модулем не выше
    габарита печати; пара не ниже наружного диаметра со стенкой, чтобы
    каналы верхнего и нижнего колена одной прямой не сошлись. Возвращает FitLimits.
    """
    base = bottom_turn_height_mm(params)
    rise = inlet_rise_mm(params)
    max_first = params.max_height_mm - params.head_reserve_mm - base
    socket = socket_length_mm(trim) if trim is not None else 0.0
    keep = exit_keep_mm(params, trim)
    return FitLimits(
        body_mm=tuning.body_length_mm,
        turn_mm=math.pi * params.turn_radius_mm,
        base_mm=base,
        rise_mm=rise,
        joint_mm=params.joint_length_mm,
        min_pair_mm=params.outer_diameter_mm + params.wall_thickness_mm,
        max_pair_mm=max_first - rise,
        max_first_mm=max_first,
        exit_keep_mm=keep,
        socket_mm=socket,
    )


def exit_keep_mm(params: TubeParams, trim: TrimPlan | None) -> float:
    """Сколько оси от выхода занято цоколем или царгой подстройки.

    Принимает параметры и подстройку. Дырку туда не поставить: снизу она
    ушла бы в цоколь, а царга закрыла бы её изнутри. Возвращает большее
    из высоты цоколя и длины царги в миллиметрах.
    """
    socket = socket_length_mm(trim) if trim is not None else 0.0
    return max(socket, bottom_turn_height_mm(params))


def hole_cutters(centerline: Centerline, params: TubeParams, placed: tuple[PlacedHole, ...]):
    """Точки и направления цилиндров, которые вырезают дырки.

    Принимает ось, параметры и привязанные отверстия. Для каждой дырки
    считает точку внутри канала, единичное направление наружу, радиус
    и длину цилиндра сквозь стенку. Возвращает кортеж таких четвёрок.
    """
    wall = params.wall_thickness_mm
    overshoot = 0.6
    cuts: list[tuple[Vec3, Vec3, float, float]] = []
    for hole in placed:
        frame = centerline.sample(hole.spec.s_mm)
        bore = params.bore_diameter_mm / 2.0
        start = Vec3(
            frame.point.x + hole.outward.x * (bore - overshoot),
            frame.point.y + hole.outward.y * (bore - overshoot),
            frame.point.z + hole.outward.z * (bore - overshoot),
        )
        length = wall + 2.0 * overshoot + 2.0
        cuts.append((start, hole.outward, hole.spec.diameter_mm / 2.0, length))
    return tuple(cuts)


def _counts(params: TubeParams) -> tuple[int, ...]:
    """Какие числа прямых пробовать под дырки.

    Принимает параметры. Заданное число — только его. Иначе нечётные
    от трёх до потолка. Возвращает кортеж.
    """
    if params.straight_count is not None:
        return (params.straight_count,)
    return tuple(range(3, MAX_STRAIGHTS + 1, 2))


def _margins(params: TubeParams) -> tuple[float, float]:
    """Удобный и минимальный отступ центра дырки от начала колена.

    Принимает параметры. Минимальный — половина дырки плюс 1,5 мм: вырез
    целиком на прямой, а у нижнего колена над верхом цоколя (+0,5 мм)
    остаётся миллиметр стенки. Удобный — половина дырки плюс 6 мм.
    Возвращает (удобный, минимальный).
    """
    half = params.hole_diameter_mm / 2.0
    return half + 6.0, half + 1.5


def _segment_at(
    lengths: tuple[float, ...],
    turn_mm: float,
    s_mm: float,
) -> tuple[str, int, float, float]:
    """Какой участок оси содержит координату s.

    Принимает длины прямых, длину разворота и s. Возвращает («straight»
    или «turn», номер, начало, конец). Если s вне оси, поднимает LayoutError.
    """
    cursor = 0.0
    last = len(lengths) - 1
    for index, length in enumerate(lengths):
        end = cursor + length
        if s_mm < end - 1e-9 or index == last:
            if cursor - 1e-9 <= s_mm <= end + 1e-9:
                return "straight", index, cursor, end
        cursor = end
        if index == last:
            break
        turn_end = cursor + turn_mm
        if s_mm < turn_end - 1e-9:
            return "turn", index, cursor, turn_end
        cursor = turn_end
    raise LayoutError([f"Координата отверстия {_format_mm(s_mm)} мм вне оси."])


def _radial_is_free(columns: tuple[Point2, ...], index: int, params: TubeParams) -> bool:
    """Свободен ли луч от центра вязанки через эту прямую наружу.

    Принимает центры прямых, номер и параметры. Возвращает True, если по
    этому лучу сверло дырки не задевает другие трубы.
    """
    outward = _outward_vector(columns, index)
    return outward is not None and _ray_is_free(columns, index, outward, params)


def _ray_is_free(
    columns: tuple[Point2, ...],
    index: int,
    direction: Vec3,
    params: TubeParams,
) -> bool:
    """Не задевает ли сверло дырки по направлению соседние трубы.

    Принимает центры прямых, номер прямой с дыркой, горизонтальное
    направление и параметры. Труба впереди по лучу мешает, если её ось
    ближе к лучу, чем половина трубы, половина дырки и запас. Возвращает True,
    если путь свободен.
    """
    origin = columns[index]
    reach = params.outer_diameter_mm / 2.0 + params.hole_diameter_mm / 2.0 + _AIM_CLEARANCE_MM
    for other_index, other in enumerate(columns):
        if other_index == index:
            continue
        vx = other[0] - origin[0]
        vy = other[1] - origin[1]
        along = vx * direction.x + vy * direction.y
        if along < 1e-6:
            continue
        perp = abs(vx * direction.y - vy * direction.x)
        if perp < reach - 1e-6:
            return False
    return True


def _aim_directions(
    columns: tuple[Point2, ...],
    hole_columns: tuple[int, ...],
    params: TubeParams,
) -> tuple[Vec3, ...]:
    """Направления дырок: наружу и к общей лицевой стороне.

    Принимает центры прямых, номера прямых с дырками и параметры. Лицевая
    сторона — среднее направление «от центра» этих прямых. Каждую дырку
    доворачивает к ней не дальше _MAX_AIM_DEG от своего «от центра», пока
    сверло не задевает соседние трубы. Возвращает единичные векторы.
    """
    radials = [_outward_vector(columns, index) for index in hole_columns]
    sx = sum(vector.x for vector in radials if vector is not None)
    sy = sum(vector.y for vector in radials if vector is not None)
    front = math.atan2(sy, sx) if math.hypot(sx, sy) > 1e-6 else None
    result: list[Vec3] = []
    for index, radial in zip(hole_columns, radials):
        if radial is None:
            raise LayoutError([f"У прямой {index + 1} нет направления наружу."])
        if front is None:
            result.append(radial)
            continue
        base = math.atan2(radial.y, radial.x)
        best = radial
        best_gap = abs(_angle_diff(base, front))
        steps = int(_MAX_AIM_DEG)
        for step in range(-steps, steps + 1):
            angle = base + math.radians(step)
            candidate = Vec3(math.cos(angle), math.sin(angle), 0.0)
            gap = abs(_angle_diff(angle, front))
            if gap + 1e-9 < best_gap and _ray_is_free(columns, index, candidate, params):
                best, best_gap = candidate, gap
        result.append(best)
    return tuple(result)


def _angle_diff(first: float, second: float) -> float:
    """Разница углов в радианах, приведённая к (−π, π].

    Принимает два угла. Возвращает first − second по кратчайшей дуге.
    """
    value = (first - second + math.pi) % (2.0 * math.pi) - math.pi
    return value if value != -math.pi else math.pi


def _outward_vector(columns: tuple[Point2, ...], index: int) -> Vec3 | None:
    """Единичное направление от центра вязанки через эту прямую.

    Принимает столбцы и номер. Берёт вектор от среднего центра к этой
    прямой в плане. У центра возвращает None. Возвращает Vec3 в плоскости xy.
    """
    point = columns[index]
    cx = sum(item[0] for item in columns) / len(columns)
    cy = sum(item[1] for item in columns) / len(columns)
    dx = point[0] - cx
    dy = point[1] - cy
    norm = math.hypot(dx, dy)
    if norm < 1e-9:
        return None
    return Vec3(dx / norm, dy / norm, 0.0)


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает короткую запись: целое без дроби,
    иначе до трёх знаков после запятой без хвостовых нулей.
    """
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")
