"""Большой аудит укладок G1…G2: дырки от шести до восьми, все лады, пары с дроном.

Считается без CAD, в восемь процессов, несколько минут. В обычном прогоне
пропускается; запуск: pytest -m audit. Каждый вариант должен уложиться:
вязанка не из одной прямой, дырки на месте, при высоте выше стола разрезы
находятся мимо колен, дырок и царги. Без разрезов допускается отказ,
который называет нужную высоту печати. Подстройка на два полутона с ладом,
у которого первая ступень — целый тон, физически не встаёт (царга
длиннее места под первую дырку) и в аудит не входит.
"""

from concurrent.futures import ProcessPoolExecutor
from itertools import product

import pytest

NOTES = ("G1", "G#1", "A1", "A#1", "B1", "C2", "C#2", "D2", "D#2", "E2", "F2", "F#2", "G2")
SCALES = ("major", "natural_minor", "melodic_minor", "pentatonic", "major_pentatonic")
HOLE_COUNTS = (6, 7, 8)
# (высота стола, диаметр дырки, подстройка, разрезы)
SINGLE_SETUPS = (
    (250.0, 8.0, 1, True),
    (250.0, 8.0, 0, False),
    (200.0, 8.0, 1, True),
    (200.0, 10.0, 1, True),
    (150.0, 6.0, 0, True),
)
_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

pytestmark = pytest.mark.audit


def _box(height: float, splits: bool, trim: int) -> dict:
    """Габарит окна по умолчанию с заданной высотой, разрезами и подстройкой.

    Принимает высоту стола, флаг разрезов и полутоны подстройки.
    Возвращает словарь для tube_params.
    """
    return {
        "layout": "bundle",
        "max_height_mm": height,
        "max_width_mm": 150.0,
        "max_depth_mm": 150.0,
        "head_reserve_mm": 35.0,
        "turn_radius_mm": 11.0,
        "gap_mm": 1.0,
        "trim_semitones": trim,
        "print_splits": splits,
    }


def check_single(case: tuple) -> str | None:
    """Считает одну трубу с дырками и проверяет укладку.

    Принимает (нота, число дырок, лад, высота, диаметр, подстройка, разрезы).
    Без разрезов честный отказ с нужной высотой печати тоже годится: восемь
    частых дырок коротких труб при колене, не касающемся соседа по
    шестиграннику, в 250 мм одной деталью не встают, с разрезами — встают.
    Возвращает None, если всё сошлось, иначе текст проблемы.
    """
    from bass_tube.acoustics.trim import socket_length_mm
    from bass_tube.design import plan_design
    from bass_tube.layout.print_cuts import coil_cut_heights
    from bass_tube.params import tube_params

    note, count, scale, height, diameter, trim, splits = case
    try:
        params = tube_params(
            note=note, hole_count=count, scale=scale, hole_diameter_mm=diameter,
            **_box(height, splits, trim),
        )
        plan = plan_design(params)
    except Exception as exc:
        if not splits and "Влезет при высоте печати" in str(exc):
            return None
        return f"{case}: {type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    coil = plan.coil
    if coil.straight_count < 3:
        return f"{case}: одна прямая"
    if len(plan.placed_holes) != count:
        return f"{case}: дырок {len(plan.placed_holes)}"
    if coil.height_with_head_mm > height + 1e-9:
        if not splits:
            return f"{case}: выше стола без разрезов"
        try:
            coil_cut_heights(
                coil, params,
                holes=tuple((hole.spec.s_mm, hole.spec.diameter_mm) for hole in plan.placed_holes),
                bottom_keep_mm=socket_length_mm(plan.trim) if plan.trim is not None else 0.0,
            )
        except Exception as exc:
            return f"{case}: разрез: {exc}"
    return None


def check_pair(case: tuple) -> str | None:
    """Считает пару мелодия с дырками + дрон и проверяет входы.

    Принимает (нота, число дырок, лад, высота, интервал дрона вверх).
    Входы на 48 мм и на одной высоте, обе вязанки не из одной прямой.
    Возвращает None, если всё сошлось, иначе текст проблемы.
    """
    import math

    from bass_tube.acoustics.notes import midi_number, parse_note_name
    from bass_tube.pair import inlet_distance_mm, plan_voice_pair
    from bass_tube.params import tube_params

    note, count, scale, height, interval = case
    midi = midi_number(parse_note_name(note)) + interval
    drone = f"{_NAMES[midi % 12]}{midi // 12 - 1}"
    try:
        params = tube_params(
            note=note, hole_count=count, scale=scale, drone_note=drone,
            drone_trim_semitones=1, **_box(height, True, 1),
        )
        plan = plan_voice_pair(params)
    except Exception as exc:
        return f"{case} дрон {drone}: {type(exc).__name__}: {str(exc).splitlines()[0][:160]}"
    if not math.isclose(inlet_distance_mm(plan), 48.0, abs_tol=1e-6):
        return f"{case}: шаг входов {inlet_distance_mm(plan)}"
    if not math.isclose(plan.melody.coil.inlet_z_mm, plan.drone.coil.inlet_z_mm, abs_tol=1e-6):
        return f"{case}: входы на разной высоте"
    if min(plan.melody.coil.straight_count, plan.drone.coil.straight_count) < 3:
        return f"{case}: одна прямая"
    return None


def _run(check, cases: list) -> list[str]:
    """Прогоняет проверку по всем вариантам в восемь процессов.

    Принимает функцию проверки и список вариантов. Возвращает тексты проблем.
    """
    with ProcessPoolExecutor(max_workers=8) as pool:
        return [text for text in pool.map(check, cases, chunksize=4) if text]


def test_all_hole_layouts_g1_to_g2() -> None:
    """Все трубы G1…G2 с 6–8 дырками во всех ладах укладываются при пяти габаритах.

    Ничего не принимает. Ничего не возвращает.
    """
    cases = [
        (note, count, scale, *setup)
        for note, count, scale, setup in product(NOTES, HOLE_COUNTS, SCALES, SINGLE_SETUPS)
    ]
    problems = _run(check_single, cases)
    assert not problems, "\n".join(problems[:40])


def test_all_pairs_g1_to_g2() -> None:
    """Пары G1…G2 с 6–8 дырками и дроном на тонику или квинту складываются одной деталью.

    Ничего не принимает. Столы 250 и 200 мм с разрезами. Ничего не возвращает.
    """
    cases = list(product(NOTES, HOLE_COUNTS, ("major", "natural_minor", "pentatonic"), (250.0, 200.0), (0, 7)))
    problems = _run(check_pair, cases)
    assert not problems, "\n".join(problems[:40])
