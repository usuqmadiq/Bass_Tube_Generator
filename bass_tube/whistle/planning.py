"""Расчётный паспорт прототипа; акустическая калибровка ещё не выполнена.

Головка в 1D-модели заменяется цилиндром длиной nominal_head_length_mm.
Это геометрический ориентир, а не извлечённый из CAD импеданс окна.
"""

from __future__ import annotations

from dataclasses import asdict
import math

from bass_tube.whistle.acoustics import (
    BoreSection,
    WhistleAcousticsError,
    estimate_airflow,
    first_resonance_hz,
    sections_for_tube,
    straight_length_for_frequency_mm,
)
from bass_tube.whistle.params import WhistleHeadParams


SOURCES = {
    "upstream": "https://github.com/usuqmadiq/Bass_Tube_Generator/tree/cd544a93c104d5b4c2c60b5792e91d816ca5878c",
    "open_closed": "https://www.phys.unsw.edu.au/jw/flutes.v.clarinets.html",
    "window_impedance": "https://doi.org/10.3813/AAA.919037",
    "jet_scaling": "https://www.dalembert.upmc.fr/lelam/Publications/Articles/FamilleAAABlancFabre2010.pdf",
    "pair_synchronization": "https://arxiv.org/pdf/physics/0506094",
    "printed_bass_heads": "https://doi.org/10.1177/20592043231210653",
}


def uniform_body_length_mm(
    target_hz: float,
    head: WhistleHeadParams,
    *,
    termination: str = "open",
    mouth_correction_mm: float = 0.0,
    c: float = 343.0,
) -> float:
    """Длина новой ровной трубы до её торца, включая штатную посадку.

Труба и neck головки имеют один диаметр. Участок посадки 8 мм входит
в полученную длину корпуса и не прибавляется повторно.
"""
    end_correction = 0.3 * head.tube_bore_diameter_mm if termination == "open" else 0.0
    full = straight_length_for_frequency_mm(
        target_hz, termination=termination,
        mouth_correction_mm=mouth_correction_mm,
        end_correction_mm=end_correction, c=c,
    )
    body = full - head.nominal_head_length_mm
    if body <= head.socket_depth_mm:
        raise WhistleAcousticsError("Расчётный корпус короче посадки головки.")
    return body


def plan_uniform_whistle(
    body_length_mm: float,
    head: WhistleHeadParams,
    *,
    termination: str = "open",
    pressure_pa: float = 100.0,
    mouth_correction_mm: float = 0.0,
    c: float = 343.0,
    velocity_coefficient: float = 0.8,
    mean_to_center_ratio: float = 1.0,
) -> dict:
    """Паспорт ровного канала без отверстий, изгибов и слайдера."""
    if not math.isfinite(body_length_mm) or body_length_mm <= head.socket_depth_mm:
        raise WhistleAcousticsError("Длина корпуса должна быть больше глубины посадки.")
    return _report(
        (BoreSection(body_length_mm, head.tube_bore_diameter_mm),),
        head, termination, pressure_pa, mouth_correction_mm,
        0.3 * head.tube_bore_diameter_mm if termination == "open" else 0.0,
        c, velocity_coefficient, mean_to_center_ratio,
    )


def plan_existing_tube(
    tube,
    head: WhistleHeadParams | None = None,
    *,
    body_length_mm: float | None = None,
    termination: str = "open",
    pressure_pa: float = 100.0,
    mouth_correction_mm: float = 0.0,
    velocity_coefficient: float = 0.8,
    mean_to_center_ratio: float = 1.0,
) -> dict:
    """Читает существующий TubeParams и меняет только акустическую модель.

Если передана нота старого генератора, она определяет физическую длину
уже рассчитанной мембранной трубы. Новая частота считается независимо.
Отверстия, выдвижные секции и их поправки этот прототип не моделирует.
"""
    from bass_tube.acoustics.tuning import resolve_tuning

    if head is None:
        head = WhistleHeadParams(
            tube_outer_diameter_mm=tube.seat_outer_diameter_mm,
            tube_bore_diameter_mm=tube.seat_bore_diameter_mm,
            socket_depth_mm=tube.seat_length_mm,
        )
    if not math.isclose(head.tube_outer_diameter_mm, tube.seat_outer_diameter_mm, abs_tol=1e-6):
        raise WhistleAcousticsError("Наружный диаметр посадки трубы не совпадает с головкой.")
    if not math.isclose(head.tube_bore_diameter_mm, tube.seat_bore_diameter_mm, abs_tol=1e-6):
        raise WhistleAcousticsError("Канал торца трубы не совпадает с каналом головки.")
    if head.socket_depth_mm > tube.seat_length_mm + 1e-6:
        raise WhistleAcousticsError("Головка сядет на переходник: глубина больше прямой посадки.")
    length = resolve_tuning(tube).body_length_mm if body_length_mm is None else body_length_mm
    sections = sections_for_tube(tube, length)
    report = _report(
        sections, head, termination, pressure_pa, mouth_correction_mm,
        tube.delta_out_mm if termination == "open" else 0.0,
        tube.speed_of_sound_m_s, velocity_coefficient, mean_to_center_ratio,
    )
    report["geometry_source"] = "Existing TubeParams; only the straight/stepped axial bore profile is retained."
    report["omitted_old_corrections_mm"] = {
        "membrane_head": tube.delta_head_mm,
        "bends": tube.delta_bends_mm,
    }
    return report


