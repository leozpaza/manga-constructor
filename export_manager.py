#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - менеджер экспорта
Профессиональный экспорт готовых страниц в различные форматы
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import copy
import zipfile
import threading
import time
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import json

# PIL для работы с изображениями
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import io

# Для PDF экспорта
try:
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.pagesizes import letter, A4, legal
    from reportlab.lib.units import mm, inch
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False
    
# Импорт из наших модулей
from utils import (logger, get_temp_dir, safe_filename, 
                   mm_to_pixels, pixels_to_mm, center_window, create_tooltip,
                   PAGE_SIZES, ORIENTATIONS
                   )
from page_constructor import Panel, PanelType

REFERENCE_DPI_FOR_PAGE_SIZES = 300.0

class ExportFormat(Enum):
    """Форматы экспорта"""
    PNG = "PNG"
    JPEG = "JPEG"
    PDF = "PDF"
    CBZ = "CBZ"      # Comic Book Archive
    CBR = "CBR"      # Comic Book RAR (пока не поддерживается)
    TIFF = "TIFF"
    BMP = "BMP"
    WEBP = "WEBP"


class ExportQuality(Enum):
    """Качество экспорта"""
    WEB = "web"           # 72 DPI, оптимизация для веба
    PRINT = "print"       # 300 DPI, для печати
    HIGH = "high"         # 600 DPI, высокое качество
    CUSTOM = "custom"     # Пользовательские настройки


@dataclass
class ExportSettings:
    """Настройки экспорта"""
    format: ExportFormat = ExportFormat.PNG
    quality: ExportQuality = ExportQuality.PRINT
    dpi: int = 300
    jpeg_quality: int = 95
    png_compression: int = 6
    
    # Размеры и поля
    include_bleed: bool = False
    bleed_size: float = 3.0  # мм
    include_crop_marks: bool = False
    include_registration_marks: bool = False
    
    # Водяной знак
    watermark_enabled: bool = False
    watermark_text: str = ""
    watermark_position: str = "bottom_right"  # bottom_right, center, etc.
    watermark_opacity: float = 0.3
    watermark_font_size: int = 12
    watermark_color: str = "#888888"
    
    # Настройки цвета
    color_profile: str = "sRGB"  # sRGB, Adobe RGB, CMYK
    gamma_correction: float = 1.0
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    
    # Дополнительные опции
    background_color: str = "#FFFFFF"
    transparent_background: bool = False
    anti_aliasing: bool = True
    embed_fonts: bool = True
    
    # Пакетный экспорт
    output_path: str = ""
    filename_template: str = "page_{number:03d}"
    include_metadata: bool = True

    export_page_size_name: str = "Текущий холст" # Новое значение по умолчанию
    export_orientation_name: str = "Текущий холст" # Новое значение по умолчанию
    # Для пользовательского размера ЭКСПОРТА (если отличается от холста)
    custom_export_width_px: Optional[int] = None
    custom_export_height_px: Optional[int] = None


@dataclass
class ExportProgress:
    """Прогресс экспорта"""
    current_page: int = 0
    total_pages: int = 0
    current_operation: str = ""
    completed: bool = False
    error: Optional[str] = None
    start_time: float = 0
    estimated_time: float = 0


