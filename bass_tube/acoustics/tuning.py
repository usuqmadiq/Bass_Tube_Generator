"""Строй закрыто-открытой трубы: нота, частота и длина корпуса.

Труба считается закрытой со стороны мембраны и открытой на выходе.
Основная длина — четверть волны. Передув на октаву здесь не закладывается.
Если у конца другой диаметр, чем у трубы, длина считается по профилю
с переходником, а разница с ровной трубой ложится в delta_transition_mm.
Геометрию укладки этот модуль не проверяет: длинный корпус возвращается
как есть, даже если в габарит он потом не влезет.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bass_tube.acoustics.notes import NoteNameError, midi_number, note_from_midi, parse_note_name
from bass_tube.acoustics.profile import (
    ProfileError,
    frequency_for_rest_length_hz,
    rest_length_for_frequency_mm,
)
from bass_tube.params import TubeParams


class TuningError(ValueError):
    """Строй не удалось перевести в длину корпуса. Текст исключения — причина."""


@dataclass(frozen=True, slots=True)
class Tuning:
    """Нота, частота и длины одного режима.

    В режиме ноты body_length_mm получена из частоты. В режиме длины она
    совпадает с заданной, а note — ближайшая ступень к прогнозу.
    cents — насколько частота выше названной ноты; у точной ноты это ноль.
    delta_transition_mm — сдвиг от переходника:
    L_body = L_eff − Δ_head − Δ_out − Δ_bends − Δ_transition. У ровной трубы ноль,
    узкий конец у мембраны делает его отрицательным, то есть корпус длиннее.
    head_calibrated остаётся ложью, пока нет профиля замера мембраны:
    ручное число в delta_head_mm калибровкой не считается.
    """

    note: str
    frequency_hz: float
    effective_length_mm: float
    body_length_mm: float
    delta_head_mm: float
    delta_out_mm: float
    delta_bends_mm: float
    delta_transition_mm: float
    head_calibrated: bool
    cents: float

    @property
    def head_calibration_mark(self) -> str:
        """Фраза о калибровке головки для отчёта.

        Ничего не принимает. Смотрит на head_calibrated.
        Возвращает «головка калибрована» либо «головка не калибрована».
        """
        if self.head_calibrated:
            return "головка калибрована"
        return "головка не калибрована"


def resolve_tuning(params: TubeParams) -> Tuning:
    """Переводит цель трубы в длину корпуса или в прогноз строя.

    Принимает проверенные параметры. В режиме ноты идёт от MIDI к частоте,
    к эффективной длине L_eff = c / (4f) и к корпусу
    L_body = L_eff − Δ_head − Δ_out − Δ_bends.
    При переходнике корпус подбирается по профилю посадки и конуса.
    В режиме длины сохраняет заданный корпус, собирает эффективную длину
    обратно и называет ближайшую ноту. Скорость звука и A4 берутся из параметров.

    Возвращает Tuning. Головка в результате помечена как некалиброванная.
    Если корпус короче стыка или не положительный, либо эффективная
    длина не положительна, поднимает TuningError с текстом причины.
    """
    if params.note is not None:
        return _tuning_from_note(params)
    return _tuning_from_length(params)


def frequency_hz(midi: int, a4_hz: float) -> float:
    """Частота равномерно темперированной ноты.

    Принимает номер MIDI и частоту A4 в герцах.
    Считает f = f_A4 · 2^((m − 69) / 12).
    Возвращает частоту в герцах.
    """
    return a4_hz * 2.0 ** ((midi - 69) / 12.0)


def effective_length_mm(frequency: float, speed_of_sound_m_s: float) -> float:
    """Эффективная длина закрыто-открытой трубы.

    Принимает частоту в герцах и скорость звука в метрах в секунду.
    Считает четверть волны c / (4f) и переводит её в миллиметры.
    Возвращает L_eff в миллиметрах.
    """
    return speed_of_sound_m_s / (4.0 * frequency) * 1000.0


def frequency_from_effective_length_hz(
    effective_length: float,
    speed_of_sound_m_s: float,
) -> float:
    """Частота по эффективной длине закрыто-открытой трубы.

    Принимает L_eff в миллиметрах и скорость звука в метрах в секунду.
    Считает f = c / (4 L_eff). Возвращает частоту в герцах.
    """
    length_m = effective_length / 1000.0
    return speed_of_sound_m_s / (4.0 * length_m)


def _tuning_from_note(params: TubeParams) -> Tuning:
    """Считает длину корпуса под заданную ноту.

    Принимает параметры, у которых заполнено имя ноты. Переводит его в MIDI,
    частоту и четверть волны, затем вычитает три поправки.
    Возвращает Tuning с нулевым отклонением в центах.
    Если корпус получается не длиннее посадки, поднимает TuningError.
    """
    note = parse_note_name(params.note or "")
    midi = midi_number(note)
    frequency = frequency_hz(midi, params.a4_hz)
    effective = effective_length_mm(frequency, params.speed_of_sound_m_s)
    if params.has_transition:
        try:
            rest = rest_length_for_frequency_mm(params, frequency)
        except ProfileError as exc:
            raise TuningError(str(exc)) from exc
        body = params.joint_length_mm + rest - params.delta_head_mm - params.delta_bends_mm
    else:
        body = effective - _corrections_mm(params)
    _require_body_length(body, params)
    return _assemble(params, note.spelling, frequency, effective, body, cents=0.0)


def _tuning_from_length(params: TubeParams) -> Tuning:
    """Прогнозирует частоту и ноту по заданной длине корпуса.

    Принимает параметры с body_length_mm. Эту длину не меняет.
    Прибавляет три поправки, получает частоту четвертьволнового резонанса
    и ближайшую ноту. Ровно посередине между ступеньками берёт верхнюю,
    записывает её диезами.
    Возвращает Tuning с пометкой, что головка не калибрована.
    Если эффективная длина не положительна или частота выходит за C-1…B9,
    поднимает TuningError.
    """
    body = float(params.body_length_mm or 0.0)
    if params.has_transition:
        frequency = _frequency_with_transition(params, body)
        effective = effective_length_mm(frequency, params.speed_of_sound_m_s)
    else:
        effective = body + _corrections_mm(params)
        if effective <= 0.0:
            raise TuningError(
                f"Эффективная длина {_format_mm(effective)} мм не положительна."
            )
        frequency = frequency_from_effective_length_hz(
            effective,
            params.speed_of_sound_m_s,
        )
    try:
        nearest = note_from_midi(_nearest_midi(frequency, params.a4_hz))
    except NoteNameError as exc:
        raise TuningError(
            f"Частота {_format_hz(frequency)} Гц не попадает в ноты от C-1 до B9."
        ) from exc

    nearest_frequency = frequency_hz(midi_number(nearest), params.a4_hz)
    cents = _cents(frequency, nearest_frequency)
    return _assemble(params, nearest.spelling, frequency, effective, body, cents)


def _frequency_with_transition(params: TubeParams, body_mm: float) -> float:
    """Частота корпуса заданной длины с переходником у мембраны.

    Принимает параметры и длину корпуса по оси. Прибавляет поправки
    головки и изгибов, вычитает стык и подбирает частоту по профилю.
    Возвращает герцы. Если канала после стыка не остаётся или резонанс
    не найден, поднимает TuningError.
    """
    acoustic = body_mm + params.delta_head_mm + params.delta_bends_mm
    rest = acoustic - params.joint_length_mm
    if rest <= 0.0:
        raise TuningError(
            f"Длина {_format_mm(acoustic)} мм с поправками не длиннее посадки "
            f"с переходником {_format_mm(params.joint_length_mm)} мм."
        )
    try:
        return frequency_for_rest_length_hz(params, rest)
    except ProfileError as exc:
        raise TuningError(str(exc)) from exc


def _assemble(
    params: TubeParams,
    note: str,
    frequency: float,
    effective: float,
    body: float,
    cents: float,
) -> Tuning:
    """Собирает результат строя из уже посчитанных чисел.

    Принимает параметры, имя ноты, частоту, обе длины и центы.
    Копирует три поправки, сдвиг переходника берёт как остаток формулы
    длины и ставит head_calibrated в False: профиля замера мембраны
    у параметров нет. Возвращает неизменяемый Tuning.
    """
    transition = 0.0
    if params.has_transition:
        transition = effective - _corrections_mm(params) - body
    return Tuning(
        note=note,
        frequency_hz=frequency,
        effective_length_mm=effective,
        body_length_mm=body,
        delta_head_mm=params.delta_head_mm,
        delta_out_mm=params.delta_out_mm,
        delta_bends_mm=params.delta_bends_mm,
        delta_transition_mm=transition,
        head_calibrated=False,
        cents=cents,
    )


def _corrections_mm(params: TubeParams) -> float:
    """Сумма трёх поправок длины.

    Принимает параметры. Складывает поправки головки, открытого конца и изгибов.
    Возвращает сумму в миллиметрах. Знак каждой поправки сохраняется.
    """
    return params.delta_head_mm + params.delta_out_mm + params.delta_bends_mm


def _require_body_length(body_mm: float, params: TubeParams) -> None:
    """Проверяет, что посчитанный корпус длиннее стыка.

    Принимает длину корпуса и параметры с длиной посадки и переходника.
    Ничего не возвращает. Если корпус не положительный или короче стыка,
    поднимает TuningError с текстом причины.
    """
    if body_mm <= 0.0:
        raise TuningError(
            f"Длина корпуса {_format_mm(body_mm)} мм не положительна."
        )
    if body_mm < params.joint_length_mm:
        joint = "посадки" if not params.has_transition else "посадки с переходником"
        raise TuningError(
            f"Длина корпуса {_format_mm(body_mm)} мм короче {joint} "
            f"{_format_mm(params.joint_length_mm)} мм."
        )


def _nearest_midi(frequency: float, a4_hz: float) -> int:
    """Ближайший номер MIDI к частоте.

    Принимает частоту и частоту A4 в герцах.
    Считает непрерывный номер и округляет до целого; ровно половина
    полутона уходит в верхнюю ноту.
    Возвращает номер MIDI.
    """
    midi_float = 69.0 + 12.0 * math.log2(frequency / a4_hz)
    return math.floor(midi_float + 0.5)


def _cents(frequency: float, reference: float) -> float:
    """Отклонение частоты от опорной в центах.

    Принимает две частоты в герцах. Считает 1200 · log2(f / f_оп).
    Возвращает положительное число, когда первая частота выше опорной.
    """
    return 1200.0 * math.log2(frequency / reference)


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает короткую запись: целое без дроби,
    иначе до трёх знаков после запятой без хвостовых нулей.
    """
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")


def _format_hz(value: float) -> str:
    """Форматирует герцы для текста причины.

    Принимает частоту. Возвращает запись до двух знаков после запятой
    без хвостовых нулей.
    """
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")
