"""Второй голос: мелодия и дрон одной деталью, входы на 48 мм.

Каждая труба считается своим строем. Мелодия укладывается как обычно,
вход в центре её вязанки. Дрон укладывается под ту же высоту входа, его
вход на краю вязанки, на 48 мм от входа мелодии: на эти два входа сядет
отдельная насадка на две мембраны. Обе трубы стоят на столе, общий
цоколь связывает их в одну деталь, каналы внутри не соединяются. Камеры
подачи в модели нет. При разрезах на печать режется вся пара целиком.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

from bass_tube.acoustics.holes import HoleError
from bass_tube.acoustics.slider import skip_turns_after_straights
from bass_tube.acoustics.trim import TrimPlan, resolve_trim
from bass_tube.acoustics.tuning import Tuning, resolve_tuning
from bass_tube.body.slider import build_slider_body
from bass_tube.body.splits import PrintSlice, split_solid_for_print
from bass_tube.body.tube import BodyError, BodyVoice, TubeBody, build_joined_body, export_tube_body
from bass_tube.body.tuner import build_tuner_body
from bass_tube.constants import DUAL_INLET_SPACING_MM, PRINT_PLUG_MM
from bass_tube.design import Design, DesignPlan, build_design, plan_design, preview_solid, slider_print_slices
from bass_tube.layout.centerline import build_centerline
from bass_tube.layout.clearance import check_channel_clearance
from bass_tube.layout.coil import LayoutError, bottom_socket_mm
from bass_tube.layout.holes import MAX_PRINT_PIECES
from bass_tube.layout.pair_layout import PairPlacement, drone_coils_for_inlet, place_pair
from bass_tube.layout.print_cuts import (
    ColumnSpan,
    PrintCutError,
    column_spans,
    cut_heights,
    keep_out_bands,
)
from bass_tube.params import ParamsError, TubeParams


@dataclass(frozen=True, slots=True)
class CouplingCheck:
    """Проверка, что трубы не связаны общей камерой сильнее, чем заложено.

    inlet_spacing_mm — расстояние между осями входов.
    min_column_distance_mm — наименьшее расстояние в плане между осями
    прямых и колен разных труб. wall_clearance_mm — зазор между наружными
    стенками (расстояние минус диаметр). channels_independent — каналы
    вырезаны по отдельности и не сливаются. supply_chamber — камера подачи
    в генераторе есть; всегда False: насадку моделируют отдельно.
    """

    inlet_spacing_mm: float
    min_column_distance_mm: float
    wall_clearance_mm: float
    channels_independent: bool
    supply_chamber: bool


@dataclass(eq=False)
class PairPlan:
    """Расчёт пары без CAD: обе трубы на местах и разрезы.

    params — общий набор с нотой дрона. melody и drone — планы труб в
    координатах общей детали. placement — найденное положение. spans и
    bands — прямые обеих труб и запретные полосы высот для разрезов.
    height_mm — верх общей детали.
    """

    params: TubeParams
    melody: DesignPlan
    drone: DesignPlan
    placement: PairPlacement
    spans: tuple[ColumnSpan, ...]
    bands: tuple[tuple[float, float], ...]
    height_mm: float


@dataclass(eq=False)
class VoicePair:
    """Собранная пара: одна деталь с двумя каналами и отдельные вставки.

    params — исходный набор. melody и drone — планы труб на местах.
    body — общая деталь. melody_tuner и drone_tuner — трубки подстройки,
    slider_body — деталь слайдера мелодии. body_slices и slider_slices —
    куски на печать, если включены разрезы. width_mm, depth_mm, height_mm —
    габарит общей детали. coupling — что каналы не слиты.
    """

    params: TubeParams
    melody: DesignPlan
    drone: DesignPlan
    body: TubeBody
    melody_tuner: TubeBody | None
    drone_tuner: TubeBody | None
    slider_body: TubeBody | None
    body_slices: tuple[PrintSlice, ...]
    slider_slices: tuple[PrintSlice, ...]
    inlet_spacing_mm: float
    coupling: CouplingCheck
    width_mm: float
    depth_mm: float
    height_mm: float


def build_instrument(params: TubeParams) -> Design | VoicePair:
    """Считает одну трубу или пару мелодия+дрон.

    Принимает проверенные параметры. Если нота дрона не задана, строит
    одну трубу. Если задана — одну деталь с двумя каналами и входами на
    48 мм. Возвращает Design либо VoicePair.
    """
    if params.drone_note:
        return build_voice_pair(params)
    return build_design(params)


def plan_voice_pair(params: TubeParams) -> PairPlan:
    """Раскладывает мелодию и дрон в одну деталь без CAD.

    Принимает параметры с нотой дрона. Мелодия — обычный расчёт трубы.
    Дрон — от меньшего числа прямых к большему: вход на высоте входа
    мелодии, положение рядом без пересечений и без помех дыркам, общий
    план в столе, при разрезах — высоты разрезов мимо колен, дырок и
    царг обеих труб. Если пара не встала, а разрезы включены, мелодия
    собирается выше (на два куска стола, на три и дальше): вход выше,
    обеим трубам нужно меньше прямых, план уже. Возвращает PairPlan.
    Если ноты дрона нет, поднимает ParamsError; если дрон не встал —
    LayoutError с причиной первой попытки.
    """
    if not params.drone_note:
        raise ParamsError(["Нота дрона не задана."])
    melody_set = melody_params(params)
    drone_set = drone_params(params)
    tuning = resolve_tuning(drone_set)
    trim = resolve_trim(drone_set, tuning)
    first_reasons: list[str] | None = None
    for stack in _melody_stacks(params):
        try:
            melody = plan_design(melody_set, stack)
        except (LayoutError, HoleError):
            if stack is None:
                raise
            continue
        if stack is not None and melody.coil.height_with_head_mm <= params.max_height_mm:
            continue
        plan, reasons = _plan_with_melody(params, melody, drone_set, tuning, trim)
        if plan is not None:
            return plan
        if first_reasons is None:
            first_reasons = reasons
    raise LayoutError(first_reasons or ["Пара мелодии и дрона не сложилась."])


def _melody_stacks(params: TubeParams) -> list[float | None]:
    """Пределы собранной высоты мелодии, от обычного к высоким.

    Принимает параметры. Без разрезов — только обычный расчёт (None).
    С разрезами — ещё стол плюс (стол − папа стыка) на каждый лишний кусок,
    до MAX_PRINT_PIECES кусков. Возвращает список.
    """
    stacks: list[float | None] = [None]
    unique = params.max_height_mm - PRINT_PLUG_MM
    if params.print_splits and unique > 1e-6:
        stacks.extend(
            params.max_height_mm + pieces * unique for pieces in range(1, MAX_PRINT_PIECES)
        )
    return stacks


def _plan_with_melody(
    params: TubeParams,
    melody: DesignPlan,
    drone_set: TubeParams,
    tuning: Tuning,
    trim: TrimPlan | None,
) -> tuple[PairPlan | None, list[str]]:
    """Ставит дрон к готовой мелодии.

    Принимает общие параметры, план мелодии, параметры, строй и подстройку
    дрона. Перебирает укладки дрона от меньшего числа прямых. Возвращает
    (PairPlan или None, причины отказа).
    """
    melody_set = melody.params
    coils, reasons = drone_coils_for_inlet(
        drone_set, tuning.body_length_mm, melody.coil.inlet_z_mm, trim
    )
    placed_any = False
    for coil in coils:
        try:
            check_channel_clearance(build_centerline(coil, drone_set.joint_length_mm), drone_set)
        except LayoutError:
            continue
        placement = place_pair(
            melody.coil, melody.placed_holes, coil, params, DUAL_INLET_SPACING_MM
        )
        if placement is None:
            continue
        placed_any = True
        spans = column_spans(placement.melody) + column_spans(placement.drone)
        bands = keep_out_bands(
            placement.melody,
            melody_set,
            holes=tuple((hole.spec.s_mm, hole.spec.diameter_mm) for hole in melody.placed_holes),
            bottom_keep_mm=bottom_socket_mm(melody.trim, melody.slider),
        ) + keep_out_bands(
            placement.drone, drone_set, bottom_keep_mm=bottom_socket_mm(trim, None)
        )
        height = max(placement.melody.height_mm, placement.drone.height_mm)
        if params.print_splits:
            try:
                cut_heights(0.0, height, params.max_height_mm, PRINT_PLUG_MM, bands)
            except PrintCutError:
                continue
        melody_line = build_centerline(placement.melody, melody_set.joint_length_mm)
        drone_line = build_centerline(placement.drone, drone_set.joint_length_mm)
        return PairPlan(
            params=params,
            melody=replace(
                melody,
                coil=placement.melody,
                centerline=melody_line,
                placed_holes=placement.melody_holes,
            ),
            drone=DesignPlan(
                params=drone_set,
                tuning=tuning,
                coil=placement.drone,
                centerline=drone_line,
                channel_wall_mm=check_channel_clearance(drone_line, drone_set),
                trim=trim,
                slider=None,
                holes=None,
                placed_holes=(),
            ),
            placement=placement,
            spans=spans,
            bands=bands,
            height_mm=height,
        ), []
    if not reasons:
        if not placed_any:
            reasons.append(
                "Дрон не встаёт рядом с мелодией на шаге входов 48 мм: вязанки "
                "пересекаются, дрон закрывает дырки или общий план не влезает "
                f"в стол {_format_mm(params.max_width_mm)}×{_format_mm(params.max_depth_mm)} мм. "
                "Увеличьте ширину и глубину"
                + (" или включите разрезы на печать." if not params.print_splits else ".")
            )
        else:
            reasons.append(
                "Пару не разрезать на куски стола: колени, дырки и царги двух "
                "труб перекрывают все высоты разреза. Поднимите высоту печати."
            )
    return None, reasons


def build_voice_pair(params: TubeParams) -> VoicePair:
    """Строит одну деталь мелодии и дрона и вставки к ней.

    Принимает параметры с нотой дрона. Раскладку берёт из plan_voice_pair,
    тело — одно на обе трубы с общим цоколем. Трубки подстройки и слайдер
    мелодии — отдельные детали. При разрезах режет общую деталь целиком.
    Возвращает VoicePair. Ошибки расчёта, укладки и тела пробрасывает.
    """
    plan = plan_voice_pair(params)
    melody, drone = plan.melody, plan.drone
    skip = skip_turns_after_straights(melody.slider, melody.coil.straight_count)
    voices = (
        BodyVoice(melody.centerline, melody.params, melody.placed_holes, skip),
        BodyVoice(drone.centerline, drone.params),
    )
    points = melody.coil.columns + drone.coil.columns
    base = max(melody.coil.base_height_mm, drone.coil.base_height_mm)
    body = build_joined_body(voices, points, base)
    slider_body = (
        build_slider_body(
            melody.slider,
            melody.coil.turn_radius_mm,
            melody.coil.columns,
            melody.coil.base_height_mm,
        )
        if melody.slider is not None
        else None
    )
    body_slices: tuple[PrintSlice, ...] = ()
    if params.print_splits:
        try:
            body_slices = split_solid_for_print(
                body.solid, params, points, stem="корпус", spans=plan.spans, bands=plan.bands
            )
        except Exception as exc:
            raise BodyError(f"Разрезы пары не построились: {exc}") from exc
        if len(body_slices) <= 1:
            body_slices = ()
    distance = plan.placement.min_distance_mm
    return VoicePair(
        params=params,
        melody=melody,
        drone=drone,
        body=body,
        melody_tuner=build_tuner_body(melody.trim) if melody.trim is not None else None,
        drone_tuner=build_tuner_body(drone.trim) if drone.trim is not None else None,
        slider_body=slider_body,
        body_slices=body_slices,
        slider_slices=slider_print_slices(params, melody.coil, melody.slider, slider_body),
        inlet_spacing_mm=DUAL_INLET_SPACING_MM,
        coupling=CouplingCheck(
            inlet_spacing_mm=DUAL_INLET_SPACING_MM,
            min_column_distance_mm=distance,
            wall_clearance_mm=distance - params.outer_diameter_mm,
            channels_independent=True,
            supply_chamber=False,
        ),
        width_mm=plan.placement.width_mm,
        depth_mm=plan.placement.depth_mm,
        height_mm=plan.height_mm,
    )


def melody_params(params: TubeParams) -> TubeParams:
    """Параметры мелодии без полей дрона.

    Принимает общий набор. Снимает ноту и подстройку дрона, чтобы расчёт
    одной трубы их не видел. Возвращает TubeParams мелодии.
    """
    return replace(params, drone_note=None, drone_trim_semitones=0)


def drone_params(params: TubeParams) -> TubeParams:
    """Параметры дрона: своя нота и подстройка, без дырок и слайдера.

    Принимает общий набор с нотой дрона. Цель дрона всегда нота, длина
    корпуса мелодии не переносится. Отверстия и слайдер мелодии гасятся:
    дрон держит свой строй трубкой подстройки. Возвращает TubeParams дрона.
    """
    if not params.drone_note:
        raise ParamsError(["Нота дрона не задана."])
    return replace(
        params,
        note=params.drone_note,
        body_length_mm=None,
        hole_count=0,
        slider_kind="",
        slider_semitones=0,
        slider_pairs=0,
        trim_semitones=params.drone_trim_semitones,
        drone_note=None,
        drone_trim_semitones=0,
    )


def preview_instrument(result: Design | VoicePair):
    """Солид для окна: одна труба или пара одной деталью.

    Принимает Design или VoicePair. Для пары показывает общую деталь,
    справа — трубки подстройки и слайдер, если они есть. Возвращает
    фигуру CadQuery.
    """
    if isinstance(result, VoicePair):
        return preview_pair(result)
    return preview_solid(result)


def preview_pair(pair: VoicePair):
    """Предпросмотр пары: общая деталь, вставки сбоку.

    Принимает VoicePair. Трубки подстройки и слайдер ставит справа от
    габарита детали с зазором 10 мм. Возвращает фигуру CadQuery.
    """
    shape = pair.body.solid.val()
    extras = [
        part.solid.val()
        for part in (pair.slider_body, pair.melody_tuner, pair.drone_tuner)
        if part is not None
    ]
    gap_mm = 10.0
    cursor = shape.BoundingBox().xmax + gap_mm
    for extra in extras:
        moved = extra.translate((cursor - extra.BoundingBox().xmin, 0.0, 0.0))
        shape = shape.fuse(moved)
        cursor = moved.BoundingBox().xmax + gap_mm
    return shape


def inlet_distance_mm(pair: VoicePair | PairPlan) -> float:
    """Расстояние между осями входов в плане, мм.

    Принимает VoicePair или PairPlan. Берёт первые прямые мелодии и дрона
    — это входы. Возвращает миллиметры.
    """
    return math.dist(pair.melody.coil.columns[0], pair.drone.coil.columns[0])


def export_pair(pair: VoicePair, step_path: str | Path, stl_path: str | Path) -> list[Path]:
    """Пишет общую деталь пары, её куски и вставки в STEP и STL.

    Принимает VoicePair и пути STEP/STL детали. Если включены разрезы и
    деталь выше стола, вместо целой пишет куски «-корпус-N». Трубка
    подстройки мелодии — «-подстройка», дрона — «-подстройка-дрон»,
    слайдер — «-слайдер» или куски «-слайдер-N». Возвращает список
    записанных путей. Если запись не удалась, поднимает BodyError.
    """
    step = Path(step_path)
    stl = Path(stl_path)
    saved: list[Path] = []
    saved.extend(_export_part(pair.body, pair.body_slices, step, stl, ""))
    for part, suffix in ((pair.melody_tuner, "-подстройка"), (pair.drone_tuner, "-подстройка-дрон")):
        if part is not None:
            saved.extend(_export_part(part, (), step, stl, suffix))
    if pair.slider_body is not None:
        saved.extend(_export_part(pair.slider_body, pair.slider_slices, step, stl, "-слайдер"))
    return saved


def _export_part(
    body: TubeBody,
    slices: tuple[PrintSlice, ...],
    step: Path,
    stl: Path,
    suffix: str,
) -> list[Path]:
    """Пишет одну деталь или её куски рядом с основным файлом.

    Принимает деталь, её куски (может быть пусто), основные пути и суффикс
    имени. Куски получают суффикс по своему имени. Возвращает пути.
    """
    saved: list[Path] = []
    if slices:
        for piece in slices:
            piece_step = step.with_name(f"{step.stem}-{piece.name}{step.suffix}")
            piece_stl = stl.with_name(f"{stl.stem}-{piece.name}.stl")
            export_tube_body(replace(body, solid=piece.solid), piece_step, piece_stl)
            saved.extend((piece_step, piece_stl))
        return saved
    part_step = step.with_name(f"{step.stem}{suffix}{step.suffix}")
    part_stl = stl.with_name(f"{stl.stem}{suffix}.stl")
    export_tube_body(body, part_step, part_stl)
    return [part_step, part_stl]


def _format_mm(value: float) -> str:
    """Миллиметры для текста: один знак, запятая, без хвостовых нулей.

    Принимает число. Возвращает строку.
    """
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
