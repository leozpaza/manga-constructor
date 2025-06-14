#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - основной canvas и система панелей
Ядро программы для создания и редактирования панелей манги
"""

import tkinter as tk
import copy
from tkinter import ttk, Canvas, messagebox, simpledialog
import math
from enum import Enum
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass, field
import uuid
from PIL import Image, ImageTk, ImageDraw 
import os # если еще нет


class PanelType(Enum):
    """Типы панелей манги"""
    RECTANGULAR = "rectangular"
    ROUND = "round" 
    SPLASH = "splash"  # Панель на всю страницу
    SPEECH_BUBBLE = "speech_bubble"
    THOUGHT_BUBBLE = "thought_bubble"
    IRREGULAR = "irregular"  # Неправильная форма


class Tool(Enum):
    """Инструменты редактирования"""
    SELECT = "select"
    PANEL = "panel"
    TEXT = "text"
    SPEECH = "speech"


@dataclass
class PanelStyle:
    """Стиль панели"""
    border_width: int = 2
    border_color: str = "#000000"
    fill_color: str = "#FFFFFF"
    corner_radius: int = 0
    shadow: bool = False
    shadow_offset: Tuple[int, int] = (2, 2)
    shadow_color: str = "#888888"


@dataclass
class Panel:
    """Базовый класс панели манги"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    x: float = 0
    y: float = 0
    width: float = 100
    height: float = 100
    panel_type: PanelType = PanelType.RECTANGULAR
    style: PanelStyle = field(default_factory=PanelStyle)
    rotation: float = 0
    layer: int = 0
    visible: bool = True
    locked: bool = False
    content_image: Optional[str] = None  # Путь к изображению
    content_text: str = ""
    selected: bool = False

    tail_dx: float = 10.0   # смещение конца хвоста от центра
    tail_dy: float = 20.0

    tail_root_offset: float = 0.0

    # Угол положения основания хвоста относительно центра овала (радианы).
    # pi/2 соответствует нижней точке, т.е. хвост снизу по умолчанию.
    tail_root_angle: float = math.pi / 2
    
    # Для неправильных форм - список точек
    custom_points: List[Tuple[float, float]] = field(default_factory=list)

    # НОВЫЕ ПОЛЯ ДЛЯ КАДРИРОВАНИЯ ИЗОБРАЖЕНИЯ ВНУТРИ ПАНЕЛИ:
    # Смещение изображения (в единицах страницы) относительно левого верхнего угла панели.
    # Отрицательные значения означают, что часть изображения "выходит" за пределы панели влево/вверх.
    image_offset_x: float = 0.0
    image_offset_y: float = 0.0
    # Масштаб изображения внутри панели. 1.0 = изображение заполнило панель по одной из сторон при первоначальной вставке.
    image_scale: float = 1.0
    # Временный флаг для отметки, что оригинальное изображение было изменено (для пере-кэширования PIL)
    _image_content_updated_flag: bool = False # Используется для инвалидации кэша PIL.Image
    
    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Получить границы панели (x1, y1, x2, y2)"""
        return (self.x, self.y, self.x + self.width, self.y + self.height)
        
    def contains_point(self, px: float, py: float) -> bool:
        """Проверить, содержит ли панель точку"""
        x1, y1, x2, y2 = self.get_bounds()
        return x1 <= px <= x2 and y1 <= py <= y2
        
    def move(self, dx: float, dy: float):
        """Переместить панель"""
        self.x += dx
        self.y += dy
        
    def resize(self, new_width: float, new_height: float):
        """Изменить размер панели"""
        self.width = max(10, new_width)  # Минимальный размер
        self.height = max(10, new_height)

    def reset_image_transform(self):
        """Сбрасывает трансформации изображения к значениям по умолчанию."""
        self.image_offset_x = 0.0
        self.image_offset_y = 0.0
        self.image_scale = 1.0
        self._image_content_updated_flag = True # Помечаем для обновления кэша

    def mark_visuals_for_update(self): # Новый метод
        self._image_content_updated_flag = True


class SelectionHandle:
    """Маркер выделения для изменения размера"""
    SIZE = 8
    
    def __init__(self, x: float, y: float, cursor: str, handle_type: str):
        # ИСПРАВЛЕНО: сохраняем экранные координаты
        self.screen_x = x  
        self.screen_y = y
        self.cursor = cursor
        self.handle_type = handle_type
        
    def contains_point(self, px: float, py: float) -> bool:
        """Проверить, содержит ли маркер точку (экранные координаты)"""
        half_size = self.SIZE // 2
        return (self.screen_x - half_size <= px <= self.screen_x + half_size and 
                self.screen_y - half_size <= py <= self.screen_y + half_size)


class PageConstructor:
    """Главный класс конструктора страниц манги"""
    
    def __init__(self, parent_frame: ttk.Frame, app_instance):
        self.parent = parent_frame
        self.app = app_instance

        self.image_tk_cache: Dict[str, ImageTk.PhotoImage] = {} 
        # Кэш для PIL.Image, чтобы не грузить с диска постоянно
        # Ключ - panel.id. Значение - словарь {'path': str, 'image': PIL.Image, 'original_size': (w,h)}
        # original_size - это размер ИСХОДНОГО файла изображения, до обработки ImageManager'ом
        self.pil_image_cache: Dict[str, Dict[str, Any]] = {}

        self.creation_panel_type: Optional[PanelType] = None
        self.tail_move_panel: Optional[Panel] = None
        self.tail_root_move_panel: Optional[Panel] = None
        self.tail_root_drag_end_x: float = 0.0
        self.tail_root_drag_end_y: float = 0.0
        
        # Настройки страницы
        self.page_width = 595
        self.page_height = 842
        self.margin = 20
        
        # Состояние
        self.current_tool = Tool.SELECT
        self.zoom = 1.0
        self.grid_size = 50
        self.show_grid = False
        self.show_guides = False
        self.snap_to_grid = False

        self.temp_panel_rect_coords = None
        
        # Панели и выделение
        self.panels: List[Panel] = []
        self.selected_panels: List[Panel] = []
        self.selection_handles: List[SelectionHandle] = []

        self.panel_drag_initial_states: Dict[str, Tuple[float, float]] = {}
        self.page_drag_start_coords: Tuple[float, float] = (0, 0)
        
        # Состояние мыши
        self.mouse_start_x = 0
        self.mouse_start_y = 0
        self.drag_start_x = 0  # Экранные координаты начала перетаскивания
        self.drag_start_y = 0
        self.dragging = False
        self.drag_mode = None  # "move", "resize", "create", "pan_image"
        self.resize_handle = None

        # НОВОЕ СОСТОЯНИЕ для режима редактирования изображения в панели
        self.image_editing_panel: Optional[Panel] = None
        self.image_pan_start_offset_x: float = 0.0
        self.image_pan_start_offset_y: float = 0.0
        self.image_pan_mouse_start_page_x: float = 0.0 # Координаты мыши в единицах страницы
        self.image_pan_mouse_start_page_y: float = 0.0

        # История изменений
        self.MAX_HISTORY_SIZE = 50  # Максимальное количество шагов в истории
        self.undo_stack: List[List[Panel]] = []
        self.redo_stack: List[List[Panel]] = []

        self.save_history_state()
        
        self.setup_ui()
        self.bind_events()

    def _normalize_layers(self):
        """Пере-нумеровывает слои так, чтобы у каждой панели был свой уникальный
        слой, а порядок сверху-вниз сохранялся."""
        # сортируем сначала по layer, потом по порядку появления
        ordered = sorted(self.panels, key=lambda p: p.layer)
        for new_layer, p in enumerate(ordered):
            p.layer = new_layer

    def clear_panel_image_cache(self, panel_id: str):
        if panel_id in self.image_tk_cache:
            del self.image_tk_cache[panel_id]
        if panel_id in self.pil_image_cache:
            del self.pil_image_cache[panel_id]
        
    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        # Главный контейнер
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Создание canvas с прокруткой
        self.canvas_frame = ttk.Frame(main_frame)
        self.canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas
        self.canvas = Canvas(self.canvas_frame, bg="#F0F0F0", highlightthickness=0)
        
        # Полосы прокрутки
        v_scroll = ttk.Scrollbar(self.canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        h_scroll = ttk.Scrollbar(self.canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        # Размещение элементов
        self.canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        self.canvas_frame.grid_rowconfigure(0, weight=1)
        self.canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Настройка области прокрутки
        self.update_scroll_region()

        self.center_canvas_view()

    def set_page_dimensions(self, width: int, height: int):
        self.page_width = width
        self.page_height = height
        self.update_scroll_region()
        # Возможно, потребуется пересчитать позиции/размеры панелей, если они были в %
        # или если нужно адаптировать существующий макет.
        # Пока просто перерисовываем.
        if hasattr(self.app, 'zoom_fit'): # Если приложение уже полностью инициализировано
            self.app.zoom_fit() # Подгоняем масштаб под новый размер
        else:
            self.redraw()
        
    def bind_events(self):
        """Привязка событий к холсту и контекстному меню"""
        self.canvas.bind("<Button-1>",        self.on_mouse_down)
        self.canvas.bind("<B1-Motion>",       self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>",          self.on_mouse_move)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

        self.canvas.bind("<Configure>", self.on_canvas_configure)

        # Контекстное меню
        self.canvas.bind("<Button-3>", self.show_context_menu)

        # Клавиатурные действия над панелями
        self.canvas.bind("<Delete>",    self.delete_selected)
        self.canvas.bind("<Control-c>", self.copy_selected)
        self.canvas.bind("<Control-v>", self.paste_panels)
        self.canvas.bind("<Control-a>", self.select_all)

        # Новые бинды для отмены/возврата прямо на холсте
        self.canvas.bind("<Control-z>", lambda e: (self.app.undo(), "break"))
        self.canvas.bind("<Control-y>", lambda e: (self.app.redo(), "break"))

        # Масштабирование колёсиком
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)   # Windows / macOS
        self.canvas.bind("<Button-4>",   self.on_mouse_wheel)   # Linux (вверх)
        self.canvas.bind("<Button-5>",   self.on_mouse_wheel)   # Linux (вниз)

        # Делаем холст приоритетным для клавиатуры
        self.canvas.focus_set()

    def on_canvas_configure(self, event):
            """Обработка изменения размеров холста."""
            self.update_scroll_region()
            self.center_canvas_view()
            self.redraw()

    def on_mouse_wheel(self, event):
        """Обработка колеса мыши для масштабирования."""
        # Определяем направление прокрутки
        if event.num == 5 or event.delta < 0:  # Прокрутка вниз
            zoom_direction = "out"
        elif event.num == 4 or event.delta > 0:  # Прокрутка вверх
            zoom_direction = "in"
        else:
            return

        # Проверяем модификаторы
        ctrl_pressed = bool(event.state & 0x0004)
        
        if self.image_editing_panel and self.image_editing_panel.content_image:
            # В режиме редактирования изображения
            if ctrl_pressed:
                # Ctrl + колесо = масштаб холста
                if zoom_direction == "out":
                    self.app.zoom_out()
                else:
                    self.app.zoom_in()
            else:
                # Простое колесо = масштаб изображения в панели
                panel = self.image_editing_panel
                
                if zoom_direction == "out":
                    scale_factor = 1 / 1.1
                else:
                    scale_factor = 1.1

                old_scale = panel.image_scale
                new_scale = max(0.1, min(10.0, old_scale * scale_factor))

                if abs(new_scale - old_scale) < 0.001:
                    return

                # Координаты курсора мыши относительно страницы
                mouse_page_x, mouse_page_y = self.screen_to_page(event.x, event.y)

                # Координаты курсора мыши относительно левого верхнего угла панели
                mouse_in_panel_x = mouse_page_x - panel.x
                mouse_in_panel_y = mouse_page_y - panel.y
                
                # Корректируем смещение для зума относительно курсора
                panel.image_offset_x = mouse_in_panel_x - (mouse_in_panel_x - panel.image_offset_x) * (new_scale / old_scale)
                panel.image_offset_y = mouse_in_panel_y - (mouse_in_panel_y - panel.image_offset_y) * (new_scale / old_scale)
                
                panel.image_scale = new_scale
                panel.mark_visuals_for_update()

                self.redraw()
                self.app.set_status(f"Масштаб изображения: {panel.image_scale:.2f}x")
        else:
            # Не в режиме редактирования изображения = масштаб холста
            if zoom_direction == "out":
                self.app.zoom_out()
            else:
                self.app.zoom_in()
        
    def set_tool(self, tool_name: str):
        """Установка активного инструмента"""
        self.current_tool = Tool(tool_name)
        self.clear_selection()
        self.redraw()
        
        # Обновление курсора
        cursors = {
            Tool.SELECT: "arrow",
            Tool.PANEL: "crosshair",
            Tool.TEXT: "xterm",
            Tool.SPEECH: "crosshair"
        }
        self.canvas.configure(cursor=cursors.get(self.current_tool, "arrow"))
        
    def set_zoom(self, zoom_level: float):
        """Установка масштаба"""
        new_zoom = max(0.01, min(10.0, zoom_level)) # Минимальный зум > 0, максимальный увеличен

        # Проверяем, действительно ли зум изменился, чтобы избежать лишних перерисовок
        if abs(self.zoom - new_zoom) > 0.001: # Допуск на погрешность float
            self.zoom = new_zoom
            self.update_scroll_region() # Важно обновить scrollregion после изменения зума
            self.redraw()
        elif self.zoom <= 0.01 and zoom_level > 0.01 : # Если пытаемся выйти из минимального зума
            self.zoom = new_zoom
            self.update_scroll_region()
            self.redraw()
        
    def zoom_to_fit(self):
        """Масштабирование по размеру окна и центрирование страницы."""
        # Обновляем размеры Canvas, чтобы точно узнать его width/height
        self.canvas.update_idletasks()

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Если Canvas ещё не «встроился» в окно (размеры слишком малы), пробуем позже
        if canvas_width <= 1 or canvas_height <= 1:
            self.canvas.after(100, self.zoom_to_fit)  # повторить попытку через 100ms
            return

        # Ширина/высота контента (страницы + поля)
        page_content_width_units = self.page_width + 2 * self.margin
        page_content_height_units = self.page_height + 2 * self.margin

        if page_content_width_units <= 0 or page_content_height_units <= 0:
            return  # нечего масштабировать

        # Вычисляем новый зум так, чтобы вся страница вместе с полями поместилась в Canvas
        zoom_x = canvas_width  / max(1, page_content_width_units)
        zoom_y = canvas_height / max(1, page_content_height_units)
        # Уменьшаем чуть-чуть (0.95), чтобы оставить «воздух» по краям
        new_zoom = min(zoom_x, zoom_y) * 0.95
        new_zoom = max(0.01, new_zoom)  # ограничение снизу

        # Устанавливаем новый зум (сам метод set_zoom внутри обновит scrollregion и сделает redraw)
        self.set_zoom(new_zoom)

        # Обновляем возможные виджеты-индикаторы уровня зума (если они есть в вашем интерфейсе)
        if hasattr(self.app, 'zoom_level') and self.app.zoom_level:
            self.app.zoom_level.set(new_zoom)
        if hasattr(self.app, 'zoom_label') and self.app.zoom_label:
            self.app.zoom_label.config(text=f"{int(new_zoom * 100)}%")

        # Вместо ручного расчёта scrollregion → xview/yview, просто центрируем вид
        self.center_canvas_view()
            
    def screen_to_page(self, screen_x: float, screen_y: float) -> Tuple[float, float]:
        """Преобразование экранных координат в координаты страницы"""
        canvas_x = self.canvas.canvasx(screen_x)
        canvas_y = self.canvas.canvasy(screen_y)
        
        page_x = (canvas_x - self.margin) / self.zoom
        page_y = (canvas_y - self.margin) / self.zoom
        
        return page_x, page_y
        
    def page_to_screen(self, page_x: float, page_y: float) -> Tuple[float, float]:
        """Преобразование координат страницы в экранные"""
        canvas_x = page_x * self.zoom + self.margin
        canvas_y = page_y * self.zoom + self.margin
        
        return canvas_x, canvas_y
        
    def snap_to_grid_coords(self, x: float, y: float) -> Tuple[float, float]:
        """Привязка координат к сетке"""
        if self.snap_to_grid and self.grid_size > 0:
            x = round(x / self.grid_size) * self.grid_size
            y = round(y / self.grid_size) * self.grid_size
        return x, y
        
    def update_scroll_region(self):
        """Обновляет область прокрутки и «пустые поля» вокруг страницы."""
        self.canvas.update_idletasks()               # узнаём реальный size холста

        zoom = max(0.01, self.zoom)
        content_w = (self.page_width  + 2 * self.margin) * zoom
        content_h = (self.page_height + 2 * self.margin) * zoom

        canvas_w = max(self.canvas.winfo_width(),  1)
        canvas_h = max(self.canvas.winfo_height(), 1)

        # Сколько не хватает до размеров окна → добавим симметричные поля
        pad_x = max(0, (canvas_w - content_w) / 2)
        pad_y = max(0, (canvas_h - content_h) / 2)

        # scrollregion может начинаться с отрицательных координат – это нормально
        self.canvas.configure(
            scrollregion=(-pad_x, -pad_y,
                        content_w + pad_x,
                        content_h + pad_y)
        )

    def center_canvas_view(self):
        """Сдвигает вид таким образом, чтобы страница была по центру Canvas."""
        self.canvas.update_idletasks()
        x0, y0, x1, y1 = map(float, self.canvas.cget("scrollregion").split())
        sr_w, sr_h = x1 - x0, y1 - y0
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()

        fx = 0 if sr_w <= cw else (sr_w - cw) / 2 / sr_w
        fy = 0 if sr_h <= ch else (sr_h - ch) / 2 / sr_h

        self.canvas.xview_moveto(fx)
        self.canvas.yview_moveto(fy)
        
    def clear_page(self):
        """Очистка страницы"""
        self.panels.clear()
        self.selected_panels.clear()
        self.selection_handles.clear()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.save_history_state()
        self.image_editing_panel = None # Сброс режима редактирования
        self.pil_image_cache.clear()    # Очистка кэша PIL изображений
        self.image_tk_cache.clear()   # Очистка кэша PhotoImage
        self.redraw()
        
    def redraw(self):
        """Перерисовка всего canvas"""
        self.canvas.delete("all")

        # фон страницы
        self.draw_page_background()

        # сетка
        if self.show_grid:
            self.draw_grid()

        # направляющие
        if self.show_guides:
            self.draw_guides()

        # панели (по слоям)
        for panel in sorted(self.panels, key=lambda p: p.layer):
            if panel.visible:
                self.draw_panel(panel)

        # выделение
        self.draw_selection()

        # временный прямоугольник при создании новой панели
        if (self.dragging and
            self.drag_mode == "create" and
            self.temp_panel_rect_coords and
            len(self.temp_panel_rect_coords) == 4):
            sx1, sy1, sx2, sy2 = self.temp_panel_rect_coords
            if sx2 > sx1 and sy2 > sy1:
                self.canvas.create_rectangle(
                    sx1, sy1, sx2, sy2,
                    fill="",
                    outline="#4CAF50",
                    width=2,
                    dash=(5, 5),
                    tags="temp_panel"
                )
        
    def draw_page_background(self):
        """Рисование фона страницы"""
        x1, y1 = self.page_to_screen(0, 0)
        x2, y2 = self.page_to_screen(self.page_width, self.page_height)
        
        # Тень страницы
        shadow_offset = 4
        self.canvas.create_rectangle(
            x1 + shadow_offset, y1 + shadow_offset, 
            x2 + shadow_offset, y2 + shadow_offset,
            fill="#CCCCCC", outline="", tags="page_shadow"
        )
        
        # Страница
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            fill="white", outline="#888888", width=1, tags="page"
        )
        
        # Поля страницы
        margin = 20
        mx1, my1 = self.page_to_screen(margin, margin)
        mx2, my2 = self.page_to_screen(self.page_width - margin, self.page_height - margin)
        
        self.canvas.create_rectangle(
            mx1, my1, mx2, my2,
            fill="", outline="#DDDDDD", width=1, dash=(2, 2), tags="page_margin"
        )
        
    def draw_grid(self):
        """Рисование сетки"""
        if self.grid_size <= 0:
            return
            
        # Границы видимой области
        x1, y1 = self.screen_to_page(0, 0)
        x2, y2 = self.screen_to_page(self.canvas.winfo_width(), self.canvas.winfo_height())
        
        # Ограничение сетки областью страницы
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(self.page_width, x2)
        y2 = min(self.page_height, y2)
        
        # Вертикальные линии
        start_x = int(x1 / self.grid_size) * self.grid_size
        for x in range(int(start_x), int(x2) + self.grid_size, self.grid_size):
            sx1, sy1 = self.page_to_screen(x, y1)
            sx2, sy2 = self.page_to_screen(x, y2)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#E0E0E0", tags="grid")
            
        # Горизонтальные линии
        start_y = int(y1 / self.grid_size) * self.grid_size
        for y in range(int(start_y), int(y2) + self.grid_size, self.grid_size):
            sx1, sy1 = self.page_to_screen(x1, y)
            sx2, sy2 = self.page_to_screen(x2, y)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#E0E0E0", tags="grid")
            
    def draw_guides(self):
        """Рисование направляющих"""
        # Центральные линии
        center_x = self.page_width / 2
        center_y = self.page_height / 2
        
        # Вертикальная центральная линия
        sx1, sy1 = self.page_to_screen(center_x, 0)
        sx2, sy2 = self.page_to_screen(center_x, self.page_height)
        self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#FFB6C1", width=1, dash=(5, 5), tags="guides")
        
        # Горизонтальная центральная линия
        sx1, sy1 = self.page_to_screen(0, center_y)
        sx2, sy2 = self.page_to_screen(self.page_width, center_y)
        self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#FFB6C1", width=1, dash=(5, 5), tags="guides")
        
        # Правило третей
        third_x1 = self.page_width / 3
        third_x2 = self.page_width * 2 / 3
        third_y1 = self.page_height / 3
        third_y2 = self.page_height * 2 / 3
        
        for x in [third_x1, third_x2]:
            sx1, sy1 = self.page_to_screen(x, 0)
            sx2, sy2 = self.page_to_screen(x, self.page_height)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#DDA0DD", width=1, dash=(3, 7), tags="guides")
            
        for y in [third_y1, third_y2]:
            sx1, sy1 = self.page_to_screen(0, y)
            sx2, sy2 = self.page_to_screen(self.page_width, y)
            self.canvas.create_line(sx1, sy1, sx2, sy2, fill="#DDA0DD", width=1, dash=(3, 7), tags="guides")
            
    def draw_panel(self, panel: Panel):
        """Рисование панели"""
        if panel.panel_type == PanelType.RECTANGULAR:
            self.draw_rectangular_panel(panel)
        elif panel.panel_type == PanelType.ROUND:
            self.draw_round_panel(panel)
        elif panel.panel_type == PanelType.SPEECH_BUBBLE:
            self.draw_speech_bubble(panel)
        elif panel.panel_type == PanelType.THOUGHT_BUBBLE:
            self.draw_thought_bubble(panel)
        elif panel.panel_type == PanelType.SPLASH:
            self.draw_splash_panel(panel)
            
    def draw_rectangular_panel(self, panel: Panel):
        x1_s, y1_s = self.page_to_screen(panel.x, panel.y)
        x2_s, y2_s = self.page_to_screen(panel.x + panel.width, panel.y + panel.height)
        
        panel_screen_width = int(x2_s - x1_s)
        panel_screen_height = int(y2_s - y1_s)

        if panel_screen_width <= 0 or panel_screen_height <= 0: return

        if panel.style.shadow:
            shadow_offset_x = panel.style.shadow_offset[0] # Тень не зависит от self.zoom, она в экранных пикселях
            shadow_offset_y = panel.style.shadow_offset[1]
            self.canvas.create_rectangle(
                x1_s + shadow_offset_x, y1_s + shadow_offset_y, 
                x2_s + shadow_offset_x, y2_s + shadow_offset_y,
                fill=panel.style.shadow_color, outline="", tags=f"panel_{panel.id}_shadow"
            )
            
        self.canvas.create_rectangle(
            x1_s, y1_s, x2_s, y2_s,
            fill=panel.style.fill_color,
            outline="", 
            tags=f"panel_{panel.id}_bg"
        )

        if panel.content_image and os.path.exists(panel.content_image):
            # КЛЮЧ КЭША УЧИТЫВАЕТ ЭКРАННЫЕ РАЗМЕРЫ ПАНЕЛИ
            cache_key = (
                f"{panel.id}_rect_{os.path.basename(panel.content_image)}_"
                f"scr({panel_screen_width}x{panel_screen_height})_"
                f"off({panel.image_offset_x:.2f},{panel.image_offset_y:.2f})_"
                f"scale({panel.image_scale:.2f})"
            )
            
            if panel._image_content_updated_flag:
                # Если контент/кадрирование изменилось, удаляем ВСЕ PhotoImage, связанные с этим panel.id,
                # так как старые размеры/параметры могут быть другими.
                self.clear_specific_image_tk_cache(panel.id) 
                panel._image_content_updated_flag = False

            tk_image = self.image_tk_cache.get(cache_key)

            if tk_image is None:
                pil_img_source_data = self.pil_image_cache.get(panel.id)
                pil_img_source = None

                if pil_img_source_data and pil_img_source_data['path'] == panel.content_image:
                    pil_img_source = pil_img_source_data['image']
                else: 
                    try:
                        loaded_pil_img = Image.open(panel.content_image)
                        self.pil_image_cache[panel.id] = {
                            'path': panel.content_image, 
                            'image': loaded_pil_img.copy(),
                        }
                        pil_img_source = loaded_pil_img
                        self.clear_specific_image_tk_cache(panel.id) 
                    except Exception as e:
                        print(f"Error loading PIL image for panel {panel.id} from {panel.content_image}: {e}")
                
                if pil_img_source:
                    try:
                        # Размеры изображения С УЧЕТОМ panel.image_scale, в экранных пикселях
                        # pil_img_source.width/height - это пиксели файла, соответствующего panel.width/height (в ед.стр.) при его создании
                        # Умножаем на image_scale, чтобы получить "виртуальный" размер отмасштабированного изображения.
                        # Затем умножаем на self.zoom, чтобы получить экранные пиксели для этого вирт. размера.
                        img_to_render_width = int(pil_img_source.width * panel.image_scale * self.zoom)
                        img_to_render_height = int(pil_img_source.height * panel.image_scale * self.zoom)
                        
                        if img_to_render_width <=0 or img_to_render_height <=0:
                            # print(f"Skipping tk image for {panel.id}, zero/neg render dim")
                            pass # Пропустить создание tk_image если размеры некорректны
                        else:
                            pil_img_rendered_content = pil_img_source.resize(
                                (img_to_render_width, img_to_render_height),
                                Image.Resampling.LANCZOS
                            )

                            final_image_on_screen = Image.new(
                                'RGBA', 
                                (panel_screen_width, panel_screen_height), 
                                (0,0,0,0) 
                            )
                            
                            if panel.style.fill_color and panel.style.fill_color.lower() != "transparent":
                                fill_img = Image.new('RGBA', (panel_screen_width, panel_screen_height), panel.style.fill_color)
                                final_image_on_screen.paste(fill_img, (0,0))

                            paste_offset_x_on_screen = int(panel.image_offset_x * self.zoom)
                            paste_offset_y_on_screen = int(panel.image_offset_y * self.zoom)
                            
                            final_image_on_screen.paste(pil_img_rendered_content, (paste_offset_x_on_screen, paste_offset_y_on_screen))
                            
                            tk_image = ImageTk.PhotoImage(final_image_on_screen)
                            self.image_tk_cache[cache_key] = tk_image
                    except Exception as e:
                        print(f"Error processing/creating ImageTk for panel {panel.id} with key {cache_key}: {e}")
            
            if tk_image: # tk_image может быть None если размеры были некорректны
                self.canvas.create_image(x1_s, y1_s, image=tk_image, anchor=tk.NW, tags=(f"panel_{panel.id}", f"panel_{panel.id}_image"))

        outline_color = "#FF6B6B" if panel.selected else panel.style.border_color
        if self.image_editing_panel == panel:
            outline_color = "#00A0FF" 
            
        outline_width = panel.style.border_width * self.zoom 
        outline_width = max(1, int(outline_width)) if panel.style.border_width > 0 else 0
        
        if outline_width > 0 :
            self.canvas.create_rectangle(
                x1_s, y1_s, x2_s, y2_s,
                fill="", 
                outline=outline_color,
                width=outline_width,
                tags=f"panel_{panel.id}_border"
            )
        
        if panel.content_text:
            self.draw_panel_text(panel)

    def edit_panel_text(self, panel: Panel):
        """Открытие диалога для редактирования текста панели."""
        if panel.locked:
            self.app.set_status(f"Панель {panel.id[:8]} заблокирована.")
            return

        current_text = panel.content_text
        # Используем simpledialog для простоты. В будущем можно заменить на более продвинутый редактор.
        new_text = simpledialog.askstring(
            "Редактировать текст",
            f"Введите текст для панели (ID: {panel.id[:8]}):",
            initialvalue=current_text,
            parent=self.canvas  # Важно для корректного отображения диалога
        )

        if new_text is not None:  # Если пользователь не нажал "Отмена"
            if panel.content_text != new_text:
                panel.content_text = new_text
                self.save_history_state()
                self.redraw()
                self.app.project_modified = True
                self.app.update_title()
                self.app.set_status(f"Текст панели {panel.id[:8]} обновлен.")

    def clicked_canvas_item_has_tag(self, x: float, y: float,
                                    tag_suffix: str) -> tuple[bool, str | None]:
        """
        Проверяет, содержит ли ближайший Canvas-элемент под (x, y)
        тег вида  «panel_<id>…{tag_suffix}».
        Возвращает (True/False, panel_id | None).
        """
        cx, cy = self.canvas.canvasx(x), self.canvas.canvasy(y)
        item = self.canvas.find_closest(cx, cy)
        if not item:
            return False, None

        for tag in self.canvas.gettags(item[0]):
            if tag.endswith(tag_suffix) and tag.startswith("panel_"):
                parts = tag.split("_")
                if len(parts) >= 3:
                    return True, parts[1]          # panel_id
        return False, None
            
    def draw_round_panel(self, panel: Panel):
        x1_s, y1_s = self.page_to_screen(panel.x, panel.y)
        x2_s, y2_s = self.page_to_screen(panel.x + panel.width, panel.y + panel.height)

        panel_screen_width = int(x2_s - x1_s)
        panel_screen_height = int(y2_s - y1_s)

        if panel_screen_width <= 0 or panel_screen_height <= 0: return
        
        if panel.content_image and os.path.exists(panel.content_image):
            # КЛЮЧ КЭША УЧИТЫВАЕТ ЭКРАННЫЕ РАЗМЕРЫ ПАНЕЛИ
            cache_key = (
                f"{panel.id}_round_{os.path.basename(panel.content_image)}_"
                f"scr({panel_screen_width}x{panel_screen_height})_"
                f"off({panel.image_offset_x:.2f},{panel.image_offset_y:.2f})_"
                f"scale({panel.image_scale:.2f})"
            )

            if panel._image_content_updated_flag:
                self.clear_specific_image_tk_cache(panel.id)
                panel._image_content_updated_flag = False

            tk_image = self.image_tk_cache.get(cache_key)

            if tk_image is None:
                pil_img_source_data = self.pil_image_cache.get(panel.id)
                pil_img_source = None
                if pil_img_source_data and pil_img_source_data['path'] == panel.content_image:
                    pil_img_source = pil_img_source_data['image']
                else:
                    try:
                        loaded_pil_img = Image.open(panel.content_image)
                        self.pil_image_cache[panel.id] = {'path': panel.content_image, 'image': loaded_pil_img.copy()}
                        pil_img_source = loaded_pil_img
                        self.clear_specific_image_tk_cache(panel.id)
                    except Exception as e:
                        print(f"Error loading PIL for round panel {panel.id}: {e}")

                if pil_img_source:
                    try:
                        img_to_render_width = int(pil_img_source.width * panel.image_scale * self.zoom)
                        img_to_render_height = int(pil_img_source.height * panel.image_scale * self.zoom)

                        if img_to_render_width > 0 and img_to_render_height > 0:
                            pil_img_rendered_content = pil_img_source.resize(
                                (img_to_render_width, img_to_render_height), Image.Resampling.LANCZOS
                            )

                            final_image_on_screen = Image.new('RGBA', (panel_screen_width, panel_screen_height), (0,0,0,0)) 
                            
                            if panel.style.fill_color and panel.style.fill_color.lower() != "transparent":
                                fill_img = Image.new('RGBA', (panel_screen_width, panel_screen_height), panel.style.fill_color)
                                # Сначала фон, потом контент, потом маска
                                final_image_on_screen.paste(fill_img,(0,0)) 

                            paste_offset_x_on_screen = int(panel.image_offset_x * self.zoom)
                            paste_offset_y_on_screen = int(panel.image_offset_y * self.zoom)
                            
                            # Создаем временный слой для контента, чтобы применить его под маску поверх фона
                            content_layer_for_masking = Image.new('RGBA', (panel_screen_width, panel_screen_height), (0,0,0,0))
                            content_layer_for_masking.paste(pil_img_rendered_content, (paste_offset_x_on_screen, paste_offset_y_on_screen))
                            
                            # Комбинируем фон (если есть) с контентом
                            final_image_on_screen.alpha_composite(content_layer_for_masking)

                            mask = Image.new('L', (panel_screen_width, panel_screen_height), 0)
                            draw_mask = ImageDraw.Draw(mask)
                            draw_mask.ellipse((0, 0, panel_screen_width, panel_screen_height), fill=255)
                            
                            final_image_on_screen.putalpha(mask)

                            tk_image = ImageTk.PhotoImage(final_image_on_screen)
                            self.image_tk_cache[cache_key] = tk_image
                        # else: print(f"Skipping tk image for {panel.id}, zero/neg render dim for round")
                    except Exception as e:
                        print(f"Error processing/creating masked ImageTk for round panel {panel.id} with key {cache_key}: {e}")
            
            if tk_image:
                self.canvas.create_image(x1_s, y1_s, image=tk_image, anchor=tk.NW, tags=(f"panel_{panel.id}", f"panel_{panel.id}_image"))
        elif panel.style.fill_color and panel.style.fill_color.lower() != "transparent":
            self.canvas.create_oval(
                x1_s, y1_s, x2_s, y2_s,
                fill=panel.style.fill_color,
                outline="", 
                tags=f"panel_{panel.id}_bg"
            )

        outline_color = "#FF6B6B" if panel.selected else panel.style.border_color
        if self.image_editing_panel == panel:
            outline_color = "#00A0FF"
            
        outline_width = panel.style.border_width * self.zoom
        outline_width = max(1, int(outline_width)) if panel.style.border_width > 0 else 0

        if outline_width > 0:
            self.canvas.create_oval(
                x1_s, y1_s, x2_s, y2_s,
                fill="", 
                outline=outline_color,
                width=outline_width,
                tags=f"panel_{panel.id}_border"
            )
        
        if panel.content_text:
            self.draw_panel_text(panel)
        
    def draw_speech_bubble(self, panel: Panel):
        """Отрисовка речевого пузыря (овал + хвост + draggable-хэндл)."""
        # 1) основной овал
        self.draw_round_panel(panel)

        # 2) точка крепления хвоста
        center_x = panel.x + panel.width / 2
        center_y = panel.y + panel.height / 2

        root_angle = getattr(panel, 'tail_root_angle', math.pi / 2)
        root_page_x = center_x + (panel.width / 2) * math.cos(root_angle)
        root_page_y = center_y + (panel.height / 2) * math.sin(root_angle)

        root_x, root_y = self.page_to_screen(root_page_x, root_page_y)

        # 2. кончик хвоста (учитываем dx/dy в единицах страницы)
        end_page_x = root_page_x + panel.tail_dx
        end_page_y = root_page_y + panel.tail_dy
        end_x, end_y = self.page_to_screen(end_page_x, end_page_y)

        # 4) стиль
        outline = "#FF6B6B" if panel.selected else panel.style.border_color
        bw      = max(1, int(panel.style.border_width * self.zoom))

        # 5) треугольник-хвост с ориентацией по касательной к овалу
        tang_dx = -math.sin(root_angle) * panel.width
        tang_dy =  math.cos(root_angle) * panel.height
        norm = math.hypot(tang_dx, tang_dy)
        if norm == 0:
            tang_dx, tang_dy = 1, 0
        else:
            tang_dx /= norm
            tang_dy /= norm

        base = 5 * self.zoom
        x1 = root_x + tang_dx * base
        y1 = root_y + tang_dy * base
        x2 = root_x - tang_dx * base
        y2 = root_y - tang_dy * base

        self.canvas.create_polygon(
            x1, y1, x2, y2, end_x, end_y,
            fill=panel.style.fill_color,
            outline=outline,
            width=bw,
            tags=(f"panel_{panel.id}_tail", f"panel_{panel.id}_handle")
        )

        # 6) круг-хэндлы
        r = max(4, 6 * self.zoom)
        self.canvas.create_oval(
            end_x - r, end_y - r, end_x + r, end_y + r,
            fill=outline, outline="",
            tags=(f"panel_{panel.id}_tail_handle", f"panel_{panel.id}_handle")
        )

        self.canvas.create_oval(
            root_x - r, root_y - r, root_x + r, root_y + r,
            fill=outline, outline="",
            tags=(f"panel_{panel.id}_tail_root_handle", f"panel_{panel.id}_handle")
        )

        # 7) текст (если есть)
        if panel.content_text:
            self.draw_panel_text(panel)
        
    def draw_thought_bubble(self, panel: Panel):
        """Рисование пузыря мыслей"""
        self.draw_round_panel(panel)
        
        # Маленькие пузырьки для мыслей
        x1, y1 = self.page_to_screen(panel.x, panel.y)
        x2, y2 = self.page_to_screen(panel.x + panel.width, panel.y + panel.height)
        
        outline_color = "#FF6B6B" if panel.selected else panel.style.border_color
        
        # Маленькие пузырьки
        bubble_x = (x1 + x2) / 2
        bubble_y = y2 + 10
        
        for i, size in enumerate([6, 4, 2]):
            by = bubble_y + i * 8
            self.canvas.create_oval(
                bubble_x - size, by - size,
                bubble_x + size, by + size,
                fill=panel.style.fill_color,
                outline=outline_color,
                width=1,
                tags=f"panel_{panel.id}_thought_{i}"
            )
            
    def draw_splash_panel(self, panel: Panel):
        """Рисование панели на всю страницу"""
        # Специальные эффекты для splash панели
        self.draw_rectangular_panel(panel)
        
        # Дополнительные эффекты (звёздочки, линии скорости и т.д.)
        x1, y1 = self.page_to_screen(panel.x, panel.y)
        x2, y2 = self.page_to_screen(panel.x + panel.width, panel.y + panel.height)
        
        # Линии воздействия от углов
        outline_color = "#FF6B6B" if panel.selected else "#FFD700"
        for corner_x, corner_y in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            for i in range(3):
                length = 20 + i * 10
                angle = math.radians(45 + i * 15)
                end_x = corner_x + math.cos(angle) * length
                end_y = corner_y + math.sin(angle) * length
                
                self.canvas.create_line(
                    corner_x, corner_y, end_x, end_y,
                    fill=outline_color, width=2,
                    tags=f"panel_{panel.id}_effect"
                )
                
    def draw_panel_text(self, panel: Panel):
        """Рисование текста в панели"""
        if not panel.content_text:
            return
            
        # Центр панели
        center_x = panel.x + panel.width / 2
        center_y = panel.y + panel.height / 2
        
        text_x, text_y = self.page_to_screen(center_x, center_y)
        
        self.canvas.create_text(
            text_x, text_y,
            text=panel.content_text,
            font=("Arial", int(12 * self.zoom)),
            anchor="center",
            tags=f"panel_{panel.id}_text"
        )
        
    def draw_selection(self):
        """Рисование выделения и маркеров изменения размера"""
        self.selection_handles.clear()
        
        for panel in self.selected_panels:
            # Рамка выделения
            x1, y1 = self.page_to_screen(panel.x, panel.y)
            x2, y2 = self.page_to_screen(panel.x + panel.width, panel.y + panel.height)
            
            self.canvas.create_rectangle(
                x1 - 1, y1 - 1, x2 + 1, y2 + 1,
                fill="", outline="#FF6B6B", width=2, dash=(4, 4),
                tags="selection"
            )
            
            # Маркеры изменения размера - ИСПРАВЛЕНО: сохраняем экранные координаты
            handles = [
                ("nw", x1, y1, "top_left_corner"),
                ("n", (x1 + x2) / 2, y1, "top_side"),
                ("ne", x2, y1, "top_right_corner"),
                ("e", x2, (y1 + y2) / 2, "right_side"),
                ("se", x2, y2, "bottom_right_corner"),
                ("s", (x1 + x2) / 2, y2, "bottom_side"),
                ("sw", x1, y2, "bottom_left_corner"),
                ("w", x1, (y1 + y2) / 2, "left_side")
            ]
            
            for handle_type, hx, hy, cursor in handles:
                # ИСПРАВЛЕНО: сохраняем экранные координаты как есть
                handle = SelectionHandle(hx, hy, cursor, handle_type)
                self.selection_handles.append(handle)
                
                # Рисование маркера
                half_size = SelectionHandle.SIZE // 2
                self.canvas.create_rectangle(
                    hx - half_size, hy - half_size,
                    hx + half_size, hy + half_size,
                    fill="white", outline="#FF6B6B", width=2,
                    tags="selection_handle"
                )
                
    # События мыши
    def on_mouse_down(self, event):
        """Обработка нажатия ЛКМ."""
        self.canvas.focus_set()

        # координаты старта (экран + страница)
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        page_x_down, page_y_down = self.screen_to_page(event.x, event.y)

        self.temp_panel_rect_coords = None          # служебное
        self.creation_panel_type   = None           # какой тип будет создаваться
        self.tail_move_panel       = None           # панель-владелец хвоста

        # ───── 0. pan_image ────────────────────────────────────────────────
        if self.image_editing_panel:
            p = self.image_editing_panel
            if p.contains_point(page_x_down, page_y_down):
                self.drag_mode                    = "pan_image"
                self.image_pan_mouse_start_page_x = page_x_down
                self.image_pan_mouse_start_page_y = page_y_down
                self.image_pan_start_offset_x     = p.image_offset_x
                self.image_pan_start_offset_y     = p.image_offset_y
                self.dragging = True
                return
            # кликнули вне редактируемой панели → закрываем режим
            self.save_history_state()
            self.app.project_modified = True
            self.app.update_title()
            self.image_editing_panel = None
            self.canvas.config(cursor="arrow")

        # ───── 1. SELECT ──────────────────────────────────────────────────
        if self.current_tool == Tool.SELECT:
            # 1-a. хвост речевого пузыря?
            hit, pid = self.clicked_canvas_item_has_tag(event.x, event.y, "_tail_handle")
            if hit and pid:
                self.tail_move_panel = next((p for p in self.panels if p.id == pid), None)
                if self.tail_move_panel:
                    self.drag_mode = "move_tail"
                    self.dragging  = True
                    return

            hit, pid = self.clicked_canvas_item_has_tag(event.x, event.y, "_tail_root_handle")
            if hit and pid:
                self.tail_root_move_panel = next((p for p in self.panels if p.id == pid), None)
                if self.tail_root_move_panel:
                    self.drag_mode = "move_tail_root"
                    self.dragging  = True
                    angle = getattr(self.tail_root_move_panel, 'tail_root_angle', math.pi / 2)
                    cx = self.tail_root_move_panel.x + self.tail_root_move_panel.width / 2
                    cy = self.tail_root_move_panel.y + self.tail_root_move_panel.height / 2
                    rx = cx + (self.tail_root_move_panel.width / 2) * math.cos(angle)
                    ry = cy + (self.tail_root_move_panel.height / 2) * math.sin(angle)
                    self.tail_root_drag_end_x = rx + self.tail_root_move_panel.tail_dx
                    self.tail_root_drag_end_y = ry + self.tail_root_move_panel.tail_dy
                    return

            # 1-b. resize-handle?
            if self.selected_panels:
                cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
                for handle in self.selection_handles:
                    if handle.contains_point(cx, cy):
                        self.drag_mode    = "resize"
                        self.resize_handle = handle
                        self.dragging     = True
                        return

            # 1-c. обычный выбор / перемещение
            clicked_panel = self.find_panel_at_point(page_x_down, page_y_down)
            if clicked_panel:
                if clicked_panel not in self.selected_panels:
                    if not (event.state & 4):          # Ctrl
                        self.clear_selection()
                    self.select_panel(clicked_panel)
                if clicked_panel in self.selected_panels:
                    self.drag_mode = "move"
                    self.dragging  = True
                    self.panel_drag_initial_states = {
                        p.id: (p.x, p.y, p.width, p.height) for p in self.selected_panels
                    }
                    self.page_drag_start_coords = (page_x_down, page_y_down)
            else:
                if not (event.state & 4):
                    self.clear_selection()
                self.drag_mode = "select_area"
                self.dragging  = True

        # ───── 2. PANEL ───────────────────────────────────────────────────
        elif self.current_tool == Tool.PANEL:
            self.drag_mode              = "create"
            self.dragging               = True
            self.creation_panel_type    = PanelType.RECTANGULAR
            self.temp_panel_rect_coords = (event.x, event.y, event.x, event.y)

        # ───── 3. SPEECH ──────────────────────────────────────────────────
        elif self.current_tool == Tool.SPEECH:
            self.drag_mode              = "create"       # drag-to-create!
            self.dragging               = True
            self.creation_panel_type    = PanelType.SPEECH_BUBBLE
            self.temp_panel_rect_coords = (event.x, event.y, event.x, event.y)

        # ───── 4. TEXT ────────────────────────────────────────────────────
        elif self.current_tool == Tool.TEXT:
            clicked_panel_for_text = self.find_panel_at_point(page_x_down, page_y_down)
            if clicked_panel_for_text:
                self.edit_panel_text(clicked_panel_for_text)
            else:
                self.app.set_status("Кликните на панель для редактирования текста.")

        # ───── 5. Автопереключение / очистка выделения ───────────────────
        if (self.current_tool != Tool.SELECT and
            not self.dragging and
            not self.find_panel_at_point(page_x_down, page_y_down) and
            not self.image_editing_panel):
            self.set_tool('select')
            if hasattr(self.app, 'tool_buttons'):
                for tid, btn in self.app.tool_buttons.items():
                    btn.configure(relief=tk.SUNKEN if tid == 'select' else tk.RAISED)
            self.app.set_status("Автоматически переключен на инструмент выбора")

        if (self.current_tool != Tool.SELECT and
            not self.find_panel_at_point(page_x_down, page_y_down) and
            not (event.state & 4)):
            self.clear_selection()

        self.redraw()
        
    def on_mouse_drag(self, event):
        """Перетаскивание мыши с зажатой кнопкой."""
        if not self.dragging:
            return

        current_page_x, current_page_y = self.screen_to_page(event.x, event.y)

        # 3-a. перетягиваем хвост речевого пузыря
        if self.drag_mode == "move_tail" and self.tail_move_panel:
            p = self.tail_move_panel
            root_angle = getattr(p, 'tail_root_angle', math.pi / 2)
            cx = p.x + p.width / 2
            cy = p.y + p.height / 2
            root_px = cx + (p.width / 2) * math.cos(root_angle)
            root_py = cy + (p.height / 2) * math.sin(root_angle)
            cur_page_x, cur_page_y = self.screen_to_page(event.x, event.y)
            p.tail_dx = cur_page_x - root_px
            p.tail_dy = cur_page_y - root_py
            p.mark_visuals_for_update()
            self.redraw()
            return

        if self.drag_mode == "move_tail_root" and self.tail_root_move_panel:
            p = self.tail_root_move_panel
            cur_page_x, cur_page_y = self.screen_to_page(event.x, event.y)
            cx = p.x + p.width / 2
            cy = p.y + p.height / 2
            angle = math.atan2((cur_page_y - cy) * p.width,
                               (cur_page_x - cx) * p.height)
            p.tail_root_angle = angle
            root_px = cx + (p.width / 2) * math.cos(angle)
            root_py = cy + (p.height / 2) * math.sin(angle)
            p.tail_dx = self.tail_root_drag_end_x - root_px
            p.tail_dy = self.tail_root_drag_end_y - root_py
            p.mark_visuals_for_update()
            self.redraw()
            return

        # 3-b. панорамирование изображения
        if self.drag_mode == "pan_image" and self.image_editing_panel:
            p  = self.image_editing_panel
            dx = current_page_x - self.image_pan_mouse_start_page_x
            dy = current_page_y - self.image_pan_mouse_start_page_y
            p.image_offset_x = self.image_pan_start_offset_x + dx
            p.image_offset_y = self.image_pan_start_offset_y + dy
            p.mark_visuals_for_update()

        # 3-c. перемещение панелей
        elif self.drag_mode == "move":
            dx = current_page_x - self.page_drag_start_coords[0]
            dy = current_page_y - self.page_drag_start_coords[1]
            for p in self.selected_panels:
                if p.id in self.panel_drag_initial_states:
                    ix, iy, pw, ph = self.panel_drag_initial_states[p.id]
                    nx = max(0, min(self.page_width  - pw, ix + dx))
                    ny = max(0, min(self.page_height - ph, iy + dy))
                    nx, ny = self.snap_to_grid_coords(nx, ny)
                    p.x, p.y = nx, ny

        # 3-d. resize
        elif self.drag_mode == "resize" and self.resize_handle and self.selected_panels:
            panel = self.selected_panels[0]
            self.resize_panel_with_handle(panel, self.resize_handle,
                                        current_page_x, current_page_y)
            panel._image_content_updated_flag = True

        # 3-e. создание новой панели
        elif self.drag_mode == "create":
            sx, sy = self.screen_to_page(self.drag_start_x, self.drag_start_y)
            sx, sy = self.snap_to_grid_coords(sx, sy)
            cx, cy = self.snap_to_grid_coords(current_page_x, current_page_y)
            x1_s, y1_s = self.page_to_screen(min(sx, cx), min(sy, cy))
            x2_s, y2_s = self.page_to_screen(max(sx, cx), max(sy, cy))
            self.temp_panel_rect_coords = (x1_s, y1_s, x2_s, y2_s)

        self.redraw()
        
    def on_mouse_up(self, event):
        """Отпускание ЛКМ."""
        # 4-0. Клик без drag в режиме редактирования изображения
        if not self.dragging:
            if self.image_editing_panel:
                px, py = self.screen_to_page(event.x, event.y)
                if not self.image_editing_panel.contains_point(px, py):
                    self.save_history_state()
                    self.app.project_modified = True
                    self.app.update_title()
                    self.image_editing_panel = None
                    self.canvas.config(cursor="arrow")
                    self.redraw()
            return

        # координаты финала
        cur_x, cur_y = self.screen_to_page(event.x, event.y)
        start_px, start_py = self.screen_to_page(self.drag_start_x, self.drag_start_y)

        # 4-1. закончили таскать хвост
        if self.drag_mode == "move_tail":
            self.save_history_state()
            self.app.project_modified = True
            self.app.update_title()
            self.tail_move_panel = None
            self.dragging = False
            self.drag_mode = None
            self.redraw()
            return

        if self.drag_mode == "move_tail_root":
            self.save_history_state()
            self.app.project_modified = True
            self.app.update_title()
            self.tail_root_move_panel = None
            self.dragging = False
            self.drag_mode = None
            self.redraw()
            return

        # 4-2. закончили создание новой панели
        if self.drag_mode == "create":
            spx, spy = self.snap_to_grid_coords(start_px, start_py)
            cpx, cpy = self.snap_to_grid_coords(cur_x, cur_y)

            x1, y1 = min(spx, cpx), min(spy, cpy)
            x2, y2 = max(spx, cpx), max(spy, cpy)
            w, h = x2 - x1, y2 - y1

            if w >= 10 and h >= 10:
                ptype = self.creation_panel_type or PanelType.RECTANGULAR
                new_panel = self.create_panel(x1, y1, w, h, ptype)
                if ptype == PanelType.SPEECH_BUBBLE:
                    new_panel.content_text = "Текст"
                self.app.project_modified = True
                self.app.update_title()
            self.creation_panel_type = None

        # 4-3. move / resize / pan_image
        elif self.drag_mode in ("move", "resize", "pan_image"):
            self.save_history_state()
            self.app.project_modified = True
            self.app.update_title()

        # 4-4. финальная очистка
        self.temp_panel_rect_coords = None
        self.dragging = False
        if not self.image_editing_panel:
            self.drag_mode = None
        self.resize_handle = None
        self.panel_drag_initial_states.clear()
        self.tail_move_panel = None
        self.tail_root_move_panel = None

        self.redraw()
        
    def on_mouse_move(self, event):
        """Обработка движения мыши (для курсора)"""
        page_x, page_y = self.screen_to_page(event.x, event.y)
        
        # Обновление координат в статусной строке
        if hasattr(self.app, 'coords_label'):
            self.app.coords_label.config(text=f"X: {int(page_x)}, Y: {int(page_y)}")
            
        # ИСПРАВЛЕНО: изменение курсора над маркерами
        cursor = "arrow"
        if self.selected_panels:
            # ИСПРАВЛЕНИЕ: Преобразуем координаты события в координаты canvas
            canvas_event_x = self.canvas.canvasx(event.x)
            canvas_event_y = self.canvas.canvasy(event.y)
            
            for handle in self.selection_handles:
                if handle.contains_point(canvas_event_x, canvas_event_y):
                    cursor = handle.cursor
                    break
                    
        # Fallback для неподдерживаемых курсоров
        try:
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            self.canvas.configure(cursor="arrow")
                    
        pass
        
    def on_double_click(self, event):
        """Обработка двойного клика."""
        page_x, page_y = self.screen_to_page(event.x, event.y)
        panel = self.find_panel_at_point(page_x, page_y)
        
        if panel:
            if panel.content_image:
                # Вход/выход из режима редактирования изображения
                if self.image_editing_panel == panel:
                    self.image_editing_panel = None
                    self.canvas.config(cursor="arrow")
                    self.app.set_status("Режим выбора активен.")
                    self.save_history_state() # Сохраняем изменения кадрирования
                    self.app.project_modified = True
                    self.app.update_title()
                else:
                    self.clear_selection() # Снимаем выделение с других панелей
                    self.select_panel(panel) # Выделяем эту панель
                    self.image_editing_panel = panel
                    self.canvas.config(cursor="fleur") # Курсор для перемещения
                    self.app.set_status(f"Редактирование изображения в панели {panel.id[:8]}. Двигайте мышью, масштабируйте колесом. Двойной клик для выхода.")
                self.redraw()
            else:
                # Если нет изображения, открываем свойства панели или редактор текста
                self.edit_panel_text(panel) # или self.edit_panel_properties(panel)
            
    def show_context_menu(self, event):
        """Показать контекстное меню."""
        context_menu = tk.Menu(self.canvas, tearoff=0)
        
        page_x, page_y = self.screen_to_page(event.x, event.y)
        panel_under_mouse = self.find_panel_at_point(page_x, page_y)

        if self.image_editing_panel: # Если в режиме редактирования изображения
            context_menu.add_command(label="Сбросить кадрирование", 
                                     command=lambda p=self.image_editing_panel: (
                                         p.reset_image_transform(), 
                                         self.clear_specific_image_tk_cache(p.id), # Очистить кэш PhotoImage
                                         self.redraw(),
                                         self.save_history_state(),
                                         self.app.set_status("Кадрирование сброшено.")
                                     ))
            context_menu.add_command(label="Завершить редактирование изображения", 
                                     command=lambda: (
                                         setattr(self, 'image_editing_panel', None), 
                                         self.canvas.config(cursor="arrow"),
                                         self.save_history_state(),
                                         self.redraw(),
                                         self.app.set_status("Режим выбора активен.")
                                     ))
        elif panel_under_mouse:
            if panel_under_mouse not in self.selected_panels:
                self.clear_selection()
                self.select_panel(panel_under_mouse)
                self.redraw() # Чтобы выделение отобразилось до меню

            context_menu.add_command(label="Добавить/Изменить изображение...", 
                                     command=lambda p=panel_under_mouse: self.handle_panel_image_action(p))
            if panel_under_mouse.content_image:
                context_menu.add_command(label="Редактировать кадрирование", 
                                         command=lambda p=panel_under_mouse: self.enter_image_editing_mode(p))
                context_menu.add_command(label="Удалить изображение из панели",
                                         command=lambda p=panel_under_mouse: self.remove_image_from_panel(p))

            context_menu.add_command(label="Редактировать текст", command=lambda p=panel_under_mouse: self.edit_panel_text(p))
            context_menu.add_separator()
            context_menu.add_command(label="Свойства панели...", command=lambda p=panel_under_mouse: self.edit_panel_properties(p))
            context_menu.add_command(label="Дублировать", command=lambda: self.app.copy_panel() if self.selected_panels else None) # Копируем выделенные
            context_menu.add_separator()
            context_menu.add_command(label="На передний план", command=lambda p=panel_under_mouse: self.bring_to_front(p))
            context_menu.add_command(label="На задний план", command=lambda p=panel_under_mouse: self.send_to_back(p))
            context_menu.add_separator()
            context_menu.add_command(label="Удалить панель", command=lambda: self.app.delete_panel()) # Удаляем выделенные
        else: # Клик на пустом месте
            context_menu.add_command(label="Вставить", command=self.app.paste_panel)
            context_menu.add_command(label="Выделить все", command=self.app.select_all)
            
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def handle_panel_image_action(self, panel: Panel):
        if panel.locked:
            self.app.set_status(f"Панель {panel.id[:8]} заблокирована."); return

        if not panel.content_image:
            from tkinter import filedialog
            file = filedialog.askopenfilename(
                title="Выберите изображение",
                filetypes=[("Изображения", "*.png *.jpg *.jpeg *.bmp *.gif")]
            )
            if file:
                img_id = self.app.image_manager.library.add_image(file)
                if img_id:
                    self.app.image_manager.apply_image_to_panel(img_id, panel)
            return

        self.app.image_manager._target_panel_for_image_selection = panel
        self.app.image_manager.show_image_library()

    def enter_image_editing_mode(self, panel: Panel):
        """Войти в режим редактирования (кадрирования) изображения для панели."""
        if panel.locked or not panel.content_image:
            return
        self.clear_selection()
        self.select_panel(panel)
        self.image_editing_panel = panel
        self.canvas.config(cursor="fleur")
        self.redraw()
        self.app.set_status(f"Редактирование изображения в панели {panel.id[:8]}. Двигайте/масштабируйте. Двойной клик для выхода.")

    def remove_image_from_panel(self, panel: Panel):
        """Удаляет изображение из указанной панели."""
        if panel.content_image:
            confirm = messagebox.askyesno("Удалить изображение", 
                                          f"Удалить изображение из панели {panel.id[:8]}?",
                                          parent=self.canvas)
            if confirm:
                panel.content_image = None
                panel.reset_image_transform() # Сбрасываем кадрирование
                self.clear_specific_image_tk_cache(panel.id) # Очищаем кэш PhotoImage
                self.clear_specific_pil_image_cache(panel.id) # Очищаем кэш PIL.Image
                self.save_history_state()
                self.redraw()
                self.app.project_modified = True
                self.app.update_title()
                self.app.set_status(f"Изображение удалено из панели {panel.id[:8]}.")

    def clear_specific_pil_image_cache(self, panel_id: str):
        if panel_id in self.pil_image_cache:
            del self.pil_image_cache[panel_id]

    def clear_specific_image_tk_cache(self, panel_id_or_key_prefix: str):
        """Очищает кэш ImageTk.PhotoImage для конкретной панели или по префиксу ключа."""
        keys_to_delete = [key for key in self.image_tk_cache if key.startswith(panel_id_or_key_prefix)]
        for key in keys_to_delete:
            del self.image_tk_cache[key]
            
    # Вспомогательные методы
    def find_panel_at_point(self, x: float, y: float) -> Optional[Panel]:
        """Найти панель в указанной точке (по порядку слоёв)"""
        # Сортировка по слоям (верхние слои проверяются первыми)
        sorted_panels = sorted(self.panels, key=lambda p: p.layer, reverse=True)
        
        for panel in sorted_panels:
            if panel.visible and panel.contains_point(x, y):
                return panel
        return None
        
    def create_panel(self, x: float, y: float, width: float, height: float, panel_type: PanelType = PanelType.RECTANGULAR):
        """Создание новой панели"""
        panel = Panel(
            x=x, y=y, width=width, height=height,
            panel_type=panel_type,
            layer=max((p.layer for p in self.panels), default=-1) + 1 if self.panels else 0
        )
        panel._image_content_updated_flag = True # Новая панель, контент "обновлен"
        
        self.panels.append(panel)
        self.clear_selection()
        self.select_panel(panel)
        self.save_history_state()
        
        if hasattr(self.app, 'update_layers_list'):
            self.app.update_layers_list()
        
        return panel
        
    def create_speech_bubble(self, x: float, y: float):
        """Создание речевого пузыря"""
        width, height = 80, 60
        x, y = self.snap_to_grid_coords(x - width/2, y - height/2)
        
        panel = self.create_panel(x, y, width, height, PanelType.SPEECH_BUBBLE)
        panel.content_text = "Текст"
        
    def select_panel(self, panel: Panel):
        """Выделение панели"""
        if panel not in self.selected_panels:
            panel.selected = True
            self.selected_panels.append(panel)
            # Исправлено: добавлена проверка на существование метода
            if hasattr(self.app, 'update_layers_list'):
                self.app.update_layers_list()
            
    def clear_selection(self):
        """Очистка выделения"""
        for panel in self.selected_panels:
            panel.selected = False
        # Исправлено: добавлена проверка на существование метода
        if hasattr(self.app, 'update_layers_list'):
            self.app.update_layers_list()
        self.selected_panels.clear()
        self.selection_handles.clear()
        
    def delete_selected(self, event=None):
        """Удаление выделенных панелей"""
        if self.selected_panels:
            ids_to_clear = []
            for panel in self.selected_panels:
                if panel in self.panels:
                    ids_to_clear.append(panel.id)
                    self.panels.remove(panel)
            
            for panel_id in ids_to_clear:
                self.clear_specific_pil_image_cache(panel_id)
                self.clear_specific_image_tk_cache(panel_id) # Удаляем по префиксу id

            # Если удаляемая панель была в режиме редактирования изображения
            if self.image_editing_panel and self.image_editing_panel.id in ids_to_clear:
                self.image_editing_panel = None
                self.canvas.config(cursor="arrow")

            self.clear_selection()
            if hasattr(self.app, 'update_layers_list'):
                self.app.update_layers_list()
            self.save_history_state()
            self.redraw()
            self.app.project_modified = True
            self.app.update_title()
            
    def save_history_state(self):
        """Сохраняет текущее состояние панелей в стек отмены."""
        self.redo_stack.clear() # Любое новое действие очищает стек повтора
        
        current_panels_copy = copy.deepcopy(self.panels)
        self.undo_stack.append(current_panels_copy)
        
        if len(self.undo_stack) > self.MAX_HISTORY_SIZE:
            self.undo_stack.pop(0) # Удаляем самое старое состояние

    def undo_action(self): # Будет вызываться из main.py
        """Отмена последнего действия."""
        if len(self.undo_stack) > 1: # Нужно, чтобы осталось хотя бы одно (самое первое) состояние
            current_state_for_redo = self.undo_stack.pop()
            self.redo_stack.append(current_state_for_redo)
            
            previous_state = self.undo_stack[-1]
            self.panels = copy.deepcopy(previous_state)
            
            self._post_history_change_update()
            return True
        return False

    def redo_action(self): # Будет вызываться из main.py
        """Повтор отмененного действия."""
        if self.redo_stack:
            state_to_restore = self.redo_stack.pop()
            # Добавляем обратно в undo_stack, сохраняя его максимальный размер
            self.undo_stack.append(copy.deepcopy(state_to_restore))
            if len(self.undo_stack) > self.MAX_HISTORY_SIZE:
                self.undo_stack.pop(0)

            self.panels = copy.deepcopy(state_to_restore)
            
            self._post_history_change_update()
            return True
        return False

    def _post_history_change_update(self):
        """Вспомогательный метод для обновления UI после undo/redo."""
        if self.image_editing_panel:
            self.image_editing_panel = None
            self.canvas.config(cursor="arrow")
        self.clear_selection()
        self.image_tk_cache.clear() 
        self.redraw()
        if hasattr(self.app, 'update_layers_list'):
            self.app.update_layers_list()
        if hasattr(self.app, 'update_properties_panel'):
            self.app.update_properties_panel()
            
    def resize_panel_with_handle(self, panel: Panel, handle: SelectionHandle, current_page_x: float, current_page_y: float):
        """Изменение размера панели с помощью маркера. current_page_x/y - это page-координаты мыши."""
        
        # Начальные page-координаты панели
        orig_x1, orig_y1 = panel.x, panel.y
        orig_x2, orig_y2 = panel.x + panel.width, panel.y + panel.height

        new_x1, new_y1, new_x2, new_y2 = orig_x1, orig_y1, orig_x2, orig_y2

        # Координаты мыши (уже в page-координатах)
        # Привязка к сетке применяется к координате, которую мы двигаем
        
        # Обновляем соответствующую(ие) границу(ы)
        # Важно: привязываем к сетке именно ту координату, которую двигает маркер
        if "n" in handle.handle_type:
            new_y1 = self.snap_to_grid_coords(current_page_x, current_page_y)[1]
        if "s" in handle.handle_type:
            new_y2 = self.snap_to_grid_coords(current_page_x, current_page_y)[1]
        if "w" in handle.handle_type:
            new_x1 = self.snap_to_grid_coords(current_page_x, current_page_y)[0]
        if "e" in handle.handle_type:
            new_x2 = self.snap_to_grid_coords(current_page_x, current_page_y)[0]

        # Обеспечиваем минимальный размер панели
        min_page_size = 20 # Минимальный размер в page-координатах
        
        if new_x2 - new_x1 < min_page_size:
            if "w" in handle.handle_type and new_x1 > orig_x2 - min_page_size : # Если тащили левую границу и она "перескочила"
                new_x1 = orig_x2 - min_page_size
            elif "e" in handle.handle_type and new_x2 < orig_x1 + min_page_size: # Если тащили правую и она "перескочила"
                new_x2 = orig_x1 + min_page_size
            else: # Общий случай или угловые маркеры
                if "w" in handle.handle_type: new_x1 = new_x2 - min_page_size
                else: new_x2 = new_x1 + min_page_size
        
        if new_y2 - new_y1 < min_page_size:
            if "n" in handle.handle_type and new_y1 > orig_y2 - min_page_size:
                new_y1 = orig_y2 - min_page_size
            elif "s" in handle.handle_type and new_y2 < orig_y1 + min_page_size:
                new_y2 = orig_y1 + min_page_size
            else:
                if "n" in handle.handle_type: new_y1 = new_y2 - min_page_size
                else: new_y2 = new_y1 + min_page_size
                
        # Устанавливаем новые значения панели
        panel.x = new_x1
        panel.y = new_y1
        panel.width = new_x2 - new_x1
        panel.height = new_y2 - new_y1

        # Ограничиваем панель границами страницы (простая обрезка)
        panel.x = max(0, panel.x)
        panel.y = max(0, panel.y)
        
        if panel.x + panel.width > self.page_width:
            panel.width = self.page_width - panel.x
        if panel.y + panel.height > self.page_height:
            panel.height = self.page_height - panel.y
        
        # Гарантируем минимальный размер после обрезки границами страницы
        panel.width = max(min_page_size, panel.width)
        panel.height = max(min_page_size, panel.height)

        panel.mark_visuals_for_update()

        # После изменения размера панели, нужно очистить ее кэш изображения,
        # т.к. PhotoImage нужно будет пересоздать с новым размером.
        self.clear_panel_image_cache(panel.id)
            
    # Заглушки для методов, которые будут реализованы позже
    def copy_selected(self, event=None):
        """Копирование выделенных панелей"""
        if not self.selected_panels:
            self.app.set_status("Нет выделенных панелей для копирования")
            return
            
        # Копирование панелей в буфер обмена приложения
        self.app.clipboard_panels = copy.deepcopy(self.selected_panels)
        self.app.set_status(f"Скопировано панелей: {len(self.selected_panels)}")

        return "break"

    def paste_panels(self, event=None):
        """Вставка панелей из буфера обмена"""
        if not hasattr(self.app, 'clipboard_panels') or not self.app.clipboard_panels:
            self.app.set_status("Буфер обмена пуст")
            return
            
        # Очистка текущего выделения
        self.clear_selection()
        
        # Вставка панелей со смещением
        offset_x = 20
        offset_y = 20
        
        for panel in self.app.clipboard_panels:
            new_panel = copy.deepcopy(panel)
            new_panel.id = str(uuid.uuid4())  # Новый уникальный ID
            new_panel.x += offset_x
            new_panel.y += offset_y
            new_panel.selected = False  # Сброс выделения
            
            # Проверка границ страницы
            if new_panel.x + new_panel.width > self.page_width:
                new_panel.x = self.page_width - new_panel.width
            if new_panel.y + new_panel.height > self.page_height:
                new_panel.y = self.page_height - new_panel.height
                
            # Убеждаемся, что панель не выходит за границы
            new_panel.x = max(0, new_panel.x)
            new_panel.y = max(0, new_panel.y)
            
            self.panels.append(new_panel)
            self.select_panel(new_panel)
            
        self.save_history_state()
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()
        self.app.set_status(f"Вставлено панелей: {len(self.app.clipboard_panels)}")

        return "break"

    def select_all(self, event=None):
        """Выделение всех панелей на странице"""
        self.clear_selection()
        
        for panel in self.panels:
            self.select_panel(panel)
            
        self.redraw()
        self.app.set_status(f"Выделено панелей: {len(self.panels)}")

        return "break"

    def select_all_panels(self):
        """Альтернативный метод выделения всех панелей"""
        self.select_all()

    def edit_panel_properties(self, panel):
        """Открытие диалога редактирования свойств панели"""
        # Создание диалогового окна
        dialog = tk.Toplevel(self.canvas)
        dialog.title(f"Свойства панели")
        dialog.geometry("400x500")
        dialog.resizable(False, False)
        
        # Центрирование диалога
        dialog.transient(self.canvas)
        dialog.grab_set()
        
        # Переменные для хранения значений
        vars_dict = {}
        
        # Основные свойства
        main_frame = tk.LabelFrame(dialog, text="Основные свойства")
        main_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Позиция
        tk.Label(main_frame, text="X:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['x'] = tk.DoubleVar(value=panel.x)
        tk.Entry(main_frame, textvariable=vars_dict['x'], width=10).grid(row=0, column=1, padx=5, pady=2)
        
        tk.Label(main_frame, text="Y:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        vars_dict['y'] = tk.DoubleVar(value=panel.y)
        tk.Entry(main_frame, textvariable=vars_dict['y'], width=10).grid(row=0, column=3, padx=5, pady=2)
        
        # Размеры
        tk.Label(main_frame, text="Ширина:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['width'] = tk.DoubleVar(value=panel.width)
        tk.Entry(main_frame, textvariable=vars_dict['width'], width=10).grid(row=1, column=1, padx=5, pady=2)
        
        tk.Label(main_frame, text="Высота:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        vars_dict['height'] = tk.DoubleVar(value=panel.height)
        tk.Entry(main_frame, textvariable=vars_dict['height'], width=10).grid(row=1, column=3, padx=5, pady=2)
        
        # Тип панели
        tk.Label(main_frame, text="Тип:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['panel_type'] = tk.StringVar(value=panel.panel_type.value)
        type_combo = tk.ttk.Combobox(main_frame, textvariable=vars_dict['panel_type'],
                                    values=[t.value for t in PanelType], state="readonly", width=15)
        type_combo.grid(row=2, column=1, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        # Слой
        tk.Label(main_frame, text="Слой:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['layer'] = tk.IntVar(value=panel.layer)
        tk.Spinbox(main_frame, from_=0, to=100, textvariable=vars_dict['layer'], width=10).grid(row=3, column=1, padx=5, pady=2)
        
        # Стиль панели
        style_frame = tk.LabelFrame(dialog, text="Стиль")
        style_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Толщина рамки
        tk.Label(style_frame, text="Толщина рамки:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['border_width'] = tk.IntVar(value=panel.style.border_width)
        tk.Spinbox(style_frame, from_=0, to=20, textvariable=vars_dict['border_width'], width=10).grid(row=0, column=1, padx=5, pady=2)
        
        # Цвет рамки
        tk.Label(style_frame, text="Цвет рамки:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['border_color'] = tk.StringVar(value=panel.style.border_color)
        
        color_frame = tk.Frame(style_frame)
        color_frame.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        color_button = tk.Button(color_frame, text="  ", width=3, bg=panel.style.border_color,
                                command=lambda: choose_color(vars_dict['border_color'], color_button))
        color_button.pack(side=tk.LEFT)
        
        tk.Entry(color_frame, textvariable=vars_dict['border_color'], width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # Цвет заливки
        tk.Label(style_frame, text="Цвет заливки:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['fill_color'] = tk.StringVar(value=panel.style.fill_color)
        
        fill_frame = tk.Frame(style_frame)
        fill_frame.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        fill_button = tk.Button(fill_frame, text="  ", width=3, bg=panel.style.fill_color,
                            command=lambda: choose_color(vars_dict['fill_color'], fill_button))
        fill_button.pack(side=tk.LEFT)
        
        tk.Entry(fill_frame, textvariable=vars_dict['fill_color'], width=10).pack(side=tk.LEFT, padx=(5, 0))
        
        # Тень
        vars_dict['shadow'] = tk.BooleanVar(value=panel.style.shadow)
        tk.Checkbutton(style_frame, text="Тень", variable=vars_dict['shadow']).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        # Содержимое
        content_frame = tk.LabelFrame(dialog, text="Содержимое")
        content_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Текст
        tk.Label(content_frame, text="Текст:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        vars_dict['content_text'] = tk.StringVar(value=panel.content_text)
        tk.Entry(content_frame, textvariable=vars_dict['content_text'], width=30).grid(row=0, column=1, padx=5, pady=2)
        
        # Состояние
        state_frame = tk.LabelFrame(dialog, text="Состояние")
        state_frame.pack(fill=tk.X, padx=10, pady=5)
        
        vars_dict['visible'] = tk.BooleanVar(value=panel.visible)
        tk.Checkbutton(state_frame, text="Видимая", variable=vars_dict['visible']).grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        
        vars_dict['locked'] = tk.BooleanVar(value=panel.locked)
        tk.Checkbutton(state_frame, text="Заблокированная", variable=vars_dict['locked']).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        
        def choose_color(color_var, button):
            """Выбор цвета"""
            import tkinter.colorchooser as colorchooser
            color = colorchooser.askcolor(color=color_var.get(), title="Выберите цвет")[1]
            if color:
                color_var.set(color)
                button.configure(bg=color)
        
        def apply_changes():
            """Применение изменений"""
            try:
                # Обновление свойств панели
                panel.x = vars_dict['x'].get()
                panel.y = vars_dict['y'].get()
                panel.width = max(10, vars_dict['width'].get())  # Минимальный размер
                panel.height = max(10, vars_dict['height'].get())
                panel.panel_type = PanelType(vars_dict['panel_type'].get())
                panel.layer = vars_dict['layer'].get()
                
                # Обновление стиля
                panel.style.border_width = vars_dict['border_width'].get()
                panel.style.border_color = vars_dict['border_color'].get()
                panel.style.fill_color = vars_dict['fill_color'].get()
                panel.style.shadow = vars_dict['shadow'].get()
                
                # Обновление содержимого
                panel.content_text = vars_dict['content_text'].get()
                
                # Обновление состояния
                panel.visible = vars_dict['visible'].get()
                panel.locked = vars_dict['locked'].get()
                
                # Сохранение в истории и обновление
                self.save_history_state()
                self.redraw()
                self.app.project_modified = True
                self.app.update_title()
                
                dialog.destroy()
                
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось применить изменения:\n{e}")
        
        # Кнопки
        buttons_frame = tk.Frame(dialog)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttons_frame, text="OK", command=apply_changes).pack(side=tk.RIGHT, padx=5)
        tk.Button(buttons_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT)
    def duplicate_panel(self, panel):
        """Дублирование панели"""
        # Создание копии панели
        new_panel = copy.deepcopy(panel)
        new_panel.id = str(uuid.uuid4())  # Новый уникальный ID
        
        # Смещение новой панели
        offset = 20
        new_panel.x += offset
        new_panel.y += offset
        
        # Проверка границ страницы
        if new_panel.x + new_panel.width > self.page_width:
            new_panel.x = panel.x - offset
        if new_panel.y + new_panel.height > self.page_height:
            new_panel.y = panel.y - offset
            
        # Убеждаемся, что панель не выходит за границы
        new_panel.x = max(0, new_panel.x)
        new_panel.y = max(0, new_panel.y)
        
        # Добавление на тот же слой
        new_panel.layer = max(p.layer for p in self.panels) + 1
        new_panel.selected = False
        
        self.panels.append(new_panel)
        
        # Выделение новой панели
        self.clear_selection()
        self.select_panel(new_panel)
        
        self.save_history_state()
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()
        self.app.set_status("Панель дублирована")
        
    def bring_to_front(self, panel):
        self._normalize_layers()                     # <-- важно
        top = max(p.layer for p in self.panels)
        if panel.layer < top:
            panel.layer = top + 1
            self.save_history_state()
            self.redraw(); self.app.project_modified = True
            self.app.update_title(); self.app.update_layers_list()
            self.app.set_status("Панель поднята вверх")
        else:
            self.app.set_status("Панель уже сверху")

    def send_to_back(self, panel):
        self._normalize_layers()
        bottom = min(p.layer for p in self.panels)
        if panel.layer > bottom:
            panel.layer = bottom - 1
            self.save_history_state()
            self.redraw(); self.app.project_modified = True
            self.app.update_title(); self.app.update_layers_list()
            self.app.set_status("Панель отправлена вниз")
        else:
            self.app.set_status("Панель уже внизу")

    def delete_panel(self, panel):
        """Удаление конкретной панели"""
        if panel in self.panels:
            # Подтверждение удаления
            result = messagebox.askyesno("Подтверждение", 
                                    "Удалить выбранную панель?")
            if result:
                self.panels.remove(panel)
                self.clear_panel_image_cache(panel.id)
                
                # Удаление из выделения если выделена
                if panel in self.selected_panels:
                    self.selected_panels.remove(panel)
                    self.clear_panel_image_cache(panel.id)
                    
                self.save_history_state()
                self.redraw()
                self.app.project_modified = True
                self.app.update_title()
                self.app.set_status("Панель удалена")

    def set_panel_text(self, panel, text):
        """Установка текста панели"""
        panel.content_text = text
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()

    def get_panel_at_position(self, x, y):
        """Получение панели в указанной позиции (альтернатива find_panel_at_point)"""
        return self.find_panel_at_point(x, y)
    
    def align_panels_horizontal(self, alignment="center"):
        """Выравнивание панелей по горизонтали"""
        if len(self.selected_panels) < 2:
            self.app.set_status("Выделите минимум 2 панели для выравнивания")
            return
            
        if alignment == "left":
            ref_x = min(panel.x for panel in self.selected_panels)
            for panel in self.selected_panels:
                panel.x = ref_x
        elif alignment == "right":
            ref_x = max(panel.x + panel.width for panel in self.selected_panels)
            for panel in self.selected_panels:
                panel.x = ref_x - panel.width
        else:  # center
            ref_x = sum(panel.x + panel.width/2 for panel in self.selected_panels) / len(self.selected_panels)
            for panel in self.selected_panels:
                panel.x = ref_x - panel.width/2
                
        self.save_history_state()
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()
        self.app.set_status(f"Панели выровнены по {alignment}")

    def align_panels_vertical(self, alignment="center"):
        """Выравнивание панелей по вертикали"""
        if len(self.selected_panels) < 2:
            self.app.set_status("Выделите минимум 2 панели для выравнивания")
            return
            
        if alignment == "top":
            ref_y = min(panel.y for panel in self.selected_panels)
            for panel in self.selected_panels:
                panel.y = ref_y
        elif alignment == "bottom":
            ref_y = max(panel.y + panel.height for panel in self.selected_panels)
            for panel in self.selected_panels:
                panel.y = ref_y - panel.height
        else:  # center
            ref_y = sum(panel.y + panel.height/2 for panel in self.selected_panels) / len(self.selected_panels)
            for panel in self.selected_panels:
                panel.y = ref_y - panel.height/2
                
        self.save_history_state()
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()
        self.app.set_status(f"Панели выровнены по {alignment}")

    def distribute_panels_horizontal(self):
        """Равномерное распределение панелей по горизонтали"""
        if len(self.selected_panels) < 3:
            self.app.set_status("Выделите минимум 3 панели для распределения")
            return
            
        # Сортировка панелей по X координате
        sorted_panels = sorted(self.selected_panels, key=lambda p: p.x)
        
        # Вычисление интервала
        total_width = sorted_panels[-1].x - sorted_panels[0].x
        interval = total_width / (len(sorted_panels) - 1)
        
        # Распределение панелей
        for i, panel in enumerate(sorted_panels[1:-1], 1):
            panel.x = sorted_panels[0].x + interval * i
            
        self.save_history_state()
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()
        self.app.set_status("Панели распределены по горизонтали")

    def distribute_panels_vertical(self):
        """Равномерное распределение панелей по вертикали"""
        if len(self.selected_panels) < 3:
            self.app.set_status("Выделите минимум 3 панели для распределения")
            return
            
        # Сортировка панелей по Y координате
        sorted_panels = sorted(self.selected_panels, key=lambda p: p.y)
        
        # Вычисление интервала
        total_height = sorted_panels[-1].y - sorted_panels[0].y
        interval = total_height / (len(sorted_panels) - 1)
        
        # Распределение панелей
        for i, panel in enumerate(sorted_panels[1:-1], 1):
            panel.y = sorted_panels[0].y + interval * i
            
        self.save_history_state()
        self.redraw()
        self.app.project_modified = True
        self.app.update_title()
        self.app.set_status("Панели распределены по вертикали")