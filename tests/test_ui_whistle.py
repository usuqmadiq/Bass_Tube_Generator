"""Окно со свистковым источником: поля, правила гашения, отчёт, сохранение, язык."""

from dataclasses import replace
from pathlib import Path

import pytest

from bass_tube.params import ParamsError
from bass_tube.ui.app import TubeApp
from bass_tube.ui.form import default_form, params_from_form


def _disabled(app: TubeApp, name: str) -> bool:
    """Погашено ли поле окна по имени переменной формы."""
    return app._widgets[name].instate(["disabled"])


def test_default_form_stays_membrane() -> None:
    """Стартовая форма — прежняя мембрана: свистковые поля в расчёт не идут."""
    params = params_from_form(default_form())

    assert params.source == "membrane"
    assert params.termination == "open"
    assert params.drone_source == "membrane"
    assert params.whistle_head_kind == "side"


def test_form_passes_whistle_fields() -> None:
    """Свисток: источник, конец, вид головки и геометрия доходят до параметров."""
    form = replace(
        default_form(),
        source="свисток",
        termination="заглушён",
        trim_semitones="0",
        whistle_head_kind="осевая (мундштук)",
        whistle_windway_height="0,8",
        whistle_cutup="12",
        whistle_window_azimuth="90",
        mouth_correction="10",
    )
    params = params_from_form(form)

    assert params.source == "whistle"
    assert params.termination == "stopped"
    assert params.whistle_head_kind == "axial"
    assert params.whistle_windway_height_mm == pytest.approx(0.8)
    assert params.whistle_cutup_mm == pytest.approx(12.0)
    assert params.whistle_windway_length_mm == pytest.approx(4.0)
    assert params.whistle_window_azimuth_deg == pytest.approx(90.0)
    assert params.mouth_correction_mm == pytest.approx(10.0)


def test_form_reads_english_labels() -> None:
    """Подписи списков на английском понимаются так же, как русские."""
    form = replace(
        default_form(),
        source="whistle",
        termination="stopped",
        trim_semitones="0",
        whistle_head_kind="axial (mouthpiece)",
    )
    params = params_from_form(form)

    assert (params.source, params.termination, params.whistle_head_kind) == (
        "whistle",
        "stopped",
        "axial",
    )


def test_form_drops_disabled_fields() -> None:
    """Погашенные поля в расчёт не идут: у мембраны конец открыт, свисток не задан."""
    params = params_from_form(
        replace(
            default_form(),
            termination="заглушён",
            whistle_head_kind="осевая (мундштук)",
            whistle_cutup="16",
            drone_source="свисток",
        )
    )

    assert params.termination == "open"
    assert params.whistle_head_kind == "side"
    assert params.whistle_cutup_mm is None
    assert params.drone_source == "membrane"


def test_form_passes_whistle_drone() -> None:
    """Дрон-свисток: свой источник и конец, геометрия общего свисткового поля."""
    params = params_from_form(
        replace(
            default_form(),
            drone_note="G1",
            drone_source="свисток",
            drone_termination="заглушён",
            drone_trim_semitones="0",
            whistle_cutup="12",
        )
    )

    assert params.source == "membrane"
    assert params.drone_source == "whistle"
    assert params.drone_termination == "stopped"
    assert params.whistle_cutup_mm == pytest.approx(12.0)


def test_form_rejects_bad_whistle_number() -> None:
    """Нечисло в поле свистка отвергается с подписью поля."""
    with pytest.raises(ParamsError) as error:
        params_from_form(replace(default_form(), source="свисток", whistle_cutup="абв"))

    assert "Окно свистка" in str(error.value)


def test_window_rules_follow_the_source() -> None:
    """Поля гаснут и загораются по источнику, концу, виду головки и дрону."""
    app = TubeApp(visible=False)
    try:
        variables = app._vars
        assert _disabled(app, "termination")
        assert _disabled(app, "whistle_cutup")
        assert _disabled(app, "drone_source")
        assert not _disabled(app, "hole_count")

        variables["source"].set("свисток")
        assert not _disabled(app, "termination")
        assert not _disabled(app, "whistle_cutup")
        assert _disabled(app, "whistle_window_azimuth")
        assert _disabled(app, "hole_count") and _disabled(app, "slider_kind")
        assert variables["hole_count"].get() == "0"
        assert not _disabled(app, "trim_semitones")

        variables["termination"].set("заглушён")
        assert _disabled(app, "trim_semitones")
        assert variables["trim_semitones"].get() == "0"

        variables["whistle_head_kind"].set("осевая (мундштук)")
        assert not _disabled(app, "whistle_window_azimuth")
        variables["whistle_window_azimuth"].set("45")
        variables["whistle_head_kind"].set("боковая")
        assert _disabled(app, "whistle_window_azimuth")
        assert variables["whistle_window_azimuth"].get() == "0"

        variables["source"].set("мембрана")
        assert _disabled(app, "termination")
        assert variables["termination"].get() == "открыт"
        assert _disabled(app, "whistle_cutup")
        assert not _disabled(app, "hole_count")
        assert not _disabled(app, "trim_semitones")

        variables["drone_note"].set("G1")
        assert not _disabled(app, "drone_source")
        assert _disabled(app, "drone_termination")
        variables["drone_source"].set("свисток")
        assert not _disabled(app, "drone_termination")
        assert not _disabled(app, "whistle_cutup")
        variables["drone_termination"].set("заглушён")
        assert _disabled(app, "drone_trim_semitones")
        assert variables["drone_trim_semitones"].get() == "0"
    finally:
        app.destroy()


