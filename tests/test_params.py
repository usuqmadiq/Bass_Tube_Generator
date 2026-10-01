"""Проверка входного набора: валидный стык принимается, противоречия отвергаются."""

import pytest

from bass_tube import ParamsError, tube_params
from bass_tube.acoustics import parse_note_name


def _box(**overrides):
    """Общий габарит и укладка для проверок входа.

    Принимает подмену отдельных полей. Подставляет высоту 320 мм, резерв
    модуля 35 мм и радиус разворота 30 мм. Возвращает словарь для tube_params.
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


def test_c2_nominal_section_is_accepted():
    """Нота C2 с номиналом стыка даёт канал 15.5 мм и концевую поправку 4.65 мм."""
    params = tube_params(note="c2", **_box())

    assert params.note == "C2"
    assert params.body_length_mm is None
    assert params.outer_diameter_mm == pytest.approx(19.5)
    assert params.wall_thickness_mm == pytest.approx(2.0)
    assert params.bore_diameter_mm == pytest.approx(15.5)
    assert params.inner_radius_mm == pytest.approx(7.75)
    assert params.delta_out_mm == pytest.approx(4.65)
    assert params.delta_head_mm == 0.0
    assert params.delta_bends_mm == 0.0
    assert params.module_hole_mm == pytest.approx(19.63)
    assert params.joint_clearance_mm == pytest.approx(0.13)
    assert params.seat_length_mm == pytest.approx(8.0)
    assert params.layout == "bundle"
    assert params.straight_count is None
    assert params.trim_semitones == 0
    assert params.hole_count == 0
    assert params.slider_kind == ""
    assert params.slider_semitones == 0
    assert params.slider_pairs == 0
    assert params.print_splits is False
    assert params.slider_clearance_mm == pytest.approx(0.3)
    assert params.drone_note is None
    assert params.drone_trim_semitones == 0
    assert not params.has_drone
    assert params.has_transition is False
    assert params.joint_length_mm == pytest.approx(8.0)
    assert params.speed_of_sound_m_s == pytest.approx(343.0)
    assert params.a4_hz == pytest.approx(440.0)


def test_length_mode_keeps_body_length():
    """Режим длины сохраняет корпус и не подставляет ноту."""
    params = tube_params(body_length_mm=1306.0, **_box())

    assert params.note is None
    assert params.body_length_mm == pytest.approx(1306.0)


def test_explicit_end_correction_is_kept():
    """Явная поправка открытого конца не заменяется формулой 0,6a."""
    params = tube_params(note="C2", delta_out_mm=6.1, **_box())

    assert params.delta_out_mm == pytest.approx(6.1)


def test_rejects_seat_shorter_than_8_mm():
    """Посадка короче 8 мм отвергается с текстом про минимум."""
    with pytest.raises(ParamsError, match="короче минимума 8") as caught:
        tube_params(note="C2", seat_length_mm=7.0, **_box())

    assert caught.value.reasons


def test_seat_of_exactly_8_mm_is_accepted():
    """Прямой участок ровно 8 мм — допустимая посадка."""
    params = tube_params(note="C2", seat_length_mm=8.0, **_box())

    assert params.seat_length_mm == pytest.approx(8.0)


def test_rejects_zero_wall():
    """Нулевая стенка отвергается отдельной причиной."""
    with pytest.raises(ParamsError, match="Толщина стенки равна нулю") as caught:
        tube_params(note="C2", wall_thickness_mm=0.0, **_box())

    assert any("нулю" in reason for reason in caught.value.reasons)


def test_rejects_note_without_octave():
    """Нота без октавы отвергается и для латинской буквы, и для слогового имени."""
    for raw in ("C", "C#", "до", "соль"):
        with pytest.raises(ParamsError, match="без октавы"):
            tube_params(note=raw, **_box())


def test_rejects_note_and_length_together():
    """Нота и длина корпуса одновременно не смешиваются."""
    with pytest.raises(ParamsError, match="Одновременно заданы нота и длина") as caught:
        tube_params(note="C2", body_length_mm=1306.0, **_box())

    assert len(caught.value.reasons) == 1


def test_rejects_missing_goal():
    """Без ноты и без длины цель не задана."""
    with pytest.raises(ParamsError, match="Не задана цель"):
        tube_params(**_box())


def test_thick_tube_gets_a_transition_instead_of_a_refusal():
    """Труба 30 мм при конце 19,5 мм принимается: между ними конус 15°."""
    params = tube_params(note="C2", outer_diameter_mm=30.0, **_box())

    assert params.has_transition is True
    assert params.bore_diameter_mm == pytest.approx(26.0)
    assert params.seat_bore_diameter_mm == pytest.approx(15.5)
    assert params.transition_length_mm == pytest.approx(5.25 / 0.2679491924, rel=1e-6)
    assert params.joint_length_mm == pytest.approx(8.0 + params.transition_length_mm)
    assert params.delta_out_mm == pytest.approx(0.6 * 13.0)


def test_end_thicker_than_module_hole_is_fitted_with_a_transition():
    """Конец 27 мм под отверстие 19,63 мм не отказ: он ужат под модуль, к трубе идёт конус."""
    params = tube_params(note="C2", outer_diameter_mm=27.0, seat_outer_diameter_mm=27.0, **_box())
    empty = tube_params(note="C2", outer_diameter_mm=27.0, **_box())

    assert params.seat_outer_diameter_mm == pytest.approx(19.5)
    assert params.joint_clearance_mm > 0.0
    assert params.has_transition is True
    assert empty.seat_outer_diameter_mm == pytest.approx(19.5)


def test_small_turn_radius_grows_with_the_outer_diameter():
    """Труба 30 мм с радиусом 11 мм не отвергается: радиус поднимается под диаметр."""
    params = tube_params(note="C2", outer_diameter_mm=30.0, **_box(turn_radius_mm=11.0, gap_mm=1.0))

    assert params.outer_diameter_mm == pytest.approx(30.0)
    assert params.turn_radius_mm == pytest.approx(31.0 / 3.0**0.5)
    assert params.has_transition is True


def test_zero_transition_becomes_a_cone_when_diameters_differ():
    """Нулевой переходник при трубе 30 мм заменяется конусом 15°, а не отказом."""
    params = tube_params(note="C2", outer_diameter_mm=30.0, transition_length_mm=0.0, **_box())

    assert params.has_transition is True
    assert params.transition_length_mm > 0.0


def test_floor_thinner_than_wall_is_raised():
    """Дно тоньше стенки поднимается, чтобы разворот не вылез под стол."""
    params = tube_params(note="C2", floor_mm=2.0, **_box())

    assert params.floor_mm > params.wall_thickness_mm
    assert params.wall_thickness_mm == pytest.approx(2.0)


def test_wall_that_eats_the_bore_is_thinned():
    """Стенка, съевшая канал, ужимается: наружный диаметр важнее."""
    params = tube_params(note="C2", wall_thickness_mm=10.0, **_box())

    assert params.bore_diameter_mm == pytest.approx(1.0)
    assert params.seat_bore_diameter_mm == pytest.approx(1.0)


def test_rejects_unknown_layout_and_fractional_straight_count():
    """Неизвестная укладка и дробное число прямых называются вместе."""
    with pytest.raises(ParamsError) as caught:
        tube_params(note="C2", layout="spiral", straight_count=2.5, **_box())

    assert len(caught.value.reasons) == 2


def test_rejects_even_straight_count():
    """Чётное число прямых отвергается: выход должен быть в дне."""
    with pytest.raises(ParamsError, match="нечётное"):
        tube_params(note="C2", straight_count=2, **_box())


def test_rejects_flat_layout():
    """Плоский змеевик больше не режим: остаётся только вязанка."""
    with pytest.raises(ParamsError, match="не известна"):
        tube_params(note="C2", layout="flat", **_box())


def test_rejects_negative_and_fractional_trim():
    """Отрицательная и дробная подстройка отвергаются."""
    with pytest.raises(ParamsError, match="отрицательная"):
        tube_params(note="C2", trim_semitones=-1, **_box())
    with pytest.raises(ParamsError, match="целым"):
        tube_params(note="C2", trim_semitones=1.5, **_box())


def test_rejects_too_many_holes_and_unknown_scale():
    """Больше восьми отверстий и чужой лад отвергаются."""
    with pytest.raises(ParamsError, match="пальцев"):
        tube_params(note="C2", hole_count=9, **_box())
    with pytest.raises(ParamsError, match="не известен"):
        tube_params(note="C2", hole_count=3, scale="blues", **_box())


def test_reports_every_reason_at_once():
    """Короткая посадка, нулевая стенка и чужая нота называются вместе."""
    with pytest.raises(ParamsError) as caught:
        tube_params(
            note="C",
            body_length_mm=1306.0,
            wall_thickness_mm=0.0,
            seat_length_mm=3.0,
            **_box(),
        )

    text = str(caught.value)
    assert "Одновременно заданы нота и длина" in text
    assert "без октавы" in text
    assert "равна нулю" in text
    assert "короче минимума 8" in text


def test_parse_note_name_spelling():
    """Разбор ноты канонизирует регистр и принимает крайнюю октаву."""
    assert parse_note_name("f#3").spelling == "F#3"
    assert parse_note_name("bb1").spelling == "Bb1"
    assert parse_note_name("C-1").spelling == "C-1"

    with pytest.raises(ValueError, match="не разбирается"):
        parse_note_name("H2")


def test_drone_note_and_trim_are_accepted():
    """Нота дрона канонизируется, пустая — один голос, без октавы отвергается.

    Ничего не принимает. G1 даёт дрон и свою подстройку. Пустой дрон
    гасит подстройку дрона. Нота без октавы у дрона — отказ.
    Ничего не возвращает.
    """
    params = tube_params(note="C2", drone_note="g1", drone_trim_semitones=2, **_box())
    assert params.drone_note == "G1"
    assert params.drone_trim_semitones == 2
    assert params.has_drone

    silent = tube_params(note="C2", drone_note="", drone_trim_semitones=2, **_box())
    assert silent.drone_note is None
    assert silent.drone_trim_semitones == 0
    assert not silent.has_drone

    with pytest.raises(ParamsError, match="Дрон"):
        tube_params(note="C2", drone_note="G", **_box())
