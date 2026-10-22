"""Печатная головка свистка в генераторе: деталь, паспорт, сборка, экспорт."""

import pytest

from bass_tube import ParamsError, tube_params
from bass_tube.body.tube import export_whistle_head, load_tube_step
from bass_tube.constants import (
    DEFAULT_WHISTLE_EDGE_MM,
    DEFAULT_WHISTLE_LABIUM_OFFSET_MM,
    DEFAULT_WHISTLE_WINDWAY_LENGTH_MM,
)
from bass_tube.design import build_design, preview_solid, whistle_head_at_inlet
from bass_tube.whistle.params import WhistleHeadParams, head_for_tube


def _short_whistle(**overrides):
    """Короткая свистковая труба одной прямой: быстрый CAD для проверок.

    Принимает подмену полей tube_params. Возвращает TubeParams.
    """
    values = dict(
        body_length_mm=300.0,
        source="whistle",
        termination="stopped",
        straight_count=1,
        max_height_mm=400.0,
        max_width_mm=150.0,
        max_depth_mm=150.0,
        head_reserve_mm=35.0,
        turn_radius_mm=11.0,
        gap_mm=1.0,
    )
    values.update(overrides)
    return tube_params(**values)


def test_defaults_follow_the_print_test():
    """Умолчания после продувки: прототипный канал и кромка, шире щель, свободнее гнездо.

    Ветровой канал, кромка и смещение остались прототипными. Ширина щели
    выросла до четверти окружности канала, гнездо получило +0,3 мм, щель и
    окно по умолчанию пустые — подбор по давлению дутья.
    """
    head = WhistleHeadParams()
    params = _short_whistle()
    generated = head_for_tube(params)

    assert DEFAULT_WHISTLE_WINDWAY_LENGTH_MM == head.windway_length_mm
    assert DEFAULT_WHISTLE_EDGE_MM == head.edge_thickness_mm
    assert DEFAULT_WHISTLE_LABIUM_OFFSET_MM == head.labium_offset_mm
    assert params.whistle_windway_height_mm is None and params.whistle_cutup_mm is None
    assert generated.windway_width_mm == pytest.approx(12.0)
    assert generated.socket_inner_diameter_mm == pytest.approx(19.93)
    assert generated.windway_height_mm == pytest.approx(
        min(max(round(generated.window_length_mm / 12.0, 1), 0.6), 2.5)
    )


@pytest.mark.parametrize(
    ("height_mm", "cutup_mm"),
    [(0.6, 8.0), (0.8, 12.0), (1.0, 16.0)],
)
def test_abc_variants_build_with_requested_geometry(height_mm, cutup_mm):
    """Ряд A/B/C строится, размеры и шейка следуют за полями набора."""
    design = build_design(
        _short_whistle(
            whistle_windway_height_mm=height_mm,
            whistle_cutup_mm=cutup_mm,
        )
    )

    assert design.whistle_head is not None
    head = design.whistle_head.params
    assert head.windway_height_mm == height_mm
    assert head.window_length_mm == cutup_mm
    assert design.tuning.whistle_neck_mm == pytest.approx(
        head.chamber_height_mm + height_mm / 2.0
    )
    for part in design.whistle_head.print_parts().values():
        solids = part.solids().vals()
        assert len(solids) == 1 and solids[0].isValid()
        assert part.val().BoundingBox().zmin == pytest.approx(0.0, abs=1e-6)


def test_passport_matches_tuning_and_warns():
    """Паспорт свистка совпадает со строем и честно перечисляет допущения."""
    design = build_design(_short_whistle(whistle_windway_height_mm=0.8))
    report = design.whistle_report

    assert report is not None
    assert report["passive_frequency_hz"] == pytest.approx(
        design.tuning.frequency_hz, rel=1e-9
    )
    assert report["body_length_mm"] == pytest.approx(design.tuning.body_length_mm)
    assert report["head_calibrated"] is False
    assert report["termination"] == "stopped"
    assert report["warnings"]
    assert report["head"]["windway_height_mm"] == 0.8


def test_membrane_design_has_no_head():
    """Мембранная труба не получает ни головки, ни паспорта свистка."""
    design = build_design(
        tube_params(
            body_length_mm=300.0,
            straight_count=1,
            max_height_mm=400.0,
            max_width_mm=150.0,
            max_depth_mm=150.0,
            head_reserve_mm=35.0,
            turn_radius_mm=11.0,
            gap_mm=1.0,
        )
    )

    assert design.whistle_head is None
    assert design.whistle_report is None


def test_assembly_on_real_c2_body_without_intersections():
    """Голова B на входе корпуса C2: гнездо обнимает конец без пересечений."""
    design = build_design(
        tube_params(
            body_length_mm=1306.0,
            source="whistle",
            termination="stopped",
            whistle_windway_height_mm=0.8,
            whistle_cutup_mm=12.0,
            max_height_mm=250.0,
            max_width_mm=150.0,
            max_depth_mm=150.0,
            head_reserve_mm=35.0,
            turn_radius_mm=11.0,
            gap_mm=1.0,
        )
    )
    assembly = whistle_head_at_inlet(design)

    assert assembly is not None
    assert len(assembly.Solids()) == 2
    tube_solid = design.body.solid.val()
    for solid in assembly.Solids():
        common = tube_solid.intersect(solid)
        volume = sum(piece.Volume() for piece in common.Solids())
        assert volume == pytest.approx(0.0, abs=1e-6)

    inlet = design.centerline.sample(0.0).point
    socket = design.whistle_head.params.socket_depth_mm
    assert assembly.BoundingBox().zmin == pytest.approx(inlet.z - socket, abs=1e-6)
    assert preview_solid(design).isValid()


def test_export_writes_four_printable_files(tmp_path):
    """Экспорт пишет корпус и крышку головки в STEP и STL, STEP читается."""
    design = build_design(_short_whistle())
    body_step = tmp_path / "труба-свисток.step"
    body_stl = tmp_path / "труба-свисток.stl"
    lid_step = tmp_path / "труба-свисток-крышка.step"
    lid_stl = tmp_path / "труба-свисток-крышка.stl"

    export_whistle_head(design.whistle_head, body_step, body_stl, lid_step, lid_stl)

    for path in (body_step, body_stl, lid_step, lid_stl):
        assert path.exists() and path.stat().st_size > 0
    for path in (body_step, lid_step):
        solids = load_tube_step(path).solids().vals()
        assert len(solids) == 1 and solids[0].isValid()


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        (dict(source="whistle", whistle_windway_height_mm=0.0), "больше нуля"),
        (dict(source="whistle", whistle_cutup_mm=-1.0), "больше нуля"),
        (
            dict(
                source="whistle",
                whistle_windway_height_mm=0.4,
                whistle_edge_thickness_mm=0.5,
            ),
            "толще щели",
        ),
        (
            dict(source="whistle", whistle_labium_offset_mm=2.0),
            "выводит лабиум из струи",
        ),
        (dict(source="whistle", whistle_windway_width_mm=25.0), "не умещается"),
        (dict(whistle_windway_height_mm=0.8), "свисткового голоса нет"),
    ],
)
def test_bad_head_geometry_is_rejected(overrides, fragment):
    """Невалидная геометрия головки отвергается с русской причиной."""
    with pytest.raises(ParamsError) as error:
        tube_params(
            note="C2",
            max_height_mm=320.0,
            max_width_mm=400.0,
            max_depth_mm=40.0,
            head_reserve_mm=35.0,
            turn_radius_mm=30.0,
            gap_mm=2.0,
            **overrides,
        )

    assert fragment in str(error.value)
