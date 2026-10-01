"""Укладка канала вертикальными прямыми вязанкой.

Вертикаль — ось z, стол печати — плоскость z = 0. Модуль мембраны сверху:
вход трубы — верх первой прямой, первая прямая идёт вниз. Развороты 180°
чередуются: первый снизу, следующий сверху. Шаг между соседними прямыми 2R.

Внизу цоколь: сплошной низ по контуру прямых высотой до центров нижних
разворотов. Под нижней точкой канала остаётся дно floor_mm. Последняя прямая
проходит цоколь насквозь и открывается в столе.

Вход стоит в центре и окружён верхними разворотами, поэтому посадка
с переходником целиком поднята над их макушками. Нижние развороты все
лежат в цоколе на одной высоте. Выход всегда в дне: прямых только
нечётное число, последняя проходит цоколь насквозь.

Если есть подстройка, последняя прямая не короче царги: туда вставляется
трубка, посадка мембраны неподвижна.

Если есть слайдер, печатается сложенный корпус: высота на полном ходу
пишется в отчёт и область печати не режет. Деталь слайдера должна влезть
на стол любой стороной; при включённых разрезах её можно нарезать со
стыками «папа — мама», если стенка вставки не тоньше 1,6 мм. Ход сам не
укорачивается: когда деталь не влезает,
отказ называет её размер и габарит печати.
U-колено садится на последнее нижнее колено: обе его прямые доходят до дна.
Двойное U — на два последних нижних колена. «U авто» забирает все нижние
колена укладки, кроме выхода: больше прямых — больше колен и короче царги.
Выдвижной конец садится в последнюю прямую, как трубка подстройки.
Разрезы на печать: высота собранной вязанки может быть больше стола,
каждый кусок вместе с папой стыка влезает в область печати.

Ноту и радиус укладка не подменяет: если габарит не вмещает ни одно число
прямых, наружу уходит причина.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bass_tube.acoustics.slider import (
    SliderError,
    SliderPlan,
    bind_slider_columns,
    default_slider_pairs,
    is_u_family,
    max_u_pairs,
    min_straight_count,
    plan_with_pairs,
    printed_slider_bbox_mm,
    printed_slider_fits_envelope,
    resolve_slider,
    slider_can_be_split,
    slider_wall_mm,
    slider_kind_label,
    slider_leg_indices,
    socket_length_mm as slider_socket_length_mm,
)
from bass_tube.acoustics.trim import TrimPlan, socket_length_mm, resolve_trim
from bass_tube.acoustics.tuning import Tuning
from bass_tube.constants import PRINT_JOINT_MIN_WALL_MM, PRINT_PLUG_MM, SLIDER_END, SLIDER_UAUTO
from bass_tube.layout.columns import Point2, bundle_columns
from bass_tube.layout.print_cuts import PrintCutError, coil_cut_heights
from bass_tube.params import TubeParams

_MIN_STRAIGHT_MM = 1.0
# Три кольца вязанки. Больше прямых — сотни кусков тела и долгие булевы операции.
MAX_STRAIGHTS = 37


class LayoutError(ValueError):
    """Укладка не вошла в габарит. reasons — причины по-русски."""

    def __init__(self, reasons: list[str]) -> None:
        """Запоминает причины отказа.

        Принимает непустой список текстов. Сохраняет его в reasons и
        передаёт склейку в ValueError. Возвращает None.
        """
        if not reasons:
            raise ValueError("LayoutError без причин.")
        self.reasons = list(reasons)
        super().__init__("\n".join(self.reasons))


@dataclass(frozen=True, slots=True)
class Coil:
    """Посчитанная укладка: где стоят прямые, их длины и габарит.

    columns — центры прямых на плане по ходу канала. straight_lengths_mm —
    длины прямых в том же порядке; первая включает посадку и переходник.
    regular_straight_mm — длина прямой между нижним и верхним разворотом.
    bottom_turn_z_mm и top_turn_z_mm — высоты центров разворотов,
    inlet_z_mm — торец входа. base_height_mm — высота цоколя, ноль у одной
    прямой. height_mm — верх детали, height_with_head_mm — вместе с модулем.
    width_mm и depth_mm — размах по x и y.
    """

    layout: str
    straight_count: int
    columns: tuple[Point2, ...]
    straight_lengths_mm: tuple[float, ...]
    regular_straight_mm: float
    turn_count: int
    turn_radius_mm: float
    turn_length_mm: float
    axis_length_mm: float
    bottom_turn_z_mm: float
    top_turn_z_mm: float
    inlet_z_mm: float
    base_height_mm: float
    height_mm: float
    height_with_head_mm: float
    width_mm: float
    depth_mm: float
    outer_diameter_mm: float

    @property
    def straight_length_mm(self) -> float:
        """Длина обычной прямой между разворотами, мм.

        Ничего не принимает. Возвращает regular_straight_mm.
        """
        return self.regular_straight_mm

    @property
    def outlet_at_bottom(self) -> bool:
        """Выходит ли канал в дно.

        Ничего не принимает. Нечётное число прямых кончается ходом вниз.
        Возвращает True, если выход в столе.
        """
        return self.straight_count % 2 == 1


def layout_coil(
    params: TubeParams,
    tuning: Tuning,
    trim: TrimPlan | None = None,
    slider: SliderPlan | None = None,
    stack_height_mm: float | None = None,
) -> Coil:
    """Укладывает длину корпуса вертикальными прямыми в габарит.

    Принимает проверенные параметры, строй с длиной корпуса, необязательный
    план подстройки и необязательный план слайдера. Радиус, зазор, диаметры
    и резерв модуля не меняет.
    Если число прямых задано, считает только его. Иначе перебирает нечётные
    числа от одного до MAX_STRAIGHTS, при которых прямые не короче стыка, и
    берёт наименьшее, вошедшее в габарит: меньше всего колен, укладка самая
    высокая из допустимых. Ниже и шире её делает меньшая высота габарита или
    явное число прямых. Ось равна длине корпуса.

    Прямых только нечётное число: выход всегда в дне, последняя прямая
    проходит цоколь. При подстройке или выдвижном конце последняя ещё не
    короче царги. При семействе U ветви выбранных нижних разворотов
    доходят до дна и не короче царги слайдера. Высота собранного инструмента
    на полном ходу в область печати не входит: это размер игры. Деталь
    слайдера должна влезть на стол любой стороной; при разрезах её режут
    на куски со стыками «папа — мама». Если разрезы включены и компактная укладка
    не сходится по высоте, берётся более высокая собранная вязанка.
    Ход не укорачивается.

    Готовый план подстройки или слайдера можно передать снаружи; иначе он
    считается из параметров и строя. stack_height_mm при разрезах задаёт
    предел собранной высоты вместо стола: берётся укладка с наименьшим
    числом прямых не выше него (так пара с дроном просит мелодию выше и
    уже в плане); разрезы по-прежнему по столу.

    Возвращает Coil. Радиус разворота и дно подгоняет tube_params под диаметр
    трубы. Если после этого мало высоты, ширины или глубины, прямых больше
    потолка или каналы колен сходятся, поднимает LayoutError со всеми причинами.
    """
    plan = _resolved_trim(params, tuning, trim)
    slide = _resolved_slider(params, tuning, slider)
    blockers = _blockers(params)
    if params.straight_count is not None and params.straight_count % 2 == 0:
        blockers.append(
            "Выход должен открываться в дне: нужно нечётное число прямых."
        )
    blockers.extend(_slider_blockers(params, slide))
    if blockers:
        raise LayoutError(blockers)

    body = tuning.body_length_mm
    if params.straight_count is not None:
        if params.straight_count > MAX_STRAIGHTS:
            raise LayoutError(
                [
                    f"Прямых {params.straight_count}, а генератор укладывает не больше "
                    f"{MAX_STRAIGHTS}: увеличьте высоту или радиус разворота."
                ]
            )
        coil = _measure(params.straight_count, body, params, _slide_for_count(slide, params.straight_count))
        if coil is None:
            raise LayoutError([_too_short_reason(params.straight_count, params)])
        bound = _slide_for_count(slide, params.straight_count)
        failures = _failures(coil, params, plan, bound)
        if failures and params.print_splits:
            failures = _failures(coil, params, plan, bound, allow_tall=True)
        if failures:
            raise LayoutError(failures)
        return coil

    candidates = _candidates(body, params, plan, slide)
    if not candidates:
        raise LayoutError(
            [
                "Прямой участок короче стыка: длина корпуса "
                f"{_format_mm(body)} мм не вмещает прямую не короче "
                f"{_format_mm(params.joint_length_mm)} мм."
            ]
        )
    if stack_height_mm is not None and params.print_splits:
        stacked = [
            coil
            for coil in candidates
            if coil.height_with_head_mm <= stack_height_mm + 1e-9
            and not _failures(
                coil,
                params,
                plan,
                _slide_for_count(slide, coil.straight_count),
                allow_tall=True,
            )
        ]
        if stacked:
            return min(stacked, key=lambda coil: coil.straight_count)
        raise LayoutError(
            [f"Под собранную высоту {_format_mm(stack_height_mm)} мм укладка не нашлась."]
        )
    for coil in candidates:
        bound = _slide_for_count(slide, coil.straight_count)
        if not _failures(coil, params, plan, bound):
            return coil
    if params.print_splits:
        tall = [
            coil
            for coil in candidates
            if not _failures(
                coil,
                params,
                plan,
                _slide_for_count(slide, coil.straight_count),
                allow_tall=True,
            )
        ]
        if tall:
            return min(tall, key=lambda coil: _tall_rank(coil, params))
    raise LayoutError(_fit_reasons(candidates, params, plan, slide))


def print_piece_count(height_mm: float, params: TubeParams) -> int:
    """Сколько кусков стола уйдёт на деталь этой высоты при разрезах.

    Принимает высоту детали и параметры с высотой печати. Верхний кусок
    занимает весь стол, каждый нижний — стол минус папа стыка, который
    торчит вверх. Возвращает целое не меньше единицы.
    """
    bed = params.max_height_mm
    if height_mm <= bed + 1e-9:
        return 1
    unique = bed - PRINT_PLUG_MM
    if unique <= 1e-6:
        return 1_000_000
    return 1 + math.ceil((height_mm - bed) / unique - 1e-9)


def _tall_rank(coil: Coil, params: TubeParams) -> tuple[int, int]:
    """Порядок выбора высокой укладки, когда её режут на куски.

    Принимает укладку и параметры. Меньше кусков печати — лучше: одна
    прямая в полтора метра даёт много кусков и проигрывает вязанке чуть
    выше стола. При равном числе кусков — меньше прямых. Возвращает ключ
    сортировки.
    """
    return (print_piece_count(coil.height_mm, params), coil.straight_count)


def fitting_coils(
    params: TubeParams,
    tuning: Tuning,
    trim: TrimPlan | None = None,
    slider: SliderPlan | None = None,
) -> tuple[Coil, ...]:
    """Укладки, которые входят в габарит, от меньшего числа прямых к большему.

    Принимает параметры, строй, подстройку и слайдер. Если число прямых задано,
    возвращает этот один вариант, когда он нечётный и влезает. Иначе все
    нечётные n, что проходят габарит, царгу и ход слайдера. Возвращает кортеж;
    пустой, если ничего не влезло.
    """
    plan = _resolved_trim(params, tuning, trim)
    slide = _resolved_slider(params, tuning, slider)
    blockers = _blockers(params)
    if params.straight_count is not None and params.straight_count % 2 == 0:
        return ()
    if blockers or _slider_blockers(params, slide):
        return ()
    body = tuning.body_length_mm
    if params.straight_count is not None:
        if params.straight_count > MAX_STRAIGHTS:
            return ()
        coil = _measure(params.straight_count, body, params, _slide_for_count(slide, params.straight_count))
        bound = _slide_for_count(slide, params.straight_count)
        if coil is None or _failures(coil, params, plan, bound):
            if (
                coil is not None
                and params.print_splits
                and not _failures(coil, params, plan, bound, allow_tall=True)
            ):
                return (coil,)
            return ()
        return (coil,)
    found = tuple(
        coil
        for coil in _candidates(body, params, plan, slide)
        if not _failures(coil, params, plan, _slide_for_count(slide, coil.straight_count))
    )
    if found:
        return found
    if not params.print_splits:
        return ()
    tall = [
        coil
        for coil in _candidates(body, params, plan, slide)
        if not _failures(
            coil,
            params,
            plan,
            _slide_for_count(slide, coil.straight_count),
            allow_tall=True,
        )
    ]
    return tuple(sorted(tall, key=lambda coil: _tall_rank(coil, params)))


def _resolved_trim(
    params: TubeParams,
    tuning: Tuning,
    trim: TrimPlan | None,
) -> TrimPlan | None:
    """План подстройки для этой укладки.

    Принимает параметры, строй верхней ноты и готовый план либо None.
    Если план уже передан, возвращает его. Если полутонов нет, возвращает
    None. Иначе считает план из параметров и строя.
    """
    if trim is not None:
        return trim
    if params.trim_semitones <= 0:
        return None
    return resolve_trim(params, tuning)


def _resolved_slider(
    params: TubeParams,
    tuning: Tuning,
    slider: SliderPlan | None,
) -> SliderPlan | None:
    """План слайдера для этой укладки.

    Принимает параметры, строй верхней ноты и готовый план либо None.
    Если план уже передан, возвращает его. Если полутонов нет или схема
    не выбрана, возвращает None. Иначе считает план из параметров и строя.
    """
    if slider is not None:
        return slider
    if params.slider_semitones <= 0 or not params.slider_kind:
        return None
    return resolve_slider(params, tuning)


def _slide_for_count(slide: SliderPlan | None, straight_count: int) -> SliderPlan | None:
    """План слайдера с числом колен и царгой под конкретное число прямых.

    Принимает общий план (или None) и число прямых. Для «U авто» забирает
    все нижние колена этой укладки. Для остальных U берёт заданное или
    схемное число колен и пересчитывает ход. Выдвижной конец не трогает.
    Возвращает план для проверки укладки либо None.
    """
    if slide is None:
        return None
    if not is_u_family(slide.kind):
        return slide
    if slide.kind == SLIDER_UAUTO:
        pairs = max_u_pairs(straight_count)
        if pairs < 1:
            return slide
        return plan_with_pairs(slide, pairs)
    pairs = slide.pairs if slide.pairs > 0 else default_slider_pairs(slide.kind)
    return plan_with_pairs(slide, pairs)


def _slider_blockers(params: TubeParams, slide: SliderPlan | None) -> list[str]:
    """Причины, из-за которых слайдер нельзя укладывать при любом числе прямых.

    Принимает параметры и план слайдера. U-колено при явно заданных одной
    прямой отвергается сразу, двойное U — при числе прямых меньше пяти.
    Возвращает список текстов.
    """
    if slide is None:
        return []
    count = params.straight_count
    needed = min_straight_count(slide.kind, slide.pairs)
    if count is not None and count < needed:
        return [
            f"Схеме «{slider_kind_label(slide.kind)}» нужно минимум "
            f"{needed} прямых: ветви слайдера и выход в дне."
        ]
    return []


def _blockers(params: TubeParams) -> list[str]:
    """Причины, из-за которых перебор прямых бессмыслен.

    Принимает параметры. Проверяет зазор вокруг разворота и радиус колена
    против радиуса трубы — на случай, если набор собрали минуя tube_params.
    Возвращает список текстов; пустой значит, что число прямых ещё можно
    перебирать.
    """
    reasons: list[str] = []
    span = 2.0 * params.turn_radius_mm
    needed = params.outer_diameter_mm + params.gap_mm
    if span + 1e-9 < needed:
        reasons.append(
            "Радиус разворота не лезет в зазор: "
            f"между осями {_format_mm(span)} мм, а нужно не меньше "
            f"{_format_mm(needed)} мм."
        )
    elif params.turn_radius_mm <= params.outer_diameter_mm / 2.0 + 1e-9:
        reasons.append(
            f"Радиус разворота {_format_mm(params.turn_radius_mm)} мм не больше "
            f"радиуса трубы {_format_mm(params.outer_diameter_mm / 2.0)} мм: "
            "колено схлопнется внутрь."
        )
    return reasons


def _candidates(
    body_length_mm: float,
    params: TubeParams,
    plan: TrimPlan | None,
    slide: SliderPlan | None = None,
) -> list[Coil]:
    """Все укладки, у которых прямые не короче стыка.

    Принимает длину корпуса, параметры, план подстройки и план слайдера.
    Идёт от одной прямой вверх до потолка MAX_STRAIGHTS, пока обычная прямая
    не станет короче миллиметра. Чётные числа пропускает: выход всегда в дне.
    При U-колене считает от трёх прямых, при двойном U — от пяти,
    при «U авто» — от трёх. Возвращает список Coil по возрастанию числа
    прямых. Для каждой n царги считаются уже с числом колен этой укладки.
    """
    found: list[Coil] = []
    start = min_straight_count(slide.kind, slide.pairs) if slide is not None else 1
    for count in range(start, MAX_STRAIGHTS + 1):
        if count % 2 == 0:
            continue
        bound = _slide_for_count(slide, count)
        coil = _measure(count, body_length_mm, params, bound)
        if coil is None:
            if count > 2:
                break
            continue
        found.append(coil)
    return found


def _measure(
    count: int,
    body_length_mm: float,
    params: TubeParams,
    slide: SliderPlan | None = None,
) -> Coil | None:
    """Длины прямых, высоты и габарит для конкретного числа прямых.

    Принимает число прямых, длину корпуса, параметры и необязательный план
    слайдера. Решает линейное уравнение длины оси относительно обычной
    прямой ℓ. При семействе U ветви выбранных нижних разворотов доходят
    до дна, и ℓ укорачивается, чтобы ось осталась равна корпусу. Возвращает
    Coil либо None, если ℓ короче миллиметра или первая прямая короче стыка.
    """
    radius = params.turn_radius_mm
    turn = math.pi * radius
    outer = params.outer_diameter_mm
    bottom = bottom_turn_height_mm(params)
    rise = _inlet_rise_mm(count, params)
    legs: tuple[int, ...] = ()
    if (
        slide is not None
        and is_u_family(slide.kind)
        and count >= min_straight_count(slide.kind, slide.pairs)
    ):
        legs = slider_leg_indices(slide.kind, count, slide.pairs)

    if count == 1:
        regular = body_length_mm
        lengths = (body_length_mm,)
        inlet = body_length_mm
        top = body_length_mm
        bottom = 0.0
        base = 0.0
        height = body_length_mm
    else:
        extra_floor = bottom * len(legs)
        extra = rise + (bottom if count % 2 == 1 else 0.0) + extra_floor
        regular = (body_length_mm - (count - 1) * turn - extra) / count
        if regular < _MIN_STRAIGHT_MM:
            return None
        top = bottom + regular
        inlet = top + rise
        lengths = list(_straight_lengths(count, regular, rise, bottom))
        for index in legs:
            lengths[index] += bottom
        lengths = tuple(lengths)
        base = bottom
        height = inlet
        if count >= 3:
            height = max(height, top + radius + outer / 2.0)

    if lengths[0] + 1e-9 < params.joint_length_mm:
        return None

    columns = _columns(count, params)
    width, depth = _footprint(columns, params)
    return Coil(
        layout=params.layout,
        straight_count=count,
        columns=columns,
        straight_lengths_mm=lengths,
        regular_straight_mm=regular,
        turn_count=count - 1,
        turn_radius_mm=radius,
        turn_length_mm=turn,
        axis_length_mm=sum(lengths) + (count - 1) * turn,
        bottom_turn_z_mm=bottom,
        top_turn_z_mm=top,
        inlet_z_mm=inlet,
        base_height_mm=base,
        height_mm=height,
        height_with_head_mm=max(height, inlet + params.head_reserve_mm),
        width_mm=width,
        depth_mm=depth,
        outer_diameter_mm=outer,
    )


def _inlet_rise_mm(count: int, params: TubeParams) -> float:
    """На сколько вход выше центров верхних разворотов.

    Принимает число прямых и параметры. С верхними разворотами вход
    поднимается над их макушками на весь стык: R, половина трубы,
    посадка и переходник. Без верхних разворотов вход на уровне их
    центров. Возвращает миллиметры.
    """
    if count < 3:
        return 0.0
    return params.turn_radius_mm + params.outer_diameter_mm / 2.0 + params.joint_length_mm


def _straight_lengths(
    count: int,
    regular_mm: float,
    rise_mm: float,
    bottom_mm: float,
) -> tuple[float, ...]:
    """Длины прямых по ходу канала.

    Принимает число прямых (от двух), обычную прямую, подъём входа и высоту
    центров нижних разворотов. Первая длиннее на подъём входа. Последняя при
    выходе вниз длиннее на цоколь: она доходит до стола. Возвращает кортеж.
    """
    lengths = [regular_mm] * count
    lengths[0] = regular_mm + rise_mm
    if count % 2 == 1:
        lengths[-1] = regular_mm + bottom_mm
    return tuple(lengths)


def bottom_turn_height_mm(params: TubeParams) -> float:
    """Высота центров нижних разворотов над столом — она же высота цоколя.

    Принимает параметры. Дно под каналом плюс радиус разворота плюс
    половина канала трубы. Возвращает миллиметры.
    """
    return params.floor_mm + params.turn_radius_mm + params.bore_diameter_mm / 2.0


def inlet_rise_mm(params: TubeParams) -> float:
    """На сколько вход выше центра самого высокого верхнего разворота.

    Принимает параметры. Радиус колена, половина трубы, посадка и переходник:
    так торец входа стоит над макушками, и модуль насаживается свободно.
    Возвращает миллиметры.
    """
    return _inlet_rise_mm(3, params)


def coil_from_heights(
    count: int,
    first_mm: float,
    pair_heights_mm: tuple[float, ...],
    params: TubeParams,
) -> Coil:
    """Укладка с парами разной высоты, но с коленами внизу на цоколе.

    Принимает нечётное число прямых (от трёх), длину первой прямой от
    входа до первого нижнего колена, высоты пар над цоколем (подъём и
    следующий спуск одной высоты) и параметры. Последняя прямая идёт
    сквозь цоколь до стола. Вход — на высоте цоколь плюс первая прямая.
    Возвращает Coil; ось — сумма прямых и разворотов. Если число прямых
    не сходится с числом пар, поднимает LayoutError.
    """
    pairs = (count - 1) // 2
    if count < 3 or count % 2 == 0 or len(pair_heights_mm) != pairs:
        raise LayoutError(["Высоты пар не сходятся с нечётным числом прямых."])
    radius = params.turn_radius_mm
    turn = math.pi * radius
    outer = params.outer_diameter_mm
    bottom = bottom_turn_height_mm(params)
    lengths = [first_mm]
    for index, height in enumerate(pair_heights_mm):
        lengths.append(height)
        lengths.append(height + bottom if index == pairs - 1 else height)
    tallest = max(pair_heights_mm)
    top = bottom + tallest
    inlet = bottom + first_mm
    height = max(inlet, top + radius + outer / 2.0)
    columns = _columns(count, params)
    width, depth = _footprint(columns, params)
    return Coil(
        layout=params.layout,
        straight_count=count,
        columns=columns,
        straight_lengths_mm=tuple(lengths),
        regular_straight_mm=tallest,
        turn_count=count - 1,
        turn_radius_mm=radius,
        turn_length_mm=turn,
        axis_length_mm=sum(lengths) + (count - 1) * turn,
        bottom_turn_z_mm=bottom,
        top_turn_z_mm=top,
        inlet_z_mm=inlet,
        base_height_mm=bottom,
        height_mm=height,
        height_with_head_mm=max(height, inlet + params.head_reserve_mm),
        width_mm=width,
        depth_mm=depth,
        outer_diameter_mm=outer,
    )


def bundle_plan(count: int, params: TubeParams) -> tuple[tuple[Point2, ...], float, float]:
    """Центры прямых вязанки и размах плана для числа прямых.

    Принимает число прямых и параметры. Возвращает (центры, ширина, глубина).
    """
    columns = _columns(count, params)
    width, depth = _footprint(columns, params)
    return columns, width, depth


def _columns(count: int, params: TubeParams) -> tuple[Point2, ...]:
    """Центры прямых на плане вязанки.

    Принимает число прямых и параметры. Шаг — два радиуса разворота.
    Возвращает кортеж точек шестигранной сетки.
    """
    return bundle_columns(count, 2.0 * params.turn_radius_mm)


def footprint_mm(columns: tuple[Point2, ...], params: TubeParams) -> tuple[float, float]:
    """Размах плана по x и y для любого набора прямых, первая — вход.

    Принимает центры прямых и параметры. Возвращает (ширина, глубина)
    в миллиметрах, как у укладки.
    """
    return _footprint(columns, params)


def _footprint(columns: tuple[Point2, ...], params: TubeParams) -> tuple[float, float]:
    """Размах укладки по x и y.

    Принимает центры прямых и параметры. Вокруг каждой прямой откладывает
    половину наружного диаметра, у входа — половину большего из диаметров
    трубы и конца. Возвращает (ширина, глубина) в миллиметрах.
    """
    body_radius = params.outer_diameter_mm / 2.0
    inlet_radius = max(body_radius, params.seat_outer_diameter_mm / 2.0)
    xs_low, xs_high, ys_low, ys_high = [], [], [], []
    for index, (x, y) in enumerate(columns):
        radius = inlet_radius if index == 0 else body_radius
        xs_low.append(x - radius)
        xs_high.append(x + radius)
        ys_low.append(y - radius)
        ys_high.append(y + radius)
    return max(xs_high) - min(xs_low), max(ys_high) - min(ys_low)


def _failures(
    coil: Coil,
    params: TubeParams,
    plan: TrimPlan | None,
    slide: SliderPlan | None = None,
    *,
    allow_tall: bool = False,
) -> list[str]:
    """Какие лимиты укладка превышает.

    Принимает укладку, параметры, план подстройки, план слайдера и флаг
    allow_tall: при разрезах на печать собранная высота может быть больше
    стола, тогда высоту не проверяют, но разрезы должны найтись мимо
    колен, посадки и царги. Возвращает фразы про габарит, царгу
    подстройки, слайдер и разрезы.
    """
    tall = allow_tall and params.print_splits
    reasons = envelope_failures(coil, params, ignore_height=tall)
    reasons.extend(_trim_failures(coil, plan))
    reasons.extend(_slider_failures(coil, params, slide))
    if tall and not reasons and coil.height_mm > params.max_height_mm + 1e-9:
        try:
            coil_cut_heights(
                coil, params, bottom_keep_mm=bottom_socket_mm(plan, slide)
            )
        except PrintCutError as exc:
            reasons.append(str(exc))
    return reasons


def bottom_socket_mm(trim: TrimPlan | None, slide: SliderPlan | None) -> float:
    """Сколько канала от стола занимает царга подстройки или слайдера.

    Принимает планы подстройки и слайдера. Разрез туда не ставят: стык
    «папа — мама» не должен проходить по ходу царги. Возвращает миллиметры,
    ноль без подстройки и слайдера.
    """
    keep = socket_length_mm(trim) if trim is not None else 0.0
    if slide is not None:
        keep = max(keep, slider_socket_length_mm(slide))
    return keep


def envelope_failures(
    coil: Coil,
    params: TubeParams,
    *,
    ignore_height: bool = False,
) -> list[str]:
    """Какие лимиты габарита укладка превышает.

    Принимает укладку, параметры и флаг ignore_height: не проверять высоту
    собранной вязанки, если её режут на куски стола. Возвращает фразы про
    высоту, ширину и глубину для превышенных лимитов.
    """
    reasons: list[str] = []
    if not ignore_height and coil.height_with_head_mm > params.max_height_mm + 1e-9:
        reasons.append(
            f"Мало высоты: вязанка с резервом модуля занимает "
            f"{_format_mm(coil.height_with_head_mm)} мм при лимите "
            f"{_format_mm(params.max_height_mm)} мм."
            + (
                ""
                if params.print_splits
                else " Включите разрезы на печать, чтобы собрать более высокую вязанку из кусков."
            )
        )
    if coil.width_mm > params.max_width_mm + 1e-9:
        reasons.append(
            f"Мало ширины: вязанка занимает {_format_mm(coil.width_mm)} мм "
            f"при лимите {_format_mm(params.max_width_mm)} мм."
        )
    if coil.depth_mm > params.max_depth_mm + 1e-9:
        reasons.append(
            f"Мало глубины: вязанка занимает {_format_mm(coil.depth_mm)} мм "
            f"при лимите {_format_mm(params.max_depth_mm)} мм."
        )
    return reasons


def _trim_failures(coil: Coil, plan: TrimPlan | None) -> list[str]:
    """Почему подстройка не встаёт в эту укладку.

    Принимает укладку и план подстройки. Без плана возвращает пустой список.
    Иначе проверяет, что выход в дне (нечётное число прямых) и последняя
    не короче царги.
    """
    if plan is None:
        return []
    reasons: list[str] = []
    if coil.straight_count % 2 == 0:
        reasons.append(
            "Выход должен открываться в дне: нужно нечётное число прямых."
        )
    needed = socket_length_mm(plan)
    last = coil.straight_lengths_mm[-1]
    if last + 1e-9 < needed:
        reasons.append(
            f"Последняя прямая {_format_mm(last)} мм короче трубки подстройки "
            f"{_format_mm(needed)} мм: уменьшите ход или задайте меньше прямых."
        )
    return reasons


def _slider_failures(
    coil: Coil,
    params: TubeParams,
    slide: SliderPlan | None,
) -> list[str]:
    """Почему слайдер не встаёт в эту укладку.

    Принимает укладку, параметры и план слайдера. Без плана возвращает
    пустой список. Проверяет, что царги влезают в нужные прямые и что
    печатная деталь слайдера влезает на стол любой стороной. Высота
    собранного инструмента на полном ходу сюда не входит. Ход не
    укорачивает. Возвращает список текстов.
    """
    if slide is None:
        return []
    reasons: list[str] = []
    needed = slider_socket_length_mm(slide)
    if slide.kind == SLIDER_END:
        last = coil.straight_lengths_mm[-1]
        if last + 1e-9 < needed:
            reasons.append(
                f"Последняя прямая {_format_mm(last)} мм короче царги слайдера "
                f"{_format_mm(needed)} мм: уменьшите число прямых или увеличьте "
                "высоту габарита. Ход слайдера сам не укорачивается."
            )
    elif is_u_family(slide.kind):
        needed_count = min_straight_count(slide.kind, slide.pairs)
        if coil.straight_count < needed_count:
            reasons.append(
                f"Схеме «{slider_kind_label(slide.kind)}» нужно минимум "
                f"{needed_count} прямых: ветви слайдера и выход в дне."
            )
        else:
            bound = bind_slider_columns(slide, coil.straight_count)
            for index in bound.legs:
                length = coil.straight_lengths_mm[index]
                if length + 1e-9 < needed:
                    reasons.append(
                        f"Прямая {index + 1} ветви слайдера {_format_mm(length)} мм "
                        f"короче царги {_format_mm(needed)} мм: задайте "
                        "меньше прямых, больше колен слайдера или включите "
                        "разрезы на печать. Ход сам не укорачивается."
                    )
                    break
    reasons.extend(_slider_print_failures(slide, coil.turn_radius_mm, params, coil.columns))
    return reasons


def _fit_reasons(
    candidates: list[Coil],
    params: TubeParams,
    plan: TrimPlan | None,
    slide: SliderPlan | None = None,
) -> list[str]:
    """Объясняет, почему ни одно число прямых не вошло в габарит.

    Принимает все просчитанные укладки, параметры, план подстройки и план
    слайдера. Если какой-то лимит не выполняется ни при одном числе прямых,
    называет его с лучшим достижимым размером. Если царгу нельзя вставить
    ни в одну последнюю прямую, пишет это отдельно. Если деталь слайдера
    не влезает на стол, называет её размер. Если каждый лимит по отдельности
    достижим, но не вместе, говорит об этом одной фразой. Возвращает список
    текстов.
    """
    height_ok = params.print_splits or any(
        c.height_with_head_mm <= params.max_height_mm + 1e-9 for c in candidates
    )
    width_ok = any(c.width_mm <= params.max_width_mm + 1e-9 for c in candidates)
    depth_ok = any(c.depth_mm <= params.max_depth_mm + 1e-9 for c in candidates)
    reasons: list[str] = []
    socket = bottom_socket_mm(plan, slide)
    if params.print_splits and socket + PRINT_PLUG_MM + 2.0 > params.max_height_mm:
        reasons.append(
            f"Царга {_format_mm(socket)} мм не помещается в нижний кусок печати: "
            "разрез через её ход не ставится, поэтому нижний кусок должен "
            f"вместить царгу и папу стыка над ней, а стол {_format_mm(params.max_height_mm)} мм. "
            "Уменьшите число полутонов или поднимите высоту печати, чтобы "
            "вязанка влезла без разрезов через царгу."
        )
    if not height_ok:
        lowest = min(c.height_with_head_mm for c in candidates)
        reasons.append(
            "Мало высоты: даже самая низкая укладка с резервом модуля занимает "
            f"{_format_mm(lowest)} мм при лимите {_format_mm(params.max_height_mm)} мм."
        )
    if not width_ok:
        narrowest = min(c.width_mm for c in candidates)
        reasons.append(
            f"Мало ширины: даже самая узкая укладка занимает {_format_mm(narrowest)} мм "
            f"при лимите {_format_mm(params.max_width_mm)} мм."
        )
    if not depth_ok:
        shallowest = min(c.depth_mm for c in candidates)
        reasons.append(
            f"Мало глубины: даже самая мелкая укладка занимает {_format_mm(shallowest)} мм "
            f"при лимите {_format_mm(params.max_depth_mm)} мм."
        )
    if plan is not None and candidates:
        needed = socket_length_mm(plan)
        if all(c.straight_lengths_mm[-1] + 1e-9 < needed for c in candidates):
            longest = max(c.straight_lengths_mm[-1] for c in candidates)
            reasons.append(
                "Последняя прямая даже у самой длинной укладки "
                f"{_format_mm(longest)} мм короче трубки подстройки "
                f"{_format_mm(needed)} мм: уменьшите ход подстройки."
            )
    if slide is not None and candidates:
        needed = slider_socket_length_mm(slide)
        if slide.kind == SLIDER_END and all(
            c.straight_lengths_mm[-1] + 1e-9 < needed for c in candidates
        ):
            longest = max(c.straight_lengths_mm[-1] for c in candidates)
            reasons.append(
                "Последняя прямая даже у самой длинной укладки "
                f"{_format_mm(longest)} мм короче царги слайдера "
                f"{_format_mm(needed)} мм. Ход сам не укорачивается: "
                "увеличьте высоту габарита."
            )
        if is_u_family(slide.kind):
            viable = []
            for item in candidates:
                bound = _slide_for_count(slide, item.straight_count)
                if bound is None:
                    continue
                try:
                    legs = slider_leg_indices(
                        bound.kind, item.straight_count, bound.pairs
                    )
                except SliderError:
                    continue
                if not legs:
                    continue
                shortest_leg = min(item.straight_lengths_mm[index] for index in legs)
                viable.append((item, bound, shortest_leg))
            if viable and all(
                leg + 1e-9 < slider_socket_length_mm(bound) for _item, bound, leg in viable
            ):
                closest = max(
                    viable, key=lambda entry: entry[2] - slider_socket_length_mm(entry[1])
                )
                item, bound, leg = closest
                reasons.append(
                    "Ход сам не укорачивается: ветви слайдера короче царги "
                    f"при любом числе прямых. Ближе всего {item.straight_count} "
                    f"прямых и колен U {bound.pairs}: ветвь {_format_mm(leg)} мм, "
                    f"царга {_format_mm(slider_socket_length_mm(bound))} мм. Больше "
                    "колен укорачивают и ход, и ветви: царга должна вмещать весь "
                    f"свой ход, а удлинение {_format_mm(slide.extra_length_mm)} мм "
                    "сравнимо со всей трубой. Уменьшите число полутонов."
                )
        if all(
            not printed_slider_fits_envelope(
                _slide_for_count(slide, item.straight_count) or slide,
                item.turn_radius_mm,
                params.max_height_mm,
                params.max_width_mm,
                params.max_depth_mm,
                item.columns,
                params.print_splits,
            )
            for item in candidates
        ):
            smallest = min(
                candidates,
                key=lambda item: max(
                    printed_slider_bbox_mm(
                        slide, item.turn_radius_mm, item.columns
                    )
                ),
            )
            reasons.extend(
                _slider_print_failures(
                    slide,
                    smallest.turn_radius_mm,
                    params,
                    smallest.columns,
                )
            )
    if not reasons:
        if plan is not None and any(not envelope_failures(c, params) for c in candidates):
            reasons.append(
                "Подстройка не сходится с габаритом: там, где трубка влезает "
                "в последнюю прямую, не хватает высоты, ширины или глубины."
            )
        else:
            reasons.append(
                "Мало места по высоте, ширине и глубине вместе: низкая укладка "
                "выходит за ширину или глубину, узкая — за высоту."
            )
    return reasons


def _slider_print_failures(
    slide: SliderPlan,
    turn_radius_mm: float,
    params: TubeParams,
    columns: tuple[tuple[float, float], ...] = (),
) -> list[str]:
    """Почему печатную деталь слайдера нельзя положить на стол.

    Принимает план слайдера, радиус колена, параметры с габаритом печати
    и необязательные центры прямых. Если деталь влезает любой стороной,
    возвращает пустой список. Иначе одну причину с размером детали и стола
    и, если резать её мешает тонкая стенка вставки, с этим; ход не укорачивает.
    """
    if printed_slider_fits_envelope(
        slide,
        turn_radius_mm,
        params.max_height_mm,
        params.max_width_mm,
        params.max_depth_mm,
        columns,
        params.print_splits,
    ):
        return []
    height, width, depth = printed_slider_bbox_mm(slide, turn_radius_mm, columns)
    reason = (
        f"Деталь слайдера {_format_mm(height)}×{_format_mm(width)}×"
        f"{_format_mm(depth)} мм не влезает в область печати "
        f"{_format_mm(params.max_height_mm)}×{_format_mm(params.max_width_mm)}×"
        f"{_format_mm(params.max_depth_mm)} мм ни одной стороной. "
    )
    if params.print_splits and not slider_can_be_split(slide):
        reason += (
            f"Резать её нельзя: стенка вставки {_format_mm(slider_wall_mm(slide))} мм "
            f"тоньше {_format_mm(PRINT_JOINT_MIN_WALL_MM)} мм, папа и мама сломаются. "
        )
    return [
        reason + "Ход сам не укорачивается: увеличьте габарит печати "
        "или уменьшите число полутонов."
    ]


def _too_short_reason(count: int, params: TubeParams) -> str:
    """Причина, по которой заданное число прямых не делится.

    Принимает число прямых и параметры. Возвращает текст: прямые выходят
    короче миллиметра или первая короче стыка.
    """
    return (
        f"При {count} прямых длина корпуса не делится: прямая между разворотами "
        f"короче {_format_mm(_MIN_STRAIGHT_MM)} мм или первая короче стыка "
        f"{_format_mm(params.joint_length_mm)} мм."
    )


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает короткую запись: целое без дроби,
    иначе до трёх знаков после запятой без хвостовых нулей.
    """
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")
