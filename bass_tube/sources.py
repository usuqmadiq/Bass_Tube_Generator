"""Модули-источники на входах труб: мембрана или свисток.

Свистковую головку генератор строит сам (bass_tube.whistle). Мембранный
модуль — обкатанная готовая деталь parts/head.stl с кольцом parts/ring.stl:
её не перестраивают, а ставят на вход для вида и кладут рядом с трубой при
сохранении. Положение модуля снято с head.stl: ось гнезда (31,952; 16,720),
упор трубы на z = 9,02, уши смотрят в сторону (−0,748; 0,663) и доходят до
радиуса 37,4 мм — в паре их разворачивают от соседнего голоса.
"""

from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cadquery as cq

from bass_tube.constants import SOURCE_MEMBRANE

PARTS_DIR = Path(__file__).resolve().parent.parent / "parts"
MEMBRANE_MODULE_STL = PARTS_DIR / "head.stl"
MEMBRANE_RING_STL = PARTS_DIR / "ring.stl"
MEMBRANE_AXIS_XY = (31.952, 16.720)
MEMBRANE_STOP_Z_MM = 9.02
MEMBRANE_EAR_DIRECTION = (-0.748, 0.663)


@lru_cache(maxsize=1)
def membrane_module_shape() -> cq.Shape | None:
    """Мембранный модуль из parts/head.stl в своих координатах: упор трубы в z = 0.

    Ничего не принимает. Читает сетку STL один раз, переносит ось гнезда в
    начало координат, упор трубы — на z = 0. Возвращает фигуру или None,
    если файла нет (пакет установлен без папки parts).
    """
    if not MEMBRANE_MODULE_STL.exists():
        return None
    from OCP.StlAPI import StlAPI_Reader
    from OCP.TopoDS import TopoDS_Shape

    shape = TopoDS_Shape()
    if not StlAPI_Reader().Read(shape, str(MEMBRANE_MODULE_STL)):
        return None
    module = cq.Shape.cast(shape)
    return module.translate(
        cq.Vector(-MEMBRANE_AXIS_XY[0], -MEMBRANE_AXIS_XY[1], -MEMBRANE_STOP_Z_MM)
    )


def membrane_module_at(inlet, away: tuple[float, float] | None = None) -> cq.Shape | None:
    """Мембранный модуль на входе трубы, уши — в сторону away.

    Принимает точку входа (торец трубы, x/y/z) и необязательное направление
    в плане, куда развернуть уши (от соседнего голоса). Возвращает фигуру
    или None, если модуля нет.
    """
    module = membrane_module_shape()
    if module is None:
        return None
    if away is not None and math.hypot(*away) > 1e-9:
        turn = math.degrees(
            math.atan2(away[1], away[0])
            - math.atan2(MEMBRANE_EAR_DIRECTION[1], MEMBRANE_EAR_DIRECTION[0])
        )
        module = module.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), turn)
    return module.translate(cq.Vector(inlet.x, inlet.y, inlet.z))


def design_sources(design) -> list[cq.Shape]:
    """Модуль-источник одиночной трубы на её входе.

    Принимает Design. У свистка — корпус и крышка (или одна деталь) головки
    на месте, у мембраны — мембранный модуль. Возвращает список фигур
    (пустой, если мембранного модуля нет на диске).
    """
    from bass_tube.design import whistle_head_at_inlet

    if design.whistle_head is not None:
        return list(whistle_head_at_inlet(design).Solids())
    module = membrane_module_at(design.centerline.sample(0.0).point)
    return [] if module is None else [module]


def pair_sources(pair) -> list[cq.Shape]:
    """Модули-источники обоих голосов пары на их входах.

    Принимает VoicePair. Свистковые головки стоят как у whistle_heads_at_inlets,
    мембранные модули — ушами от соседнего входа. Возвращает список фигур.
    """
    from bass_tube.design import whistle_head_solids

    shapes: list[cq.Shape] = []
    voices = (
        (pair.melody, pair.melody_whistle_head, pair.drone),
        (pair.drone, pair.drone_whistle_head, pair.melody),
    )
    for plan, head, other in voices:
        inlet = plan.centerline.sample(0.0).point
        if head is not None:
            shapes.extend(
                part.translate((inlet.x, inlet.y, inlet.z)) for part in whistle_head_solids(head)
            )
            continue
        partner = other.centerline.sample(0.0).point
        module = membrane_module_at(inlet, (inlet.x - partner.x, inlet.y - partner.y))
        if module is not None:
            shapes.append(module)
    return shapes


def export_membrane_sources(params, step_path: Path, suffix: str = "") -> list[Path]:
    """Кладёт мембранный модуль и кольцо рядом с трубой, если голос — мембрана.

    Принимает параметры голоса, путь STEP трубы и суффикс голоса («-дрон»).
    Копирует parts/head.stl и parts/ring.stl как «<имя>-мембрана<суффикс>.stl»
    и «<имя>-мембрана<суффикс>-кольцо.stl»: это готовые детали печати, их
    не перестраивают. Возвращает записанные пути (пусто у свистка или без
    папки parts).
    """
    if params.source != SOURCE_MEMBRANE:
        return []
    saved: list[Path] = []
    for source, tail in ((MEMBRANE_MODULE_STL, ""), (MEMBRANE_RING_STL, "-кольцо")):
        if not source.exists():
            continue
        target = step_path.with_name(f"{step_path.stem}-мембрана{suffix}{tail}.stl")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        saved.append(target)
    return saved


