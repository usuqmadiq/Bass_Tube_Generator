"""Горизонтальные разрезы корпуса и царги на куски области печати.

Каждый стык — «папа — мама», без зазора и без клея. Стенка делится
пополам по радиусу: папа — внутренняя половина стенки нижнего куска,
торчит вверх на длину штекера и по каналу совпадает с трубой; мама —
наружная половина стенки верхнего куска, надевается на папу. Снаружи и
внутри трубы ни утолщений, ни сужений. Нижний кусок не начинается
с узкого места при печати: папа на его верху, мама — полая юбка
полного диаметра у основания верхнего. Куски получаются одним и тем
же разбиением тела, поэтому сходятся точно. Штекер ставится только на
прямые, которые проходят сквозь разрез; высоты разрезов обходят колени,
посадку, дырки и царгу (bass_tube.layout.print_cuts).
"""

from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq

from bass_tube.constants import PRINT_PLUG_MM
from bass_tube.layout.columns import Point2
from bass_tube.layout.print_cuts import ColumnSpan, cut_heights
from bass_tube.params import TubeParams

_MARGIN_MM = 5.0
# Насколько цилиндр папы уходит ниже разреза, чтобы слиться с полупространством.
_ROOT_MM = 1.0


@dataclass(eq=False)
class PrintSlice:
    """Один печатный кусок после разреза.

    name — суффикс файла («корпус-1»). solid — тело CadQuery.
    z_min_mm и z_max_mm — диапазон по разрезам, без папы сверху.
    """

    name: str
    solid: cq.Workplane
    z_min_mm: float
    z_max_mm: float


def split_solid_for_print(
    shape: cq.Workplane,
    params: TubeParams,
    columns: tuple[Point2, ...],
    *,
    stem: str,
    bore_diameter_mm: float | None = None,
    outer_diameter_mm: float | None = None,
    spans: tuple[ColumnSpan, ...] | None = None,
    bands: tuple[tuple[float, float], ...] = (),
) -> tuple[PrintSlice, ...]:
    """Режет солид горизонтальными плоскостями на куски не выше стола.

    Принимает тело, параметры с габаритом печати, центры столбов, основу
    имени кусков, необязательные диаметры канала и наружной стенки в месте
    стыка (по умолчанию труба), необязательные отрезки прямых spans и
    запретные полосы высот bands. Со spans стык «папа — мама» ставится
    только на прямые, которые проходят сквозь разрез; без них — на все
    столбы. Разрез не встаёт в запретную полосу. Граница папы и мамы —
    середина стенки. Если высота уже не больше стола, возвращает один
    кусок. Иначе режет снизу вверх: у каждого куска, кроме верхнего,
    сверху папа, у каждого, кроме нижнего, снизу мама. Возвращает кортеж
    PrintSlice снизу вверх. Если разрез не находится, поднимает
    PrintCutError; если булева операция потеряла тело, RuntimeError.
    """
    solid = shape.val()
    box = solid.BoundingBox()
    height = box.zmax - box.zmin
    whole = (PrintSlice(name=stem, solid=shape, z_min_mm=box.zmin, z_max_mm=box.zmax),)
    if height <= params.max_height_mm + 1e-6:
        return whole
    bore = params.bore_diameter_mm if bore_diameter_mm is None else bore_diameter_mm
    outer = params.outer_diameter_mm if outer_diameter_mm is None else outer_diameter_mm
    joint_r = joint_radius_mm(bore, outer)
    cuts = cut_heights(box.zmin, box.zmax, params.max_height_mm, PRINT_PLUG_MM, bands)
    if not cuts:
        return whole
    tools = [
        _lower_side(box, cut, joint_r, _crossing(columns, spans, cut)) for cut in cuts
    ]
    bounds = [box.zmin, *cuts, box.zmax]
    slices: list[PrintSlice] = []
    for index in range(len(bounds) - 1):
        piece = solid
        if index < len(cuts):
            piece = piece.intersect(tools[index])
        if index > 0:
            piece = piece.cut(tools[index - 1])
        piece = piece.clean()
        if not piece.Solids():
            raise RuntimeError(f"Кусок {index + 1} пропал при разрезе.")
        slices.append(
            PrintSlice(
                name=f"{stem}-{index + 1}",
                solid=cq.Workplane("XY").add(piece),
                z_min_mm=bounds[index],
                z_max_mm=bounds[index + 1],
            )
        )
    return tuple(slices)


def joint_radius_mm(bore_diameter_mm: float, outer_diameter_mm: float) -> float:
    """Радиус границы папы и мамы — середина стенки.

    Принимает диаметры канала и наружной стенки. Папа от канала до этого
    радиуса, мама от него до наружной стенки. Возвращает миллиметры.
    """
    return (bore_diameter_mm + outer_diameter_mm) / 4.0


def _crossing(
    columns: tuple[Point2, ...],
    spans: tuple[ColumnSpan, ...] | None,
    cut: float,
) -> tuple[Point2, ...]:
    """Центры прямых, на которые у этого разреза нужен стык.

    Принимает все центры столбов, необязательные отрезки прямых и высоту
    разреза. Без отрезков — все столбы. Возвращает кортеж центров.
    """
    if spans is None:
        return columns
    return tuple((span.x_mm, span.y_mm) for span in spans if span.crosses(cut))


def _lower_side(
    box: cq.BoundBox,
    cut: float,
    joint_r: float,
    columns: tuple[Point2, ...],
) -> cq.Shape:
    """Область, которая при разрезе уходит нижнему куску.

    Принимает габарит тела, высоту разреза, радиус середины стенки и
    центры прямых со стыком. Это всё ниже плоскости разреза и ещё по
    цилиндру середины стенки на длину штекера вверх над каждой прямой:
    пересечение с трубой даёт папу, остаток трубы над разрезом — маму.
    Возвращает солид.
    """
    pad = _MARGIN_MM
    region: cq.Shape = _box(
        box.xmin - pad, box.xmax + pad, box.ymin - pad, box.ymax + pad, box.zmin - pad, cut
    )
    up = cq.Vector(0.0, 0.0, 1.0)
    for x, y in columns:
        male = cq.Solid.makeCylinder(
            joint_r, PRINT_PLUG_MM + _ROOT_MM, cq.Vector(x, y, cut - _ROOT_MM), up
        )
        region = region.fuse(male)
    return region.clean()


def _box(
    x0: float,
    x1: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
) -> cq.Solid:
    """Прямоугольный параллелепипед по двум углам.

    Принимает границы по x, y и z. Возвращает солид.
    """
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))
