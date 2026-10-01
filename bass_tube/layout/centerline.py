"""Осевая линия укладки в пространстве: прямые и дуги 180°, без сглаживания.

Координата s идёт от плоскости стыка с модулем мембраны до выхода.
s = 0 — этот стык, верх первой прямой. Ось z смотрит вверх, стол — z = 0.
Прямые вертикальные. Разворот — полуокружность в вертикальной плоскости,
проходящей через оси двух соседних прямых. Первый разворот снизу, следующий
сверху. Касательная на стыке прямой и дуги совпадает.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bass_tube.layout.coil import Coil


class CenterlineError(ValueError):
    """Ось нельзя построить или координата s лежит вне неё. Текст — причина."""


@dataclass(frozen=True, slots=True)
class Vec3:
    """Точка или вектор в пространстве, миллиметры. z растёт вверх."""

    x: float
    y: float
    z: float

    def plus(self, other: Vec3, scale: float = 1.0) -> Vec3:
        """Сумма с другим вектором, умноженным на число.

        Принимает вектор и множитель. Возвращает self + scale · other.
        """
        return Vec3(
            self.x + other.x * scale,
            self.y + other.y * scale,
            self.z + other.z * scale,
        )

    def dot(self, other: Vec3) -> float:
        """Скалярное произведение.

        Принимает вектор. Возвращает число.
        """
        return self.x * other.x + self.y * other.y + self.z * other.z


_UP = Vec3(0.0, 0.0, 1.0)
_DOWN = Vec3(0.0, 0.0, -1.0)


@dataclass(frozen=True, slots=True)
class AxisFrame:
    """Положение и единичная касательная на одной координате s."""

    s_mm: float
    point: Vec3
    tangent: Vec3


@dataclass(frozen=True, slots=True)
class Straight:
    """Прямой участок оси.

    s_start_mm и s_end_mm — диапазон вдоль канала. origin — точка при s_start,
    direction — единичная касательная, постоянная на всём участке.
    """

    length_mm: float
    s_start_mm: float
    s_end_mm: float
    origin: Vec3
    direction: Vec3

    def point(self, distance_mm: float) -> Vec3:
        """Точка прямой на расстоянии от её начала.

        Принимает расстояние вдоль участка в миллиметрах.
        Сдвигает origin на direction, умноженный на это расстояние.
        Возвращает точку.
        """
        return self.origin.plus(self.direction, distance_mm)

    def tangent(self, distance_mm: float) -> Vec3:
        """Единичная касательная прямой.

        Принимает расстояние вдоль участка: на прямой направление от него
        не зависит. Возвращает direction.
        """
        del distance_mm
        return self.direction


@dataclass(frozen=True, slots=True)
class Turn:
    """Дуга оси на 180° в вертикальной плоскости.

    Точка при угле θ: center + R·(cos θ · axis_u + sin θ · z). axis_u —
    горизонтальный единичный вектор от первой прямой ко второй.
    Угол идёт от angle_start к angle_end: снизу от π до 2π, сверху от π до 0.
    Длина дуги равна радиусу, умноженному на π.
    """

    length_mm: float
    s_start_mm: float
    s_end_mm: float
    center: Vec3
    radius_mm: float
    axis_u: Vec3
    angle_start: float
    angle_end: float

    def point(self, distance_mm: float) -> Vec3:
        """Точка дуги на расстоянии от её начала.

        Принимает расстояние вдоль дуги в миллиметрах.
        Переводит его в угол и кладёт точку на окружность.
        Возвращает точку.
        """
        theta = self._angle(distance_mm)
        return self.center.plus(self.axis_u, self.radius_mm * math.cos(theta)).plus(
            _UP, self.radius_mm * math.sin(theta)
        )

    def tangent(self, distance_mm: float) -> Vec3:
        """Единичная касательная дуги.

        Принимает расстояние вдоль дуги в миллиметрах.
        Берёт производную окружности в сторону роста s.
        Возвращает вектор длины 1.
        """
        theta = self._angle(distance_mm)
        sign = 1.0 if self.angle_end >= self.angle_start else -1.0
        return Vec3(0.0, 0.0, 0.0).plus(self.axis_u, -sign * math.sin(theta)).plus(
            _UP, sign * math.cos(theta)
        )

    def _angle(self, distance_mm: float) -> float:
        """Угол окружности на расстоянии от начала дуги.

        Принимает расстояние вдоль дуги в миллиметрах.
        Делит его на радиус и прибавляет к angle_start со знаком обхода.
        Возвращает угол в радианах.
        """
        sign = 1.0 if self.angle_end >= self.angle_start else -1.0
        return self.angle_start + sign * distance_mm / self.radius_mm


AxisPrimitive = Straight | Turn


@dataclass(frozen=True, slots=True)
class Centerline:
    """Список примитивов оси от стыка с модулем до выхода."""

    primitives: tuple[AxisPrimitive, ...]
    length_mm: float

    def primitive_at(self, s_mm: float) -> AxisPrimitive:
        """Примитив, на котором лежит координата s.

        Принимает s в миллиметрах от плоскости стыка. На стыке двух примитивов
        возвращает следующий: это та же точка, что и конец предыдущего.
        Последняя точка оси принадлежит последнему примитиву.
        Возвращает прямую или дугу. Если s вне оси, поднимает CenterlineError.
        """
        s_mm = _clamp_axis_s(s_mm, self.length_mm)
        last = self.primitives[-1]
        for primitive in self.primitives:
            if s_mm < primitive.s_end_mm or primitive is last:
                return primitive
        return last

    def sample(self, s_mm: float) -> AxisFrame:
        """Точка и касательная на координате s.

        Принимает s в миллиметрах от плоскости стыка. Находит примитив и
        считает положение и единичную касательную по его формуле, без ломаной.
        Возвращает AxisFrame. Если s вне оси, поднимает CenterlineError.
        """
        s_mm = _clamp_axis_s(s_mm, self.length_mm)
        primitive = self.primitive_at(s_mm)
        distance = s_mm - primitive.s_start_mm
        return AxisFrame(
            s_mm=s_mm,
            point=primitive.point(distance),
            tangent=primitive.tangent(distance),
        )


def build_centerline(coil: Coil, joint_length_mm: float) -> Centerline:
    """Собирает ось укладки из её прямых и разворотов.

    Принимает укладку и длину стыка от мембраны: посадка с переходником.
    Ставит s = 0 на верхний торец первой прямой. Чётные прямые идут вниз,
    нечётные вверх, между ними дуги 180°. Весь стык остаётся на первой прямой.
    Возвращает Centerline, сумма длин которой равна длине оси укладки.
    Если прямых нет, число столбцов не совпало или стык длиннее первой
    прямой, поднимает CenterlineError.
    """
    lengths = coil.straight_lengths_mm
    if not lengths:
        raise CenterlineError("В укладке нет прямых.")
    if len(coil.columns) != len(lengths):
        raise CenterlineError("Число столбцов укладки не совпало с числом прямых.")
    if lengths[0] + 1e-9 < joint_length_mm:
        raise CenterlineError(
            "Стык "
            f"{_format_mm(joint_length_mm)} мм не лежит на первой прямой "
            f"длиной {_format_mm(lengths[0])} мм."
        )

    primitives: list[AxisPrimitive] = []
    s_mm = 0.0
    z_mm = coil.inlet_z_mm
    last = len(lengths) - 1
    for index, length in enumerate(lengths):
        primitives.append(_straight(coil, index, length, s_mm, z_mm))
        s_mm += length
        z_mm = z_mm - length if index % 2 == 0 else z_mm + length
        if index == last:
            continue
        primitives.append(_turn(coil, index, s_mm, z_mm))
        s_mm += coil.turn_length_mm

    return Centerline(primitives=tuple(primitives), length_mm=s_mm)


def _straight(
    coil: Coil,
    index: int,
    length_mm: float,
    s_start_mm: float,
    z_start_mm: float,
) -> Straight:
    """Прямая с номером index, начиная с заданной высоты.

    Принимает укладку, номер с нуля, длину участка, s начала и z начала.
    Чётные прямые идут вниз, нечётные вверх. Первая длиннее на подъём входа,
    последняя — на ход сквозь цоколь; средние одинаковы, поэтому все нижние
    колени лежат на одной высоте. Возвращает Straight.
    """
    x_mm, y_mm = coil.columns[index]
    direction = _DOWN if index % 2 == 0 else _UP
    return Straight(
        length_mm=length_mm,
        s_start_mm=s_start_mm,
        s_end_mm=s_start_mm + length_mm,
        origin=Vec3(x_mm, y_mm, z_start_mm),
        direction=direction,
    )


def _turn(coil: Coil, straight_index: int, s_start_mm: float, z_mm: float) -> Turn:
    """Разворот после прямой с номером straight_index на высоте z.

    Принимает укладку, номер прямой, s начала дуги и высоту центра.
    Центр — посередине между осями двух прямых. Снизу угол идёт от π до 2π,
    сверху от π до 0. Возвращает Turn.
    """
    first = coil.columns[straight_index]
    second = coil.columns[straight_index + 1]
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    span = math.hypot(dx, dy)
    if span < 1e-9:
        raise CenterlineError("Две соседние прямые стоят в одной точке.")
    bottom = straight_index % 2 == 0
    return Turn(
        length_mm=coil.turn_length_mm,
        s_start_mm=s_start_mm,
        s_end_mm=s_start_mm + coil.turn_length_mm,
        center=Vec3((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0, z_mm),
        radius_mm=coil.turn_radius_mm,
        axis_u=Vec3(dx / span, dy / span, 0.0),
        angle_start=math.pi,
        angle_end=2.0 * math.pi if bottom else 0.0,
    )


def _clamp_axis_s(s_mm: float, length_mm: float) -> float:
    """Проверяет, что s лежит на оси, и убирает численный хвост у концов.

    Принимает координату и длину оси в миллиметрах. Возвращает s,
    прижатую к отрезку, если она уехала на доли нанометра.
    Если s явно вне оси, поднимает CenterlineError.
    """
    if s_mm < -1e-9 or s_mm > length_mm + 1e-9:
        raise CenterlineError(
            f"Координата s {_format_mm(s_mm)} мм вне оси длиной {_format_mm(length_mm)} мм."
        )
    if s_mm < 0.0:
        return 0.0
    if s_mm > length_mm:
        return length_mm
    return s_mm


def _format_mm(value: float) -> str:
    """Форматирует миллиметры для текста причины.

    Принимает число. Возвращает короткую запись: целое без дроби,
    иначе до трёх знаков после запятой без хвостовых нулей.
    """
    rounded = round(float(value), 3)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.3f}".rstrip("0").rstrip(".")
