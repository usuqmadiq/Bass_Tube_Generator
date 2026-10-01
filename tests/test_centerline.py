"""Ось в пространстве: сумма длин, непрерывность стыков, вход сверху, выход в дне."""

import math

import pytest

from bass_tube import CenterlineError, LayoutError, build_centerline, layout_coil, resolve_tuning, tube_params
from bass_tube.layout import Straight, Turn, check_channel_clearance


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


def _line(**kwargs):
    """Параметры, укладка и ось.

    Принимает аргументы tube_params. Возвращает (params, coil, Centerline).
    """
    params = tube_params(**kwargs)
    coil = layout_coil(params, resolve_tuning(params))
    return params, coil, build_centerline(coil, params.joint_length_mm)


def test_bundle_axis_sums_to_the_body_and_alternates_turns():
    """Семь прямых и шесть дуг дают длину корпуса, развороты по очереди внизу и вверху."""
    params, coil, line = _line(note="C2", **_bundle())
    kinds = [type(item) for item in line.primitives]

    assert kinds == [Straight, Turn] * 6 + [Straight]
    assert sum(item.length_mm for item in line.primitives) == pytest.approx(coil.axis_length_mm, abs=1e-9)
    assert line.length_mm == pytest.approx(resolve_tuning(params).body_length_mm, abs=1e-6)
    for index, turn in enumerate(line.primitives[1::2]):
        middle = line.sample(turn.s_start_mm + turn.length_mm / 2.0).point
        if index % 2 == 0:
            assert middle.z == pytest.approx(coil.bottom_turn_z_mm - params.turn_radius_mm)
        else:
            assert middle.z == pytest.approx(coil.top_turn_z_mm + params.turn_radius_mm)


def test_joints_keep_position_and_tangent():
    """На каждом стыке прямой и дуги точка и касательная не прыгают."""
    _, _, line = _line(note="C2", **_bundle())

    for left, right in zip(line.primitives, line.primitives[1:]):
        end = left.point(left.length_mm)
        start = right.point(0.0)
        assert math.dist((end.x, end.y, end.z), (start.x, start.y, start.z)) == pytest.approx(0.0, abs=1e-9)
        assert left.tangent(left.length_mm).dot(right.tangent(0.0)) == pytest.approx(1.0, abs=1e-9)


def test_inlet_is_on_top_of_the_centre_and_outlet_opens_in_the_table():
    """s = 0 над центральной прямой смотрит вниз, стык с переходником на первой прямой, выход на z = 0."""
    params, coil, line = _line(note="C2", **_bundle())
    inlet = line.sample(0.0)
    outlet = line.sample(line.length_mm)

    assert (inlet.point.x, inlet.point.y) == pytest.approx((0.0, 0.0))
    assert inlet.point.z == pytest.approx(coil.inlet_z_mm)
    assert inlet.tangent.z == pytest.approx(-1.0)
    assert line.primitive_at(params.joint_length_mm) is line.primitives[0]
    assert (outlet.point.x, outlet.point.y) == pytest.approx(coil.columns[-1])
    assert outlet.point.z == pytest.approx(0.0, abs=1e-9)
    assert outlet.tangent.z == pytest.approx(-1.0)


def test_bundle_channels_keep_a_wall_between_neighbours():
    """Вязанка C2: самая тонкая стенка — от колена до общего соседа, √3·R минус канал."""
    params, _, line = _line(note="C2", **_bundle())

    wall = check_channel_clearance(line, params)
    assert wall == pytest.approx(3.0**0.5 * params.turn_radius_mm - params.bore_diameter_mm, abs=0.01)
    assert wall >= params.wall_thickness_mm


def test_fat_channel_on_a_tight_axis_is_rejected():
    """Канал 19,5 мм на оси, уложенной под трубу 19,5 мм: каналы соседей сходятся, отказ."""
    _, _, line = _line(note="C2", **_bundle())
    fat = tube_params(note="C2", outer_diameter_mm=23.5, **_bundle())

    with pytest.raises(LayoutError, match="сходятся"):
        check_channel_clearance(line, fat)


def test_coordinate_outside_the_axis_is_rejected():
    """Координата до входа и за выходом не получают точку."""
    _, _, line = _line(note="C2", **_bundle())

    with pytest.raises(CenterlineError, match="вне оси"):
        line.sample(-1.0)
    with pytest.raises(CenterlineError, match="вне оси"):
        line.sample(line.length_mm + 1.0)