class ExportManager:
    """Менеджер экспорта страниц манги"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        
        # Настройки экспорта по умолчанию
        self.settings = ExportSettings()
        
        # Прогресс экспорта
        self.progress = ExportProgress()
        
        # UI элементы
        self.export_window = None
        self.progress_window = None
        
        # Многопоточность
        self.export_thread = None
        self.cancel_export = False
        
        # Кэш шрифтов
        self.fonts_cache: Dict[str, ImageFont.FreeTypeFont] = {}
        
    def show_export_dialog(self):
        """Показ диалога экспорта"""
        if self.export_window and self.export_window.winfo_exists():
            self.export_window.lift()
            return
            
        self.export_window = tk.Toplevel(self.app.root)
        self.export_window.title("Экспорт страницы")
        self.export_window.geometry("500x700")
        self.export_window.resizable(False, False)

        self.export_window.transient(self.app.root)
        self.export_window.grab_set()
        
        center_window(self.export_window, self.app.root)
        
        self.setup_export_ui()

        self.export_window.protocol("WM_DELETE_WINDOW", self._on_export_dialog_close)

    def _on_export_dialog_close(self):
        """Обработчик закрытия диалога экспорта."""
        if self.export_window and self.export_window.winfo_exists():
            self.export_window.grab_release() # Важно освободить захват
            self.export_window.destroy()
            self.export_window = None
        
    def setup_export_ui(self):
        """Настройка интерфейса экспорта"""
        # Главный контейнер
        main_frame = ttk.Frame(self.export_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Notebook для настроек
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Создание вкладок (эти методы создадут self.xxx_var атрибуты)
        self.create_basic_tab(notebook)
        self.create_quality_tab(notebook)
        self.create_layout_tab(notebook)
        self.create_watermark_tab(notebook)
        self.create_advanced_tab(notebook)
        
        # Предпросмотр
        preview_frame = ttk.LabelFrame(main_frame, text="Предпросмотр")
        preview_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Элемент self.preview_canvas СОЗДАЕТСЯ ЗДЕСЬ
        self.preview_canvas = tk.Canvas(preview_frame, width=200, height=150, bg="white")
        self.preview_canvas.pack(padx=10, pady=10)
        
        # Информация об экспорте
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=tk.X, pady=(5, 0))
        
        # Элемент self.info_label СОЗДАЕТСЯ ЗДЕСЬ
        self.info_label = ttk.Label(info_frame, text="", font=("Arial", 8))
        self.info_label.pack()
        
        # Кнопки
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(buttons_frame, text="Экспорт", 
                command=self.start_export).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(buttons_frame, text="Отмена", 
                command=self._on_export_dialog_close).pack(side=tk.RIGHT)
        
        ttk.Button(buttons_frame, text="Сохранить настройки", 
                  command=self.save_export_settings).pack(side=tk.LEFT)
        ttk.Button(buttons_frame, text="Загрузить настройки", 
                  command=self.load_export_settings).pack(side=tk.LEFT, padx=(5, 0))
        
        # Обновление предпросмотра
        self.on_export_settings_change()

    def on_export_settings_change(self, event=None):
        # Показать/скрыть поля для пользовательского размера экспорта
        if hasattr(self, 'export_page_size_var') and hasattr(self, 'export_custom_size_frame'):
            if self.export_page_size_var.get() == "Пользовательский":
                # Отображаем фрейм пользовательского размера
                self.export_custom_size_frame.grid(row=self.current_custom_size_row_idx, 
                                                    column=0, columnspan=3, 
                                                    sticky=tk.W, padx=5, pady=2)
                # Если поля пустые или содержат значения из предыдущего пресета, можно заполнить их
                # значениями по умолчанию для "Пользовательский" или текущего холста
                if not self.export_custom_width_var.get() or not self.export_custom_height_var.get():
                    # Предлагаем размеры B5 при 300 DPI по умолчанию для пользовательского режима
                    default_w, default_h = PAGE_SIZES["B5"] 
                    self.export_custom_width_var.set(str(default_w))
                    self.export_custom_height_var.set(str(default_h))

            else:
                # Скрываем фрейм пользовательского размера
                self.export_custom_size_frame.grid_remove()

        # 2. Логика для качества "custom" (как было)
        if hasattr(self, 'quality_var') and self.quality_var.get() != ExportQuality.CUSTOM.value:
            quality_val = self.quality_var.get()
            dpi_map = {
                ExportQuality.WEB.value: 72,
                ExportQuality.PRINT.value: 300,
                ExportQuality.HIGH.value: 600
            }
            if quality_val in dpi_map and hasattr(self, 'dpi_var'):
                self.dpi_var.set(dpi_map[quality_val])

        # 3. Обновление UI
        self.update_export_preview()
        self.update_export_info()
        
    def create_basic_tab(self, notebook: ttk.Notebook):
        """Создание основной вкладки с настройками экспорта."""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Основные")

        row_idx = 0 # Единый индекс текущей строки для grid

        # Формат экспорта
        ttk.Label(frame, text="Формат:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        self.format_var = tk.StringVar(value=self.settings.format.value)
        format_combo = ttk.Combobox(frame, textvariable=self.format_var,
                                   values=[fmt.value for fmt in ExportFormat],
                                   state="readonly", width=15)
        format_combo.grid(row=row_idx, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        format_combo.bind('<<ComboboxSelected>>', self.on_export_settings_change)
        create_tooltip(format_combo, "Выберите формат выходного файла")
        row_idx += 1
        
        # Качество экспорта (пресет)
        ttk.Label(frame, text="Качество (пресет):").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        self.quality_var = tk.StringVar(value=self.settings.quality.value)
        quality_combo = ttk.Combobox(frame, textvariable=self.quality_var,
                                    values=[q.value for q in ExportQuality],
                                    state="readonly", width=15)
        quality_combo.grid(row=row_idx, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        quality_combo.bind('<<ComboboxSelected>>', self.on_export_settings_change)
        row_idx += 1

        # -- Размер страницы для экспорта --
        ttk.Label(frame, text="Размер страницы:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        self.export_page_size_var = tk.StringVar(value=self.settings.export_page_size_name)
        export_page_size_options = ["Текущий холст", "Пользовательский"] + sorted(list(PAGE_SIZES.keys()))
        export_page_size_combo = ttk.Combobox(frame, textvariable=self.export_page_size_var,
                                        values=export_page_size_options,
                                        state="readonly", width=15)
        export_page_size_combo.grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=5) # Убрал columnspan=2
        export_page_size_combo.bind('<<ComboboxSelected>>', self.on_export_settings_change)
        row_idx += 1

        # -- Ориентация для экспорта --
        ttk.Label(frame, text="Ориентация:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        self.export_orientation_var = tk.StringVar(value=self.settings.export_orientation_name)
        export_orientation_options = ["Текущий холст"] + list(ORIENTATIONS.keys())
        export_orientation_combo = ttk.Combobox(frame, textvariable=self.export_orientation_var,
                                            values=export_orientation_options,
                                            state="readonly", width=15)
        export_orientation_combo.grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=5) # Убрал columnspan=2
        export_orientation_combo.bind('<<ComboboxSelected>>', self.on_export_settings_change)
        row_idx += 1
        
        # -- Пользовательские размеры для экспорта (появляются, если выбран "Пользовательский" размер) --
        self.export_custom_size_frame = ttk.Frame(frame)
        # Фрейм будет добавлен в grid в on_export_settings_change
        
        ttk.Label(self.export_custom_size_frame, text="Шир. (px):").grid(row=0, column=0, padx=2, pady=2)
        self.export_custom_width_var = tk.StringVar(value=str(self.settings.custom_export_width_px or ""))
        self.export_custom_width_entry = ttk.Entry(self.export_custom_size_frame, textvariable=self.export_custom_width_var, width=7)
        self.export_custom_width_entry.grid(row=0, column=1, padx=2, pady=2)
        self.export_custom_width_entry.bind("<FocusOut>", self.on_export_settings_change)
        self.export_custom_width_entry.bind("<Return>", self.on_export_settings_change)

        ttk.Label(self.export_custom_size_frame, text="Выс. (px):").grid(row=0, column=2, padx=2, pady=2)
        self.export_custom_height_var = tk.StringVar(value=str(self.settings.custom_export_height_px or ""))
        self.export_custom_height_entry = ttk.Entry(self.export_custom_size_frame, textvariable=self.export_custom_height_var, width=7)
        self.export_custom_height_entry.grid(row=0, column=3, padx=2, pady=2)
        self.export_custom_height_entry.bind("<FocusOut>", self.on_export_settings_change)
        self.export_custom_height_entry.bind("<Return>", self.on_export_settings_change)

        self.current_custom_size_row_idx = row_idx # Сохраняем индекс строки для грида фрейма
        row_idx += 1 # Эта строка будет занята, если export_custom_size_frame отобразится

        # -- DPI --
        ttk.Label(frame, text="DPI:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        self.dpi_var = tk.IntVar(value=self.settings.dpi)
        dpi_combo = ttk.Combobox(frame, textvariable=self.dpi_var,
                                values=[72, 150, 300, 600, 1200], width=15)
        dpi_combo.grid(row=row_idx, column=1, sticky=tk.W, padx=5, pady=5) # Убрал columnspan=2
        dpi_combo.bind('<<ComboboxSelected>>', self.on_export_settings_change)
        dpi_combo.bind("<FocusOut>", self.on_export_settings_change)
        row_idx += 1
        
        # Путь сохранения
        ttk.Label(frame, text="Сохранить в:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        path_frame = ttk.Frame(frame)
        path_frame.grid(row=row_idx, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        self.output_path_var = tk.StringVar(value=self.settings.output_path or os.path.expanduser("~"))
        path_entry = ttk.Entry(path_frame, textvariable=self.output_path_var, width=30)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(path_frame, text="Обзор...", 
                  command=self.browse_output_path).pack(side=tk.RIGHT, padx=(5, 0))
        row_idx += 1
        
        # Шаблон имени файла
        ttk.Label(frame, text="Имя файла:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        self.filename_var = tk.StringVar(value=self.settings.filename_template)
        filename_entry = ttk.Entry(frame, textvariable=self.filename_var, width=20)
        filename_entry.grid(row=row_idx, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        create_tooltip(filename_entry, "Используйте {number} для номера страницы (если применимо)")
        row_idx += 1
        
        # Цвет фона
        ttk.Label(frame, text="Цвет фона:").grid(row=row_idx, column=0, sticky=tk.W, padx=5, pady=5)
        bg_frame = ttk.Frame(frame)
        bg_frame.grid(row=row_idx, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        self.bg_color_var = tk.StringVar(value=self.settings.background_color)
        self.bg_color_button = tk.Button(bg_frame, text="  ", width=3, relief=tk.GROOVE,
                                        bg=self.settings.background_color,
                                        command=self.choose_background_color)
        self.bg_color_button.pack(side=tk.LEFT)
        self.transparent_bg_var = tk.BooleanVar(value=self.settings.transparent_background)
        self.transparent_bg_check = ttk.Checkbutton(bg_frame, text="Прозрачный (PNG)", 
                                                   variable=self.transparent_bg_var,
                                                   command=self.on_export_settings_change)
        self.transparent_bg_check.pack(side=tk.LEFT, padx=(10, 0))
        row_idx += 1
        
    def create_quality_tab(self, notebook: ttk.Notebook):
        """Создание вкладки качества"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Качество")
        
        # JPEG качество
        ttk.Label(frame, text="JPEG качество:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.jpeg_quality_var = tk.IntVar(value=self.settings.jpeg_quality)
        jpeg_scale = ttk.Scale(frame, from_=1, to=100, variable=self.jpeg_quality_var, 
                              orient=tk.HORIZONTAL, length=200)
        jpeg_scale.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        self.jpeg_quality_label = ttk.Label(frame, text=f"{self.settings.jpeg_quality}%")
        self.jpeg_quality_label.grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        
        jpeg_scale.configure(command=self.update_jpeg_quality_label)
        
        # PNG сжатие
        ttk.Label(frame, text="PNG сжатие:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.png_compression_var = tk.IntVar(value=self.settings.png_compression)
        png_scale = ttk.Scale(frame, from_=0, to=9, variable=self.png_compression_var,
                             orient=tk.HORIZONTAL, length=200)
        png_scale.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Коррекция цвета
        ttk.Label(frame, text="Яркость:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.brightness_var = tk.DoubleVar(value=self.settings.brightness)
        brightness_scale = ttk.Scale(frame, from_=-1.0, to=1.0, variable=self.brightness_var,
                                    orient=tk.HORIZONTAL, length=200)
        brightness_scale.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(frame, text="Контрастность:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.contrast_var = tk.DoubleVar(value=self.settings.contrast)
        contrast_scale = ttk.Scale(frame, from_=-1.0, to=1.0, variable=self.contrast_var,
                                  orient=tk.HORIZONTAL, length=200)
        contrast_scale.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(frame, text="Насыщенность:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.saturation_var = tk.DoubleVar(value=self.settings.saturation)
        saturation_scale = ttk.Scale(frame, from_=-1.0, to=1.0, variable=self.saturation_var,
                                    orient=tk.HORIZONTAL, length=200)
        saturation_scale.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Дополнительные опции
        self.anti_aliasing_var = tk.BooleanVar(value=self.settings.anti_aliasing)
        ttk.Checkbutton(frame, text="Сглаживание", 
                       variable=self.anti_aliasing_var).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
    def create_layout_tab(self, notebook: ttk.Notebook):
        """Создание вкладки макета"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Макет")
        
        # Вылеты
        self.include_bleed_var = tk.BooleanVar(value=self.settings.include_bleed)
        ttk.Checkbutton(frame, text="Включить вылеты", 
                       variable=self.include_bleed_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        ttk.Label(frame, text="Размер вылетов (мм):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.bleed_size_var = tk.DoubleVar(value=self.settings.bleed_size)
        bleed_spin = ttk.Spinbox(frame, from_=0, to=10, increment=0.5, 
                                textvariable=self.bleed_size_var, width=10)
        bleed_spin.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Метки обрезки
        self.crop_marks_var = tk.BooleanVar(value=self.settings.include_crop_marks)
        ttk.Checkbutton(frame, text="Метки обрезки", 
                       variable=self.crop_marks_var).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # Приводочные метки
        self.reg_marks_var = tk.BooleanVar(value=self.settings.include_registration_marks)
        ttk.Checkbutton(frame, text="Приводочные метки", 
                       variable=self.reg_marks_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # Цветовой профиль
        ttk.Label(frame, text="Цветовой профиль:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.color_profile_var = tk.StringVar(value=self.settings.color_profile)
        profile_combo = ttk.Combobox(frame, textvariable=self.color_profile_var,
                                    values=["sRGB", "Adobe RGB", "CMYK"], 
                                    state="readonly", width=15)
        profile_combo.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
    def create_watermark_tab(self, notebook: ttk.Notebook):
        """Создание вкладки водяного знака"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Водяной знак")
        
        # Включение водяного знака
        self.watermark_enabled_var = tk.BooleanVar(value=self.settings.watermark_enabled)
        ttk.Checkbutton(frame, text="Добавить водяной знак", 
                       variable=self.watermark_enabled_var,
                       command=self.toggle_watermark).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # Текст водяного знака
        ttk.Label(frame, text="Текст:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.watermark_text_var = tk.StringVar(value=self.settings.watermark_text)
        watermark_entry = ttk.Entry(frame, textvariable=self.watermark_text_var, width=30)
        watermark_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Позиция
        ttk.Label(frame, text="Позиция:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.watermark_position_var = tk.StringVar(value=self.settings.watermark_position)
        position_combo = ttk.Combobox(frame, textvariable=self.watermark_position_var,
                                     values=["top_left", "top_right", "bottom_left", "bottom_right", "center"],
                                     state="readonly", width=15)
        position_combo.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Прозрачность
        ttk.Label(frame, text="Прозрачность:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.watermark_opacity_var = tk.DoubleVar(value=self.settings.watermark_opacity)
        opacity_scale = ttk.Scale(frame, from_=0.1, to=1.0, variable=self.watermark_opacity_var,
                                 orient=tk.HORIZONTAL, length=200)
        opacity_scale.grid(row=3, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Размер шрифта
        ttk.Label(frame, text="Размер шрифта:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.watermark_font_size_var = tk.IntVar(value=self.settings.watermark_font_size)
        font_spin = ttk.Spinbox(frame, from_=8, to=72, textvariable=self.watermark_font_size_var, width=10)
        font_spin.grid(row=4, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Цвет
        ttk.Label(frame, text="Цвет:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.watermark_color_var = tk.StringVar(value=self.settings.watermark_color)
        self.watermark_color_button = tk.Button(frame, text="  ", width=3,
                                               bg=self.settings.watermark_color,
                                               command=self.choose_watermark_color)
        self.watermark_color_button.grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)
        
    def create_advanced_tab(self, notebook: ttk.Notebook):
        """Создание расширенной вкладки"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text="Расширенные")
        
        # Включение метаданных
        self.include_metadata_var = tk.BooleanVar(value=self.settings.include_metadata)
        ttk.Checkbutton(frame, text="Включить метаданные", 
                       variable=self.include_metadata_var).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # Встраивание шрифтов (для PDF)
        self.embed_fonts_var = tk.BooleanVar(value=self.settings.embed_fonts)
        ttk.Checkbutton(frame, text="Встраивать шрифты (PDF)", 
                       variable=self.embed_fonts_var).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        # Гамма-коррекция
        ttk.Label(frame, text="Гамма-коррекция:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.gamma_var = tk.DoubleVar(value=self.settings.gamma_correction)
        gamma_scale = ttk.Scale(frame, from_=0.5, to=2.0, variable=self.gamma_var,
                               orient=tk.HORIZONTAL, length=200)
        gamma_scale.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Пакетные настройки
        ttk.Label(frame, text="Пакетные операции:", font=("Arial", 9, "bold")).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(10, 5))
        
        # Экспорт всех страниц (пока заглушка)
        ttk.Button(frame, text="Экспорт всех страниц проекта", 
                  command=self.export_all_pages).grid(row=4, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=2)
        
        # Создание CBZ архива
        ttk.Button(frame, text="Создать CBZ архив", 
                  command=self.create_cbz_archive).grid(row=5, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=2)
        
    def update_jpeg_quality_label(self, value):
        """Обновление метки качества JPEG"""
        self.jpeg_quality_label.config(text=f"{int(float(value))}%")
        
    def toggle_watermark(self):
        """Переключение водяного знака"""
        # Можно добавить включение/отключение виджетов водяного знака
        pass
        
    def on_format_change(self, event=None):
        """Обработчик изменения формата"""
        self.update_export_preview()
        self.update_export_info()
        
    def on_quality_change(self, event=None):
        """Обработчик изменения качества"""
        quality = self.quality_var.get()
        
        # Автоматическое изменение DPI в зависимости от качества
        quality_dpi = {
            "web": 72,
            "print": 300,
            "high": 600,
            "custom": self.dpi_var.get()
        }
        
        if quality != "custom":
            self.dpi_var.set(quality_dpi[quality])
            
        self.update_export_preview()
        self.update_export_info()
        
    def choose_background_color(self):
        """Выбор цвета фона"""
        from tkinter import colorchooser
        color = colorchooser.askcolor(color=self.bg_color_var.get(), title="Выберите цвет фона")[1]
        if color:
            self.bg_color_var.set(color)
            self.bg_color_button.configure(bg=color)
            
    def choose_watermark_color(self):
        """Выбор цвета водяного знака"""
        from tkinter import colorchooser
        color = colorchooser.askcolor(color=self.watermark_color_var.get(), title="Выберите цвет водяного знака")[1]
        if color:
            self.watermark_color_var.set(color)
            self.watermark_color_button.configure(bg=color)
            
    def browse_output_path(self):
        """Выбор пути сохранения"""
        initial_dir = self.output_path_var.get() or os.path.expanduser("~")
        path = filedialog.askdirectory(
            title="Выберите папку для сохранения", 
            initialdir=initial_dir,
            parent=self.export_window
        )
        if path:
            self.output_path_var.set(path)
            
    def update_export_preview(self):
        self.preview_canvas.delete("all")

        # Получаем текущие размеры холста из PageConstructor
        # Эти размеры УЖЕ учитывают выбранный размер и ориентацию в главном UI
        page_width_units = self.app.page_constructor.page_width
        page_height_units = self.app.page_constructor.page_height

        if page_width_units <= 0 or page_height_units <= 0: # Предотвращение деления на ноль
            return

        page_aspect_ratio = page_width_units / page_height_units

        # Размеры самого виджета Canvas для предпросмотра
        preview_widget_width = self.preview_canvas.winfo_width()
        preview_widget_height = self.preview_canvas.winfo_height()
        
        # Если виджет еще не отрисован, используем заданные размеры
        if preview_widget_width <= 1: preview_widget_width = 200
        if preview_widget_height <= 1: preview_widget_height = 150
            
        padding = 10
        target_w_area = preview_widget_width - 2 * padding
        target_h_area = preview_widget_height - 2 * padding

        if target_w_area <= 0 or target_h_area <= 0: return


        # Рассчитываем размеры превью с сохранением пропорций
        scaled_w = target_w_area
        scaled_h = scaled_w / page_aspect_ratio

        if scaled_h > target_h_area:
            scaled_h = target_h_area
            scaled_w = scaled_h * page_aspect_ratio
        
        # Центрируем превью на холсте виджета
        offset_x = padding + (target_w_area - scaled_w) / 2
        offset_y = padding + (target_h_area - scaled_h) / 2

        # Рисуем фон страницы превью
        self.preview_canvas.create_rectangle(
            offset_x, offset_y,
            offset_x + scaled_w, offset_y + scaled_h,
            fill="white", outline="black", width=1
        )

        # Рисуем панели (масштабированные)
        panels = self.app.page_constructor.panels
        for panel in panels[:10]:  # Ограничиваем количество для производительности превью
            if not panel.visible: continue

            # Координаты и размеры панели относительно страницы (0.0 до 1.0)
            # Но у нас panel.x и panel.width в "page units", а не в %
            
            prev_panel_x = offset_x + (panel.x / page_width_units) * scaled_w
            prev_panel_y = offset_y + (panel.y / page_height_units) * scaled_h
            prev_panel_w = (panel.width / page_width_units) * scaled_w
            prev_panel_h = (panel.height / page_height_units) * scaled_h
            
            # Ограничение минимального размера для отрисовки
            if prev_panel_w > 0.5 and prev_panel_h > 0.5:
                self.preview_canvas.create_rectangle(
                    prev_panel_x, prev_panel_y,
                    prev_panel_x + prev_panel_w, prev_panel_y + prev_panel_h,
                    fill="#F0F0F0", outline="#666666", width=0.5 # Тоньше линии для превью
                )

        # Показ водяного знака (если включен в UI экспорта)
        # Нужно получить watermark_enabled_var и watermark_text_var из UI экспорта
        # Это немного сложно, т.к. update_export_preview может вызываться до того, как переменные UI созданы.
        # Добавим проверку на существование.
        watermark_text_to_show = ""
        if hasattr(self, 'watermark_enabled_var') and self.watermark_enabled_var.get():
            if hasattr(self, 'watermark_text_var') and self.watermark_text_var.get():
                watermark_text_to_show = self.watermark_text_var.get()[:10] + "..."
        
        if watermark_text_to_show:
            self.preview_canvas.create_text(
                offset_x + scaled_w - 2, offset_y + scaled_h - 2, # Низ-право превью
                text=watermark_text_to_show,
                font=("Arial", 6), fill="#CCCCCC", anchor="se"
            )
        
        # Также обновим информацию о размере под превью
        self.update_export_info()
                                          
    def update_export_info(self):
        # Если переменные еще не созданы (например, при первом открытии), выходим
        if not all(hasattr(self, attr) for attr in ['dpi_var', 'export_page_size_var', 'export_orientation_var']):
            self.info_label.config(text="Загрузка настроек...")
            return

        format_name = self.format_var.get()
        target_dpi = float(self.dpi_var.get())
        export_page_size_key = self.export_page_size_var.get()
        export_orientation_key = self.export_orientation_var.get()
        
        pixel_width, pixel_height = 0, 0

        if export_page_size_key == "Текущий холст":
            # Размеры холста PageConstructor уже в пикселях при REFERENCE_DPI_FOR_PAGE_SIZES (300 DPI)
            canvas_w_at_ref_dpi = self.app.page_constructor.page_width
            canvas_h_at_ref_dpi = self.app.page_constructor.page_height
            
            pixel_width = int(canvas_w_at_ref_dpi * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))
            pixel_height = int(canvas_h_at_ref_dpi * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))

        elif export_page_size_key == "Пользовательский":
            # Используем прямое значение из полей ввода (если валидно)
            try:
                pixel_width = int(self.export_custom_width_var.get())
                pixel_height = int(self.export_custom_height_var.get())
            except ValueError:
                # Если некорректный ввод, покажем сообщение об ошибке
                self.info_label.config(text="Неверные пользовательские размеры (px).")
                return # Выходим, чтобы избежать дальнейших ошибок

        else: # Выбран один из стандартных размеров (A4, B5, Letter и т.д.)
            base_w_at_ref_dpi, base_h_at_ref_dpi = PAGE_SIZES.get(export_page_size_key, PAGE_SIZES["B5"])
            
            # Определяем ориентацию для выбранного стандартного размера
            orientation_val_str = export_orientation_key
            if orientation_val_str == "Текущий холст": # Если ориентация наследуется, берем с холста
                if self.app.page_constructor.page_width > self.app.page_constructor.page_height:
                    orientation_val = "landscape"
                else:
                    orientation_val = "portrait"
            else:
                orientation_val = ORIENTATIONS.get(orientation_val_str, "portrait")

            if orientation_val == "landscape":
                base_w_final, base_h_final = base_h_at_ref_dpi, base_w_at_ref_dpi
            else: # portrait
                base_w_final, base_h_final = base_w_at_ref_dpi, base_h_at_ref_dpi
            
            pixel_width = int(base_w_final * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))
            pixel_height = int(base_h_final * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))

        if pixel_width <=0 or pixel_height <=0:
            self.info_label.config(text="Неверные размеры после расчетов.")
            return

        # Примерный размер файла (остается как было)
        estimated_size_kb = 0
        if format_name == ExportFormat.PNG.value:
            estimated_size_kb = (pixel_width * pixel_height * 3) // 1024 
        elif format_name == ExportFormat.JPEG.value:
            quality_factor = (self.jpeg_quality_var.get() if hasattr(self, 'jpeg_quality_var') else 95) / 100.0
            estimated_size_kb = int((pixel_width * pixel_height * 3 * quality_factor) / 1024.0)
        elif format_name == ExportFormat.PDF.value: # PDF сложно оценить так
            estimated_size_kb = (pixel_width * pixel_height * 0.5) // 1024 # Грубая оценка
        else: # Для других форматов или по умолчанию
            estimated_size_kb = (pixel_width * pixel_height * 1) // 1024 
            
        info_text = f"Размер: {pixel_width}×{pixel_height} пикс. ({target_dpi} DPI) | Файл: ~{max(1,estimated_size_kb)} КБ ({format_name})"
        self.info_label.config(text=info_text)
        
    def collect_export_settings(self) -> ExportSettings:
        """Сбор настроек экспорта из UI"""
        settings = ExportSettings(
            format=ExportFormat(self.format_var.get()),
            quality=ExportQuality(self.quality_var.get()),
            dpi=self.dpi_var.get(),
            jpeg_quality=self.jpeg_quality_var.get(),
            png_compression=self.png_compression_var.get(),
            
            include_bleed=self.include_bleed_var.get(),
            bleed_size=self.bleed_size_var.get(),
            include_crop_marks=self.crop_marks_var.get(),
            include_registration_marks=self.reg_marks_var.get(),
            
            watermark_enabled=self.watermark_enabled_var.get(),
            watermark_text=self.watermark_text_var.get(),
            watermark_position=self.watermark_position_var.get(),
            watermark_opacity=self.watermark_opacity_var.get(),
            watermark_font_size=self.watermark_font_size_var.get(),
            watermark_color=self.watermark_color_var.get(),
            
            color_profile=self.color_profile_var.get(),
            gamma_correction=self.gamma_var.get(),
            brightness=self.brightness_var.get(),
            contrast=self.contrast_var.get(),
            saturation=self.saturation_var.get(),
            
            background_color=self.bg_color_var.get(),
            transparent_background=self.transparent_bg_var.get(),
            anti_aliasing=self.anti_aliasing_var.get(),
            embed_fonts=self.embed_fonts_var.get(),
            
            output_path=self.output_path_var.get(),
            filename_template=self.filename_var.get(),
            include_metadata=self.include_metadata_var.get(),
            
            # >>> НОВЫЕ ПОЛЯ
            export_page_size_name=self.export_page_size_var.get(),
            export_orientation_name=self.export_orientation_var.get()
        )

        # Сохраняем пользовательские пиксельные размеры, если выбран этот режим
        if settings.export_page_size_name == "Пользовательский":
            try:
                settings.custom_export_width_px = int(self.export_custom_width_var.get())
                settings.custom_export_height_px = int(self.export_custom_height_var.get())
            except ValueError:
                settings.custom_export_width_px = None
                settings.custom_export_height_px = None
        # <<< КОНЕЦ НОВЫХ ПОЛЕЙ

        return settings
        
    def start_export(self):
        """Начало экспорта"""
        # Проверка данных
        if not self.app.page_constructor.panels:
            messagebox.showwarning("Предупреждение", "Нет панелей для экспорта")
            return
            
        if not self.output_path_var.get():
            messagebox.showwarning("Предупреждение", "Выберите папку для сохранения")
            return
            
        # Сбор настроек
        self.settings = self.collect_export_settings()
        
        # Закрытие окна настроек
        self._on_export_dialog_close()
        
        # Запуск экспорта в отдельном потоке
        self.cancel_export = False
        self.export_thread = threading.Thread(target=self.export_worker, daemon=True)
        self.export_thread.start()
        
        # Показ окна прогресса
        self.show_progress_window()
        
    def export_worker(self):
        """Рабочий поток экспорта"""
        try:
            self.progress.start_time = time.time()
            self.progress.current_page = 0
            self.progress.total_pages = 1  # Пока экспортируем только текущую страницу
            self.progress.completed = False
            self.progress.error = None
            
            # Экспорт страницы
            success = self.export_current_page()
            
            if success and not self.cancel_export:
                self.progress.completed = True
                self.progress.current_operation = "Экспорт завершён"
            elif self.cancel_export:
                self.progress.error = "Экспорт отменён пользователем"
            else:
                self.progress.error = "Ошибка экспорта"
                
        except Exception as e:
            logger.error(f"Ошибка в потоке экспорта: {e}")
            self.progress.error = str(e)
            
    def export_current_page(self) -> bool:
        """Экспорт текущей страницы"""
        try:
            self.progress.current_operation = "Подготовка экспорта..."
            
            # Создание изображения страницы
            page_image = self.render_page_to_image()
            
            if not page_image:
                return False
                
            self.progress.current_operation = "Применение эффектов..."
            
            # Применение настроек
            processed_image = self.apply_export_settings(page_image)
            
            self.progress.current_operation = "Сохранение файла..."
            
            # Сохранение файла
            output_path = self.get_output_filename()
            success = self.save_image(processed_image, output_path)
            
            if success:
                self.progress.current_page = 1
                logger.info(f"Страница экспортирована: {output_path}")
                
            return success
            
        except Exception as e:
            logger.error(f"Ошибка экспорта страницы: {e}")
            return False
            
    def render_page_to_image(self) -> Optional[Image.Image]:
        """
        Рендеринг страницы в изображение, используя настройки экспорта.
        Вычисляет конечные пиксельные размеры на основе выбранного формата,
        ориентации и DPI, затем масштабирует панели PageConstructor.
        """
        try:
            # --- 1. Определяем конечные пиксельные размеры области страницы (без вылетов) ---
            target_dpi = float(self.settings.dpi) # DPI для конечного изображения
            export_page_width_px, export_page_height_px = 0, 0 # Размеры страницы без вылетов

            if self.settings.export_page_size_name == "Текущий холст":
                # Берем размеры текущего холста PageConstructor.
                # page_constructor.page_width/height хранятся как пиксели при REFERENCE_DPI_FOR_PAGE_SIZES (300 DPI).
                canvas_w_at_ref_dpi = self.app.page_constructor.page_width
                canvas_h_at_ref_dpi = self.app.page_constructor.page_height
                
                export_page_width_px = int(canvas_w_at_ref_dpi * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))
                export_page_height_px = int(canvas_h_at_ref_dpi * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))

            elif self.settings.export_page_size_name == "Пользовательский":
                # Пользователь задал точные пиксельные размеры. Используем их напрямую.
                if self.settings.custom_export_width_px is not None and self.settings.custom_export_height_px is not None:
                    export_page_width_px = self.settings.custom_export_width_px
                    export_page_height_px = self.settings.custom_export_height_px
                else: 
                    # Если пользовательские поля пусты или некорректны, используем B5 по умолчанию
                    logger.warning("Пользовательский размер не задан или некорректен, использую B5 при текущем DPI.")
                    base_w, base_h = PAGE_SIZES["B5"] # Эти значения при 300 DPI
                    export_page_width_px = int(base_w * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))
                    export_page_height_px = int(base_h * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))

            else: # Выбран один из стандартных размеров (A4, B5, Letter и т.д.)
                # PAGE_SIZES содержат пиксели при REFERENCE_DPI_FOR_PAGE_SIZES (300 DPI).
                base_w_at_ref_dpi, base_h_at_ref_dpi = PAGE_SIZES.get(
                    self.settings.export_page_size_name, PAGE_SIZES["B5"]
                )
                
                # Определяем ориентацию. Если выбрано "Текущий холст", наследуем от главного холста.
                # Иначе - используем выбранную в диалоге экспорта.
                orientation_val_str = self.settings.export_orientation_name
                if orientation_val_str == "Текущий холст":
                    # Определяем ориентацию холста PageConstructor по его ширине/высоте
                    if self.app.page_constructor.page_width > self.app.page_constructor.page_height:
                        orientation_val = "landscape"
                    else:
                        orientation_val = "portrait"
                else:
                    orientation_val = ORIENTATIONS.get(orientation_val_str, "portrait") # Fallback на портретную

                # Применяем ориентацию к базовым размерам 
                if orientation_val == "landscape":
                    base_w_final_at_ref_dpi, base_h_final_at_ref_dpi = base_h_at_ref_dpi, base_w_at_ref_dpi
                else: # portrait
                    base_w_final_at_ref_dpi, base_h_final_at_ref_dpi = base_w_at_ref_dpi, base_h_at_ref_dpi
                
                # Масштабируем до целевого DPI
                export_page_width_px = int(base_w_final_at_ref_dpi * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))
                export_page_height_px = int(base_h_final_at_ref_dpi * (target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES))

            if export_page_width_px <= 0 or export_page_height_px <= 0:
                logger.error("Неверные конечные размеры для экспорта страницы (после всех расчетов).")
                return None

            # --- 2. Подготовка конечного изображения, включая вылеты ---
            total_img_width, total_img_height = export_page_width_px, export_page_height_px
            offset_x_bleed_px, offset_y_bleed_px = 0, 0

            if self.settings.include_bleed:
                bleed_pixels = int(mm_to_pixels(self.settings.bleed_size, target_dpi))
                total_img_width += bleed_pixels * 2
                total_img_height += bleed_pixels * 2
                offset_x_bleed_px = bleed_pixels
                offset_y_bleed_px = bleed_pixels
            
            # Создание PIL Image
            if self.settings.transparent_background and self.settings.format == ExportFormat.PNG:
                image = Image.new('RGBA', (total_img_width, total_img_height), (0, 0, 0, 0))
            else:
                bg_color = self.settings.background_color
                image = Image.new('RGB', (total_img_width, total_img_height), bg_color)
            draw = ImageDraw.Draw(image)

            # --- 3. Масштабирование и рендеринг панелей на это изображение ---
            
            # Размеры холста PageConstructor (которые являются 300 DPI пикселями, как мы договорились)
            canvas_base_width_for_panels = self.app.page_constructor.page_width
            canvas_base_height_for_panels = self.app.page_constructor.page_height

            if canvas_base_width_for_panels == 0 or canvas_base_height_for_panels == 0:
                logger.warning("Холст PageConstructor имеет нулевые размеры. Возвращаю пустое изображение.")
                return image # Вернуть пустое изображение

            # Коэффициенты масштабирования для перехода от "единиц холста" к пикселям целевого экспорта
            # Эти коэффициенты применятся к координатам и размерам панелей.
            scale_content_x = export_page_width_px / canvas_base_width_for_panels
            scale_content_y = export_page_height_px / canvas_base_height_for_panels
            
            panels = sorted(self.app.page_constructor.panels, key=lambda p: p.layer)
            for panel in panels:
                if not panel.visible:
                    continue
                    
                # Координаты и размеры панели на экспортном холсте (в пикселях)
                # Сначала масштабируем относительно экспортной области, затем добавляем смещение вылетов
                px1, py1 = panel.x, panel.y
                px2, py2 = panel.x + panel.width, panel.y + panel.height

                if panel.panel_type == PanelType.SPEECH_BUBBLE:
                    cx = panel.x + panel.width / 2
                    cy = panel.y + panel.height / 2
                    angle = getattr(panel, 'tail_root_angle', math.pi / 2)
                    rx = cx + (panel.width / 2) * math.cos(angle) + panel.tail_dx
                    ry = cy + (panel.height / 2) * math.sin(angle) + panel.tail_dy
                    px1 = min(px1, rx)
                    py1 = min(py1, ry)
                    px2 = max(px2, rx)
                    py2 = max(py2, ry)

                panel_export_x = int(px1 * scale_content_x) + offset_x_bleed_px
                panel_export_y = int(py1 * scale_content_y) + offset_y_bleed_px
                panel_export_w = int((px2 - px1) * scale_content_x)
                panel_export_h = int((py2 - py1) * scale_content_y)
                offset_inside_x = int((panel.x - px1) * scale_content_x)
                offset_inside_y = int((panel.y - py1) * scale_content_y)

                if panel_export_w <=0 or panel_export_h <=0: 
                    continue # Пропускаем нулевые или отрицательные размеры
                
                # Передаем общий масштабный коэффициент для внутренних деталей панели (шрифт, толщина рамки).
                # Это отношение целевого DPI к "базовому DPI" панелей (который теперь 300 DPI).
                detail_scale_factor = target_dpi / REFERENCE_DPI_FOR_PAGE_SIZES 

                self.render_panel_to_image(
                    draw,
                    panel,
                    (panel_export_x, panel_export_y,
                     panel_export_x + panel_export_w, panel_export_y + panel_export_h),
                    detail_scale_factor,
                    export_target_image=image,
                    scale_x=scale_content_x,
                    scale_y=scale_content_y,
                    offset_x_px=offset_inside_x,
                    offset_y_px=offset_inside_y,
                )

            # --- 4. Добавление меток (если включены) ---
            # Здесь export_page_width_px и export_page_height_px - это размеры обрезной страницы
            if self.settings.include_crop_marks:
                self.add_crop_marks(draw, export_page_width_px, export_page_height_px, offset_x_bleed_px, offset_y_bleed_px)
            if self.settings.include_registration_marks:
                # add_registration_marks должна работать с общими размерами холста с вылетами,
                # и смещением вылетов, чтобы правильно позиционировать метки.
                self.add_registration_marks(draw, total_img_width, total_img_height, offset_x_bleed_px, offset_y_bleed_px)

            return image
        except Exception as e:
            logger.error(f"Критическая ошибка при рендеринге страницы на экспорт: {e}")
            import traceback
            traceback.print_exc()
            return None
            
    def render_panel_to_image(
            self,
            draw: ImageDraw.Draw,
            panel: Panel,
            bounds: Tuple[int, int, int, int],
            scale_factor: float,                        # target_dpi / REFERENCE_DPI
            export_target_image: Image.Image,
            *,
            scale_x: float,
            scale_y: float,
            offset_x_px: int = 0,
            offset_y_px: int = 0,
    ):
        """
        Рендерит одну панель страницы на итоговый export-canvas.

        • scale_factor переводит «единицы страницы» в пиксели.
        • panel.image_scale — пользовательский zoom изображения внутри панели.
        """

        x1_panel, y1_panel, x2_panel, y2_panel = bounds
        buf_w = x2_panel - x1_panel
        buf_h = y2_panel - y1_panel
        if buf_w <= 0 or buf_h <= 0:
            return

        panel_buf = Image.new("RGBA", (buf_w, buf_h), (0, 0, 0, 0))

        panel_w_px = int(panel.width * scale_x)
        panel_h_px = int(panel.height * scale_y)

        # 1. фон
        if panel.style.fill_color and panel.style.fill_color.lower() != "transparent":
            try:
                panel_buf.paste(
                    Image.new("RGBA", (buf_w, buf_h), panel.style.fill_color),
                    (0, 0)
                )
            except ValueError:
                logger.warning(f"Некорректный цвет фона '{panel.style.fill_color}' у панели {panel.id}")

        # 2. изображение-контент
        self._render_panel_image_content(
            panel, panel_buf, panel_w_px, panel_h_px, origin_x=offset_x_px, origin_y=offset_y_px
        )

        # 3. маска базовой формы (овал или прямоугольник)
        mask = Image.new("L", (buf_w, buf_h), 0)
        mdraw = ImageDraw.Draw(mask)
        if panel.panel_type in (PanelType.ROUND,
                                PanelType.SPEECH_BUBBLE,
                                PanelType.THOUGHT_BUBBLE):
            mdraw.ellipse(
                (offset_x_px, offset_y_px,
                 offset_x_px + panel_w_px, offset_y_px + panel_h_px),
                fill=255)
        else:
            mdraw.rectangle(
                (offset_x_px, offset_y_px,
                 offset_x_px + panel_w_px, offset_y_px + panel_h_px),
                fill=255)

        # 3-a. хвост речевого пузыря
        if panel.panel_type == PanelType.SPEECH_BUBBLE:
            angle = getattr(panel, 'tail_root_angle', math.pi / 2)
            cx = offset_x_px + panel_w_px / 2
            cy = offset_y_px + panel_h_px / 2
            root_x_px = cx + (panel_w_px / 2) * math.cos(angle)
            root_y_px = cy + (panel_h_px / 2) * math.sin(angle)
            end_x_px = root_x_px + panel.tail_dx * scale_x
            end_y_px = root_y_px + panel.tail_dy * scale_y

            tang_dx = -math.sin(angle) * panel_w_px
            tang_dy = math.cos(angle) * panel_h_px
            norm = math.hypot(tang_dx, tang_dy)
            if norm == 0:
                tang_dx, tang_dy = 1, 0
            else:
                tang_dx /= norm
                tang_dy /= norm

            base_px = int(6 * max(scale_x, scale_y))
            bx1 = root_x_px + tang_dx * base_px
            by1 = root_y_px + tang_dy * base_px
            bx2 = root_x_px - tang_dx * base_px
            by2 = root_y_px - tang_dy * base_px

            # маска (чтобы хвост вырезался в ту же альфа-область)
            mdraw.polygon((bx1, by1, bx2, by2, end_x_px, end_y_px), fill=255)

            # сам хвост
            panel_draw = ImageDraw.Draw(panel_buf)
            border_w   = max(1, int(panel.style.border_width * scale_factor)) \
                if panel.style.border_width > 0 else 0
            panel_draw.polygon((bx1, by1, bx2, by2, end_x_px, end_y_px),
                               fill=panel.style.fill_color,
                               outline=panel.style.border_color if border_w else None,
                               width=border_w)

        # 4. объединяем маску и буфер
        panel_buf.putalpha(mask)

        # 5. вставляем панель на общий экспорт-canvas
        export_target_image.paste(panel_buf, (x1_panel, y1_panel), panel_buf)

        text_bounds = (
            x1_panel + offset_x_px,
            y1_panel + offset_y_px,
            x1_panel + offset_x_px + panel_w_px,
            y1_panel + offset_y_px + panel_h_px,
        )

        # 6. текст
        if panel.content_text:
            self.render_panel_text(draw, panel, text_bounds, scale_factor)

        # 7. внешняя рамка панели
        border_w = max(1, int(panel.style.border_width * scale_factor)) \
            if panel.style.border_width > 0 else 0
        if border_w and panel.style.border_color:
            try:
                if panel.panel_type in (PanelType.ROUND,
                                        PanelType.SPEECH_BUBBLE,
                                        PanelType.THOUGHT_BUBBLE):
                    draw.ellipse(text_bounds, outline=panel.style.border_color, width=border_w)
                else:
                    draw.rectangle(text_bounds, outline=panel.style.border_color, width=border_w)
            except ValueError:
                logger.warning(f"Некорректный цвет рамки '{panel.style.border_color}' у панели {panel.id}")

    def _render_panel_image_content(
            self,
            panel: Panel,
            panel_buf: Image.Image,
            panel_w_px: int,
            panel_h_px: int,
            *,
            origin_x: int = 0,
            origin_y: int = 0,
    ) -> None:
        """Отрисовка изображения внутри панели на временный буфер."""
        if not panel.content_image or not os.path.exists(panel.content_image):
            return

        try:
            src = Image.open(panel.content_image)
        except Exception as e:
            logger.error(f"Не удалось открыть изображение панели {panel.id}: {e}")
            return

        sx = panel_w_px / panel.width if panel.width else 1.0
        sy = panel_h_px / panel.height if panel.height else 1.0

        render_w = int(src.width * panel.image_scale * sx)
        render_h = int(src.height * panel.image_scale * sy)
        if render_w <= 0 or render_h <= 0:
            return

        img_resized = src.resize((render_w, render_h), Image.Resampling.LANCZOS)
        offset_x_px = int(panel.image_offset_x * sx) + origin_x
        offset_y_px = int(panel.image_offset_y * sy) + origin_y

        panel_buf.paste(img_resized, (offset_x_px, offset_y_px))
            
    def render_panel_text(self, draw: ImageDraw.Draw, panel: Panel, 
                         bounds: Tuple[int, int, int, int], scale_factor: float):
        """Рендеринг текста панели"""
        try:
            x1, y1, x2, y2 = bounds
            
            # Размер шрифта с учётом масштаба
            font_size = max(8, int(12 * scale_factor))
            
            # Попытка загрузки шрифта
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                font = ImageFont.load_default()
                
            # Центрирование текста
            text_bbox = draw.textbbox((0, 0), panel.content_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            text_x = x1 + (x2 - x1 - text_width) // 2
            text_y = y1 + (y2 - y1 - text_height) // 2
            
            # Рендеринг текста с тенью для лучшей читаемости
            draw.text((text_x + 1, text_y + 1), panel.content_text, fill="#888888", font=font)
            draw.text((text_x, text_y), panel.content_text, fill="#000000", font=font)
            
        except Exception as e:
            logger.error(f"Ошибка рендеринга текста панели: {e}")
            
    def apply_export_settings(self, image: Image.Image) -> Image.Image:
        """Применение настроек экспорта к изображению"""
        processed = image.copy()
        
        # Коррекция яркости
        if self.settings.brightness != 0:
            enhancer = ImageEnhance.Brightness(processed)
            processed = enhancer.enhance(1.0 + self.settings.brightness)
            
        # Коррекция контрастности
        if self.settings.contrast != 0:
            enhancer = ImageEnhance.Contrast(processed)
            processed = enhancer.enhance(1.0 + self.settings.contrast)
            
        # Коррекция насыщенности
        if self.settings.saturation != 0:
            enhancer = ImageEnhance.Color(processed)
            processed = enhancer.enhance(1.0 + self.settings.saturation)
            
        # Добавление водяного знака
        if self.settings.watermark_enabled and self.settings.watermark_text:
            processed = self.add_watermark(processed)
            
        return processed
        
    def add_watermark(self, image: Image.Image) -> Image.Image:
        """Добавление водяного знака"""
        try:
            # Создание слоя для водяного знака
            watermark_layer = Image.new('RGBA', image.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(watermark_layer)
            
            # Шрифт для водяного знака
            try:
                font = ImageFont.truetype("arial.ttf", self.settings.watermark_font_size)
            except:
                font = ImageFont.load_default()
                
            # Размер текста
            text_bbox = draw.textbbox((0, 0), self.settings.watermark_text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # Позиционирование
            if self.settings.watermark_position == "top_left":
                x, y = 10, 10
            elif self.settings.watermark_position == "top_right":
                x, y = image.width - text_width - 10, 10
            elif self.settings.watermark_position == "bottom_left":
                x, y = 10, image.height - text_height - 10
            elif self.settings.watermark_position == "bottom_right":
                x, y = image.width - text_width - 10, image.height - text_height - 10
            else:  # center
                x = (image.width - text_width) // 2
                y = (image.height - text_height) // 2
                
            # Цвет с учётом прозрачности
            color = self.settings.watermark_color
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            alpha = int(255 * self.settings.watermark_opacity)
            
            # Рендеринг водяного знака
            draw.text((x, y), self.settings.watermark_text, 
                     fill=(r, g, b, alpha), font=font)
            
            # Композитинг
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
                
            return Image.alpha_composite(image, watermark_layer)
            
        except Exception as e:
            logger.error(f"Ошибка добавления водяного знака: {e}")
            return image
            
    def add_crop_marks(self, draw: ImageDraw.Draw, page_width_px: int, page_height_px: int, 
                    offset_x_bleed_px: int, offset_y_bleed_px: int):
        """Добавление меток обрезки"""
        mark_length = int(mm_to_pixels(5, self.settings.dpi)) # Длина меток, 5мм
        mark_offset = int(mm_to_pixels(2, self.settings.dpi)) # Отступ от края страницы, 2мм
        
        # Координаты углов страницы (БЕЗ вылетов, т.е. фактические края страницы)
        page_x1 = offset_x_bleed_px
        page_y1 = offset_y_bleed_px
        page_x2 = offset_x_bleed_px + page_width_px
        page_y2 = offset_y_bleed_px + page_height_px
        
        # Метки в углах
        # Верхний левый
        draw.line([page_x1 - mark_offset, page_y1, page_x1 - mark_offset - mark_length, page_y1], fill="black", width=1)
        draw.line([page_x1, page_y1 - mark_offset, page_x1, page_y1 - mark_offset - mark_length], fill="black", width=1)
        
        # Верхний правый
        draw.line([page_x2 + mark_offset, page_y1, page_x2 + mark_offset + mark_length, page_y1], fill="black", width=1)
        draw.line([page_x2, page_y1 - mark_offset, page_x2, page_y1 - mark_offset - mark_length], fill="black", width=1)
        
        # Нижний левый
        draw.line([page_x1 - mark_offset, page_y2, page_x1 - mark_offset - mark_length, page_y2], fill="black", width=1)
        draw.line([page_x1, page_y2 + mark_offset, page_x1, page_y2 + mark_offset + mark_length], fill="black", width=1)
        
        # Нижний правый
        draw.line([page_x2 + mark_offset, page_y2, page_x2 + mark_offset + mark_length, page_y2], fill="black", width=1)
        draw.line([page_x2, page_y2 + mark_offset, page_x2, page_y2 + mark_offset + mark_length], fill="black", width=1)
        
    def add_registration_marks(self, draw: ImageDraw.Draw, total_img_width: int, total_img_height: int,
                            offset_x_bleed_px: int, offset_y_bleed_px: int):
        """Добавление приводочных меток"""
        mark_size = int(mm_to_pixels(5, self.settings.dpi)) # Размер метки, 5мм
        offset_from_page_edge = int(mm_to_pixels(10, self.settings.dpi)) # Отступ от обрезного края страницы

        # Координаты центра обрезной области
        center_x_page = offset_x_bleed_px + (total_img_width - 2 * offset_x_bleed_px) // 2
        center_y_page = offset_y_bleed_px + (total_img_height - 2 * offset_y_bleed_px) // 2

        # Метки по центру каждой стороны обрезной области
        mark_color = "black"
        mark_width = 1

        # Верхняя метка
        cx, cy = center_x_page, offset_y_bleed_px - offset_from_page_edge
        draw.ellipse([cx - mark_size//2, cy - mark_size//2, cx + mark_size//2, cy + mark_size//2], outline=mark_color, width=mark_width)
        draw.line([cx - mark_size, cy, cx + mark_size, cy], fill=mark_color, width=mark_width)
        draw.line([cx, cy - mark_size, cx, cy + mark_size], fill=mark_color, width=mark_width)

        # Нижняя метка
        cx, cy = center_x_page, total_img_height - offset_y_bleed_px + offset_from_page_edge
        draw.ellipse([cx - mark_size//2, cy - mark_size//2, cx + mark_size//2, cy + mark_size//2], outline=mark_color, width=mark_width)
        draw.line([cx - mark_size, cy, cx + mark_size, cy], fill=mark_color, width=mark_width)
        draw.line([cx, cy - mark_size, cx, cy + mark_size], fill=mark_color, width=mark_width)

        # Левая метка
        cx, cy = offset_x_bleed_px - offset_from_page_edge, center_y_page
        draw.ellipse([cx - mark_size//2, cy - mark_size//2, cx + mark_size//2, cy + mark_size//2], outline=mark_color, width=mark_width)
        draw.line([cx - mark_size, cy, cx + mark_size, cy], fill=mark_color, width=mark_width)
        draw.line([cx, cy - mark_size, cx, cy + mark_size], fill=mark_color, width=mark_width)

        # Правая метка
        cx, cy = total_img_width - offset_x_bleed_px + offset_from_page_edge, center_y_page
        draw.ellipse([cx - mark_size//2, cy - mark_size//2, cx + mark_size//2, cy + mark_size//2], outline=mark_color, width=mark_width)
        draw.line([cx - mark_size, cy, cx + mark_size, cy], fill=mark_color, width=mark_width)
        draw.line([cx, cy - mark_size, cx, cy + mark_size], fill=mark_color, width=mark_width)
        
    def get_output_filename(self) -> str:
        """Получение имени выходного файла"""
        output_dir = self.settings.output_path
        template = self.settings.filename_template
        
        # Подстановка номера страницы
        filename = template.format(number=1)  # Пока только одна страница
        
        # Добавление расширения
        extension = self.get_file_extension()
        if not filename.endswith(extension):
            filename += extension
            
        return os.path.join(output_dir, filename)
        
    def get_file_extension(self) -> str:
        """Получение расширения файла для формата"""
        extensions = {
            ExportFormat.PNG: ".png",
            ExportFormat.JPEG: ".jpg",
            ExportFormat.PDF: ".pdf",
            ExportFormat.CBZ: ".cbz",
            ExportFormat.TIFF: ".tiff",
            ExportFormat.BMP: ".bmp",
            ExportFormat.WEBP: ".webp"
        }
        return extensions.get(self.settings.format, ".png")
        
    def save_image(self, image: Image.Image, output_path: str) -> bool:
        """Сохранение изображения"""
        try:
            if self.settings.format == ExportFormat.PNG:
                save_kwargs = {
                    'format': 'PNG',
                    'compress_level': self.settings.png_compression,
                    'optimize': True
                }
                
            elif self.settings.format == ExportFormat.JPEG:
                # Конвертация в RGB для JPEG
                if image.mode in ('RGBA', 'LA', 'P'):
                    rgb_image = Image.new('RGB', image.size, self.settings.background_color)
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = rgb_image
                    
                save_kwargs = {
                    'format': 'JPEG',
                    'quality': self.settings.jpeg_quality,
                    'optimize': True
                }
                
            elif self.settings.format == ExportFormat.PDF:
                return self.save_as_pdf(image, output_path)
                
            elif self.settings.format == ExportFormat.CBZ:
                return self.save_as_cbz([image], output_path)
                
            else:
                save_kwargs = {'format': self.settings.format.value}
                
            # Добавление метаданных
            if self.settings.include_metadata:
                from PIL.ExifTags import TAGS
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                # Можно добавить различные метаданные
                
            # Сохранение
            image.save(output_path, **save_kwargs)
            
            logger.info(f"Изображение сохранено: {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения изображения {output_path}: {e}")
            return False
            
    def save_as_pdf(self, image: Image.Image, output_path: str) -> bool:
        """Сохранение как PDF"""
        try:
            if not HAS_REPORTLAB:
                messagebox.showerror("Ошибка", 
                    "Для экспорта в PDF требуется библиотека ReportLab.\n"
                    "Установите её командой: pip install reportlab")
                return False
                
            # Конвертация изображения для PDF
            if image.mode != 'RGB':
                image = image.convert('RGB')
                
            # Сохранение во временный файл
            temp_path = get_temp_dir() / "temp_page.png"
            # Исправлено: убедимся что директория существует
            temp_path.parent.mkdir(parents=True, exist_ok=True)
            image.save(temp_path, "PNG")
            
            # Создание PDF
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Image as RLImage
            
            doc = SimpleDocTemplate(output_path, pagesize=letter)
            story = []
            
            # Добавление изображения
            img = RLImage(str(temp_path))
            img.drawHeight = image.height * 72 / self.settings.dpi
            img.drawWidth = image.width * 72 / self.settings.dpi
            
            story.append(img)
            doc.build(story)
            
            # Удаление временного файла
            temp_path.unlink(missing_ok=True)
            
            return True
            
        except Exception as e:
            logger.error(f"Ошибка сохранения PDF {output_path}: {e}")
            messagebox.showerror("Ошибка PDF", f"Не удалось создать PDF:\n{e}")
            return False
            
    def save_as_cbz(self, images: List[Image.Image], output_path: str) -> bool:
        """Сохранение как CBZ архив"""
        try:
            with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as cbz:
                for i, image in enumerate(images):
                    # Сохранение изображения во временный буфер
                    img_buffer = io.BytesIO()
                    
                    if image.mode != 'RGB':
                        image = image.convert('RGB')
                        
                    image.save(img_buffer, format='JPEG', quality=self.settings.jpeg_quality)
                    img_buffer.seek(0)
                    
                    # Добавление в архив
                    filename = f"page_{i+1:03d}.jpg"
                    cbz.writestr(filename, img_buffer.getvalue())
                    
            return True
            
        except Exception as e:
            logger.error(f"Ошибка создания CBZ {output_path}: {e}")
            return False
            
    def show_progress_window(self):
        """Показ окна прогресса"""
        self.progress_window = tk.Toplevel(self.app.root)
        self.progress_window.title("Экспорт в процессе...")
        self.progress_window.geometry("400x150")
        self.progress_window.resizable(False, False)
        
        center_window(self.progress_window, self.app.root)
        
        # Прогресс-бар
        ttk.Label(self.progress_window, text="Экспорт страницы...").pack(pady=10)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.progress_window, variable=self.progress_var, 
                                          maximum=100, length=300)
        self.progress_bar.pack(pady=10)
        
        self.progress_label = ttk.Label(self.progress_window, text="Подготовка...")
        self.progress_label.pack()
        
        # Кнопка отмены
        ttk.Button(self.progress_window, text="Отмена", 
                  command=self.cancel_export_process).pack(pady=10)
        
        # Запуск мониторинга прогресса
        self.monitor_progress()
        
    def monitor_progress(self):
        """Мониторинг прогресса экспорта"""
        if self.progress.completed:
            self.progress_var.set(100)
            self.progress_label.config(text="Экспорт завершён успешно!")
            
            # Закрытие окна через 2 секунды
            self.progress_window.after(2000, self.progress_window.destroy)
            
            # Показ результата
            output_path = self.get_output_filename()
            messagebox.showinfo("Экспорт завершён", f"Страница экспортирована:\n{output_path}")
            
        elif self.progress.error:
            self.progress_var.set(0)
            self.progress_label.config(text=f"Ошибка: {self.progress.error}")
            
            # Закрытие окна через 3 секунды
            self.progress_window.after(3000, self.progress_window.destroy)
            
            messagebox.showerror("Ошибка экспорта", self.progress.error)
            
        else:
            # Обновление прогресса
            if self.progress.total_pages > 0:
                progress_percent = (self.progress.current_page / self.progress.total_pages) * 100
                self.progress_var.set(progress_percent)
                
            self.progress_label.config(text=self.progress.current_operation)
            
            # Продолжение мониторинга
            self.progress_window.after(100, self.monitor_progress)
            
    def cancel_export_process(self):
        """Отмена процесса экспорта"""
        self.cancel_export = True
        self.progress_window.destroy()
        
    def save_export_settings(self):
        """Сохранение настроек экспорта"""
        settings = self.collect_export_settings()
        
        file_path = filedialog.asksaveasfilename(
            title="Сохранить настройки экспорта",
            defaultextension=".json",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
            parent=self.export_window
        )
        
        if file_path:
            try:
                import json
                with open(file_path, 'w', encoding='utf-8') as f:
                    # Преобразование в словарь для сериализации
                    settings_dict = {
                        'format': settings.format.value,
                        'quality': settings.quality.value,
                        'dpi': settings.dpi,
                        'jpeg_quality': settings.jpeg_quality,
                        'png_compression': settings.png_compression,
                        'include_bleed': settings.include_bleed,
                        'bleed_size': settings.bleed_size,
                        'include_crop_marks': settings.include_crop_marks,
                        'include_registration_marks': settings.include_registration_marks,
                        'watermark_enabled': settings.watermark_enabled,
                        'watermark_text': settings.watermark_text,
                        'watermark_position': settings.watermark_position,
                        'watermark_opacity': settings.watermark_opacity,
                        'watermark_font_size': settings.watermark_font_size,
                        'watermark_color': settings.watermark_color,
                        'color_profile': settings.color_profile,
                        'gamma_correction': settings.gamma_correction,
                        'brightness': settings.brightness,
                        'contrast': settings.contrast,
                        'saturation': settings.saturation,
                        'background_color': settings.background_color,
                        'transparent_background': settings.transparent_background,
                        'anti_aliasing': settings.anti_aliasing,
                        'embed_fonts': settings.embed_fonts,
                        'filename_template': settings.filename_template,
                        'include_metadata': settings.include_metadata
                    }
                    
                    json.dump(settings_dict, f, indent=2, ensure_ascii=False)
                    
                messagebox.showinfo("Сохранено", f"Настройки экспорта сохранены:\n{file_path}")
                
            except Exception as e:
                logger.error(f"Ошибка сохранения настроек экспорта: {e}")
                messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{e}")
                
    def load_export_settings(self):
        """Загрузка настроек экспорта"""
        file_path = filedialog.askopenfilename(
            title="Загрузить настройки экспорта",
            filetypes=[("JSON файлы", "*.json"), ("Все файлы", "*.*")],
            parent=self.export_window
        )
        
        if file_path:
            try:
                import json
                with open(file_path, 'r', encoding='utf-8') as f:
                    settings_dict = json.load(f)
                    
                # Применение загруженных настроек к UI
                if 'format' in settings_dict:
                    self.format_var.set(settings_dict['format'])
                if 'quality' in settings_dict:
                    self.quality_var.set(settings_dict['quality'])
                if 'dpi' in settings_dict:
                    self.dpi_var.set(settings_dict['dpi'])
                if 'jpeg_quality' in settings_dict:
                    self.jpeg_quality_var.set(settings_dict['jpeg_quality'])
                if 'png_compression' in settings_dict:
                    self.png_compression_var.set(settings_dict['png_compression'])
                if 'include_bleed' in settings_dict:
                    self.include_bleed_var.set(settings_dict['include_bleed'])
                if 'bleed_size' in settings_dict:
                    self.bleed_size_var.set(settings_dict['bleed_size'])
                if 'include_crop_marks' in settings_dict:
                    self.crop_marks_var.set(settings_dict['include_crop_marks'])
                if 'include_registration_marks' in settings_dict:
                    self.reg_marks_var.set(settings_dict['include_registration_marks'])
                if 'watermark_enabled' in settings_dict:
                    self.watermark_enabled_var.set(settings_dict['watermark_enabled'])
                if 'watermark_text' in settings_dict:
                    self.watermark_text_var.set(settings_dict['watermark_text'])
                if 'watermark_position' in settings_dict:
                    self.watermark_position_var.set(settings_dict['watermark_position'])
                if 'watermark_opacity' in settings_dict:
                    self.watermark_opacity_var.set(settings_dict['watermark_opacity'])
                if 'watermark_font_size' in settings_dict:
                    self.watermark_font_size_var.set(settings_dict['watermark_font_size'])
                if 'watermark_color' in settings_dict:
                    self.watermark_color_var.set(settings_dict['watermark_color'])
                    self.watermark_color_button.configure(bg=settings_dict['watermark_color'])
                if 'brightness' in settings_dict:
                    self.brightness_var.set(settings_dict['brightness'])
                if 'contrast' in settings_dict:
                    self.contrast_var.set(settings_dict['contrast'])
                if 'saturation' in settings_dict:
                    self.saturation_var.set(settings_dict['saturation'])
                if 'background_color' in settings_dict:
                    self.bg_color_var.set(settings_dict['background_color'])
                    self.bg_color_button.configure(bg=settings_dict['background_color'])
                if 'transparent_background' in settings_dict:
                    self.transparent_bg_var.set(settings_dict['transparent_background'])
                if 'anti_aliasing' in settings_dict:
                    self.anti_aliasing_var.set(settings_dict['anti_aliasing'])
                if 'embed_fonts' in settings_dict:
                    self.embed_fonts_var.set(settings_dict['embed_fonts'])
                if 'filename_template' in settings_dict:
                    self.filename_var.set(settings_dict['filename_template'])
                if 'include_metadata' in settings_dict:
                    self.include_metadata_var.set(settings_dict['include_metadata'])
                    
                # Обновление предпросмотра
                self.update_export_preview()
                self.update_export_info()
                
                messagebox.showinfo("Загружено", f"Настройки экспорта загружены:\n{file_path}")
                
            except Exception as e:
                logger.error(f"Ошибка загрузки настроек экспорта: {e}")
                messagebox.showerror("Ошибка", f"Не удалось загрузить настройки:\n{e}")
                
    def export_all_pages(self):
        """Экспорт всех страниц проекта"""
        # Пока у нас только одна страница, но можно расширить для мультистраничных проектов
        
        # Диалог настроек пакетного экспорта
        batch_dialog = tk.Toplevel(self.app.root)
        batch_dialog.title("Пакетный экспорт страниц")
        batch_dialog.geometry("500x400")
        batch_dialog.resizable(False, False)
        
        # Центрирование диалога
        batch_dialog.transient(self.app.root)
        batch_dialog.grab_set()
        
        # Переменные настроек
        batch_vars = {}
        
        # Основные настройки
        main_frame = tk.LabelFrame(batch_dialog, text="Настройки экспорта")
        main_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Формат экспорта
        tk.Label(main_frame, text="Формат:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        batch_vars['format'] = tk.StringVar(value="PNG")
        format_combo = tk.ttk.Combobox(main_frame, textvariable=batch_vars['format'],
                                    values=["PNG", "JPEG", "PDF"], state="readonly")
        format_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # DPI
        tk.Label(main_frame, text="DPI:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        batch_vars['dpi'] = tk.IntVar(value=300)
        dpi_combo = tk.ttk.Combobox(main_frame, textvariable=batch_vars['dpi'],
                                values=[72, 150, 300, 600])
        dpi_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Путь экспорта
        tk.Label(main_frame, text="Папка экспорта:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        
        path_frame = tk.Frame(main_frame)
        path_frame.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        
        batch_vars['output_path'] = tk.StringVar(value=os.path.expanduser("~/Desktop"))
        path_entry = tk.Entry(path_frame, textvariable=batch_vars['output_path'], width=30)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def browse_batch_path():
            path = filedialog.askdirectory(title="Выберите папку для экспорта", parent=batch_dialog)
            if path:
                batch_vars['output_path'].set(path)
                
        tk.Button(path_frame, text="Обзор...", command=browse_batch_path).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Шаблон имени файла
        tk.Label(main_frame, text="Шаблон имени:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        batch_vars['filename_template'] = tk.StringVar(value="page_{number:03d}")
        tk.Entry(main_frame, textvariable=batch_vars['filename_template'], width=20).grid(row=3, column=1, padx=5, pady=5)
        
        # Дополнительные опции
        options_frame = tk.LabelFrame(batch_dialog, text="Дополнительные опции")
        options_frame.pack(fill=tk.X, padx=10, pady=5)
        
        batch_vars['create_cbz'] = tk.BooleanVar(value=False)
        tk.Checkbutton(options_frame, text="Создать CBZ архив после экспорта", 
                    variable=batch_vars['create_cbz']).pack(anchor=tk.W, padx=5, pady=2)
        
        batch_vars['include_metadata'] = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Включить метаданные", 
                    variable=batch_vars['include_metadata']).pack(anchor=tk.W, padx=5, pady=2)
        
        batch_vars['optimize_size'] = tk.BooleanVar(value=True)
        tk.Checkbutton(options_frame, text="Оптимизировать размер файлов", 
                    variable=batch_vars['optimize_size']).pack(anchor=tk.W, padx=5, pady=2)
        
        # Список страниц (пока заглушка для будущего расширения)
        pages_frame = tk.LabelFrame(batch_dialog, text="Страницы для экспорта")
        pages_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Простой список страниц
        pages_listbox = tk.Listbox(pages_frame, height=4)
        pages_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Добавление текущей страницы
        pages_listbox.insert(0, "Страница 1 (текущая)")
        pages_listbox.selection_set(0)
        
        def start_batch_export():
            """Запуск пакетного экспорта"""
            if not batch_vars['output_path'].get():
                messagebox.showerror("Ошибка", "Выберите папку для экспорта")
                return
                
            # Сбор настроек
            batch_settings = ExportSettings(
                format=ExportFormat(batch_vars['format'].get()),
                dpi=batch_vars['dpi'].get(),
                output_path=batch_vars['output_path'].get(),
                filename_template=batch_vars['filename_template'].get(),
                include_metadata=batch_vars['include_metadata'].get()
            )
            
            # Закрытие диалога
            batch_dialog.destroy()
            
            # Запуск экспорта
            self.run_batch_export(batch_settings, batch_vars['create_cbz'].get())
            
        # Кнопки
        buttons_frame = tk.Frame(batch_dialog)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttons_frame, text="Экспорт", command=start_batch_export).pack(side=tk.RIGHT, padx=5)
        tk.Button(buttons_frame, text="Отмена", command=batch_dialog.destroy).pack(side=tk.RIGHT)

    def run_batch_export(self, batch_settings: ExportSettings, create_cbz: bool = False):
        """Выполнение пакетного экспорта"""
        try:
            # Создание папки экспорта
            export_path = Path(batch_settings.output_path)
            export_path.mkdir(parents=True, exist_ok=True)
            
            # Временная замена настроек
            original_settings = self.settings
            self.settings = batch_settings
            
            # Экспорт текущей страницы
            success = self.export_current_page()
            
            if success:
                exported_files = []
                
                # Получение имени экспортированного файла
                output_filename = self.get_output_filename()
                if os.path.exists(output_filename):
                    exported_files.append(output_filename)
                    
                # Создание CBZ архива если требуется
                if create_cbz and exported_files:
                    cbz_path = export_path / "manga_pages.cbz"
                    self.create_cbz_from_files(exported_files, str(cbz_path))
                    
                messagebox.showinfo("Экспорт завершён", 
                                f"Экспортировано страниц: {len(exported_files)}\n"
                                f"Путь: {export_path}")
            else:
                messagebox.showerror("Ошибка", "Не удалось экспортировать страницы")
                
            # Восстановление настроек
            self.settings = original_settings
            
        except Exception as e:
            logger.error(f"Ошибка пакетного экспорта: {e}")
            messagebox.showerror("Ошибка", f"Ошибка пакетного экспорта:\n{e}")
        
    def create_cbz_archive(self):
        """Создание CBZ архива из экспортированных страниц"""
        # Диалог создания архива
        cbz_dialog = tk.Toplevel(self.app.root)
        cbz_dialog.title("Создание CBZ архива")
        cbz_dialog.geometry("500x400")
        cbz_dialog.resizable(False, False)
        
        # Центрирование диалога
        cbz_dialog.transient(self.app.root)
        cbz_dialog.grab_set()
        
        # Переменные
        cbz_vars = {}
        
        # Выбор изображений
        images_frame = tk.LabelFrame(cbz_dialog, text="Изображения для архива")
        images_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Список изображений
        images_listbox = tk.Listbox(images_frame, selectmode=tk.EXTENDED)
        images_scrollbar = tk.Scrollbar(images_frame, orient=tk.VERTICAL, command=images_listbox.yview)
        images_listbox.configure(yscrollcommand=images_scrollbar.set)
        
        images_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0), pady=5)
        images_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # Кнопки управления списком
        list_buttons_frame = tk.Frame(images_frame)
        list_buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        
        def add_images():
            """Добавление изображений в список"""
            files = filedialog.askopenfilenames(
                title="Выберите изображения",
                filetypes=[
                    ("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
                    ("PNG файлы", "*.png"),
                    ("JPEG файлы", "*.jpg *.jpeg"),
                    ("Все файлы", "*.*")
                ],
                parent=cbz_dialog
            )
            
            for file in files:
                # Проверка, что файл ещё не добавлен
                if file not in [images_listbox.get(i) for i in range(images_listbox.size())]:
                    images_listbox.insert(tk.END, file)
                    
        def remove_selected():
            """Удаление выбранных изображений"""
            selected = images_listbox.curselection()
            for index in reversed(selected):  # Удаляем с конца
                images_listbox.delete(index)
                
        def move_up():
            """Перемещение вверх по списку"""
            selected = images_listbox.curselection()
            if selected and selected[0] > 0:
                index = selected[0]
                item = images_listbox.get(index)
                images_listbox.delete(index)
                images_listbox.insert(index - 1, item)
                images_listbox.selection_set(index - 1)
                
        def move_down():
            """Перемещение вниз по списку"""
            selected = images_listbox.curselection()
            if selected and selected[0] < images_listbox.size() - 1:
                index = selected[0]
                item = images_listbox.get(index)
                images_listbox.delete(index)
                images_listbox.insert(index + 1, item)
                images_listbox.selection_set(index + 1)
        
        tk.Button(list_buttons_frame, text="Добавить изображения", command=add_images).pack(side=tk.LEFT, padx=2)
        tk.Button(list_buttons_frame, text="Удалить", command=remove_selected).pack(side=tk.LEFT, padx=2)
        tk.Button(list_buttons_frame, text="↑", command=move_up, width=3).pack(side=tk.LEFT, padx=2)
        tk.Button(list_buttons_frame, text="↓", command=move_down, width=3).pack(side=tk.LEFT, padx=2)
        
        # Настройки архива
        settings_frame = tk.LabelFrame(cbz_dialog, text="Настройки архива")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Имя архива
        tk.Label(settings_frame, text="Имя архива:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        cbz_vars['archive_name'] = tk.StringVar(value="manga_archive")
        tk.Entry(settings_frame, textvariable=cbz_vars['archive_name'], width=30).grid(row=0, column=1, padx=5, pady=5)
        
        # Путь сохранения
        tk.Label(settings_frame, text="Сохранить в:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        
        save_frame = tk.Frame(settings_frame)
        save_frame.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=5)
        
        cbz_vars['save_path'] = tk.StringVar(value=os.path.expanduser("~/Desktop"))
        save_entry = tk.Entry(save_frame, textvariable=cbz_vars['save_path'], width=25)
        save_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def browse_save_path():
            path = filedialog.askdirectory(title="Выберите папку для сохранения", parent=cbz_dialog)
            if path:
                cbz_vars['save_path'].set(path)
                
        tk.Button(save_frame, text="Обзор...", command=browse_save_path).pack(side=tk.RIGHT, padx=(5, 0))
        
        # Качество и сжатие
        tk.Label(settings_frame, text="Качество JPEG:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        cbz_vars['jpeg_quality'] = tk.IntVar(value=95)
        tk.Scale(settings_frame, from_=50, to=100, variable=cbz_vars['jpeg_quality'], 
                orient=tk.HORIZONTAL, length=200).grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Опции
        cbz_vars['convert_to_jpeg'] = tk.BooleanVar(value=True)
        tk.Checkbutton(settings_frame, text="Конвертировать все изображения в JPEG", 
                    variable=cbz_vars['convert_to_jpeg']).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        cbz_vars['optimize_size'] = tk.BooleanVar(value=True)
        tk.Checkbutton(settings_frame, text="Оптимизировать размер архива", 
                    variable=cbz_vars['optimize_size']).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        
        def create_archive():
            """Создание CBZ архива"""
            # Получение списка изображений
            image_files = [images_listbox.get(i) for i in range(images_listbox.size())]
            
            if not image_files:
                messagebox.showerror("Ошибка", "Добавьте изображения в список")
                return
                
            if not cbz_vars['archive_name'].get():
                messagebox.showerror("Ошибка", "Введите имя архива")
                return
                
            if not cbz_vars['save_path'].get():
                messagebox.showerror("Ошибка", "Выберите папку для сохранения")
                return
                
            # Формирование пути к архиву
            archive_name = cbz_vars['archive_name'].get()
            if not archive_name.endswith('.cbz'):
                archive_name += '.cbz'
                
            archive_path = os.path.join(cbz_vars['save_path'].get(), archive_name)
            
            # Закрытие диалога
            cbz_dialog.destroy()
            
            # Создание архива
            self.create_cbz_from_files(
                image_files, 
                archive_path,
                convert_to_jpeg=cbz_vars['convert_to_jpeg'].get(),
                jpeg_quality=cbz_vars['jpeg_quality'].get(),
                optimize=cbz_vars['optimize_size'].get()
            )
        
        # Кнопки
        buttons_frame = tk.Frame(cbz_dialog)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttons_frame, text="Создать архив", command=create_archive).pack(side=tk.RIGHT, padx=5)
        tk.Button(buttons_frame, text="Отмена", command=cbz_dialog.destroy).pack(side=tk.RIGHT)
        
        # Автоматическое добавление текущей страницы если она экспортирована
        try:
            # Попытка найти последний экспортированный файл
            if hasattr(self, 'last_exported_file') and os.path.exists(self.last_exported_file):
                images_listbox.insert(0, self.last_exported_file)
        except:
            pass

    def create_cbz_from_files(self, image_files: list, output_path: str, 
                            convert_to_jpeg: bool = True, jpeg_quality: int = 95, 
                            optimize: bool = True):
        """Создание CBZ архива из списка файлов изображений"""
        
        # Создание окна прогресса
        progress_window = tk.Toplevel(self.app.root)
        progress_window.title("Создание CBZ архива")
        progress_window.geometry("400x150")
        progress_window.resizable(False, False)
        
        # Центрирование окна
        progress_window.transient(self.app.root)
        progress_window.grab_set()
        
        tk.Label(progress_window, text="Создание CBZ архива...").pack(pady=10)
        
        progress_var = tk.DoubleVar()
        progress_bar = tk.ttk.Progressbar(progress_window, variable=progress_var, 
                                        maximum=len(image_files), length=300)
        progress_bar.pack(pady=10)
        
        status_label = tk.Label(progress_window, text="")
        status_label.pack()
        
        cancel_var = tk.BooleanVar(value=False)
        tk.Button(progress_window, text="Отмена", 
                command=lambda: cancel_var.set(True)).pack(pady=10)
        
        def create_archive_thread():
            """Поток создания архива"""
            try:
                with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as cbz:
                    for i, image_file in enumerate(image_files):
                        if cancel_var.get():
                            break
                            
                        # Обновление прогресса
                        filename = os.path.basename(image_file)
                        status_label.config(text=f"Обработка: {filename}")
                        progress_window.update_idletasks()
                        
                        try:
                            # Загрузка изображения
                            with Image.open(image_file) as img:
                                # Определение имени файла в архиве
                                base_name = f"page_{i+1:03d}"
                                
                                if convert_to_jpeg:
                                    # Конвертация в JPEG
                                    if img.mode in ('RGBA', 'LA', 'P'):
                                        # Конвертация с белым фоном
                                        rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                                        if img.mode == 'P':
                                            img = img.convert('RGBA')
                                        rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                                        img = rgb_img
                                        
                                    # Сохранение в буфер
                                    img_buffer = io.BytesIO()
                                    save_kwargs = {
                                        'format': 'JPEG',
                                        'quality': jpeg_quality,
                                        'optimize': optimize
                                    }
                                    img.save(img_buffer, **save_kwargs)
                                    img_buffer.seek(0)
                                    
                                    # Добавление в архив
                                    cbz.writestr(f"{base_name}.jpg", img_buffer.getvalue())
                                else:
                                    # Копирование оригинального файла
                                    ext = os.path.splitext(image_file)[1].lower()
                                    with open(image_file, 'rb') as f:
                                        cbz.writestr(f"{base_name}{ext}", f.read())
                                        
                        except Exception as e:
                            logger.error(f"Ошибка обработки изображения {image_file}: {e}")
                            
                        progress_var.set(i + 1)
                        progress_window.update_idletasks()
                        
                # Завершение
                if not cancel_var.get():
                    progress_window.destroy()
                    messagebox.showinfo("CBZ архив создан", 
                                    f"Архив успешно создан:\n{output_path}\n\n"
                                    f"Обработано изображений: {len(image_files)}")
                else:
                    progress_window.destroy()
                    # Удаление частично созданного архива
                    try:
                        os.remove(output_path)
                    except:
                        pass
                    messagebox.showinfo("Отменено", "Создание архива отменено")
                    
            except Exception as e:
                progress_window.destroy()
                logger.error(f"Ошибка создания CBZ архива: {e}")
                messagebox.showerror("Ошибка", f"Не удалось создать CBZ архив:\n{e}")
        
        # Запуск в отдельном потоке
        thread = threading.Thread(target=create_archive_thread, daemon=True)
        thread.start()

    def export_with_templates(self):
        """Экспорт с применением различных шаблонов"""
        # Диалог выбора шаблонов для экспорта
        templates_dialog = tk.Toplevel(self.app.root)
        templates_dialog.title("Экспорт с шаблонами")
        templates_dialog.geometry("600x500")
        
        # Центрирование диалога
        templates_dialog.transient(self.app.root)
        templates_dialog.grab_set()
        
        tk.Label(templates_dialog, text="Выберите шаблоны для применения к текущей странице:", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        # Список доступных шаблонов
        templates_frame = tk.Frame(templates_dialog)
        templates_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        templates_listbox = tk.Listbox(templates_frame, selectmode=tk.EXTENDED)
        templates_scrollbar = tk.Scrollbar(templates_frame, orient=tk.VERTICAL, 
                                        command=templates_listbox.yview)
        templates_listbox.configure(yscrollcommand=templates_scrollbar.set)
        
        templates_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        templates_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Заполнение списка шаблонов
        if hasattr(self.app, 'templates_library') and self.app.templates_library:
            for template_id, template in self.app.templates_library.templates.items():
                display_name = f"{template.metadata.name} ({template.metadata.category.value})"
                templates_listbox.insert(tk.END, display_name)
                templates_listbox.insert(tk.END, template_id)  # Скрытый ID
        
        # Настройки экспорта
        settings_frame = tk.LabelFrame(templates_dialog, text="Настройки экспорта")
        settings_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Путь экспорта
        tk.Label(settings_frame, text="Папка экспорта:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        path_frame = tk.Frame(settings_frame)
        path_frame.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        export_path_var = tk.StringVar(value=os.path.expanduser("~/Desktop/manga_templates"))
        path_entry = tk.Entry(path_frame, textvariable=export_path_var, width=40)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        def browse_export_path():
            path = filedialog.askdirectory(title="Выберите папку для экспорта", parent=templates_dialog)
            if path:
                export_path_var.set(path)
                
        tk.Button(path_frame, text="Обзор...", command=browse_export_path).pack(side=tk.RIGHT, padx=(5, 0))
        
        def start_template_export():
            """Запуск экспорта с шаблонами"""
            selected_indices = templates_listbox.curselection()
            if not selected_indices:
                messagebox.showerror("Ошибка", "Выберите хотя бы один шаблон")
                return
                
            if not export_path_var.get():
                messagebox.showerror("Ошибка", "Выберите папку для экспорта")
                return
                
            # Получение выбранных шаблонов
            selected_templates = []
            for index in selected_indices:
                if index % 2 == 1:  # ID шаблона (нечётные индексы)
                    template_id = templates_listbox.get(index)
                    if template_id in self.app.templates_library.templates:
                        selected_templates.append((template_id, self.app.templates_library.templates[template_id]))
            
            if not selected_templates:
                messagebox.showerror("Ошибка", "Не удалось получить выбранные шаблоны")
                return
                
            templates_dialog.destroy()
            
            # Запуск экспорта
            self.export_page_with_multiple_templates(selected_templates, export_path_var.get())
        
        # Кнопки
        buttons_frame = tk.Frame(templates_dialog)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttons_frame, text="Экспорт", command=start_template_export).pack(side=tk.RIGHT, padx=5)
        tk.Button(buttons_frame, text="Отмена", command=templates_dialog.destroy).pack(side=tk.RIGHT)

    def export_page_with_multiple_templates(self, templates_list: list, output_path: str):
        """Экспорт страницы с применением нескольких шаблонов"""
        try:
            # Создание папки экспорта
            export_dir = Path(output_path)
            export_dir.mkdir(parents=True, exist_ok=True)
            
            # Сохранение текущего состояния страницы
            original_panels = copy.deepcopy(self.app.page_constructor.panels)
            
            exported_count = 0
            
            for template_id, template in templates_list:
                try:
                    # Применение шаблона
                    self.app.templates_library.apply_template(template_id)
                    
                    # Формирование имени файла
                    safe_name = "".join(c for c in template.metadata.name if c.isalnum() or c in (' ', '-', '_')).strip()
                    filename = f"page_with_{safe_name}.png"
                    filepath = export_dir / filename
                    
                    # Временная настройка экспорта
                    temp_settings = ExportSettings(
                        format=ExportFormat.PNG,
                        dpi=300,
                        output_path=str(export_dir),
                        filename_template=f"page_with_{safe_name}",
                        include_metadata=True
                    )
                    
                    # Сохранение оригинальных настроек
                    original_settings = self.settings
                    self.settings = temp_settings
                    
                    # Экспорт
                    success = self.export_current_page()
                    
                    if success:
                        exported_count += 1
                        
                    # Восстановление настроек
                    self.settings = original_settings
                    
                except Exception as e:
                    logger.error(f"Ошибка экспорта с шаблоном {template_id}: {e}")
                    
            # Восстановление оригинального состояния страницы
            self.app.page_constructor.panels = original_panels
            self.app.page_constructor.redraw()
            
            # Показ результатов
            if exported_count > 0:
                messagebox.showinfo("Экспорт завершён", 
                                f"Экспортировано вариантов: {exported_count}\n"
                                f"Путь: {output_path}")
            else:
                messagebox.showerror("Ошибка", "Не удалось экспортировать ни одного варианта")
                
        except Exception as e:
            logger.error(f"Ошибка экспорта с шаблонами: {e}")
            messagebox.showerror("Ошибка", f"Ошибка экспорта с шаблонами:\n{e}")

    def create_animated_gif(self):
        """Создание анимированного GIF из последовательности страниц"""
        # Заглушка для будущей функциональности
        messagebox.showinfo("В разработке", 
                        "Функция создания анимированных GIF будет добавлена в следующей версии.\n"
                        "Планируется поддержка:\n"
                        "• Анимация переходов между панелями\n"
                        "• Эффекты появления текста\n"
                        "• Анимированные речевые пузыри")
        
    def export_for_web(self):
        """Экспорт оптимизированный для веб-публикации"""
        # Диалог веб-экспорта
        web_dialog = tk.Toplevel(self.app.root)
        web_dialog.title("Экспорт для веб")
        web_dialog.geometry("400x300")
        web_dialog.resizable(False, False)
        
        # Центрирование диалога
        web_dialog.transient(self.app.root)
        web_dialog.grab_set()
        
        tk.Label(web_dialog, text="Настройки веб-экспорта", 
                font=("Arial", 12, "bold")).pack(pady=10)
        
        # Настройки веб-экспорта
        settings_frame = tk.LabelFrame(web_dialog, text="Параметры")
        settings_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Размер для веб
        tk.Label(settings_frame, text="Ширина (пикселей):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        web_width_var = tk.IntVar(value=800)
        tk.Entry(settings_frame, textvariable=web_width_var, width=10).grid(row=0, column=1, padx=5, pady=5)
        
        # Качество
        tk.Label(settings_frame, text="Качество JPEG:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        web_quality_var = tk.IntVar(value=85)
        tk.Scale(settings_frame, from_=50, to=100, variable=web_quality_var, 
                orient=tk.HORIZONTAL, length=150).grid(row=1, column=1, padx=5, pady=5)
        
        # Формат
        tk.Label(settings_frame, text="Формат:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        web_format_var = tk.StringVar(value="JPEG")
        format_combo = tk.ttk.Combobox(settings_frame, textvariable=web_format_var,
                                    values=["JPEG", "PNG", "WEBP"], state="readonly")
        format_combo.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Оптимизация
        optimize_var = tk.BooleanVar(value=True)
        tk.Checkbutton(settings_frame, text="Оптимизировать для скорости загрузки", 
                    variable=optimize_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        
        def export_for_web_start():
            """Запуск веб-экспорта"""
            web_dialog.destroy()
            
            # Настройки веб-экспорта
            web_settings = ExportSettings(
                format=ExportFormat(web_format_var.get()),
                dpi=72,  # Веб DPI
                jpeg_quality=web_quality_var.get(),
                anti_aliasing=True,
                include_metadata=False,  # Для веб метаданные не нужны
                filename_template="web_page"
            )
            
            # Пока применяем к текущей странице
            original_settings = self.settings
            self.settings = web_settings
            
            success = self.export_current_page()
            
            if success:
                messagebox.showinfo("Веб-экспорт завершён", 
                                "Страница экспортирована для веб-публикации")
            
            self.settings = original_settings
        
        # Кнопки
        buttons_frame = tk.Frame(web_dialog)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Button(buttons_frame, text="Экспорт", command=export_for_web_start).pack(side=tk.RIGHT, padx=5)
        tk.Button(buttons_frame, text="Отмена", command=web_dialog.destroy).pack(side=tk.RIGHT)
        
    def quick_export(self, format_type: ExportFormat = ExportFormat.PNG, 
                    quality: ExportQuality = ExportQuality.PRINT) -> bool:
        """Быстрый экспорт без диалога настроек"""
        try:
            # Базовые настройки для быстрого экспорта
            self.settings.format = format_type
            self.settings.quality = quality
            
            # Установка DPI в зависимости от качества
            if quality == ExportQuality.WEB:
                self.settings.dpi = 72
            elif quality == ExportQuality.PRINT:
                self.settings.dpi = 300
            elif quality == ExportQuality.HIGH:
                self.settings.dpi = 600
                
            # Путь сохранения
            if not self.settings.output_path:
                self.settings.output_path = os.path.expanduser("~/Desktop")
                
            # Запуск экспорта
            return self.export_current_page()
            
        except Exception as e:
            logger.error(f"Ошибка быстрого экспорта: {e}")
            return False
            
    def get_export_formats_info(self) -> Dict[str, str]:
        """Получение информации о поддерживаемых форматах"""
        return {
            "PNG": "Растровый формат с поддержкой прозрачности. Лучший выбор для веб-публикации.",
            "JPEG": "Сжатый растровый формат. Хорош для печати, но без прозрачности.",
            "PDF": "Векторный формат документов. Идеален для печати и профессионального использования.",
            "CBZ": "Архив комиксов. Стандартный формат для цифровых комиксов и манги.",
            "TIFF": "Профессиональный растровый формат. Используется в полиграфии.",
            "BMP": "Несжатый растровый формат. Большой размер файла.",
            "WEBP": "Современный веб-формат с хорошим сжатием."
        }
        
    def cleanup(self):
        """Очистка ресурсов"""
        # Завершение потока экспорта
        self.cancel_export = True
        
        if self.export_thread and self.export_thread.is_alive():
            self.export_thread.join(timeout=1)
            
        # Очистка кэша шрифтов
        self.fonts_cache.clear()
        
        # Закрытие окон
        if self.export_window and self.export_window.winfo_exists():
            self.export_window.destroy()
            
        if self.progress_window and self.progress_window.winfo_exists():
            self.progress_window.destroy()
            
        logger.info("Менеджер экспорта очищен")