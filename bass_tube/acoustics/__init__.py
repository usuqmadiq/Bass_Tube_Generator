"""Акустика воздушного канала: имя ноты, частота, эффективная длина, поправки.

Геометрию трубы этот пакет не строит. Имя ноты и номер MIDI живут в notes,
длина корпуса и прогноз строя — в tuning, короткая подстройка — в trim,
слайдер длины — в slider, игровые отверстия и лад — в holes и scales.
"""

from bass_tube.acoustics.holes import HoleError, HolePlan, plan_holes
from bass_tube.acoustics.notes import (
    NoteName,
    NoteNameError,
    midi_number,
    note_from_midi,
    parse_note_name,
    shift_midi,
)
from bass_tube.acoustics.scales import ScaleError, scale_note_names
from bass_tube.acoustics.slider import SliderError, SliderPlan, resolve_slider
from bass_tube.acoustics.trim import TrimError, TrimPlan, resolve_trim, socket_length_mm
from bass_tube.acoustics.tuning import Tuning, TuningError, resolve_tuning

__all__ = [
    "HoleError",
    "HolePlan",
    "NoteName",
    "NoteNameError",
    "ScaleError",
    "SliderError",
    "SliderPlan",
    "TrimError",
    "TrimPlan",
    "Tuning",
    "TuningError",
    "midi_number",
    "note_from_midi",
    "parse_note_name",
    "plan_holes",
    "resolve_slider",
    "resolve_trim",
    "resolve_tuning",
    "scale_note_names",
    "shift_midi",
    "socket_length_mm",
]
