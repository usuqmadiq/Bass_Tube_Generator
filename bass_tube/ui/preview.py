"""Предпросмотр детали: кадр VTK рисуется в картинку, мышь крутит камеру.

Отдельное окно VTK в tkinter на этой сборке не открывается, поэтому
кадр снимается вне экрана и показывается как изображение.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import numpy as np
import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
from PIL import Image, ImageTk
from vtkmodules.util.numpy_support import vtk_to_numpy
from vtkmodules.vtkRenderingCore import (
    vtkActor,
    vtkPolyDataMapper,
    vtkRenderer,
    vtkRenderWindow,
    vtkWindowToImageFilter,
)

from bass_tube.body.tube import TubeBody
from bass_tube.ui.i18n import t
from bass_tube.ui.theme import (
    PREVIEW_BG,
    PREVIEW_EMPTY_BG,
    PREVIEW_EMPTY_FG,
    PREVIEW_MODEL,
)


class PreviewScene:
    """Камера и сетка детали без окна на экране."""

    def __init__(self) -> None:
        """Готовит пустой кадр.

        Ничего не принимает. Создаёт внеэкранное окно VTK и светлый фон.
        Модель появится после show_shape.
        """
        self._renderer = vtkRenderer()
        self._renderer.SetBackground(*PREVIEW_BG)
        self._window = vtkRenderWindow()
        self._window.SetOffScreenRendering(1)
        self._window.AddRenderer(self._renderer)
        self._window.SetSize(640, 480)
        self._image_filter = vtkWindowToImageFilter()
        self._image_filter.SetInput(self._window)
        self._image_filter.SetInputBufferTypeToRGB()
        self._image_filter.ReadFrontBufferOff()
        self._actor: vtkActor | None = None

    def show_shape(self, shape) -> None:
        """Ставит солид в кадр и наводит камеру.

        Принимает фигуру CadQuery. Строит сетку, красит деталь и
        вписывает её в кадр видом сбоку сверху. Ничего не возвращает.
        """
        self._renderer.RemoveAllViewProps()
        poly = shape.toVtkPolyData(angularTolerance=0.25, normals=True)
        mapper = vtkPolyDataMapper()
        mapper.SetInputData(poly)
        mapper.SetScalarVisibility(False)
        actor = vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        prop.SetColor(*PREVIEW_MODEL)
        prop.SetAmbient(0.28)
        prop.SetDiffuse(0.72)
        prop.SetSpecular(0.28)
        prop.SetSpecularPower(36)
        self._renderer.AddActor(actor)
        self._actor = actor
        self._aim_camera()

    def _aim_camera(self) -> None:
        """Ставит камеру сбоку и чуть сверху, ось z — вверх экрана.

        Ничего не принимает. Стол детали (z = 0) оказывается внизу кадра,
        модуль сверху. Вписывает деталь в кадр. Ничего не возвращает.
        """
        camera = self._renderer.GetActiveCamera()
        camera.SetFocalPoint(0.0, 0.0, 0.0)
        camera.SetPosition(1.0, -1.3, 0.7)
        camera.SetViewUp(0.0, 0.0, 1.0)
        self._renderer.ResetCamera()
        self._renderer.ResetCameraClippingRange()

    def has_shape(self) -> bool:
        """Есть ли в кадре деталь.

        Ничего не принимает. Возвращает True после успешного show_shape.
        """
        return self._actor is not None

    def clear(self) -> None:
        """Убирает деталь из кадра.

        Ничего не принимает и не возвращает.
        """
        self._renderer.RemoveAllViewProps()
        self._actor = None

    def orbit(self, delta_x: float, delta_y: float) -> None:
        """Крутит камеру вокруг детали.

        Принимает сдвиг мыши в пикселях. Горизонталь меняет азимут,
        вертикаль — высоту. Ничего не возвращает.
        """
        camera = self._renderer.GetActiveCamera()
        camera.Azimuth(-delta_x * 0.4)
        camera.Elevation(-delta_y * 0.4)
        camera.OrthogonalizeViewUp()
        self._renderer.ResetCameraClippingRange()

    def pan(self, delta_x: float, delta_y: float) -> None:
        """Сдвигает камеру в плоскости экрана.

        Принимает сдвиг мыши в пикселях. Двигает и положение, и точку
        взгляда. Ничего не возвращает.
        """
        camera = self._renderer.GetActiveCamera()
        camera.OrthogonalizeViewUp()
        forward = np.array(camera.GetDirectionOfProjection(), dtype=float)
        up = np.array(camera.GetViewUp(), dtype=float)
        right = np.cross(forward, up)
        right_norm = np.linalg.norm(right)
        up_norm = np.linalg.norm(up)
        if right_norm == 0.0 or up_norm == 0.0:
            return
        right /= right_norm
        up /= up_norm
        shift = (-delta_x * right + delta_y * up) * camera.GetDistance() * 0.0015
        position = np.array(camera.GetPosition(), dtype=float) + shift
        focal = np.array(camera.GetFocalPoint(), dtype=float) + shift
        camera.SetPosition(*position)
        camera.SetFocalPoint(*focal)
        self._renderer.ResetCameraClippingRange()

    def zoom(self, steps: int) -> None:
        """Приближает или отдаляет камеру.

        Принимает число шагов колёсика. Положительное приближает.
        Ничего не возвращает.
        """
        if steps == 0:
            return
        camera = self._renderer.GetActiveCamera()
        factor = 1.1 ** steps
        camera.Dolly(factor)
        self._renderer.ResetCameraClippingRange()

    def image(self, width: int, height: int) -> Image.Image:
        """Снимает кадр в картинку.

        Принимает ширину и высоту в пикселях. Рисует вне экрана.
        Возвращает RGB-изображение. Нулевой размер заменяет на 2×2.
        """
        self._window.SetSize(max(int(width), 2), max(int(height), 2))
        self._window.Render()
        self._image_filter.Modified()
        self._image_filter.Update()
        return _vtk_image_to_pil(self._image_filter.GetOutput())


class ModelPreview(ttk.Frame):
    """Область предпросмотра: картинка детали и мышь."""

    def __init__(self, master: tk.Misc) -> None:
        """Создаёт пустую область.

        Принимает родителя tkinter. Пока модели нет, показывает подсказку.
        Мышь начнёт крутить кадр после show.
        """
        super().__init__(master, style="Surface.TFrame")
        self.scene = PreviewScene()
        self._photo: ImageTk.PhotoImage | None = None
        self._press_x = 0
        self._press_y = 0
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.view = tk.Label(
            self,
            text=t("preview.empty"),
            bg=PREVIEW_EMPTY_BG,
            fg=PREVIEW_EMPTY_FG,
            font=("Segoe UI", 12),
        )
        self.view.grid(row=0, column=0, sticky="nsew")
        self.hint = ttk.Label(self, text=t("preview.hint"), style="PreviewHint.TLabel")
        self.hint.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.view.bind("<Configure>", self._on_resize)
        self.view.bind("<ButtonPress-1>", self._press)
        self.view.bind("<B1-Motion>", self._drag_orbit)
        self.view.bind("<ButtonPress-3>", self._press)
        self.view.bind("<B3-Motion>", self._drag_pan)
        self.view.bind("<MouseWheel>", self._wheel)

    def show(self, body: TubeBody) -> None:
        """Показывает построенную деталь корпуса.

        Принимает TubeBody. Заменяет прошлую сетку и рисует кадр
        по текущему размеру области. Ничего не возвращает.
        """
        self.show_shape(body.solid.val())

    def show_shape(self, shape) -> None:
        """Показывает произвольный солид CadQuery.

        Принимает фигуру (корпус или корпус вместе с трубкой подстройки).
        Заменяет прошлую сетку и рисует кадр. Ничего не возвращает.
        """
        self.scene.show_shape(shape)
        self.view.configure(text="")
        self._redraw()

    def clear(self) -> None:
        """Убирает модель и возвращает подсказку.

        Ничего не принимает и не возвращает.
        """
        self.scene.clear()
        self._photo = None
        self.view.configure(image="", text=t("preview.empty"))

    def apply_language(self) -> None:
        """Обновляет пустую подсказку и жест мыши под текущий язык.

        Ничего не принимает. Если модель на экране, текст кадра не трогает.
        Ничего не возвращает.
        """
        self.hint.configure(text=t("preview.hint"))
        if not self.scene.has_shape():
            self.view.configure(text=t("preview.empty"))

    def has_model(self) -> bool:
        """Показана ли сейчас деталь.

        Ничего не принимает. Возвращает True, если сетка в кадре есть.
        """
        return self.scene.has_shape()

    def _press(self, event: tk.Event) -> None:
        """Запоминает точку, откуда пошёл жест мыши.

        Принимает событие tkinter. Ничего не возвращает.
        """
        self._press_x = event.x
        self._press_y = event.y

    def _drag_orbit(self, event: tk.Event) -> None:
        """Вращает модель левой кнопкой.

        Принимает событие движения. Считает сдвиг от прошлого положения
        и перерисовывает кадр. Ничего не возвращает.
        """
        if not self.scene.has_shape():
            return
        self.scene.orbit(event.x - self._press_x, event.y - self._press_y)
        self._press_x = event.x
        self._press_y = event.y
        self._redraw()

    def _drag_pan(self, event: tk.Event) -> None:
        """Сдвигает модель правой кнопкой.

        Принимает событие движения. Считает сдвиг и перерисовывает кадр.
        Ничего не возвращает.
        """
        if not self.scene.has_shape():
            return
        self.scene.pan(event.x - self._press_x, event.y - self._press_y)
        self._press_x = event.x
        self._press_y = event.y
        self._redraw()

    def _wheel(self, event: tk.Event) -> None:
        """Масштабирует модель колёсиком.

        Принимает событие. На Windows шаг сидит в delta.
        Перерисовывает кадр. Ничего не возвращает.
        """
        if not self.scene.has_shape():
            return
        steps = 1 if event.delta > 0 else -1
        self.scene.zoom(steps)
        self._redraw()

    def _on_resize(self, _event: tk.Event) -> None:
        """Переснимает кадр, когда область изменила размер.

        Принимает событие Configure. Пока модели нет, ничего не делает.
        Ничего не возвращает.
        """
        if self.scene.has_shape():
            self._redraw()

    def _redraw(self) -> None:
        """Кладёт свежий кадр в подпись.

        Ничего не принимает. Берёт размер подписи, снимает картинку
        и держит ссылку на PhotoImage, иначе tkinter её сотрёт.
        Ничего не возвращает.
        """
        width = self.view.winfo_width()
        height = self.view.winfo_height()
        if width < 2 or height < 2:
            width, height = 640, 480
        image = self.scene.image(width, height)
        self._photo = ImageTk.PhotoImage(image)
        self.view.configure(image=self._photo, text="")


def _vtk_image_to_pil(vtk_image) -> Image.Image:
    """Переводит кадр VTK в картинку Pillow.

    Принимает vtkImageData после съёмки окна. Строки VTK идут снизу вверх,
    поэтому кадр переворачивается. Возвращает RGB-изображение.
    """
    width, height, _components = vtk_image.GetDimensions()
    raw = vtk_to_numpy(vtk_image.GetPointData().GetScalars())
    channels = raw.shape[-1] if raw.ndim > 1 else 1
    frame = np.flipud(raw.reshape(height, width, channels))
    if channels > 3:
        frame = frame[:, :, :3]
    return Image.fromarray(np.ascontiguousarray(frame), mode="RGB")
