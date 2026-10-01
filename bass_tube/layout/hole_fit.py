"""Подбор высот пар прямых, при которых все дырки лежат на прямых снаружи.

Геометрия жёсткая: все нижние развороты на цоколе, последняя прямая идёт
сквозь цоколь в стол, вход — над самым высоким верхним разворотом. Свобода
одна: высота каждой пары (подъём и следующий спуск одной длины) и длина
первой прямой. Ось должна остаться длиной корпуса.

Вдоль оси s это значит: каждый разворот — отрезок длины πR, и ни одна дырка
не должна попасть на него или ближе отступа к нему; дырка не должна стоять на
внутренней прямой, в цоколе и в царге подстройки. Высоты перебираются
динамикой по парам от выхода к входу на сетке 0,5 мм.

Цель — удобство пальцев, потом высота. Если между соседними дырками одно
колено, их высоты зависят только от того, где это колено стоит, а колено
принадлежит одной паре: штраф растяжки считается по паре и складывается
в динамике. Колено между далёкими дырками ставит их рядом на соседних
прямых. При равном штрафе берётся вариант с самой низкой высокой парой —
так пары выходят ровнее, а деталь ниже.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from bass_tube.layout.fingers import spacing_penalty

_GRID_MM = 0.5
# Штрафы ближе этого (мм²) считаются равными: тогда решает высота детали.
_PENALTY_TIE_MM2 = 5.0


@dataclass(frozen=True, slots=True)
class PairFit:
    """Найденная раскладка высот.

    first_mm — первая прямая от входа до первого нижнего разворота.
    pair_heights_mm — высоты пар над цоколем по ходу канала.
    margin_mm — отступ дырок от разворотов, с которым раскладка найдена.
    penalty_mm2 — оценка штрафа пальцев по плану центров прямых.
    """

    first_mm: float
    pair_heights_mm: tuple[float, ...]
    margin_mm: float
    penalty_mm2: float = 0.0


@dataclass(frozen=True, slots=True)
class FingerModel:
    """Что решателю нужно знать о пальцах.

    plan_mm — расстояния в плане между точками дырок на прямых (N×N).
    limits_mm — допуск растяжки каждой пары соседних дырок в порядке
    возрастания s (от входа к выходу).
    """

    plan_mm: np.ndarray
    limits_mm: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class FitLimits:
    """Числа, которые решатель берёт из параметров и строя.

    body_mm — длина оси. turn_mm — длина разворота πR. base_mm — высота
    цоколя (центры нижних разворотов). rise_mm — подъём входа над центром
    самого высокого верхнего разворота. joint_mm — посадка с переходником
    на первой прямой. min_pair_mm и max_pair_mm — пределы высоты пары.
    max_first_mm — самая длинная первая прямая, при которой вход с модулем
    ещё в высоте печати. exit_keep_mm — сколько от выхода занято цоколем
    или царгой подстройки: туда дырку не поставить. socket_mm — царга,
    которая должна целиком лечь в последнюю прямую.
    """

    body_mm: float
    turn_mm: float
    base_mm: float
    rise_mm: float
    joint_mm: float
    min_pair_mm: float
    max_pair_mm: float
    max_first_mm: float
    exit_keep_mm: float
    socket_mm: float


def fit_pair_heights(
    count: int,
    outer: tuple[bool, ...],
    holes_s_mm: tuple[float, ...],
    limits: FitLimits,
    margin_mm: float,
    fingers: FingerModel | None = None,
) -> PairFit | None:
    """Подбирает высоты пар для нечётного числа прямых.

    Принимает число прямых (от трёх), флаги «с этой прямой можно смотреть
    наружу» по номерам прямых, координаты дырок, пределы, отступ дырки от
    разворота и необязательную модель пальцев. С моделью ищет наименьший
    штраф растяжки, при равном — самую низкую деталь; без неё — просто
    самую низкую. Если удобные пальцам пути не проходят по высоте входа,
    отдаёт самую низкую раскладку. Возвращает PairFit либо None, если при
    этом числе прямых дырки на прямые снаружи не ложатся.
    """
    if count < 3 or count % 2 == 0 or len(outer) != count:
        return None
    holes = np.sort(np.asarray(holes_s_mm, dtype=float))
    body = limits.body_mm
    turn = limits.turn_mm
    if not _clear(holes, body - limits.exit_keep_mm - margin_mm, body + 1.0):
        return None
    if not _clear(holes, -1.0, limits.joint_mm + margin_mm):
        return None
    pairs = (count - 1) // 2
    low = limits.min_pair_mm
    high = limits.max_pair_mm
    if high < low:
        return None
    steps = int(math.floor((high - low) / _GRID_MM + 1e-9))
    heights = low + _GRID_MM * np.arange(steps + 1)
    # Сумма высот всех пар не больше того, что оставляет самая короткая первая прямая.
    budget = body - limits.base_mm - (count - 1) * turn - (low + limits.rise_mm)
    max_sum = budget / 2.0
    if max_sum < pairs * low:
        return None

    # best[j] — наименьшая «самая высокая пара» среди пар i..m при сумме индексов j,
    # penalty[j] — штраф пальцев этих пар; сравнение сначала по штрафу.
    best_next = np.zeros(1)
    penalty_next = np.zeros(1)
    choices: list[np.ndarray] = []
    for pair in range(pairs - 1, -1, -1):
        suffix = pairs - pair
        size = min(suffix * steps, int(math.floor((max_sum - suffix * low) / _GRID_MM + 1e-9))) + 1
        if size <= 0:
            return None
        best = np.full(size, np.inf)
        penalty = np.full(size, np.inf)
        choice = np.full(size, -1, dtype=np.int32)
        next_index = np.arange(best_next.size)
        finite = np.isfinite(best_next)
        after = pairs - 1 - pair
        for k, height in enumerate(heights):
            if k >= size:
                break
            span = min(best_next.size, size - k)
            if span <= 0:
                break
            j_next = next_index[:span]
            usable = finite[:span]
            if not usable.any():
                continue
            total = (suffix * low) + (j_next + k) * _GRID_MM
            start = body - limits.base_mm - turn - 2.0 * after * turn - 2.0 * total
            ok = usable & _pair_ok(
                holes, start, height, pair, pairs, count, outer, limits, margin_mm
            )
            if not ok.any():
                continue
            value = np.maximum(best_next[:span], height)
            cost = penalty_next[:span] + _pair_cost(
                holes, start, height, pair, pairs, limits, fingers
            )
            target = slice(k, k + span)
            known = penalty[target]
            with np.errstate(invalid="ignore"):
                same = np.abs(cost - known) <= 1e-9
            better = ok & (
                ~np.isfinite(known)
                | (cost < known - 1e-9)
                | (same & (value < best[target]))
            )
            if better.any():
                best[target] = np.where(better, value, best[target])
                penalty[target] = np.where(better, cost, known)
                choice[target] = np.where(better, k, choice[target])
        if not np.isfinite(best).any():
            return None
        best_next = best
        penalty_next = penalty
        choices.append(choice)
    choices.reverse()

    totals = pairs * low + np.arange(best_next.size) * _GRID_MM
    first = body - limits.base_mm - (count - 1) * turn - 2.0 * totals
    ok = np.isfinite(best_next)
    ok &= first + 1e-9 >= best_next + limits.rise_mm
    ok &= first + 1e-9 >= limits.joint_mm
    ok &= first <= limits.max_first_mm + 1e-9
    ok &= _clear_many(holes, first - margin_mm, first + turn + margin_mm)
    if not outer[0]:
        ok &= _clear_many(holes, np.full_like(first, -1.0), first)
    if not ok.any():
        if fingers is None:
            return None
        # Удобный пальцам путь мог поднять самую высокую пару выше входа;
        # тогда годится хотя бы самая низкая раскладка.
        return fit_pair_heights(count, outer, holes_s_mm, limits, margin_mm)
    total_penalty = penalty_next + _first_cost(holes, first, limits, fingers)
    lowest = float(total_penalty[ok].min())
    # Самая низкая деталь — самая короткая первая прямая, то есть наибольшая сумма высот.
    best_index = int(np.flatnonzero(ok & (total_penalty <= lowest + _PENALTY_TIE_MM2))[-1])
    index = best_index
    chosen: list[float] = []
    for pair in range(pairs):
        k = int(choices[pair][index])
        if k < 0:
            return None
        chosen.append(float(low + k * _GRID_MM))
        index -= k
    return PairFit(
        first_mm=float(first[best_index]),
        pair_heights_mm=tuple(chosen),
        margin_mm=margin_mm,
        penalty_mm2=float(total_penalty[best_index]),
    )


def _pair_cost(
    holes: np.ndarray,
    start: np.ndarray,
    height: float,
    pair: int,
    pairs: int,
    limits: FitLimits,
    fingers: FingerModel | None,
) -> np.ndarray:
    """Штраф пальцев за соседние дырки, у которых первая стоит на этой паре.

    Принимает отсортированные дырки, массив s начала подъёма, высоту пары,
    её номер, число пар, пределы и модель пальцев. Если вторая дырка на той
    же прямой, расстояние — шаг по оси. Если между ними колено этой пары,
    вторая считается на следующей прямой: высота обеих зависит только от
    места колена, в плане — расстояние между прямыми. Без модели или без
    дырок рядом возвращает нули. Возвращает массив той же длины, что start.
    """
    if fingers is None or holes.size < 2:
        return np.zeros_like(start)
    turn = limits.turn_mm
    up = 1 + 2 * pair
    down = up + 1
    last = pair == pairs - 1
    high_edge = limits.body_mm if last else float(start.max()) + 2.0 * height + turn
    firsts = holes[:-1]
    chosen = np.flatnonzero((firsts >= float(start.min()) - 1e-9) & (firsts <= high_edge + 1e-9))
    if chosen.size == 0:
        return np.zeros_like(start)
    plan = fingers.plan_mm
    first = holes[chosen][:, None]
    second = holes[chosen + 1][:, None]
    limit = np.asarray(fingers.limits_mm, dtype=float)[chosen][:, None]
    begin = start[None, :]
    top = begin + height
    down_start = top + turn
    down_end = down_start + height
    step = second - first
    # Высоты над цоколем: на подъёме растут от начала, на спуске падают от макушки.
    across_top = np.hypot(plan[up][down], (first - begin) - (height - (second - down_start)))
    up_distance = np.where(second <= top, step, across_top)
    on_up = (first >= begin) & (first <= top)
    if last:
        on_down = first >= down_start
        down_distance = np.broadcast_to(step, on_down.shape)
    else:
        on_down = (first >= down_start) & (first <= down_end)
        across_bottom = np.hypot(
            plan[down][up + 2],
            (height - (first - down_start)) - (second - down_end - turn),
        )
        down_distance = np.where(second <= down_end, step, across_bottom)
    cost = np.where(on_up, spacing_penalty(up_distance, limit), 0.0)
    cost += np.where(on_down, spacing_penalty(down_distance, limit), 0.0)
    return cost.sum(axis=0)


def _first_cost(
    holes: np.ndarray,
    first: np.ndarray,
    limits: FitLimits,
    fingers: FingerModel | None,
) -> np.ndarray:
    """Штраф пальцев за дырки на первой прямой (от входа до первого колена).

    Принимает дырки, массив длин первой прямой, пределы и модель пальцев.
    Считается как у пары: та же прямая — шаг по оси, за коленом — соседняя
    прямая на высоте от места колена. Возвращает массив длины first.
    """
    cost = np.zeros_like(first)
    if fingers is None or holes.size < 2:
        return cost
    turn = limits.turn_mm
    base = limits.base_mm
    plan = fingers.plan_mm
    for index in range(holes.size - 1):
        a, b = float(holes[index]), float(holes[index + 1])
        if a > float(first.max()) + 1e-9:
            break
        on_first = a <= first
        across = np.hypot(plan[0][1], (base + first - a) - (base + (b - first - turn)))
        distance = np.where(b <= first, b - a, across)
        cost += np.where(on_first, spacing_penalty(distance, fingers.limits_mm[index]), 0.0)
    return cost


def _pair_ok(
    holes: np.ndarray,
    start: np.ndarray,
    height: float,
    pair: int,
    pairs: int,
    count: int,
    outer: tuple[bool, ...],
    limits: FitLimits,
    margin: float,
) -> np.ndarray:
    """Годится ли пара с этой высотой при каждом из начал.

    Принимает дырки, массив s начала подъёма, высоту пары, её номер, число
    пар, число прямых, флаги наружных прямых, пределы и отступ. Проверяет:
    верхний разворот и следующий нижний без дырок с отступом, на внутренних
    прямых дырок нет, у последней пары царга помещается. Возвращает массив
    флагов той же длины, что start.
    """
    turn = limits.turn_mm
    up = 1 + 2 * pair
    down = up + 1
    last = pair == pairs - 1
    top = start + height
    ok = _clear_many(holes, top - margin, top + turn + margin)
    down_start = top + turn
    down_end = down_start + height
    if not outer[up]:
        ok &= _clear_many(holes, start, top)
    if last:
        if height + limits.base_mm + 1e-9 < limits.socket_mm:
            return np.zeros_like(ok)
        if not outer[down]:
            ok &= _clear_many(holes, down_start, np.full_like(start, limits.body_mm))
    else:
        ok &= _clear_many(holes, down_end - margin, down_end + turn + margin)
        if not outer[down]:
            ok &= _clear_many(holes, down_start, down_end)
    return ok


def _clear(holes: np.ndarray, low: float, high: float) -> bool:
    """Нет ли дырок на отрезке [low, high].

    Принимает отсортированные координаты и границы. Возвращает True, если пусто.
    """
    if high < low:
        return True
    return int(np.searchsorted(holes, low, "left")) == int(np.searchsorted(holes, high, "right"))


def _clear_many(holes: np.ndarray, low: np.ndarray, high: np.ndarray) -> np.ndarray:
    """То же для массива отрезков.

    Принимает отсортированные координаты и массивы границ. Возвращает массив
    флагов: True там, где на отрезке нет ни одной дырки.
    """
    low = np.asarray(low, dtype=float)
    high = np.asarray(high, dtype=float)
    return np.searchsorted(holes, low, "left") == np.searchsorted(holes, high, "right")
