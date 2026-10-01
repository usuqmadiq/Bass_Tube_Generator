"""Укладка воздушного канала в габарит и осевая линия этой укладки.

Укладка задаёт, где стоят вертикальные прямые вязанки и какой они длины.
Ось — список прямых и дуг 180° в пространстве, точка и касательная
на координате s считаются по формуле участка. Под игровые отверстия укладка
подбирается решателем hole_fit: число прямых и высоты пар такие, чтобы колена
легли между дырками; подъём равен следующему спуску, все нижние колени на цоколе.
Слайдер меняет длины ветвей последних нижних колен (U или двойное U) или царгу выхода
(выдвижной конец); печатается сложенный корпус, высота на полном ходу
пишется в отчёт, деталь слайдера должна влезть на стол.
Проверка зазоров следит, чтобы каналы разных колен не сливались. Частоту
и твёрдое тело пакет не считает.
"""

from bass_tube.layout.centerline import (
    AxisFrame,
    Centerline,
    CenterlineError,
    Straight,
    Turn,
    Vec3,
    build_centerline,
)
from bass_tube.layout.clearance import check_channel_clearance
from bass_tube.layout.coil import Coil, LayoutError, layout_coil
from bass_tube.layout.columns import adjacent_pairs, bundle_columns, flat_columns
from bass_tube.layout.holes import PlacedHole, place_holes_in_envelope, place_holes_on_coil

__all__ = [
    "AxisFrame",
    "Centerline",
    "CenterlineError",
    "Coil",
    "LayoutError",
    "PlacedHole",
    "Straight",
    "Turn",
    "Vec3",
    "adjacent_pairs",
    "build_centerline",
    "bundle_columns",
    "check_channel_clearance",
    "flat_columns",
    "layout_coil",
    "place_holes_in_envelope",
    "place_holes_on_coil",
]
