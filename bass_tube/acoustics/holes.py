"""Игровые отверстия: матрицы передачи, координата s и ошибка строя в центах.

Тоника — нота корпуса. Дырки открываются по очереди от выходного конца:
все закрыты дают тонику, первая открытая — следующую ступень лада.
Закрытые дырки остаются боковым объёмом и слегка сдвигают основную ноту.
Посадка мембраны в расчёт дырок не входит: они стоят на канале трубы.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from bass_tube.acoustics.matrix import (
    IDENTITY,
    cylinder_matrix,
    multiply,
    shunt_matrix,
    wave_number,
)
from bass_tube.acoustics.notes import midi_number, parse_note_name
from bass_tube.acoustics.scales import ScaleError, scale_note_names
from bass_tube.acoustics.tuning import Tuning, frequency_hz
from bass_tube.constants import (
    HOLE_END_MARGIN_MM,
    HOLE_MIN_GAP_MM,
    OPEN_END_CORRECTION_FACTOR,
)
from bass_tube.params import TubeParams

_CONE_STEPS = 64


class HoleError(ValueError):
    """Отверстия нельзя расставить или посчитать. Текст исключения — причина."""


@dataclass(frozen=True, slots=True)
class HoleSpec:
    """Одно отверстие на канале до привязки к прямой укладки.

    s_mm — координата вдоль оси от мембраны. diameter_mm — диаметр дырки.
    chimney_mm — длина бокового канала, здесь толщина стенки.
    note — ступень, которая должна зазвучать, когда открыты эта дырка
    и все ближе к выходу. target_hz — частота этой ступени.
    """

    s_mm: float
    diameter_mm: float
    chimney_mm: float
    note: str
    target_hz: float


@dataclass(frozen=True, slots=True)
class FingeringReport:
    """Прогноз одной аппликатуры последовательного открывания.

    open_count — сколько дырок открыто с выходного конца. predicted_hz —
    резонанс модели. cents — насколько прогноз выше целевой ступени.
    """

    note: str
    target_hz: float
    predicted_hz: float
    cents: float
    open_count: int


@dataclass(frozen=True, slots=True)
class HolePlan:
    """Набор отверстий и прогноз всех аппликатур, включая «все закрыты»."""

    scale_id: str
    tonic: str
    holes: tuple[HoleSpec, ...]
    fingerings: tuple[FingeringReport, ...]


def plan_holes(
    params: TubeParams,
    tuning: Tuning,
    exit_keep_mm: float = 0.0,
) -> HolePlan | None:
    """Расставляет отверстия под лад тоники корпуса.

    Принимает параметры, уже посчитанный строй и сколько оси от выхода
    занято цоколем или царгой подстройки (туда дырку не поставить). Если
    дырок нет, возвращает None. Иначе берёт ноту строя как тонику, считает
    целевые частоты ступеней и подбирает координаты s от выходного конца
    к мембране так, чтобы резонанс матриц попал в ступень. Возвращает
    HolePlan с прогнозом всех аппликатур. Если дырка не помещается на
    канале, поднимает HoleError.
    """
    count = params.hole_count
    if count <= 0:
        return None
    tonic = tuning.note
    try:
        names = scale_note_names(tonic, params.scale, count)
    except ScaleError as exc:
        raise HoleError(str(exc)) from exc

    diameter = params.hole_diameter_mm
    chimney = params.wall_thickness_mm
    body = tuning.body_length_mm
    placed: list[HoleSpec] = []
    # От выходного конца: первая дырка — вторая нота набора.
    for index in range(count):
        note = names[index + 1]
        target = frequency_hz(midi_number(parse_note_name(note)), params.a4_hz)
        high = body - max(exit_keep_mm, 0.0) - HOLE_END_MARGIN_MM
        if placed:
            high = min(high, placed[-1].s_mm - HOLE_MIN_GAP_MM)
        low = params.joint_length_mm + HOLE_END_MARGIN_MM
        if high <= low:
            raise HoleError(
                f"Для ноты {note} на канале не осталось места под отверстие: "
                "уменьшите число дырок или диаметр."
            )
        try:
            s_mm = _locate_hole(params, body, placed, diameter, chimney, target, low, high)
        except HoleError as exc:
            if placed or exit_keep_mm <= 0.0:
                raise
            raise HoleError(
                f"Первая дырка ({note}) должна стоять ближе к выходу, чем "
                f"позволяют цоколь или царга подстройки: они занимают "
                f"{_format_mm(exit_keep_mm)} мм оси от выхода. Уменьшите "
                "подстройку (обычно хватает одного полутона) или диаметр "
                "дырок: меньшая дырка стоит выше по трубе."
            ) from exc
        placed.append(
            HoleSpec(
                s_mm=s_mm,
                diameter_mm=diameter,
                chimney_mm=chimney,
                note=note,
                target_hz=target,
            )
        )

    holes = tuple(placed)
    fingerings = _evaluate_fingerings(params, body, names, holes)
    return HolePlan(
        scale_id=params.scale,
        tonic=tonic,
        holes=holes,
        fingerings=fingerings,
    )


def resonance_hz(
    params: TubeParams,
    body_length_mm: float,
    holes: tuple[HoleSpec, ...],
    open_from_exit: int,
) -> float:
    """Частота основного резонанса при заданной аппликатуре.

    Принимает параметры, длину корпуса, отверстия по возрастанию номера
    от выхода и сколько из них открыто с выходного конца (0 — все закрыты).
    Ищет частоту, на которой D матрицы от мембраны к открытому концу равен
    нулю. Возвращает герцы. Если нуля рядом с четвертью волны нет,
    поднимает HoleError.
    """
    estimate = _resonance_estimate_hz(params, body_length_mm, holes, open_from_exit)
    low, high, low_d, high_d = _bracket_resonance(
        params, body_length_mm, holes, open_from_exit, estimate
    )
    for _ in range(80):
        middle = (low + high) / 2.0
        mid_d = _resonance_d(params, body_length_mm, holes, open_from_exit, middle)
        if mid_d * low_d > 0.0:
            low, low_d = middle, mid_d
        else:
            high = middle
        if high - low < 1e-6 * estimate:
            break
    return (low + high) / 2.0


def _resonance_estimate_hz(
    params: TubeParams,
    body_length_mm: float,
    holes: tuple[HoleSpec, ...],
    open_from_exit: int,
) -> float:
    """Черновая частота основного тона по длине до ближайшей открытой дырки.

    Принимает параметры, корпус, дырки и сколько их открыто с выхода.
    Без открытых дырок берёт четверть волны корпуса. С открытыми — четверть
    волны до самой ближней к мембране открытой дырки, плюс её боковой канал.
    Возвращает герцы.
    """
    speed_mm = params.speed_of_sound_m_s * 1000.0
    if open_from_exit > 0 and holes:
        by_exit = sorted(holes, key=lambda item: item.s_mm, reverse=True)
        opened = by_exit[:open_from_exit]
        cut = min(opened, key=lambda item: item.s_mm)
        extra = cut.chimney_mm + OPEN_END_CORRECTION_FACTOR * (cut.diameter_mm / 2.0)
        length = max(cut.s_mm + extra + params.delta_head_mm, 1.0)
        return speed_mm / (4.0 * length)
    length = body_length_mm + params.delta_out_mm + params.delta_head_mm
    return speed_mm / (4.0 * max(length, 1.0))


def _bracket_resonance(
    params: TubeParams,
    body_length_mm: float,
    holes: tuple[HoleSpec, ...],
    open_from_exit: int,
    estimate: float,
) -> tuple[float, float, float, float]:
    """Находит интервал частот, на концах которого D меняет знак.

    Принимает параметры, корпус, дырки, сколько открыто с выхода и оценку
    частоты. Берёт несколько точек вокруг оценки, пока не появится смена
    знака. Возвращает (низ, верх, D низа, D верха). Если смены нет,
    поднимает HoleError.
    """
    factors = (0.25, 0.4, 0.55, 0.75, 1.0, 1.3, 1.7, 2.3, 3.2, 4.5, 6.5)
    samples = [max(estimate * factor, 1.0) for factor in factors]
    values = [
        _resonance_d(params, body_length_mm, holes, open_from_exit, frequency)
        for frequency in samples
    ]
    for index in range(len(samples) - 1):
        if values[index] * values[index + 1] <= 0.0:
            return samples[index], samples[index + 1], values[index], values[index + 1]
    raise HoleError("Основной резонанс трубы с отверстиями не найден.")


def _locate_hole(
    params: TubeParams,
    body_length_mm: float,
    already: list[HoleSpec],
    diameter_mm: float,
    chimney_mm: float,
    target_hz: float,
    low_mm: float,
    high_mm: float,
) -> float:
    """Координата s новой дырки под целевую частоту.

    Принимает параметры, длину корпуса, уже поставленные дырки ближе к выходу,
    размер новой дырки, частоту и окно поиска. На краях окна резонанс должен
    обрамлять цель. Возвращает s в миллиметрах.
    """
    probe = HoleSpec(
        s_mm=0.0,
        diameter_mm=diameter_mm,
        chimney_mm=chimney_mm,
        note="",
        target_hz=target_hz,
    )

    def frequency_at(s_mm: float) -> float:
        """Резонанс, если новая дырка стоит на s. Принимает s, возвращает Гц."""
        candidate = HoleSpec(
            s_mm=s_mm,
            diameter_mm=diameter_mm,
            chimney_mm=chimney_mm,
            note=probe.note,
            target_hz=target_hz,
        )
        return resonance_hz(
            params,
            body_length_mm,
            tuple(already + [candidate]),
            open_from_exit=len(already) + 1,
        )

    left, right = _bracket_hole_s(frequency_at, target_hz, low_mm, high_mm)
    f_left = frequency_at(left)
    for _ in range(50):
        middle = (left + right) / 2.0
        f_mid = frequency_at(middle)
        if (f_left - target_hz) * (f_mid - target_hz) > 0.0:
            left, f_left = middle, f_mid
        else:
            right = middle
        if right - left < 0.05:
            break
    return (left + right) / 2.0


def _bracket_hole_s(
    frequency_at: Callable[[float], float],
    target_hz: float,
    low_mm: float,
    high_mm: float,
) -> tuple[float, float]:
    """Сужает окно s так, чтобы частоты на краях обрамляли целевую ноту.

    Принимает функцию s → Гц, целевую частоту и исходные границы канала.
    Сначала пробует края, затем шаг к середине, если на краю резонанс
    не считается или цель вне интервала. Возвращает пару (низ, верх).
    """
    probes = [low_mm, high_mm]
    span = high_mm - low_mm
    for step in (0.15, 0.3, 0.45):
        probes.append(low_mm + span * step)
        probes.append(high_mm - span * step)
    found: list[tuple[float, float]] = []
    for s_mm in probes:
        try:
            found.append((s_mm, frequency_at(s_mm)))
        except HoleError:
            continue
    found.sort(key=lambda item: item[0])
    for (left, f_left), (right, f_right) in zip(found, found[1:]):
        if f_left >= target_hz >= f_right or f_left <= target_hz <= f_right:
            return left, right
    if found:
        lowest = min(item[1] for item in found)
        highest = max(item[1] for item in found)
        raise HoleError(
            f"Целевая нота {target_hz:.2f} Гц не попадает между "
            f"{lowest:.2f} и {highest:.2f} Гц на доступном участке канала."
        )
    raise HoleError(
        f"Отверстие под {target_hz:.2f} Гц не сходится на канале."
    )


def _evaluate_fingerings(
    params: TubeParams,
    body_length_mm: float,
    names: tuple[str, ...],
    holes: tuple[HoleSpec, ...],
) -> tuple[FingeringReport, ...]:
    """Прогноз всех последовательных аппликатур.

    Принимает параметры, корпус, имена нот (тоника плюс ступени) и дырки
    от выхода к мембране. Возвращает отчёт по каждой, начиная с «все закрыты».
    """
    reports: list[FingeringReport] = []
    for open_count, note in enumerate(names):
        target = frequency_hz(midi_number(parse_note_name(note)), params.a4_hz)
        predicted = resonance_hz(params, body_length_mm, holes, open_count)
        reports.append(
            FingeringReport(
                note=note,
                target_hz=target,
                predicted_hz=predicted,
                cents=_cents(predicted, target),
                open_count=open_count,
            )
        )
    return tuple(reports)


def _resonance_d(
    params: TubeParams,
    body_length_mm: float,
    holes: tuple[HoleSpec, ...],
    open_from_exit: int,
    frequency_hz_value: float,
) -> float:
    """Знак резонанса: вещественная часть D матрицы при p_вых = 0.

    Принимает параметры, корпус, дырки, сколько открыто с выхода и частоту.
    D = 0 — основной резонанс закрыто-открытой трубы. Возвращает Re(D).
    """
    k = wave_number(frequency_hz_value, params.speed_of_sound_m_s)
    matrix = _pipe_matrix(params, body_length_mm, holes, open_from_exit, k)
    return float(matrix[1][1].real)


def _pipe_matrix(
    params: TubeParams,
    body_length_mm: float,
    holes: tuple[HoleSpec, ...],
    open_from_exit: int,
    k: float,
):
    """Матрица от мембраны до открытого конца с поправкой Δ_out.

    Принимает параметры, корпус, дырки от выхода, сколько из них открыто
    и волновое число. Собирает посадку, конус, цилиндры между дырками,
    шунты дырок и концевую поправку. Возвращает матрицу 2×2.
    """
    body_radius = params.bore_diameter_mm / 2.0
    matrix = _front_matrix(params, k)
    cursor = params.joint_length_mm if params.has_transition else 0.0
    # Дырки от мембраны к выходу: уже поставленные ближе к выходу имеют большее s.
    along = sorted(holes, key=lambda item: item.s_mm)
    total = len(along)
    for order, spec in enumerate(along):
        if spec.s_mm + 1e-9 < cursor:
            continue
        matrix = multiply(matrix, cylinder_matrix(k, spec.s_mm - cursor, body_radius))
        # open_from_exit считает от выхода: дырка с наибольшим s — номер 0.
        index_from_exit = total - 1 - order
        opened = index_from_exit < open_from_exit
        matrix = multiply(matrix, _hole_shunt(k, spec, opened))
        cursor = spec.s_mm
    rest = body_length_mm - cursor
    if rest > 1e-9:
        matrix = multiply(matrix, cylinder_matrix(k, rest, body_radius))
    delta = params.delta_out_mm
    if delta > 1e-9:
        matrix = multiply(matrix, cylinder_matrix(k, delta, body_radius))
    return matrix


def _front_matrix(params: TubeParams, k: float):
    """Матрица посадки и переходника.

    Принимает параметры и волновое число. Без переходника — единичная
    матрица: канал сразу трубы. С переходником — цилиндр посадки и
    лесенка конуса. Возвращает матрицу 2×2.
    """
    if not params.has_transition:
        return IDENTITY
    seat_radius = params.seat_bore_diameter_mm / 2.0
    body_radius = params.bore_diameter_mm / 2.0
    matrix = cylinder_matrix(k, params.seat_length_mm, seat_radius)
    step = params.transition_length_mm / _CONE_STEPS
    for index in range(_CONE_STEPS):
        fraction = (index + 0.5) / _CONE_STEPS
        radius = seat_radius + (body_radius - seat_radius) * fraction
        matrix = multiply(matrix, cylinder_matrix(k, step, radius))
    return matrix


def _hole_shunt(k: float, spec: HoleSpec, opened: bool):
    """Шунт одного отверстия.

    Принимает волновое число, размеры дырки и открыта ли она.
    Открытая — короткий канал в атмосферу с поправкой 0,6 радиуса дырки.
    Закрытая — тот же канал, заглушённый пальцем: остаётся боковой объём.
    Возвращает матрицу шунта.
    """
    hole_radius = spec.diameter_mm / 2.0
    impedance = 1.0 / (math.pi * hole_radius * hole_radius)
    if opened:
        length = spec.chimney_mm + OPEN_END_CORRECTION_FACTOR * hole_radius
        tangent = math.tan(k * length)
        if abs(tangent) < 1e-12:
            admittance = 1e12 + 0j
        else:
            admittance = -1j / (impedance * tangent)
    else:
        tangent = math.tan(k * spec.chimney_mm)
        admittance = 1j * tangent / impedance
    return shunt_matrix(admittance)


def _cents(frequency: float, reference: float) -> float:
    """Отклонение частоты от опорной в центах.

    Принимает две частоты в герцах. Считает 1200 · log2(f / f_оп).
    Возвращает положительное число, когда первая частота выше опорной.
    """
    return 1200.0 * math.log2(frequency / reference)


def _format_mm(value: float) -> str:
    """Миллиметры для текста ошибки: один знак, запятая, без хвостовых нулей.

    Принимает число. Возвращает строку.
    """
    return f"{value:.1f}".rstrip("0").rstrip(".").replace(".", ",")
