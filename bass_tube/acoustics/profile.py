"""Строй трубы с переходником: матрицы передачи плоской волны без потерь.

Профиль от мембраны: посадка постоянного канала, конус переходника, дальше
канал трубы до выхода. Мембрана — закрытый конец, выход — открытый с
поправкой Δ_out. Конус заменяется лесенкой коротких цилиндров: на басовых
длинах волн погрешность лесенки меньше сотых миллиметра.

Для ровной трубы этот расчёт совпадает с четвертью волны
L + Δ_out = c / (4f), поэтому tuning использует его только при переходнике.
"""

from __future__ import annotations

import math

from bass_tube.acoustics.matrix import area_mm2, cylinder_matrix, multiply, wave_number
from bass_tube.params import TubeParams

_CONE_STEPS = 64


class ProfileError(ValueError):
    """Профиль с переходником не даёт основного резонанса. Текст — причина."""


def rest_length_for_frequency_mm(params: TubeParams, frequency_hz: float) -> float:
    """Длина ровного канала после переходника под заданную частоту.

    Принимает параметры с переходником и частоту основного резонанса.
    Считает матрицу посадки и конуса, затем ищет длину канала трубы, при
    которой у мембраны поток равен нулю, с поправкой открытого конца.
    Возвращает миллиметры от конца конуса до выхода. Если стык длиннее
    четверти волны и места под канал не остаётся, поднимает ProfileError.
    """
    k = wave_number(frequency_hz, params.speed_of_sound_m_s)
    c_front, d_front = _front_matrix_bottom_row(params, k)
    body_impedance = 1.0 / area_mm2(params.bore_diameter_mm)
    ratio = -d_front / (c_front * 1j * body_impedance)
    phase = math.atan(ratio.real) % math.pi
    rest = phase / k - params.delta_out_mm
    if rest <= 0.0:
        raise ProfileError(
            "Посадка с переходником длиннее четверти волны: "
            "под канал трубы места не остаётся."
        )
    return rest


def frequency_for_rest_length_hz(params: TubeParams, rest_mm: float) -> float:
    """Частота основного резонанса при заданной длине канала трубы.

    Принимает параметры с переходником и длину ровного канала после конуса.
    Берёт оценку четверти волны по всей длине, затем делением отрезка
    подбирает частоту, при которой rest_length_for_frequency_mm совпадает
    с заданной. Возвращает герцы. Если корня рядом с оценкой нет,
    поднимает ProfileError.
    """
    if rest_mm <= 0.0:
        raise ProfileError("Канал трубы после переходника не положительной длины.")
    total = params.joint_length_mm + rest_mm + params.delta_out_mm
    estimate = params.speed_of_sound_m_s * 1000.0 / (4.0 * total)
    low = estimate * 0.5
    high = estimate * 2.0
    low_gap = _rest_gap(params, low, rest_mm)
    high_gap = _rest_gap(params, high, rest_mm)
    if low_gap is None or high_gap is None or low_gap * high_gap > 0.0:
        raise ProfileError("Основной резонанс профиля с переходником не найден.")
    for _ in range(200):
        middle = (low + high) / 2.0
        gap = _rest_gap(params, middle, rest_mm)
        if gap is None:
            raise ProfileError("Основной резонанс профиля с переходником не найден.")
        if gap * low_gap > 0.0:
            low, low_gap = middle, gap
        else:
            high = middle
        if high - low < 1e-12 * estimate:
            break
    return (low + high) / 2.0


def _rest_gap(params: TubeParams, frequency_hz: float, rest_mm: float) -> float | None:
    """Разница между нужной и заданной длиной канала на частоте.

    Принимает параметры, пробную частоту и заданную длину канала.
    Возвращает нужная минус заданная; None, если на этой частоте
    канала не остаётся вовсе.
    """
    try:
        return rest_length_for_frequency_mm(params, frequency_hz) - rest_mm
    except ProfileError:
        return None


def _front_matrix_bottom_row(params: TubeParams, k: float) -> tuple[complex, complex]:
    """Нижняя строка матрицы передачи посадки и конуса.

    Принимает параметры и волновое число в 1/мм. Перемножает матрицы
    цилиндра посадки и ступенек конуса от мембраны к трубе. Импеданс
    нормирован на ρc: у цилиндра он 1/S. Возвращает пару (C, D):
    поток у мембраны равен C·p + D·U на конце конуса.
    """
    seat_radius = params.seat_bore_diameter_mm / 2.0
    body_radius = params.bore_diameter_mm / 2.0
    matrix = cylinder_matrix(k, params.seat_length_mm, seat_radius)
    step = params.transition_length_mm / _CONE_STEPS
    for index in range(_CONE_STEPS):
        fraction = (index + 0.5) / _CONE_STEPS
        radius = seat_radius + (body_radius - seat_radius) * fraction
        matrix = multiply(matrix, cylinder_matrix(k, step, radius))
    return matrix[1][0], matrix[1][1]
