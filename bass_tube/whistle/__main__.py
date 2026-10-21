"""CLI прототипа: python -m bass_tube.whistle --help."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from bass_tube.whistle.acoustics import estimate_pair, sound_speed_m_s
from bass_tube.whistle.params import WhistleHeadParams
from bass_tube.whistle.planning import plan_uniform_whistle, uniform_body_length_mm


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
    p.add_argument("--socket-clearance-mm", type=float, default=0.13, help="Зазор ПО ДИАМЕТРУ, не по радиусу.")
    p.add_argument("--socket-depth-mm", type=float, default=8.0)
    p.add_argument("--windway-height-mm", type=float, default=0.6)
    p.add_argument("--windway-width-mm", type=float, default=8.0)
    p.add_argument("--windway-length-mm", type=float, default=12.0)
    p.add_argument("--cutup-mm", type=float, default=8.0, help="Расстояние от выхода щели до лабиума.")
    p.add_argument("--labium-offset-mm", type=float, default=0.0)
    p.add_argument("--edge-thickness-mm", type=float, default=0.3)
    p.add_argument("--mouth-correction-mm", type=float, default=0.0, help="Эквивалентная масса окна в мм канала; 0 = не задана, не калибрована.")
    p.add_argument("--pressure-pa", type=float, default=100.0, help="Пробное избыточное давление перед головкой.")
    p.add_argument("--velocity-coefficient", type=float, default=0.8, help="Предполагаемый коэффициент скорости, не измеренное значение.")
    p.add_argument("--mean-to-center-ratio", type=float, default=1.0, help="Средняя/центральная скорость струи; 1 = приближение ровного профиля.")
    p.add_argument("--temperature-c", type=float, help="При отсутствии используется c=343 м/с.")
    p.add_argument("--pair-spacing-mm", type=float, default=48.0)
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
        head = WhistleHeadParams(
            tube_outer_diameter_mm=args.tube_outer_mm,
            tube_bore_diameter_mm=args.bore_mm,
            socket_clearance_mm=args.socket_clearance_mm,
            socket_depth_mm=args.socket_depth_mm,
            windway_width_mm=args.windway_width_mm,
            windway_height_mm=args.windway_height_mm,
            windway_length_mm=args.windway_length_mm,
            window_length_mm=args.cutup_mm,
            labium_offset_mm=args.labium_offset_mm,
            edge_thickness_mm=args.edge_thickness_mm,
        )
        c = 343.0 if args.temperature_c is None else sound_speed_m_s(args.temperature_c)
        target_hz = args.target_hz
        if args.note:
            from bass_tube.acoustics.notes import midi_number, parse_note_name
            target_hz = 440.0 * 2.0 ** ((midi_number(parse_note_name(args.note)) - 69) / 12.0)

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
            pressure_pa=args.pressure_pa,
            mouth_correction_mm=args.mouth_correction_mm, c=c,
            velocity_coefficient=args.velocity_coefficient,
            mean_to_center_ratio=args.mean_to_center_ratio,
        ) for length in lengths]
        result = {
            "status": "experimental_unvoiced",
            "description": "Heads are generated; the computed tube lengths are inputs for the existing body generator in length mode.",
            "voices": voices,
        }
        if len(voices) == 2:
            import math
            if not math.isfinite(args.pair_spacing_mm) or args.pair_spacing_mm <= 0:
                raise ValueError("Расстояние входов пары должно быть положительным конечным числом.")
            result["pair"] = asdict(estimate_pair(
                voices[0]["passive_frequency_hz"], voices[1]["passive_frequency_hz"],
                voices[0]["air_estimate"]["flow_l_min"], voices[1]["air_estimate"]["flow_l_min"],
            ))
            result["pair"]["inlet_spacing_mm"] = args.pair_spacing_mm
            result["pair"]["common_supply_manifold"] = False
            result["pair"]["warning"] = "Two separate heads and feeds; no guarantee of beat frequency, phase, loudness, or pneumatic/acoustic isolation."
        if args.export_dir is not None:
            result["exports"] = export_heads(head, len(voices), args.pair_spacing_mm, args.export_dir)
            report_path = args.export_dir / "report.json"
            report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, RuntimeError) as exc:
        p.error(str(exc))
        return 2


def export_heads(head: WhistleHeadParams, count: int, spacing: float, directory: Path) -> list[str]:
    """Отдельные печатные детали + STEP в сборочных координатах."""
    import cadquery as cq
    from bass_tube.whistle.geometry import build_head

    parts = build_head(head)
    body = parts.body.val() if hasattr(parts.body, "val") else parts.body
    lid = parts.lid.val() if hasattr(parts.lid, "val") else parts.lid
    if count == 2 and spacing <= max(body.BoundingBox().ylen, lid.BoundingBox().ylen):
        raise ValueError("Головки пересекаются: шаг пары меньше поперечного габарита головки.")
    directory.mkdir(parents=True, exist_ok=True)
    files = []
    assembled = []
    for i in range(count):
        dy = 0.0 if count == 1 else (i - 0.5) * spacing
        for name, shape in (("body", body), ("lid", lid)):
            prefix = f"voice_{i + 1}_{name}"
            on_bed = shape.translate((0, 0, -shape.BoundingBox().zmin))
            for extension in ("step", "stl"):
                filename = prefix + "." + extension
                cq.exporters.export(on_bed, str(directory / filename), tolerance=0.03, angularTolerance=0.08)
                files.append(filename)
            assembled.append(shape.translate((0, dy, 0)))
    cq.exporters.export(cq.Compound.makeCompound(assembled), str(directory / "assembly.step"))
    files.append("assembly.step")
    (directory / "PRINT_README.txt").write_text(
        "ЭКСПЕРИМЕНТАЛЬНАЯ ГОЛОВКА, НЕ ПРОШЛА ПРОДУВКУ.\n\n"
        "Печатайте body и lid отдельно. STL уже имеют нижнюю точку z=0.\n"
        "assembly.step показывает сборку; это не единая деталь для печати.\n"
        "Крышка возвращается на верхние площадки воздушного канала.\n"
        "Прижмите и герметизируйте её снаружи, не перекрывая щель и окно.\n"
        "Поддержки в канале ветра не нужны благодаря съёмной крышке;\n"
        "нависания полости/посадки проверьте в слайсере отдельно.\n"
        "Первый ряд слоёв, нити и шов не должны искажать лабиум.\n"
        "Зазор посадки дан по диаметру и требует проверки на вашем принтере.\n"
        "Для stopped нужна отдельная герметичная заглушка дальнего торца;\n"
        "она НЕ включена в эти файлы и должна подходить реальному выходу.\n"
        "Для пары подавайте воздух в два отдельных входа; общего коллектора нет.\n"
        "JSON содержит пассивную частоту и допущения, а не измеренный строй.\n",
        encoding="utf-8",
    )
    files.append("PRINT_README.txt")
    return files


if __name__ == "__main__":
    sys.exit(main())
