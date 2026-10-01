"""Игровые отверстия: лад от тоники корпуса, координата s, дырки на прямых наружу."""

import math

import pytest

from bass_tube.acoustics.holes import plan_holes
from bass_tube.acoustics.scales import ScaleError, scale_note_names
from bass_tube.acoustics.trim import resolve_trim
from bass_tube.acoustics.tuning import resolve_tuning
from bass_tube.layout.centerline import Straight, Turn, build_centerline
from bass_tube.layout.coil import LayoutError
from bass_tube.layout.holes import exit_keep_mm, place_holes_in_envelope
from bass_tube.params import tube_params


def _bundle(**overrides):
    """Габарит контрольной вязанки C2 без подстройки.

    Принимает подмену отдельных полей. Высота 250 мм, радиус 11 мм, зазор 1 мм.
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
        "trim_semitones": 0,
    }
    values.update(overrides)
    return values


def test_scale_notes_from_c2_tonic():
    """Тоника C2 даёт ожидаемые ступени пяти ладов; больше восьми отвергается."""
    assert scale_note_names("C2", "major", 7) == (
        "C2",
        "D2",
        "E2",
        "F2",
        "G2",
        "A2",
        "B2",
        "C3",
    )
    assert scale_note_names("C2", "natural_minor", 7) == (
        "C2",
        "D2",
        "D#2",
        "F2",
        "G2",
        "G#2",
        "A#2",
        "C3",
    )
    assert scale_note_names("C2", "melodic_minor", 7) == (
        "C2",
        "D2",
        "D#2",
        "F2",
        "G2",
        "A2",
        "B2",
        "C3",
    )
    assert scale_note_names("C2", "pentatonic", 5) == (
        "C2",
        "D#2",
        "F2",
        "G2",
        "A#2",
        "C3",
    )
    assert scale_note_names("C2", "major_pentatonic", 5) == (
        "C2",
        "D2",
        "E2",
        "G2",
        "A2",
        "C3",
    )
    with pytest.raises(ScaleError, match="от 1 до 8"):
        scale_note_names("C2", "major", 9)


def test_plan_holes_places_from_exit_and_reports_cents():
    """Две дырки мажора от C2: D2 и E2 ближе к выходу имеют большее s."""
    params = tube_params(note="C2", hole_count=2, scale="major", **_bundle())
    tuning = resolve_tuning(params)
    plan = plan_holes(params, tuning)

    assert plan is not None
    assert plan.tonic == "C2"
    assert [hole.note for hole in plan.holes] == ["D2", "E2"]
    assert plan.holes[0].s_mm > plan.holes[1].s_mm
    assert plan.holes[0].s_mm < tuning.body_length_mm
    assert plan.holes[1].s_mm > params.joint_length_mm

    closed, first, second = plan.fingerings
    assert closed.note == "C2" and closed.open_count == 0
    assert first.note == "D2" and first.open_count == 1
    assert second.note == "E2" and second.open_count == 2
    assert abs(first.cents) < 5.0
    assert abs(second.cents) < 5.0
    assert abs(closed.cents) < 80.0


def test_zero_holes_skip_the_plan():
    """Без дырок акустический план не строится."""
    params = tube_params(note="C2", **_bundle())
    assert plan_holes(params, resolve_tuning(params)) is None


def _fit(note, scale, count, trim):
    """Параметры, строй, подстройка, план и найденная укладка с дырками.

    Принимает ноту, лад, число дырок и полутоны подстройки. Считает всё так
    же, как окно. Возвращает (params, tuning, trim_plan, plan, coil, placed).
    """
    params = tube_params(note=note, hole_count=count, scale=scale, **_bundle(trim_semitones=trim))
    tuning = resolve_tuning(params)
    trim_plan = resolve_trim(params, tuning)
    plan = plan_holes(params, tuning, exit_keep_mm(params, trim_plan))
    assert plan is not None
    coil, placed = place_holes_in_envelope(params, tuning, plan, trim_plan)
    return params, tuning, trim_plan, plan, coil, placed


def _assert_print_rules(params, tuning, trim_plan, plan, coil, placed):
    """Проверяет правила печатной трубы с дырками.

    Принимает то, что вернул _fit. Ось равна корпусу; все нижние колени
    на цоколе; выход в столе вниз; вход — самая высокая точка оси и выше
    макушек на радиус, полтрубы и посадку; деталь с модулем в габарите.
    Каждая дырка на прямой, не ближе половины дырки плюс 1,5 мм к колену,
    не в цоколе и не в царге, смотрит горизонтально и не дальше 45° от
    «наружу», сверло не задевает соседние трубы. Ничего не возвращает.
    """
    line = build_centerline(coil, params.joint_length_mm)
    assert coil.straight_count % 2 == 1
    assert line.length_mm == pytest.approx(tuning.body_length_mm, abs=1e-6)
    turns = [p for p in line.primitives if isinstance(p, Turn)]
    bottoms = [t.center.z for t in turns if t.angle_end > math.pi]
    tops = [t.center.z for t in turns if t.angle_end < math.pi]
    assert bottoms and all(abs(z - coil.base_height_mm) < 1e-6 for z in bottoms)
    outlet = line.sample(line.length_mm)
    assert outlet.point.z == pytest.approx(0.0, abs=1e-9)
    assert outlet.tangent.z == pytest.approx(-1.0)
    inlet = line.sample(0.0).point.z
    rise = coil.turn_radius_mm + params.outer_diameter_mm / 2.0 + params.joint_length_mm
    assert all(z + rise <= inlet + 1e-6 for z in tops)
    assert coil.height_with_head_mm <= params.max_height_mm + 1e-6

    assert sorted(h.spec.s_mm for h in placed) == sorted(h.s_mm for h in plan.holes)
    margin = params.hole_diameter_mm / 2.0 + 1.5
    keep = exit_keep_mm(params, trim_plan)
    cx = sum(c[0] for c in coil.columns) / len(coil.columns)
    cy = sum(c[1] for c in coil.columns) / len(coil.columns)
    reach = params.outer_diameter_mm / 2.0 + params.hole_diameter_mm / 2.0
    for hole in placed:
        s = hole.spec.s_mm
        piece = line.primitive_at(s)
        assert isinstance(piece, Straight)
        assert piece.s_start_mm + margin - 1e-6 <= s <= piece.s_end_mm - margin + 1e-6
        assert s <= line.length_mm - keep - margin + 1e-6
        out = hole.outward
        assert abs(out.z) < 1e-9 and math.hypot(out.x, out.y) == pytest.approx(1.0)
        x, y = coil.columns[hole.column]
        radial = math.hypot(x - cx, y - cy)
        assert radial > 1e-6
        cos_off = ((x - cx) * out.x + (y - cy) * out.y) / radial
        assert cos_off >= math.cos(math.radians(45.0)) - 1e-6
        for index, (ox, oy) in enumerate(coil.columns):
            if index == hole.column:
                continue
            along = (ox - x) * out.x + (oy - y) * out.y
            if along > 1e-6:
                assert abs((ox - x) * out.y - (oy - y) * out.x) >= reach - 1e-6


def test_holes_sit_on_outer_straights_and_keep_axis_length():
    """Три дырки C2: на прямых снаружи, ось той же длины, s не подменена."""
    result = _fit("C2", "major", 3, 0)
    _assert_print_rules(*result)
    assert len(result[-1]) == 3


def test_eight_holes_obey_print_rules_across_notes_and_scales():
    """8 дырок на нотах и ладах, где жадный сдвиг пар раньше не справлялся.

    Каждая укладка держит правила печати: колени на цоколе, выход в дне,
    вход над макушками, дырки на наружных прямых, деталь в 250 мм.
    """
    cases = (
        ("C2", "major", 0),
        ("C2", "natural_minor", 1),
        ("F2", "major", 1),
        ("F#2", "natural_minor", 1),
        ("G2", "natural_minor", 0),
        ("A2", "major", 1),
        ("D2", "melodic_minor", 1),
        ("A1", "natural_minor", 1),
        ("G1", "major", 1),
    )
    for note, scale, trim in cases:
        result = _fit(note, scale, 8, trim)
        _assert_print_rules(*result)
        assert len(result[-1]) == 8


def test_impossible_holes_name_the_height_that_helps():
    """C3 с 8 дырками мажора не влезает в 250 мм: отказ называет нужную высоту."""
    with pytest.raises(LayoutError, match="Влезет при высоте печати"):
        _fit("C3", "major", 8, 0)
