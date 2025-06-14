#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - вспомогательные функции
Общие утилиты, константы и вспомогательные классы
"""

import tkinter as tk
from tkinter import ttk
import os
import sys
import math
import json
import logging
from pathlib import Path
from typing import Tuple, List, Optional, Dict, Any, Union
from PIL import Image, ImageTk, ImageDraw, ImageFilter
import tempfile
from datetime import datetime


# ========================================
# КОНСТАНТЫ
# ========================================

# Размеры страниц (в пикселях при 300 DPI)
PAGE_SIZES = {
    "A4": (2480, 3508),
    "A5": (1748, 2480),
    "B4": (2953, 4169),
    "B5": (2079, 2953),
    "Letter": (2550, 3300),
    "Tabloid": (3300, 5100),
    "Пользовательский": (2079, 2953)  # По умолчанию B5
}

ORIENTATIONS = {
    "Портретный": "portrait",
    "Альбомный": "landscape"
}

# Также полезно иметь обратный словарь для удобства
ORIENTATIONS_REV = {v: k for k, v in ORIENTATIONS.items()}

# Стандартные DPI для экспорта
DPI_SETTINGS = {
    "Веб": 72,
    "Печать": 300,
    "Высокое качество": 600
}

# Цветовые схемы для интерфейса
COLOR_SCHEMES = {
    "light": {
        "bg": "#F5F5F5",
        "fg": "#333333",
        "select": "#FF6B6B",
        "grid": "#E0E0E0",
        "guides": "#FFB6C1",
        "panel_bg": "#FFFFFF",
        "panel_border": "#000000"
    },
    "dark": {
        "bg": "#2E2E2E",
        "fg": "#FFFFFF",
        "select": "#FF6B6B",
        "grid": "#404040",
        "guides": "#8B4B8B",
        "panel_bg": "#1E1E1E",
        "panel_border": "#CCCCCC"
    }
}

# Форматы экспорта
EXPORT_FORMATS = {
    "PNG": {"ext": ".png", "desc": "PNG изображение"},
    "JPEG": {"ext": ".jpg", "desc": "JPEG изображение"},
    "PDF": {"ext": ".pdf", "desc": "PDF документ"},
    "CBZ": {"ext": ".cbz", "desc": "Comic Book Archive"},
    "PSD": {"ext": ".psd", "desc": "Photoshop Document"}
}

# Типы переходов между панелями
PANEL_TRANSITIONS = {
    "moment_to_moment": "Мгновение к мгновению",
    "action_to_action": "Действие к действию", 
    "subject_to_subject": "Субъект к субъекту",
    "scene_to_scene": "Сцена к сцене",
    "aspect_to_aspect": "Аспект к аспекту",
    "non_sequitur": "Произвольный переход"
}

# Эмоциональные эффекты панелей
PANEL_EFFECTS = {
    "calm": {"border_style": "solid", "shadow": False, "corner_radius": 0},
    "tension": {"border_style": "jagged", "shadow": True, "corner_radius": 0},
    "shock": {"border_style": "burst", "shadow": True, "corner_radius": 0},
    "flashback": {"border_style": "wavy", "shadow": False, "corner_radius": 10},
    "dream": {"border_style": "cloud", "shadow": False, "corner_radius": 20}
}


# ========================================
# ЛОГИРОВАНИЕ
# ========================================

def setup_logging(log_level=logging.INFO):
    """Настройка логирования"""
    log_dir = Path.home() / ".manga_constructor" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"manga_constructor_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger("MangaConstructor")


# ========================================
# РАБОТА С ИЗОБРАЖЕНИЯМИ
# ========================================

def load_icon(icon_path: str, size: Tuple[int, int] = (16, 16)) -> Optional[ImageTk.PhotoImage]:
    """Загрузка иконки с обработкой ошибок"""
    try:
        if os.path.exists(icon_path):
            image = Image.open(icon_path)
            image = image.resize(size, Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image)
    except Exception as e:
        logging.warning(f"Не удалось загрузить иконку {icon_path}: {e}")
    
    # Создание простой иконки по умолчанию
    return create_default_icon(size)


def create_default_icon(size: Tuple[int, int] = (16, 16)) -> ImageTk.PhotoImage:
    """Создание простой иконки по умолчанию"""
    try:
        image = Image.new('RGBA', size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Простой квадрат с рамкой
        margin = 2
        draw.rectangle([margin, margin, size[0]-margin-1, size[1]-margin-1], 
                      outline='#333333', fill='#FFFFFF', width=1)
        
        return ImageTk.PhotoImage(image)
    except Exception:
        return None


def resize_image_to_fit(image_path: str, target_width: int, target_height: int, 
                       keep_aspect: bool = True) -> Optional[Image.Image]:
    """Изменение размера изображения с сохранением пропорций"""
    try:
        image = Image.open(image_path)
        
        if keep_aspect:
            # Вычисление размера с сохранением пропорций
            image_ratio = image.width / image.height
            target_ratio = target_width / target_height
            
            if image_ratio > target_ratio:
                # Изображение шире - подгоняем по ширине
                new_width = target_width
                new_height = int(target_width / image_ratio)
            else:
                # Изображение выше - подгоняем по высоте
                new_height = target_height
                new_width = int(target_height * image_ratio)
        else:
            new_width, new_height = target_width, target_height
            
        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
    except Exception as e:
        logging.error(f"Ошибка изменения размера изображения {image_path}: {e}")
        return None


def crop_image_to_panel(image: Image.Image, panel_bounds: Tuple[int, int, int, int],
                       crop_mode: str = "center") -> Image.Image:
    """Обрезка изображения под размер панели"""
    panel_width = panel_bounds[2] - panel_bounds[0]
    panel_height = panel_bounds[3] - panel_bounds[1]
    
    # Изменение размера изображения
    resized = resize_image_to_fit_exact(image, panel_width, panel_height)
    
    if crop_mode == "center":
        # Центрированная обрезка
        left = (resized.width - panel_width) // 2
        top = (resized.height - panel_height) // 2
        right = left + panel_width
        bottom = top + panel_height
        
        return resized.crop((left, top, right, bottom))
    
    elif crop_mode == "smart":
        # Умная обрезка (пытается сохранить важные детали)
        return smart_crop(resized, panel_width, panel_height)
    
    else:
        # Обрезка сверху-слева
        return resized.crop((0, 0, panel_width, panel_height))


def resize_image_to_fit_exact(image: Image.Image, width: int, height: int) -> Image.Image:
    """Изменение размера с заполнением всей области"""
    image_ratio = image.width / image.height
    target_ratio = width / height
    
    if image_ratio > target_ratio:
        # Подгоняем по высоте
        new_height = height
        new_width = int(height * image_ratio)
    else:
        # Подгоняем по ширине
        new_width = width
        new_height = int(width / image_ratio)
        
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def smart_crop(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """
    Умная обрезка изображения с попыткой сохранить наиболее «интересные» детали.
    Если исходник меньше цели хотя бы по одной стороне, выполняется простое
    центр-кадрирование; иначе ищется наиболее контрастная область.
    """
    # ── 1. Быстрый путь: исходник меньше цели ───────────────────────────────
    if image.width <= target_width or image.height <= target_height:
        left = max(0, (image.width  - target_width)  // 2)
        top  = max(0, (image.height - target_height) // 2)
        return image.crop((left, top, left + target_width, top + target_height))

    # ── 2. Поиск самой деталированной области по сетке ─────────────────────
    try:
        gray   = image.convert("L")
        edges  = gray.filter(ImageFilter.FIND_EDGES)

        grid_size     = 32
        max_interest  = -1
        best_x        = 0
        best_y        = 0

        for y in range(0, image.height - target_height + 1, grid_size):
            for x in range(0, image.width - target_width + 1, grid_size):
                crop_area = edges.crop((x, y, x + target_width, y + target_height))
                interest_score = sum(crop_area.getdata())

                if interest_score > max_interest:
                    max_interest = interest_score
                    best_x, best_y = x, y

        return image.crop((best_x, best_y,
                           best_x + target_width, best_y + target_height))

    # ── 3. Резерв: центр-кадрирование при сбоях алгоритма ───────────────────
    except Exception:
        left = (image.width  - target_width)  // 2
        top  = (image.height - target_height) // 2
        return image.crop((left, top, left + target_width, top + target_height))

# ========================================
# РАБОТА С ФАЙЛАМИ
# ========================================

def ensure_directory(path: Union[str, Path]) -> Path:
    """Создание директории если она не существует"""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_app_data_dir() -> Path:
    """Получение директории данных приложения"""
    if sys.platform == "win32":
        base_dir = Path(os.environ.get('APPDATA', Path.home()))
    else:
        base_dir = Path.home() / '.config'
        
    return ensure_directory(base_dir / 'MangaConstructor')


def get_temp_dir() -> Path:
    """Получение временной директории"""
    temp_dir = Path(tempfile.gettempdir()) / 'MangaConstructor'
    return ensure_directory(temp_dir)


def safe_filename(filename: str) -> str:
    """Создание безопасного имени файла"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Ограничение длины
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
        
    return filename


