"""Окно: разбор полей, кадр предпросмотра и построение контрольной вязанки C2."""

from dataclasses import replace
from pathlib import Path

import cadquery as cq
import pytest

from bass_tube.params import ParamsError
from bass_tube.ui.app import TubeApp
from bass_tube.ui.form import (
    default_form,
    derived_form_updates,
    numeric_text_ok,
    params_from_form,
    suggested_stem,
)
from bass_tube.ui.preview import PreviewScene


def test_default_form_is_control_c2() -> None:
    """Стартовая форма собирает контрольную ноту C2.

    Ничего не принимает. Проверяет режим ноты, канал 15,5 мм и
    поправку открытого конца 0,6 радиуса. Ничего не возвращает.
    """
    params = params_from_form(default_form())
    assert params.note == "C2"
    assert params.body_length_mm is None
    assert params.bore_diameter_mm == pytest.approx(15.5)
    assert params.delta_out_mm == pytest.approx(4.65)
    assert params.layout == "bundle"
    assert params.straight_count is None
    assert params.has_transition is False
    assert params.trim_semitones == 1
    assert params.hole_count == 0
    assert params.scale == "natural_minor"
    assert params.seat_outer_diameter_mm == pytest.approx(19.5)
    assert params.hole_diameter_mm == pytest.approx(8.0)
    assert params.slider_kind == ""
    assert params.slider_semitones == 0
    assert params.slider_pairs == 0
    assert params.print_splits is True
    assert params.slider_clearance_mm == pytest.approx(0.3)
    assert params.drone_note is None
    assert params.drone_trim_semitones == 0
    assert params.speed_of_sound_m_s == pytest.approx(343.0)
    assert not hasattr(default_form(), "speed")


def test_form_raises_turn_radius_when_outer_grows() -> None:
    """Труба 30 мм в форме поднимает радиус разворота под диаметр, скорость звука не спрашивает.

    Ничего не принимает. Старый радиус 11 мм становится (30 + 1)/√3 ≈ 17,9 мм:
    колено между соседними прямыми не должно касаться их общего соседа.
    Пустой радиус так и остаётся пустым — это «самый тесный».
    Ничего не возвращает.
    """
    updates = derived_form_updates("30", "2", "19.5", "3", "11", "1", "150")
    assert float(updates["turn_radius"]) == pytest.approx(31 / 3**0.5, abs=0.01)
    assert "speed" not in updates
    assert "turn_radius" not in derived_form_updates("30", "2", "", "3", "", "1", "150")


def test_window_does_not_rewrite_fields_while_typing() -> None:
    """Недописанный диаметр не переписывает стенку и глубину до конца ввода.

    Ничего не принимает. Набирает «3» в диаметр и «1» в глубину — соседи
    не меняются. После завершения ввода (уход из поля) диаметр 30 мм
    поднимает глубину и радиус остаётся пустым. Ничего не возвращает.
    """
    app = TubeApp(visible=False)
    try:
        wall = app._vars["wall"].get()
        app._vars["outer_diameter"].set("3")
        app._vars["max_depth"].set("1")
        assert app._vars["wall"].get() == wall
        assert app._vars["max_depth"].get() == "1"
        app._vars["outer_diameter"].set("30")
        app._vars["max_depth"].set("150")
        app.commit_dependents()
        assert app._vars["wall"].get() == wall
        assert app._vars["turn_radius"].get() == ""
        assert "конец 19,5" in app.seat_bore_label.cget("text")
    finally:
        app.destroy()


def test_form_passes_count_transition_and_trim() -> None:
    """Явные 5 прямых, труба 30 мм с автопереходником и два полутона подстройки доходят до параметров.

    Ничего не принимает. Пустое поле переходника даёт конус 15°,
    дробное число прямых и дробная подстройка отвергаются. Пустая подстройка — ноль.
    Ничего не возвращает.
    """
    form = replace(default_form(), straight_count="5", outer_diameter="30", trim_semitones="2")
    params = params_from_form(form)
    assert params.layout == "bundle"
    assert params.straight_count == 5
    assert params.trim_semitones == 2
    assert params.has_transition is True
    assert params.transition_length_mm > 0.0

    assert params_from_form(replace(default_form(), trim_semitones="")).trim_semitones == 0
    assert params_from_form(replace(default_form(), straight_count="авто")).straight_count is None
    assert params_from_form(replace(default_form(), straight_count="")).straight_count is None

    with pytest.raises(ParamsError, match="целое"):
        params_from_form(replace(default_form(), straight_count="2,5"))
    with pytest.raises(ParamsError, match="целое"):
        params_from_form(replace(default_form(), trim_semitones="1,5"))


