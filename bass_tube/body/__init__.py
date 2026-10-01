"""Твёрдое тело трубы: полый канал по оси, стык с модулем, цоколь, экспорт STEP и STL.

Длину канала и ноту этот пакет не назначает. При включённых разрезах корпус
режется на куски стола со стыками «папа — мама» без зазора; без разрезов деталь одна.
Конец под модуль и труба могут быть разного диаметра: между ними конус.
Выдвижная трубка подстройки печатается отдельно, если ход задан.
Слайдер — отдельная деталь: выдвижной конец или подвижное U-колено.
Игровые отверстия вырезаются сквозь стенку наружу вязанки.
"""

from bass_tube.body.slider import build_slider_body
from bass_tube.body.tube import BodyError, TubeBody, build_tube_body, export_tube_body, load_tube_step
from bass_tube.body.tuner import build_tuner_body

__all__ = [
    "BodyError",
    "TubeBody",
    "build_slider_body",
    "build_tube_body",
    "build_tuner_body",
    "export_tube_body",
    "load_tube_step",
]
