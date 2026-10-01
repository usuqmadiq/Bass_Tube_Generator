"""Твёрдые куски трубы: участки оси, переходник и цоколь.

Радиус колена не меньше (D + зазор)/√3, поэтому наружные стенки одной
трубы не пересекаются даже через ряд шестигранника. И стенка, и канал —
по одной протяжке круга вдоль оси без внутренних стыков: куски прямых и
колен с нахлёстом OCC сливал ненадёжно и изредка терял тело. Посадка и
конус переходника — отдельные соосные куски на первой прямой, снаружи
и в канале. Концы канала на входе и выходе продлены чуть за торец,
чтобы разрез не шёл по совпадающим плоскостям.
"""

from __future__ import annotations

import math

import cadquery as cq

from bass_tube.layout.centerline import Centerline, Straight, Turn, Vec3
from bass_tube.layout.coil import Coil
from bass_tube.layout.columns import Point2
from bass_tube.params import TubeParams

_OPEN_END_OVERSHOOT_MM = 0.5
# Цоколь чуть шире трубы и чуть выше стыков колен: совпадающие поверхности
# цилиндров и плоскостей ломают объединение в OCC.
_BASE_SIDE_MARGIN_MM = 0.05
_BASE_TOP_MARGIN_MM = 0.5


def outer_parts(
    centerline: Centerline,
    params: TubeParams,
    skip_turns_after: tuple[int, ...] = (),
) -> list[cq.Solid]:
    """Сплошные куски по наружному сечению.

    Принимает ось, параметры и номера прямых, после которых колено не
    печатается: туда сядет U-слайдер или двойное U. Если есть переходник,
    первые куски — цилиндр посадки и конус. Дальше наружная стенка — одна
    протяжка круга по оси до выхода (при слайдере — по куску между
    пропущенными коленами). Радиус колена не меньше (D + зазор)/√3,
    поэтому стенки одной трубы нигде не пересекаются, и протяжка себя не
    режет. Отдельные цилиндры с нахлёстом в колена OCC сливал ненадёжно:
    на почти совпадающих поверхностях нахлёста тело изредка пропадало.
    Возвращает список солидов.
    """
    seat_radius = params.seat_outer_diameter_mm / 2.0
    body_radius = params.outer_diameter_mm / 2.0
    solids: list[cq.Solid] = []
    start = 0.0
    if params.has_transition:
        inlet = centerline.primitives[0]
        if not isinstance(inlet, Straight):
            raise ValueError("Ось начинается не с прямой.")
        solids.append(_cylinder(inlet, 0.0, params.seat_length_mm, seat_radius, 0.0, 0.0))
        solids.append(
            _cone(inlet, params.seat_length_mm, params.joint_length_mm, seat_radius, body_radius)
        )
        start = params.joint_length_mm
    cursor = start
    for skip in sorted(skip_turns_after):
        turn, _, _ = _slider_gap(centerline, skip)
        solids.append(_sweep_along(centerline, cursor, turn.s_start_mm, body_radius))
        cursor = turn.s_end_mm
    solids.append(_sweep_along(centerline, cursor, centerline.length_mm, body_radius))
    return solids


def bore_parts(
    centerline: Centerline,
    params: TubeParams,
    skip_turns_after: tuple[int, ...] = (),
) -> list[cq.Solid]:
    """Куски канала для вычитания, по порядку вычитания.

    Принимает ось, параметры и номера прямых, после которых колено не
    печатается: канал там не протягивается, вместо него царги открываются
    в дне под U-слайдер. Первый кусок — протяжка круга канала трубы от
    конца переходника (без переходника — от входа) до выхода, выход продлён
    на полмиллиметра. Если переходник есть, дальше идут цилиндр посадки,
    продлённый за вход, и конус. Возвращает список солидов.
    """
    overshoot = _OPEN_END_OVERSHOOT_MM
    start = params.joint_length_mm if params.has_transition else -overshoot
    body_radius = params.bore_diameter_mm / 2.0
    if not skip_turns_after:
        pieces = [_sweep_along(centerline, start, centerline.length_mm + overshoot, body_radius)]
    else:
        pieces = _split_bore(centerline, start, body_radius, overshoot, skip_turns_after)
    if params.has_transition:
        inlet = centerline.primitives[0]
        if not isinstance(inlet, Straight):
            raise ValueError("Ось начинается не с прямой.")
        seat_radius = params.seat_bore_diameter_mm / 2.0
        pieces.append(_cylinder(inlet, 0.0, params.seat_length_mm, seat_radius, overshoot, 0.0))
        pieces.append(
            _cone(inlet, params.seat_length_mm, params.joint_length_mm, seat_radius, body_radius)
        )
    return pieces


