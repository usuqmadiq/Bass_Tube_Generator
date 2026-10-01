"""Высокие укладки под разрезы: вязанка вместо одной прямой, разрезы мимо колен и дырок."""

import cadquery as cq
import pytest

from bass_tube.acoustics.holes import HoleError, plan_holes
from bass_tube.body.splits import split_solid_for_print
from bass_tube.acoustics.trim import resolve_trim, socket_length_mm
from bass_tube.acoustics.tuning import resolve_tuning
from bass_tube.constants import PRINT_PLUG_MM, SLIDER_END
from bass_tube.design import build_design, plan_design
from bass_tube.layout.coil import LayoutError, layout_coil, print_piece_count
from bass_tube.layout.holes import exit_keep_mm, place_holes_in_envelope
from bass_tube.layout.print_cuts import (
    PrintCutError,
    column_spans,
    coil_cut_heights,
    cut_heights,
    hole_levels,
    keep_out_bands,
)
from bass_tube.params import ParamsError, tube_params


def _bundle(**overrides):
    """Габарит окна с разрезами: 250 × 150 × 150 мм, R = 11 мм, зазор 1 мм.

    Принимает подмену отдельных полей. Возвращает словарь для tube_params.
    """
    values = {
        "layout": "bundle",
        "max_height_mm": 250.0,
        "max_width_mm": 150.0,
        "max_depth_mm": 150.0,
        "head_reserve_mm": 35.0,
        "turn_radius_mm": 11.0,
        "gap_mm": 1.0,
        "trim_semitones": 1,
        "print_splits": True,
    }
    values.update(overrides)
    return values


def _assert_cuts_clear(cuts, bands, height, bed) -> None:
    """Разрезы не в запретных полосах и каждый кусок с папой сверху не выше стола.

    Принимает высоты разрезов, полосы, высоту детали и стол. У всех кусков,
    кроме верхнего, папа торчит вверх на длину штекера. Ничего не возвращает.
    """
    for cut in cuts:
        assert not any(low < cut < high for low, high in bands)
    bounds = [0.0, *cuts, height]
    for index in range(len(bounds) - 1):
        plug = PRINT_PLUG_MM if index < len(cuts) else 0.0
        assert bounds[index + 1] - bounds[index] + plug <= bed + 1e-6


def test_tall_layout_prefers_bundle_over_one_long_straight() -> None:
    """Выдвижной конец G1 на 2 полутона при столе 250: вязанка, а не прямая 2 м.

    Ничего не принимает. Компактная укладка не вмещает царгу, высокая
    выбирается по числу кусков печати: одна прямая дала бы девять кусков.
    Ничего не возвращает.
    """
    params = tube_params(
        note="G1", slider_kind=SLIDER_END, slider_semitones=2, **_bundle(trim_semitones=0)
    )
    plan = plan_design(params)
    assert plan.coil.straight_count >= 3
    assert plan.coil.height_mm > params.max_height_mm
    assert print_piece_count(plan.coil.height_mm, params) <= 3


def test_socket_longer_than_the_bed_is_named() -> None:
    """Царга слайдера длиннее стола: отказ называет царгу, а не ширину.

    Ничего не принимает. Разрез через ход царги не ставится, нижний кусок
    должен вместить её целиком. Ничего не возвращает.
    """
    params = tube_params(
        note="G1", slider_kind=SLIDER_END, slider_semitones=5, **_bundle(trim_semitones=0)
    )
    with pytest.raises(LayoutError, match="Царга"):
        plan_design(params)


