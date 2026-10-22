"""Комбинированные пары: у каждого голоса свой источник и свой дальний конец."""

import math
from pathlib import Path

import pytest

from bass_tube import ParamsError, resolve_tuning, tube_params
from bass_tube.acoustics.notes import midi_number, parse_note_name
from bass_tube.constants import MEMBRANE_MOUTHPIECE_SEAT_MM
from bass_tube.pair import (
    build_voice_pair,
    drone_params,
    export_pair,
    inlet_distance_mm,
    melody_params,
    mouthpiece_seat_mm,
    plan_voice_pair,
    whistle_heads_at_inlets,
)
from bass_tube.whistle.axial_head import AxialHeadParams

PARTS = Path(__file__).resolve().parent.parent / "parts"


def _box(**overrides):
    """Габарит контрольной пары: стол 250×150×150, R = 11 мм.

    Принимает подмену полей. Возвращает словарь для tube_params.
    """
    values = dict(
        max_height_mm=250.0,
        max_width_mm=150.0,
        max_depth_mm=150.0,
        head_reserve_mm=35.0,
        turn_radius_mm=11.0,
        gap_mm=1.0,
    )
    values.update(overrides)
    return values


def _membrane_and_axial_drone(**overrides):
    """Мелодия-мембрана C2 и дрон — осевой свисток G1 с заглушённым концом."""
    values = dict(
        note="C2",
        drone_note="G1",
        drone_source="whistle",
        drone_termination="stopped",
        whistle_head_kind="axial",
    )
    values.update(overrides)
    return tube_params(**values, **_box())


def _frequency(note: str) -> float:
    return 440.0 * 2.0 ** ((midi_number(parse_note_name(note)) - 69) / 12.0)


def test_combined_lengths_match_hand_formula():
    """Мембрана C2 и свистковый дрон G1: длины сходятся с ручным расчётом.

    Мелодия — прежняя четверть волны мембраны (1306 мм). Заглушённый
    свисток без поправки окна: столб = c/(4f) минус шейка осевой головки.
    Ось дрона длиннее столба на дно печатной заглушки.
    """
    params = _membrane_and_axial_drone()
    plan = plan_voice_pair(params)

    single = resolve_tuning(tube_params(note="C2", **_box()))
    assert plan.melody.tuning.body_length_mm == pytest.approx(single.body_length_mm)
    assert plan.melody.tuning.source == "membrane"

    neck = AxialHeadParams().nominal_head_length_mm
    expected = 343.0 * 1000.0 / (4.0 * _frequency("G1")) - neck
    drone = plan.drone.tuning
    assert drone.source == "whistle" and drone.termination == "stopped"
    assert drone.body_length_mm == pytest.approx(expected, abs=1e-6)
    assert plan.drone.centerline.length_mm == pytest.approx(
        drone.body_length_mm + params.floor_mm
    )
    assert plan.melody.centerline.length_mm == pytest.approx(single.body_length_mm)


def test_whistle_melody_with_membrane_drone():
    """Наоборот: свисток-мелодия и мембранный дрон считаются каждый своим строем."""
    params = tube_params(
        note="C2",
        source="whistle",
        termination="stopped",
        whistle_head_kind="axial",
        drone_note="G1",
        **_box(),
    )
    plan = plan_voice_pair(params)

    melody_alone = resolve_tuning(
        tube_params(
            note="C2", source="whistle", termination="stopped",
            whistle_head_kind="axial", **_box(),
        )
    )
    drone_alone = resolve_tuning(tube_params(note="G1", **_box()))
    assert plan.melody.tuning.body_length_mm == pytest.approx(melody_alone.body_length_mm)
    assert plan.drone.tuning.body_length_mm == pytest.approx(drone_alone.body_length_mm)
    assert plan.drone.tuning.source == "membrane"
    assert plan.drone_inlet_offset_mm > 0.0


def test_joined_body_seals_stopped_drone_and_keeps_channels_apart():
    """Общая деталь: глухой выход дрона, каналы не связаны, входы на 48 мм."""
    from bass_tube.body.tube import _vector

    pair = build_voice_pair(_membrane_and_axial_drone())

    assert inlet_distance_mm(pair) == pytest.approx(48.0)
    assert pair.coupling.channels_independent is True
    assert pair.coupling.supply_chamber is False
    shape = pair.body.solid.solids().vals()[0]
    floor = pair.drone.params.floor_mm
    line = pair.drone.centerline
    assert shape.isInside(_vector(line.sample(line.length_mm - floor / 2.0).point))
    assert not shape.isInside(_vector(line.sample(line.length_mm - floor - 1.0).point))
    melody_exit = pair.melody.centerline.sample(pair.melody.centerline.length_mm - 1.0)
    assert not shape.isInside(_vector(melody_exit.point))

    assert pair.melody_whistle_head is None and pair.melody_whistle_report is None
    assert pair.drone_whistle_head is not None
    assert pair.drone_whistle_report["passive_frequency_hz"] == pytest.approx(
        pair.drone.tuning.frequency_hz, rel=1e-9
    )


