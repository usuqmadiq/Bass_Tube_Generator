"""Свистковая головка с осевой подачей под готовый двойной мундштук.

Стык как у мембранного модуля: трубка мундштука (наружная Ø22) упирается
торцом в торец нашей верхней трубки, торец юбки мундштука (Ø26,5…31,4)
ложится на кольцо нашего «стакана» (Ø26,44…32,11), а наружный конус
стакана (Ø33,44 → 32,11, тот же уклон 4,4°) продолжает конус мундштука
заподлицо. Сверх мембранного модуля добавлена центрирующая губа вокруг
носика юбки — мембране она мешала бы, жёсткой головке помогает.

Воздух изо рта мундштук подаёт в КОЛЬЦО между своей трубкой и юбкой; оно
общее для обоих гнёзд. Центральный канал мундштука со ртом не связан —
это сквозная отдушина. Поэтому наш стакан не глухой: из его полости
четыре канала под 45° уходят вниз в шахту над пластиной-язычком (languid
органной трубы), а верх шахты закрыт конусной кровлей 45° — воздух не
уходит в отдушину, печать без поддержек. Торец верхней трубки — сплошной
диск: прижатый к трубке мундштука, он отделяет кольцо под давлением от
отдушины. У края язычка — вертикальная щель, струя бьёт вниз поперёк
бокового окна и встречает кромку-лабиум на верхнем краю стенки канала.
Окно смотрит вбок и целиком ниже мундштука; его азимут — параметр.

Размеры стыка сняты с parts/двойной мундштук.step (точный STEP) и
parts/head.stl (обкатанная печать): tests/test_whistle_axial.py сверяет
константы с файлами. Акустически головка не продувалась: шейка модели —
высота лабиума, поправка окна задаётся пользователем, как у прототипа.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from numbers import Real

# Интерфейс двойного мундштука, снятый с parts/. Это номиналы обкатанной
# пары «мундштук — мембранный модуль», а не свободные параметры.
MOUTHPIECE_SOCKET_SPACING_MM = 48.0
# Верхняя трубка: торец в торец с трубкой мундштука (наружная Ø22.0).
# Трубка мундштука выступает за его юбку на 1 мм (торцы z=25 и z=24 в STEP),
# поэтому наша трубка на столько же утоплена ниже кольца стакана: оба
# кольцевых упора — трубка-трубка и юбка-стакан — срабатывают одновременно.
MP_TUBE_OUTER_MM = 22.04
MP_TUBE_PROUD_MM = 1.0
MP_INLET_BORE_MM = 18.0         # канал мундштука Ø18…20,4 продолжает шахту
# Кольцо стакана, на которое ложится торец юбки мундштука.
MP_CUP_INNER_MM = 26.44
MP_CUP_RIM_OUTER_MM = 32.11
MP_CUP_CONE_BASE_MM = 33.44     # низ конуса стакана (уклон как у мундштука)
MP_CUP_CONE_LEN_MM = 9.5
MP_CUP_BELT_LEN_MM = 3.2        # цилиндрический поясок Ø33,44 под конусом
MP_CUP_CAVITY_DEPTH_MM = 4.0    # полость стакана; носик мундштука туда не входит
# Центрирующая губа вокруг носика юбки (наружный конус юбки 32,02…31,37).
MP_LIP_INNER_MM = 32.4
MP_LIP_OUTER_MM = 35.4
MP_LIP_HEIGHT_MM = 1.5

# Каналы из полости стакана в шахту: под 45°, печатаются без поддержек.
FEED_PORT_COUNT = 4
FEED_PORT_DIAMETER_MM = 3.0
FEED_PORT_FIRST_AZIMUTH_DEG = 45.0
# Сплошной диск над конусной кровлей шахты: отделяет давление от отдушины.
ROOF_CAP_MM = 1.5

_OVERSHOOT_MM = 0.5
_WINDOW_TOP_MARGIN_MM = 1.5     # окно ниже начала конуса к стакану

Point3 = tuple[float, float, float]


class AxialHeadError(ValueError):
    """Осевая головка не собирается на такие размеры. Текст — причина."""


@dataclass(frozen=True, slots=True)
class AxialHeadParams:
    """Размеры осевой головки; миллиметры, датум z = 0 — торец трубы.

    Труба входит в гнездо снизу, как у мембранного модуля и головки
    прототипа. chamber_height_mm — высота лабиума над датумом, она же
    модельная шейка. windway_length_mm — вертикальная длина щели в
    пластине-язычке: это толщина languid, у органных труб она короткая.
    labium_offset_mm — смещение кромки от поверхности канала наружу
    (плюс — наружу); кромка должна опираться на стенку канала.
    window_azimuth_deg поворачивает окно вокруг оси готовой детали.
    """

    tube_outer_diameter_mm: float = 19.5
    tube_bore_diameter_mm: float = 15.5
    socket_clearance_mm: float = 0.13
    socket_depth_mm: float = 8.0
    wall_mm: float = 2.0
    windway_width_mm: float = 8.0
    windway_height_mm: float = 0.6
    windway_length_mm: float = 4.0
    window_length_mm: float = 8.0
    labium_offset_mm: float = 0.0
    edge_thickness_mm: float = 0.3
    blade_angle_deg: float = 25.0
    chamber_height_mm: float = 12.0
    window_azimuth_deg: float = 0.0

    def __post_init__(self) -> None:
        reasons: list[str] = []
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                reasons.append(f"{field.name}: нужно конечное число")
        if reasons:
            raise AxialHeadError("; ".join(reasons))

        signed = {"labium_offset_mm", "window_azimuth_deg"}
        nonnegative = {"socket_clearance_mm"}
        for field in fields(self):
            value = getattr(self, field.name)
            if field.name in signed:
                continue
            if field.name in nonnegative:
                if value < 0.0:
                    reasons.append(f"{field.name}: не бывает отрицательным")
            elif value <= 0.0:
                reasons.append(f"{field.name}: нужно положительное число")
        if reasons:
            raise AxialHeadError("; ".join(reasons))

        if self.tube_bore_diameter_mm >= self.tube_outer_diameter_mm:
            reasons.append("канал трубы должен быть уже её наружного диаметра")
        if not 0.0 < self.blade_angle_deg < 60.0:
            reasons.append("blade_angle_deg: уклон кромки от 0 до 60 градусов")
        if self.edge_thickness_mm > self.windway_height_mm:
            reasons.append("кромка толще щели: edge_thickness_mm не больше windway_height_mm")
        if self.edge_inner_x_mm < self.bore_radius_mm - 0.2:
            reasons.append(
                "кромка повисает в канале: labium_offset_mm меньше минимума, "
                "кромке не на что опереться (смещайте наружу)"
            )
        if self.edge_outer_x_mm > self.socket_outer_radius_mm - 1.0:
            reasons.append("кромка почти на наружной стенке: некуда положить скос")
        half_chord = self.shaft_radius_mm**2 - self.flue_outer_x_mm**2
        if half_chord <= 0.0 or self.windway_width_mm / 2.0 > math.sqrt(half_chord):
            limit = 0.0 if half_chord <= 0.0 else 2.0 * math.sqrt(half_chord)
            reasons.append(
                f"щель шире шахты подачи: при этом канале ширина не больше {limit:.1f} мм"
            )
        if self.windway_width_mm >= 2.0 * self.socket_outer_radius_mm - 2.0:
            reasons.append("окно шире тела головки")
        if self.bevel_bottom_z_mm < 0.5:
            reasons.append(
                "скос лабиума доходит до посадки трубы: поднимите лабиум "
                "(chamber_height_mm) или уменьшите уклон кромки"
            )
        if self.roof_start_z_mm < self.languid_top_z_mm + 0.5:
            limit = self.roof_start_z_mm - 0.5 - self.window_top_z_mm
            reasons.append(
                "длинный язычок не оставляет шахте места под кровлей: "
                f"windway_length_mm не больше {limit:.1f} мм"
            )
        if reasons:
            raise AxialHeadError("; ".join(reasons))

    # --- посадка на трубу ---
    @property
    def socket_inner_radius_mm(self) -> float:
        return (self.tube_outer_diameter_mm + self.socket_clearance_mm) / 2.0

    @property
    def socket_outer_radius_mm(self) -> float:
        return self.socket_inner_radius_mm + self.wall_mm

    @property
    def bore_radius_mm(self) -> float:
        return self.tube_bore_diameter_mm / 2.0

    # --- рот: лабиум, окно, щель ---
    @property
    def labium_z_mm(self) -> float:
        return self.chamber_height_mm

    @property
    def window_top_z_mm(self) -> float:
        """Выход щели: верх окна, отсюда струя идёт вниз на кромку."""
        return self.labium_z_mm + self.window_length_mm

    @property
    def languid_top_z_mm(self) -> float:
        return self.window_top_z_mm + self.windway_length_mm

    @property
    def flue_outer_x_mm(self) -> float:
        """Наружная направляющая щели — продолжение поверхности канала."""
        return self.bore_radius_mm

    @property
    def jet_center_x_mm(self) -> float:
        return self.flue_outer_x_mm - self.windway_height_mm / 2.0

    @property
    def edge_center_x_mm(self) -> float:
        return self.bore_radius_mm + self.labium_offset_mm

    @property
    def edge_inner_x_mm(self) -> float:
        return self.edge_center_x_mm - self.edge_thickness_mm / 2.0

    @property
    def edge_outer_x_mm(self) -> float:
        return self.edge_center_x_mm + self.edge_thickness_mm / 2.0

    @property
    def bevel_bottom_z_mm(self) -> float:
        """Нижняя точка скоса кромки на наружной стенке."""
        run = (self.socket_outer_radius_mm + 1.0) - self.edge_outer_x_mm
        return self.labium_z_mm - run / math.tan(math.radians(self.blade_angle_deg))

    # --- верх под мундштук ---
    @property
    def shaft_radius_mm(self) -> float:
        return MP_INLET_BORE_MM / 2.0

    @property
    def cone_start_z_mm(self) -> float:
        return self.window_top_z_mm + _WINDOW_TOP_MARGIN_MM

    @property
    def belt_start_z_mm(self) -> float:
        """Низ пояска Ø33,44: конус 45° от тела до пояска."""
        return self.cone_start_z_mm + (MP_CUP_CONE_BASE_MM / 2.0 - self.socket_outer_radius_mm)

    @property
    def cup_cone_start_z_mm(self) -> float:
        return self.belt_start_z_mm + MP_CUP_BELT_LEN_MM

    @property
    def cup_rim_z_mm(self) -> float:
        return self.cup_cone_start_z_mm + MP_CUP_CONE_LEN_MM

    @property
    def top_z_mm(self) -> float:
        """Торец верхней трубки: утоплен под выступающую трубку мундштука."""
        return self.cup_rim_z_mm - MP_TUBE_PROUD_MM

    @property
    def cup_floor_z_mm(self) -> float:
        """Дно полости стакана: продолжение кольца мундштука вниз."""
        return self.cup_rim_z_mm - MP_CUP_CAVITY_DEPTH_MM

    @property
    def roof_apex_z_mm(self) -> float:
        """Вершина конусной кровли шахты, под сплошным диском торца."""
        return self.top_z_mm - ROOF_CAP_MM

    @property
    def roof_start_z_mm(self) -> float:
        """Где цилиндр шахты переходит в кровлю 45°."""
        return self.roof_apex_z_mm - self.shaft_radius_mm

    @property
    def feed_port_start(self) -> tuple[float, float]:
        """(r, z) входа канала подачи: середина кольца над дном стакана."""
        r = (MP_TUBE_OUTER_MM + MP_CUP_INNER_MM) / 4.0
        return r, self.cup_floor_z_mm + 0.5

    @property
    def feed_port_end(self) -> tuple[float, float]:
        """(r, z) выхода канала подачи: внутри цилиндра шахты под кровлей."""
        r0, z0 = self.feed_port_start
        r1 = 4.0
        return r1, z0 - (r0 - r1)

    @property
    def nominal_head_length_mm(self) -> float:
        """Модельная шейка: высота лабиума; не калиброванная поправка."""
        return self.labium_z_mm


@dataclass(frozen=True)
class AxialHeadParts:
    """Построенная осевая головка: одна печатная деталь.

    solid — деталь CadQuery в координатах датума трубы. Окна и кромка уже
    повёрнуты на window_azimuth_deg. print_part ставит деталь гнездом вниз
    на z = 0 — печать как у головки прототипа, крышки нет: щель вертикальна
    и доступна снизу через окно.
    """

    solid: object
    params: AxialHeadParams
    tube_port: Point3
    inlet_center: Point3
    labium_edge_center: Point3

    def print_part(self):
        return self.solid.translate((0.0, 0.0, self.params.socket_depth_mm))


def build_axial_head(params: AxialHeadParams | None = None) -> AxialHeadParts:
    """Строит осевую головку: тело вращения, шахта, язычок, щель и окно.

    Принимает проверенные размеры (None — по умолчанию). Возвращает
    AxialHeadParts. Если тело не вышло одним валидным солидом или проходы
    перекрыты, поднимает AxialHeadError.
    """
    import cadquery as cq

    p = params if params is not None else AxialHeadParams()
    if not isinstance(p, AxialHeadParams):
        raise AxialHeadError("params: нужны AxialHeadParams")
    eps = _OVERSHOOT_MM

    r_sock_out = p.socket_outer_radius_mm
    r_belt = MP_CUP_CONE_BASE_MM / 2.0
    r_rim = MP_CUP_RIM_OUTER_MM / 2.0
    r_cav = MP_CUP_INNER_MM / 2.0
    r_tube = MP_TUBE_OUTER_MM / 2.0
    r_lip_in = MP_LIP_INNER_MM / 2.0
    r_lip_out = MP_LIP_OUTER_MM / 2.0
    r_shaft = p.shaft_radius_mm
    z0 = -p.socket_depth_mm
    z_cav_floor = p.cup_rim_z_mm - MP_CUP_CAVITY_DEPTH_MM
    z_lip_top = p.cup_rim_z_mm + MP_LIP_HEIGHT_MM
    # Подход к губе круче 45°: наплыв за 1 мм подъёма, печатается без опор.
    lip_lead = 1.0

    # Наружный контур одним вращением: юбка-гнездо, конус 45°, поясок,
    # конус стакана, губа, полость стакана и верхняя трубка.
    profile = [
        (0.0, z0),
        (r_sock_out, z0),
        (r_sock_out, p.cone_start_z_mm),
        (r_belt, p.belt_start_z_mm),
        (r_belt, p.cup_cone_start_z_mm),
        (r_rim, p.cup_rim_z_mm),
        (r_lip_out, p.cup_rim_z_mm + lip_lead),
        (r_lip_out, z_lip_top),
        (r_lip_in, z_lip_top),
        (r_lip_in, p.cup_rim_z_mm),
        (r_cav, p.cup_rim_z_mm),
        (r_cav, z_cav_floor),
        (r_tube, z_cav_floor),
        (r_tube, p.top_z_mm),
        (0.0, p.top_z_mm),
    ]
    shape = (
        cq.Workplane("XZ")
        .polyline(profile)
        .close()
        .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        .val()
    )

    half_b = p.windway_width_mm / 2.0
    socket = cq.Solid.makeCylinder(
        p.socket_inner_radius_mm, p.socket_depth_mm + eps, cq.Vector(0, 0, z0 - eps)
    )
    bore = cq.Solid.makeCylinder(
        p.bore_radius_mm, p.window_top_z_mm + eps, cq.Vector(0, 0, -eps)
    )
    shaft = (
        cq.Workplane("XZ")
        .polyline(
            [
                (0.0, p.languid_top_z_mm),
                (r_shaft, p.languid_top_z_mm),
                (r_shaft, p.roof_start_z_mm),
                (0.0, p.roof_apex_z_mm),
            ]
        )
        .close()
        .revolve(360.0, (0.0, 0.0, 0.0), (0.0, 1.0, 0.0))
        .val()
    )
    ports = _feed_ports(p)
    flue = _box(
        p.flue_outer_x_mm - p.windway_height_mm,
        p.flue_outer_x_mm,
        -half_b,
        half_b,
        p.window_top_z_mm - 0.1,
        p.languid_top_z_mm + 0.1,
    )
    window = _box(
        p.edge_inner_x_mm,
        r_sock_out + 1.0,
        -half_b,
        half_b,
        p.labium_z_mm,
        p.window_top_z_mm,
    )
    bevel = (
        cq.Workplane("XZ")
        .polyline(
            [
                (p.edge_outer_x_mm, p.labium_z_mm),
                (r_sock_out + 1.0, p.bevel_bottom_z_mm),
                (r_sock_out + 1.0, p.labium_z_mm),
            ]
        )
        .close()
        .extrude(half_b, both=True)
        .val()
    )
    for cutter in (socket, bore, shaft, flue, window, bevel, *ports):
        shape = shape.cut(cutter)
    shape = shape.clean()

    result = AxialHeadParts(
        solid=cq.Workplane("XY").add(shape),
        params=p,
        tube_port=(0.0, 0.0, 0.0),
        inlet_center=(0.0, 0.0, p.top_z_mm),
        labium_edge_center=(p.edge_center_x_mm, 0.0, p.labium_z_mm),
    )
    _validate_axial(result)
    if p.window_azimuth_deg:
        rotated = result.solid.rotate((0, 0, 0), (0, 0, 1), p.window_azimuth_deg)
        result = AxialHeadParts(
            solid=rotated,
            params=p,
            tube_port=result.tube_port,
            inlet_center=result.inlet_center,
            labium_edge_center=_rotated_z(result.labium_edge_center, p.window_azimuth_deg),
        )
    return result


def _validate_axial(parts: AxialHeadParts) -> None:
    """Проверяет тело, воздушный тракт и стенки до поворота окна.

    Воздух: гнездо, канал, низ язычка, щель, окно перед кромкой, шахта,
    вход и полость стакана. Материал: стенка гнезда, язычок, наружная
    направляющая щели, опора кромки, щёки окна, стенки трубки, стакана и
    губы. Ничего не возвращает; при нарушении поднимает AxialHeadError.
    """
    import cadquery as cq

    solids = parts.solid.solids().vals()
    if len(solids) != 1 or not solids[0].isValid() or solids[0].Volume() <= 0.0:
        raise AxialHeadError("Головка не вышла одним валидным телом.")
    shape = solids[0]
    p = parts.params

    mid_window_z = (p.labium_z_mm + p.window_top_z_mm) / 2.0
    languid_mid_z = p.window_top_z_mm + p.windway_length_mm / 2.0
    r0, z0 = p.feed_port_start
    r1, z1 = p.feed_port_end
    port_angle = math.radians(FEED_PORT_FIRST_AZIMUTH_DEG)
    port_r, port_z = (r0 + r1) / 2.0, (z0 + z1) / 2.0
    air: list[Point3] = [
        (0.0, 0.0, -p.socket_depth_mm / 2.0),
        (0.0, 0.0, p.labium_z_mm / 2.0),
        (0.0, 0.0, p.window_top_z_mm - 1.0),
        (p.jet_center_x_mm, 0.0, languid_mid_z),
        (p.jet_center_x_mm, 0.0, p.window_top_z_mm - 0.5),
        (p.socket_outer_radius_mm - 0.5, 0.0, mid_window_z),
        (0.0, 0.0, p.languid_top_z_mm + 0.5),
        (0.0, 0.0, p.roof_apex_z_mm - 1.0),
        (0.0, (MP_CUP_INNER_MM / 2.0 + MP_TUBE_OUTER_MM / 2.0) / 2.0, p.cup_rim_z_mm - 1.0),
        (port_r * math.cos(port_angle), port_r * math.sin(port_angle), port_z),
    ]
    for point in air:
        if shape.isInside(cq.Vector(*point)):
            raise AxialHeadError(f"Задуманный воздушный проход перекрыт в {point}.")

    spread = math.tan(math.radians(p.blade_angle_deg))
    support_x = (p.bore_radius_mm + min(p.edge_outer_x_mm + 0.4 * spread, p.socket_outer_radius_mm)) / 2.0
    material: list[Point3] = [
        ((p.socket_inner_radius_mm + p.socket_outer_radius_mm) / 2.0, 0.0, -p.socket_depth_mm / 2.0),
        (0.0, p.shaft_radius_mm + 1.0, languid_mid_z),
        ((p.bore_radius_mm + p.socket_outer_radius_mm) / 2.0, 0.0, languid_mid_z),
        (support_x, 0.0, p.labium_z_mm - 0.4),
        (_cheek_x(p), p.windway_width_mm / 2.0 + 0.8, mid_window_z),
        (0.0, (MP_TUBE_OUTER_MM / 2.0 + p.shaft_radius_mm) / 2.0, p.top_z_mm - 0.7),
        # Торец над кровлей сплошной: давление не уходит в отдушину мундштука.
        (0.0, 0.0, p.top_z_mm - ROOF_CAP_MM / 2.0),
        (0.0, (MP_CUP_INNER_MM + MP_CUP_CONE_BASE_MM) / 4.0, p.belt_start_z_mm + 1.0),
        (0.0, (MP_LIP_INNER_MM + MP_LIP_OUTER_MM) / 4.0, p.cup_rim_z_mm + MP_LIP_HEIGHT_MM / 2.0),
    ]
    for point in material:
        if not shape.isInside(cq.Vector(*point)):
            raise AxialHeadError(f"Стенка головки отсутствует в {point}.")


def axial_head_for_tube(tube) -> AxialHeadParams:
    """Размеры осевой головки для проверенного набора параметров трубы.

    Принимает объект с полями TubeParams (утиная типизация, как у
    head_for_tube боковой головки). Гнездо — по концу под модуль с зазором
    гнезда свистка, щель и окно — из flue_for_tube (заданные или по давлению
    дутья), кромка — из свистковых полей, поворот окна — из
    whistle_window_azimuth_deg. Набора крышек у осевой головки нет: она
    одна деталь. Возвращает AxialHeadParams; его проверка поднимает
    AxialHeadError.
    """
    from bass_tube.whistle.params import flue_for_tube

    height, cutup = flue_for_tube(tube)
    return AxialHeadParams(
        tube_outer_diameter_mm=tube.seat_outer_diameter_mm,
        tube_bore_diameter_mm=tube.seat_bore_diameter_mm,
        socket_clearance_mm=tube.whistle_socket_clearance_mm,
        socket_depth_mm=tube.seat_length_mm,
        windway_width_mm=tube.whistle_windway_width_mm,
        windway_height_mm=height,
        windway_length_mm=tube.whistle_windway_length_mm,
        window_length_mm=cutup,
        labium_offset_mm=tube.whistle_labium_offset_mm,
        edge_thickness_mm=tube.whistle_edge_thickness_mm,
        window_azimuth_deg=tube.whistle_window_azimuth_deg,
    )


def _feed_ports(p: AxialHeadParams) -> list:
    """Каналы подачи из полости стакана вниз-внутрь в шахту, под 45°.

    Принимает размеры. Каждый канал начинается чуть выше дна полости
    (с запасом назад вдоль оси канала) и кончается внутри цилиндра шахты
    под кровлей. Азимуты — через равный шаг от FEED_PORT_FIRST_AZIMUTH_DEG,
    в стороне от щели. Возвращает список цилиндров CadQuery.
    """
    import cadquery as cq

    r0, z0 = p.feed_port_start
    r1, z1 = p.feed_port_end
    back = 1.0
    length = math.hypot(r0 - r1, z0 - z1) + back
    ports = []
    for index in range(FEED_PORT_COUNT):
        angle = math.radians(FEED_PORT_FIRST_AZIMUTH_DEG + index * 360.0 / FEED_PORT_COUNT)
        c, s = math.cos(angle), math.sin(angle)
        direction = cq.Vector(-c, -s, -1.0).normalized()
        start = cq.Vector(r0 * c, r0 * s, z0) - direction * back
        ports.append(
            cq.Solid.makeCylinder(FEED_PORT_DIAMETER_MM / 2.0, length, start, direction)
        )
    return ports


def _cheek_x(p: AxialHeadParams) -> float:
    """Точка щеки окна: внутри круглого тела рядом с вырезом окна."""
    y = p.windway_width_mm / 2.0 + 0.8
    reach = (p.socket_outer_radius_mm - 0.8) ** 2 - y * y
    return math.sqrt(max(reach, 0.25))


def _rotated_z(point: Point3, degrees: float) -> Point3:
    angle = math.radians(degrees)
    x, y, z = point
    return (
        x * math.cos(angle) - y * math.sin(angle),
        x * math.sin(angle) + y * math.cos(angle),
        z,
    )


def _box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
    import cadquery as cq

    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))