def test_holes_fit_a_low_bed_by_cutting_a_taller_bundle() -> None:
    """G1, восемь дырок по 10 мм, стол 150 мм: вязанка выше стола и режется мимо дырок.

    Ничего не принимает. Раньше подбор дырок не знал о разрезах и
    отказывал. Ничего не возвращает.
    """
    params = tube_params(
        note="G1", hole_count=8, scale="natural_minor", hole_diameter_mm=10.0,
        **_bundle(max_height_mm=150.0),
    )
    tuning = resolve_tuning(params)
    trim = resolve_trim(params, tuning)
    holes = plan_holes(params, tuning, exit_keep_mm(params, trim))
    coil, placed = place_holes_in_envelope(params, tuning, holes, trim)
    assert len(placed) == 8
    assert coil.straight_count >= 3
    assert coil.height_mm > params.max_height_mm
    specs = tuple((spec.s_mm, spec.diameter_mm) for spec in holes.holes)
    bands = keep_out_bands(coil, params, holes=specs, bottom_keep_mm=socket_length_mm(trim))
    cuts = coil_cut_heights(coil, params, holes=specs, bottom_keep_mm=socket_length_mm(trim))
    assert cuts
    _assert_cuts_clear(cuts, bands, coil.height_mm, params.max_height_mm)
    for level, diameter in hole_levels(coil, specs):
        for cut in cuts:
            assert not level - diameter / 2.0 - PRINT_PLUG_MM <= cut <= level + diameter / 2.0


def test_cut_heights_step_below_blocked_bands() -> None:
    """Разрез в запретной полосе опускается под неё, куски не выше стола.

    Ничего не принимает. Ничего не возвращает.
    """
    bands = ((-1e9, 30.0), (180.0, 215.0), (330.0, 1e9))
    cuts = cut_heights(0.0, 360.0, 200.0, PRINT_PLUG_MM, bands)
    assert cuts[0] < 180.0
    _assert_cuts_clear(cuts, bands, 360.0, 200.0)
    with pytest.raises(PrintCutError):
        cut_heights(0.0, 360.0, 200.0, PRINT_PLUG_MM, ((-1e9, 30.0), (20.0, 250.0)))


def test_plugs_only_on_straights_crossing_the_cut() -> None:
    """Штекер ставится только на прямые, которые проходят сквозь разрез.

    Ничего не принимает. У вязанки с парами разной высоты под дырки часть
    прямых кончается ниже разреза: папа на них висел бы в воздухе. Прямая
    со стыком идёт выше разреза не меньше длины папы; прямая без стыка
    разрез вообще не пересекает. Ничего не возвращает.
    """
    params = tube_params(note="G2", hole_count=6, scale="natural_minor", **_bundle(max_height_mm=150.0))
    plan = plan_design(params)
    spans = column_spans(plan.coil)
    specs = tuple((hole.spec.s_mm, hole.spec.diameter_mm) for hole in plan.placed_holes)
    cuts = coil_cut_heights(
        plan.coil, params, holes=specs, bottom_keep_mm=socket_length_mm(plan.trim)
    )
    assert cuts
    for cut in cuts:
        crossing = [span for span in spans if span.crosses(cut)]
        assert crossing
        assert all(span.z_low_mm < cut < cut + PRINT_PLUG_MM < span.z_high_mm for span in crossing)
        missing = [span for span in spans if span not in crossing]
        assert all(span.z_high_mm <= cut or span.z_low_mm >= cut for span in missing)


def test_trim_longer_than_the_first_step_is_explained() -> None:
    """Подстройка на 2 полутона и мажор: царга занимает место первой дырки.

    Ничего не принимает. Первая ступень — целый тон, царга подстройки на
    два полутона длиннее места у выхода: текст говорит, что уменьшить.
    Ничего не возвращает.
    """
    params = tube_params(note="G1", hole_count=6, scale="major", **_bundle(trim_semitones=2))
    with pytest.raises(HoleError, match="Первая дырка"):
        plan_design(params)


def test_split_body_pieces_fit_the_bed() -> None:
    """G2 с шестью дырками на столе 150 мм: каждый кусок корпуса валиден и не выше стола.

    Ничего не принимает. Строит тело CadQuery. Ничего не возвращает.
    """
    params = tube_params(note="G2", hole_count=6, scale="natural_minor", **_bundle(max_height_mm=150.0))
    design = build_design(params)
    assert len(design.body_slices) >= 2
    volume = 0.0
    for piece in design.body_slices:
        for solid in piece.solid.solids().vals():
            assert solid.isValid()
            assert solid.BoundingBox().zlen <= params.max_height_mm + 1e-6
            volume += solid.Volume()
    assert volume == pytest.approx(design.body.solid.val().Volume(), rel=1e-4)


