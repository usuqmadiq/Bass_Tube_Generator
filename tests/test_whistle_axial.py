"""Осевая головка под двойной мундштук: профиль, посадка, тракт, CLI."""

import json
import math
import struct
from pathlib import Path

import pytest

from bass_tube.whistle.axial_head import (
    MP_CUP_CONE_BASE_MM,
    MP_CUP_INNER_MM,
    MP_CUP_RIM_OUTER_MM,
    MP_TUBE_OUTER_MM,
    MOUTHPIECE_SOCKET_SPACING_MM,
    AxialHeadError,
    AxialHeadParams,
    build_axial_head,
)

PARTS = Path(__file__).resolve().parent.parent / "parts"
MEMBRANE_AXIS = (31.95, 16.72)  # ось модуля в координатах head.stl
MEMBRANE_TOP_Z = 27.04


def _membrane_radii(z: float) -> list[float]:
    """Радиусы сечения head.stl на высоте z вокруг оси модуля.

    Принимает z в координатах файла. Режет рёбра треугольников плоскостью
    и возвращает отсортированные радиусы точек пересечения ближе 20 мм.
    """
    data = (PARTS / "head.stl").read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    radii = []
    for index in range(count):
        v = struct.unpack_from("<9f", data, 84 + index * 50 + 12)
        corners = ((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8]))
        for p, q in ((corners[0], corners[1]), (corners[1], corners[2]), (corners[2], corners[0])):
            if (p[2] - z) * (q[2] - z) < 0:
                t = (z - p[2]) / (q[2] - p[2])
                x = p[0] + t * (q[0] - p[0]) - MEMBRANE_AXIS[0]
                y = p[1] + t * (q[1] - p[1]) - MEMBRANE_AXIS[1]
                r = math.hypot(x, y)
                if r < 20.0:
                    radii.append(r)
    return sorted(radii)


def _has_surface(radii: list[float], diameter_mm: float, tol_mm: float = 0.15) -> bool:
    """Есть ли в сечении поверхность данного диаметра с допуском."""
    return any(abs(2.0 * r - diameter_mm) <= tol_mm for r in radii)


def test_default_axial_head_builds_on_bed():
    """Голова по умолчанию — один валидный солид, печать гнездом вниз."""
    head = build_axial_head()

    solids = head.solid.solids().vals()
    assert len(solids) == 1 and solids[0].isValid()
    assert head.params.nominal_head_length_mm == pytest.approx(12.0)
    printable = head.print_part()
    assert printable.val().BoundingBox().zmin == pytest.approx(0.0, abs=1e-6)


def test_interface_constants_match_membrane_module():
    """Ступени стыка сняты с head.stl: трубка, стакан и конус совпадают."""
    # Верхняя трубка и стакан видны в сечении z=16 файла head.stl.
    mid = _membrane_radii(16.0)
    assert _has_surface(mid, MP_TUBE_OUTER_MM)
    assert _has_surface(mid, MP_CUP_INNER_MM)
    # Конус стакана: широк у основания, узок у кромки.
    assert _has_surface(_membrane_radii(14.0), MP_CUP_CONE_BASE_MM)
    assert _has_surface(_membrane_radii(23.4), MP_CUP_RIM_OUTER_MM, tol_mm=0.2)


def test_axial_head_mates_with_real_mouthpiece():
    """Булева посадка в parts/двойной мундштук.step пуста на обоих гнёздах."""
    import cadquery as cq

    mouthpiece = cq.importers.importStep(str(PARTS / "двойной мундштук.step")).val()
    head = build_axial_head()
    p = head.params
    flipped = head.solid.rotate((0, 0, 0), (1, 0, 0), 180.0).val()
    # Торец юбки мундштука (z=24 в файле) над кольцом стакана с зазором 0,1.
    lift = 24.1 + p.cup_rim_z_mm
    for socket_x in (0.0, -MOUTHPIECE_SOCKET_SPACING_MM):
        placed = flipped.translate((socket_x, 0.0, lift))
        common = mouthpiece.intersect(placed)
        volume = sum(piece.Volume() for piece in common.Solids())
        assert volume == pytest.approx(0.0, abs=1e-6), f"пересечение у гнезда {socket_x}"

    placed = flipped.translate((0.0, 0.0, lift))
    # Торцы трубок встречаются с тем же зазором, что юбка со стаканом.
    assert lift - p.top_z_mm - 25.0 == pytest.approx(0.1, abs=1e-6)
    # Окно остаётся снаружи, далеко под юбкой мундштука.
    window = cq.Vector(p.socket_outer_radius_mm - 0.5, 0.0, lift - (p.labium_z_mm + 1.0))
    assert not mouthpiece.isInside(window)


