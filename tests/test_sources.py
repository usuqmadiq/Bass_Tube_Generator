"""Модули-источники на входах: вид в окне и файлы рядом с трубой."""

import math

import numpy as np
import pytest

from bass_tube import tube_params
from bass_tube.design import build_design
from bass_tube.pair import build_voice_pair, export_pair
from bass_tube.sources import (
    MEMBRANE_EAR_DIRECTION,
    MEMBRANE_MODULE_STL,
    MEMBRANE_RING_STL,
    MEMBRANE_STOP_Z_MM,
    design_sources,
    membrane_module_shape,
    pair_sources,
)
from bass_tube.ui.app import _export_design, instrument_sources
from bass_tube.ui.preview import PreviewScene
from bass_tube.ui.theme import PREVIEW_SOURCE


def _box(**overrides):
    values = dict(
        max_height_mm=250.0,
        max_width_mm=150.0,
        max_depth_mm=150.0,
        head_reserve_mm=35.0,
        turn_radius_mm=11.0,
        gap_mm=1.0,
    )
    values.update(overrides)
    return values


def test_membrane_module_sits_on_the_tube_end():
    """Модуль из head.stl: гнездо соосно входу, упор трубы на торце."""
    module = membrane_module_shape()
    assert module is not None
    bb = module.BoundingBox()
    assert bb.zmin == pytest.approx(-MEMBRANE_STOP_Z_MM, abs=1e-3)

    design = build_design(tube_params(note="C3", **_box()))
    (placed,) = design_sources(design)
    inlet = design.centerline.sample(0.0).point
    box = placed.BoundingBox()
    assert box.zmin == pytest.approx(inlet.z - MEMBRANE_STOP_Z_MM, abs=1e-3)
    # Гнездо Ø20,04 соосно входу: вершины стенки гнезда (без входной фаски)
    # лежат на одной окружности вокруг оси трубы.
    vertices = np.array([v.toTuple() for v in placed.Vertices()])
    low = vertices[vertices[:, 2] < inlet.z - 1.0]
    radii = np.hypot(low[:, 0] - inlet.x, low[:, 1] - inlet.y)
    socket = low[np.abs(radii - 10.02) < 0.05]
    assert len(socket) > 50
    assert abs(socket[:, 0].mean() - inlet.x) < 0.05
    assert abs(socket[:, 1].mean() - inlet.y) < 0.05


def test_whistle_design_shows_its_head():
    """У свистка источник — его головка на входе, а не мембрана."""
    design = build_design(
        tube_params(note="C3", source="whistle", termination="stopped",
                    whistle_head_kind="axial", **_box())
    )
    sources = design_sources(design)

    assert len(sources) == 1
    inlet = design.centerline.sample(0.0).point
    bb = sources[0].BoundingBox()
    socket = design.whistle_head.params.socket_depth_mm
    assert bb.zmin == pytest.approx(inlet.z - socket, abs=1e-6)


def test_pair_membrane_ears_point_away_from_partner():
    """В паре мембранный модуль развёрнут ушами от соседнего входа."""
    pair = build_voice_pair(
        tube_params(note="C2", drone_note="G1", drone_source="whistle",
                    drone_termination="stopped", whistle_head_kind="axial", **_box())
    )
    sources = pair_sources(pair)
    assert len(sources) == 2

    melody_inlet = pair.melody.centerline.sample(0.0).point
    drone_inlet = pair.drone.centerline.sample(0.0).point
    away = np.array([melody_inlet.x - drone_inlet.x, melody_inlet.y - drone_inlet.y])
    module = sources[0]
    vertices = np.array([v.toTuple() for v in module.Vertices()])
    radii = np.hypot(vertices[:, 0] - melody_inlet.x, vertices[:, 1] - melody_inlet.y)
    ears = vertices[radii > 21.0][:, :2] - [melody_inlet.x, melody_inlet.y]
    direction = ears.mean(axis=0)
    cosine = direction @ away / (np.linalg.norm(direction) * np.linalg.norm(away))
    assert cosine > 0.99
    assert math.hypot(*MEMBRANE_EAR_DIRECTION) == pytest.approx(1.0, abs=1e-3)


def test_preview_paints_sources_in_their_colour():
    """Кадр окна содержит пиксели цвета источников."""
    design = build_design(tube_params(note="C3", **_box()))
    scene = PreviewScene()
    scene.show_shape(design.body.solid.val(), instrument_sources(design))
    image = np.asarray(scene.image(320, 260)).astype(float) / 255.0

    bluish = (image[:, :, 2] > image[:, :, 0] + 0.08).sum()
    assert bluish > 200, "источник не виден в кадре"
    assert PREVIEW_SOURCE[2] > PREVIEW_SOURCE[0]


def test_membrane_tube_saves_module_and_ring(tmp_path):
    """Мембранная труба сохраняется вместе с модулем и кольцом из parts/."""
    design = build_design(tube_params(note="C3", **_box()))
    saved = _export_design(design, tmp_path / "т.step", tmp_path / "т.stl")
    names = {path.name for path in saved}

    assert {"т-мембрана.stl", "т-мембрана-кольцо.stl"} <= names
    assert (tmp_path / "т-мембрана.stl").read_bytes() == MEMBRANE_MODULE_STL.read_bytes()
    assert (tmp_path / "т-мембрана-кольцо.stl").read_bytes() == MEMBRANE_RING_STL.read_bytes()


def test_whistle_tube_saves_no_membrane(tmp_path):
    """У свистка мембранных файлов нет, только головка."""
    design = build_design(
        tube_params(body_length_mm=300.0, straight_count=1, source="whistle",
                    termination="stopped", **_box(max_height_mm=400.0))
    )
    names = {p.name for p in _export_design(design, tmp_path / "т.step", tmp_path / "т.stl")}

    assert not any("мембрана" in name for name in names)
    assert {"т-свисток.stl", "т-свисток-крышка.stl"} <= names


def test_pair_saves_both_sources(tmp_path):
    """Пара «мембрана + свисток»: модуль мелодии и головка дрона рядом с деталью."""
    pair = build_voice_pair(
        tube_params(note="C2", drone_note="G1", drone_source="whistle",
                    drone_termination="stopped", whistle_head_kind="axial", **_box())
    )
    names = {p.name for p in export_pair(pair, tmp_path / "п.step", tmp_path / "п.stl")}

    assert {"п-мембрана.stl", "п-мембрана-кольцо.stl", "п-свисток-дрон.stl"} <= names
    assert not any("мембрана-дрон" in name for name in names)