def base_parts(coil: Coil, params: TubeParams) -> list[cq.Solid]:
    """Цоколь под нижними разворотами.

    Принимает укладку и параметры. Берёт выпуклую оболочку центров прямых,
    отодвигает её наружу на радиус трубы со скруглёнными углами и выдавливает
    от стола до центров нижних разворотов. Сбоку цоколь продолжает крайние
    цилиндры до плоского дна. Он на 0,05 мм шире трубы и на 0,5 мм выше
    центров колен. Собирается одним выдавливанием, без булевых операций.
    У одной прямой цоколя нет. Возвращает список из одного солида или пустой.
    """
    if coil.straight_count < 2 or coil.base_height_mm <= 0.0:
        return []
    radius = params.outer_diameter_mm / 2.0 + _BASE_SIDE_MARGIN_MM
    return [hull_base_solid(coil.columns, coil.base_height_mm, radius)]


def base_outline_radius_mm(params: TubeParams) -> float:
    """Радиус контура цоколя вокруг центров прямых.

    Принимает параметры. Половина наружного диаметра плюс боковой запас,
    как у цоколя одной трубы. Возвращает миллиметры.
    """
    return params.outer_diameter_mm / 2.0 + _BASE_SIDE_MARGIN_MM


def hull_base_solid(
    points: tuple[Point2, ...],
    base_height_mm: float,
    outline_radius_mm: float,
) -> cq.Solid:
    """Высокий цоколь по выпуклой оболочке точек плана.

    Принимает центры столбов, высоту до центров нижних колен и радиус
    контура (обычно половина наружного диаметра плюс боковой запас).
    Выдавливает оболочку от стола на высоту колен плюс 0,5 мм, чтобы
    плоскость не совпала со стыком цилиндров. Возвращает один солид.
    """
    height = base_height_mm + _BASE_TOP_MARGIN_MM
    outline = _rounded_hull_wire(convex_hull(points), outline_radius_mm)
    face = cq.Face.makeFromWires(outline)
    return cq.Solid.extrudeLinear(face, cq.Vector(0.0, 0.0, height))


