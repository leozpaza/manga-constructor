#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - менеджер настроек
Сохранение и загрузка пользовательских настроек и предпочтений
"""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from dataclasses import dataclass, field, asdict
import json
from enum import Enum

# Импорт из наших модулей
from utils import (logger, get_app_data_dir, save_json_file, load_json_file, 
                   COLOR_SCHEMES, PAGE_SIZES, DPI_SETTINGS, center_window, create_tooltip)


class Theme(Enum):
    """Темы интерфейса"""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"


class Language(Enum):
    """Языки интерфейса"""
    RUSSIAN = "ru"
    ENGLISH = "en"
    JAPANESE = "ja"


@dataclass
class InterfaceSettings:
    """Настройки интерфейса"""
    theme: str = "light"
    language: str = "ru"
    font_family: str = "Arial"
    font_size: int = 9
    toolbar_size: str = "medium"  # small, medium, large
    show_tooltips: bool = True
    animation_speed: int = 300  # миллисекунды
    auto_save_interval: int = 300  # секунды (0 = отключено)
    recent_files_count: int = 10
    confirm_destructive_actions: bool = True


@dataclass
class CanvasSettings:
    """Настройки рабочей области"""
    default_zoom: float = 1.0
    zoom_step: float = 0.1
    max_zoom: float = 5.0
    min_zoom: float = 0.1
    grid_size: int = 50
    grid_color: str = "#E0E0E0"
    guides_color: str = "#FFB6C1"
    selection_color: str = "#FF6B6B"
    background_color: str = "#F5F5F5"
    page_shadow: bool = True
    smooth_scrolling: bool = True
    mouse_wheel_zoom: bool = True


@dataclass
class PanelSettings:
    """Настройки панелей по умолчанию"""
    default_border_width: int = 2
    default_border_color: str = "#000000"
    default_fill_color: str = "#FFFFFF"
    snap_to_grid: bool = False
    snap_threshold: int = 5  # пикселей
    min_panel_size: int = 20
    default_gutter_h: int = 12
    default_gutter_v: int = 15
    auto_arrange: bool = False
    preserve_aspect_ratio: bool = False


@dataclass
class ExportSettings:
    """Настройки экспорта"""
    default_format: str = "PNG"
    default_dpi: int = 300
    jpeg_quality: int = 95
    png_compression: int = 6
    include_bleed: bool = False
    bleed_size: int = 3  # мм
    export_path: str = ""
    watermark_enabled: bool = False
    watermark_text: str = ""
    watermark_opacity: int = 30


@dataclass
class ProjectSettings:
    """Настройки проекта"""
    default_page_size: str = "B5"
    manga_mode: bool = True  # True = справа налево
    page_margin: int = 20
    auto_backup: bool = True
    backup_interval: int = 600  # секунды
    max_backups: int = 5
    compression_enabled: bool = True
    embed_images: bool = False


@dataclass
class PerformanceSettings:
    """Настройки производительности"""
    max_undo_steps: int = 50
    image_cache_size: int = 100  # количество изображений
    thumbnail_cache_size: int = 500
    preload_thumbnails: bool = True
    hardware_acceleration: bool = True
    multithread_export: bool = True
    memory_limit: int = 1024  # МБ


@dataclass
class ShortcutSettings:
    """Настройки горячих клавиш"""
    shortcuts: Dict[str, str] = field(default_factory=lambda: {
        "new_project": "Ctrl+N",
        "open_project": "Ctrl+O", 
        "save_project": "Ctrl+S",
        "save_as": "Ctrl+Shift+S",
        "undo": "Ctrl+Z",
        "redo": "Ctrl+Y",
        "copy": "Ctrl+C",
        "paste": "Ctrl+V",
        "delete": "Delete",
        "select_all": "Ctrl+A",
        "zoom_in": "Ctrl+Plus",
        "zoom_out": "Ctrl+Minus",
        "zoom_fit": "Ctrl+0",
        "grid_toggle": "Ctrl+G",
        "guides_toggle": "Ctrl+Semicolon",
        "import_images": "Ctrl+I",
        "export_page": "Ctrl+E",
        "new_panel": "P",
        "text_tool": "T",
        "speech_tool": "S",
        "select_tool": "V"
    })


@dataclass
class AppSettings:
    """Общие настройки приложения"""
    interface: InterfaceSettings = field(default_factory=InterfaceSettings)
    canvas: CanvasSettings = field(default_factory=CanvasSettings)
    panels: PanelSettings = field(default_factory=PanelSettings)
    export: ExportSettings = field(default_factory=ExportSettings)
    project: ProjectSettings = field(default_factory=ProjectSettings)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)
    shortcuts: ShortcutSettings = field(default_factory=ShortcutSettings)
    recent_files: List[str] = field(default_factory=list)
    window_geometry: str = "1400x900"
    window_maximized: bool = False


class SettingsManager:
    """Менеджер настроек приложения"""
    
    def __init__(self):
        self.settings_dir = get_app_data_dir()
        self.settings_file = self.settings_dir / "settings.json"
        
        # Настройки по умолчанию
        self.settings = AppSettings()
        
        # Загрузка сохранённых настроек
        self.load_settings()
        
        # Окно настроек
        self.settings_window = None
        
    def load_settings(self) -> AppSettings:
        """Загрузка настроек из файла"""
        try:
            if self.settings_file.exists():
                data = load_json_file(self.settings_file)
                if data:
                    # Обновление настроек из загруженных данных
                    self.update_settings_from_dict(data)
                    logger.info("Настройки загружены")
            else:
                logger.info("Файл настроек не найден, используются значения по умолчанию")
                
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")
            
        return self.settings
        
    def save_settings(self) -> bool:
        """Сохранение настроек в файл"""
        try:
            settings_dict = asdict(self.settings)
            success = save_json_file(settings_dict, self.settings_file)
            
            if success:
                logger.info("Настройки сохранены")
            else:
                logger.error("Ошибка сохранения настроек")
                
            return success
            
        except Exception as e:
            logger.error(f"Ошибка сохранения настроек: {e}")
            return False
            
    def update_settings_from_dict(self, data: Dict[str, Any]):
        """Обновление настроек из словаря"""
        try:
            # Обновление каждой секции
            if "interface" in data:
                self.update_dataclass(self.settings.interface, data["interface"])
            if "canvas" in data:
                self.update_dataclass(self.settings.canvas, data["canvas"])
            if "panels" in data:
                self.update_dataclass(self.settings.panels, data["panels"])
            if "export" in data:
                self.update_dataclass(self.settings.export, data["export"])
            if "project" in data:
                self.update_dataclass(self.settings.project, data["project"])
            if "performance" in data:
                self.update_dataclass(self.settings.performance, data["performance"])
            if "shortcuts" in data:
                self.update_dataclass(self.settings.shortcuts, data["shortcuts"])
                
            # Простые поля
            if "recent_files" in data:
                self.settings.recent_files = data["recent_files"]
            if "window_geometry" in data:
                self.settings.window_geometry = data["window_geometry"]
            if "window_maximized" in data:
                self.settings.window_maximized = data["window_maximized"]
                
        except Exception as e:
            logger.error(f"Ошибка обновления настроек: {e}")
            
    def update_dataclass(self, instance, data: Dict[str, Any]):
        """Обновление dataclass из словаря"""
        for key, value in data.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
                
    def reset_to_defaults(self):
        """Сброс настроек к значениям по умолчанию"""
        self.settings = AppSettings()
        logger.info("Настройки сброшены к значениям по умолчанию")
        
    def add_recent_file(self, file_path: str):
        """Добавление файла в список недавних"""
        # Удаление если уже есть в списке
        if file_path in self.settings.recent_files:
            self.settings.recent_files.remove(file_path)
            
        # Добавление в начало
        self.settings.recent_files.insert(0, file_path)
        
        # Ограничение размера списка
        max_count = self.settings.interface.recent_files_count
        self.settings.recent_files = self.settings.recent_files[:max_count]
        
    def remove_recent_file(self, file_path: str):
        """Удаление файла из списка недавних"""
        if file_path in self.settings.recent_files:
            self.settings.recent_files.remove(file_path)
            
    def get_color_scheme(self) -> Dict[str, str]:
        """Получение текущей цветовой схемы"""
        theme = self.settings.interface.theme
        return COLOR_SCHEMES.get(theme, COLOR_SCHEMES["light"])
        
    def show_settings_dialog(self, parent_window=None):
        """Показ диалога настроек"""
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
            
        self.settings_window = tk.Toplevel(parent_window)
        self.settings_window.title("Настройки")

        initial_width = 650  # Немного шире для вкладок
        initial_height = 600 # Увеличиваем начальную высоту
        min_height = 550     # Минимальная высота, чтобы кнопки были видны
        
        self.settings_window.geometry(f"{initial_width}x{initial_height}")
        self.settings_window.minsize(initial_width, min_height) # Устанавливаем минимальный размер
        self.settings_window.resizable(True, True) # Оставляем возможность изменять размер
        
        if parent_window:
            center_window(self.settings_window, parent_window)
            
        self.setup_settings_ui()

        self.settings_window.protocol("WM_DELETE_WINDOW", self._on_settings_dialog_close)

    def _on_settings_dialog_close(self):
        """Обработчик закрытия диалога настроек (по крестику)."""
        if self.settings_window and self.settings_window.winfo_exists():
            # Если бы был grab_set, здесь был бы self.settings_window.grab_release()
            self.settings_window.destroy()
            self.settings_window = None
        
    def setup_settings_ui(self):
        """Настройка интерфейса диалога настроек"""
        # Главный контейнер
        main_frame = ttk.Frame(self.settings_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Notebook для категорий
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Создание вкладок
        self.create_interface_tab(notebook)
        self.create_canvas_tab(notebook)
        self.create_panels_tab(notebook)
        self.create_export_tab(notebook)
        self.create_performance_tab(notebook)
        self.create_shortcuts_tab(notebook)
        
        # Кнопки управления
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(buttons_frame, text="Применить", 
                  command=self.apply_settings).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(buttons_frame, text="Отмена", 
                  command=self._on_settings_dialog_close).pack(side=tk.RIGHT)
        ttk.Button(buttons_frame, text="OK", 
                  command=self.ok_settings_and_close).pack(side=tk.RIGHT, padx=(0, 5))
        
        ttk.Button(buttons_frame, text="Сброс", 
                  command=self.reset_settings).pack(side=tk.LEFT)
        
    def create_interface_tab(self, notebook: ttk.Notebook):
        """Создание вкладки интерфейса"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Интерфейс")
        
        # Создание виджетов с привязкой к настройкам
        self.interface_vars = {}
        
        # Тема
        ttk.Label(frame, text="Тема интерфейса:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.interface_vars['theme'] = tk.StringVar(value=self.settings.interface.theme)
        theme_combo = ttk.Combobox(frame, textvariable=self.interface_vars['theme'],
                                  values=["light", "dark", "auto"], state="readonly")
        theme_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        create_tooltip(theme_combo, "Цветовая схема интерфейса")
        
        # Язык
        ttk.Label(frame, text="Язык:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.interface_vars['language'] = tk.StringVar(value=self.settings.interface.language)
        lang_combo = ttk.Combobox(frame, textvariable=self.interface_vars['language'],
                                 values=["ru", "en", "ja"], state="readonly")
        lang_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Размер шрифта
        ttk.Label(frame, text="Размер шрифта:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.interface_vars['font_size'] = tk.IntVar(value=self.settings.interface.font_size)
        font_spin = ttk.Spinbox(frame, from_=8, to=16, textvariable=self.interface_vars['font_size'], width=10)
        font_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Размер панели инструментов
        ttk.Label(frame, text="Размер панели инструментов:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.interface_vars['toolbar_size'] = tk.StringVar(value=self.settings.interface.toolbar_size)
        toolbar_combo = ttk.Combobox(frame, textvariable=self.interface_vars['toolbar_size'],
                                    values=["small", "medium", "large"], state="readonly")
        toolbar_combo.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Автосохранение
        ttk.Label(frame, text="Интервал автосохранения (сек):").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.interface_vars['auto_save_interval'] = tk.IntVar(value=self.settings.interface.auto_save_interval)
        autosave_spin = ttk.Spinbox(frame, from_=0, to=3600, textvariable=self.interface_vars['auto_save_interval'], width=10)
        autosave_spin.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        create_tooltip(autosave_spin, "0 = отключено")
        
        # Чекбоксы
        self.interface_vars['show_tooltips'] = tk.BooleanVar(value=self.settings.interface.show_tooltips)
        ttk.Checkbutton(frame, text="Показывать подсказки", 
                       variable=self.interface_vars['show_tooltips']).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.interface_vars['confirm_destructive_actions'] = tk.BooleanVar(value=self.settings.interface.confirm_destructive_actions)
        ttk.Checkbutton(frame, text="Подтверждать деструктивные действия", 
                       variable=self.interface_vars['confirm_destructive_actions']).grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
    def create_canvas_tab(self, notebook: ttk.Notebook):
        """Создание вкладки холста"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Рабочая область")
        
        self.canvas_vars = {}
        
        # Масштаб по умолчанию
        ttk.Label(frame, text="Масштаб по умолчанию:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.canvas_vars['default_zoom'] = tk.DoubleVar(value=self.settings.canvas.default_zoom)
        zoom_spin = ttk.Spinbox(frame, from_=0.1, to=5.0, increment=0.1, 
                               textvariable=self.canvas_vars['default_zoom'], width=10)
        zoom_spin.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Размер сетки
        ttk.Label(frame, text="Размер сетки (пикселей):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.canvas_vars['grid_size'] = tk.IntVar(value=self.settings.canvas.grid_size)
        grid_spin = ttk.Spinbox(frame, from_=10, to=200, increment=5, textvariable=self.canvas_vars['grid_size'], width=10)
        grid_spin.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Цвета
        ttk.Label(frame, text="Цвет сетки:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.canvas_vars['grid_color'] = tk.StringVar(value=self.settings.canvas.grid_color)
        grid_color_frame = ttk.Frame(frame)
        grid_color_frame.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        grid_color_btn = tk.Button(grid_color_frame, text="  ", width=3, 
                                  bg=self.settings.canvas.grid_color,
                                  command=lambda: self.choose_color('grid_color', grid_color_btn))
        grid_color_btn.pack(side=tk.LEFT)
        ttk.Label(grid_color_frame, textvariable=self.canvas_vars['grid_color']).pack(side=tk.LEFT, padx=(5, 0))
        
        # Цвет выделения
        ttk.Label(frame, text="Цвет выделения:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.canvas_vars['selection_color'] = tk.StringVar(value=self.settings.canvas.selection_color)
        selection_color_frame = ttk.Frame(frame)
        selection_color_frame.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        selection_color_btn = tk.Button(selection_color_frame, text="  ", width=3,
                                       bg=self.settings.canvas.selection_color,
                                       command=lambda: self.choose_color('selection_color', selection_color_btn))
        selection_color_btn.pack(side=tk.LEFT)
        ttk.Label(selection_color_frame, textvariable=self.canvas_vars['selection_color']).pack(side=tk.LEFT, padx=(5, 0))
        
        # Чекбоксы
        self.canvas_vars['page_shadow'] = tk.BooleanVar(value=self.settings.canvas.page_shadow)
        ttk.Checkbutton(frame, text="Тень страницы", 
                       variable=self.canvas_vars['page_shadow']).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.canvas_vars['smooth_scrolling'] = tk.BooleanVar(value=self.settings.canvas.smooth_scrolling)
        ttk.Checkbutton(frame, text="Плавная прокрутка", 
                       variable=self.canvas_vars['smooth_scrolling']).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.canvas_vars['mouse_wheel_zoom'] = tk.BooleanVar(value=self.settings.canvas.mouse_wheel_zoom)
        ttk.Checkbutton(frame, text="Масштабирование колёсиком мыши", 
                       variable=self.canvas_vars['mouse_wheel_zoom']).grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
    def create_panels_tab(self, notebook: ttk.Notebook):
        """Создание вкладки панелей"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Панели")
        
        self.panels_vars = {}
        
        # Толщина рамки по умолчанию
        ttk.Label(frame, text="Толщина рамки по умолчанию:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.panels_vars['default_border_width'] = tk.IntVar(value=self.settings.panels.default_border_width)
        border_spin = ttk.Spinbox(frame, from_=1, to=10, textvariable=self.panels_vars['default_border_width'], width=10)
        border_spin.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Минимальный размер панели
        ttk.Label(frame, text="Минимальный размер панели:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.panels_vars['min_panel_size'] = tk.IntVar(value=self.settings.panels.min_panel_size)
        min_size_spin = ttk.Spinbox(frame, from_=10, to=100, textvariable=self.panels_vars['min_panel_size'], width=10)
        min_size_spin.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Промежутки
        ttk.Label(frame, text="Горизонтальный промежуток:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.panels_vars['default_gutter_h'] = tk.IntVar(value=self.settings.panels.default_gutter_h)
        gutter_h_spin = ttk.Spinbox(frame, from_=0, to=50, textvariable=self.panels_vars['default_gutter_h'], width=10)
        gutter_h_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(frame, text="Вертикальный промежуток:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.panels_vars['default_gutter_v'] = tk.IntVar(value=self.settings.panels.default_gutter_v)
        gutter_v_spin = ttk.Spinbox(frame, from_=0, to=50, textvariable=self.panels_vars['default_gutter_v'], width=10)
        gutter_v_spin.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Привязка к сетке
        ttk.Label(frame, text="Порог привязки к сетке:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.panels_vars['snap_threshold'] = tk.IntVar(value=self.settings.panels.snap_threshold)
        snap_spin = ttk.Spinbox(frame, from_=1, to=20, textvariable=self.panels_vars['snap_threshold'], width=10)
        snap_spin.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Чекбоксы
        self.panels_vars['snap_to_grid'] = tk.BooleanVar(value=self.settings.panels.snap_to_grid)
        ttk.Checkbutton(frame, text="Привязка к сетке", 
                       variable=self.panels_vars['snap_to_grid']).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.panels_vars['auto_arrange'] = tk.BooleanVar(value=self.settings.panels.auto_arrange)
        ttk.Checkbutton(frame, text="Автоматическое расположение", 
                       variable=self.panels_vars['auto_arrange']).grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.panels_vars['preserve_aspect_ratio'] = tk.BooleanVar(value=self.settings.panels.preserve_aspect_ratio)
        ttk.Checkbutton(frame, text="Сохранять пропорции при изменении размера", 
                       variable=self.panels_vars['preserve_aspect_ratio']).grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
    def create_export_tab(self, notebook: ttk.Notebook):
        """Создание вкладки экспорта"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Экспорт")
        
        self.export_vars = {}
        
        # Формат по умолчанию
        ttk.Label(frame, text="Формат по умолчанию:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.export_vars['default_format'] = tk.StringVar(value=self.settings.export.default_format)
        format_combo = ttk.Combobox(frame, textvariable=self.export_vars['default_format'],
                                   values=["PNG", "JPEG", "PDF", "CBZ"], state="readonly")
        format_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # DPI
        ttk.Label(frame, text="DPI по умолчанию:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.export_vars['default_dpi'] = tk.IntVar(value=self.settings.export.default_dpi)
        dpi_combo = ttk.Combobox(frame, textvariable=self.export_vars['default_dpi'],
                                values=[72, 150, 300, 600], state="readonly")
        dpi_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Качество JPEG
        ttk.Label(frame, text="Качество JPEG:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.export_vars['jpeg_quality'] = tk.IntVar(value=self.settings.export.jpeg_quality)
        quality_spin = ttk.Spinbox(frame, from_=1, to=100, textvariable=self.export_vars['jpeg_quality'], width=10)
        quality_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Размер вылетов
        ttk.Label(frame, text="Размер вылетов (мм):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.export_vars['bleed_size'] = tk.IntVar(value=self.settings.export.bleed_size)
        bleed_spin = ttk.Spinbox(frame, from_=0, to=10, textvariable=self.export_vars['bleed_size'], width=10)
        bleed_spin.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Чекбоксы
        self.export_vars['include_bleed'] = tk.BooleanVar(value=self.settings.export.include_bleed)
        ttk.Checkbutton(frame, text="Включать вылеты", 
                       variable=self.export_vars['include_bleed']).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.export_vars['watermark_enabled'] = tk.BooleanVar(value=self.settings.export.watermark_enabled)
        ttk.Checkbutton(frame, text="Водяной знак", 
                       variable=self.export_vars['watermark_enabled']).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
    def create_performance_tab(self, notebook: ttk.Notebook):
        """Создание вкладки производительности"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Производительность")
        
        self.performance_vars = {}
        
        # Максимум шагов отмены
        ttk.Label(frame, text="Максимум шагов отмены:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.performance_vars['max_undo_steps'] = tk.IntVar(value=self.settings.performance.max_undo_steps)
        undo_spin = ttk.Spinbox(frame, from_=10, to=200, textvariable=self.performance_vars['max_undo_steps'], width=10)
        undo_spin.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Размер кэша изображений
        ttk.Label(frame, text="Размер кэша изображений:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.performance_vars['image_cache_size'] = tk.IntVar(value=self.settings.performance.image_cache_size)
        cache_spin = ttk.Spinbox(frame, from_=10, to=1000, textvariable=self.performance_vars['image_cache_size'], width=10)
        cache_spin.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Лимит памяти
        ttk.Label(frame, text="Лимит памяти (МБ):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.performance_vars['memory_limit'] = tk.IntVar(value=self.settings.performance.memory_limit)
        memory_spin = ttk.Spinbox(frame, from_=256, to=8192, textvariable=self.performance_vars['memory_limit'], width=10)
        memory_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Чекбоксы
        self.performance_vars['preload_thumbnails'] = tk.BooleanVar(value=self.settings.performance.preload_thumbnails)
        ttk.Checkbutton(frame, text="Предзагрузка миниатюр", 
                       variable=self.performance_vars['preload_thumbnails']).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.performance_vars['hardware_acceleration'] = tk.BooleanVar(value=self.settings.performance.hardware_acceleration)
        ttk.Checkbutton(frame, text="Аппаратное ускорение", 
                       variable=self.performance_vars['hardware_acceleration']).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        self.performance_vars['multithread_export'] = tk.BooleanVar(value=self.settings.performance.multithread_export)
        ttk.Checkbutton(frame, text="Многопоточный экспорт", 
                       variable=self.performance_vars['multithread_export']).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
    def create_shortcuts_tab(self, notebook: ttk.Notebook):
        """Создание вкладки горячих клавиш"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Горячие клавиши")
        
        # Создание таблицы горячих клавиш
        shortcuts_frame = ttk.Frame(frame)
        shortcuts_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Заголовки
        ttk.Label(shortcuts_frame, text="Действие", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Label(shortcuts_frame, text="Горячая клавиша", font=("Arial", 9, "bold")).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Создание полей для горячих клавиш
        self.shortcut_vars = {}
        shortcut_names = {
            "new_project": "Новый проект",
            "open_project": "Открыть проект",
            "save_project": "Сохранить",
            "undo": "Отменить",
            "redo": "Повторить",
            "copy": "Копировать",
            "paste": "Вставить",
            "delete": "Удалить",
            "zoom_in": "Увеличить",
            "zoom_out": "Уменьшить",
            "grid_toggle": "Переключить сетку",
            "new_panel": "Новая панель",
            "text_tool": "Инструмент текста",
            "select_tool": "Инструмент выбора"
        }
        
        row = 1
        for key, name in shortcut_names.items():
            ttk.Label(shortcuts_frame, text=name).grid(row=row, column=0, sticky=tk.W, padx=5, pady=2)
            
            self.shortcut_vars[key] = tk.StringVar(value=self.settings.shortcuts.shortcuts.get(key, ""))
            shortcut_entry = ttk.Entry(shortcuts_frame, textvariable=self.shortcut_vars[key], width=20)
            shortcut_entry.grid(row=row, column=1, sticky=tk.W, padx=5, pady=2)
            
            row += 1
            
        # Кнопка сброса горячих клавиш
        ttk.Button(shortcuts_frame, text="Сброс к значениям по умолчанию", 
                  command=self.reset_shortcuts).grid(row=row, column=0, columnspan=2, pady=10)
        
    def choose_color(self, var_name: str, button: tk.Button):
        """Выбор цвета"""
        # Исправлено: добавлена проверка существования переменной
        if not hasattr(self, 'canvas_vars') or var_name not in self.canvas_vars:
            return
            
        current_color = self.canvas_vars[var_name].get()
        color = colorchooser.askcolor(color=current_color, title="Выберите цвет")[1]
        
        if color:
            self.canvas_vars[var_name].set(color)
            button.configure(bg=color)
            
    def reset_shortcuts(self):
        """Сброс горячих клавиш к значениям по умолчанию"""
        default_shortcuts = ShortcutSettings().shortcuts
        
        for key, shortcut in default_shortcuts.items():
            if key in self.shortcut_vars:
                self.shortcut_vars[key].set(shortcut)
                
    def apply_settings(self):
        """Применение настроек"""
        try:
            # Обновление настроек из UI
            self.update_settings_from_ui()
            
            # Сохранение
            self.save_settings()
            
            messagebox.showinfo("Настройки", "Настройки применены и сохранены")
            
        except Exception as e:
            logger.error(f"Ошибка применения настроек: {e}")
            messagebox.showerror("Ошибка", f"Не удалось применить настройки: {e}")
            
    def update_settings_from_ui(self):
        """Обновление настроек из интерфейса"""
        # Интерфейс
        if hasattr(self, 'interface_vars'):
            for key, var in self.interface_vars.items():
                if hasattr(self.settings.interface, key):
                    setattr(self.settings.interface, key, var.get())
                    
        # Холст
        if hasattr(self, 'canvas_vars'):
            for key, var in self.canvas_vars.items():
                if hasattr(self.settings.canvas, key):
                    setattr(self.settings.canvas, key, var.get())
                    
        # Панели
        if hasattr(self, 'panels_vars'):
            for key, var in self.panels_vars.items():
                if hasattr(self.settings.panels, key):
                    setattr(self.settings.panels, key, var.get())
                    
        # Экспорт
        if hasattr(self, 'export_vars'):
            for key, var in self.export_vars.items():
                if hasattr(self.settings.export, key):
                    setattr(self.settings.export, key, var.get())
                    
        # Производительность
        if hasattr(self, 'performance_vars'):
            for key, var in self.performance_vars.items():
                if hasattr(self.settings.performance, key):
                    setattr(self.settings.performance, key, var.get())
                    
        # Горячие клавиши
        if hasattr(self, 'shortcut_vars'):
            for key, var in self.shortcut_vars.items():
                self.settings.shortcuts.shortcuts[key] = var.get()
                
    def ok_settings_and_close(self):
        """Применяет настройки и закрывает диалог."""
        self.apply_settings() # Применить
        self._on_settings_dialog_close()
        
    def cancel_settings(self):
        """Отмена - закрыть без сохранения"""
        self.settings_window.destroy()
        
    def reset_settings(self):
        """Сброс всех настроек"""
        result = messagebox.askyesno("Подтверждение", 
                                   "Сбросить все настройки к значениям по умолчанию?")
        if result:
            self.reset_to_defaults()
            self.settings_window.destroy()
            messagebox.showinfo("Сброс", "Настройки сброшены. Перезапустите программу для применения изменений.")
            
    def export_settings(self, file_path: str) -> bool:
        """Экспорт настроек в файл"""
        try:
            settings_dict = asdict(self.settings)
            return save_json_file(settings_dict, file_path)
        except Exception as e:
            logger.error(f"Ошибка экспорта настроек: {e}")
            return False
            
    def import_settings(self, file_path: str) -> bool:
        """Импорт настроек из файла"""
        try:
            data = load_json_file(file_path)
            if data:
                self.update_settings_from_dict(data)
                self.save_settings()
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка импорта настроек: {e}")
            return False