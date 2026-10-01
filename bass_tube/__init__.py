"""Генератор басовой трубы под готовый модуль мембраны.

Три зоны расчёта живут отдельно: acoustics, layout, body.
Общие входные данные — TubeParams. Строй считает resolve_tuning,
укладку — layout_coil, ось канала — build_centerline.
"""

from bass_tube.acoustics.tuning import Tuning, TuningError, resolve_tuning
from bass_tube.layout.centerline import Centerline, CenterlineError, build_centerline
from bass_tube.layout.coil import Coil, LayoutError, layout_coil
from bass_tube.params import ParamsError, TubeParams, tube_params

__all__ = [
    "Centerline",
    "CenterlineError",
    "Coil",
    "LayoutError",
    "ParamsError",
    "TubeParams",
    "Tuning",
    "TuningError",
    "build_centerline",
    "layout_coil",
    "resolve_tuning",
    "tube_params",
]
