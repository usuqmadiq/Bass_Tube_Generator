"""Короткая подстройка: ход не удваивает вложенный кусок, трубка — отдельная деталь."""

from dataclasses import replace

import pytest

from bass_tube.acoustics.notes import midi_number, note_from_midi, parse_note_name, shift_midi
from bass_tube.acoustics.trim import TrimError, resolve_trim, socket_length_mm
from bass_tube.acoustics.tuning import resolve_tuning
from bass_tube.body.tuner import build_tuner_body
from bass_tube.params import tube_params


def _box(**overrides):
    """Габарит, в который укладка здесь не обязана влезать.

    Принимает подмену отдельных полей. Высота 320 мм, радиус 30 мм.
    Возвращает словарь для tube_params.
    """
    values = {
        "max_height_mm": 320.0,
        "max_width_mm": 400.0,
        "max_depth_mm": 40.0,
        "head_reserve_mm": 35.0,
        "turn_radius_mm": 30.0,
        "gap_mm": 2.0,
    }
    values.update(overrides)
    return values


def test_shift_midi_drops_c2_to_b1():
    """Один полутон вниз от C2 — B1."""
    midi = midi_number(parse_note_name("C2"))
    assert note_from_midi(shift_midi(midi, -1)).spelling == "B1"


def test_zero_trim_has_no_plan():
    """Без полутонов подстройки плана нет: трубку печатать не нужно."""
    params = tube_params(note="C2", **_box())
    assert resolve_trim(params, resolve_tuning(params)) is None


def test_one_semitone_extra_is_the_body_delta_once():
    """Ход равен разнице корпусов нижней и верхней ноты, вложенное не удваивается."""
    params = tube_params(note="C2", trim_semitones=1, **_box())
    upper = resolve_tuning(params)
    plan = resolve_trim(params, upper)
    assert plan is not None
    assert plan.upper_note == "C2"
    assert plan.lower_note == "B1"

    lower = resolve_tuning(replace(params, note="B1", body_length_mm=None, trim_semitones=0))
    extra = lower.body_length_mm - upper.body_length_mm
    assert plan.extra_length_mm == pytest.approx(extra)
    assert plan.tenon_length_mm == pytest.approx(plan.overlap_mm + extra)
    assert socket_length_mm(plan) == pytest.approx(plan.tenon_length_mm)
    assert extra < upper.body_length_mm
    assert plan.tenon_diameter_mm < params.bore_diameter_mm
    assert plan.bore_diameter_mm < plan.tenon_diameter_mm


def test_trim_below_the_note_range_is_rejected():
    """Сдвиг ниже C-1 отвергается, а не подменяет ноту."""
    params = tube_params(note="C-1", trim_semitones=1, **_box())
    with pytest.raises(TrimError, match="выходит за ноты"):
        resolve_trim(params, resolve_tuning(params))


def test_tuner_body_is_one_open_tube():
    """Трубка подстройки собирается одним сквозным телом, фланец снизу."""
    params = tube_params(note="C2", trim_semitones=1, **_box())
    plan = resolve_trim(params, resolve_tuning(params))
    assert plan is not None
    body = build_tuner_body(plan)
    solids = body.solid.solids().vals()
    assert len(solids) == 1
    assert solids[0].isValid()
    assert body.axis_length_mm == pytest.approx(plan.flange_mm + plan.tenon_length_mm)
    assert body.base_height_mm == pytest.approx(plan.flange_mm)
    assert body.bore_diameter_mm == pytest.approx(plan.bore_diameter_mm)
