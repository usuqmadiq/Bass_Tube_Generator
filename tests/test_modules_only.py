"""Режим «только модуль»: источники голосов без трубы — ядро, файлы, окно."""

from pathlib import Path

import pytest

from bass_tube import tube_params
from bass_tube.design import build_design
from bass_tube.sources import (
    MEMBRANE_MODULE_STL,
    MEMBRANE_RING_STL,
    build_modules,
    export_modules,
    modules_preview,
)
from bass_tube.ui.app import TubeApp


def _box(**overrides):
    values = dict(
        max_height_mm=250.0,
        max_width_mm=150.0,
        max_depth_mm=150.0,
        head_reserve_mm=35.0,
        turn_radius_mm=11.0,
        gap_mm=1.0,
    )
    values.update(overrides)
    return values


def test_whistle_module_matches_the_full_design():
    """Модуль без трубы — та же голова и тот же строй, что у трубы с модулем."""
    params = tube_params(body_length_mm=1500.0, source="whistle", termination="stopped", **_box())
    (module,) = build_modules(params).voices
    design = build_design(params)

    assert module.role == "melody"
    assert module.tuning.frequency_hz == pytest.approx(design.tuning.frequency_hz)
    assert module.head.params == design.whistle_head.params
    assert module.report["passive_frequency_hz"] == pytest.approx(
        design.whistle_report["passive_frequency_hz"]
    )


def test_modules_skip_the_layout():
    """Труба, которая не влезла бы в стол, модулю не мешает: укладка не строится."""
    params = tube_params(
        body_length_mm=6000.0, source="whistle", termination="stopped",
        **_box(max_height_mm=120.0, max_width_mm=60.0, max_depth_mm=60.0),
    )
    (module,) = build_modules(params).voices
    assert module.head is not None


def test_pair_gives_a_module_per_voice(tmp_path):
    """Пара: модуль мелодии под именем файла, модуль дрона — с «-дрон»."""
    params = tube_params(
        note="C2", drone_note="G1", drone_source="whistle", drone_termination="stopped",
        whistle_head_kind="axial", **_box(),
    )
    modules = build_modules(params)
    assert [(m.role, m.params.source) for m in modules.voices] == [
        ("melody", "membrane"),
        ("drone", "whistle"),
    ]
    names = {p.name for p in export_modules(modules, tmp_path / "м.step")}
    assert {"м.stl", "м-кольцо.stl", "м-дрон.step", "м-дрон.stl"} <= names
    assert (tmp_path / "м.stl").read_bytes() == MEMBRANE_MODULE_STL.read_bytes()
    assert (tmp_path / "м-кольцо.stl").read_bytes() == MEMBRANE_RING_STL.read_bytes()
    assert not any("крышка" in name for name in names)


def test_side_module_saves_head_lid_and_kit(tmp_path):
    """Боковая голова без трубы: корпус под выбранным именем, крышка и набор."""
    params = tube_params(body_length_mm=1500.0, source="whistle", termination="stopped", **_box())
    names = {p.name for p in export_modules(build_modules(params), tmp_path / "с.step")}

    assert {"с.step", "с.stl", "с-крышка.step", "с-крышка.stl", "с-крышка-h1.3.stl"} <= names
    assert not (tmp_path / "с-дрон.stl").exists()


def test_preview_lays_parts_on_the_bed():
    """Кадр модулей: детали в ряд на столе, без пересечений."""
    params = tube_params(body_length_mm=1500.0, source="whistle", termination="stopped", **_box())
    shape = modules_preview(build_modules(params))
    solids = shape.Solids()

    assert len(solids) == 2
    for solid in solids:
        assert solid.BoundingBox().zmin == pytest.approx(0.0, abs=1e-6)
    first, second = (solid.BoundingBox() for solid in solids)
    assert second.xmin >= first.xmax + 9.99


def test_window_builds_and_saves_module_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Окно в режиме «только модуль»: отчёт модуля, сохранение без трубы."""
    app = TubeApp(visible=False)
    try:
        variables = app._vars
        variables["goal"].set("length")
        variables["body_length"].set("1500")
        variables["source"].set("свисток")
        variables["termination"].set("заглушён")
        variables["build_scope"].set("только модуль")
        app.build_model()

        report = app.report_text()
        assert "труба не строится" in report
        assert "Основной тон держится при" in report
        assert app.preview.has_model()
        assert "disabled" not in app.save_button.state()

        captured = {}

        def dialog(**kwargs):
            captured.update(kwargs)
            return str(tmp_path / "голова.step")

        monkeypatch.setattr("bass_tube.ui.app.filedialog.asksaveasfilename", dialog)
        app.save_model()
        names = {p.name for p in tmp_path.iterdir()}
        assert captured["initialfile"] == "свисток-1500мм.step"
        assert {"голова.step", "голова.stl", "голова-крышка.stl"} <= names
        assert not any("свисток" in name or "мембрана" in name for name in names)

        app.set_language("en", persist=False)
        assert variables["build_scope"].get() == "module only"
        assert "no tube is built" in app.report_text()
        assert "disabled" not in app.save_button.state()
    finally:
        app.destroy()


def test_window_tube_mode_is_unchanged() -> None:
    """По умолчанию окно строит трубу с модулем, как раньше."""
    app = TubeApp(visible=False)
    try:
        assert app._vars["build_scope"].get() == "трубу с модулем"
    finally:
        app.destroy()
