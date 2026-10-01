"""Зависимые размеры: наружный диаметр трубы главный, остальное под него.

Скорость звука сюда не входит — это константа мира в constants, не поле формы.
Геометрия колена, дна, стенки и минимальной глубины габарита следует из
диаметра трубы, зазора и стенки, чтобы не ловить отказ «не лезет / схлопнется».
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Канал не тоньше миллиметра: стенка не имеет права съесть отверстие.
_MIN_BORE_MM = 1.0
# Колено чуть больше радиуса трубы, иначе внутренняя стенка сомкнётся.
_KNEE_CLEARANCE_MM = 0.05
# Дно чуть толще стенки, иначе нижний разворот вылезет под стол.
_FLOOR_OVER_WALL_MM = 0.05
# Наименьший просвет между трубами через ряд шестигранника: касание по
# касательной OCC сливает с потерей грани колена.
_HEX_MIN_GAP_MM = 0.5


@dataclass(frozen=True, slots=True)
class FittedGeometry:
    """Подогнанные под наружный диаметр зависимые размеры.

    wall_thickness_mm — стенка, не толще чем оставляет канал.
    floor_mm — дно цоколя не тоньше стенки.
    turn_radius_mm — радиус разворота, чтобы колено не схлопнулось
    и соседние трубы держали зазор.
    max_depth_mm — глубина габарита не меньше самой толстой трубы.
    """

    wall_thickness_mm: float
    floor_mm: float
    turn_radius_mm: float
    max_depth_mm: float


def min_turn_radius_mm(outer_diameter_mm: float, gap_mm: float) -> float:
    """Наименьший радиус разворота под диаметр трубы и зазор.

    Принимает наружный диаметр трубы и зазор между соседними трубами.
    Между осями соседних прямых должно быть не меньше D_o + g, и радиус
    больше половины трубы, иначе колено схлопнется. В шестиграннике шаг
    сетки 2R, а колено между двумя прямыми проходит от их общего соседа на
    √3·R: там тоже нужен зазор, хотя бы полмиллиметра. Иначе стенки
    касаются вскользь, OCC теряет грань колена, а у центральной входной
    прямой толстой трубы каналы сходятся. Возвращает миллиметры.
    """
    gap = max(gap_mm, 0.0)
    by_gap = (outer_diameter_mm + gap) / 2.0
    by_hex = (outer_diameter_mm + max(gap, _HEX_MIN_GAP_MM)) / math.sqrt(3.0)
    by_knee = outer_diameter_mm / 2.0 + _KNEE_CLEARANCE_MM
    return max(by_gap, by_hex, by_knee)


def max_wall_thickness_mm(outer_diameter_mm: float, seat_outer_diameter_mm: float) -> float:
    """Самая толстая стенка, при которой ещё есть канал.

    Принимает наружные диаметры трубы и конца под модуль. Канал не короче
    _MIN_BORE_MM и в трубе, и в конце. Возвращает миллиметры, не меньше
    пяти сотых: нулевую стенку эта функция не чинит.
    """
    thinnest = min(outer_diameter_mm, seat_outer_diameter_mm)
    return max((thinnest - _MIN_BORE_MM) / 2.0, 0.05)


def min_floor_mm(wall_thickness_mm: float) -> float:
    """Самое тонкое дно цоколя под данной стенкой.

    Принимает толщину стенки. Возвращает стенку плюс небольшой запас,
    чтобы низ канала не оказался на столе или под ним.
    """
    return wall_thickness_mm + _FLOOR_OVER_WALL_MM


def min_depth_mm(outer_diameter_mm: float, seat_outer_diameter_mm: float) -> float:
    """Наименьшая глубина габарита, в которую встанет одна труба.

    Принимает диаметры трубы и конца. Возвращает больший из них:
    одна труба вязанки не тоньше своего наружного диаметра.
    """
    return max(outer_diameter_mm, seat_outer_diameter_mm)


def fit_geometry(
    outer_diameter_mm: float,
    seat_outer_diameter_mm: float,
    wall_thickness_mm: float,
    floor_mm: float,
    turn_radius_mm: float | None,
    gap_mm: float,
    max_depth_mm: float,
) -> FittedGeometry:
    """Подгоняет стенку, дно, радиус и глубину под наружный диаметр.

    Принимает сечение, дно, радиус (None — взять минимум), зазор и глубину
    габарита. Наружный диаметр трубы не меняет. Стенку ужимает, только если
    она съела канал. Радиус поднимает до минимума, больший оставляет.
    Дно поднимает выше стенки. Глубину поднимает, чтобы одна труба влезла.
    Возвращает FittedGeometry. Нулевую и отрицательную стенку не чинит:
    их отвергнет проверка входа.
    """
    wall = wall_thickness_mm
    if wall > 0.0:
        wall = min(wall, max_wall_thickness_mm(outer_diameter_mm, seat_outer_diameter_mm))
    floor = max(floor_mm, min_floor_mm(wall) if wall > 0.0 else floor_mm)
    needed_radius = min_turn_radius_mm(outer_diameter_mm, gap_mm)
    radius = needed_radius if turn_radius_mm is None else max(turn_radius_mm, needed_radius)
    depth = max(max_depth_mm, min_depth_mm(outer_diameter_mm, seat_outer_diameter_mm))
    return FittedGeometry(
        wall_thickness_mm=wall,
        floor_mm=floor,
        turn_radius_mm=radius,
        max_depth_mm=depth,
    )
