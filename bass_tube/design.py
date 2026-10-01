"""Сборка трубы от параметров до полой детали.

Окно и проверка вызывают одну и ту же последовательность: строй верхней
ноты, укладка, ось, проверка стенки между коленами, тело корпуса и при
нужде трубка подстройки. Ноту и радиус здесь не подменяют: если укладка
не сходится, ошибка остаётся ошибкой.
"""

from __future__ import annotations

from dataclasses import dataclass

from bass_tube.acoustics.holes import HolePlan, plan_holes
from bass_tube.acoustics.slider import SliderPlan, bind_slider_columns, resolve_slider, slider_leg_points
from bass_tube.acoustics.trim import TrimPlan, resolve_trim
from bass_tube.acoustics.tuning import Tuning, resolve_tuning
from bass_tube.body.slider import build_slider_body
from bass_tube.body.splits import PrintSlice, split_solid_for_print
from bass_tube.body.tube import BodyError, TubeBody, build_tube_body
from bass_tube.body.tuner import build_tuner_body
from bass_tube.layout.centerline import Centerline, build_centerline
from bass_tube.layout.clearance import check_channel_clearance
from bass_tube.layout.coil import Coil, bottom_socket_mm, layout_coil
from bass_tube.layout.holes import PlacedHole, exit_keep_mm, place_holes_in_envelope
from bass_tube.layout.print_cuts import ColumnSpan, column_spans, keep_out_bands
from bass_tube.params import TubeParams


@dataclass(eq=False)
class Design:
    """Посчитанная труба: строй, укладка, ось, стенка между коленами и тело.

    channel_wall_mm — самая тонкая стенка между каналами несоседних колен,
    бесконечность, если колено одно. trim — ход выдвижной трубки, None если
    подстройки нет. tuner — отдельная деталь этой трубки. slider — ход
    выдвижного конца или U-колена, None если слайдера нет. slider_body —
    отдельная деталь слайдера. holes — лад и прогноз аппликатур,
    placed_holes — дырки на прямых с направлением наружу.
    body_slices и slider_slices — куски на печать со стыками «папа — мама», если
    включены разрезы; иначе пустые кортежи (сохраняется целая деталь).
    """

    params: TubeParams
    tuning: Tuning
    coil: Coil
    centerline: Centerline
    channel_wall_mm: float
    body: TubeBody
    trim: TrimPlan | None
    tuner: TubeBody | None
    slider: SliderPlan | None
    slider_body: TubeBody | None
    holes: HolePlan | None
    placed_holes: tuple[PlacedHole, ...]
    body_slices: tuple[PrintSlice, ...]
    slider_slices: tuple[PrintSlice, ...]


@dataclass(eq=False)
class DesignPlan:
    """Расчёт трубы без CAD: строй, подстройка, слайдер, дырки, укладка, ось.

    Поля как у Design, но без тел и кусков печати. slider уже привязан к
    прямым укладки. Из плана строится одна труба или общая модель пары.
    """

    params: TubeParams
    tuning: Tuning
    coil: Coil
    centerline: Centerline
    channel_wall_mm: float
    trim: TrimPlan | None
    slider: SliderPlan | None
    holes: HolePlan | None
    placed_holes: tuple[PlacedHole, ...]


def plan_design(params: TubeParams, stack_height_mm: float | None = None) -> DesignPlan:
    """Считает строй, подстройку, слайдер, дырки и укладку без тела.

    Принимает проверенные параметры и необязательный предел собранной
    высоты при разрезах (вместо стола; разрезы всё равно по столу).
    Порядок и правила те же, что у build_design, но CAD не трогается.
    Возвращает DesignPlan. Ошибки расчёта и укладки пробрасывает как есть.
    """
    tuning = resolve_tuning(params)
    slider = resolve_slider(params, tuning)
    trim = None if slider is not None else resolve_trim(params, tuning)
    holes = plan_holes(params, tuning, exit_keep_mm(params, trim))
    placed: tuple[PlacedHole, ...] = ()
    if holes is None:
        coil = layout_coil(params, tuning, trim, slider, stack_height_mm)
    else:
        coil, placed = place_holes_in_envelope(params, tuning, holes, trim, stack_height_mm)
    if slider is not None:
        slider = bind_slider_columns(slider, coil.straight_count)
    centerline = build_centerline(coil, params.joint_length_mm)
    wall = check_channel_clearance(centerline, params)
    return DesignPlan(
        params=params,
        tuning=tuning,
        coil=coil,
        centerline=centerline,
        channel_wall_mm=wall,
        trim=trim,
        slider=slider,
        holes=holes,
        placed_holes=placed,
    )


