"""Слайдер: три схемы, стопы полутонов неравномерны, печать сложенного корпуса."""

from dataclasses import replace

import pytest

from bass_tube.acoustics.slider import (
    bind_slider_columns,
    printed_slider_bbox_mm,
    printed_slider_fits_envelope,
    resolve_slider,
    slider_q,
    socket_length_mm,
)
from bass_tube.acoustics.tuning import resolve_tuning
from bass_tube.body.slider import build_slider_body
from bass_tube.constants import SLIDER_END, SLIDER_U, SLIDER_UU
from bass_tube.layout.coil import LayoutError, layout_coil
from bass_tube.params import ParamsError, tube_params


def _box(**overrides):
    """Габарит, в который укладка здесь не обязана влезать.

    Принимает подмену отдельных полей.     Высота 400 мм, радиус 11 мм: слайдеру нужен запас на царгу и
    печатную деталь. Высота на полном ходу в область печати не входит.
    Возвращает словарь для tube_params.
    """
    values = {
        "max_height_mm": 400.0,
        "max_width_mm": 150.0,
        "max_depth_mm": 150.0,
        "head_reserve_mm": 35.0,
        "turn_radius_mm": 11.0,
        "gap_mm": 1.0,
        "trim_semitones": 0,
    }
    values.update(overrides)
    return values


def test_slider_and_holes_are_rejected_together():
    """Слайдер и отверстия в одном наборе отвергаются."""
    with pytest.raises(ParamsError, match="Слайдер и отверстия"):
        tube_params(
            note="C3",
            hole_count=3,
            slider_kind=SLIDER_END,
            slider_semitones=2,
            **_box(),
        )


def test_slider_turns_trim_off():
    """Слайдер сам гасит трубку подстройки: её отдельно выключать не нужно."""
    params = tube_params(
        note="C3",
        slider_kind=SLIDER_U,
        slider_semitones=2,
        **_box(trim_semitones=1),
    )
    assert params.slider_kind == SLIDER_U
    assert params.slider_semitones == 2
    assert params.trim_semitones == 0
    assert params.slider_clearance_mm == pytest.approx(0.3)


def test_slider_without_kind_is_rejected():
    """Ход без схемы слайдера отвергается."""
    with pytest.raises(ParamsError, match="не выбрана схема"):
        tube_params(note="C3", slider_semitones=2, **_box())


def test_unknown_slider_kind_is_rejected():
    """Чужая схема слайдера отвергается."""
    with pytest.raises(ParamsError, match="не известна"):
        tube_params(note="C3", slider_kind="piston", slider_semitones=2, **_box())


def test_end_slider_q_is_one_and_u_is_two():
    """Выдвижной конец даёт ΔL ≈ x, U-колено — ΔL ≈ 2x, двойное U — ΔL ≈ 4x."""
    assert slider_q(SLIDER_END) == 1
    assert slider_q(SLIDER_U) == 2
    assert slider_q(SLIDER_UU) == 4


def test_slider_stops_are_not_uniform():
    """Каждый следующий полутон требует большего хода, чем предыдущий."""
    params = tube_params(note="C3", slider_kind=SLIDER_U, slider_semitones=4, **_box())
    plan = resolve_slider(params, resolve_tuning(params))
    assert plan is not None
    assert plan.q == 2
    assert plan.upper_note == "C3"
    steps = [stop.travel_mm for stop in plan.stops]
    assert steps[0] == pytest.approx(0.0)
    deltas = [steps[i] - steps[i - 1] for i in range(1, len(steps))]
    for previous, nxt in zip(deltas, deltas[1:]):
        assert nxt > previous
    assert plan.travel_mm == pytest.approx(plan.extra_length_mm / 2.0)
    assert plan.tenon_length_mm == pytest.approx(plan.overlap_mm + plan.travel_mm)
    assert socket_length_mm(plan) == pytest.approx(plan.tenon_length_mm)
    assert plan.radial_clearance_mm == pytest.approx(0.3)
    assert plan.tenon_diameter_mm == pytest.approx(
        params.bore_diameter_mm - 2.0 * plan.radial_clearance_mm
    )