def test_joint_is_male_below_female_above_without_steps() -> None:
    """Стык прямой трубы: папа внизу смотрит вверх, мама сверху, канал ровный.

    Ничего не принимает. Режет трубу 19,5/15,5 мм высотой 300 мм на столе
    150 мм. Над разрезом на половине папы: у стенки канала — нижний кусок
    (папа), у наружной стенки — верхний (мама), в канале — ничего. Под
    разрезом всё у нижнего куска, у верхнего над папой — полная стенка.
    Сумма объёмов равна трубе, нижний кусок с папой не выше стола.
    Ничего не возвращает.
    """
    params = tube_params(note="C2", **_bundle(max_height_mm=150.0))
    outer_r = params.outer_diameter_mm / 2.0
    bore_r = params.bore_diameter_mm / 2.0
    tube = (
        cq.Workplane("XY").circle(outer_r).circle(bore_r).extrude(300.0)
    )
    pieces = split_solid_for_print(tube, params, ((0.0, 0.0),), stem="т")
    assert len(pieces) == 3
    lower, upper = pieces[0].solid.val(), pieces[1].solid.val()
    cut = pieces[0].z_max_mm
    joint_r = (outer_r + bore_r) / 2.0
    inner_wall = (bore_r + joint_r) / 2.0
    outer_wall = (joint_r + outer_r) / 2.0
    mid_male = cut + PRINT_PLUG_MM / 2.0

    def inside(shape, radius, z):
        """Лежит ли точка на радиусе radius и высоте z внутри тела."""
        return shape.isInside(cq.Vector(radius, 0.0, z))

    assert inside(lower, inner_wall, mid_male)
    assert not inside(upper, inner_wall, mid_male)
    assert inside(upper, outer_wall, mid_male)
    assert not inside(lower, outer_wall, mid_male)
    assert not inside(lower, bore_r / 2.0, mid_male)
    assert not inside(upper, bore_r / 2.0, mid_male)
    assert inside(lower, outer_wall, cut - 2.0)
    assert inside(upper, inner_wall, cut + PRINT_PLUG_MM + 2.0)
    assert lower.BoundingBox().zmax == pytest.approx(cut + PRINT_PLUG_MM)
    assert lower.BoundingBox().zlen <= params.max_height_mm + 1e-6
    total = sum(piece.solid.val().Volume() for piece in pieces)
    assert total == pytest.approx(tube.val().Volume(), rel=1e-6)


def test_thin_wall_is_refused_with_print_splits() -> None:
    """Стенка 1,5 мм при разрезах отвергается, 1,6 мм — проходит, без разрезов — любая.

    Ничего не принимает. Ничего не возвращает.
    """
    with pytest.raises(ParamsError, match=r"тоньше 1\.6"):
        tube_params(note="C2", wall_thickness_mm=1.5, **_bundle())
    assert tube_params(note="C2", wall_thickness_mm=1.6, **_bundle()).wall_thickness_mm == 1.6
    assert tube_params(
        note="C2", wall_thickness_mm=1.5, **_bundle(print_splits=False)
    ).wall_thickness_mm == 1.5


def test_plain_layouts_never_fall_back_to_one_straight() -> None:
    """Без дырок G1…G2 при столе 200 и 250 мм всегда вязанка из трёх и больше прямых.

    Ничего не принимает. Ничего не возвращает.
    """
    for note in ("G1", "A1", "C2", "E2", "G2"):
        for height in (200.0, 250.0):
            params = tube_params(note=note, **_bundle(max_height_mm=height))
            coil = layout_coil(params, resolve_tuning(params), resolve_trim(params, resolve_tuning(params)))
            assert coil.straight_count >= 3, (note, height)
