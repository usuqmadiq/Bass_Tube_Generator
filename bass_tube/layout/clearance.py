"""Проверка, что каналы разных колен не сливаются.

В плотной вязанке наружные стенки соседних колен могут срастаться: так деталь
жёстче. Каналы при этом должны оставаться отдельными, между ними — не меньше
одной стенки. Ось проходит с шагом не больше миллиметра, каждая пара точек на
несоседних участках сравнивается с суммой радиусов каналов и стенкой.
"""

from __future__ import annotations

import math

import numpy as np

from bass_tube.layout.centerline import Centerline
from bass_tube.layout.coil import LayoutError
from bass_tube.params import TubeParams
from bass_tube.section import bore_radius_at

_STEP_MM = 1.0
_CHUNK = 512


def check_channel_clearance(centerline: Centerline, params: TubeParams) -> float:
    """Проверяет стенку между каналами несоседних участков оси.

    Принимает ось и параметры. Соседние участки (прямая и её разворот)
    не сравниваются: их стык гладкий по построению. Радиус канала берётся
    на своей координате s, с посадкой и переходником.
    Возвращает самую тонкую стенку между каналами в миллиметрах или
    бесконечность, если сравнивать нечего. Если она тоньше стенки трубы,
    поднимает LayoutError с числами.
    """
    points, radii, owners = _samples(centerline, params)
    thinnest = math.inf
    count = len(points)
    for start in range(0, count, _CHUNK):
        stop = min(start + _CHUNK, count)
        block = points[start:stop]
        distance = np.linalg.norm(block[:, None, :] - points[None, :, :], axis=2)
        wall = distance - radii[start:stop, None] - radii[None, :]
        far = np.abs(owners[start:stop, None] - owners[None, :]) >= 2
        if np.any(far):
            thinnest = min(thinnest, float(wall[far].min()))

    if thinnest + 1e-6 < params.wall_thickness_mm:
        raise LayoutError(
            [
                "Каналы соседних колен сходятся: между ними "
                f"{_format_mm(max(thinnest, 0.0))} мм материала при стенке "
                f"{_format_mm(params.wall_thickness_mm)} мм. "
                "Увеличьте радиус разворота или зазор."
            ]
        )
    return thinnest


def _samples(centerline: Centerline, params: TubeParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Точки оси, радиусы каналов и номера участков.

    Принимает ось и параметры. На каждом участке ставит точки с шагом
    не больше миллиметра, включая оба конца. Возвращает три массива:
    координаты N×3, радиусы N и номера участков N.
    """
    coordinates: list[tuple[float, float, float]] = []
    radii: list[float] = []
    owners: list[int] = []
    for index, primitive in enumerate(centerline.primitives):
        pieces = max(1, math.ceil(primitive.length_mm / _STEP_MM))
        for step in range(pieces + 1):
            distance = primitive.length_mm * step / pieces
            point = primitive.point(distance)
            coordinates.append((point.x, point.y, point.z))
            radii.append(bore_radius_at(params, primitive.s_start_mm + distance))
            owners.append(index)
    return (
        np.asarray(coordinates, dtype=float),
        np.asarray(radii, dtype=float),
        np.asarray(owners, dtype=int),
    )


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает запись до двух знаков после запятой
    без хвостовых нулей.
    """
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")