def test_u_slider_octave_travel_matches_half_the_body_delta():
    """Октава C3→C2 у U-колена даёт ход около половины прироста корпуса."""
    params = tube_params(note="C3", slider_kind=SLIDER_U, slider_semitones=12, **_box())
    upper = resolve_tuning(params)
    plan = resolve_slider(params, upper)
    assert plan is not None
    lower = resolve_tuning(replace(params, note="C2", slider_semitones=0, slider_kind=""))
    extra = lower.body_length_mm - upper.body_length_mm
    assert plan.extra_length_mm == pytest.approx(extra)
    assert plan.travel_mm == pytest.approx(extra / 2.0)
    assert plan.travel_mm == pytest.approx(327.8, rel=0.05)


def test_end_slider_travel_is_the_full_body_delta():
    """Выдвижной конец: ход равен приросту корпуса, без удвоения вложенного."""
    params = tube_params(note="C3", slider_kind=SLIDER_END, slider_semitones=2, **_box())
    upper = resolve_tuning(params)
    plan = resolve_slider(params, upper)
    assert plan is not None
    assert plan.q == 1
    assert plan.travel_mm == pytest.approx(plan.extra_length_mm)


def test_zero_slider_has_no_plan():
    """Без полутонов слайдера плана нет."""
    params = tube_params(note="C3", **_box())
    assert resolve_slider(params, resolve_tuning(params)) is None


def test_slider_clearance_is_radial_and_at_least_0_3():
    """Зазор слайдера — со всех сторон, не меньше 0,3 мм; царга уже на 2×зазор."""
    with pytest.raises(ParamsError, match="со всех сторон"):
        tube_params(
            note="C3",
            slider_kind=SLIDER_U,
            slider_semitones=2,
            slider_clearance_mm=0.2,
            **_box(),
        )
    params = tube_params(
        note="C3",
        slider_kind=SLIDER_U,
        slider_semitones=2,
        slider_clearance_mm=0.5,
        **_box(),
    )
    plan = resolve_slider(params, resolve_tuning(params))
    assert plan is not None
    assert plan.radial_clearance_mm == pytest.approx(0.5)
    assert plan.tenon_diameter_mm == pytest.approx(params.bore_diameter_mm - 1.0)


def test_layout_does_not_quietly_shorten_an_octave_u_slider():
    """Октавный U-слайдер в 250 мм отвергается: деталь не влезает на стол."""
    params = tube_params(
        note="C3",
        slider_kind=SLIDER_U,
        slider_semitones=12,
        **_box(max_height_mm=250.0),
    )
    with pytest.raises(LayoutError, match="не укорачивается") as caught:
        layout_coil(params, resolve_tuning(params))
    text = str(caught.value)
    assert "Деталь слайдера" in text
    assert "полном ходу" not in text


def test_u_slider_fits_default_c2_print_envelope():
    """Два полутона U-колена на C2 в 250 мм укладываются: печать сложенного корпуса."""
    params = tube_params(
        note="C2",
        slider_kind=SLIDER_U,
        slider_semitones=2,
        max_height_mm=250.0,
        max_width_mm=150.0,
        max_depth_mm=150.0,
        head_reserve_mm=35.0,
        turn_radius_mm=11.0,
        gap_mm=1.0,
        trim_semitones=0,
    )
    tuning = resolve_tuning(params)
    coil = layout_coil(params, tuning)
    plan = resolve_slider(params, tuning)
    assert plan is not None
    assert coil.straight_count >= 3
    assert coil.straight_count % 2 == 1
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm)
    assert coil.height_with_head_mm <= params.max_height_mm + 1e-6
    assert printed_slider_fits_envelope(
        plan,
        params.turn_radius_mm,
        params.max_height_mm,
        params.max_width_mm,
        params.max_depth_mm,
    )
    height, _width, _depth = printed_slider_bbox_mm(plan, params.turn_radius_mm)
    assert height == pytest.approx(plan.flange_mm + plan.tenon_length_mm)
    first = coil.straight_count - 3
    assert coil.straight_lengths_mm[first] >= socket_length_mm(plan)
    assert coil.straight_lengths_mm[first + 1] >= socket_length_mm(plan)


def test_u_slider_fits_a_tall_envelope():
    """Два полутона U-колена в 400 мм укладываются, ось равна корпусу."""
    params = tube_params(note="C3", slider_kind=SLIDER_U, slider_semitones=2, **_box())
    tuning = resolve_tuning(params)
    coil = layout_coil(params, tuning)
    plan = resolve_slider(params, tuning)
    assert plan is not None
    assert coil.straight_count >= 3
    assert coil.straight_count % 2 == 1
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm)
    assert coil.height_with_head_mm <= params.max_height_mm + 1e-6
    first = coil.straight_count - 3
    assert coil.straight_lengths_mm[first] >= socket_length_mm(plan)
    assert coil.straight_lengths_mm[first + 1] >= socket_length_mm(plan)


