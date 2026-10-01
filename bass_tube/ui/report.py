"""Текст отчёта по уже посчитанной трубе для окна.

Язык строк — текущий язык интерфейса. Числа: запятая по-русски,
точка по-английски.
"""

from __future__ import annotations

import math

from bass_tube.design import Design, DesignPlan
from bass_tube.layout.fingers import FINGER_COMFORT_MM, HAND_GAP_MM
from bass_tube.layout.holes import finger_spacings
from bass_tube.pair import VoicePair
from bass_tube.ui.form import format_mm_ui
from bass_tube.ui.i18n import current_language, scale_choice_label, slider_choice_label, t


def format_design_report(design: Design | DesignPlan, *, splits: bool = True) -> str:
    """Собирает читаемый отчёт по строю и укладке.

    Принимает Design или DesignPlan и флаг splits: писать ли строку про
    разрезы этой трубы (у пары разрезы общие, их пишет отчёт пары). Пишет ноту, частоту, длины, поправки (с переходником,
    если он есть), укладку, прямые, радиус колена (и что он затянут под
    дырки, если отличается от окна), цоколь, габарит и самую тонкую стенку
    между каналами соседних колен.     Если есть подстройка — ход и царгу. Если есть слайдер — схему, зазор
    вокруг царги, ход, стопы полутонов и высоту на полном ходу (это размер
    игры, не печати). Если есть отверстия — лад,
    прогноз аппликатур в центах, прямую каждой дырки и расстояния между
    соседними дырками по стенке — насколько тянуться пальцам. Пометку калибровки
    головки берёт из строя. Возвращает многострочный текст на текущем языке окна.
    """
    tuning = design.tuning
    coil = design.coil
    params = design.params
    mm = format_mm_ui
    if params.note is not None:
        goal = t("report.note_goal").format(note=tuning.note, hz=format_hz(tuning.frequency_hz))
    else:
        goal = t("report.length_goal").format(
            mm=mm(tuning.body_length_mm),
            note=tuning.note,
            hz=format_hz(tuning.frequency_hz),
            cents=format_cents(tuning.cents),
        )
    corrections = t("report.corrections").format(
        head=mm(tuning.delta_head_mm),
        out=mm(tuning.delta_out_mm),
        bends=mm(tuning.delta_bends_mm),
    )
    if params.has_transition:
        corrections += t("report.transition_extra").format(mm=mm(tuning.delta_transition_mm))
    lengths = sorted({round(value, 2) for value in coil.straight_lengths_mm})
    straights = t("report.straights").format(
        count=coil.straight_count, mm=mm(coil.regular_straight_mm)
    )
    if len(lengths) > 1:
        straights += t("report.straights_range").format(low=mm(lengths[0]), high=mm(lengths[-1]))
    outlet = t("report.outlet_bottom") if coil.outlet_at_bottom else t("report.outlet_top")
    turns = t("report.turns").format(count=coil.turn_count, mm=mm(coil.turn_radius_mm))
    if abs(coil.turn_radius_mm - params.turn_radius_mm) > 1e-6:
        turns += t("report.turns_tightened").format(mm=mm(params.turn_radius_mm))
    calibrated = (
        t("report.calibrated") if tuning.head_calibrated else t("report.uncalibrated")
    )
    lines = [
        goal,
        t("report.effective").format(mm=mm(tuning.effective_length_mm)),
        t("report.body").format(mm=mm(tuning.body_length_mm)),
        calibrated,
        corrections,
        "",
        t("report.layout").format(outlet=outlet),
        straights,
        turns,
        t("report.axis").format(axis=mm(coil.axis_length_mm), base=mm(coil.base_height_mm)),
        t("report.envelope").format(
            width=mm(coil.width_mm),
            depth=mm(coil.depth_mm),
            height=mm(coil.height_mm),
            head=mm(coil.height_with_head_mm),
        ),
        _section_line(design),
    ]
    if design.trim is not None:
        plan = design.trim
        lines.append(
            t("report.trim").format(
                steps=params.trim_semitones,
                upper=plan.upper_note,
                lower=plan.lower_note,
                travel=mm(plan.extra_length_mm),
                tenon=mm(plan.tenon_length_mm),
            )
        )
    if design.slider is not None:
        plan = design.slider
        extended = design.coil.height_with_head_mm + plan.travel_mm
        extra = t("report.slider_pairs").format(pairs=plan.pairs) if plan.pairs else ""
        lines.append("")
        lines.append(
            t("report.slider").format(
                kind=slider_choice_label(plan.kind),
                steps=params.slider_semitones,
                upper=plan.upper_note,
                lower=plan.lower_note,
                q=plan.q,
                delta=mm(plan.extra_length_mm),
                travel=mm(plan.travel_mm),
                gap=mm(plan.radial_clearance_mm),
                tenon=mm(plan.tenon_length_mm),
            )
            + extra
        )
        lines.append(t("report.slider_height").format(mm=mm(extended)))
        for stop in plan.stops:
            lines.append(
                t("report.slider_stop").format(
                    note=stop.note,
                    steps=stop.semitones,
                    delta=mm(stop.extra_length_mm),
                    travel=mm(stop.travel_mm),
                )
            )
    if splits and params.print_splits and isinstance(design, Design):
        body_n = len(design.body_slices)
        slide_n = len(design.slider_slices)
        if body_n or slide_n:
            parts = []
            if body_n:
                parts.append(t("report.splits_body").format(n=body_n))
            if slide_n:
                parts.append(t("report.splits_slider").format(n=slide_n))
            lines.append(t("report.splits").format(parts=", ".join(parts)))
        else:
            lines.append(t("report.splits_fit"))
    if design.holes is not None:
        lines.append("")
        lines.append(
            t("report.holes").format(
                count=len(design.holes.holes),
                scale=scale_choice_label(design.holes.scale_id),
                tonic=design.holes.tonic,
            )
        )
        for fingering in design.holes.fingerings:
            state = (
                t("report.closed")
                if fingering.open_count == 0
                else t("report.open_count").format(n=fingering.open_count)
            )
            lines.append(
                t("report.fingering").format(
                    note=fingering.note,
                    hz=format_hz(fingering.predicted_hz),
                    cents=format_cents(fingering.cents),
                    state=state,
                )
            )
        for hole in design.placed_holes:
            lines.append(
                t("report.hole").format(
                    note=hole.spec.note,
                    s=mm(hole.spec.s_mm),
                    column=hole.column + 1,
                    diameter=mm(hole.spec.diameter_mm),
                )
            )
        if len(design.placed_holes) > 1:
            spacings = finger_spacings(design.centerline, params, design.placed_holes)
            lines.append(
                t("report.fingers").format(
                    spacings=", ".join(mm(value) for value in spacings),
                    comfort=mm(FINGER_COMFORT_MM),
                    hands=mm(HAND_GAP_MM),
                )
            )
    if math.isfinite(design.channel_wall_mm):
        lines.append(t("report.wall").format(mm=mm(design.channel_wall_mm)))
    return "\n".join(lines)


