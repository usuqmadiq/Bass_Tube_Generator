"""Настройка воздушного канала свистка после продувки 22.10.2026.

Голова B засвистела, но тихо и без основного тона полутораметрового пути:
окно было рассчитано на ~100 Па. Гнездо не садилось до упора. Здесь —
зазор гнезда, подбор окна и щели по давлению дутья, набор сменных крышек.
"""

import math

import pytest

from bass_tube import resolve_tuning, tube_params
from bass_tube.constants import WHISTLE_THETA_RANGE, WHISTLE_THETA_TARGET
from bass_tube.design import build_design
from bass_tube.ui.app import _export_design
from bass_tube.ui.form import parse_lid_kit
from bass_tube.ui.report import format_design_report
from bass_tube.whistle.axial_head import axial_head_for_tube
from bass_tube.whistle.geometry import build_head, build_lid, lid_kit
from bass_tube.whistle.params import (
    cutup_for_pressure_mm,
    flue_for_tube,
    head_for_tube,
    voice_frequency_estimate_hz,
)
from bass_tube.whistle.planning import flue_tuning


def _whistle(**overrides):
    """Свистковая труба 1500 мм с заглушкой — как на продувке."""
    values = dict(
        body_length_mm=1500.0,
        source="whistle",
        termination="stopped",
        max_height_mm=250.0,
        max_width_mm=150.0,
        max_depth_mm=150.0,
        head_reserve_mm=35.0,
        turn_radius_mm=11.0,
        gap_mm=1.0,
    )
    values.update(overrides)
    return tube_params(**values)


def test_socket_gets_extra_clearance():
    """Гнездо обеих голов на 0,3 мм свободнее прежнего: Ø19,93 на конец 19,5."""
    import cadquery as cq

    params = _whistle()
    side = head_for_tube(params)
    axial = axial_head_for_tube(_whistle(whistle_head_kind="axial"))
    assert side.socket_inner_diameter_mm == pytest.approx(19.93)
    assert 2.0 * axial.socket_inner_radius_mm == pytest.approx(19.93)

    body = build_head(side).body.val()
    radius = side.socket_inner_diameter_mm / 2.0
    z = -side.socket_depth_mm / 2.0
    assert not body.isInside(cq.Vector(radius - 0.05, 0.0, z))
    assert body.isInside(cq.Vector(radius + 0.05, 0.0, z))

    custom = head_for_tube(_whistle(whistle_socket_clearance_mm=0.6))
    assert custom.socket_inner_diameter_mm == pytest.approx(20.1)


@pytest.mark.parametrize("pressure", [150.0, 200.0, 300.0])
def test_cutup_follows_blowing_pressure(pressure):
    """Окно подбирается так, что при давлении дутья θ ≈ 11, а щель — W/12."""
    params = _whistle(whistle_blow_pressure_pa=pressure)
    flue, cutup = flue_for_tube(params)
    frequency = voice_frequency_estimate_hz(params)

    exact = cutup_for_pressure_mm(frequency, pressure, WHISTLE_THETA_TARGET)
    assert abs(cutup - exact) <= 0.25 + 1e-9
    assert flue == pytest.approx(min(max(round(cutup / 12.0, 1), 0.6), 2.5))
    # Ориентир частоты близок к точному строю — окно подбирается не вслепую.
    assert resolve_tuning(params).frequency_hz == pytest.approx(frequency, rel=0.01)


def test_harder_blowing_needs_a_longer_cutup():
    """Чем сильнее дуют, тем длиннее окно; пределы 6…36 мм соблюдаются."""
    cutups = [flue_for_tube(_whistle(whistle_blow_pressure_pa=p))[1] for p in (100, 200, 400)]
    assert cutups[0] < cutups[1] < cutups[2]
    assert flue_for_tube(_whistle(whistle_blow_pressure_pa=5000))[1] == pytest.approx(36.0)


def test_explicit_flue_and_cutup_win():
    """Заданные щель и окно не подменяются подбором."""
    params = _whistle(whistle_windway_height_mm=0.8, whistle_cutup_mm=12.0)
    assert flue_for_tube(params) == (0.8, 12.0)


