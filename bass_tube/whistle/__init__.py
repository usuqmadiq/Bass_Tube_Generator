"""Экспериментальная печатная лабиальная головка.

Расчёт пассивного резонатора не является подтверждением звучания.
Старый мембранный генератор и его интерфейс не изменяются.
CAD импортируется только при вызове build_head.
"""

from bass_tube.whistle.params import WhistleHeadParams


def build_head(params: WhistleHeadParams | None = None):
    """Строит корпус и отдельную крышку воздушного канала."""
    from bass_tube.whistle.geometry import build_head as _build

    return _build(params or WhistleHeadParams())


__all__ = ["WhistleHeadParams", "build_head"]
