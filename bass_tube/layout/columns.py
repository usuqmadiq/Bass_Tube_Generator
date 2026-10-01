"""Где стоят вертикальные прямые в плане: ряд или шестигранная вязанка.

Соседние по ходу канала прямые всегда стоят на расстоянии шага 2R:
разворот между ними — полуокружность радиуса R.
Вязанка идёт по шестигранной сетке: центр, первое кольцо из шести,
второе из двенадцати и так далее. Переход из кольца в кольцо — тоже шаг сетки.
"""

from __future__ import annotations

import math

Point2 = tuple[float, float]

# Шесть направлений шестигранной сетки в осевых координатах (q, r).
_HEX_DIRECTIONS = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))


def flat_columns(count: int, pitch_mm: float) -> tuple[Point2, ...]:
    """Прямые плоского змеевика в один ряд.

    Принимает число прямых и шаг между осями. Ставит их по оси x
    через шаг, y у всех ноль. Возвращает кортеж точек плана.
    """
    return tuple((index * pitch_mm, 0.0) for index in range(count))


def bundle_columns(count: int, pitch_mm: float) -> tuple[Point2, ...]:
    """Прямые вязанки по шестигранной сетке.

    Принимает число прямых и шаг сетки. Первая прямая — центр, дальше
    кольцо за кольцом; каждая следующая прямая — соседняя клетка предыдущей.
    Возвращает кортеж точек плана.
    """
    cells = _hex_path(count)
    return tuple(_hex_to_plane(cell, pitch_mm) for cell in cells)


def adjacent_pairs(columns: tuple[Point2, ...], pitch_mm: float) -> tuple[tuple[int, int], ...]:
    """Пары прямых, стоящих вплотную на одном шаге.

    Принимает точки плана и шаг. Возвращает пары номеров (i, j), i < j,
    расстояние между которыми равно шагу. По ним строится цоколь.
    """
    pairs: list[tuple[int, int]] = []
    for first in range(len(columns)):
        for second in range(first + 1, len(columns)):
            distance = math.dist(columns[first], columns[second])
            if abs(distance - pitch_mm) <= 1e-6 * max(1.0, pitch_mm):
                pairs.append((first, second))
    return tuple(pairs)


def _hex_path(count: int) -> list[tuple[int, int]]:
    """Путь по клеткам сетки от центра по кольцам.

    Принимает число клеток. Каждое кольцо обходится по кругу и начинается
    с клетки, соседней с последней пройденной. Возвращает список осевых
    координат длиной count.
    """
    path = [(0, 0)]
    radius = 1
    while len(path) < count:
        ring = _hex_ring(radius)
        start = next(
            index for index, cell in enumerate(ring) if _hex_distance(cell, path[-1]) == 1
        )
        ordered = ring[start:] + ring[:start]
        path.extend(ordered[: count - len(path)])
        radius += 1
    return path[:count]


def _hex_ring(radius: int) -> list[tuple[int, int]]:
    """Клетки одного кольца по кругу.

    Принимает номер кольца от 1. Начинает с клетки radius·(−1, 1) и идёт
    по шести направлениям radius шагов в каждом. Соседние в списке клетки
    соседние на сетке, последняя соседствует с первой. Возвращает список.
    """
    q, r = -radius, radius
    ring: list[tuple[int, int]] = []
    for dq, dr in _HEX_DIRECTIONS:
        for _ in range(radius):
            ring.append((q, r))
            q += dq
            r += dr
    return ring


def _hex_distance(first: tuple[int, int], second: tuple[int, int]) -> int:
    """Число шагов сетки между клетками.

    Принимает две клетки в осевых координатах. Возвращает целое расстояние.
    """
    dq = first[0] - second[0]
    dr = first[1] - second[1]
    return max(abs(dq), abs(dr), abs(dq + dr))


def _hex_to_plane(cell: tuple[int, int], pitch_mm: float) -> Point2:
    """Центр клетки на плане.

    Принимает осевые координаты и шаг. Возвращает (x, y) в миллиметрах:
    x = шаг·(q + r/2), y = шаг·r·√3/2.
    """
    q, r = cell
    return (pitch_mm * (q + r / 2.0), pitch_mm * r * math.sqrt(3.0) / 2.0)
