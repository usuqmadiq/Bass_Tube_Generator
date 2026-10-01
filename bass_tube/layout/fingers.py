"""Удобство пальцев: расстояния между соседними дырками и штраф раскладки.

Дырки открываются по очереди от выхода, поэтому соседние по оси дырки —
соседние пальцы. Меряется расстояние в пространстве между центрами дырок
на наружной стенке: две дырки на одной прямой разнесены на свой шаг по оси,
а колено между ними складывает путь, и дырки встают рядом на соседних
прямых. До FINGER_COMFORT_MM штрафа нет, дальше он растёт квадратом
растяжки. Между руками (середина ряда при пяти дырках и больше) допуск
шире — HAND_GAP_MM. Ближе FINGER_MIN_MM пальцы не помещаются — тоже штраф.
"""

from __future__ import annotations

import math

import numpy as np

from bass_tube.layout.centerline import Centerline, Vec3
from bass_tube.layout.columns import Point2

# Удобный шаг соседних пальцев одной руки, между центрами дырок.
FINGER_COMFORT_MM = 30.0
# Допуск между руками: верхняя рука выше нижней.
HAND_GAP_MM = 55.0
# Ближе подушечки пальцев не встают.
FINGER_MIN_MM = 18.0
# Слишком тесные дырки хуже растяжки: палец закрывает соседнюю.
_TOO_CLOSE_WEIGHT = 4.0
# С какого числа дырок играют двумя руками.
_TWO_HANDS_FROM = 5


def spacing_limits(count: int) -> tuple[float, ...]:
    """Допуск растяжки для каждой пары соседних дырок, по порядку от выхода.

    Принимает число дырок. С пяти дырок пара посередине — стык рук с
    допуском HAND_GAP_MM, остальные — FINGER_COMFORT_MM. Возвращает кортеж
    длиной count − 1 (пустой при одной дырке).
    """
    if count < 2:
        return ()
    limits = [FINGER_COMFORT_MM] * (count - 1)
    if count >= _TWO_HANDS_FROM:
        limits[count // 2 - 1] = HAND_GAP_MM
    return tuple(limits)


def spacing_penalty(distance_mm, limit_mm: float):
    """Штраф одной пары соседних дырок.

    Принимает расстояние (число или массив numpy) и допуск растяжки.
    Сверх допуска — квадрат растяжки, ближе FINGER_MIN_MM — квадрат
    нехватки с весом. Возвращает число или массив той же формы.
    """
    stretch = np.maximum(np.asarray(distance_mm, dtype=float) - limit_mm, 0.0)
    crowd = np.maximum(FINGER_MIN_MM - np.asarray(distance_mm, dtype=float), 0.0)
    return stretch * stretch + _TOO_CLOSE_WEIGHT * crowd * crowd


def hole_surface_point(
    centerline: Centerline,
    s_mm: float,
    outward: Vec3,
    outer_radius_mm: float,
) -> Vec3:
    """Центр дырки на наружной стенке.

    Принимает ось, координату дырки, направление наружу и наружный
    радиус трубы. Возвращает точку.
    """
    frame = centerline.sample(s_mm)
    return Vec3(
        frame.point.x + outward.x * outer_radius_mm,
        frame.point.y + outward.y * outer_radius_mm,
        frame.point.z + outward.z * outer_radius_mm,
    )


def finger_spacings_mm(
    centerline: Centerline,
    outer_radius_mm: float,
    holes: tuple[tuple[float, Vec3], ...],
) -> tuple[float, ...]:
    """Расстояния между соседними дырками, по порядку от выхода.

    Принимает ось, наружный радиус и дырки парами (s, направление наружу).
    Сортирует от выхода к входу. Возвращает кортеж длиной число дырок − 1.
    """
    ordered = sorted(holes, key=lambda item: -item[0])
    points = [
        hole_surface_point(centerline, s_mm, outward, outer_radius_mm)
        for s_mm, outward in ordered
    ]
    return tuple(
        math.dist((a.x, a.y, a.z), (b.x, b.y, b.z)) for a, b in zip(points, points[1:])
    )


def layout_penalty(spacings_mm: tuple[float, ...]) -> float:
    """Штраф всей раскладки по расстояниям от выхода.

    Принимает расстояния соседних дырок по порядку от выхода. Складывает
    штрафы пар с допусками spacing_limits. Возвращает мм².
    """
    limits = spacing_limits(len(spacings_mm) + 1)
    return float(
        sum(spacing_penalty(distance, limit) for distance, limit in zip(spacings_mm, limits))
    )


def plan_distances_mm(
    columns: tuple[Point2, ...],
    outward: tuple[Vec3 | None, ...],
    outer_radius_mm: float,
) -> np.ndarray:
    """Расстояния в плане между точками дырок на разных прямых.

    Принимает центры прямых, направления наружу по прямым (None у
    внутренних — берётся центр) и наружный радиус. Точка дырки — центр
    прямой, сдвинутый наружу на радиус. Возвращает матрицу N×N.
    """
    points = []
    for (x, y), direction in zip(columns, outward):
        if direction is None:
            points.append((x, y))
        else:
            points.append((x + direction.x * outer_radius_mm, y + direction.y * outer_radius_mm))
    array = np.asarray(points, dtype=float)
    return np.linalg.norm(array[:, None, :] - array[None, :, :], axis=2)
