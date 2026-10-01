"""Второй голос: мелодия и дрон одной деталью, входы на 48 мм на одной высоте."""

import math
from pathlib import Path

import numpy as np
import pytest

from bass_tube.body.parts import convex_hull
from bass_tube.constants import DUAL_INLET_SPACING_MM
from bass_tube.layout.print_cuts import column_spans
from bass_tube.pair import (
    build_voice_pair,
    drone_params,
    export_pair,
    inlet_distance_mm,
    melody_params,
    plan_voice_pair,
)
from bass_tube.params import tube_params


def _bundle(**overrides):
    """Габарит вязанки окна: R = 11 мм, зазор 1 мм, ящик 250 × 150 × 150 мм.

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
        "trim_semitones": 1,
        "print_splits": True,
    }
    values.update(overrides)
    return values


def _plan_distance(first, second) -> float:
    """Наименьшее расстояние в плане между осями двух укладок.

    Принимает две укладки. Прямые — точки, колени — отрезки между
    соседними прямыми через полмиллиметра. Возвращает миллиметры.
    """

    def samples(columns):
        """Точки оси укладки в плане. Принимает центры, возвращает массив."""
        points = [np.array(columns)]
        for a, b in zip(columns[:-1], columns[1:]):
            steps = np.linspace(0.0, 1.0, 45)[1:-1]
            points.append(np.array(a) + np.outer(steps, np.subtract(b, a)))
        return np.vstack(points)

    left, right = samples(first.columns), samples(second.columns)
    diff = left[:, None, :] - right[None, :, :]
    return float(np.sqrt((diff * diff).sum(-1)).min())


def test_drone_params_drop_holes_and_slider() -> None:
    """Дрон берёт свою ноту и подстройку, дырки и слайдер мелодии не копирует.

    Ничего не принимает. Мелодия с тремя дырками даёт дрон без дырок.
    Ничего не возвращает.
    """
    params = tube_params(note="C2", drone_note="G1", drone_trim_semitones=1, hole_count=3, **_bundle())
    melody = melody_params(params)
    drone = drone_params(params)
    assert melody.note == "C2"
    assert melody.drone_note is None
    assert melody.hole_count == 3
    assert drone.note == "G1"
    assert drone.body_length_mm is None
    assert drone.hole_count == 0
    assert drone.slider_kind == ""
    assert drone.trim_semitones == 1
    assert drone.drone_note is None


def test_pair_plan_puts_inlets_48_mm_apart_on_one_height() -> None:
    """Мелодия G1 с семью дырками и дрон D2: входы на 48 мм и на одной высоте.

    Ничего не принимает. Обе трубы стоят на столе (последние прямые
    доходят до z = 0), вход дрона на краю его вязанки, оси разных труб
    не ближе наружного диаметра плюс зазор, общий план в столе.
    Ничего не возвращает.
    """
    params = tube_params(note="G1", hole_count=7, drone_note="D2", drone_trim_semitones=1, **_bundle())
    plan = plan_voice_pair(params)
    melody, drone = plan.melody.coil, plan.drone.coil
    assert inlet_distance_mm(plan) == pytest.approx(DUAL_INLET_SPACING_MM)
    assert melody.inlet_z_mm == pytest.approx(drone.inlet_z_mm)
    assert column_spans(melody)[-1].z_low_mm == pytest.approx(0.0)
    assert column_spans(drone)[-1].z_low_mm == pytest.approx(0.0)
    assert drone.columns[0] in convex_hull(drone.columns)
    assert drone.straight_count >= 3
    assert _plan_distance(melody, drone) + 1e-6 >= params.outer_diameter_mm + params.gap_mm
    assert plan.placement.width_mm <= params.max_width_mm + 1e-9
    assert plan.placement.depth_mm <= params.max_depth_mm + 1e-9
    assert plan.drone.tuning.note == "D2"
    assert plan.drone.trim is not None


def test_pair_keeps_finger_corridor_of_melody_holes_free() -> None:
    """Дрон не стоит перед дырками мелодии.

    Ничего не принимает. От стенки мелодии наружу по направлению каждой
    дырки на 25 мм до осей дрона не ближе половины трубы плюс половины
    дырки. Ничего не возвращает.
    """
    params = tube_params(note="C2", hole_count=8, drone_note="C2", drone_trim_semitones=1, **_bundle())
    plan = plan_voice_pair(params)
    melody, drone = plan.melody.coil, plan.drone.coil
    assert plan.melody.placed_holes
    reach = params.outer_diameter_mm / 2.0 + params.hole_diameter_mm / 2.0
    for hole in plan.melody.placed_holes:
        cx, cy = melody.columns[hole.column]
        for step in np.arange(params.outer_diameter_mm / 2.0, params.outer_diameter_mm / 2.0 + 25.0, 1.0):
            point = (cx + hole.outward.x * step, cy + hole.outward.y * step)
            nearest = min(math.dist(point, column) for column in drone.columns)
            assert nearest + 1e-6 >= reach


def test_low_bed_pair_lifts_melody_instead_of_failing() -> None:
    """Стол 150 мм, мелодия и дрон G1: пара собирается выше стола и режется.

    Ничего не принимает. Двухметровые трубы при низком входе не входят
    в план 150 × 150 мм; с разрезами мелодия поднимается, вход выше, обе
    вязанки уже. Ничего не возвращает.
    """
    params = tube_params(
        note="G1", hole_count=6, scale="major", drone_note="G1", drone_trim_semitones=1,
        **_bundle(max_height_mm=150.0),
    )
    plan = plan_voice_pair(params)
    assert plan.height_mm > params.max_height_mm
    assert plan.melody.coil.inlet_z_mm == pytest.approx(plan.drone.coil.inlet_z_mm)
    assert inlet_distance_mm(plan) == pytest.approx(DUAL_INLET_SPACING_MM)


def test_pair_is_one_valid_solid_and_exports(tmp_path: Path) -> None:
    """Пара C2 + G2 — одна валидная деталь на столе, файлы без отдельного дрона.

    Принимает временный каталог. Деталь — одно тело от z = 0, пишутся
    деталь и две трубки подстройки. Ничего не возвращает.
    """
    params = tube_params(note="C2", drone_note="G2", drone_trim_semitones=1, **_bundle())
    pair = build_voice_pair(params)
    solids = pair.body.solid.solids().vals()
    assert len(solids) == 1
    assert solids[0].isValid()
    assert solids[0].BoundingBox().zmin == pytest.approx(0.0, abs=1e-6)
    assert pair.coupling.channels_independent is True
    assert pair.coupling.supply_chamber is False
    assert pair.coupling.wall_clearance_mm + 1e-9 >= params.gap_mm
    saved = export_pair(pair, tmp_path / "пара.step", tmp_path / "пара.stl")
    names = {path.name for path in saved}
    assert {"пара.step", "пара.stl", "пара-подстройка.step", "пара-подстройка-дрон.step"} <= names
    assert all(path.is_file() for path in saved)


def test_pair_on_low_bed_is_cut_as_a_whole() -> None:
    """Пара G1 (7 дырок) + D2 на столе 150 мм режется целиком на куски стола.

    Ничего не принимает. Кусков больше одного, каждый не выше стола
    вместе со штекером. Ничего не возвращает.
    """
    params = tube_params(
        note="G1", hole_count=7, drone_note="D2", drone_trim_semitones=1,
        **_bundle(max_height_mm=150.0),
    )
    pair = build_voice_pair(params)
    assert len(pair.body_slices) >= 2
    for piece in pair.body_slices:
        for solid in piece.solid.solids().vals():
            assert solid.isValid()
            assert solid.BoundingBox().zlen <= params.max_height_mm + 1e-6
