"""Раскладка пары мелодия + дрон в одну деталь, без CAD.

Мелодия уже уложена своим расчётом: вход в центре её вязанки. Дрон
укладывается под ту же высоту входа, чтобы насадка на две мембраны
легла плашмя: первая прямая дрона идёт от входа до цоколя, пары прямых
одной высоты добирают длину корпуса, колени ниже входа на весь стык.
Путь дрона по сетке обращён: вход на краю его вязанки, выход в центре.
Так вход дрона встаёт на 48 мм от входа мелодии, а остальная вязанка
дрона уходит в сторону.

Положение дрона ищется перебором: направление от входа мелодии ко
входу дрона и поворот вязанки дрона вокруг своего входа на шаг
шестигранной сетки (прямо и зеркально). Прямые и колени
разных труб в плане не ближе наружного диаметра плюс зазор, лучи дырок
мелодии не упираются в дрон, общий план влезает в стол (при нужде вся
пара поворачивается). Из подходящих берётся самый компактный план.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from bass_tube.acoustics.trim import TrimPlan, socket_length_mm
from bass_tube.layout.centerline import Vec3
from bass_tube.layout.coil import (
    MAX_STRAIGHTS,
    Coil,
    bottom_turn_height_mm,
    coil_from_heights,
    footprint_mm,
    inlet_rise_mm,
)
from bass_tube.layout.columns import Point2, bundle_columns
from bass_tube.layout.holes import PlacedHole
from bass_tube.params import TubeParams

# Шаг перебора направления от входа мелодии ко входу дрона, градусы.
_PLACE_STEP_DEG = 5.0
# Повороты вязанки дрона и всей пары — только на шаг шестигранной сетки:
# колени тогда ориентированы как у одиночной трубы, а на произвольных
# углах булевы операции OCC изредка дают невалидное тело.
_GRID_STEP_DEG = 60.0
# Шаг точек на коленах при проверке зазора в плане, мм.
_SAMPLE_MM = 1.0
# Длина свободного коридора перед дыркой мелодии, мм.
_FINGER_REACH_MM = 25.0


@dataclass(frozen=True, slots=True)
class PairPlacement:
    """Найденное положение пары в общих координатах детали.

    melody — укладка мелодии, повёрнутая под стол; вход по-прежнему в
    начале координат. drone — укладка дрона на месте: вход на шаге входов
    от мелодии. melody_holes — дырки мелодии с повёрнутым направлением.
    min_distance_mm — наименьшее расстояние в плане между осями прямых и
    колен разных труб. width_mm, depth_mm — габарит общего плана.
    """

    melody: Coil
    drone: Coil
    melody_holes: tuple[PlacedHole, ...]
    min_distance_mm: float
    width_mm: float
    depth_mm: float


def drone_coils_for_inlet(
    params: TubeParams,
    body_length_mm: float,
    inlet_z_mm: float,
    trim: TrimPlan | None,
) -> tuple[list[Coil], list[str]]:
    """Укладки дрона с входом на заданной высоте, от меньшего числа прямых.

    Принимает параметры дрона, длину его корпуса, высоту торца входа
    мелодии и подстройку дрона. Первая прямая — от входа до цоколя, пары
    добирают длину корпуса. Пары одной высоты, но последняя не ниже
    царги подстройки (она в последней прямой): если ровные пары короче,
    последняя поднимается под царгу, остальные ниже. Пара не ниже
    диаметра со стенкой, колени ниже входа на весь стык. Путь по сетке
    обращён: вход на краю вязанки. Возвращает (подходящие укладки,
    причины отказа для текста ошибки).
    """
    base = bottom_turn_height_mm(params)
    first = inlet_z_mm - base
    turn = math.pi * params.turn_radius_mm
    rise = inlet_rise_mm(params)
    min_pair = params.outer_diameter_mm + params.wall_thickness_mm
    max_pair = first - rise
    socket = socket_length_mm(trim) if trim is not None else 0.0
    last_pair = max(min_pair, socket - base)
    found: list[Coil] = []
    too_short = True
    for count in range(3, MAX_STRAIGHTS + 1, 2):
        pairs = (count - 1) // 2
        total = body_length_mm - first - base - (count - 1) * turn
        even = total / (count - 1)
        if even < min_pair - 1e-9:
            break
        too_short = False
        if even >= last_pair - 1e-9:
            heights = (even,) * pairs
        elif pairs > 1:
            rest = (total - 2.0 * last_pair) / (2.0 * (pairs - 1))
            heights = (rest,) * (pairs - 1) + (last_pair,)
        else:
            continue
        if max(heights) > max_pair + 1e-9 or min(heights) < min_pair - 1e-9:
            continue
        coil = coil_from_heights(count, first, heights, params)
        found.append(with_columns(coil, tuple(reversed(coil.columns)), params))
    reasons: list[str] = []
    if not found:
        if last_pair > max_pair + 1e-9:
            reasons.append(
                f"Царга подстройки дрона {_format_mm(socket)} мм не встаёт в последнюю "
                f"прямую под входом на высоте {_format_mm(inlet_z_mm)} мм. Уменьшите "
                "подстройку дрона или поднимите высоту печати."
            )
        elif too_short:
            reasons.append(
                f"Дрон слишком короткий для входа на высоте {_format_mm(inlet_z_mm)} мм: "
                f"пары прямых выходят ниже {_format_mm(min_pair)} мм. Возьмите ноту "
                "дрона ниже или уменьшите высоту печати."
            )
        else:
            reasons.append(
                f"Дрон не укладывается под вход на высоте {_format_mm(inlet_z_mm)} мм: "
                "колени не встают ниже входа. Поднимите высоту печати."
            )
    return found, reasons


def with_columns(coil: Coil, columns: tuple[Point2, ...], params: TubeParams) -> Coil:
    """Та же укладка с другими центрами прямых.

    Принимает укладку, новые центры по ходу канала и параметры. Ось
    строится по этим центрам, поэтому переставленный или сдвинутый набор
    двигает всё тело. Габарит плана пересчитывается. Возвращает Coil.
    """
    width, depth = footprint_mm(columns, params)
    return replace(coil, columns=columns, width_mm=width, depth_mm=depth)


def place_pair(
    melody: Coil,
    melody_holes: tuple[PlacedHole, ...],
    drone: Coil,
    params: TubeParams,
    spacing_mm: float,
) -> PairPlacement | None:
    """Ищет положение дрона рядом с мелодией и поворот пары под стол.

    Принимает укладку мелодии (вход — первая прямая), её дырки, укладку
    дрона с входом первой прямой, общие параметры и шаг осей входов.
    Перебирает направление на вход дрона через 5° и поворот дрона вокруг
    входа на шаг сетки, прямо и зеркально — колени остаются в тех же
    направлениях, что у одиночной трубы. Трубы в плане не ближе
    наружного диаметра плюс зазор, коридор перед
    каждой дыркой мелодии свободен от дрона, общий план влезает в стол.
    Возвращает самое компактное положение или None.
    """
    limit = params.outer_diameter_mm + params.gap_mm + _SAMPLE_MM
    origin = np.array(melody.columns[0])
    melody_pts = _samples(np.array(melody.columns) - origin)
    rays = _hole_rays(melody, melody_holes, params)
    finger = params.outer_diameter_mm / 2.0 + params.hole_diameter_mm / 2.0
    drone_cols = np.array(drone.columns) - np.array(drone.columns[0])
    drone_pts = _samples(drone_cols)
    mirror = np.array([1.0, -1.0])
    spins = _rotations(np.radians(np.arange(0.0, 360.0, _GRID_STEP_DEG)))
    spun_cols = np.concatenate(
        [
            np.einsum("kij,nj->kni", spins, drone_cols),
            np.einsum("kij,nj->kni", spins, drone_cols * mirror),
        ]
    )
    spun_pts = np.concatenate(
        [
            np.einsum("kij,nj->kni", spins, drone_pts),
            np.einsum("kij,nj->kni", spins, drone_pts * mirror),
        ]
    )
    best: tuple[float, float, PairPlacement] | None = None
    for angle in np.radians(np.arange(0.0, 360.0, _PLACE_STEP_DEG)):
        inlet = spacing_mm * np.array([math.cos(angle), math.sin(angle)])
        if _min_distance(melody_pts, inlet[None, :]) < limit:
            continue
        placed_pts = spun_pts + inlet
        gaps = _min_distance_batch(melody_pts, placed_pts)
        for index in np.nonzero(gaps >= limit)[0]:
            if rays.size and _min_distance(placed_pts[index], rays) < finger:
                continue
            columns = spun_cols[index] + inlet
            fit = _bed_fit(melody.columns, columns, origin, params)
            if fit is None:
                continue
            area, theta, width, depth = fit
            score = (area, -float(gaps[index]))
            if best is not None and score >= best[:2]:
                continue
            placement = _placement(
                melody, melody_holes, drone, columns + origin, theta, origin,
                float(gaps[index]) - _SAMPLE_MM, width, depth, params,
            )
            best = (score[0], score[1], placement)
    return None if best is None else best[2]


def _placement(
    melody: Coil,
    holes: tuple[PlacedHole, ...],
    drone: Coil,
    drone_columns: np.ndarray,
    theta: float,
    origin: np.ndarray,
    min_distance_mm: float,
    width_mm: float,
    depth_mm: float,
    params: TubeParams,
) -> PairPlacement:
    """Собирает PairPlacement: поворачивает обе укладки и дырки на theta.

    Принимает укладки, дырки, центры дрона в координатах мелодии, угол
    поворота пары под стол, центр поворота (вход мелодии), зазор и габарит.
    Возвращает PairPlacement.
    """
    melody_cols = _turn_points(np.array(melody.columns), theta, origin)
    drone_cols = _turn_points(drone_columns, theta, origin)
    cosine, sine = math.cos(theta), math.sin(theta)
    turned = tuple(
        replace(
            hole,
            outward=Vec3(
                cosine * hole.outward.x - sine * hole.outward.y,
                sine * hole.outward.x + cosine * hole.outward.y,
                hole.outward.z,
            ),
        )
        for hole in holes
    )
    return PairPlacement(
        melody=with_columns(melody, melody_cols, params),
        drone=with_columns(drone, drone_cols, params),
        melody_holes=turned,
        min_distance_mm=min_distance_mm,
        width_mm=width_mm,
        depth_mm=depth_mm,
    )


def _bed_fit(
    melody_columns: tuple[Point2, ...],
    drone_columns: np.ndarray,
    origin: np.ndarray,
    params: TubeParams,
) -> tuple[float, float, float, float] | None:
    """Поворот пары, при котором общий план влезает в стол.

    Принимает центры мелодии, центры дрона относительно входа мелодии,
    вход мелодии и параметры. У входов радиус посадки, у остальных — трубы.
    Перебирает повороты на шаг сетки (0°, 60°, 120°). Возвращает
    (площадь, угол, ширина, глубина) самого компактного подходящего или None.
    """
    points = np.vstack([np.array(melody_columns) - origin, drone_columns])
    body = params.outer_diameter_mm / 2.0
    seat = max(body, params.seat_outer_diameter_mm / 2.0)
    radii = np.full(len(points), body)
    radii[0] = seat
    radii[len(melody_columns)] = seat
    thetas = np.radians(np.arange(0.0, 180.0, _GRID_STEP_DEG))
    rotated = np.einsum("kij,nj->kni", _rotations(thetas), points)
    xs, ys = rotated[..., 0], rotated[..., 1]
    widths = (xs + radii).max(axis=1) - (xs - radii).min(axis=1)
    depths = (ys + radii).max(axis=1) - (ys - radii).min(axis=1)
    fits = (widths <= params.max_width_mm + 1e-9) & (depths <= params.max_depth_mm + 1e-9)
    if not fits.any():
        return None
    areas = np.where(fits, widths * depths, np.inf)
    index = int(np.argmin(areas))
    return float(areas[index]), float(thetas[index]), float(widths[index]), float(depths[index])


def _hole_rays(melody: Coil, holes: tuple[PlacedHole, ...], params: TubeParams) -> np.ndarray:
    """Точки коридора перед каждой дыркой мелодии в плане.

    Принимает укладку мелодии, её дырки и параметры. От стенки наружу по
    направлению дырки через миллиметр на длину пальца. Координаты — от
    входа мелодии. Возвращает массив точек (может быть пустым).
    """
    origin = np.array(melody.columns[0])
    start = params.outer_diameter_mm / 2.0
    steps = np.arange(start, start + _FINGER_REACH_MM + 1e-9, _SAMPLE_MM)
    points = []
    for hole in holes:
        center = np.array(melody.columns[hole.column]) - origin
        direction = np.array([hole.outward.x, hole.outward.y])
        norm = np.linalg.norm(direction)
        if norm < 1e-9:
            continue
        points.append(center + np.outer(steps, direction / norm))
    if not points:
        return np.zeros((0, 2))
    return np.vstack(points)


def _samples(columns: np.ndarray) -> np.ndarray:
    """Точки оси в плане: центры прямых и точки на коленах между ними.

    Принимает центры прямых по ходу канала. Колено в плане — отрезок между
    соседними центрами, точки через миллиметр. Возвращает массив точек.
    """
    points = [columns]
    for first, second in zip(columns[:-1], columns[1:]):
        length = float(np.linalg.norm(second - first))
        count = max(int(math.ceil(length / _SAMPLE_MM)), 1)
        steps = np.linspace(0.0, 1.0, count + 1)[1:-1]
        if steps.size:
            points.append(first + np.outer(steps, second - first))
    return np.vstack(points)


def _rotations(angles: np.ndarray) -> np.ndarray:
    """Матрицы поворота плана на заданные углы.

    Принимает углы в радианах. Возвращает массив k×2×2.
    """
    cosine, sine = np.cos(angles), np.sin(angles)
    return np.stack([np.stack([cosine, -sine], -1), np.stack([sine, cosine], -1)], -2)


def _turn_points(points: np.ndarray, theta: float, origin: np.ndarray) -> tuple[Point2, ...]:
    """Поворачивает точки плана вокруг центра.

    Принимает точки, угол в радианах и центр. Возвращает кортеж точек.
    """
    matrix = _rotations(np.array([theta]))[0]
    turned = (points - origin) @ matrix.T + origin
    return tuple((float(x), float(y)) for x, y in turned)


def _min_distance(first: np.ndarray, second: np.ndarray) -> float:
    """Наименьшее расстояние между точками двух наборов.

    Принимает два массива точек n×2 и m×2. Возвращает число.
    """
    diff = first[:, None, :] - second[None, :, :]
    return float(np.sqrt((diff * diff).sum(axis=-1).min()))


def _min_distance_batch(fixed: np.ndarray, moving: np.ndarray) -> np.ndarray:
    """Наименьшее расстояние от набора до каждого из k сдвинутых наборов.

    Принимает неподвижные точки n×2 и k наборов k×m×2. Возвращает массив k.
    """
    squared = (
        (moving * moving).sum(-1)[:, :, None]
        + (fixed * fixed).sum(-1)[None, None, :]
        - 2.0 * np.einsum("kmj,nj->kmn", moving, fixed)
    )
    return np.sqrt(np.maximum(squared.min(axis=(1, 2)), 0.0))


def _format_mm(value: float) -> str:
    """Миллиметры для текста: один знак, запятая, без хвостовых нулей.

    Принимает число. Возвращает строку.
    """
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
