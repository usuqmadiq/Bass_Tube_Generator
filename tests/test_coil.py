"""Укладка прямых вязанкой: ось равна корпусу, отказы называются, подстройка в дне."""

import math

import pytest

from bass_tube import LayoutError, layout_coil, resolve_tuning, tube_params
from bass_tube.acoustics.trim import resolve_trim, socket_length_mm
from bass_tube.layout.coil import MAX_STRAIGHTS


def _bundle(**overrides):
    """Габарит контрольной вязанки C2.

    Принимает подмену отдельных полей. Радиус разворота 11 мм, зазор 1 мм,
    высота 250 мм, план 150 × 150 мм, резерв модуля 35 мм.
    Возвращает словарь для tube_params.
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


def _coil(**kwargs):
    """Параметры, строй и укладка одним вызовом.

    Принимает аргументы tube_params. Возвращает (params, tuning, coil).
    """
    params = tube_params(**kwargs)
    tuning = resolve_tuning(params)
    return params, tuning, layout_coil(params, tuning)


def test_c2_bundle_is_a_hexagon_of_seven_straights():
    """C2 в ящике 250 мм: центр и шесть прямых вокруг, вход над кольцом, выход в дне."""
    params, tuning, coil = _coil(note="C2", **_bundle())
    regular = coil.regular_straight_mm
    radius = params.turn_radius_mm
    rise = radius + 19.5 / 2.0 + params.joint_length_mm
    bottom = params.floor_mm + radius + params.bore_diameter_mm / 2.0

    assert coil.layout == "bundle"
    assert coil.straight_count == 7
    assert coil.turn_count == 6
    assert coil.columns[0] == (0.0, 0.0)
    for x, y in coil.columns[1:]:
        assert math.hypot(x, y) == pytest.approx(2.0 * radius)
    body = resolve_tuning(params).body_length_mm
    assert regular == pytest.approx((body - rise - bottom - 6 * math.pi * radius) / 7.0, abs=1e-3)
    assert coil.straight_lengths_mm[0] == pytest.approx(regular + rise)
    assert coil.straight_lengths_mm[-1] == pytest.approx(regular + bottom)
    assert coil.bottom_turn_z_mm == pytest.approx(bottom)
    assert coil.base_height_mm == pytest.approx(bottom)
    assert coil.inlet_z_mm == pytest.approx(coil.top_turn_z_mm + rise)
    assert coil.outlet_at_bottom is True
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm, abs=1e-9)
    assert sum(coil.straight_lengths_mm) + 6 * math.pi * radius == pytest.approx(tuning.body_length_mm)
    assert coil.height_mm == pytest.approx(coil.inlet_z_mm)
    assert coil.height_with_head_mm == pytest.approx(coil.inlet_z_mm + 35.0)
    assert coil.height_with_head_mm <= params.max_height_mm
    assert coil.width_mm == pytest.approx(4.0 * radius + 19.5)
    assert coil.depth_mm == pytest.approx(2.0 * 2.0 * radius * math.sqrt(3.0) / 2.0 + 19.5)


def test_lower_box_packs_more_straights():
    """Чем ниже ящик, тем больше прямых подбирает автоподбор, ось всё равно равна корпусу."""
    _, tuning, tall = _coil(note="C2", **_bundle())
    _, _, low = _coil(note="C2", **_bundle(max_height_mm=150.0, max_width_mm=200.0, max_depth_mm=200.0))

    assert low.straight_count > tall.straight_count
    assert low.height_with_head_mm <= 150.0
    assert low.axis_length_mm == pytest.approx(tuning.body_length_mm)


def test_explicit_straight_count_is_respected():
    """Заданные 9 прямых не заменяются подобранными 7."""
    _, tuning, coil = _coil(note="C2", straight_count=9, **_bundle())

    assert coil.straight_count == 9
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm)


def test_auto_fit_keeps_bottoms_on_the_base_and_opens_in_the_floor():
    """Корпус 400 мм в ящике 300 мм: нечётное число прямых, выход в дне, колени на цоколе."""
    params, _, coil = _coil(body_length_mm=400.0, **_bundle(max_height_mm=300.0))

    assert coil.straight_count % 2 == 1
    assert coil.straight_count >= 3
    assert coil.outlet_at_bottom is True
    assert coil.bottom_turn_z_mm == pytest.approx(coil.base_height_mm)
    rise = params.turn_radius_mm + params.outer_diameter_mm / 2.0 + params.joint_length_mm
    assert coil.inlet_z_mm == pytest.approx(coil.top_turn_z_mm + rise)
    assert coil.straight_lengths_mm[-1] == pytest.approx(coil.regular_straight_mm + coil.base_height_mm)


def test_even_straight_count_is_rejected_without_trim():
    """Чётное число прямых отвергается и без подстройки: выход был бы сверху."""
    from bass_tube.params import ParamsError

    with pytest.raises(ParamsError, match="нечётное"):
        tube_params(note="C2", straight_count=8, **_bundle())


def test_single_straight_stands_on_the_table_without_a_base():
    """Короткий корпус — одна прямая от стола до входа, цоколя нет."""
    _, _, coil = _coil(body_length_mm=80.0, **_bundle(max_height_mm=300.0))

    assert coil.straight_count == 1
    assert coil.turn_count == 0
    assert coil.base_height_mm == 0.0
    assert coil.inlet_z_mm == pytest.approx(80.0)
    assert coil.height_with_head_mm == pytest.approx(115.0)


def test_transition_raises_the_inlet_by_the_cone():
    """Труба 30 мм: подъём входа включает посадку и переходник, стенка труб не мешает."""
    params, tuning, coil = _coil(
        note="C2",
        outer_diameter_mm=30.0,
        straight_count=7,
        **_bundle(turn_radius_mm=17.0, gap_mm=4.0, max_height_mm=300.0, max_width_mm=200.0, max_depth_mm=200.0),
    )

    assert params.has_transition is True
    assert coil.inlet_z_mm - coil.top_turn_z_mm == pytest.approx(
        params.turn_radius_mm + 15.0 + params.joint_length_mm
    )
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm)


def test_tight_gap_raises_the_turn_radius():
    """Зазор держится и через ряд шестигранника: радиус поднимается до (D_o + g)/√3."""
    params = tube_params(note="C2", **_bundle(gap_mm=2.6))
    coil = layout_coil(params, resolve_tuning(params))

    assert params.turn_radius_mm == pytest.approx((19.5 + 2.6) / 3.0**0.5)
    assert coil.straight_count >= 1
    assert params.note == "C2"


def test_low_box_reports_height_and_keeps_the_note():
    """В ящик 60 мм не влезает ни одна укладка C2: причина про высоту, нота та же."""
    params = tube_params(note="C2", **_bundle(max_height_mm=60.0))

    with pytest.raises(LayoutError, match="Мало высоты"):
        layout_coil(params, resolve_tuning(params))
    assert params.note == "C2"


def test_narrow_plan_reports_width_only():
    """Семь прямых в плане 30 мм: причина про ширину, высота не упоминается."""
    params = tube_params(note="C2", straight_count=7, **_bundle(max_width_mm=30.0))

    with pytest.raises(LayoutError, match="Мало ширины") as caught:
        layout_coil(params, resolve_tuning(params))
    assert all("Мало высоты" not in reason for reason in caught.value.reasons)


def test_straight_count_above_the_ceiling_is_rejected():
    """Число прямых выше потолка генератора отвергается, а не строится часами."""
    params = tube_params(note="C2", straight_count=MAX_STRAIGHTS + 2, **_bundle())

    with pytest.raises(LayoutError, match="не больше"):
        layout_coil(params, resolve_tuning(params))


def test_trim_keeps_odd_straights_and_a_socket_in_the_last():
    """Один полутон вниз: семь прямых, выход в дне, последняя длиннее царги."""
    params, tuning, coil = _coil(note="C2", trim_semitones=1, **_bundle())
    plan = resolve_trim(params, tuning)

    assert plan is not None
    assert coil.straight_count == 7
    assert coil.outlet_at_bottom is True
    assert coil.straight_lengths_mm[-1] >= socket_length_mm(plan)
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm)


def test_trim_rejects_even_straight_count():
    """Чётное число прямых с подстройкой отвергается ещё на параметрах."""
    from bass_tube.params import ParamsError

    with pytest.raises(ParamsError, match="нечётное"):
        tube_params(note="C2", trim_semitones=1, straight_count=8, **_bundle())