def test_each_kit_lid_leaves_its_own_flue():
    """Крышка набора оставляет в глубоком канале ровно свою щель, корпус не задевает."""
    import cadquery as cq

    head = head_for_tube(_whistle())
    body = build_head(head).body.val()
    floor = head.chamber_height_mm
    x = (head.wind_inlet_x_mm + head.window_start_x_mm) / 2.0
    assert head.channel_depth_resolved_mm == pytest.approx(2.5)
    for flue in (0.6, 1.0, 1.6, 2.5):
        lid = build_lid(head, flue).val()
        assert lid.isValid()
        assert sum(part.Volume() for part in body.intersect(lid).Solids()) == pytest.approx(0.0, abs=1e-6)
        assert not lid.isInside(cq.Vector(x, 0.0, floor + flue - 0.05))
        assert not body.isInside(cq.Vector(x, 0.0, floor + flue - 0.05))
        if flue < head.channel_depth_resolved_mm:
            assert lid.isInside(cq.Vector(x, 0.0, floor + flue + 0.05))


def test_kit_lids_print_flue_face_down():
    """В печатном виде крышка стоит на столе гранью потолка щели."""
    import cadquery as cq

    head = head_for_tube(_whistle())
    kit = lid_kit(head, (0.6, 1.3, 2.5, 9.0))
    assert set(kit) == {0.6, 1.3, 2.5}
    for flue, lid in kit.items():
        shape = lid.val()
        assert shape.BoundingBox().zmin == pytest.approx(0.0, abs=1e-6)
        assert shape.isInside(cq.Vector(
            (head.wind_inlet_x_mm + head.window_start_x_mm) / 2.0, 0.0, 0.05
        ))


def test_flue_tuning_brackets_the_working_pressure():
    """Рабочие давления дают θ на краях 7…17; кромка вне струи помечается."""
    head = head_for_tube(_whistle())
    frequency = 56.7
    tuning = flue_tuning(head, frequency, 200.0, (0.6, 1.0, 2.0))
    low, high = tuning["working_pressure_pa"]

    def theta(pressure):
        velocity = 0.8 * math.sqrt(2.0 * pressure / 1.2)
        return velocity / (frequency * head.window_length_mm / 1000.0)

    assert theta(low) == pytest.approx(WHISTLE_THETA_RANGE[0])
    assert theta(high) == pytest.approx(WHISTLE_THETA_RANGE[1])
    assert low < 200.0 < high
    by_flue = {lid["flue_mm"]: lid for lid in tuning["lids"]}
    assert by_flue[0.6]["labium_in_jet"] is False
    assert by_flue[2.0]["labium_in_jet"] is True
    assert by_flue[2.0]["flow_l_min"] > 3.0 * by_flue[0.6]["flow_l_min"]


def test_trim_keeps_the_printed_head():
    """Подстройка открытого свистка считает нижнюю ноту с той же головкой."""
    from bass_tube.acoustics.trim import resolve_trim

    upper_params = _whistle(body_length_mm=None, note="C3", termination="open", trim_semitones=1)
    upper = resolve_tuning(upper_params)
    flue, cutup = flue_for_tube(upper_params)
    lower = resolve_tuning(
        _whistle(body_length_mm=None, note="B2", termination="open",
                 whistle_windway_height_mm=flue, whistle_cutup_mm=cutup)
    )
    plan = resolve_trim(upper_params, upper)
    assert plan.extra_length_mm == pytest.approx(lower.body_length_mm - upper.body_length_mm)


def test_export_writes_the_lid_kit(tmp_path):
    """Сохранение кладёт рядом набор крышек с щелью в имени."""
    design = build_design(_whistle(body_length_mm=300.0, straight_count=1, max_height_mm=400.0))
    names = {p.name for p in _export_design(design, tmp_path / "т.step", tmp_path / "т.stl")}

    assert {"т-свисток.stl", "т-свисток-крышка.stl"} <= names
    for flue in ("0.6", "1", "1.3", "2.5"):
        assert f"т-свисток-крышка-h{flue}.stl" in names


def test_report_shows_pressures_and_lids():
    """Отчёт пишет рабочие давления, окно под давление и крышки."""
    report = format_design_report(build_design(_whistle(body_length_mm=300.0, straight_count=1, max_height_mm=400.0)))

    assert "Основной тон держится при" in report
    assert "Окно под 200 Па" in report
    assert "h 1,3 мм" in report


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0.6, 0.8 1,3; 2", (0.6, 0.8, 1.3, 2.0)),
        ("", None),
        ("нет", ()),
        ("0", ()),
    ],
)
def test_form_reads_the_lid_kit(text, expected):
    """Поле набора: пробелы, «;» и «, » — разделители, «1,3» — десятичная."""
    reasons: list[str] = []
    assert parse_lid_kit(text, reasons) == expected
    assert not reasons


def test_form_rejects_bad_lid_kit():
    reasons: list[str] = []
    assert parse_lid_kit("0.6, абв", reasons) is None
    assert reasons
