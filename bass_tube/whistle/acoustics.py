"""Пассивная акустика свистковой трубы и оценки подачи, только stdlib.

Резонатор: плоская волна без потерь, цилиндрические матрицы p/U, Z/(ρc).
У лабиума p_in = -Z_m U_in, Z_m = j k Δ_m / S_in. Δ_m — задаваемая
эквивалентная инерционная поправка, НЕ формула по размерам окна. Открытый
выход получает виртуальный цилиндр Δ_out; у закрытого выхода U_out = 0.
Поршень меняет физическую длину секций. Старые поправки мембраны, изгибов,
игровые отверстия, потери и запуск струи этим расчётом не моделируются.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bass_tube.acoustics.matrix import area_mm2, cylinder_matrix, wave_number

if TYPE_CHECKING:
    from bass_tube.params import TubeParams


class WhistleAcousticsError(ValueError):
    """Некорректные исходные данные или неразрешимый пассивный расчёт."""


def _number(name: str, value: float, *, zero: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WhistleAcousticsError(f"{name}: нужно число.")
    value = float(value)
    if not math.isfinite(value) or (value < 0 if zero else value <= 0):
        limit = "неотрицательное" if zero else "положительное"
        raise WhistleAcousticsError(f"{name}: нужно конечное {limit} число.")
    return value


@dataclass(frozen=True, slots=True)
class BoreSection:
    """Длина по оси и внутренний диаметр цилиндрической секции, мм."""

    length_mm: float
    diameter_mm: float

    def __post_init__(self) -> None:
        for name in ("length_mm", "diameter_mm"):
            object.__setattr__(self, name, _number(name, getattr(self, name)))
        _number("Площадь канала", area_mm2(self.diameter_mm))


@dataclass(frozen=True, slots=True)
class AirEstimate:
    """Оценка струи: скорость в центре отдельно от средней и расхода."""

    pressure_pa: float
    density_kg_m3: float
    velocity_coefficient: float
    mean_to_center_ratio: float
    jet_area_mm2: float
    ideal_velocity_m_s: float
    estimated_center_velocity_m_s: float
    estimated_mean_velocity_m_s: float
    flow_l_min: float
    theta: float | None
    strouhal: float | None
    model_notes: tuple[str, ...]

    @property
    def estimated_velocity_m_s(self) -> float:
        """Совместимый короткий псевдоним скорости в центре струи."""
        return self.estimated_center_velocity_m_s


@dataclass(frozen=True, slots=True)
class PairEstimate:
    """Свободные целевые частоты; захват и совместный спектр не предсказаны."""

    frequency_1_hz: float
    frequency_2_hz: float
    beat_hz: float
    detuning_cents: float
    total_flow_l_min: float
    model_notes: tuple[str, ...]


def sound_speed_m_s(temp_c: float) -> float:
    """Приближение для сухого воздуха; температура выше абсолютного нуля."""
    if isinstance(temp_c, bool) or not isinstance(temp_c, (int, float)):
        raise WhistleAcousticsError("Температура: нужно число.")
    if not math.isfinite(temp_c) or temp_c <= -273.15:
        raise WhistleAcousticsError("Температура должна быть выше -273.15 °C.")
    return 331.3 * math.sqrt(1.0 + temp_c / 273.15)


def _settings(termination: str, mouth: float, end: float, c: float):
    if termination not in ("open", "stopped"):
        raise WhistleAcousticsError("Конец трубы: только 'open' или 'stopped'.")
    mouth = _number("Поправка рта", mouth, zero=True)
    end = _number("Поправка выхода", end, zero=True)
    c = _number("Скорость звука", c)
    if termination == "stopped" and end != 0.0:
        raise WhistleAcousticsError("У закрытого торца нет открытой концевой поправки.")
    return mouth, end, c


def ideal_effective_length_mm(
    frequency_hz: float, termination: str = "open", c: float = 343.0,
) -> float:
    """Идеальный ровный канал: c/(2f) открытый, c/(4f) закрытый с конца."""
    _, _, c = _settings(termination, 0.0, 0.0, c)
    frequency_hz = _number("Частота", frequency_hz)
    divisor = 2.0 if termination == "open" else 4.0
    return _number("Эффективная длина", c * 1000.0 / divisor / frequency_hz)


def straight_length_for_frequency_mm(
    frequency_hz: float, termination: str = "open",
    mouth_correction_mm: float = 0.0, end_correction_mm: float = 0.0,
    c: float = 343.0,
) -> float:
    """Обратный расчёт ровного канала в данной модели, без сборки корпуса.

    Δ_m представлена сосредоточенной инерцией, поэтому сдвиг фазы atan(kΔ_m),
    а не kΔ_m. Длина включает весь цилиндр от окна до физического торца;
    длину цилиндрической шейки головки caller вычитает отдельно.
    """
    mouth, end, c = _settings(termination, mouth_correction_mm, end_correction_mm, c)
    k = wave_number(_number("Частота", frequency_hz), c)
    target = math.pi if termination == "open" else math.pi / 2.0
    return _number("Физическая длина", (target - math.atan(k * mouth)) / k - end)


def _phase(k: float, sections: tuple[BoreSection, ...], stopped: bool, mouth: float):
    """Развёрнутая фаза p и U/j; позволяет не перескочить первую моду.

    В каждой секции фаза растёт на kL. На стыке меняется масштаб U/S,
    но сохраняется квадрант. Здесь нет деления на тангенс или полюсов Z.
    """
    phase = 0.0 if stopped else math.pi / 2.0
    previous_area = area_mm2(sections[-1].diameter_mm)
    for section in reversed(sections):
        area = area_mm2(section.diameter_mm)
        turns = math.floor(phase / math.pi)
        reduced = phase - turns * math.pi
        phase = turns * math.pi + math.atan2(
            previous_area * math.sin(reduced), area * math.cos(reduced),
        )
        phase += k * section.length_mm
        previous_area = area
    return phase + math.atan(k * mouth)


def _characteristic(k: float, sections: tuple[BoreSection, ...], stopped: bool, mouth: float):
    """Нуль A+Zm*C (stopped) или B+Zm*D (open), без полюсов импеданса.

    Передаём граничный вектор цилиндрическими матрицами. Положительная
    нормировка после каждой секции сохраняет нули и знаки характеристики.
    """
    pressure, flow = (1.0 + 0j, 0j) if stopped else (0j, 1.0 + 0j)
    for section in reversed(sections):
        (a, b), (c, d) = cylinder_matrix(k, section.length_mm, section.diameter_mm / 2.0)
        pressure, flow = a * pressure + b * flow, c * pressure + d * flow
        scale = _number("Масштаб матрицы", max(abs(pressure), abs(flow)))
        pressure, flow = pressure / scale, flow / scale
    residual = pressure + 1j * k * mouth / area_mm2(sections[0].diameter_mm) * flow
    value = residual.real if stopped else residual.imag
    if not math.isfinite(value):
        raise WhistleAcousticsError("Характеристика вышла за численный диапазон.")
    return value


def first_resonance_hz(
    sections: Iterable[BoreSection], termination: str = "open",
    mouth_correction_mm: float = 0.0, end_correction_mm: float = 0.0,
    c: float = 343.0,
) -> float:
    """Первый положительный ПАССИВНЫЙ резонанс; не частота гарантированного звука.

    Фаза изолирует первую моду, затем бисекция ищет нуль матричной
    характеристики. Нуль DC у open исключён. Нельзя переносить сюда
    delta_head мембраны. Разные mouth_correction_mm — сценарии чувствительности,
    пока поправка не измерена; они не являются доверительным интервалом.
    """
    mouth, end, c = _settings(termination, mouth_correction_mm, end_correction_mm, c)
    try:
        sections = tuple(sections)
    except TypeError as exc:
        raise WhistleAcousticsError("Нужен непустой набор BoreSection.") from exc
    if not sections or any(not isinstance(s, BoreSection) for s in sections):
        raise WhistleAcousticsError("Нужен непустой набор BoreSection.")
    if end:
        sections += (BoreSection(end, sections[-1].diameter_mm),)
    total = _number("Полная длина", math.fsum(s.length_mm for s in sections) + mouth)
    stopped = termination == "stopped"
    target = math.pi / 2.0 if stopped else 1.5 * math.pi
    low, high = 0.0, math.pi / total  # Здесь ищется волновое число, 1/мм.
    for _ in range(1024):
        if _phase(high, sections, stopped, mouth) >= target:
            break
        high *= 2.0
    else:
        raise WhistleAcousticsError("Не найдена верхняя граница первого резонанса.")
    for _ in range(1024):
        middle = (low + high) / 2.0
        if _phase(middle, sections, stopped, mouth) < target:
            low = middle
        else:
            high = middle
        if low > 0 and _phase(high, sections, stopped, mouth) - target < math.pi / 8:
            if target - _phase(low, sections, stopped, mouth) < math.pi / 8:
                break
    else:
        raise WhistleAcousticsError("Не удалось изолировать первый положительный корень.")
    low *= 1.0 - 1e-9
    high *= 1.0 + 1e-9  # Не оставить точный корень на границе из-за округления.
    low_value = _characteristic(low, sections, stopped, mouth)
    high_value = _characteristic(high, sections, stopped, mouth)
    if (low_value > 0) == (high_value > 0):
        raise WhistleAcousticsError("Не удалось устойчиво ограничить первый корень.")
    for _ in range(100):
        middle = (low + high) / 2.0
        value = _characteristic(middle, sections, stopped, mouth)
        if value == 0:
            low = high = middle
            break
        if (value > 0) == (low_value > 0):
            low, low_value = middle, value
        else:
            high = middle
        if high - low < high * 1e-12:
            break
    return (low + high) / 2.0 * c * 1000.0 / (2.0 * math.pi)


def sections_for_tube(params: TubeParams, body_length_mm: float) -> tuple[BoreSection, ...]:
    """Посадка + 64 цилиндра конуса + остальной канал по физической оси.

    Головка сюда не входит. Игровые отверстия и слайдеры отвергаются.
    delta_head, delta_out, delta_bends старой модели не применяются; caller
    задаёт новые поправки solver отдельно. Не моделирует выдвинутый тюнер.
    """
    if params.hole_count or params.slider_kind or params.slider_semitones or params.slider_pairs:
        raise WhistleAcousticsError("Свистковой прототип не моделирует отверстия и слайдеры.")
    body = _number("Длина корпуса", body_length_mm)
    if body < params.joint_length_mm:
        raise WhistleAcousticsError("Корпус короче посадки и переходника.")
    result = [BoreSection(params.seat_length_mm, params.seat_bore_diameter_mm)]
    if params.transition_length_mm:
        step = params.transition_length_mm / 64.0
        for index in range(64):
            diameter = params.seat_bore_diameter_mm + (
                params.bore_diameter_mm - params.seat_bore_diameter_mm
            ) * (index + 0.5) / 64.0
            result.append(BoreSection(step, diameter))
    rest = body - params.joint_length_mm
    if rest > 0:
        result.append(BoreSection(rest, params.bore_diameter_mm))
    return tuple(result)


def estimate_airflow(
    pressure_pa: float, windway_width_mm: float, windway_height_mm: float, *,
    frequency_hz: float | None = None, cutup_mm: float | None = None,
    velocity_coefficient: float = 0.8, density_kg_m3: float = 1.2,
    mean_to_center_ratio: float = 1.0,
) -> AirEstimate:
    """U_center=Cv√(2P/ρ), U_mean=rU_center, Q=bhU_mean, θ=U_center/(fW).

    P — предполагаемый перепад у струи, не измеренный перепад всей подачи.
    Cv=0.8 — пользовательское допущение, Cv=1 даёт идеальную оценку скорости.
    r=1 предполагает плоский профиль. При P=0 число St не определено.
    """
    pressure = _number("Давление", pressure_pa, zero=True)
    width = _number("Ширина щели", windway_width_mm)
    height = _number("Высота щели", windway_height_mm)
    density = _number("Плотность", density_kg_m3)
    coefficient = _number("Коэффициент скорости", velocity_coefficient)
    ratio = _number("Отношение средней скорости к центральной", mean_to_center_ratio)
    if coefficient > 1 or ratio > 1:
        raise WhistleAcousticsError("Коэффициенты скорости в этой модели не больше единицы.")
    if (frequency_hz is None) != (cutup_mm is None):
        raise WhistleAcousticsError("Для θ и St нужны одновременно частота и высота окна.")
    ideal = math.sqrt(2.0 * pressure / density)
    center, mean = coefficient * ideal, coefficient * ideal * ratio
    area = _number("Площадь щели", width * height)
    flow = _number("Расход", area * mean * 0.06, zero=True)
    theta = strouhal = None
    if frequency_hz is not None:
        frequency = _number("Частота", frequency_hz)
        cutup = _number("Высота окна", cutup_mm)
        theta = center / (frequency * cutup * 0.001)
        strouhal = 1.0 / theta if theta > 0 else None
    notes = (
        "Cv — заданное допущение, не измеренная калибровка; потери подачи неизвестны.",
        "U_mean/U_center=1 предполагает плоский профиль; расход использует среднюю скорость.",
        "θ использует центральную скорость. Эти оценки не гарантируют запуск или основной тон.",
    )
    return AirEstimate(pressure, density, coefficient, ratio, area, ideal, center, mean,
                       flow, theta, strouhal, notes)


def estimate_pair(
    frequency_1_hz: float, frequency_2_hz: float,
    flow_1_l_min: float = 0.0, flow_2_l_min: float = 0.0,
) -> PairEstimate:
    """Расстройка f2 относительно f1; биения |f2-f1| только без захвата."""
    first = _number("Частота 1", frequency_1_hz)
    second = _number("Частота 2", frequency_2_hz)
    flow = _number("Расход 1", flow_1_l_min, zero=True) + _number("Расход 2", flow_2_l_min, zero=True)
    flow = _number("Суммарный расход", flow, zero=True)
    return PairEstimate(first, second, abs(second - first),
                        1200.0 * (math.log2(second) - math.log2(first)), flow, (
        "Свободные целевые частоты; совместное звучание может захватить одну частоту.",
        "Сумма расходов предполагает сохранение режима каждой ветви; связь подачи не рассчитана.",
    ))
