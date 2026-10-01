"""Короткая подстройка длины после печати: выдвижная трубка в открытом конце.

Это не слайдер на октаву. Корпус считается на верхнюю ноту диапазона
(трубка задвинута). Выдвигая трубку, путь удлиняется примерно на ход:
вложенный участок в длину не считается дважды. Посадка мембраны неподвижна.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from bass_tube.acoustics.notes import (
    NoteNameError,
    midi_number,
    note_from_midi,
    parse_note_name,
    shift_midi,
)
from bass_tube.acoustics.tuning import Tuning, TuningError, resolve_tuning
from bass_tube.constants import (
    TRIM_FLANGE_MM,
    TRIM_MIN_WALL_MM,
    TRIM_OVERLAP_MM,
    TRIM_SLIDE_CLEARANCE_MM,
)
from bass_tube.params import TubeParams


class TrimError(ValueError):
    """Подстройку нельзя посчитать. Текст исключения — причина."""


@dataclass(frozen=True, slots=True)
class TrimPlan:
    """Размеры выдвижной трубки и ноты по краям хода.

    extra_length_mm — сколько миллиметров пути добавляет полное выдвижение
    (q = 1, открытый конец). overlap_mm — сколько трубки всегда остаётся
    внутри канала, чтобы не выпасть. tenon_diameter_mm — наружный диаметр
    вставляемой части, чуть меньше канала. bore_diameter_mm — канал трубки,
    чуть уже канала корпуса: стенка вставки должна куда-то деться.
    """

    upper_note: str
    lower_note: str
    extra_length_mm: float
    overlap_mm: float
    flange_mm: float
    tenon_diameter_mm: float
    bore_diameter_mm: float
    flange_diameter_mm: float
    tenon_length_mm: float


def resolve_trim(params: TubeParams, upper: Tuning) -> TrimPlan | None:
    """Считает ход подстройки под уже полученный строй корпуса.

    Принимает параметры и строй верхней ноты (задвинутая трубка). Если
    полутонов подстройки нет, возвращает None. Иначе опускает ноту на это
    число полутонов, считает корпус нижней ноты тем же строем и берёт
    разницу длин как ход. Посадка мембраны в расчёт не входит: меняется
    только открытый конец. Возвращает TrimPlan.

    Если нижняя нота вне C-1…B9, ход не положительный или вставка не
    оставляет канала, поднимает TrimError.
    """
    steps = params.trim_semitones
    if steps <= 0:
        return None
    try:
        upper_parsed = parse_note_name(upper.note)
        lower_midi = shift_midi(midi_number(upper_parsed), -steps)
        lower_name = note_from_midi(lower_midi).spelling
    except NoteNameError as exc:
        raise TrimError(
            f"Подстройка на {steps} полутонов вниз от {upper.note} "
            f"выходит за ноты от C-1 до B9: {exc}"
        ) from exc

    lower_params = replace(params, note=lower_name, body_length_mm=None)
    try:
        lower = resolve_tuning(lower_params)
    except TuningError as exc:
        raise TrimError(str(exc)) from exc

    extra = lower.body_length_mm - upper.body_length_mm
    if extra <= 1e-6:
        raise TrimError(
            f"Подстройка на {steps} полутонов не удлиняет корпус: "
            f"верх {upper.body_length_mm:.3f} мм, низ {lower.body_length_mm:.3f} мм."
        )

    bore = params.bore_diameter_mm
    tenon = bore - TRIM_SLIDE_CLEARANCE_MM
    wall = min(params.wall_thickness_mm, TRIM_MIN_WALL_MM)
    inner = tenon - 2.0 * wall
    if tenon <= 0.0 or inner <= 0.0:
        raise TrimError(
            "Канал трубы слишком узкий для выдвижной вставки: "
            "не остаётся отверстия внутри трубки подстройки."
        )

    overlap = TRIM_OVERLAP_MM
    return TrimPlan(
        upper_note=upper.note,
        lower_note=lower_name,
        extra_length_mm=extra,
        overlap_mm=overlap,
        flange_mm=TRIM_FLANGE_MM,
        tenon_diameter_mm=tenon,
        bore_diameter_mm=inner,
        flange_diameter_mm=params.outer_diameter_mm,
        tenon_length_mm=overlap + extra,
    )


def socket_length_mm(plan: TrimPlan) -> float:
    """Какой длины свободный канал нужен в последней прямой.

    Принимает план подстройки. Возвращает длину царги: перекрытие плюс ход,
    чтобы трубку можно было задвинуть до конца.
    """
    return plan.tenon_length_mm