def test_mouthpiece_seats_on_membrane_and_axial_heads():
    """Мундштук садится на оба модуля разом: вход свистка опущен на разницу высот.

    Реальный parts/двойной мундштук.step ставится гнездом 0 над мембраной,
    гнездом −48 над осевой головкой дрона; он не пересекает ни корпус, ни
    головку, а его трубка встаёт на торец головки с зазором стыка.
    """
    import cadquery as cq

    pair = build_voice_pair(_membrane_and_axial_drone())
    melody_inlet = pair.melody.centerline.sample(0.0).point
    drone_inlet = pair.drone.centerline.sample(0.0).point
    melody_seat = mouthpiece_seat_mm(pair.melody.params)
    drone_seat = mouthpiece_seat_mm(pair.drone.params)

    assert melody_seat == pytest.approx(MEMBRANE_MOUTHPIECE_SEAT_MM)
    assert pair.drone_inlet_offset_mm == pytest.approx(melody_seat - drone_seat)
    assert melody_inlet.z + melody_seat == pytest.approx(drone_inlet.z + drone_seat, abs=1e-6)

    mouthpiece = cq.importers.importStep(str(PARTS / "двойной мундштук.step")).val()
    ux = (drone_inlet.x - melody_inlet.x) / 48.0
    uy = (drone_inlet.y - melody_inlet.y) / 48.0
    turn = math.degrees(math.atan2(-uy, -ux))
    gap = 0.1
    placed = (
        mouthpiece.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), 180.0)
        .rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), turn)
        .translate(
            cq.Vector(melody_inlet.x, melody_inlet.y, melody_inlet.z + melody_seat + gap + 25.0)
        )
    )
    heads = whistle_heads_at_inlets(pair)
    for solid in (pair.body.solid.val(), *heads.Solids()):
        common = placed.intersect(solid)
        assert sum(piece.Volume() for piece in common.Solids()) == pytest.approx(0.0, abs=1e-6)

    # Над головкой дрона — стенка трубки мундштука сразу над её торцом
    # (у торца канал мундштука раскрыт до Ø20,4, стенка r 10,2…11):
    # гнездо −48 действительно встало на осевую головку.
    above_head = cq.Vector(
        drone_inlet.x + uy * 10.6,
        drone_inlet.y - ux * 10.6,
        drone_inlet.z + drone_seat + gap + 0.5,
    )
    assert placed.isInside(above_head)


def test_axial_and_side_pairs_keep_inlets_level_and_heads_apart():
    """Свисток + свисток: входы на одной высоте, головки не задевают друг друга."""
    for kind, parts_per_head in (("axial", 1), ("side", 2)):
        pair = build_voice_pair(
            tube_params(
                note="C2",
                source="whistle",
                termination="stopped",
                whistle_head_kind=kind,
                drone_note="G1",
                drone_source="whistle",
                drone_termination="stopped",
                **_box(),
            )
        )
        if kind == "axial":
            # Окна подобраны под ноту каждого голоса — головы разной высоты,
            # и вход дрона сдвинут так, чтобы мундштук сел на обе.
            melody_z = pair.melody.centerline.sample(0.0).point.z
            drone_z = pair.drone.centerline.sample(0.0).point.z
            assert melody_z + mouthpiece_seat_mm(pair.melody.params) == pytest.approx(
                drone_z + mouthpiece_seat_mm(pair.drone.params), abs=1e-6
            )
        else:
            assert pair.drone_inlet_offset_mm == 0.0
        solids = whistle_heads_at_inlets(pair).Solids()
        assert len(solids) == 2 * parts_per_head
        body = pair.body.solid.val()
        for index, solid in enumerate(solids):
            assert sum(p.Volume() for p in body.intersect(solid).Solids()) == pytest.approx(0.0, abs=1e-6)
            for other in solids[index + 1:]:
                assert sum(p.Volume() for p in solid.intersect(other).Solids()) == pytest.approx(
                    0.0, abs=1e-6
                )


def test_export_pair_writes_heads(tmp_path):
    """Экспорт пары пишет общую деталь и головки свистковых голосов."""
    pair = build_voice_pair(_membrane_and_axial_drone())
    saved = export_pair(pair, tmp_path / "пара.step", tmp_path / "пара.stl")
    names = {path.name for path in saved}

    assert {"пара.step", "пара.stl", "пара-свисток-дрон.step", "пара-свисток-дрон.stl"} <= names
    assert not any("крышка" in name for name in names)
    for path in saved:
        assert path.exists() and path.stat().st_size > 0


def test_print_splits_cut_the_combined_pair():
    """Разрезы на печать режут комбинированную пару по прежним правилам."""
    pair = build_voice_pair(
        tube_params(
            note="C2",
            drone_note="G1",
            drone_source="whistle",
            drone_termination="stopped",
            whistle_head_kind="axial",
            print_splits=True,
            **_box(max_height_mm=160.0),
        )
    )

    assert len(pair.body_slices) >= 2
    for piece in pair.body_slices:
        solids = piece.solid.solids().vals()
        assert solids and all(solid.isValid() for solid in solids)


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        (dict(drone_source="whistle"), "ноты дрона нет"),
        (dict(drone_note="G1", drone_termination="stopped"), "только у свисткового дрона"),
        (
            dict(
                drone_note="G1", drone_source="whistle", drone_termination="stopped",
                drone_trim_semitones=1,
            ),
            "дрона некуда выходить",
        ),
        (dict(drone_note="G1", whistle_windway_height_mm=0.8), "свисткового голоса нет"),
        (dict(drone_note="G1", drone_source="дудка"), "не известен"),
    ],
)
def test_rejected_pair_combinations(overrides, fragment):
    """Невалидные сочетания голосов отвергаются с понятной причиной."""
    with pytest.raises(ParamsError) as error:
        tube_params(note="C2", **overrides, **_box())

    assert fragment in str(error.value)


def test_voice_params_drop_foreign_whistle_fields():
    """Голос-мембрана в паре не несёт свистковых полей соседа."""
    params = _membrane_and_axial_drone(whistle_windway_height_mm=0.8)
    melody = melody_params(params)
    drone = drone_params(params)

    assert melody.source == "membrane"
    assert melody.whistle_head_kind == "side"
    assert melody.whistle_windway_height_mm is None
    assert drone.source == "whistle" and drone.whistle_head_kind == "axial"
    assert drone.whistle_windway_height_mm == 0.8
