"""Коллектор пары свистков: деталь, сборка, воздушный путь, CLI и отказы."""

import json

import pytest

from bass_tube.whistle.acoustics import estimate_pair
from bass_tube.whistle.geometry import build_head
from bass_tube.whistle.manifold import (
    ManifoldParams,
    WhistleManifoldError,
    build_manifold,
)
from bass_tube.whistle.params import WhistleHeadParams


def _head_b() -> WhistleHeadParams:
    """Голова B: щель 0,8 мм, окно 12 мм — первый кандидат пары."""
    return WhistleHeadParams(windway_height_mm=0.8, window_length_mm=12.0)


def test_default_manifold_builds_one_valid_solid():
    """Коллектор по умолчанию строится одним валидным телом с хватом ≥ 2 мм."""
    manifold = build_manifold(ManifoldParams(head=_head_b()))

    solids = manifold.solid.solids().vals()
    assert len(solids) == 1 and solids[0].isValid()
    assert manifold.params.grip_resolved_mm >= 2.0
    assert manifold.params.pocket_end_x_mm < _head_b().window_start_x_mm


def test_assembly_feeds_both_windways_without_intersections():
    """Один порт продувает обе щели; коллектор не задевает головы и окна."""
    import cadquery as cq

    head = _head_b()
    manifold = build_manifold(ManifoldParams(head=head))
    parts = build_head(head)
    spacing = manifold.params.spacing_mm
    head_solids = []
    for dy in (-spacing / 2.0, spacing / 2.0):
        head_solids.append(parts.body.val().translate((0.0, dy, 0.0)))
        head_solids.append(parts.lid.val().translate((0.0, dy, 0.0)))
    collector = manifold.solid.val()

    for solid in head_solids:
        common = collector.intersect(solid)
        assert sum(piece.Volume() for piece in common.Solids()) == pytest.approx(
            0.0, abs=1e-6
        )

    jet = head.jet_center_z_mm
    x_in = head.wind_inlet_x_mm
    p = manifold.params
    path = [
        (p.outer_start_x_mm + 1.0, 0.0, p.port_center[2]),
        (x_in - p.plenum_depth_mm / 2.0, 0.0, p.cavity_top_z_mm / 2.0),
    ]
    for side in (-spacing / 2.0, spacing / 2.0):
        path += [
            (x_in - 1.0, side, jet),
            (x_in + p.grip_resolved_mm / 2.0, side, jet),
            (x_in + head.windway_length_mm * 0.75, side, jet),
            (head.window_end_x_mm - 0.1, side, head.labium_center_z_mm),
        ]
    everything = [collector, *head_solids]
    for point in path:
        assert not any(
            solid.isInside(cq.Vector(*point)) for solid in everything
        ), f"воздушный путь перекрыт в {point}"

    # Окна остаются открытыми в атмосферу: полости после лабиумов коллектор
    # не накрывает и не соединяет.
    for side in (-spacing / 2.0, spacing / 2.0):
        over_window = cq.Vector(0.0, side, head.body_top_z_mm + 0.5)
        assert not collector.isInside(over_window)


def test_print_part_stands_on_bed():
    """Печатная ориентация: портом вниз, низ детали на z = 0."""
    manifold = build_manifold(ManifoldParams(head=_head_b()))
    printable = manifold.print_part()

    assert printable.val().isValid()
    assert printable.val().BoundingBox().zmin == pytest.approx(0.0, abs=1e-6)


def test_pair_flow_is_sum_of_branches():
    """Паспорт пары складывает расходы ветвей при сохранении их режимов."""
    pair = estimate_pair(80.0, 82.0, 3.97, 3.96)

    assert pair.total_flow_l_min == pytest.approx(3.97 + 3.96)
    assert pair.beat_hz == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        (dict(grip_mm=20.0), "налезает на круглое тело"),
        (dict(port_diameter_mm=20.0), "не умещается по высоте"),
        (dict(spacing_mm=10.0), "карманы голов сливаются"),
    ],
)
def test_bad_manifold_is_rejected(overrides, fragment):
    """Невалидный коллектор отвергается с понятной причиной."""
    with pytest.raises(WhistleManifoldError) as error:
        ManifoldParams(head=_head_b(), **overrides)

    assert fragment in str(error.value)


def test_short_windway_leaves_no_grip():
    """Короткий ветровой канал не оставляет карману хвата — честный отказ."""
    head = WhistleHeadParams(windway_length_mm=9.0)
    with pytest.raises(WhistleManifoldError) as error:
        ManifoldParams(head=head)

    assert "хвата" in str(error.value)


def test_cli_pair_exports_manifold(tmp_path, capsys):
    """CLI пары пишет коллектор, сборку и паспорт с общим расходом."""
    from bass_tube.whistle.__main__ import main

    code = main(
        [
            "--target-hz", "80",
            "--second-target-hz", "82",
            "--termination", "stopped",
            "--windway-height-mm", "0.8",
            "--cutup-mm", "12",
            "--export-dir", str(tmp_path),
        ]
    )
    capsys.readouterr()

    assert code == 0
    for name in ("manifold.step", "manifold.stl", "assembly.step", "report.json"):
        assert (tmp_path / name).exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    pair = report["pair"]
    assert pair["common_supply_manifold"] is True
    assert pair["manifold"]["grip_mm"] >= 2.0
    flows = [voice["air_estimate"]["flow_l_min"] for voice in report["voices"]]
    assert pair["total_flow_l_min"] == pytest.approx(sum(flows))
    readme = (tmp_path / "PRINT_README.txt").read_text(encoding="utf-8")
    assert "Коллектор" in readme


def test_cli_no_manifold_keeps_separate_feeds(tmp_path, capsys):
    """Флаг --no-manifold оставляет две раздельные подачи без коллектора."""
    from bass_tube.whistle.__main__ import main

    code = main(
        [
            "--target-hz", "80",
            "--second-target-hz", "82",
            "--no-manifold",
            "--export-dir", str(tmp_path),
        ]
    )
    capsys.readouterr()

    assert code == 0
    assert not (tmp_path / "manifold.stl").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["pair"]["common_supply_manifold"] is False
    assert "manifold" not in report["pair"]
