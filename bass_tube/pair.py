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
from bass_tube.body.tube import (
    BodyError,
    BodyVoice,
    TubeBody,
    build_joined_body,
    export_tube_body,
    export_whistle_head,
)
from bass_tube.body.tuner import build_tuner_body
from bass_tube.constants import (
    DEFAULT_SOURCE,
    DEFAULT_TERMINATION,
    DUAL_INLET_SPACING_MM,
    MEMBRANE_MOUTHPIECE_SEAT_MM,
    PRINT_PLUG_MM,
    SOURCE_MEMBRANE,
    TERMINATION_STOPPED,
    WHISTLE_HEAD_AXIAL,
)
from bass_tube.design import (
    Design,
    DesignPlan,
    _build_whistle_head,
    build_design,
    plan_design,
    preview_solid,
    slider_print_slices,
    whistle_head_solids,
)
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
from bass_tube.sources import export_membrane_sources


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
    height_mm — верх общей детали. drone_inlet_offset_mm — насколько вход
    дрона выше входа мелодии: ноль, кроме пары «мембрана + осевой свисток»,
    где мундштук должен сесть на оба модуля разом.
    """

    params: TubeParams
    melody: DesignPlan
    drone: DesignPlan
    placement: PairPlacement
    spans: tuple[ColumnSpan, ...]
    bands: tuple[tuple[float, float], ...]
    height_mm: float
    drone_inlet_offset_mm: float = 0.0


@dataclass(eq=False)
class VoicePair:
    """Собранная пара: одна деталь с двумя каналами и отдельные вставки.

    params — исходный набор. melody и drone — планы труб на местах.
    body — общая деталь. melody_tuner и drone_tuner — трубки подстройки,
    slider_body — деталь слайдера мелодии. body_slices и slider_slices —
    куски на печать, если включены разрезы. width_mm, depth_mm, height_mm —
    габарит общей детали. coupling — что каналы не слиты.
    melody_whistle_head и drone_whistle_head — печатные головки свистковых
    голосов (None у мембраны), melody_whistle_report и drone_whistle_report —
    их расчётные паспорта с допущениями.
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
    melody_whistle_head: object | None = None
    drone_whistle_head: object | None = None
    melody_whistle_report: dict | None = None
    drone_whistle_report: dict | None = None
    drone_inlet_offset_mm: float = 0.0


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
    # Заглушённый конец дрона печатается глухим: ось длиннее воздушного
    # столба на дно заглушки, как у одиночной трубы (см. plan_design).
    drone_layout_mm = tuning.body_length_mm
    if drone_set.termination == TERMINATION_STOPPED:
        drone_layout_mm += drone_set.floor_mm
    offset = drone_inlet_offset_mm(melody_set, drone_set)
    drone_inlet_z = melody.coil.inlet_z_mm + offset
    if offset > 0.0 and not params.print_splits and drone_inlet_z > params.max_height_mm + 1e-9:
        return None, [
            f"Мембранный дрон под общий мундштук поднимается на {_format_mm(offset)} мм "
            f"над входом свистка и выходит за высоту печати "
            f"{_format_mm(params.max_height_mm)} мм. Включите разрезы на печать "
            "или поднимите высоту."
        ]
    coils, reasons = drone_coils_for_inlet(
        drone_set, drone_layout_mm, drone_inlet_z, trim
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
            drone_inlet_offset_mm=offset,
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
    melody_head, melody_report = _build_whistle_head(melody.params, melody.tuning)
    drone_head, drone_report = _build_whistle_head(drone.params, drone.tuning)
    return VoicePair(
        params=params,
        melody=melody,
        drone=drone,
        body=body,
        melody_whistle_head=melody_head,
        drone_whistle_head=drone_head,
        melody_whistle_report=melody_report,
        drone_whistle_report=drone_report,
        drone_inlet_offset_mm=plan.drone_inlet_offset_mm,
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
    return replace(
        params,
        drone_note=None,
        drone_trim_semitones=0,
        drone_source=DEFAULT_SOURCE,
        drone_termination=DEFAULT_TERMINATION,
        **_whistle_reset(params.source),
    )


def drone_params(params: TubeParams) -> TubeParams:
    """Параметры дрона: своя нота, источник, конец и подстройка.

    Принимает общий набор с нотой дрона. Цель дрона всегда нота, длина
    корпуса мелодии не переносится. Отверстия и слайдер мелодии гасятся:
    дрон держит свой строй трубкой подстройки. Источник и дальний конец
    дрона становятся его собственными source и termination: свистковый
    дрон считается свистковым строем, заглушённый печатается глухим.
    Возвращает TubeParams дрона.
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
        source=params.drone_source,
        termination=params.drone_termination,
        drone_note=None,
        drone_trim_semitones=0,
        drone_source=DEFAULT_SOURCE,
        drone_termination=DEFAULT_TERMINATION,
        **_whistle_reset(params.drone_source),
    )


def _whistle_reset(source: str) -> dict:
    """Свистковые поля голоса-мембраны в паре — по умолчанию.

    Принимает источник голоса. Свистковая геометрия и поправка окна у пары
    общие для свисткового голоса; мембранному голосу они не нужны, и его
    собственная проверка их бы отвергла. Возвращает поля для replace:
    пустой словарь у свистка.
    """
    if source != SOURCE_MEMBRANE:
        return {}
    from bass_tube.constants import (
        DEFAULT_MOUTH_CORRECTION_MM,
        DEFAULT_WHISTLE_BLOW_PRESSURE_PA,
        DEFAULT_WHISTLE_EDGE_MM,
        DEFAULT_WHISTLE_HEAD_KIND,
        DEFAULT_WHISTLE_LABIUM_OFFSET_MM,
        DEFAULT_WHISTLE_LID_KIT_MM,
        DEFAULT_WHISTLE_SOCKET_CLEARANCE_MM,
        DEFAULT_WHISTLE_WINDOW_AZIMUTH_DEG,
        DEFAULT_WHISTLE_WINDWAY_LENGTH_MM,
        DEFAULT_WHISTLE_WINDWAY_WIDTH_MM,
    )

    return dict(
        mouth_correction_mm=DEFAULT_MOUTH_CORRECTION_MM,
        whistle_windway_height_mm=None,
        whistle_windway_width_mm=DEFAULT_WHISTLE_WINDWAY_WIDTH_MM,
        whistle_windway_length_mm=DEFAULT_WHISTLE_WINDWAY_LENGTH_MM,
        whistle_cutup_mm=None,
        whistle_edge_thickness_mm=DEFAULT_WHISTLE_EDGE_MM,
        whistle_labium_offset_mm=DEFAULT_WHISTLE_LABIUM_OFFSET_MM,
        whistle_head_kind=DEFAULT_WHISTLE_HEAD_KIND,
        whistle_window_azimuth_deg=DEFAULT_WHISTLE_WINDOW_AZIMUTH_DEG,
        whistle_socket_clearance_mm=DEFAULT_WHISTLE_SOCKET_CLEARANCE_MM,
        whistle_lid_kit_mm=DEFAULT_WHISTLE_LID_KIT_MM,
        whistle_blow_pressure_pa=DEFAULT_WHISTLE_BLOW_PRESSURE_PA,
    )


def mouthpiece_seat_mm(voice: TubeParams) -> float | None:
    """Где трубка двойного мундштука упирается в модуль голоса, над торцом трубы.

    Принимает параметры одного голоса. У мембраны — торец трубки модуля
    (MEMBRANE_MOUTHPIECE_SEAT_MM), у осевого свистка — сплошной торец
    головки. Боковой свисток в мундштук не садится: None.
    Возвращает миллиметры или None.
    """
    if voice.source == SOURCE_MEMBRANE:
        return MEMBRANE_MOUTHPIECE_SEAT_MM
    if voice.whistle_head_kind == WHISTLE_HEAD_AXIAL:
        from bass_tube.whistle.axial_head import axial_head_for_tube

        return axial_head_for_tube(voice).top_z_mm
    return None


def drone_inlet_offset_mm(melody: TubeParams, drone: TubeParams) -> float:
    """Насколько вход дрона выше входа мелодии, чтобы мундштук сел на оба.

    Принимает параметры мелодии и дрона. Если оба голоса садятся в двойной
    мундштук, но модули разной высоты (мембрана и осевой свисток), вход
    низкого модуля поднимается, высокого — опускается на разницу. Иначе
    входы на одной высоте, как у пары мембран. Возвращает миллиметры:
    плюс — дрон выше, минус — ниже.
    """
    melody_seat = mouthpiece_seat_mm(melody)
    drone_seat = mouthpiece_seat_mm(drone)
    if melody_seat is None or drone_seat is None:
        return 0.0
    return melody_seat - drone_seat


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
    saved.extend(export_membrane_sources(pair.melody.params, step))
    saved.extend(export_membrane_sources(pair.drone.params, step, "-дрон"))
    for head, suffix in (
        (pair.melody_whistle_head, "-свисток"),
        (pair.drone_whistle_head, "-свисток-дрон"),
    ):
        if head is None:
            continue
        paths = (
            step.with_name(f"{step.stem}{suffix}{step.suffix}"),
            stl.with_name(f"{stl.stem}{suffix}.stl"),
            step.with_name(f"{step.stem}{suffix}-крышка{step.suffix}"),
            stl.with_name(f"{stl.stem}{suffix}-крышка.stl"),
        )
        plan = pair.melody if head is pair.melody_whistle_head else pair.drone
        saved.extend(export_whistle_head(head, *paths, kit_mm=plan.params.whistle_lid_kit_mm))
    return saved


def whistle_heads_at_inlets(pair: VoicePair):
    """Головки свистковых голосов на входах общей детали, для сборки.

    Принимает VoicePair. Ставит каждую головку на вход своей трубы:
    гнездо обнимает конец, детали не сливаются. Возвращает Compound или
    None, если свистковых голосов нет.
    """
    import cadquery as cq

    solids = []
    for head, plan in (
        (pair.melody_whistle_head, pair.melody),
        (pair.drone_whistle_head, pair.drone),
    ):
        if head is None:
            continue
        inlet = plan.centerline.sample(0.0).point
        solids.extend(
            part.translate((inlet.x, inlet.y, inlet.z)) for part in whistle_head_solids(head)
        )
    if not solids:
        return None
    return cq.Compound.makeCompound(solids)


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