def test_slider_body_is_one_open_solid():
    """Деталь U-колена собирается одним телом, фланец снизу."""
    params = tube_params(note="C3", slider_kind=SLIDER_U, slider_semitones=2, **_box())
    plan = resolve_slider(params, resolve_tuning(params))
    assert plan is not None
    body = build_slider_body(plan, params.turn_radius_mm)
    solids = body.solid.solids().vals()
    assert len(solids) == 1
    assert solids[0].isValid()
    assert body.base_height_mm == pytest.approx(plan.flange_mm)
    assert body.base_height_mm == pytest.approx(
        params.floor_mm + params.turn_radius_mm + params.bore_diameter_mm / 2.0
    )
    assert body.bore_diameter_mm == pytest.approx(plan.bore_diameter_mm)


def test_design_with_u_slider_builds_two_parts():
    """Корпус C3 с U-коленом на два полутона и отдельная деталь слайдера."""
    from bass_tube.design import build_design

    params = tube_params(note="C3", slider_kind=SLIDER_U, slider_semitones=2, **_box())
    design = build_design(params)
    assert design.slider is not None
    assert design.slider_body is not None
    assert design.holes is None
    assert design.trim is None
    assert design.tuner is None
    assert design.coil.axis_length_mm == pytest.approx(design.tuning.body_length_mm)
    solids = design.body.solid.solids().vals()
    assert len(solids) == 1
    assert solids[0].isValid()


def test_double_u_q_is_four_and_needs_five_straights():
    """Двойное U даёт ΔL ≈ 4x и не садится в три прямые."""
    params = tube_params(note="C3", slider_kind=SLIDER_UU, slider_semitones=2, **_box())
    plan = resolve_slider(params, resolve_tuning(params))
    assert plan is not None
    assert plan.q == 4
    assert plan.travel_mm == pytest.approx(plan.extra_length_mm / 4.0)
    tight = tube_params(
        note="C3",
        slider_kind=SLIDER_UU,
        slider_semitones=2,
        straight_count=3,
        **_box(),
    )
    with pytest.raises(LayoutError, match="5 прямых"):
        layout_coil(tight, resolve_tuning(tight))


def test_double_u_octave_does_not_quietly_shorten():
    """Октава двойного U на C3 не укорачивается молча: царги длиннее ветвей."""
    params = tube_params(
        note="C3",
        slider_kind=SLIDER_UU,
        slider_semitones=12,
        **_box(max_height_mm=250.0),
    )
    with pytest.raises(LayoutError, match="не укорачивается") as caught:
        layout_coil(params, resolve_tuning(params))
    assert "царги" in str(caught.value)


def test_double_u_two_semitones_fit_c3_print_envelope():
    """Два полутона двойного U на C3 в 250 мм укладываются, четыре ветви до дна."""
    params = tube_params(
        note="C3",
        slider_kind=SLIDER_UU,
        slider_semitones=2,
        **_box(max_height_mm=250.0),
    )
    tuning = resolve_tuning(params)
    coil = layout_coil(params, tuning)
    plan = resolve_slider(params, tuning)
    assert plan is not None
    assert coil.straight_count >= 5
    assert coil.straight_count % 2 == 1
    assert plan.travel_mm == pytest.approx(plan.extra_length_mm / 4.0)
    assert printed_slider_fits_envelope(
        plan,
        params.turn_radius_mm,
        params.max_height_mm,
        params.max_width_mm,
        params.max_depth_mm,
        coil.columns,
    )
    bound = bind_slider_columns(plan, coil.straight_count)
    assert len(bound.legs) == 4
    for index in bound.legs:
        assert coil.straight_lengths_mm[index] >= socket_length_mm(plan)


def test_double_u_layout_has_four_floor_legs():
    """Два полутона двойного U: четыре ветви до дна, ось равна корпусу."""
    params = tube_params(note="C3", slider_kind=SLIDER_UU, slider_semitones=2, **_box())
    tuning = resolve_tuning(params)
    coil = layout_coil(params, tuning)
    plan = resolve_slider(params, tuning)
    assert plan is not None
    assert coil.straight_count >= 5
    assert coil.axis_length_mm == pytest.approx(tuning.body_length_mm)
    bound = bind_slider_columns(plan, coil.straight_count)
    assert bound.legs == (
        coil.straight_count - 5,
        coil.straight_count - 4,
        coil.straight_count - 3,
        coil.straight_count - 2,
    )
    for index in bound.legs:
        assert coil.straight_lengths_mm[index] >= socket_length_mm(plan)