def _report(sections, head, termination, pressure, mouth, outlet, c, coefficient, ratio):
    neck = BoreSection(head.nominal_head_length_mm, head.tube_bore_diameter_mm)
    complete = (neck, *sections)
    frequency = first_resonance_hz(
        complete, termination=termination, mouth_correction_mm=mouth,
        end_correction_mm=outlet, c=c,
    )
    def airflow(p):
        return estimate_airflow(
            p, head.windway_width_mm, head.windway_height_mm,
            frequency_hz=frequency, cutup_mm=head.window_length_mm,
            velocity_coefficient=coefficient, mean_to_center_ratio=ratio,
        )

    air = airflow(pressure)
    warnings = [
        "EXPERIMENTAL: no physical print, blowing test, measured pitch, or SPL validation has been performed.",
        "The reported frequency is a passive lossless resonance, not a predicted stable sounding frequency.",
        "The CAD head cavity is replaced by a cylinder of length nominal_head_length_mm; this approximation is uncalibrated.",
        "mouth_correction_mm is an input equivalent inertance, not computed from window dimensions. Zero means omitted, not measured zero.",
        "Airflow uses an assumed velocity coefficient and mean/center velocity ratio; windway friction and source pressure droop are not solved.",
        "Finger holes, bend losses, joint leaks, reed mechanics, register selection, loudness, and mutual coupling are not solved.",
        "The mouth-correction sweep is a set of illustrative scenarios, not a confidence interval or an experimentally established range.",
    ]
    if termination == "stopped":
        warnings.append("STOPPED requires an airtight distal closure at the specified end plane; no outlet end correction applies. A closure inserted into the bore shortens the air column.")
    if head.window_length_mm / head.windway_height_mm > 15.0:
        warnings.append("Long thin jet: W/h > 15; this diagnostic does not validate jet amplification at the labium.")
    if air.theta is not None and not 7.0 <= air.theta <= 17.0:
        warnings.append("Theta falls outside 7..17 observed in one recorder study. This is a diagnostic, not a universal onset or register threshold.")

    return {
        "schema_version": 1,
        "status": "experimental_unvoiced",
        "head_calibrated": False,
        "termination": termination,
        "speed_of_sound_m_s": c,
        "body_length_mm": sum(section.length_mm for section in sections),
        "neck_reference_length_mm": head.nominal_head_length_mm,
        "mouth_correction_mm": mouth,
        "outlet_correction_mm": outlet,
        "passive_frequency_hz": frequency,
        "head": asdict(head),
        "bore_sections": [asdict(s) for s in complete],
        "air_estimate": asdict(air),
        "window_to_jet_height_ratio": head.window_length_mm / head.windway_height_mm,
        "mouth_correction_scenarios": [
            {"mouth_correction_mm": correction, "passive_frequency_hz": first_resonance_hz(
                complete, termination=termination, mouth_correction_mm=correction,
                end_correction_mm=outlet, c=c,
            )}
            for correction in (0.0, 10.0, 30.0, 60.0)
        ],
        "pressure_scenarios": [asdict(airflow(p)) for p in (40.0, 80.0, 160.0, 320.0)],
        "warnings": warnings,
        "sources": SOURCES,
    }
