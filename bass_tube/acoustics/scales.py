"""Лад от ноты корпуса: ступени для последовательного открывания отверстий.

Нота, по которой считается длина трубы, — тоника. Отверстия открываются
от открытого конца к мембране: первое даёт соседнюю ступень лада, последнее —
самую высокую из набора. Хроматических комбинаций нет.
"""

from __future__ import annotations

from bass_tube.acoustics.notes import NoteNameError, midi_number, note_from_midi, parse_note_name, shift_midi
from bass_tube.constants import MAX_HOLES, SCALE_IDS, SCALE_STEPS

SCALE_LABELS = {
    "major": "мажор",
    "natural_minor": "натуральный минор",
    "melodic_minor": "минор мелодический",
    "pentatonic": "пентатоника",
    "major_pentatonic": "мажорная пентатоника",
}


class ScaleError(ValueError):
    """Лад или число отверстий нельзя собрать. Текст исключения — причина."""


def scale_note_names(tonic: str, scale_id: str, hole_count: int) -> tuple[str, ...]:
    """Имена нот последовательного открывания, считая тонику.

    Принимает запись тоники, идентификатор лада и число отверстий.
    Возвращает hole_count + 1 имён: сначала тоника (все закрыты), дальше
    ступени по мере открывания дырок от выходного конца. Если лад неизвестен,
    дырок больше восьми или нота выходит за C-1…B9, поднимает ScaleError.
    """
    if hole_count < 1 or hole_count > MAX_HOLES:
        raise ScaleError(
            f"Отверстий {hole_count}: можно от 1 до {MAX_HOLES}."
        )
    if scale_id not in SCALE_STEPS:
        known = ", ".join(SCALE_IDS)
        raise ScaleError(f"Лад «{scale_id}» не известен: есть {known}.")
    try:
        root_midi = midi_number(parse_note_name(tonic))
    except NoteNameError as exc:
        raise ScaleError(str(exc)) from exc
    names = [parse_note_name(tonic).spelling]
    for steps in SCALE_STEPS[scale_id][:hole_count]:
        try:
            names.append(note_from_midi(shift_midi(root_midi, steps)).spelling)
        except NoteNameError as exc:
            raise ScaleError(
                f"Ступень лада на {steps} полутонов от {tonic} "
                f"выходит за ноты от C-1 до B9: {exc}"
            ) from exc
    return tuple(names)


def scale_label(scale_id: str) -> str:
    """Русское имя лада для окна и отчёта.

    Принимает идентификатор. Возвращает подпись; неизвестный идентификатор
    отдаёт как есть.
    """
    return SCALE_LABELS.get(scale_id, scale_id)