def test_design_with_double_u_slider_builds_two_parts():
    """Корпус C3 с двойным U на два полутона и отдельная деталь из четырёх царг."""
    from bass_tube.design import build_design

    params = tube_params(note="C3", slider_kind=SLIDER_UU, slider_semitones=2, **_box())
    design = build_design(params)
    assert design.slider is not None
    assert design.slider.q == 4
    assert len(design.slider.legs) == 4
    assert design.slider_body is not None
    assert design.trim is None
    solids = design.body.solid.solids().vals()
    assert len(solids) == 1
    assert solids[0].isValid()
    extra = design.slider_body.solid.solids().vals()
    assert len(extra) == 1
    assert extra[0].isValid()


def test_slider_q_scales_with_u_pairs():
    """Одно U даёт q=2, три колена — q=6, авто без числа колен считает как одно."""
    from bass_tube.acoustics.slider import slider_q
    from bass_tube.constants import SLIDER_U, SLIDER_UAUTO, SLIDER_UU

    assert slider_q(SLIDER_U) == 2
    assert slider_q(SLIDER_U, 3) == 6
    assert slider_q(SLIDER_UU) == 4
    assert slider_q(SLIDER_UAUTO, 4) == 8


def test_triple_u_needs_seven_straights():
    """Три U-колена не садятся в пять прямых: нужны семь."""
    params = tube_params(
        note="C3",
        slider_kind=SLIDER_U,
        slider_pairs=3,
        slider_semitones=2,
        straight_count=5,
        **_box(),
    )
    with pytest.raises(LayoutError, match="7 прямых"):
        layout_coil(params, resolve_tuning(params))


def test_uauto_takes_all_bottom_turns_on_five_straights():
    """U авто на пяти прямых забирает два нижних колена, q=4."""
    from bass_tube.acoustics.slider import bind_slider_columns, max_u_pairs
    from bass_tube.constants import SLIDER_UAUTO

    params = tube_params(
        note="C3",
        slider_kind=SLIDER_UAUTO,
        slider_semitones=2,
        **_box(max_height_mm=250.0),
    )
    tuning = resolve_tuning(params)
    coil = layout_coil(params, tuning)
    plan = resolve_slider(params, tuning)
    assert plan is not None
    bound = bind_slider_columns(plan, coil.straight_count)
    assert bound.pairs == max_u_pairs(coil.straight_count)
    assert bound.q == 2 * bound.pairs
    assert len(bound.legs) == 2 * bound.pairs
    assert coil.straight_count % 2 == 1
    for index in bound.legs:
        assert coil.straight_lengths_mm[index] >= socket_length_mm(bound)


def test_print_splits_allow_tall_three_straights_on_c2():
    """Три прямые C2 выше стола 250 мм: без разрезов отказ, с разрезами укладка есть."""
    tight = tube_params(
        note="C2",
        straight_count=3,
        **_box(max_height_mm=250.0, max_width_mm=150.0, max_depth_mm=150.0, trim_semitones=0),
    )
    with pytest.raises(LayoutError, match="Мало высоты"):
        layout_coil(tight, resolve_tuning(tight))
    split = tube_params(
        note="C2",
        straight_count=3,
        print_splits=True,
        **_box(max_height_mm=250.0, max_width_mm=150.0, max_depth_mm=150.0, trim_semitones=0),
    )
    coil = layout_coil(split, resolve_tuning(split))
    assert coil.straight_count == 3
    assert coil.height_with_head_mm > split.max_height_mm


def test_design_with_print_splits_cuts_tall_c2_into_pieces():
    """Разрезы C2 из трёх прямых дают несколько кусков корпуса со штекерами."""
    from bass_tube.design import build_design

    params = tube_params(
        note="C2",
        straight_count=3,
        print_splits=True,
        **_box(max_height_mm=250.0, max_width_mm=150.0, max_depth_mm=150.0, trim_semitones=0),
    )
    design = build_design(params)
    assert len(design.body_slices) >= 2
    for piece in design.body_slices:
        solids = piece.solid.solids().vals()
        assert len(solids) >= 1
        assert solids[0].isValid()
        box = solids[0].BoundingBox()
        assert box.zlen <= params.max_height_mm + 1.0