def test_window_builds_axial_whistle_and_saves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Окно строит свисток C2 с заглушённым концом, пишет отчёт и головку."""
    app = TubeApp(visible=False)
    try:
        app._vars["source"].set("свисток")
        app._vars["termination"].set("заглушён")
        app._vars["whistle_head_kind"].set("осевая (мундштук)")
        app.build_model()

        report = app.report_text()
        assert "Источник: свисток" in report
        assert "заглушён" in report
        assert "Пассивный резонанс 65,41 Гц" in report
        assert "не продувалась" in report
        assert "Выход заглушён" in report
        assert app.preview.has_model()
        assert "disabled" not in app.save_button.state()

        target = tmp_path / "свисток-C2.step"
        monkeypatch.setattr(
            "bass_tube.ui.app.filedialog.asksaveasfilename", lambda **_: str(target)
        )
        app.save_model()
        names = {path.name for path in tmp_path.iterdir()}
        assert {
            "свисток-C2.step",
            "свисток-C2.stl",
            "свисток-C2-свисток.step",
            "свисток-C2-свисток.stl",
        } <= names
        assert not any("крышка" in name for name in names)
    finally:
        app.destroy()


def test_window_saves_side_head_with_lid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Боковая головка сохраняется двумя деталями: корпус и съёмная крышка."""
    app = TubeApp(visible=False)
    try:
        app._vars["goal"].set("length")
        app._vars["body_length"].set("300")
        app._vars["source"].set("свисток")
        app._vars["termination"].set("заглушён")
        app.build_model()
        target = tmp_path / "т.step"
        monkeypatch.setattr(
            "bass_tube.ui.app.filedialog.asksaveasfilename", lambda **_: str(target)
        )
        app.save_model()
        names = {path.name for path in tmp_path.iterdir()}
        assert {"т-свисток.stl", "т-свисток-крышка.stl", "т-свисток-крышка.step"} <= names
    finally:
        app.destroy()


def test_window_builds_combined_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Мембрана + осевой свисток-дрон: отчёт пишет разную высоту входов, головку дрона."""
    app = TubeApp(visible=False)
    try:
        app._vars["drone_note"].set("G1")
        app._vars["drone_source"].set("свисток")
        app._vars["drone_termination"].set("заглушён")
        app._vars["whistle_head_kind"].set("осевая (мундштук)")
        app.build_model()

        report = app.report_text()
        assert "входы на разной высоте" in report
        assert "Источник: свисток" in report
        target = tmp_path / "пара.step"
        monkeypatch.setattr(
            "bass_tube.ui.app.filedialog.asksaveasfilename", lambda **_: str(target)
        )
        app.save_model()
        names = {path.name for path in tmp_path.iterdir()}
        assert {"пара.step", "пара-свисток-дрон.step", "пара-свисток-дрон.stl"} <= names
    finally:
        app.destroy()


def test_language_switch_maps_whistle_choices() -> None:
    """Смена языка переводит списки свистка и не сбивает свежесть модели."""
    app = TubeApp(visible=False)
    try:
        app._vars["source"].set("свисток")
        app._vars["termination"].set("заглушён")
        app._vars["whistle_head_kind"].set("осевая (мундштук)")
        app.build_model()
        app.set_language("en", persist=False)

        assert app._vars["source"].get() == "whistle"
        assert app._vars["termination"].get() == "stopped"
        assert app._vars["whistle_head_kind"].get() == "axial (mouthpiece)"
        assert "Source: whistle" in app.report_text()
        assert "disabled" not in app.save_button.state()

        app.set_language("ru", persist=False)
        assert app._vars["source"].get() == "свисток"
        assert app._vars["termination"].get() == "заглушён"
    finally:
        app.destroy()
