"""CLI прототипа: python -m bass_tube.whistle --help."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from bass_tube.whistle.acoustics import estimate_pair, sound_speed_m_s
from bass_tube.whistle.axial_head import AxialHeadError, AxialHeadParams
from bass_tube.whistle.manifold import ManifoldParams, WhistleManifoldError
from bass_tube.whistle.params import WhistleHeadParams
from bass_tube.whistle.planning import flue_tuning, plan_uniform_whistle, uniform_body_length_mm


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Экспериментальная лабиальная головка: CAD и пассивная акустика, без гарантии запуска.",
    )
    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("--body-length-mm", type=float, help="Длина уже существующей ровной трубы, включая посадку.")
    target.add_argument("--target-hz", type=float, help="Целевая пассивная частота для расчёта длины новой ровной трубы.")
    target.add_argument("--note", help="Целевая нота новой трубы, например C2.")
    second = p.add_mutually_exclusive_group()
    second.add_argument("--second-body-length-mm", type=float)
    second.add_argument("--second-target-hz", type=float)
    p.add_argument("--termination", choices=("open", "stopped"), default="open")
    p.add_argument("--tube-outer-mm", type=float, default=19.5)
    p.add_argument("--bore-mm", type=float, default=15.5)
    p.add_argument("--socket-clearance-mm", type=float, default=0.43, help="Зазор гнезда ПО ДИАМЕТРУ; 0,13 на FDM не садится до упора.")
    p.add_argument("--socket-depth-mm", type=float, default=8.0)
    p.add_argument("--windway-height-mm", type=float, default=None, help="Щель h; по умолчанию окно/12.")
    p.add_argument("--windway-width-mm", type=float, default=None, help="Ширина щели B; по умолчанию 12 у боковой, 9 у осевой.")
    p.add_argument("--windway-length-mm", type=float, default=None, help="Длина ветрового канала; по умолчанию 12 у боковой головы и 4 у осевой.")
    p.add_argument("--mouthpiece-head", action="store_true", help="Осевая голова под готовый двойной мундштук: подача сверху, окно вбок, без крышки.")
    p.add_argument("--window-azimuth-deg", type=float, default=0.0, help="Поворот окна осевой головы вокруг оси, градусы.")
    p.add_argument("--cutup-mm", type=float, default=None, help="Окно до кромки W; по умолчанию — под давление дутья (θ ≈ 11).")
    p.add_argument("--blow-pressure-pa", type=float, default=200.0, help="Давление дутья, под которое подбирается окно.")
    p.add_argument("--lid-kit", default="0.6,0.8,1,1.3,1.6,2,2.5", help="Щели сменных крышек боковой головы через запятую; пусто — без набора.")
    p.add_argument("--labium-offset-mm", type=float, default=0.0)
    p.add_argument("--edge-thickness-mm", type=float, default=0.3)
    p.add_argument("--mouth-correction-mm", type=float, default=0.0, help="Эквивалентная масса окна в мм канала; 0 = не задана, не калибрована.")
    p.add_argument("--pressure-pa", type=float, default=None, help="Давление для паспорта; по умолчанию — давление дутья.")
    p.add_argument("--velocity-coefficient", type=float, default=0.8, help="Предполагаемый коэффициент скорости, не измеренное значение.")
    p.add_argument("--mean-to-center-ratio", type=float, default=1.0, help="Средняя/центральная скорость струи; 1 = приближение ровного профиля.")
    p.add_argument("--temperature-c", type=float, help="При отсутствии используется c=343 м/с.")
    p.add_argument("--pair-spacing-mm", type=float, default=48.0)
    p.add_argument("--port-diameter-mm", type=float, default=8.0, help="Порт коллектора пары: один вход на оба ветровых канала.")
    p.add_argument("--no-manifold", action="store_true", help="Пара без коллектора: две раздельные подачи, как раньше.")
    p.add_argument("--export-dir", type=Path, help="Папка STEP/STL, сборки и JSON-паспорта; без неё только JSON.")
    return p


def main(argv: list[str] | None = None) -> int:
    # Консоль Windows в cp1251 не кодирует θ из примечаний паспорта и
    # роняла вывод уже после записи файлов; файл отчёта остаётся UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    p = parser()
    args = p.parse_args(argv)
    try:
        c = 343.0 if args.temperature_c is None else sound_speed_m_s(args.temperature_c)
        target_hz = args.target_hz
        if args.note:
            from bass_tube.acoustics.notes import midi_number, parse_note_name
            target_hz = 440.0 * 2.0 ** ((midi_number(parse_note_name(args.note)) - 69) / 12.0)
        frequency = target_hz if target_hz is not None else _frequency_estimate_hz(
            args.body_length_mm, args.termination, c, args.bore_mm,
        )
        flue, cutup = _flue(args, frequency)
        kit = _lid_kit(args.lid_kit) if not args.mouthpiece_head else ()
        pressure = args.blow_pressure_pa if args.pressure_pa is None else args.pressure_pa
        width = args.windway_width_mm
        if width is None:
            width = 9.0 if args.mouthpiece_head else 12.0
        shared = dict(
            tube_outer_diameter_mm=args.tube_outer_mm,
            tube_bore_diameter_mm=args.bore_mm,
            socket_clearance_mm=args.socket_clearance_mm,
            socket_depth_mm=args.socket_depth_mm,
            windway_width_mm=width,
            windway_height_mm=flue,
            window_length_mm=cutup,
            labium_offset_mm=args.labium_offset_mm,
            edge_thickness_mm=args.edge_thickness_mm,
        )
        if args.mouthpiece_head:
            head = AxialHeadParams(
                windway_length_mm=4.0 if args.windway_length_mm is None else args.windway_length_mm,
                window_azimuth_deg=args.window_azimuth_deg,
                **shared,
            )
        else:
            head = WhistleHeadParams(
                windway_length_mm=12.0 if args.windway_length_mm is None else args.windway_length_mm,
                channel_depth_mm=max((flue, *kit)),
                **shared,
            )

        def length_for(target):
            return uniform_body_length_mm(
                target, head, termination=args.termination,
                mouth_correction_mm=args.mouth_correction_mm, c=c,
            )

        lengths = [length_for(target_hz) if target_hz is not None else args.body_length_mm]
        if args.second_target_hz is not None:
            lengths.append(length_for(args.second_target_hz))
        elif args.second_body_length_mm is not None:
            lengths.append(args.second_body_length_mm)
        voices = [plan_uniform_whistle(
            length, head, termination=args.termination,
            pressure_pa=pressure,
            mouth_correction_mm=args.mouth_correction_mm, c=c,
            velocity_coefficient=args.velocity_coefficient,
            mean_to_center_ratio=args.mean_to_center_ratio,
        ) for length in lengths]
        for voice in voices:
            voice["flue_tuning"] = flue_tuning(
                head, voice["passive_frequency_hz"], pressure, kit
            )
        result = {
            "status": "experimental_unvoiced",
            "description": "Heads are generated; the computed tube lengths are inputs for the existing body generator in length mode.",
            "voices": voices,
        }
        manifold = None
        if len(voices) == 2:
            import math
            if not math.isfinite(args.pair_spacing_mm) or args.pair_spacing_mm <= 0:
                raise ValueError("Расстояние входов пары должно быть положительным конечным числом.")
            result["pair"] = asdict(estimate_pair(
                voices[0]["passive_frequency_hz"], voices[1]["passive_frequency_hz"],
                voices[0]["air_estimate"]["flow_l_min"], voices[1]["air_estimate"]["flow_l_min"],
            ))
            result["pair"]["inlet_spacing_mm"] = args.pair_spacing_mm
            if args.mouthpiece_head:
                result["pair"]["manifold_note"] = (
                    "Axial heads are fed by the existing dual mouthpiece (48 mm sockets); "
                    "no printed manifold is generated."
                )
            elif not args.no_manifold:
                try:
                    manifold = ManifoldParams(
                        head=head,
                        spacing_mm=args.pair_spacing_mm,
                        port_diameter_mm=args.port_diameter_mm,
                    )
                except WhistleManifoldError as exc:
                    raise ValueError(str(exc)) from exc
                result["pair"]["manifold"] = {
                    "spacing_mm": manifold.spacing_mm,
                    "wall_mm": manifold.wall_mm,
                    "fit_clearance_mm": manifold.fit_clearance_mm,
                    "plenum_depth_mm": manifold.plenum_depth_mm,
                    "port_diameter_mm": manifold.port_diameter_mm,
                    "grip_mm": manifold.grip_resolved_mm,
                    "warnings": [
                        "The plenum joins the air ONLY upstream of both windways; resonator cavities stay separate.",
                        "Pocket and lid joints are not airtight by printing alone: clamp and seal externally during tests.",
                        "The plenum volume and the shared supply coupling are not acoustically calibrated.",
                    ],
                }
            result["pair"]["common_supply_manifold"] = manifold is not None
            result["pair"]["warning"] = "No guarantee of beat frequency, phase, loudness, or pneumatic/acoustic isolation."
        if args.export_dir is not None:
            result["exports"] = export_heads(
                head, len(voices), args.pair_spacing_mm, args.export_dir, manifold, kit
            )
            report_path = args.export_dir / "report.json"
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, RuntimeError) as exc:
        p.error(str(exc))
        return 2


def export_heads(
    head: WhistleHeadParams,
    count: int,
    spacing: float,
    directory: Path,
    manifold: ManifoldParams | None = None,
    kit: tuple[float, ...] = (),
) -> list[str]:
    """Отдельные печатные детали + STEP в сборочных координатах.

    Для пары с коллектором дополнительно пишет manifold.step/stl в печатной
    ориентации (портом вниз) и кладёт коллектор в сборку на месте.
    У осевой головы (--mouthpiece-head) крышки нет: одна деталь на голос,
    общую подачу пары даёт готовый двойной мундштук.
    """
    import cadquery as cq

    if isinstance(head, AxialHeadParams):
        from bass_tube.whistle.axial_head import build_axial_head

        axial = build_axial_head(head)
        named_shapes = [("body", axial.solid.val())]
    else:
        from bass_tube.whistle.geometry import build_head

        parts = build_head(head)
        body = parts.body.val() if hasattr(parts.body, "val") else parts.body
        lid = parts.lid.val() if hasattr(parts.lid, "val") else parts.lid
        named_shapes = [("body", body), ("lid", lid)]
    widest = max(shape.BoundingBox().ylen for _, shape in named_shapes)
    if count == 2 and spacing <= widest:
        raise ValueError("Головки пересекаются: шаг пары меньше поперечного габарита головки.")
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    assembled = []
    for i in range(count):
        dy = 0.0 if count == 1 else (i - 0.5) * spacing
        for name, shape in named_shapes:
            prefix = f"voice_{i + 1}_{name}"
            on_bed = shape.translate((0, 0, -shape.BoundingBox().zmin))
            for extension in ("step", "stl"):
                filename = prefix + "." + extension
                cq.exporters.export(on_bed, str(directory / filename), tolerance=0.03, angularTolerance=0.08)
                files.append(filename)
            assembled.append(shape.translate((0, dy, 0)))
    if kit and not isinstance(head, AxialHeadParams):
        from bass_tube.whistle.geometry import lid_kit

        for flue_mm, lid in lid_kit(head, kit).items():
            for extension in ("step", "stl"):
                filename = f"lid_h{flue_mm:g}.{extension}"
                cq.exporters.export(lid, str(directory / filename), tolerance=0.03, angularTolerance=0.08)
                files.append(filename)
    if manifold is not None and count == 2:
        from bass_tube.whistle.manifold import build_manifold

        collector = build_manifold(manifold)
        printable = collector.print_part()
        for extension in ("step", "stl"):
            filename = "manifold." + extension
            cq.exporters.export(printable, str(directory / filename), tolerance=0.03, angularTolerance=0.08)
            files.append(filename)
        assembled.append(collector.solid.val())
    cq.exporters.export(cq.Compound.makeCompound(assembled), str(directory / "assembly.step"))
    files.append("assembly.step")
    if isinstance(head, AxialHeadParams):
        build_lines = (
            "Осевая голова: одна деталь на голос, крышки нет. Печать гнездом вниз.\n"
            "Подача сверху готовым двойным мундштуком: его трубка торцом на наш\n"
            "сплошной торец, юбка — на кольцо стакана, губа центрирует юбку.\n"
            "Воздух идёт кольцом мундштука в стакан и каналами вниз к щели;\n"
            "центр мундштука — отдушина, её закрывает наш торец. Оба стыка\n"
            "прижать плотно (при нужде тонкое кольцо-прокладка): щель на торце\n"
            "трубок сливает давление в отдушину. Окна смотрят вбок, их\n"
            "ориентацию задаёт --window-azimuth-deg (разворачивайте от себя).\n"
            "Пластина-язычок печатается мостом над каналом: проверьте слайсером.\n"
        )
        pair_lines = (
            "Пара: обе головы под гнёзда мундштука на шаге 48 мм, дуть в него.\n"
            if count == 2
            else ""
        )
    else:
        build_lines = (
            "Печатайте body и lid отдельно. STL уже имеют нижнюю точку z=0.\n"
            "Крышка возвращается на верхние площадки воздушного канала.\n"
            "Прижмите и герметизируйте её снаружи, не перекрывая щель и окно.\n"
            "Поддержки в канале ветра не нужны благодаря съёмной крышке;\n"
            "lid_h*.stl — сменные крышки: число — щель, мм. Крышка лежит на\n"
            "столе гранью потолка щели. Тихо и без баса — щель больше.\n"
            "нависания полости/посадки проверьте в слайсере отдельно.\n"
        )
        pair_lines = (
            "Коллектор manifold.stl печатается портом вниз, как лежит в файле.\n"
            "Он надевается карманами на концы щёк обеих голов и прижимает их\n"
            "крышки; стыки герметизируйте снаружи лентой или прижимом.\n"
            "Воздух соединяется только перед щелями; полости после лабиумов\n"
            "раздельны. Дуйте в круглый порт передней стенки.\n"
            if manifold is not None and count == 2
            else "Для пары подавайте воздух в два отдельных входа; общего коллектора нет.\n"
        )
    (directory / "PRINT_README.txt").write_text(
        "ЭКСПЕРИМЕНТАЛЬНАЯ ГОЛОВКА, НЕ ПРОШЛА ПРОДУВКУ.\n\n"
        + build_lines
        + "assembly.step показывает сборку; это не единая деталь для печати.\n"
        "Первый ряд слоёв, нити и шов не должны искажать лабиум.\n"
        "Зазор посадки дан по диаметру и требует проверки на вашем принтере.\n"
        "Для stopped нужна отдельная герметичная заглушка дальнего торца;\n"
        "она НЕ включена в эти файлы и должна подходить реальному выходу.\n"
        + pair_lines
        + "JSON содержит пассивную частоту и допущения, а не измеренный строй.\n",
        encoding="utf-8",
    )
    files.append("PRINT_README.txt")
    return files


def _frequency_estimate_hz(length_mm: float, termination: str, c: float, bore_mm: float) -> float:
    """Ориентир основного тона по длине: идеальный столб плюс шейка ~12,5 мм."""
    length = length_mm + 12.5
    if termination == "stopped":
        return c * 1000.0 / (4.0 * length)
    return c * 1000.0 / (2.0 * (length + 0.3 * bore_mm))


def _flue(args, frequency: float) -> tuple[float, float]:
    """Щель и окно: заданные или под давление дутья, как в генераторе."""
    from bass_tube.constants import (
        WHISTLE_AUTO_CUTUP_LIMITS_MM,
        WHISTLE_AUTO_FLUE_LIMITS_MM,
        WHISTLE_CUTUP_TO_FLUE,
        WHISTLE_THETA_TARGET,
    )
    from bass_tube.whistle.params import cutup_for_pressure_mm

    cutup = args.cutup_mm
    if cutup is None:
        raw = cutup_for_pressure_mm(frequency, args.blow_pressure_pa, WHISTLE_THETA_TARGET)
        low, high = WHISTLE_AUTO_CUTUP_LIMITS_MM
        cutup = min(max(round(raw * 2.0) / 2.0, low), high)
    flue = args.windway_height_mm
    if flue is None:
        low, high = WHISTLE_AUTO_FLUE_LIMITS_MM
        flue = min(max(round(cutup / WHISTLE_CUTUP_TO_FLUE, 1), low), high)
    return flue, cutup


def _lid_kit(text: str) -> tuple[float, ...]:
    """Щели набора крышек из строки «0.6,0.8,1»; пусто — без набора."""
    items = [item.strip() for item in (text or "").split(",") if item.strip()]
    return tuple(sorted({float(item) for item in items}))


if __name__ == "__main__":
    sys.exit(main())