def test_form_passes_holes_and_scale() -> None:
    """Число дырок, лад по русской подписи и пустые поля доходят до параметров.

    Ничего не принимает. Три отверстия и «мажор» дают major. Пустое число
    дырок — ноль. Пустой диаметр — 8 мм. Девять дырок отвергаются.
    Ничего не возвращает.
    """
    form = replace(default_form(), hole_count="3", scale="мажор")
    params = params_from_form(form)
    assert params.hole_count == 3
    assert params.scale == "major"
    assert params.hole_diameter_mm == pytest.approx(8.0)

    assert params_from_form(replace(default_form(), hole_count="")).hole_count == 0
    assert params_from_form(replace(default_form(), hole_diameter="")).hole_diameter_mm == pytest.approx(8.0)
    assert params_from_form(replace(default_form(), scale="melodic_minor")).scale == "melodic_minor"

    with pytest.raises(ParamsError, match="пальцев"):
        params_from_form(replace(default_form(), hole_count="9"))
    with pytest.raises(ParamsError, match="не известен"):
        params_from_form(replace(default_form(), hole_count="2", scale="блюз"))


def test_form_passes_slider_and_rejects_it_with_holes() -> None:
    """Схема слайдера по русской подписи доходит до параметров, с дырками — нет.

    Ничего не принимает. U-колено и два полутона принимаются даже если
    в форме ещё стоит подстройка по умолчанию: трубка сама гасится.
    Слайдер вместе с отверстиями отвергается.
    Ничего не возвращает.
    """
    form = replace(
        default_form(),
        slider_kind="U-колено",
        slider_semitones="2",
    )
    params = params_from_form(form)
    assert params.slider_kind == "u"
    assert params.slider_semitones == 2
    assert params.trim_semitones == 0
    assert params.slider_clearance_mm == pytest.approx(0.3)

    double = replace(default_form(), slider_kind="двойное U", slider_semitones="2")
    assert params_from_form(double).slider_kind == "uu"

    auto = replace(default_form(), slider_kind="U авто", slider_semitones="2")
    assert params_from_form(auto).slider_kind == "uauto"

    triples = replace(
        default_form(), slider_kind="U-колено", slider_semitones="2", slider_pairs="3"
    )
    assert params_from_form(triples).slider_pairs == 3

    no_split = replace(default_form(), print_splits="нет")
    assert params_from_form(no_split).print_splits is False

    wide = replace(default_form(), slider_kind="U-колено", slider_semitones="2", slider_clearance="0,5")
    assert params_from_form(wide).slider_clearance_mm == pytest.approx(0.5)

    assert params_from_form(replace(default_form(), slider_kind="нет")).slider_kind == ""
    assert params_from_form(replace(default_form(), slider_semitones="")).slider_semitones == 0
    assert params_from_form(replace(default_form(), slider_clearance="")).slider_clearance_mm == pytest.approx(0.3)

    with pytest.raises(ParamsError, match="со всех сторон"):
        params_from_form(
            replace(
                default_form(),
                slider_kind="U-колено",
                slider_semitones="2",
                slider_clearance="0,2",
            )
        )

    with pytest.raises(ParamsError, match="Слайдер и отверстия"):
        params_from_form(
            replace(
                default_form(),
                trim_semitones="0",
                hole_count="3",
                slider_kind="выдвижной конец",
                slider_semitones="2",
            )
        )


def test_form_passes_drone_note_and_default_trim() -> None:
    """Нота дрона доходит до параметров, пустая подстройка дрона — один полутон.

    Ничего не принимает. Пустая нота дрона — один голос. Нота без октавы
    у дрона отвергается.
    Ничего не возвращает.
    """
    form = replace(default_form(), drone_note="g1")
    params = params_from_form(form)
    assert params.drone_note == "G1"
    assert params.drone_trim_semitones == 1
    assert suggested_stem(params) == "труба-C2-G1"

    assert params_from_form(replace(default_form(), drone_note="")).drone_note is None
    assert params_from_form(replace(default_form(), drone_note="нет")).drone_note is None
    explicit = replace(default_form(), drone_note="G2", drone_trim_semitones="0")
    assert params_from_form(explicit).drone_trim_semitones == 0

    with pytest.raises(ParamsError, match="Дрон"):
        params_from_form(replace(default_form(), drone_note="G"))


def test_form_accepts_comma_decimals() -> None:
    """Запятая в поле читается как десятичный разделитель.

    Ничего не принимает. Подменяет наружный диаметр на «19,5».
    Ничего не возвращает.
    """
    params = params_from_form(replace(default_form(), outer_diameter="19,5"))
    assert params.outer_diameter_mm == pytest.approx(19.5)


def test_numeric_filter_lets_unfinished_numbers_through() -> None:
    """Фильтр набора пропускает недописанные числа и режет мусор.

    Ничего не принимает. Пустое, минус, «19,» и «-0.5» проходят, буквы
    и вторая запятая — нет. Ничего не возвращает.
    """
    for text in ("", "-", "19", "19,", "19,5", "-0.5", ".5"):
        assert numeric_text_ok(text), text
    for text in ("1a", "19,5,", "1-", "--1", "19.5.1"):
        assert not numeric_text_ok(text), text


def test_form_rejects_note_without_octave() -> None:
    """Нота без октавы не проходит в параметры.

    Ничего не принимает. Ожидает ParamsError с причиной про октаву.
    Ничего не возвращает.
    """
    with pytest.raises(ParamsError, match="без октавы"):
        params_from_form(replace(default_form(), note="C"))