def format_pair_report(pair: VoicePair) -> str:
    """Собирает отчёт по паре мелодия + дрон одной деталью.

    Принимает VoicePair. Сначала пишет, что трубы — одна деталь на общем
    цоколе, шаг осей входов на одной высоте, что насадка не моделируется
    и каналы не соединены, зазор между трубами, габарит и разрезы.
    Затем отчёт мелодии и отчёт дрона. Возвращает многострочный текст
    на текущем языке окна.
    """
    coupling = pair.coupling
    inlet_z = pair.melody.coil.inlet_z_mm
    mm = format_mm_ui
    head = [
        t("report.pair.intro"),
        t("report.pair.inlets").format(
            spacing=mm(pair.inlet_spacing_mm), height=mm(inlet_z)
        ),
        t("report.pair.no_chamber"),
        t("report.pair.gap").format(
            gap=mm(coupling.wall_clearance_mm),
            min_dist=mm(coupling.min_column_distance_mm),
        ),
        t("report.pair.envelope").format(
            width=mm(pair.width_mm),
            depth=mm(pair.depth_mm),
            height=mm(pair.height_mm),
        ),
    ]
    if pair.params.print_splits:
        if pair.body_slices:
            head.append(t("report.pair.splits").format(n=len(pair.body_slices)))
        else:
            head.append(t("report.pair.splits_fit"))
    head.extend(
        [
            "",
            t("report.pair.melody"),
            format_design_report(pair.melody, splits=False),
            "",
            t("report.pair.drone"),
            format_design_report(pair.drone, splits=False),
        ]
    )
    return "\n".join(head)


def _section_line(design: Design) -> str:
    """Строка о сечении трубы и конце под модуль.

    Принимает Design. Без переходника пишет один канал, с переходником —
    канал трубы, канал конца и длину конуса. Возвращает строку на текущем языке.
    """
    params = design.params
    mm = format_mm_ui
    body = t("report.tube").format(
        bore=mm(params.bore_diameter_mm), outer=mm(params.outer_diameter_mm)
    )
    if not params.has_transition:
        return body
    return t("report.tube_transition").format(
        body=body,
        seat=mm(params.seat_outer_diameter_mm),
        seat_bore=mm(params.seat_bore_diameter_mm),
        transition=mm(params.transition_length_mm),
    )


def format_hz(value: float) -> str:
    """Герцы для отчёта.

    Принимает частоту. Русский — запятая и два знака, английский — точка.
    Возвращает строку.
    """
    text = f"{value:.2f}"
    if current_language() == "ru":
        return text.replace(".", ",")
    return text


def format_cents(value: float) -> str:
    """Центы со знаком для прогноза по длине.

    Принимает отклонение. Русский — запятая и один знак после неё,
    английский — точка. Положительное число начинается с плюса.
    Возвращает строку.
    """
    text = f"{value:+.1f}"
    if current_language() == "ru":
        return text.replace(".", ",")
    return text