def load_json_file(file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Безопасная загрузка JSON файла"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Ошибка загрузки JSON файла {file_path}: {e}")
        return None


def save_json_file(data: Dict[str, Any], file_path: Union[str, Path]) -> bool:
    """Безопасное сохранение JSON файла"""
    try:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.error(f"Ошибка сохранения JSON файла {file_path}: {e}")
        return False


# ========================================
# МАТЕМАТИЧЕСКИЕ УТИЛИТЫ
# ========================================

def distance_point_to_point(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Расстояние между двумя точками"""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)


def distance_point_to_line(point: Tuple[float, float], line_start: Tuple[float, float], 
                          line_end: Tuple[float, float]) -> float:
    """Расстояние от точки до линии"""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    # Формула расстояния от точки до прямой
    numerator = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    denominator = math.sqrt((y2 - y1)**2 + (x2 - x1)**2)
    
    return numerator / denominator if denominator != 0 else 0


def point_in_rectangle(point: Tuple[float, float], rect: Tuple[float, float, float, float]) -> bool:
    """Проверка нахождения точки в прямоугольнике"""
    x, y = point
    x1, y1, x2, y2 = rect
    return x1 <= x <= x2 and y1 <= y <= y2


def rectangles_intersect(rect1: Tuple[float, float, float, float], 
                        rect2: Tuple[float, float, float, float]) -> bool:
    """Проверка пересечения двух прямоугольников"""
    x1, y1, x2, y2 = rect1
    x3, y3, x4, y4 = rect2
    
    return not (x2 < x3 or x4 < x1 or y2 < y3 or y4 < y1)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Ограничение значения в диапазоне"""
    return max(min_val, min(max_val, value))


def lerp(a: float, b: float, t: float) -> float:
    """Линейная интерполяция"""
    return a + (b - a) * t


def angle_between_points(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Угол между двумя точками в радианах"""
    return math.atan2(p2[1] - p1[1], p2[0] - p1[0])


def rotate_point(point: Tuple[float, float], center: Tuple[float, float], angle: float) -> Tuple[float, float]:
    """Поворот точки вокруг центра"""
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    
    # Перенос в начало координат
    x = point[0] - center[0]
    y = point[1] - center[1]
    
    # Поворот
    new_x = x * cos_a - y * sin_a
    new_y = x * sin_a + y * cos_a
    
    # Перенос обратно
    return (new_x + center[0], new_y + center[1])


# ========================================
# UI УТИЛИТЫ
# ========================================

class ToolTip:
    """Класс для создания всплывающих подсказок"""
    
    def __init__(self, widget: tk.Widget, text: str, delay: int = 500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tooltip_window = None
        self.after_id = None
        
        widget.bind("<Enter>", self.on_enter)
        widget.bind("<Leave>", self.on_leave)
        widget.bind("<Motion>", self.on_motion)
        
    def on_enter(self, event=None):
        """Мышь вошла в область виджета"""
        self.schedule_show()
        
    def on_leave(self, event=None):
        """Мышь покинула область виджета"""
        self.cancel_show()
        self.hide_tooltip()
        
    def on_motion(self, event=None):
        """Движение мыши в области виджета"""
        self.cancel_show()
        self.schedule_show()
        
    def schedule_show(self):
        """Запланировать показ подсказки"""
        self.cancel_show()
        self.after_id = self.widget.after(self.delay, self.show_tooltip)
        
    def cancel_show(self):
        """Отменить показ подсказки"""
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None
            
    def show_tooltip(self):
        """Показать подсказку"""
        if self.tooltip_window or not self.text:
            return
            
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tk.Label(tw, text=self.text, background="#FFFFCC", 
                        relief=tk.SOLID, borderwidth=1, font=("Arial", 8))
        label.pack()
        
    def hide_tooltip(self):
        """Скрыть подсказку"""
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


def create_tooltip(widget: tk.Widget, text: str, delay: int = 500) -> ToolTip:
    """Создание всплывающей подсказки для виджета"""
    return ToolTip(widget, text, delay)


def center_window(window: tk.Toplevel, parent: tk.Widget = None):
    """Центрирование окна относительно родительского или экрана"""
    window.update_idletasks()
    
    width = window.winfo_width()
    height = window.winfo_height()
    
    if parent:
        x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (width // 2)
        y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (height // 2)
    else:
        x = (window.winfo_screenwidth() // 2) - (width // 2)
        y = (window.winfo_screenheight() // 2) - (height // 2)
        
    window.geometry(f'{width}x{height}+{x}+{y}')


def create_separator(parent: tk.Widget, orient: str = "horizontal") -> ttk.Separator:
    """Создание разделителя"""
    return ttk.Separator(parent, orient=orient)


def create_labeled_entry(parent: tk.Widget, label_text: str, 
                        variable: tk.Variable = None, **kwargs) -> Tuple[ttk.Label, ttk.Entry]:
    """Создание поля ввода с подписью"""
    label = ttk.Label(parent, text=label_text)
    entry = ttk.Entry(parent, textvariable=variable, **kwargs)
    return label, entry


def create_button_with_icon(parent: tk.Widget, text: str, icon_path: str = None, 
                           command=None, **kwargs) -> ttk.Button:
    """Создание кнопки с иконкой"""
    button_kwargs = kwargs.copy()
    
    if icon_path and os.path.exists(icon_path):
        try:
            icon = load_icon(icon_path, (16, 16))
            if icon:
                button_kwargs['image'] = icon
                button_kwargs['compound'] = tk.LEFT
        except Exception:
            pass
            
    return ttk.Button(parent, text=text, command=command, **button_kwargs)


# ========================================
# КОНВЕРТАЦИЯ И ВАЛИДАЦИЯ
# ========================================

def validate_numeric_input(value: str, allow_float: bool = True, 
                          min_val: float = None, max_val: float = None) -> bool:
    """Валидация числового ввода"""
    if not value:
        return True  # Пустое значение допустимо
        
    try:
        if allow_float:
            num = float(value)
        else:
            num = int(value)
            
        if min_val is not None and num < min_val:
            return False
        if max_val is not None and num > max_val:
            return False
            
        return True
    except ValueError:
        return False


def pixels_to_mm(pixels: float, dpi: float = 300) -> float:
    """Конвертация пикселей в миллиметры"""
    inches = pixels / dpi
    return inches * 25.4


def mm_to_pixels(mm: float, dpi: float = 300) -> float:
    """Конвертация миллиметров в пиксели"""
    inches = mm / 25.4
    return inches * dpi


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Конвертация RGB в HEX"""
    return f"#{r:02x}{g:02x}{b:02x}"


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Конвертация HEX в RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def darken_color(color: str, factor: float = 0.8) -> str:
    """Затемнение цвета"""
    r, g, b = hex_to_rgb(color)
    r = int(r * factor)
    g = int(g * factor)
    b = int(b * factor)
    return rgb_to_hex(r, g, b)


def lighten_color(color: str, factor: float = 1.2) -> str:
    """Осветление цвета"""
    r, g, b = hex_to_rgb(color)
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    return rgb_to_hex(r, g, b)


# ========================================
# СПЕЦИФИЧЕСКИЕ УТИЛИТЫ ДЛЯ МАНГИ
# ========================================

def calculate_reading_flow(panels: List[Any], manga_mode: bool = True) -> List[int]:
    """Вычисление порядка чтения панелей"""
    # Сортировка панелей для правильного потока чтения
    if manga_mode:
        # Манга: справа налево, сверху вниз
        sorted_panels = sorted(enumerate(panels), 
                             key=lambda x: (x[1].y, -x[1].x))
    else:
        # Комикс: слева направо, сверху вниз
        sorted_panels = sorted(enumerate(panels), 
                             key=lambda x: (x[1].y, x[1].x))
    
    return [idx for idx, _ in sorted_panels]


def suggest_panel_size(content_type: str, emotional_impact: str = "normal") -> Tuple[float, float]:
    """Предложение размера панели в зависимости от содержания"""
    base_sizes = {
        "dialogue": (150, 100),
        "action": (200, 150),
        "establishing_shot": (280, 180),
        "close_up": (120, 120),
        "splash": (400, 300)
    }
    
    width, height = base_sizes.get(content_type, (150, 100))
    
    # Корректировка на эмоциональное воздействие
    impact_multipliers = {
        "low": 0.8,
        "normal": 1.0,
        "high": 1.3,
        "extreme": 1.6
    }
    
    multiplier = impact_multipliers.get(emotional_impact, 1.0)
    
    return (width * multiplier, height * multiplier)


def generate_gutter_suggestions(panel_count: int, page_width: float, page_height: float) -> Dict[str, float]:
    """Генерация предложений для промежутков между панелями"""
    # Базовые промежутки в зависимости от количества панелей
    if panel_count <= 3:
        base_gutter = 15
    elif panel_count <= 6:
        base_gutter = 12
    else:
        base_gutter = 8
        
    return {
        "horizontal": base_gutter,
        "vertical": base_gutter * 1.2,  # Вертикальные промежутки чуть больше
        "margin": base_gutter * 2
    }


# Настройка логирования при импорте модуля
logger = setup_logging()