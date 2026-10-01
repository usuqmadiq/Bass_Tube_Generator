"""Сечение канала вдоль координаты s от мембраны.

Посадка — цилиндр конца под модуль, дальше конус переходника, дальше труба.
Стенка одна и та же, поэтому наружный радиус — канал плюс стенка.
Акустика, проверка зазоров и тело берут радиусы отсюда.
"""

from __future__ import annotations

from bass_tube.params import TubeParams


def bore_radius_at(params: TubeParams, s_mm: float) -> float:
    """Радиус канала на координате s.

    Принимает параметры и расстояние от мембраны в миллиметрах.
    В посадке это канал конца, после переходника — канал трубы,
    на конусе — линейный переход между ними. Возвращает миллиметры.
    """
    seat = params.seat_bore_diameter_mm / 2.0
    body = params.bore_diameter_mm / 2.0
    return _blend(params, s_mm, seat, body)


def outer_radius_at(params: TubeParams, s_mm: float) -> float:
    """Наружный радиус на координате s.

    Принимает параметры и расстояние от мембраны в миллиметрах.
    Устроен как bore_radius_at, только по наружным диаметрам.
    Возвращает миллиметры.
    """
    seat = params.seat_outer_diameter_mm / 2.0
    body = params.outer_diameter_mm / 2.0
    return _blend(params, s_mm, seat, body)


def _blend(params: TubeParams, s_mm: float, seat_value: float, body_value: float) -> float:
    """Значение радиуса по зонам стыка.

    Принимает параметры, координату и радиусы конца и трубы.
    До конца посадки возвращает радиус конца, после переходника — трубы,
    между ними — линейную смесь.
    """
    seat_end = params.seat_length_mm
    if not params.has_transition or s_mm <= seat_end:
        return seat_value if s_mm <= seat_end else body_value
    fraction = (s_mm - seat_end) / params.transition_length_mm
    if fraction >= 1.0:
        return body_value
    return seat_value + (body_value - seat_value) * fraction
