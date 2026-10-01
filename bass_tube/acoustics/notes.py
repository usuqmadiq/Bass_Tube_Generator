"""Имя ноты в научной нотации и её номер MIDI.

Частоту воздушного столба считает модуль строя: здесь только запись ноты
и перевод в номер, где среднее до — C4, а ля первой октавы — номер 69.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Буква A…G, необязательный знак, октава. Среднее до — C4.
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")

_OCTAVE_MIN = -1
_OCTAVE_MAX = 9


class NoteNameError(ValueError):
    """Имя ноты не удалось разобрать. Текст исключения — причина для пользователя."""


@dataclass(frozen=True, slots=True)
class NoteName:
    """Ступень с октавой, без частоты.

    letter — A…G, accidental — пустая строка, «#» или «b», octave — целое от -1 до 9.
    """

    letter: str
    accidental: str
    octave: int

    @property
    def spelling(self) -> str:
        """Каноническая запись ноты.

        Ничего не принимает. Склеивает ступень, знак и октаву.
        Возвращает строку вида C2 или F#3.
        """
        return f"{self.letter}{self.accidental}{self.octave}"


def parse_note_name(raw: str) -> NoteName:
    """Проверяет запись ноты с октавой и разбирает её на части.

    Принимает строку вида C2, F#3, Bb1 или C-1. Регистр буквы не важен.
    Среднее до — C4. Частоту не вычисляет.

    Возвращает NoteName. Если октавы нет или запись чужая, поднимает
    NoteNameError с текстом причины.
    """
    if not isinstance(raw, str):
        raise NoteNameError("Нота должна быть строкой вида C2.")

    text = raw.strip()
    if not text:
        raise NoteNameError("Пустое имя ноты. Нужна запись вида C2, где среднее до — C4.")

    match = _NOTE_RE.fullmatch(text)
    if match is None:
        if re.search(r"\d", text) is None:
            raise NoteNameError(
                f"Нота «{text}» без октавы. Нужна латинская запись вида C2, "
                "где среднее до — C4."
            )
        raise NoteNameError(
            f"Нота «{text}» не разбирается. Нужна запись вида C2 или F#3, "
            "где среднее до — C4."
        )

    letter, accidental, octave_text = match.groups()
    octave = int(octave_text)
    if octave < _OCTAVE_MIN or octave > _OCTAVE_MAX:
        raise NoteNameError(
            f"Нота «{text}»: октава {octave} вне диапазона "
            f"от {_OCTAVE_MIN} до {_OCTAVE_MAX}."
        )

    return NoteName(letter.upper(), accidental, octave)


# Полутон внутри октавы: C = 0 … B = 11.
_SEMITONE_FROM_LETTER = {
    "C": 0,
    "D": 2,
    "E": 4,
    "F": 5,
    "G": 7,
    "A": 9,
    "B": 11,
}

# Диезная запись полутонов. Бемоли сюда не входят: обратный перевод пишет диезы.
_LETTER_FROM_SEMITONE = (
    ("C", ""),
    ("C", "#"),
    ("D", ""),
    ("D", "#"),
    ("E", ""),
    ("F", ""),
    ("F", "#"),
    ("G", ""),
    ("G", "#"),
    ("A", ""),
    ("A", "#"),
    ("B", ""),
)

# C-1 и B9 — края той же октавной сетки, что и разбор имени.
MIDI_C_MINUS_1 = 0
MIDI_B9 = 131


def midi_number(note: NoteName) -> int:
    """Переводит имя ноты в номер MIDI.

    Принимает разобранную ноту. Среднее до C4 получает номер 60, A4 — 69.
    Диез поднимает ступень на полтона, бемоль опускает.
    Возвращает целое. Крайний знак вроде Cb-1 может выйти за 0…127:
    номер при этом остаётся верным интервалом от C-1.
    """
    semitone = _SEMITONE_FROM_LETTER[note.letter]
    if note.accidental == "#":
        semitone += 1
    elif note.accidental == "b":
        semitone -= 1
    return (note.octave + 1) * 12 + semitone


def note_from_midi(midi: int) -> NoteName:
    """Собирает имя ноты из номера MIDI.

    Принимает целое. Номер 60 — это C4. Полутона пишет диезами: 61 — C#4.
    Возвращает NoteName от C-1 до B9. Если номер не целый или лежит вне
    этого диапазона, поднимает NoteNameError с текстом причины.
    """
    if isinstance(midi, bool) or not isinstance(midi, int):
        raise NoteNameError("MIDI-номер должен быть целым.")
    if midi < MIDI_C_MINUS_1 or midi > MIDI_B9:
        raise NoteNameError(
            f"MIDI {midi} вне диапазона нот от C-1 до B9."
        )

    octave_index, semitone = divmod(midi, 12)
    letter, accidental = _LETTER_FROM_SEMITONE[semitone]
    return NoteName(letter, accidental, octave_index - 1)


def shift_midi(midi: int, semitones: int) -> int:
    """Сдвигает номер MIDI на целое число полутонов.

    Принимает номер и сдвиг: положительный поднимает ноту, отрицательный
    опускает. Возвращает новый номер. Диапазон C-1…B9 не проверяет:
    это сделает note_from_midi.
    """
    return midi + semitones