def test_mouthpiece_ring_feeds_the_flue():
    """Воздух изо рта идёт кольцом мундштука в стакан, каналами в шахту и в щель.

    Мундштук подаёт воздух в кольцо между трубкой и юбкой; центральный
    канал у него — отдушина. Путь проверяется точками в сборке с реальным
    STEP, а сплошной торец головы должен закрывать отдушину.
    """
    import cadquery as cq

    from bass_tube.whistle.axial_head import FEED_PORT_FIRST_AZIMUTH_DEG

    mouthpiece = cq.importers.importStep(str(PARTS / "двойной мундштук.step")).val()
    head = build_axial_head()
    p = head.params
    lift = 24.1 + p.cup_rim_z_mm
    placed = head.solid.rotate((0, 0, 0), (1, 0, 0), 180.0).val().translate((0.0, 0.0, lift))

    def at(x, y, z_local):
        return cq.Vector(x, -y, lift - z_local)

    def air(point):
        return not mouthpiece.isInside(point) and not placed.isInside(point)

    r0, z0 = p.feed_port_start
    r1, z1 = p.feed_port_end
    angle = math.radians(FEED_PORT_FIRST_AZIMUTH_DEG)
    path = [cq.Vector(0.0, 12.1, 18.0), at(0.0, 12.12, p.cup_rim_z_mm - 1.0)]
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        r, z = r0 + (r1 - r0) * t, z0 + (z1 - z0) * t
        path.append(at(r * math.cos(angle), r * math.sin(angle), z))
    path += [
        at(0.0, 0.0, p.languid_top_z_mm + 0.5),
        at(p.jet_center_x_mm, 0.0, p.window_top_z_mm + p.windway_length_mm / 2.0),
        at(p.jet_center_x_mm, 0.0, p.window_top_z_mm - 0.5),
        at(p.socket_outer_radius_mm - 0.5, 0.0, (p.labium_z_mm + p.window_top_z_mm) / 2.0),
    ]
    for point in path:
        assert air(point), f"путь воздуха перекрыт в {point.toTuple()}"

    assert placed.isInside(at(0.0, 0.0, p.top_z_mm - 0.75)), "торец не закрывает отдушину"
    assert air(cq.Vector(0.0, 0.0, 24.0)), "отдушина мундштука над торцом должна быть свободна"


def test_too_long_languid_is_rejected():
    """Язычок, съедающий место шахты под кровлей, отвергается."""
    with pytest.raises(AxialHeadError) as error:
        AxialHeadParams(windway_length_mm=9.0)

    assert "под кровлей" in str(error.value)


def test_head_is_slim_enough_for_the_pair():
    """Голова не шире гнезда: соседний модуль на 48 мм не задевается телом."""
    head = build_axial_head()
    bb = head.solid.val().BoundingBox()
    max_radius = max(abs(bb.xmin), bb.xmax, abs(bb.ymin), bb.ymax)

    assert max_radius < MOUTHPIECE_SOCKET_SPACING_MM / 2.0
    # Уши мембранного модуля шире: их разворачивают от соседнего голоса.


def test_axial_head_feeds_passive_model():
    """Осевая голова подставляется в расчёт прототипа без переделок."""
    from bass_tube.whistle.planning import plan_uniform_whistle

    head = AxialHeadParams()
    report = plan_uniform_whistle(1306.0, head, termination="stopped")

    assert report["neck_reference_length_mm"] == pytest.approx(12.0)
    assert report["passive_frequency_hz"] == pytest.approx(65.06, abs=0.05)
    assert report["head"]["window_azimuth_deg"] == 0.0


def test_window_azimuth_rotates_the_window():
    """Параметр азимута поворачивает окно и кромку вокруг оси."""
    import cadquery as cq

    head = build_axial_head(AxialHeadParams(window_azimuth_deg=90.0))
    p = head.params
    edge = head.labium_edge_center
    assert edge[0] == pytest.approx(0.0, abs=1e-9)
    assert edge[1] == pytest.approx(p.edge_center_x_mm)

    solid = head.solid.val()
    mid_window = (p.labium_z_mm + p.window_top_z_mm) / 2.0
    assert not solid.isInside(cq.Vector(0.0, p.socket_outer_radius_mm - 0.5, mid_window))
    assert solid.isInside(cq.Vector(p.socket_outer_radius_mm - 0.5, 0.0, mid_window))


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        (dict(labium_offset_mm=-1.0), "повисает в канале"),
        (dict(windway_width_mm=10.0), "шире шахты"),
        (dict(chamber_height_mm=6.0), "доходит до посадки"),
        (dict(edge_thickness_mm=0.8), "толще щели"),
    ],
)
def test_bad_axial_geometry_is_rejected(overrides, fragment):
    """Невалидная геометрия осевой головы отвергается с русской причиной."""
    with pytest.raises(AxialHeadError) as error:
        AxialHeadParams(**overrides)

    assert fragment in str(error.value)


def test_cli_pair_of_axial_heads(tmp_path, capsys):
    """CLI пары осевых голов: две детали, без коллектора, с пометкой."""
    from bass_tube.whistle.__main__ import main

    code = main(
        [
            "--target-hz", "80",
            "--second-target-hz", "82",
            "--termination", "stopped",
            "--mouthpiece-head",
            "--export-dir", str(tmp_path),
        ]
    )
    capsys.readouterr()

    assert code == 0
    for name in ("voice_1_body.stl", "voice_2_body.stl", "assembly.step"):
        assert (tmp_path / name).exists()
    assert not (tmp_path / "voice_1_lid.stl").exists()
    assert not (tmp_path / "manifold.stl").exists()
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "dual mouthpiece" in report["pair"]["manifold_note"]
    assert "manifold" not in report["pair"]
    readme = (tmp_path / "PRINT_README.txt").read_text(encoding="utf-8")
    assert "Осевая голова" in readme