def convex_hull(points: tuple[Point2, ...]) -> list[Point2]:
    """Выпуклая оболочка точек плана против часовой стрелки.

    Принимает точки. Точки на одной прямой с соседями выкидывает с
    допуском на шум округления: у повёрнутой сетки почти коллинеарные
    точки иначе дают ребро нулевой длины и вывернутый контур.
    Возвращает список вершин; у точек на одной линии — два крайних конца.
    """
    unique = sorted(set(points))
    if len(unique) <= 2:
        return unique

    def cross(origin: Point2, first: Point2, second: Point2) -> float:
        """Синус поворота origin→first→second, умноженный на знак.

        Принимает три точки. Косое произведение делится на длины обоих
        векторов, поэтому допуск не зависит от масштаба. Возвращает
        положительное число при повороте против часовой стрелки.
        """
        ax, ay = first[0] - origin[0], first[1] - origin[1]
        bx, by = second[0] - origin[0], second[1] - origin[1]
        scale = math.hypot(ax, ay) * math.hypot(bx, by)
        if scale < 1e-12:
            return 0.0
        return (ax * by - ay * bx) / scale

    lower: list[Point2] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 1e-7:
            lower.pop()
        lower.append(point)
    upper: list[Point2] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 1e-7:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _rounded_hull_wire(hull: list[Point2], radius_mm: float) -> cq.Wire:
    """Контур цоколя: оболочка, отодвинутая наружу на радиус.

    Принимает вершины выпуклой оболочки против часовой стрелки и радиус.
    Две вершины дают скруглённую полосу, три и больше — многоугольник со
    скруглёнными углами. Возвращает замкнутую кривую в плоскости z = 0.
    """
    if len(hull) == 1:
        x, y = hull[0]
        return cq.Wire.makeCircle(radius_mm, cq.Vector(x, y, 0.0), cq.Vector(0.0, 0.0, 1.0))

    count = len(hull)
    normals = []
    for index in range(count):
        ax, ay = hull[index]
        bx, by = hull[(index + 1) % count]
        length = math.hypot(bx - ax, by - ay)
        normals.append(((by - ay) / length, -(bx - ax) / length))

    edges: list[cq.Edge] = []
    for index in range(count):
        ax, ay = hull[index]
        bx, by = hull[(index + 1) % count]
        nx, ny = normals[index]
        next_nx, next_ny = normals[(index + 1) % count]
        edges.append(
            cq.Edge.makeLine(
                cq.Vector(ax + nx * radius_mm, ay + ny * radius_mm, 0.0),
                cq.Vector(bx + nx * radius_mm, by + ny * radius_mm, 0.0),
            )
        )
        mx, my = nx + next_nx, ny + next_ny
        norm = math.hypot(mx, my)
        if norm < 1e-9:
            mx, my = -ny, nx
        else:
            mx, my = mx / norm, my / norm
        edges.append(
            cq.Edge.makeThreePointArc(
                cq.Vector(bx + nx * radius_mm, by + ny * radius_mm, 0.0),
                cq.Vector(bx + mx * radius_mm, by + my * radius_mm, 0.0),
                cq.Vector(bx + next_nx * radius_mm, by + next_ny * radius_mm, 0.0),
            )
        )
    return cq.Wire.assembleEdges(edges)


def _cylinder(
    straight: Straight,
    start_mm: float,
    stop_mm: float,
    radius_mm: float,
    head_mm: float,
    tail_mm: float,
) -> cq.Solid:
    """Цилиндр на отрезке прямой.

    Принимает прямую, начало и конец отрезка вдоль неё, радиус и продления
    назад и вперёд. Возвращает солид.
    """
    base = _vector(straight.point(start_mm - head_mm))
    height = stop_mm - start_mm + head_mm + tail_mm
    return cq.Solid.makeCylinder(radius_mm, height, base, _vector(straight.direction))


def _cone(
    straight: Straight,
    start_mm: float,
    stop_mm: float,
    start_radius_mm: float,
    stop_radius_mm: float,
) -> cq.Solid:
    """Усечённый конус переходника на отрезке прямой.

    Принимает прямую, начало и конец отрезка и радиусы на них.
    Возвращает солид.
    """
    base = _vector(straight.point(start_mm))
    return cq.Solid.makeCone(
        start_radius_mm,
        stop_radius_mm,
        stop_mm - start_mm,
        base,
        _vector(straight.direction),
    )


def _split_bore(
    centerline: Centerline,
    start_mm: float,
    radius_mm: float,
    overshoot_mm: float,
    skip_turns_after: tuple[int, ...],
) -> list[cq.Solid]:
    """Канал корпуса без колен слайдера: протяжки между разрывами и царги в дне.

    Принимает ось, начало протяжки, радиус канала, продление торцов и номера
    прямых перед пропущенными коленами. Между разрывами идёт протяжка, на
    открытых торцах царг канал чуть выходит за дно. Возвращает список солидов.
    """
    pieces: list[cq.Solid] = []
    cursor = start_mm
    for skip in skip_turns_after:
        turn, first, second = _slider_gap(centerline, skip)
        pieces.append(_sweep_along(centerline, cursor, turn.s_start_mm, radius_mm))
        pieces.append(
            _cylinder(
                first,
                first.length_mm,
                first.length_mm,
                radius_mm,
                0.0,
                overshoot_mm,
            )
        )
        pieces.append(_cylinder(second, 0.0, 0.0, radius_mm, overshoot_mm, 0.0))
        cursor = turn.s_end_mm
    pieces.append(
        _sweep_along(
            centerline,
            cursor,
            centerline.length_mm + overshoot_mm,
            radius_mm,
        )
    )
    return pieces