def test_preview_box_is_visible() -> None:
    """Кадр коробки не пустой и совпадает с запрошенным размером.

    Ничего не принимает. Строит маленький параллелепипед и снимает кадр.
    Ничего не возвращает.
    """
    scene = PreviewScene()
    scene.show_shape(cq.Workplane("XY").box(20, 10, 8).val())
    image = scene.image(320, 240)
    assert image.size == (320, 240)
    colors = image.getcolors(maxcolors=320 * 240)
    assert colors is not None
    assert len(colors) > 1


def test_window_rejects_note_without_octave() -> None:
    """Окно показывает причину и не включает сохранение.

    Ничего не принимает. Ставит ноту «C» и строит модель.
    Ничего не возвращает.
    """
    app = TubeApp(visible=False)
    try:
        app._vars["note"].set("C")
        app.build_model()
        assert "без октавы" in app.report_text()
        assert not app.preview.has_model()
        assert "disabled" in app.save_button.state()
    finally:
        app.destroy()


def test_window_builds_control_c2_and_saves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Окно строит C2, держит сохранение в паре с полями и пишет оба файла.

    Принимает временный каталог и подмену диалога. Сначала проверяет, что
    слайдер сам гасит подстройку. Затем строит стартовую трубу, меняет ноту
    и возвращает её, затем сохраняет STEP и соседний STL.
    Ничего не возвращает.
    """
    app = TubeApp(visible=False)
    try:
        assert app._vars["trim_semitones"].get() == "1"
        app._vars["slider_kind"].set("U-колено")
        assert app._vars["trim_semitones"].get() == "0"
        assert app._vars["slider_semitones"].get() == "1"
        assert "disabled" in app.trim_entry.state()
        app._vars["slider_kind"].set("нет")
        assert app._vars["slider_semitones"].get() == ""
        app._vars["trim_semitones"].set("1")

        app.build_model()
        report = app.report_text()
        assert "1306" in report
        assert "не калибрована" in report
        assert "вязанка" in report
        assert "Прямых: 7" in report
        assert "Подстройка" in report
        assert app.preview.has_model()
        assert "disabled" not in app.save_button.state()

        app._vars["note"].set("D2")
        assert app.preview.has_model()
        assert "disabled" in app.save_button.state()

        app._vars["note"].set("C2")
        assert "disabled" not in app.save_button.state()

        target = tmp_path / "труба.step"
        monkeypatch.setattr(
            "bass_tube.ui.app.filedialog.asksaveasfilename",
            lambda **_kwargs: str(target),
        )
        app.save_model()
        assert target.is_file()
        assert target.with_suffix(".stl").is_file()
        tuner_step = target.with_name("труба-подстройка.step")
        tuner_stl = target.with_name("труба-подстройка.stl")
        assert tuner_step.is_file()
        assert tuner_stl.is_file()
        assert "Сохранено" in app.status.get()
    finally:
        app.destroy()


def test_form_parses_english_choice_labels() -> None:
    """Английские подписи списков собирают те же параметры, что русские.

    Ничего не принимает. Включает английский, берёт стартовую форму,
    проверяет разрезы, лад, авто, U-колено и выключенный дрон.
    Язык процесса возвращает на русский. Ничего не возвращает.
    """
    from bass_tube.ui.i18n import set_current_language

    set_current_language("en")
    try:
        form = default_form()
        assert form.print_splits == "yes"
        params = params_from_form(form)
        assert params.print_splits is True
        assert params.scale == "natural_minor"
        parsed = params_from_form(
            replace(
                form,
                print_splits="no",
                straight_count="auto",
                scale="major",
                slider_kind="U-bend",
                slider_semitones="2",
                drone_note="none",
            )
        )
        assert parsed.print_splits is False
        assert parsed.straight_count is None
        assert parsed.scale == "major"
        assert parsed.slider_kind == "u"
        assert parsed.drone_note is None
    finally:
        set_current_language("ru")


def test_window_switches_to_english() -> None:
    """Кнопка языка меняет заголовок, кнопки и подписи, параметры те же.

    Ничего не принимает. Открывает скрытое окно по-русски, переключает
    на английский без записи на диск, проверяет заголовок и разбор
    полей, затем возвращает русский. Ничего не возвращает.
    """
    from bass_tube.ui.i18n import set_current_language

    app = TubeApp(visible=False, language="ru")
    try:
        assert app.root.title() == "Генератор басовой трубы"
        app.set_language("en", persist=False)
        assert app.root.title() == "Bass tube generator"
        assert app.build_button.cget("text") == "Build"
        params = params_from_form(app.form_input())
        assert params.note == "C2"
        assert params.print_splits is True
        assert params.scale == "natural_minor"
        assert params.slider_kind == ""
        assert params.drone_note is None
        assert "Tube bore" in app.bore_label.cget("text")
        app.set_language("ru", persist=False)
        assert app.root.title() == "Генератор басовой трубы"
        assert "Канал трубы" in app.bore_label.cget("text")
    finally:
        set_current_language("ru")
        app.destroy()

