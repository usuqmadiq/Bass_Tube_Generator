"""Язык окна: русские и английские подписи, выбор запоминается.

Расчёт и отказы ядра остаются на языке кода. Здесь только то, что видно
в окне: шапка, поля, подсказки, статус, отчёт и диалоги.
"""

from __future__ import annotations

import json
from pathlib import Path

# Коды языков окна.
LANG_RU = "ru"
LANG_EN = "en"
LANGS = (LANG_RU, LANG_EN)

# Файл рядом с домашней папкой пользователя: {"lang": "en"}.
_CONFIG_PATH = Path.home() / ".bass_tube_ui.json"

# Текущий язык процесса. Стартует русским, пока окно не прочитает файл.
_current = LANG_RU

# Подписи окна. Ключ один для обоих языков.
STRINGS: dict[str, dict[str, str]] = {
    LANG_RU: {
        "app.title": "Генератор басовой трубы",
        "app.subtitle": "Параметрическая модель под 3D-печать",
        "action.build": "Построить",
        "action.save": "Сохранить…",
        "dialog.save_title": "Куда сохранить трубу. STL запишется рядом",
        "status.start": "Задайте параметры и нажмите «Построить».",
        "status.busy": "Считаю и строю модель…",
        "status.ready": "Модель построена. Её можно вращать и сохранить.",
        "status.preview_fail": "Модель посчитана, предпросмотр не открылся: {exc}",
        "status.build_first": "Сначала постройте модель по текущим полям.",
        "status.saved": "Сохранено: {paths}",
        "status.fresh": "Модель совпадает с полями. Её можно сохранить.",
        "status.stale": "Параметры изменились. На экране прошлая модель — постройте заново.",
        "status.reject": "Поправить параметры и построить снова.",
        "lang.ru": "RU",
        "lang.en": "EN",
        "lang.switch": "Язык интерфейса",
        "group.goal": "Цель",
        "group.tube": "Труба",
        "group.joint": "Конец под модуль",
        "group.envelope": "Габарит",
        "group.layout": "Укладка",
        "group.holes": "Отверстия",
        "group.slider": "Слайдер",
        "group.drone": "Дрон",
        "group.corrections": "Поправки",
        "group.reference": "Опорный строй",
        "goal.note": "Нота",
        "goal.length": "Длина корпуса",
        "field.note": "Нота",
        "field.body_length": "Длина корпуса, мм",
        "field.outer_diameter": "Наружный диаметр, мм",
        "field.wall": "Стенка, мм",
        "field.seat_outer": "Наружный диаметр конца, мм",
        "field.module_hole": "Отверстие модуля, мм",
        "field.seat": "Посадка, мм",
        "field.transition": "Переходник, мм",
        "field.max_height": "Высота, мм",
        "field.max_width": "Ширина, мм",
        "field.max_depth": "Глубина, мм",
        "field.head_reserve": "Резерв под модуль, мм",
        "field.print_splits": "Разрезы на печать",
        "field.straight_count": "Прямых",
        "field.turn_radius": "Радиус разворота, мм",
        "field.gap": "Зазор между трубами, мм",
        "field.floor": "Дно под каналом, мм",
        "field.trim": "Подстройка, полутонов вниз",
        "field.hole_count": "Число, до 8",
        "field.scale": "Лад",
        "field.hole_diameter": "Диаметр дырки, мм",
        "field.slider_kind": "Схема",
        "field.slider_semitones": "Полутонов вниз",
        "field.slider_pairs": "Колен U",
        "field.slider_clearance": "Зазор вокруг царги, мм",
        "field.drone_note": "Нота дрона",
        "field.drone_trim": "Подстройка дрона, полутонов вниз",
        "field.delta_head": "Головка, мм",
        "field.delta_out": "Открытый конец, мм",
        "field.delta_bends": "Изгибы, мм",
        "field.a4": "A4, Гц",
        "hint.diameter_master": (
            "Диаметр главный: стенка, дно, радиус разворота и глубина подтягиваются "
            "под него, когда уходишь из поля, жмёшь Enter или «Построить»."
        ),
        "hint.joint": (
            "Конец пусто — под отверстие модуля со штатным зазором. Конец толще "
            "отверстия ужимается сам. Если труба толще конца, между ними конус; "
            "переходник пусто — угол 15°."
        ),
        "hint.splits": (
            "Да — резать корпус и царгу на куски стола, стык «папа — мама» без зазора, без клея: "
            "папа — внутренняя половина стенки, торчит вверх из нижнего куска, мама — наружная "
            "половина стенки верхнего. Стенка при этом не тоньше 1,6 мм. "
            "Собранная труба может быть выше области печати. Нет — одна деталь, она должна влезть целиком."
        ),
        "hint.bundle": (
            "Вязанка: прямые вертикальные, модуль сверху, все нижние колени на цоколе, выход всегда в дне."
        ),
        "hint.straights": (
            "Авто — наименьшее нечётное число, что влезает; с дырками — удобное пальцам. Чётное нельзя: выход только в дне."
        ),
        "hint.radius": "Пусто — самый тесный разворот под диаметр и зазор.",
        "hint.trim": (
            "Корпус на верхнюю ноту. Трубка выдвигается вниз по строю и печатается отдельно. "
            "Ноль — без трубки. При слайдере поле гаснет само: слайдер уже меняет длину."
        ),
        "hint.holes": (
            "Ноль — без дырок. Открываются по очереди от выхода. Дырки только на прямых снаружи; "
            "нижние колени остаются на цоколе. Раскладка подбирается так, чтобы соседние дырки "
            "были на расстоянии пальцев: где можно, между ними ставится колено."
        ),
        "hint.scale": (
            "Тоника — нота корпуса, по которой считается длина. "
            "Дырки открываются по очереди от выхода, не хроматикой."
        ),
        "hint.slider": (
            "Верхняя нота — задвинутый конец, минимальная длина. "
            "Выдвижной конец: путь ≈ ход. U-колено: путь ≈ 2×ход на каждое колено. "
            "Двойное U — два колена, q = 4. U авто забирает все нижние колена укладки: "
            "больше прямых — больше сегментов царги и короче ход. "
            "Поле колен: пусто — из схемы; число — столько U, сколько влезет в прямые. "
            "Зазор — расстояние между каналом корпуса и царгой со всех сторон, "
            "не меньше 0,3 мм; пустое поле — 0,3. Совместно с отверстиями нельзя. "
            "Трубка подстройки при слайдере выключается сама. "
            "Цоколь царги такой же высокий, как у трубы. "
            "Печатается сложенный корпус; высота на полном ходу пишется в отчёт. "
            "Деталь слайдера должна влезть на стол целиком: стенка вставки 1 мм "
            "тоньше 1,6 мм, стык «папа — мама» на ней не сделать. Диапазон сама программа не укоротит. Схема «нет» — без слайдера."
        ),
        "hint.drone": (
            "«Нет» — один голос. Две отдельные мембраны: мелодия и дрон. Длина каждой "
            "трубы считается отдельно, печатаются они одной деталью с двумя каналами. "
            "Шаг осей входных труб 48 мм — под насадку на две мембраны, её программа "
            "не строит. Дрон без отверстий и слайдера мелодии, со своей короткой "
            "подстройкой. Пустая подстройка при заданной ноте дрона — один полутон вниз."
        ),
        "hint.delta_out": "Пустое поле открытого конца считает 0,6 радиуса канала.",
        "hint.speed": "Скорость звука 343 м/с — константа, её менять не нужно.",
        "choice.yes": "да",
        "choice.no": "нет",
        "choice.auto": "авто",
        "choice.drone_off": "нет",
        "scale.major": "мажор",
        "scale.natural_minor": "натуральный минор",
        "scale.melodic_minor": "минор мелодический",
        "scale.pentatonic": "пентатоника",
        "scale.major_pentatonic": "мажорная пентатоника",
        "slider.none": "нет",
        "slider.end": "выдвижной конец",
        "slider.u": "U-колено",
        "slider.uu": "двойное U",
        "slider.uauto": "U авто",
        "preview.empty": "Здесь появится модель",
        "preview.hint": "Левая кнопка — вращать, правая — сдвигать, колёсико — масштаб",
        "caption.tube_bore": "Канал трубы",
        "caption.seat_bore": "Канал конца",
        "caption.bore_empty": "{label}: —",
        "caption.bore_eaten": "{label}: стенка не оставляет отверстия",
        "caption.bore_value": "{label}: {mm} мм",
        "caption.clearance_empty": "Зазор пары: —",
        "caption.clearance_value": "Зазор пары: {mm} мм",
        "caption.seat_resolved": " (конец {mm} мм)",
        "error.expected_number": "ожидалось число.",
        "error.expected_integer": "ожидалось целое.",
        "error.launch": "Окно не открылось.",
        "error.form_incomplete": "Форма заполнена не до конца.",
        "error.pick_goal": "Выберите режим: нота или длина корпуса.",
        "error.layout_bundle_only": "Укладка только вязанка.",
        "error.outer": "Наружный диаметр трубы",
        "error.wall": "Толщина стенки",
        "error.seat_outer": "Наружный диаметр конца",
        "error.module_hole": "Отверстие модуля",
        "error.seat": "Длина посадки",
        "error.transition": "Длина переходника",
        "error.height": "Максимальная высота",
        "error.width": "Максимальная ширина",
        "error.depth": "Максимальная глубина",
        "error.reserve": "Резерв высоты под модуль",
        "error.radius": "Радиус разворота",
        "error.gap": "Зазор между трубами",
        "error.floor": "Дно под каналом",
        "error.trim": "Подстройка",
        "error.holes": "Число отверстий",
        "error.hole_diameter": "Диаметр отверстия",
        "error.slider": "Слайдер",
        "error.slider_pairs": "Колен слайдера",
        "error.slider_clearance": "Зазор слайдера",
        "error.drone_trim": "Подстройка дрона",
        "error.delta_head": "Поправка головки",
        "error.delta_bends": "Поправка изгибов",
        "error.a4": "Частота A4",
        "error.straights": "Число прямых",
        "error.delta_out": "Поправка открытого конца",
        "error.body_length": "Длина корпуса",
        "report.note_goal": "Нота {note}, {hz} Гц",
        "report.length_goal": (
            "Задан корпус {mm} мм. Прогноз: {note}, {hz} Гц, {cents} центов"
        ),
        "report.corrections": (
            "Поправки: головка {head} мм, открытый конец {out} мм, изгибы {bends} мм"
        ),
        "report.transition_extra": ", переходник {mm} мм",
        "report.straights": "Прямых: {count}, обычная {mm} мм",
        "report.straights_range": " (от {low} до {high} мм)",
        "report.outlet_bottom": "в дне",
        "report.outlet_top": "сверху",
        "report.turns": "Разворотов: {count}, радиус {mm} мм",
        "report.turns_tightened": (
            " (в окне {mm} мм, затянут, чтобы колена встали между дырками)"
        ),
        "report.layout": "Укладка: вязанка. Модуль сверху, выход {outlet}",
        "report.axis": "Ось {axis} мм, цоколь {base} мм",
        "report.envelope": (
            "Габарит {width} × {depth} мм, высота {height} мм, с резервом модуля {head} мм"
        ),
        "report.trim": (
            "Подстройка: {steps} полутонов вниз, {upper}…{lower}, "
            "ход {travel} мм, царга {tenon} мм"
        ),
        "report.slider": (
            "Слайдер: {kind}, {steps} полутонов вниз, {upper}…{lower}, "
            "q={q}, ΔL {delta} мм, ход {travel} мм, зазор {gap} мм со всех сторон, "
            "царга {tenon} мм"
        ),
        "report.slider_pairs": ", колен U {pairs}",
        "report.slider_height": (
            "На полном ходу высота {mm} мм (это игра, не область печати). "
            "Полутоны по ходу не равномерны:"
        ),
        "report.slider_stop": (
            "  {note}: {steps} пт, ΔL {delta} мм, ход {travel} мм"
        ),
        "report.splits_body": "корпус на {n} куска",
        "report.splits_slider": "слайдер на {n} куска",
        "report.splits": (
            "Разрезы на печать: {parts}, стыки «папа — мама» без зазора, без клея: "
            "папа внизу, смотрит вверх."
        ),
        "report.splits_fit": "Разрезы на печать включены, детали влезли на стол целиком.",
        "report.holes": "Отверстия: {count}, лад {scale}, тоника {tonic}",
        "report.closed": "все закрыты",
        "report.open_count": "открыто {n}",
        "report.fingering": (
            "  {note}: {hz} Гц, {cents} центов ({state})"
        ),
        "report.hole": (
            "  дырка {note}: s {s} мм, прямая {column}, Ø {diameter} мм"
        ),
        "report.fingers": (
            "  Пальцы: между соседними дырками от выхода {spacings} мм "
            "(удобно около {comfort}, между руками до {hands})"
        ),
        "report.wall": "Тончайшая стенка между каналами колен {mm} мм",
        "report.tube": "Труба: канал {bore} мм, снаружи {outer} мм",
        "report.tube_transition": (
            "{body}. Конец под модуль {seat} мм (канал {seat_bore} мм), "
            "переходник {transition} мм"
        ),
        "report.calibrated": "Головка калибрована",
        "report.uncalibrated": "Головка не калибрована",
        "report.pair.intro": "Второй голос: мелодия и дрон одной деталью на общем цоколе.",
        "report.pair.inlets": (
            "Шаг осей входов {spacing} мм, оба входа на высоте {height} мм "
            "(насадка на две мембраны не моделируется)."
        ),
        "report.pair.no_chamber": (
            "Камера подачи в генераторе не строится: каналы труб не соединены, "
            "общим воздухом их не связывает."
        ),
        "report.pair.gap": (
            "Зазор между трубами {gap} мм (оси не ближе {min_dist} мм)."
        ),
        "report.pair.envelope": (
            "Габарит пары {width} × {depth} мм, высота {height} мм"
        ),
        "report.pair.splits": (
            "Разрезы на печать: пара на {n} куска, стыки «папа — мама» без зазора, "
            "без клея: папа внизу, смотрит вверх."
        ),
        "report.pair.splits_fit": "Разрезы на печать включены, пара влезла на стол целиком.",
        "report.pair.melody": "Мелодия",
        "report.pair.drone": "Дрон",
        "report.effective": "Эффективная длина {mm} мм",
        "report.body": "Длина корпуса {mm} мм",
    },
    LANG_EN: {
        "app.title": "Bass tube generator",
        "app.subtitle": "Parametric model for 3D printing",
        "action.build": "Build",
        "action.save": "Save…",
        "dialog.save_title": "Where to save the tube. STL will be written next to it",
        "status.start": "Set the parameters and press Build.",
        "status.busy": "Calculating and building the model…",
        "status.ready": "Model is ready. You can orbit it and save.",
        "status.preview_fail": "Model is calculated, but the preview failed: {exc}",
        "status.build_first": "Build the model from the current fields first.",
        "status.saved": "Saved: {paths}",
        "status.fresh": "The model matches the fields. You can save it.",
        "status.stale": "Parameters changed. The preview is the previous model — build again.",
        "status.reject": "Fix the parameters and build again.",
        "lang.ru": "RU",
        "lang.en": "EN",
        "lang.switch": "Interface language",
        "group.goal": "Goal",
        "group.tube": "Tube",
        "group.joint": "Module seat",
        "group.envelope": "Build volume",
        "group.layout": "Layout",
        "group.holes": "Tone holes",
        "group.slider": "Slider",
        "group.drone": "Drone",
        "group.corrections": "Corrections",
        "group.reference": "Pitch standard",
        "goal.note": "Note",
        "goal.length": "Body length",
        "field.note": "Note",
        "field.body_length": "Body length, mm",
        "field.outer_diameter": "Outer diameter, mm",
        "field.wall": "Wall, mm",
        "field.seat_outer": "Seat outer diameter, mm",
        "field.module_hole": "Module hole, mm",
        "field.seat": "Seat length, mm",
        "field.transition": "Adapter, mm",
        "field.max_height": "Height, mm",
        "field.max_width": "Width, mm",
        "field.max_depth": "Depth, mm",
        "field.head_reserve": "Headroom for the module, mm",
        "field.print_splits": "Print splits",
        "field.straight_count": "Straights",
        "field.turn_radius": "Bend radius, mm",
        "field.gap": "Gap between tubes, mm",
        "field.floor": "Floor under the bore, mm",
        "field.trim": "Tuning slide, semitones down",
        "field.hole_count": "Count, up to 8",
        "field.scale": "Scale",
        "field.hole_diameter": "Hole diameter, mm",
        "field.slider_kind": "Scheme",
        "field.slider_semitones": "Semitones down",
        "field.slider_pairs": "U-bends",
        "field.slider_clearance": "Clearance around the tenon, mm",
        "field.drone_note": "Drone note",
        "field.drone_trim": "Drone slide, semitones down",
        "field.delta_head": "Head, mm",
        "field.delta_out": "Open end, mm",
        "field.delta_bends": "Bends, mm",
        "field.a4": "A4, Hz",
        "hint.diameter_master": (
            "Outer diameter is the master: wall, floor, bend radius and depth catch up "
            "when you leave the field, press Enter, or Build."
        ),
        "hint.joint": (
            "Empty seat follows the module hole with the stock clearance. A seat thicker "
            "than the hole is shrunk automatically. If the tube is thicker than the seat, "
            "a cone sits between them; empty adapter length means a 15° half-angle."
        ),
        "hint.splits": (
            "Yes — split the body and tenon into bed-sized pieces with a male–female joint, "
            "no gap, no glue: the male is the inner half of the wall, sticking up from the "
            "lower piece; the female is the outer half of the upper piece. The wall must be "
            "at least 1.6 mm. The assembled tube may be taller than the print volume. "
            "No — one solid, and it must fit the bed whole."
        ),
        "hint.bundle": (
            "Bundle: vertical straights, module on top, every lower knee on the base, outlet always in the floor."
        ),
        "hint.straights": (
            "Auto — the smallest odd count that fits; with holes, a fingering-friendly layout. Even counts are not allowed: the outlet is only in the floor."
        ),
        "hint.radius": "Empty — the tightest bend for the diameter and gap.",
        "hint.trim": (
            "The body is built for the upper note. The slide extends downward in pitch and is printed separately. "
            "Zero — no slide. With a slider this field turns itself off: the slider already changes length."
        ),
        "hint.holes": (
            "Zero — no holes. They open in order from the outlet. Holes sit only on outer straights; "
            "lower knees stay on the base. The layout is chosen so neighbouring holes sit at finger spacing: "
            "a knee is placed between them where that helps."
        ),
        "hint.scale": (
            "The tonic is the body note that sets the length. "
            "Holes open in order from the outlet, not as a chromatic set."
        ),
        "hint.slider": (
            "The upper note is the closed end, the shortest length. "
            "Sliding end: path ≈ travel. U-bend: path ≈ 2× travel per bend. "
            "Double U — two bends, q = 4. U auto takes every lower knee of the layout: "
            "more straights mean more tenon segments and shorter travel. "
            "Bend count: empty — from the scheme; a number — that many U-bends if the straights allow. "
            "Clearance is the gap between the body bore and the tenon on all sides, "
            "at least 0.3 mm; an empty field is 0.3. Cannot be combined with tone holes. "
            "The tuning slide turns itself off when a slider is on. "
            "The tenon base is as tall as the tube base. "
            "The folded body is printed; the height at full travel is written in the report. "
            "The slider part must fit the bed whole: the insert wall is 1 mm, thinner than 1.6 mm, "
            "so a male–female joint cannot be made on it. The program will not shorten the range. Scheme “none” — no slider."
        ),
        "hint.drone": (
            "“None” — a single voice. Two separate membranes: melody and drone. Each tube is "
            "calculated on its own pitch and they print as one part with two bores. "
            "Inlet axes are 48 mm apart — for a dual-membrane mouthpiece the program does not build. "
            "The drone has no melody holes or slider, and its own short tuning slide. "
            "An empty drone slide with a drone note set is one semitone down."
        ),
        "hint.delta_out": "An empty open-end field uses 0.6 of the bore radius.",
        "hint.speed": "The speed of sound is 343 m/s — a constant, no need to change it.",
        "choice.yes": "yes",
        "choice.no": "no",
        "choice.auto": "auto",
        "choice.drone_off": "none",
        "scale.major": "major",
        "scale.natural_minor": "natural minor",
        "scale.melodic_minor": "melodic minor",
        "scale.pentatonic": "pentatonic",
        "scale.major_pentatonic": "major pentatonic",
        "slider.none": "none",
        "slider.end": "sliding end",
        "slider.u": "U-bend",
        "slider.uu": "double U",
        "slider.uauto": "U auto",
        "preview.empty": "The model will appear here",
        "preview.hint": "Left button — orbit, right button — pan, wheel — zoom",
        "caption.tube_bore": "Tube bore",
        "caption.seat_bore": "Seat bore",
        "caption.bore_empty": "{label}: —",
        "caption.bore_eaten": "{label}: the wall leaves no opening",
        "caption.bore_value": "{label}: {mm} mm",
        "caption.clearance_empty": "Fit clearance: —",
        "caption.clearance_value": "Fit clearance: {mm} mm",
        "caption.seat_resolved": " (seat {mm} mm)",
        "error.expected_number": "a number was expected.",
        "error.expected_integer": "an integer was expected.",
        "error.launch": "The window did not open.",
        "error.form_incomplete": "The form is not filled in completely.",
        "error.pick_goal": "Choose a mode: note or body length.",
        "error.layout_bundle_only": "The only layout is the bundle.",
        "error.outer": "Tube outer diameter",
        "error.wall": "Wall thickness",
        "error.seat_outer": "Seat outer diameter",
        "error.module_hole": "Module hole",
        "error.seat": "Seat length",
        "error.transition": "Adapter length",
        "error.height": "Maximum height",
        "error.width": "Maximum width",
        "error.depth": "Maximum depth",
        "error.reserve": "Headroom for the module",
        "error.radius": "Bend radius",
        "error.gap": "Gap between tubes",
        "error.floor": "Floor under the bore",
        "error.trim": "Tuning slide",
        "error.holes": "Hole count",
        "error.hole_diameter": "Hole diameter",
        "error.slider": "Slider",
        "error.slider_pairs": "Slider bends",
        "error.slider_clearance": "Slider clearance",
        "error.drone_trim": "Drone slide",
        "error.delta_head": "Head correction",
        "error.delta_bends": "Bend correction",
        "error.a4": "A4 frequency",
        "error.straights": "Straight count",
        "error.delta_out": "Open-end correction",
        "error.body_length": "Body length",
        "report.note_goal": "Note {note}, {hz} Hz",
        "report.length_goal": (
            "Body set to {mm} mm. Prediction: {note}, {hz} Hz, {cents} cents"
        ),
        "report.corrections": (
            "Corrections: head {head} mm, open end {out} mm, bends {bends} mm"
        ),
        "report.transition_extra": ", adapter {mm} mm",
        "report.straights": "Straights: {count}, regular {mm} mm",
        "report.straights_range": " (from {low} to {high} mm)",
        "report.outlet_bottom": "in the floor",
        "report.outlet_top": "at the top",
        "report.turns": "Bends: {count}, radius {mm} mm",
        "report.turns_tightened": (
            " (in the form {mm} mm, tightened so the knees sit between the holes)"
        ),
        "report.layout": "Layout: bundle. Module on top, outlet {outlet}",
        "report.axis": "Axis {axis} mm, base {base} mm",
        "report.envelope": (
            "Envelope {width} × {depth} mm, height {height} mm, with module headroom {head} mm"
        ),
        "report.trim": (
            "Tuning slide: {steps} semitones down, {upper}…{lower}, "
            "travel {travel} mm, tenon {tenon} mm"
        ),
        "report.slider": (
            "Slider: {kind}, {steps} semitones down, {upper}…{lower}, "
            "q={q}, ΔL {delta} mm, travel {travel} mm, clearance {gap} mm on all sides, "
            "tenon {tenon} mm"
        ),
        "report.slider_pairs": ", U-bends {pairs}",
        "report.slider_height": (
            "Height at full travel {mm} mm (this is playing height, not the print volume). "
            "Semitones are not even along the travel:"
        ),
        "report.slider_stop": (
            "  {note}: {steps} st, ΔL {delta} mm, travel {travel} mm"
        ),
        "report.splits_body": "body into {n} pieces",
        "report.splits_slider": "slider into {n} pieces",
        "report.splits": (
            "Print splits: {parts}, male–female joints with no gap and no glue: "
            "the male is on the lower piece and points up."
        ),
        "report.splits_fit": "Print splits are on; the parts already fit the bed whole.",
        "report.holes": "Tone holes: {count}, scale {scale}, tonic {tonic}",
        "report.closed": "all closed",
        "report.open_count": "open {n}",
        "report.fingering": (
            "  {note}: {hz} Hz, {cents} cents ({state})"
        ),
        "report.hole": (
            "  hole {note}: s {s} mm, straight {column}, Ø {diameter} mm"
        ),
        "report.fingers": (
            "  Fingers: between neighbouring holes from the outlet {spacings} mm "
            "(comfortable around {comfort}, between hands up to {hands})"
        ),
        "report.wall": "Thinnest wall between neighbouring knee bores {mm} mm",
        "report.tube": "Tube: bore {bore} mm, outside {outer} mm",
        "report.tube_transition": (
            "{body}. Module seat {seat} mm (bore {seat_bore} mm), "
            "adapter {transition} mm"
        ),
        "report.calibrated": "Head is calibrated",
        "report.uncalibrated": "Head is not calibrated",
        "report.pair.intro": "Second voice: melody and drone as one part on a shared base.",
        "report.pair.inlets": (
            "Inlet axes {spacing} mm apart, both inlets at height {height} mm "
            "(the dual-membrane mouthpiece is not modelled)."
        ),
        "report.pair.no_chamber": (
            "The generator does not build a supply chamber: the tube bores are not joined "
            "and do not share air."
        ),
        "report.pair.gap": (
            "Gap between the tubes {gap} mm (axes no closer than {min_dist} mm)."
        ),
        "report.pair.envelope": (
            "Pair envelope {width} × {depth} mm, height {height} mm"
        ),
        "report.pair.splits": (
            "Print splits: pair into {n} pieces, male–female joints with no gap and no glue: "
            "the male is on the lower piece and points up."
        ),
        "report.pair.splits_fit": "Print splits are on; the pair already fits the bed whole.",
        "report.pair.melody": "Melody",
        "report.pair.drone": "Drone",
        "report.effective": "Effective length {mm} mm",
        "report.body": "Body length {mm} mm",
    },
}


