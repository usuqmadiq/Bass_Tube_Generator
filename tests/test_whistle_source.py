"""Свистковый источник в ядре: граничные условия, отказы и печатная заглушка.

Числа сверяются с отдельным прототипом bass_tube.whistle: ядро обязано
давать те же пассивные резонансы, что и его проверенный расчёт.
"""

import pytest

from bass_tube import ParamsError, resolve_tuning, tube_params
from bass_tube.design import build_design
from bass_tube.whistle.params import WhistleHeadParams
from bass_tube.whistle.planning import plan_uniform_whistle


def _box(**overrides):
    """Габарит, в который длинный корпус заведомо не обязан влезать.

    Принимает подмену отдельных полей. Возвращает словарь для tube_params.
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


# Геометрия прототипа (WhistleHeadParams по умолчанию): сверка строя ядра
# с прототипом идёт на одной и той же головке, а не на подборе по давлению.
PROTOTYPE_FLUE = dict(
    whistle_windway_height_mm=0.6,
    whistle_windway_width_mm=8.0,
    whistle_cutup_mm=8.0,
)


def _whistle(**overrides):
    """Параметры свистковой трубы с головкой прототипа и габаритом по умолчанию.

    Принимает подмену полей tube_params. Возвращает TubeParams.
    """
    values = dict(source="whistle", **PROTOTYPE_FLUE, **_box())
    values.update(overrides)
    return tube_params(**values)


@pytest.mark.parametrize(
    ("termination", "note", "frequency_hz"),
    [("stopped", "C2", 65.05), ("open", "C3", 129.64)],
)
def test_existing_c2_body_matches_prototype(termination, note, frequency_hz):
    """Корпус C2 1306 мм со свистком считается как в прототипе.

    Заглушённый конец остаётся басовым (≈65 Гц), открытый поднимается
    примерно на октаву (≈129,6 Гц) — ориентиры исследования.
    """
    tuning = resolve_tuning(_whistle(body_length_mm=1306.0, termination=termination))
    report = plan_uniform_whistle(1306.0, WhistleHeadParams(), termination=termination)

    assert tuning.frequency_hz == pytest.approx(report["passive_frequency_hz"], rel=1e-9)
    assert tuning.frequency_hz == pytest.approx(frequency_hz, abs=0.01)
    assert tuning.note == note
    assert tuning.source == "whistle"
    assert tuning.termination == termination
    assert tuning.whistle_neck_mm == pytest.approx(report["neck_reference_length_mm"])
    assert tuning.delta_head_mm == 0.0
    assert tuning.delta_bends_mm == 0.0
    assert tuning.head_calibrated is False


def test_mouth_correction_scenario_matches_prototype():
    """Поправка окна 30 мм сдвигает пассивную частоту как в прототипе."""
    tuning = resolve_tuning(
        _whistle(body_length_mm=1306.0, termination="stopped", mouth_correction_mm=30.0)
    )
    report = plan_uniform_whistle(
        1306.0, WhistleHeadParams(), termination="stopped", mouth_correction_mm=30.0
    )

    assert tuning.mouth_correction_mm == 30.0
    assert tuning.frequency_hz == pytest.approx(report["passive_frequency_hz"], rel=1e-9)
    assert tuning.frequency_hz == pytest.approx(63.6, abs=0.05)


@pytest.mark.parametrize("termination", ["open", "stopped"])
@pytest.mark.parametrize("outer_mm", [19.5, 30.0])
def test_note_to_length_round_trip(termination, outer_mm):
    """Нота → длина → частота сходится и у ровной трубы, и с переходником."""
    goal = resolve_tuning(
        _whistle(note="C2", termination=termination, outer_diameter_mm=outer_mm)
    )
    back = resolve_tuning(
        _whistle(
            body_length_mm=goal.body_length_mm,
            termination=termination,
            outer_diameter_mm=outer_mm,
        )
    )

    assert goal.cents == 0.0
    assert back.note == "C2"
    assert back.frequency_hz == pytest.approx(goal.frequency_hz, rel=1e-6)
    assert abs(back.cents) < 0.01


def test_stopped_keeps_bass_shorter_than_open():
    """Заглушённый конец даёт ту же ноту примерно вдвое короче открытого."""
    stopped = resolve_tuning(_whistle(note="C2", termination="stopped"))
    opened = resolve_tuning(_whistle(note="C2", termination="open"))

    assert stopped.delta_out_mm == 0.0
    assert opened.delta_out_mm == pytest.approx(4.65)
    assert opened.body_length_mm / stopped.body_length_mm == pytest.approx(2.0, abs=0.05)


def test_membrane_defaults_did_not_move():
    """Старый мембранный расчёт не сдвинулся: C2 остаётся около 1306 мм."""
    tuning = resolve_tuning(tube_params(note="C2", **_box()))

    assert tuning.source == "membrane"
    assert tuning.termination == "open"
    assert tuning.mouth_correction_mm == 0.0
    assert tuning.whistle_neck_mm == 0.0
    assert tuning.body_length_mm == pytest.approx(1306, abs=1)


def test_russian_labels_resolve():
    """Русские подписи источника и конца понимаются."""
    params = tube_params(note="C2", source="свисток", termination="заглушён", **_box())

    assert params.source == "whistle"
    assert params.termination == "stopped"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        (dict(source="whistle", hole_count=3), "отверстиями"),
        (dict(source="whistle", slider_kind="u", slider_semitones=1), "слайдером"),
        (dict(source="whistle", termination="stopped", trim_semitones=1), "глухим"),
        (dict(termination="stopped"), "только у свистка"),
        (dict(mouth_correction_mm=10.0), "у мембраны её нет"),
        (dict(source="балалайка"), "не известен"),
        (dict(source="whistle", termination="полуоткрыт"), "не известен"),
        (dict(source="whistle", mouth_correction_mm=-1.0), "отрицательная"),
    ],
)
def test_rejected_combinations(overrides, fragment):
    """Невалидные сочетания источника отвергаются с понятной причиной."""
    with pytest.raises(ParamsError) as error:
        tube_params(note="C2", **overrides, **_box())

    assert fragment in str(error.value)


def test_whistle_with_drone_is_accepted():
    """С шага 5 свисток играет в паре с дроном: набор принимается."""
    params = tube_params(note="C2", source="whistle", drone_note="G1", **_box())

    assert params.source == "whistle"
    assert params.drone_note == "G1"
    assert params.drone_source == "membrane"


def test_whistle_open_trim_follows_new_tuning():
    """Подстройка при открытом свистке считает ход по свистковому строю."""
    with_trim = _whistle(note="C2", termination="open", trim_semitones=1)
    upper = resolve_tuning(with_trim)
    lower = resolve_tuning(_whistle(note="B1", termination="open"))

    from bass_tube.acoustics.trim import resolve_trim

    plan = resolve_trim(with_trim, upper)
    assert plan is not None
    assert plan.extra_length_mm == pytest.approx(
        lower.body_length_mm - upper.body_length_mm
    )


def test_stopped_body_is_sealed_and_longer_by_floor():
    """Тело заглушённой трубы: ось длиннее столба на дно, выход глухой."""
    params = tube_params(
        body_length_mm=300.0,
        source="whistle",
        termination="stopped",
        straight_count=1,
        **_box(max_height_mm=400.0, max_width_mm=150.0, max_depth_mm=150.0),
    )
    design = build_design(params)

    assert design.centerline.length_mm == pytest.approx(
        design.tuning.body_length_mm + params.floor_mm
    )
    shape = design.body.solid.solids().vals()[0]
    from bass_tube.body.tube import _vector

    seal = design.centerline.sample(design.centerline.length_mm - params.floor_mm / 2.0)
    air = design.centerline.sample(design.centerline.length_mm - params.floor_mm - 1.0)
    assert shape.isInside(_vector(seal.point))
    assert not shape.isInside(_vector(air.point))


def test_open_whistle_body_matches_membrane_geometry():
    """Открытый свисток не меняет деталь: та же труба, что у мембраны."""
    box = _box(max_height_mm=400.0, max_width_mm=150.0, max_depth_mm=150.0)
    whistle = build_design(
        tube_params(body_length_mm=300.0, source="whistle", straight_count=1, **box)
    )
    membrane = build_design(
        tube_params(body_length_mm=300.0, straight_count=1, **box)
    )

    assert whistle.centerline.length_mm == pytest.approx(300.0)
    assert whistle.body.solid.val().Volume() == pytest.approx(
        membrane.body.solid.val().Volume()
    )