def build_design(params: TubeParams) -> Design:
    """Считает строй, укладывает прямые и строит полую деталь.

    Принимает проверенные параметры. Длина корпуса берётся из строя верхней
    ноты (трубка или слайдер задвинуты). Если есть подстройка, рядом считается
    выдвижная трубка: вложенный кусок в длину пути не входит дважды, посадка
    мембраны на месте. Слайдер — отдельное управление: выдвижной конец
    (ΔL ≈ x) или семейство U-колен (q = 2 × число колен); с отверстиями и
    с подстройкой он не сочетается. Печатается сложенный корпус; высота на
    полном ходу пишется в отчёт. Деталь слайдера должна влезть на стол
    любой стороной; резать её нельзя, пока стенка вставки тоньше 1,6 мм; ход сам
    не укорачивается. Игровые отверстия считаются по ладу той же ноты,
    первая не заходит в цоколь и царгу. Под них подбирается укладка:
    нечётное число прямых, высоты пар и при нужде тесный радиус колена,
    чтобы колена легли между дырками; нижние колени на цоколе, вход над
    самым высоким коленом, выход в дне. Ось — из укладки, тело — из оси и
    укладки. Перед телом проверяет, что каналы колен не сходятся ближе
    стенки. Возвращает Design. Ошибки расчёта, укладки и тела пробрасывает
    как есть.
    """
    plan = plan_design(params)
    coil, centerline, placed = plan.coil, plan.centerline, plan.placed_holes
    trim, slider = plan.trim, plan.slider
    body = build_tube_body(centerline, coil, params, placed, slider)
    tuner = build_tuner_body(trim) if trim is not None else None
    slider_body = (
        build_slider_body(
            slider, coil.turn_radius_mm, coil.columns, coil.base_height_mm
        )
        if slider is not None
        else None
    )
    body_slices, slider_slices = _print_slices(
        params, coil, body, slider, slider_body, placed, trim
    )
    return Design(
        params=params,
        tuning=plan.tuning,
        coil=coil,
        centerline=centerline,
        channel_wall_mm=plan.channel_wall_mm,
        body=body,
        trim=trim,
        tuner=tuner,
        slider=slider,
        slider_body=slider_body,
        holes=plan.holes,
        placed_holes=placed,
        body_slices=body_slices,
        slider_slices=slider_slices,
    )


def preview_solid(design: Design):
    """Солид для окна: корпус, справа трубка подстройки или деталь слайдера.

    Принимает Design. Сдвигает отдельную деталь по x за габарит корпуса
    с зазором 10 мм, чтобы обе были видны сразу. Возвращает фигуру CadQuery.
    """
    shape = design.body.solid.val()
    extra_body = design.slider_body if design.slider_body is not None else design.tuner
    if extra_body is None:
        return shape
    extra = extra_body.solid.val()
    gap_mm = 10.0
    dx = shape.BoundingBox().xmax + gap_mm - extra.BoundingBox().xmin
    return shape.fuse(extra.translate((dx, 0.0, 0.0)))


def body_split_guides(
    coil: Coil,
    params: TubeParams,
    placed: tuple[PlacedHole, ...],
    trim: TrimPlan | None,
    slider: SliderPlan | None,
) -> tuple[tuple[ColumnSpan, ...], tuple[tuple[float, float], ...]]:
    """Отрезки прямых и запретные полосы разрезов корпуса.

    Принимает укладку, параметры, привязанные дырки, подстройку и слайдер.
    Возвращает (отрезки прямых для стыков, полосы высот, где разрез не
    ставят: колени, посадка, дырки, цоколь и царга).
    """
    bands = keep_out_bands(
        coil,
        params,
        holes=tuple((hole.spec.s_mm, hole.spec.diameter_mm) for hole in placed),
        bottom_keep_mm=bottom_socket_mm(trim, slider),
    )
    return column_spans(coil), bands


def _print_slices(
    params: TubeParams,
    coil: Coil,
    body: TubeBody,
    slider: SliderPlan | None,
    slider_body: TubeBody | None,
    placed: tuple[PlacedHole, ...] = (),
    trim: TrimPlan | None = None,
) -> tuple[tuple[PrintSlice, ...], tuple[PrintSlice, ...]]:
    """Режет корпус и слайдер на куски стола, если разрезы включены.

    Принимает параметры, укладку, тело корпуса, план слайдера, его деталь,
    привязанные дырки и подстройку. Без разрезов или когда деталь уже
    влезает — пустые кортежи: сохраняют целую деталь. Разрезы корпуса
    обходят колени, посадку, дырки и царгу; стык «папа — мама» без зазора
    (папа внизу, смотрит вверх) стоит только на прямых сквозь разрез.
    Возвращает (куски корпуса, куски слайдера).
    """
    if not params.print_splits:
        return (), ()
    spans, bands = body_split_guides(coil, params, placed, trim, slider)
    try:
        body_slices = split_solid_for_print(
            body.solid, params, coil.columns, stem="корпус", spans=spans, bands=bands
        )
    except Exception as exc:
        raise BodyError(f"Разрезы корпуса не построились: {exc}") from exc
    if len(body_slices) <= 1:
        body_slices = ()
    return body_slices, slider_print_slices(params, coil, slider, slider_body)


def slider_print_slices(
    params: TubeParams,
    coil: Coil,
    slider: SliderPlan | None,
    slider_body: TubeBody | None,
) -> tuple[PrintSlice, ...]:
    """Режет деталь слайдера на куски стола, если она выше.

    Принимает параметры, укладку, план слайдера и его деталь. Стыки
    «папа — мама» на ветвях слайдера по стенке царги. Возвращает куски или пустой
    кортеж, если резать не нужно. Если разрез не построился, поднимает
    BodyError.
    """
    if not params.print_splits or slider is None or slider_body is None:
        return ()
    points = slider_leg_points(slider, coil.turn_radius_mm, coil.columns)
    try:
        extra = split_solid_for_print(
            slider_body.solid,
            params,
            points,
            stem="слайдер",
            bore_diameter_mm=slider.bore_diameter_mm,
            outer_diameter_mm=slider.tenon_diameter_mm,
        )
    except Exception as exc:
        raise BodyError(f"Разрезы слайдера не построились: {exc}") from exc
    return extra if len(extra) > 1 else ()
