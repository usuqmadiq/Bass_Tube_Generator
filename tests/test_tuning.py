"""Четвертьволновая длина корпуса и прогноз ноты по заданной длине."""

import pytest

from bass_tube import TuningError, resolve_tuning, tube_params
from bass_tube.acoustics import midi_number, note_from_midi, parse_note_name


def _box(**overrides):
    """Габарит, в который длинный корпус заведомо не обязан влезать.

    Принимает подмену отдельных полей. Высота 320 мм меньше корпуса C1.
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


@pytest.mark.parametrize(
    ("note", "frequency_hz", "effective_mm", "body_mm"),
    [
        ("C1", 32.70, 2622, 2617),
        ("C2", 65.41, 1311, 1306),
        ("G2", 98.00, 875, 870),
        ("C3", 130.81, 656, 651),
    ],
)
def test_quarter_wave_matches_rounded_reference(note, frequency_hz, effective_mm, body_mm):
    """C1…C3 попадают в округлённый ориентир ближе чем на 1 мм."""
    tuning = resolve_tuning(tube_params(note=note, **_box()))

    assert tuning.note == note
    assert tuning.frequency_hz == pytest.approx(frequency_hz, abs=0.005)
    assert tuning.effective_length_mm == pytest.approx(effective_mm, abs=1)
    assert tuning.body_length_mm == pytest.approx(body_mm, abs=1)
    assert tuning.body_length_mm == pytest.approx(
        tuning.effective_length_mm - tuning.delta_head_mm - tuning.delta_out_mm - tuning.delta_bends_mm
    )
    assert tuning.cents == 0
    assert tuning.head_calibrated is False
    assert tuning.head_calibration_mark == "головка не калибрована"


def test_c1_length_ignores_the_short_envelope():
    """C1 считается при высоте 320 мм и остаётся длиной около 2617 мм."""
    params = tube_params(note="C1", **_box())
    tuning = resolve_tuning(params)

    assert tuning.body_length_mm > params.max_height_mm
    assert tuning.body_length_mm == pytest.approx(2617, abs=1)


def test_head_and_bend_corrections_shorten_the_body():
    """Поправки головки и изгибов вычитаются из эффективной длины, частота та же."""
    base = resolve_tuning(tube_params(note="C2", **_box()))
    shifted = resolve_tuning(
        tube_params(note="C2", delta_head_mm=10.0, delta_bends_mm=3.0, **_box())
    )

    assert shifted.frequency_hz == pytest.approx(base.frequency_hz)
    assert shifted.effective_length_mm == pytest.approx(base.effective_length_mm)
    assert shifted.body_length_mm == pytest.approx(base.body_length_mm - 13.0)
    assert shifted.head_calibrated is False


def test_speed_of_sound_scales_the_effective_length():
    """Эффективная длина пропорциональна скорости звука."""
    base = resolve_tuning(tube_params(note="C2", **_box()))
    slower = resolve_tuning(tube_params(note="C2", speed_of_sound_m_s=340.0, **_box()))

    assert slower.effective_length_mm == pytest.approx(
        base.effective_length_mm * 340.0 / 343.0
    )


def test_length_mode_keeps_body_and_names_the_nearest_note():
    """Заданные 1000 мм сохраняются, прогноз — F2 ниже ступени, головка не калибрована."""
    tuning = resolve_tuning(tube_params(body_length_mm=1000.0, **_box()))

    assert tuning.body_length_mm == 1000.0
    assert tuning.effective_length_mm == pytest.approx(1004.65)
    assert tuning.frequency_hz == pytest.approx(85.353, abs=0.001)
    assert tuning.note == "F2"
    assert tuning.cents == pytest.approx(-39.186, abs=0.01)
    assert tuning.head_calibrated is False
    assert tuning.head_calibration_mark == "головка не калибрована"


def test_length_mode_roundtrip_of_c2_body():
    """Корпус, посчитанный для C2, в режиме длины снова даёт частоту C2."""
    target = resolve_tuning(tube_params(note="C2", **_box()))
    predicted = resolve_tuning(
        tube_params(body_length_mm=target.body_length_mm, **_box())
    )

    assert predicted.body_length_mm == target.body_length_mm
    assert predicted.frequency_hz == pytest.approx(target.frequency_hz)
    assert predicted.note == "C2"
    assert predicted.cents == pytest.approx(0, abs=0.001)
    assert predicted.head_calibrated is False


def test_note_above_the_seat_is_rejected():
    """C9 даёт корпус короче посадки 8 мм и отвергается с причиной."""
    with pytest.raises(TuningError, match="короче посадки"):
        resolve_tuning(tube_params(note="C9", **_box()))


def test_non_positive_effective_length_is_rejected():
    """Отрицательные поправки, съевшие столб, не получают частоту."""
    with pytest.raises(TuningError, match="не положительна"):
        resolve_tuning(
            tube_params(
                body_length_mm=50.0,
                delta_head_mm=-100.0,
                delta_out_mm=0.0,
                delta_bends_mm=0.0,
                **_box(),
            )
        )


def test_frequency_above_b9_is_rejected():
    """Слишком короткий столб не называет ноту вне C-1…B9."""
    with pytest.raises(TuningError, match="от C-1 до B9"):
        resolve_tuning(
            tube_params(
                body_length_mm=20.0,
                delta_head_mm=-16.0,
                delta_out_mm=0.0,
                delta_bends_mm=0.0,
                **_box(),
            )
        )


def test_transition_c2_matches_the_plane_wave_reference():
    """Труба 30 мм с конусом к концу 19,5 мм: C2 даёт корпус 1315,24 мм."""
    tuning = resolve_tuning(tube_params(note="C2", outer_diameter_mm=30.0, **_box()))

    assert tuning.frequency_hz == pytest.approx(65.406, abs=0.001)
    assert tuning.body_length_mm == pytest.approx(1315.237, abs=0.01)
    assert tuning.delta_transition_mm == pytest.approx(-12.003, abs=0.01)
    assert tuning.body_length_mm == pytest.approx(
        tuning.effective_length_mm
        - tuning.delta_head_mm
        - tuning.delta_out_mm
        - tuning.delta_bends_mm
        - tuning.delta_transition_mm
    )


def test_transition_body_roundtrips_to_the_same_note():
    """Корпус с переходником, заданный длиной, снова звучит как C2 без отклонения."""
    target = resolve_tuning(tube_params(note="C2", outer_diameter_mm=30.0, **_box()))
    predicted = resolve_tuning(
        tube_params(body_length_mm=target.body_length_mm, outer_diameter_mm=30.0, **_box())
    )

    assert predicted.note == "C2"
    assert predicted.frequency_hz == pytest.approx(target.frequency_hz, rel=1e-6)
    assert predicted.cents == pytest.approx(0, abs=0.01)


def test_straight_tube_has_no_transition_correction():
    """Без переходника поправка конуса ровно ноль и строй — чистая четверть волны."""
    tuning = resolve_tuning(tube_params(note="C2", **_box()))

    assert tuning.delta_transition_mm == 0.0


def test_midi_numbers_of_the_reference_notes():
    """C4 — 60, A4 — 69, опорные ноты трубы стоят на своих номерах."""
    assert midi_number(parse_note_name("C4")) == 60
    assert midi_number(parse_note_name("A4")) == 69
    assert midi_number(parse_note_name("C1")) == 24
    assert midi_number(parse_note_name("C2")) == 36
    assert midi_number(parse_note_name("G2")) == 43
    assert midi_number(parse_note_name("C3")) == 48
    assert midi_number(parse_note_name("C#4")) == 61
    assert midi_number(parse_note_name("Bb4")) == 70
    assert note_from_midi(70).spelling == "A#4"
    assert note_from_midi(36).spelling == "C2"
