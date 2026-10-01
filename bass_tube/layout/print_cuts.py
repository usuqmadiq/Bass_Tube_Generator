"""Где резать собранную вязанку на куски стола, не задев колени и дырки.

Считается без CAD, по одной укладке: укладка и подбор дырок проверяют,
что разрез вообще найдётся, а тело потом режется по тем же высотам.
Стык — «папа — мама»: папа — внутренняя половина стенки нижнего куска,
торчит вверх на длину штекера; мама — наружная половина стенки верхнего
куска, надевается на папу. Канал и наружная стенка идут без ступенек.
Плоскость разреза не проходит через колено, посадку модуля, дырку,
цоколь и царгу подстройки или слайдера; папа (он выше разреза на длину
штекера) не закрывает изнутри дырку и не упирается в верхнее колено или
посадку. Штекер ставится только на ту прямую, которая проходит сквозь
плоскость разреза.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from bass_tube.constants import PRINT_PLUG_MM
from bass_tube.params import TubeParams

if TYPE_CHECKING:
    from bass_tube.layout.coil import Coil

# Запас от плоскости разреза до колена, дырки или посадки, мм.
_CLEAR_MM = 1.0
# Сколько прямой должно остаться ниже разреза под основанием папы, мм.
_BELOW_MM = 2.0


class PrintCutError(ValueError):
    """Разрез на куски стола не находится: мешают колени, дырки или царга."""


@dataclass(frozen=True, slots=True)
class ColumnSpan:
    """Прямая укладки как вертикальный отрезок оси.

    x_mm, y_mm — центр прямой в плане. z_low_mm и z_high_mm — нижний и
    верхний конец прямой по оси (без колен).
    """

    x_mm: float
    y_mm: float
    z_low_mm: float
    z_high_mm: float

    def crosses(self, z_cut_mm: float, plug_mm: float = PRINT_PLUG_MM) -> bool:
        """Проходит ли прямая сквозь разрез с местом под штекер.

        Принимает высоту разреза и длину штекера. Выше разреза прямая
        должна идти не меньше штекера (там папа и мама), ниже — хотя бы
        под основание папы. Возвращает True, если на эту прямую нужен штекер.
        """
        return (
            self.z_low_mm < z_cut_mm - 0.1
            and self.z_high_mm > z_cut_mm + plug_mm + 0.1
        )


def column_spans(coil: Coil) -> tuple[ColumnSpan, ...]:
    """Вертикальные отрезки всех прямых укладки.

    Принимает укладку. Первая прямая идёт вниз от входа, дальше
    направление чередуется, как у оси. Возвращает кортеж ColumnSpan
    по ходу канала.
    """
    spans: list[ColumnSpan] = []
    z_mm = coil.inlet_z_mm
    for index, length in enumerate(coil.straight_lengths_mm):
        end = z_mm - length if index % 2 == 0 else z_mm + length
        x_mm, y_mm = coil.columns[index]
        spans.append(ColumnSpan(x_mm, y_mm, min(z_mm, end), max(z_mm, end)))
        z_mm = end
    return tuple(spans)


def hole_levels(coil: Coil, holes: Iterable[tuple[float, float]]) -> tuple[tuple[float, float], ...]:
    """Высоты центров дырок над столом.

    Принимает укладку и пары (s дырки по оси от стыка, диаметр). Дырка,
    попавшая на колено, в резах не учитывается: такой укладки и так нет.
    Возвращает пары (z центра, диаметр).
    """
    result: list[tuple[float, float]] = []
    lengths = coil.straight_lengths_mm
    for s_mm, diameter in holes:
        start = 0.0
        z_mm = coil.inlet_z_mm
        for index, length in enumerate(lengths):
            if s_mm <= start + length + 1e-9:
                along = s_mm - start
                level = z_mm - along if index % 2 == 0 else z_mm + along
                result.append((level, diameter))
                break
            z_mm = z_mm - length if index % 2 == 0 else z_mm + length
            start += length + coil.turn_length_mm
            if s_mm < start:
                break
    return tuple(result)


def keep_out_bands(
    coil: Coil,
    params: TubeParams,
    *,
    holes: Iterable[tuple[float, float]] = (),
    bottom_keep_mm: float = 0.0,
    plug_mm: float = PRINT_PLUG_MM,
) -> tuple[tuple[float, float], ...]:
    """Полосы высот, в которых плоскость разреза стоять не может.

    Принимает укладку, параметры, дырки парами (s, диаметр), длину царги
    подстройки или слайдера от стола и длину штекера. Цоколь и царга:
    разрез выше них, с местом под основание папы. Нижнее колено: разрез
    не внутри дуги и не вплотную над ней. Верхнее колено и посадка модуля:
    папа, торчащий вверх на длину штекера, до них не достаёт. Дырка: не
    сквозь неё и не ниже неё на длину папы — папа закрыл бы её изнутри.
    Возвращает кортеж пар (низ, верх) в миллиметрах.
    """
    radius = coil.turn_radius_mm
    outer = params.outer_diameter_mm
    bands: list[tuple[float, float]] = [
        (-1e9, max(coil.base_height_mm, bottom_keep_mm) + _BELOW_MM + _CLEAR_MM)
    ]
    z_mm = coil.inlet_z_mm
    last = coil.straight_count - 1
    for index, length in enumerate(coil.straight_lengths_mm):
        z_mm = z_mm - length if index % 2 == 0 else z_mm + length
        if index == last:
            break
        if index % 2 == 0:
            bands.append((z_mm - radius - outer / 2.0 - _CLEAR_MM, z_mm + _BELOW_MM + _CLEAR_MM))
        else:
            bands.append((z_mm - plug_mm - _CLEAR_MM, z_mm + radius + outer / 2.0 + _CLEAR_MM))
    inlet = coil.inlet_z_mm
    bands.append((inlet - params.joint_length_mm - plug_mm - _CLEAR_MM, 1e9))
    for level, diameter in hole_levels(coil, holes):
        half = diameter / 2.0
        bands.append((level - half - plug_mm - _CLEAR_MM, level + half + _CLEAR_MM))
    return tuple(bands)


def cut_heights(
    z_min_mm: float,
    z_max_mm: float,
    max_height_mm: float,
    plug_mm: float = PRINT_PLUG_MM,
    bands: Iterable[tuple[float, float]] = (),
) -> list[float]:
    """Высоты горизонтальных разрезов снизу вверх, не включая концы.

    Принимает диапазон детали, высоту стола, длину штекера и запретные
    полосы. Каждый кусок, кроме верхнего, не выше стола вместе с папой,
    который торчит вверх на длину штекера; верхний — просто не выше стола.
    Каждый разрез ставится как можно выше и опускается под запретную
    полосу, если попал в неё; над маминым гнездом куска снизу он не
    встаёт. Возвращает список z разрезов. Если между полосами места нет,
    поднимает PrintCutError.
    """
    if z_max_mm - z_min_mm <= max_height_mm + 1e-9:
        return []
    unique = max_height_mm - plug_mm
    if unique <= 1e-6:
        raise PrintCutError("Штекер разреза не короче высоты печати: куски некуда класть.")
    blocked = sorted(bands)
    cuts: list[float] = []
    cursor = z_min_mm
    floor = z_min_mm + _BELOW_MM
    while cursor + max_height_mm < z_max_mm - 1e-9:
        reach = cursor + unique
        cut = _below_bands(reach, blocked)
        if cut < floor:
            raise PrintCutError(
                "Не найти высоту разреза: на участке "
                f"{_format_mm(cursor)}–{_format_mm(reach)} мм сплошь колени, "
                "дырки, посадка или царга. Поднимите высоту печати или "
                "выключите разрезы."
            )
        cuts.append(cut)
        cursor = cut
        floor = cut + plug_mm + _BELOW_MM
    return cuts


def coil_cut_heights(
    coil: Coil,
    params: TubeParams,
    *,
    holes: Iterable[tuple[float, float]] = (),
    bottom_keep_mm: float = 0.0,
) -> list[float]:
    """Высоты разрезов одной укладки от стола до верха.

    Принимает укладку, параметры, дырки парами (s, диаметр) и длину царги
    от стола. Возвращает список z разрезов (пустой, если деталь не выше
    стола). Если разрез не находится, поднимает PrintCutError.
    """
    bands = keep_out_bands(coil, params, holes=holes, bottom_keep_mm=bottom_keep_mm)
    return cut_heights(0.0, coil.height_mm, params.max_height_mm, PRINT_PLUG_MM, bands)


def _below_bands(z_mm: float, bands: list[tuple[float, float]]) -> float:
    """Опускает высоту под все запретные полосы, в которые она попала.

    Принимает высоту и полосы, отсортированные по низу. Повторяет, пока
    высота лежит внутри какой-нибудь полосы. Возвращает новую высоту.
    """
    moved = True
    while moved:
        moved = False
        for low, high in bands:
            if low < z_mm < high:
                z_mm = low - 1e-3
                moved = True
    return z_mm


def _format_mm(value: float) -> str:
    """Число миллиметров для текста: без лишних нулей, запятая.

    Принимает значение. Возвращает строку с одним знаком после запятой.
    """
    text = f"{value:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")