@dataclass(eq=False)
class VoiceModule:
    """Модуль-источник одного голоса без трубы.

    role — «melody» или «drone». params и tuning — голос и его строй: длина
    корпуса, под которую считан модуль. head и report — печатная свистковая
    головка и её паспорт; у мембраны оба None — модуль готовый, из parts/.
    """

    role: str
    params: object
    tuning: object
    head: object | None
    report: dict | None


@dataclass(eq=False)
class ModuleSet:
    """Только модули-источники: мелодия и, если задан, дрон. Труба не строится."""

    params: object
    voices: tuple[VoiceModule, ...]


def build_modules(params) -> ModuleSet:
    """Считает строй каждого голоса и строит только его модуль-источник.

    Принимает проверенные параметры. Укладка, ось и корпус трубы не
    строятся: модуль печатают отдельно под уже напечатанную трубу или до
    неё. Свисток получает головку с подбором окна и щели по давлению дутья,
    мембрана — ничего не строит (готовая деталь parts/head.stl).
    Возвращает ModuleSet. Ошибки строя и головки пробрасывает.
    """
    from bass_tube.acoustics.tuning import resolve_tuning
    from bass_tube.design import _build_whistle_head
    from bass_tube.pair import drone_params, melody_params

    voices = [("melody", melody_params(params))]
    if params.drone_note:
        voices.append(("drone", drone_params(params)))
    modules = []
    for role, voice in voices:
        tuning = resolve_tuning(voice)
        head, report = _build_whistle_head(voice, tuning)
        modules.append(VoiceModule(role, voice, tuning, head, report))
    return ModuleSet(params=params, voices=tuple(modules))


def module_print_solids(module: VoiceModule) -> list[cq.Shape]:
    """Печатные детали модуля в печатном положении, на столе.

    Принимает модуль голоса. Свисток: корпус и крышка расчётной щели (или
    одна деталь осевой). Мембрана: готовый модуль из parts/head.stl, если он
    есть. Возвращает список фигур.
    """
    if module.head is None:
        shape = membrane_module_shape()
        if shape is None:
            return []
        return [shape.translate(cq.Vector(0.0, 0.0, -shape.BoundingBox().zmin))]
    if hasattr(module.head, "print_parts"):
        return [part.val() for part in module.head.print_parts().values()]
    return [module.head.print_part().val()]


def modules_preview(modules: ModuleSet) -> cq.Shape:
    """Все печатные детали модулей в ряд по x с зазором 10 мм — для окна.

    Принимает ModuleSet. Возвращает одну сборку без слияния. Если деталей
    нет (мембрана без папки parts), поднимает ValueError.
    """
    solids: list[cq.Shape] = []
    cursor = 0.0
    for module in modules.voices:
        for shape in module_print_solids(module):
            box = shape.BoundingBox()
            moved = shape.translate(cq.Vector(cursor - box.xmin, -box.center.y, 0.0))
            solids.append(moved)
            cursor = moved.BoundingBox().xmax + 10.0
    if not solids:
        raise ValueError("Нет деталей модуля: папка parts с мембранным модулем не найдена.")
    return cq.Compound.makeCompound(solids)


def export_modules(modules: ModuleSet, step_path: Path) -> list[Path]:
    """Пишет только модули: имя файла — модуль мелодии, «-дрон» — дрона.

    Принимает ModuleSet и выбранный путь STEP. Свисток: корпус головки как
    сам файл (STEP и STL), «-крышка» и набор «-крышка-h<щель>» у боковой.
    Мембрана: копии parts/head.stl и parts/ring.stl как «<имя>.stl» и
    «<имя>-кольцо.stl» (готовые детали, STEP у них нет). Возвращает пути.
    """
    from bass_tube.body.tube import export_whistle_head

    step_path = Path(step_path)
    saved: list[Path] = []
    for module in modules.voices:
        suffix = "" if module.role == "melody" else "-дрон"
        step = step_path.with_name(f"{step_path.stem}{suffix}{step_path.suffix}")
        stl = step.with_suffix(".stl")
        if module.head is None:
            for source, tail in ((MEMBRANE_MODULE_STL, ""), (MEMBRANE_RING_STL, "-кольцо")):
                if source.exists():
                    target = step.with_name(f"{step.stem}{tail}.stl")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    saved.append(target)
            continue
        saved.extend(
            export_whistle_head(
                module.head,
                step,
                stl,
                step.with_name(f"{step.stem}-крышка{step.suffix}"),
                stl.with_name(f"{stl.stem}-крышка.stl"),
                kit_mm=module.params.whistle_lid_kit_mm,
            )
        )
    return saved
