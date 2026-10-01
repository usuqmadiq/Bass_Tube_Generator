"""Полое тело: одна деталь на столе, посадка под модуль, переходник, сквозной канал.

Каждый тест собирает одно тело CadQuery (около секунды и 350 МБ памяти),
поэтому сборок здесь всего две.
"""

from pathlib import Path

import cadquery as cq
import pytest

from bass_tube.body import export_tube_body, load_tube_step
from bass_tube.design import build_design
from bass_tube.params import tube_params


def _bundle(**overrides):
    """Габарит контрольной вязанки C2: R = 11 мм, зазор 1 мм, ящик 250 × 150 × 150 мм.

    Принимает подмену отдельных полей. Возвращает словарь для tube_params.
    """
    values = {
        "layout": "bundle",
        "max_height_mm": 250.0,
        "max_width_mm": 150.0,
        "max_depth_mm": 150.0,
        "head_reserve_mm": 35.0,
        "turn_radius_mm": 11.0,
        "gap_mm": 1.0,
    }
    values.update(overrides)
    return values


def _wall_radii(shape, point, low_mm: float, high_mm: float) -> tuple[float, float]:
    """Внутренний и наружный радиусы стенки вертикальной трубы в точке оси.

    Принимает солид, точку оси и окно поиска по радиусу, в котором лежит
    только своя стенка. Идёт по +x и −x, находит вход в материал и выход
    из него бисекцией, усредняет. Возвращает пару радиусов в миллиметрах.
    """
    inners, outers = [], []
    for sign in (1.0, -1.0):
        def inside(radius: float) -> bool:
            """Точка на радиусе в стенке? Принимает радиус, возвращает bool."""
            return shape.isInside(cq.Vector(point.x + sign * radius, point.y, point.z))

        middle = _first_inside(inside, 0.0, high_mm)
        inners.append(_edge(inside, 0.0, middle, entering=True))
        outers.append(_edge(inside, middle, high_mm, entering=False))
    return sum(inners) / 2.0, sum(outers) / 2.0


def _first_inside(inside, low_mm: float, high_mm: float) -> float:
    """Радиус внутри стенки для старта бисекции.

    Принимает проверку и окно поиска. Шагает по 0,1 мм. Возвращает радиус
    в материале либо поднимает AssertionError, если стенки нет.
    """
    radius = low_mm
    while radius <= high_mm:
        if inside(radius):
            return radius
        radius += 0.1
    raise AssertionError("Стенка не найдена в окне поиска.")


def _edge(inside, low_mm: float, high_mm: float, entering: bool) -> float:
    """Граница материала бисекцией.

    Принимает проверку, окно и направление: entering=True — вход в стенку
    (снаружи low, внутри high), False — выход из неё. Возвращает радиус.
    """
    for _ in range(30):
        mid = (low_mm + high_mm) / 2.0
        if inside(mid) == entering:
            high_mm = mid
        else:
            low_mm = mid
    return (low_mm + high_mm) / 2.0


def test_c2_bundle_is_one_printable_part(tmp_path: Path):
    """Вязанка C2: одно тело на столе, посадка 19,5/15,5, дно под разворотом, выход открыт."""
    design = build_design(tube_params(note="C2", **_bundle()))
    coil, line = design.coil, design.centerline

    step_path = tmp_path / "c2.step"
    stl_path = tmp_path / "c2.stl"
    export_tube_body(design.body, step_path, stl_path)
    solids = load_tube_step(step_path).solids().vals()
    assert len(solids) == 1
    shape = solids[0]
    assert shape.isValid()
    assert stl_path.stat().st_size > 1000

    box = shape.BoundingBox()
    assert box.zmin == pytest.approx(0.0, abs=1e-3)
    assert box.zmax == pytest.approx(coil.inlet_z_mm, abs=1e-3)
    assert box.xlen == pytest.approx(coil.width_mm + 0.1, abs=0.05)

    for station in (1.0, 4.0, 7.0):
        inner, outer = _wall_radii(shape, line.sample(station).point, 0.0, 10.5)
        assert inner * 2.0 == pytest.approx(15.5, abs=0.02)
        assert outer * 2.0 == pytest.approx(19.5, abs=0.02)

    first_bottom = line.primitives[1]
    lowest = line.sample(first_bottom.s_start_mm + first_bottom.length_mm / 2.0).point
    assert shape.isInside(cq.Vector(lowest.x, lowest.y, lowest.z)) is False
    assert shape.isInside(cq.Vector(lowest.x, lowest.y, design.params.floor_mm / 2.0)) is True

    outlet = line.sample(line.length_mm - 1.0).point
    assert shape.isInside(cq.Vector(outlet.x, outlet.y, outlet.z)) is False


def test_thick_tube_narrows_to_the_module_seat():
    """Труба 30 мм: у модуля посадка 19,5/15,5, после конуса канал 26 мм, тело одно."""
    params = tube_params(
        note="C2",
        outer_diameter_mm=30.0,
        straight_count=7,
        **_bundle(turn_radius_mm=17.0, gap_mm=4.0, max_height_mm=300.0, max_width_mm=200.0, max_depth_mm=200.0),
    )
    design = build_design(params)
    shape = design.body.solid.val()
    line = design.centerline

    assert len(design.body.solid.solids().vals()) == 1
    assert shape.isValid()
    inner, outer = _wall_radii(shape, line.sample(4.0).point, 0.0, 12.0)
    assert inner * 2.0 == pytest.approx(15.5, abs=0.02)
    assert outer * 2.0 == pytest.approx(19.5, abs=0.02)

    middle = line.primitives[6]
    point = line.sample(middle.s_start_mm + middle.length_mm / 2.0).point
    inner, outer = _wall_radii(shape, point, 0.0, 17.0)
    assert inner * 2.0 == pytest.approx(26.0, abs=0.02)
    assert outer * 2.0 == pytest.approx(30.0, abs=0.02)
