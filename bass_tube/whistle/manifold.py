"""Коллектор-пленум пары свистков: один входной порт, два ветровых канала.

Отдельная надеваемая деталь над двумя одинаковыми головами на шаге пары:
неглубокие карманы садятся на выступающие концы щёк (и заодно прижимают
съёмные крышки), спереди общая камера, в её стенке один круглый порт.
Воздух соединяется только ПЕРЕД ветровыми каналами; акустические полости
после лабиумов не соединяются — иначе пропадает независимая настройка.
Герметичность стыков печать не гарантирует: карманы и крышки при
эксперименте прижимаются и герметизируются снаружи, как и у одной головы.
Объём пленума акустически не калиброван; общая подача может связывать
голоса (см. источники паспорта прототипа).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bass_tube.whistle.params import WhistleHeadParams

Point3 = tuple[float, float, float]
_OVERSHOOT_MM = 0.5
_CAVITY_JOIN_MM = 0.1
# Запас между дном кармана и круглым телом головки: карман туда не лезет.
_NECK_MARGIN_MM = 0.5


class WhistleManifoldError(ValueError):
    """Коллектор нельзя собрать на эту пару голов. Текст — причина."""


@dataclass(frozen=True, slots=True)
class ManifoldParams:
    """Размеры коллектора над двумя одинаковыми головами.

    head — геометрия голов (обе ветви одинаковы). spacing_mm — шаг осей
    голов, как у пары мембран. wall_mm — стенка коллектора.
    fit_clearance_mm — зазор карманов на сторону (проверяется на принтере).
    plenum_depth_mm — глубина общей камеры перед входами щелей.
    port_diameter_mm — круглый входной порт в передней стенке, по центру.
    grip_mm — глубина кармана по щеке; None — весь выступ щеки за круглое
    тело минус запас. Координаты — сборочные: головы в своих осях на
    y = ±spacing/2, x и z — как у головы.
    """

    head: WhistleHeadParams
    spacing_mm: float = 48.0
    wall_mm: float = 2.0
    fit_clearance_mm: float = 0.15
    plenum_depth_mm: float = 10.0
    port_diameter_mm: float = 8.0
    grip_mm: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.head, WhistleHeadParams):
            raise WhistleManifoldError("head: нужны параметры головы WhistleHeadParams.")
        reasons: list[str] = []
        numbers = (
            ("spacing_mm", self.spacing_mm, True),
            ("wall_mm", self.wall_mm, True),
            ("fit_clearance_mm", self.fit_clearance_mm, False),
            ("plenum_depth_mm", self.plenum_depth_mm, True),
            ("port_diameter_mm", self.port_diameter_mm, True),
        )
        for name, value, positive in numbers:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                reasons.append(f"{name}: нужно конечное число")
            elif value <= 0.0 if positive else value < 0.0:
                limit = "положительное" if positive else "неотрицательное"
                reasons.append(f"{name}: нужно {limit} число")
        if self.grip_mm is not None and (
            isinstance(self.grip_mm, bool)
            or not isinstance(self.grip_mm, (int, float))
            or not math.isfinite(self.grip_mm)
            or self.grip_mm <= 0.0
        ):
            reasons.append("grip_mm: нужно положительное число или None")
        if reasons:
            raise WhistleManifoldError("; ".join(reasons))

        if self.spacing_mm - 2.0 * self.pocket_half_width_mm < 1.0:
            raise WhistleManifoldError(
                "Шаг пары слишком мал: карманы голов сливаются, между ними "
                "не остаётся перемычки."
            )
        protrusion = -self.neck_radius_mm - self.head.wind_inlet_x_mm
        if self.grip_resolved_mm < 2.0:
            raise WhistleManifoldError(
                f"Щека головы выступает за круглое тело лишь на "
                f"{protrusion:.2f} мм: карману коллектора нужно не меньше "
                f"2 мм хвата. Удлините ветровой канал головы."
            )
        if self.pocket_end_x_mm > -self.neck_radius_mm - self.fit_clearance_mm:
            raise WhistleManifoldError(
                f"Хват кармана {self.grip_resolved_mm:.2f} мм налезает на "
                f"круглое тело головы: доступно не больше "
                f"{protrusion - self.fit_clearance_mm - _NECK_MARGIN_MM:.2f} мм."
            )
        if self.port_diameter_mm > self.cavity_top_z_mm - 1.0:
            raise WhistleManifoldError(
                f"Порт {self.port_diameter_mm:.1f} мм не умещается по высоте "
                f"камеры {self.cavity_top_z_mm:.1f} мм."
            )

    @property
    def neck_radius_mm(self) -> float:
        return self.head.socket_outer_diameter_mm / 2.0

    @property
    def pocket_half_width_mm(self) -> float:
        """Полуширина кармана: полкорпуса щеки плюс зазор посадки."""
        return self.head.windway_width_mm / 2.0 + self.head.wall_mm + self.fit_clearance_mm

    @property
    def grip_resolved_mm(self) -> float:
        """Фактическая глубина кармана по щеке."""
        if self.grip_mm is not None:
            return float(self.grip_mm)
        protrusion = -self.neck_radius_mm - self.head.wind_inlet_x_mm
        return protrusion - self.fit_clearance_mm - _NECK_MARGIN_MM

    @property
    def pocket_end_x_mm(self) -> float:
        return self.head.wind_inlet_x_mm + self.grip_resolved_mm

    @property
    def plenum_start_x_mm(self) -> float:
        return self.head.wind_inlet_x_mm - self.plenum_depth_mm

    @property
    def outer_start_x_mm(self) -> float:
        return self.plenum_start_x_mm - self.wall_mm

    @property
    def cavity_top_z_mm(self) -> float:
        """Потолок камеры и карманов: верх головы с крышкой плюс зазор."""
        return self.head.body_top_z_mm + self.fit_clearance_mm

    @property
    def outer_half_width_mm(self) -> float:
        return self.spacing_mm / 2.0 + self.pocket_half_width_mm + self.wall_mm

    @property
    def port_center(self) -> Point3:
        """Центр порта на наружной передней стенке."""
        return (self.outer_start_x_mm, 0.0, self.cavity_top_z_mm / 2.0)

    @property
    def inlet_centers(self) -> tuple[Point3, Point3]:
        """Центры входов щелей обеих голов в сборочных координатах."""
        x = self.head.wind_inlet_x_mm
        z = self.head.jet_center_z_mm
        return ((x, -self.spacing_mm / 2.0, z), (x, self.spacing_mm / 2.0, z))


@dataclass(frozen=True)
class ManifoldParts:
    """Построенный коллектор в сборочных координатах пары.

    solid — одна деталь CadQuery. params — размеры. Карманы открыты назад
    (+x) и вниз до низа щеки: головы вставляются концами щёк, крышки при
    этом прижаты потолком карманов. print_part ставит деталь портом вниз
    на z = 0: камера и карманы печатаются без поддержек, перемычка над
    камерой — короткий мост.
    """

    solid: object
    params: ManifoldParams

    def print_part(self):
        """Деталь в печатной ориентации: порт вниз, низ на z = 0."""
        rotated = self.solid.rotate((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), -90.0)
        return rotated.translate((0.0, 0.0, -self.params.outer_start_x_mm))


def build_manifold(params: ManifoldParams) -> ManifoldParts:
    """Строит коллектор: наружная коробка, камера, два кармана и порт.

    Принимает проверенные размеры. Камера и карманы — один воздух,
    он соединяется с головами только перед их ветровыми каналами.
    Возвращает ManifoldParts. Если деталь не вышла одним валидным телом
    или перекрыла задуманные проходы, поднимает WhistleManifoldError.
    """
    import cadquery as cq

    p = params
    eps = _OVERSHOOT_MM
    x0 = p.outer_start_x_mm
    xp = p.plenum_start_x_mm
    x_in = p.head.wind_inlet_x_mm
    x1 = p.pocket_end_x_mm
    top = p.cavity_top_z_mm
    half = p.outer_half_width_mm
    wy = p.pocket_half_width_mm

    box = _box(x0, x1, -half, half, -p.wall_mm, top + p.wall_mm)
    plenum = _box(xp, x_in + _CAVITY_JOIN_MM, -(half - p.wall_mm), half - p.wall_mm, 0.0, top)
    cutters = [plenum]
    for center in (-p.spacing_mm / 2.0, p.spacing_mm / 2.0):
        cutters.append(_box(x_in - _CAVITY_JOIN_MM, x1 + eps, center - wy, center + wy, 0.0, top))
    port = cq.Solid.makeCylinder(
        p.port_diameter_mm / 2.0,
        p.wall_mm + eps + _CAVITY_JOIN_MM,
        cq.Vector(x0 - eps, 0.0, p.port_center[2]),
        cq.Vector(1.0, 0.0, 0.0),
    )
    cutters.append(port)
    shape = box
    for cutter in cutters:
        shape = shape.cut(cutter)
    shape = shape.clean()

    result = ManifoldParts(solid=cq.Workplane("XY").add(shape), params=p)
    _validate_manifold(result)
    return result


def _validate_manifold(parts: ManifoldParts) -> None:
    """Проверяет тело, воздушные проходы и стенки коллектора.

    Принимает построенную деталь. Воздух: порт, камера, зона перед каждым
    входом щели и середина каждого кармана. Материал: передняя стенка
    рядом с портом, потолок, дно, боковая стенка и перемычка между
    карманами. Ничего не возвращает; при нарушении поднимает
    WhistleManifoldError.
    """
    import cadquery as cq

    solids = parts.solid.solids().vals()
    if len(solids) != 1 or not solids[0].isValid() or solids[0].Volume() <= 0.0:
        raise WhistleManifoldError("Коллектор не вышел одним валидным телом.")
    shape = solids[0]

    p = parts.params
    x_in = p.head.wind_inlet_x_mm
    jet = p.head.jet_center_z_mm
    mid_z = p.cavity_top_z_mm / 2.0
    plenum_x = x_in - p.plenum_depth_mm / 2.0
    s2 = p.spacing_mm / 2.0

    air: list[Point3] = [
        (p.outer_start_x_mm + p.wall_mm / 2.0, 0.0, p.port_center[2]),
        (plenum_x, 0.0, mid_z),
        (x_in - 1.0, -s2, jet),
        (x_in - 1.0, s2, jet),
        (x_in + p.grip_resolved_mm / 2.0, -s2, jet),
        (x_in + p.grip_resolved_mm / 2.0, s2, jet),
    ]
    for point in air:
        if shape.isInside(cq.Vector(*point)):
            raise WhistleManifoldError(f"Задуманный воздушный проход перекрыт в {point}.")

    material: list[Point3] = [
        (p.outer_start_x_mm + p.wall_mm / 2.0, p.port_diameter_mm / 2.0 + 2.0, p.port_center[2]),
        (plenum_x, 0.0, p.cavity_top_z_mm + p.wall_mm / 2.0),
        (plenum_x, 0.0, -p.wall_mm / 2.0),
        (plenum_x, p.outer_half_width_mm - p.wall_mm / 2.0, mid_z),
        (x_in + p.grip_resolved_mm / 2.0, 0.0, jet),
    ]
    for point in material:
        if not shape.isInside(cq.Vector(*point)):
            raise WhistleManifoldError(f"Стенка коллектора отсутствует в {point}.")


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
    import cadquery as cq

    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))