def current_language() -> str:
    """Текущий язык подписей окна.

    Ничего не принимает. Возвращает «ru» или «en».
    """
    return _current


def t(key: str, lang: str | None = None) -> str:
    """Подпись по ключу.

    Принимает ключ каталога и необязательный код языка. Без языка берёт
    текущий. Если ключа нет, пробует русский, затем отдаёт сам ключ.
    Возвращает строку.
    """
    code = lang or _current
    table = STRINGS.get(code) or STRINGS[LANG_RU]
    if key in table:
        return table[key]
    return STRINGS[LANG_RU].get(key, key)


def set_current_language(lang: str) -> str:
    """Ставит язык процесса без записи на диск.

    Принимает «ru» или «en»; неизвестное считает русским. Возвращает
    код, который реально включился.
    """
    global _current
    _current = lang if lang in LANGS else LANG_RU
    return _current


def load_saved_language() -> str:
    """Читает язык, который пользователь выбрал в прошлый раз.

    Ничего не принимает. Нет файла, битый JSON или чужой код — русский.
    Возвращает «ru» или «en».
    """
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return LANG_RU
    if not isinstance(data, dict):
        return LANG_RU
    lang = data.get("lang")
    return lang if lang in LANGS else LANG_RU


def save_language(lang: str) -> None:
    """Запоминает язык окна в домашней папке.

    Принимает «ru» или «en». Чужой код не пишет. Ошибку диска глотает:
    окно и так переключилось. Ничего не возвращает.
    """
    if lang not in LANGS:
        return
    try:
        _CONFIG_PATH.write_text(
            json.dumps({"lang": lang}, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        return


def yes_no_choices(lang: str | None = None) -> tuple[str, str]:
    """Подписи «да/нет» для разрезов на печать.

    Принимает необязательный язык. Возвращает пару (да, нет) на этом языке.
    """
    return t("choice.yes", lang), t("choice.no", lang)


def scale_choice_label(scale_id: str, lang: str | None = None) -> str:
    """Подпись лада для списка окна.

    Принимает идентификатор лада и необязательный язык. Неизвестный
    идентификатор отдаёт как есть. Возвращает строку.
    """
    return t(f"scale.{scale_id}", lang) if f"scale.{scale_id}" in STRINGS[LANG_RU] else scale_id


def slider_choice_label(kind: str, lang: str | None = None) -> str:
    """Подпись схемы слайдера для списка окна.

    Принимает ключ схемы (пусто — нет слайдера) и необязательный язык.
    Возвращает строку.
    """
    key = "slider.none" if not kind else f"slider.{kind}"
    return t(key, lang)


def is_auto_word(text: str) -> bool:
    """Слово ли это «автоподбор» на любом языке окна.

    Принимает сырую строку поля. Русское «авто» и английское «auto»
    считаются одним. Возвращает True, если прямые надо подобрать.
    """
    return text.strip().casefold() in {"авто", "auto"}


def is_drone_off_word(text: str) -> bool:
    """Выключен ли дрон в поле ноты.

    Принимает сырую строку. Пустое, русское «нет» и английские none/no/off
    означают один голос. Возвращает True, если дрона нет.
    """
    return text.strip().casefold() in {"", "нет", "none", "no", "off"}


def is_slider_off_word(text: str) -> bool:
    """Выключен ли слайдер в поле схемы.

    Принимает сырую строку. Пустое, «нет» и английские none/no/off
    означают без слайдера. Возвращает True, если схемы нет.
    """
    return text.strip().casefold() in {"", "нет", "none", "no", "off"}
