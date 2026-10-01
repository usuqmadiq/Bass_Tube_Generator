"""Передаточные матрицы цилиндра без потерь.

Импеданс нормирован на ρc: у цилиндра Z = 1/S. Так же считает профиль
переходника и отверстия. Геометрию укладки этот модуль не знает.
"""

from __future__ import annotations

import math

Matrix2 = tuple[tuple[complex, complex], tuple[complex, complex]]

IDENTITY: Matrix2 = ((1.0 + 0j, 0.0 + 0j), (0.0 + 0j, 1.0 + 0j))


def cylinder_matrix(k: float, length_mm: float, radius_mm: float) -> Matrix2:
    """Матрица передачи цилиндра без потерь.

    Принимает волновое число в 1/мм, длину и радиус канала в миллиметрах.
    Возвращает [[cos kl, jZ sin kl], [j sin kl / Z, cos kl]] с Z = 1/S.
    """
    impedance = 1.0 / (math.pi * radius_mm * radius_mm)
    phase = k * length_mm
    cosine = complex(math.cos(phase))
    sine = math.sin(phase)
    return ((cosine, 1j * impedance * sine), (1j * sine / impedance, cosine))


def shunt_matrix(admittance: complex) -> Matrix2:
    """Матрица боковой проводимости.

    Принимает Y отверстия: поток на входе больше потока на выходе на Y·p.
    Возвращает [[1, 0], [Y, 1]].
    """
    return ((1.0 + 0j, 0.0 + 0j), (admittance, 1.0 + 0j))


def multiply(left: Matrix2, right: Matrix2) -> Matrix2:
    """Произведение двух матриц 2×2.

    Принимает две матрицы кортежами строк. Возвращает их произведение:
    сначала действует right, затем left, если смотреть от мембраны к выходу.
    """
    return (
        (
            left[0][0] * right[0][0] + left[0][1] * right[1][0],
            left[0][0] * right[0][1] + left[0][1] * right[1][1],
        ),
        (
            left[1][0] * right[0][0] + left[1][1] * right[1][0],
            left[1][0] * right[0][1] + left[1][1] * right[1][1],
        ),
    )


def wave_number(frequency_hz: float, speed_of_sound_m_s: float) -> float:
    """Волновое число в обратных миллиметрах.

    Принимает частоту и скорость звука. Возвращает 2πf / c, c в мм/с.
    """
    return 2.0 * math.pi * frequency_hz / (speed_of_sound_m_s * 1000.0)


def area_mm2(diameter_mm: float) -> float:
    """Площадь круглого канала.

    Принимает диаметр в миллиметрах. Возвращает квадратные миллиметры.
    """
    return math.pi * diameter_mm * diameter_mm / 4.0