def _slider_gap(
    centerline: Centerline,
    skip_turn_after: int,
) -> tuple[Turn, Straight, Straight]:
    """Колено U-слайдера и две прямые, которые в него входят.

    Принимает ось и номер прямой перед пропущенным коленом. Возвращает
    (дуга, первая прямая, вторая прямая). Если на этом месте нет дуги
    между двумя прямыми, поднимает ValueError.
    """
    turn_index = 2 * skip_turn_after + 1
    if turn_index + 1 >= len(centerline.primitives):
        raise ValueError("U-слайдеру не хватает колена на оси.")
    turn = centerline.primitives[turn_index]
    first = centerline.primitives[turn_index - 1]
    second = centerline.primitives[turn_index + 1]
    if not isinstance(turn, Turn) or not isinstance(first, Straight) or not isinstance(second, Straight):
        raise ValueError("U-слайдер ожидает прямую, нижнее колено и прямую.")
    return turn, first, second


def _sweep_along(centerline: Centerline, s_from_mm: float, s_to_mm: float, radius_mm: float) -> cq.Solid:
    """Круг, протянутый по куску оси от s_from до s_to.

    Принимает ось, границы куска и радиус. Граница до нуля продлевает первую
    прямую назад, граница за длиной оси — последнюю вперёд. Разворот
    берётся только целиком. Возвращает солид.
    """
    edges: list[cq.Edge] = []
    last = len(centerline.primitives) - 1
    for index, primitive in enumerate(centerline.primitives):
        low = primitive.s_start_mm if index > 0 else min(primitive.s_start_mm, s_from_mm)
        high = primitive.s_end_mm if index < last else max(primitive.s_end_mm, s_to_mm)
        low = max(low, s_from_mm)
        high = min(high, s_to_mm)
        if high - low < 1e-9:
            continue
        begin = low - primitive.s_start_mm
        finish = high - primitive.s_start_mm
        if isinstance(primitive, Straight):
            edges.append(cq.Edge.makeLine(_vector(primitive.point(begin)), _vector(primitive.point(finish))))
        elif abs(begin) < 1e-9 and abs(finish - primitive.length_mm) < 1e-9:
            edges.append(
                cq.Edge.makeThreePointArc(
                    _vector(primitive.point(0.0)),
                    _vector(primitive.point(primitive.length_mm / 2.0)),
                    _vector(primitive.point(primitive.length_mm)),
                )
            )
        else:
            raise ValueError("Протяжка канала режет разворот посередине.")
    path = cq.Wire.assembleEdges(edges)
    start_point, start_tangent = _sweep_start(centerline, s_from_mm)
    profile = cq.Wire.makeCircle(radius_mm, start_point, start_tangent)
    return cq.Solid.sweep(profile, [], path, makeSolid=True, isFrenet=False)


def _sweep_start(centerline: Centerline, s_from_mm: float) -> tuple[cq.Vector, cq.Vector]:
    """Точка и касательная начала протяжки канала.

    Принимает ось и координату s начала. Если s раньше первой прямой,
    продолжает её назад. Если s на любом участке, берёт точку этого
    участка. Возвращает пару векторов CadQuery. Если начало не на оси,
    поднимает ValueError.
    """
    first = centerline.primitives[0]
    if s_from_mm < first.s_end_mm - 1e-9:
        return _vector(first.point(s_from_mm - first.s_start_mm)), _vector(first.tangent(0.0))
    last = centerline.primitives[-1]
    for primitive in centerline.primitives:
        if s_from_mm < primitive.s_end_mm - 1e-9 or primitive is last:
            distance = min(max(s_from_mm - primitive.s_start_mm, 0.0), primitive.length_mm)
            return _vector(primitive.point(distance)), _vector(primitive.tangent(distance))
    raise ValueError("Протяжка канала начинается вне оси.")


def _vector(point: Vec3) -> cq.Vector:
    """Вектор CadQuery из точки оси.

    Принимает Vec3. Возвращает Vector.
    """
    return cq.Vector(point.x, point.y, point.z)
