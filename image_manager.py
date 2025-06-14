#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - менеджер изображений
Профессиональная работа с изображениями, обрезка, библиотека контента
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, Canvas
import os
import shutil
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import json
import hashlib
from PIL import Image, ImageTk, ImageDraw, ImageFilter as PilImageFilter, ImageEnhance, ImageOps
import threading
import queue
import time

# Импорт из наших модулей
from utils import (logger, get_app_data_dir, get_temp_dir, ensure_directory, 
                   safe_filename, resize_image_to_fit, crop_image_to_panel, 
                   smart_crop, load_json_file, save_json_file)
from page_constructor import Panel


class CropMode(Enum):
    """Режимы обрезки изображений"""
    CENTER = "center"           # Центрированная обрезка
    SMART = "smart"            # Умная обрезка (сохранение важных деталей)
    MANUAL = "manual"          # Ручная обрезка
    FIT = "fit"               # Подгонка с сохранением пропорций
    STRETCH = "stretch"        # Растягивание (искажение пропорций)
    TOP = "top"               # Обрезка сверху
    BOTTOM = "bottom"         # Обрезка снизу
    LEFT = "left"             # Обрезка слева
    RIGHT = "right"           # Обрезка справа


class ImageFilterType(Enum):
    """Фильтры изображений"""
    NONE = "none"
    GRAYSCALE = "grayscale"
    SEPIA = "sepia"
    HIGH_CONTRAST = "high_contrast"
    SOFT_BLUR = "soft_blur"
    SHARPEN = "sharpen"
    EDGE_ENHANCE = "edge_enhance"
    VINTAGE = "vintage"
    DRAMATIC = "dramatic"


@dataclass
class ImageMetadata:
    """Метаданные изображения"""
    filename: str
    original_path: str
    cached_path: str
    width: int
    height: int
    file_size: int
    format: str
    created_date: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    usage_count: int = 0
    dominant_colors: List[str] = field(default_factory=list)
    is_favorite: bool = False


@dataclass
class CropSettings:
    """Настройки обрезки"""
    mode: CropMode = CropMode.SMART
    manual_crop_rect: Optional[Tuple[int, int, int, int]] = None
    preserve_aspect: bool = True
    apply_filter: ImageFilterType = ImageFilterType.NONE
    brightness: float = 1.0
    contrast: float = 1.0
    saturation: float = 1.0
    rotation: float = 0.0


class ImageLibrary:
    """Библиотека изображений проекта"""
    
    def __init__(self, library_path: Path):
        self.library_path = ensure_directory(library_path)
        self.cache_path = ensure_directory(library_path / "cache")
        self.thumbs_path = ensure_directory(library_path / "thumbnails")
        
        self.images: Dict[str, ImageMetadata] = {}
        self.load_library()
        
    def load_library(self):
        """Загрузка библиотеки из файла"""
        library_file = self.library_path / "library.json"
        if library_file.exists():
            data = load_json_file(library_file)
            if data:
                for img_id, img_data in data.get("images", {}).items():
                    self.images[img_id] = ImageMetadata(**img_data)
                    
        logger.info(f"Загружена библиотека: {len(self.images)} изображений")
        
    def save_library(self):
        """Сохранение библиотеки в файл"""
        library_file = self.library_path / "library.json"
        data = {
            "version": "1.0",
            "images": {img_id: img.__dict__ for img_id, img in self.images.items()}
        }
        save_json_file(data, library_file)
        
    def add_image(self, image_path: Union[str, Path]) -> Optional[str]:
        """Добавление изображения в библиотеку"""
        try:
            image_path = Path(image_path)
            if not image_path.exists():
                logger.error(f"Файл не найден: {image_path}")
                return None
                
            # Генерация уникального ID
            with open(image_path, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
                
            # Проверка на дубликаты
            for img_id, metadata in self.images.items():
                if img_id.startswith(file_hash):
                    logger.info(f"Изображение уже в библиотеке: {metadata.filename}")
                    return img_id
                    
            # Копирование в кэш
            cached_filename = f"{file_hash}_{safe_filename(image_path.name)}"
            cached_path = self.cache_path / cached_filename
            shutil.copy2(image_path, cached_path)
            
            # Получение метаданных
            with Image.open(cached_path) as img:
                metadata = ImageMetadata(
                    filename=image_path.name,
                    original_path=str(image_path),
                    cached_path=str(cached_path),
                    width=img.width,
                    height=img.height,
                    file_size=image_path.stat().st_size,
                    format=img.format or "Unknown",
                    created_date=time.strftime("%Y-%m-%d %H:%M:%S"),
                    dominant_colors=self.extract_dominant_colors(img)
                )
                
            # Создание миниатюры
            self.create_thumbnail(file_hash, cached_path)
            
            # Сохранение в библиотеку
            self.images[file_hash] = metadata
            self.save_library()
            
            logger.info(f"Добавлено изображение: {metadata.filename}")
            return file_hash
            
        except Exception as e:
            logger.error(f"Ошибка добавления изображения {image_path}: {e}")
            return None
            
    def create_thumbnail(self, image_id: str, image_path: Path, size: Tuple[int, int] = (150, 150)):
        """Создание миниатюры"""
        try:
            thumb_path = self.thumbs_path / f"{image_id}_thumb.jpg"
            
            with Image.open(image_path) as img:
                # Создание миниатюры с сохранением пропорций
                img.thumbnail(size, Image.Resampling.LANCZOS)
                
                # Создание квадратной миниатюры с центрированием
                thumb = Image.new('RGB', size, (255, 255, 255))
                paste_x = (size[0] - img.width) // 2
                paste_y = (size[1] - img.height) // 2
                thumb.paste(img, (paste_x, paste_y))
                
                thumb.save(thumb_path, "JPEG", quality=85)
                
        except Exception as e:
            logger.error(f"Ошибка создания миниатюры для {image_id}: {e}")
            
    def extract_dominant_colors(self, image: Image.Image, num_colors: int = 5) -> List[str]:
        """Извлечение доминирующих цветов"""
        try:
            # Уменьшение изображения для ускорения
            small_img = image.resize((50, 50))
            
            # Квантизация цветов
            quantized = small_img.quantize(colors=num_colors)
            palette = quantized.getpalette()
            
            # Извлечение RGB значений
            colors = []
            for i in range(num_colors):
                r = palette[i * 3]
                g = palette[i * 3 + 1] 
                b = palette[i * 3 + 2]
                colors.append(f"#{r:02x}{g:02x}{b:02x}")
                
            return colors
            
        except Exception:
            return ["#808080"]  # Серый по умолчанию
            
    def get_thumbnail_path(self, image_id: str) -> Optional[Path]:
        """Получение пути к миниатюре"""
        thumb_path = self.thumbs_path / f"{image_id}_thumb.jpg"
        return thumb_path if thumb_path.exists() else None
        
    def remove_image(self, image_id: str):
        """Удаление изображения из библиотеки"""
        if image_id in self.images:
            metadata = self.images[image_id]
            
            # Удаление файлов
            try:
                if Path(metadata.cached_path).exists():
                    Path(metadata.cached_path).unlink()
                    
                thumb_path = self.get_thumbnail_path(image_id)
                if thumb_path and thumb_path.exists():
                    thumb_path.unlink()
                    
            except Exception as e:
                logger.error(f"Ошибка удаления файлов для {image_id}: {e}")
                
            # Удаление из библиотеки
            del self.images[image_id]
            self.save_library()
            
            logger.info(f"Удалено изображение: {metadata.filename}")
            
    def search_images(self, query: str = "", tags: List[str] = None, 
                     format_filter: str = None) -> List[str]:
        """Поиск изображений по критериям"""
        results = []
        
        for img_id, metadata in self.images.items():
            # Поиск по имени и описанию
            if query and query.lower() not in metadata.filename.lower() and \
               query.lower() not in metadata.description.lower():
                continue
                
            # Фильтр по тегам
            if tags and not any(tag in metadata.tags for tag in tags):
                continue
                
            # Фильтр по формату
            if format_filter and metadata.format.upper() != format_filter.upper():
                continue
                
            results.append(img_id)
            
        # Сортировка по популярности
        results.sort(key=lambda x: self.images[x].usage_count, reverse=True)
        return results


class ImageManager:
    """Главный менеджер изображений"""
    
    def __init__(self, app_instance):
        self.app = app_instance
        
        # Инициализация библиотеки
        library_path = get_app_data_dir() / "image_library"
        self.library = ImageLibrary(library_path)
        
        # Кэш загруженных изображений
        self.image_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.thumbnail_cache: Dict[str, ImageTk.PhotoImage] = {}
        
        # Настройки
        self.max_cache_size = 50  # Максимум изображений в кэше
        self.thumbnail_size = (150, 150)
        
        # UI компоненты
        self.image_window = None
        self.selected_images: List[str] = []
        
        # Очередь для фоновых операций
        self.task_queue = queue.Queue()
        self.worker_thread = None
        self.start_worker_thread()
        
    def start_worker_thread(self):
        """Запуск фонового потока для обработки изображений"""
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()
        
    def worker_loop(self):
        """Основной цикл фонового потока"""
        while True:
            try:
                task = self.task_queue.get(timeout=1)
                if task is None:  # Сигнал завершения
                    break
                    
                task_type, args = task
                
                if task_type == "create_thumbnail":
                    self.library.create_thumbnail(*args)
                elif task_type == "process_image":
                    self.process_image_background(*args)
                    
                self.task_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Ошибка в фоновом потоке: {e}")
                
    def show_image_library(self):
        """Показ окна библиотеки изображений"""
        if self.image_window and self.image_window.winfo_exists():
            self.image_window.lift()
            return
            
        self.image_window = tk.Toplevel(self.app.root)
        self.image_window.title("Библиотека изображений")
        self.image_window.geometry("900x750")
        
        self.setup_image_library_ui()
        self.refresh_image_grid()
        
    def setup_image_library_ui(self):
        """Настройка интерфейса библиотеки"""
        # Панель инструментов
        toolbar = ttk.Frame(self.image_window)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # Кнопки действий
        ttk.Button(toolbar, text="Добавить изображения", 
                  command=self.import_images).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Добавить папку", 
                  command=self.import_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Удалить выбранные", 
                  command=self.delete_selected_images).pack(side=tk.LEFT, padx=2)
        
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        # Поиск и фильтры
        ttk.Label(toolbar, text="Поиск:").pack(side=tk.LEFT, padx=(0, 2))
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.on_search_change)
        search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=2)
        
        ttk.Label(toolbar, text="Формат:").pack(side=tk.LEFT, padx=(10, 2))
        self.format_var = tk.StringVar()
        format_combo = ttk.Combobox(toolbar, textvariable=self.format_var, 
                                   values=["Все", "JPEG", "PNG", "GIF", "BMP"], 
                                   state="readonly", width=10)
        format_combo.set("Все")
        format_combo.bind('<<ComboboxSelected>>', self.on_filter_change)
        format_combo.pack(side=tk.LEFT, padx=2)
        
        # Режим просмотра
        ttk.Label(toolbar, text="Вид:").pack(side=tk.LEFT, padx=(10, 2))
        self.view_mode = tk.StringVar(value="grid")
        ttk.Radiobutton(toolbar, text="Сетка", variable=self.view_mode, 
                       value="grid", command=self.change_view_mode).pack(side=tk.LEFT)
        ttk.Radiobutton(toolbar, text="Список", variable=self.view_mode, 
                       value="list", command=self.change_view_mode).pack(side=tk.LEFT)
        
        # Главная область
        main_paned = ttk.PanedWindow(self.image_window, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Левая панель - сетка изображений
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=3)
        
        # Canvas с прокруткой для изображений
        canvas_frame = ttk.Frame(left_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        self.images_canvas = Canvas(canvas_frame, bg="white")
        v_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.images_canvas.yview)
        h_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.images_canvas.xview)
        
        self.images_canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        
        self.images_frame = ttk.Frame(self.images_canvas)
        self.images_canvas.create_window((0, 0), window=self.images_frame, anchor="nw")
        
        self.images_canvas.grid(row=0, column=0, sticky="nsew")
        v_scroll.grid(row=0, column=1, sticky="ns")
        h_scroll.grid(row=1, column=0, sticky="ew")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Правая панель - предпросмотр и настройки
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)
        
        # Предпросмотр
        preview_frame = ttk.LabelFrame(right_frame, text="Предпросмотр")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.preview_canvas = Canvas(preview_frame, width=250, height=250, bg="white")
        self.preview_canvas.pack(padx=5, pady=5)
        
        # Информация об изображении
        info_frame = ttk.LabelFrame(right_frame, text="Информация")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.info_text = tk.Text(info_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self.info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Настройки обрезки
        crop_frame = ttk.LabelFrame(right_frame, text="Настройки применения")
        crop_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Режим обрезки
        ttk.Label(crop_frame, text="Режим обрезки:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.crop_mode_var = tk.StringVar(value="smart")
        crop_combo = ttk.Combobox(crop_frame, textvariable=self.crop_mode_var,
                                 values=["center", "smart", "fit", "stretch", "top", "bottom", "left", "right"],
                                 state="readonly", width=15)
        crop_combo.grid(row=0, column=1, padx=5, pady=2)
        
        # Фильтры
        ttk.Label(crop_frame, text="Фильтр:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.filter_var = tk.StringVar(value="none")
        filter_combo = ttk.Combobox(crop_frame, textvariable=self.filter_var,
                                   values=[f.value for f in ImageFilterType],
                                   state="readonly", width=15)
        filter_combo.grid(row=1, column=1, padx=5, pady=2)
        
        # Кнопки применения
        buttons_frame = ttk.Frame(crop_frame)
        buttons_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        ttk.Button(buttons_frame, text="Применить к выбранной панели", 
                  command=self.apply_to_selected_panel).pack(fill=tk.X, pady=2)
        ttk.Button(buttons_frame, text="Настроить обрезку", 
                  command=self.open_crop_editor).pack(fill=tk.X, pady=2)
        
        # Переменные состояния
        self.selected_image_id = None
        
    def refresh_image_grid(self):
        """Обновление сетки изображений"""
        # Очистка текущих виджетов
        for widget in self.images_frame.winfo_children():
            widget.destroy()
            
        # Получение отфильтрованного списка
        search_query = self.search_var.get() if hasattr(self, 'search_var') else ""
        format_filter = self.format_var.get() if hasattr(self, 'format_var') and self.format_var.get() != "Все" else None
        
        image_ids = self.library.search_images(search_query, format_filter=format_filter)
        
        if not image_ids:
            no_images_label = ttk.Label(self.images_frame, text="Нет изображений")
            no_images_label.pack(pady=50)
            return
            
        # Отображение в зависимости от режима
        if self.view_mode.get() == "grid":
            self.create_image_grid(image_ids)
        else:
            self.create_image_list(image_ids)
            
        # Обновление области прокрутки
        self.images_frame.update_idletasks()
        self.images_canvas.configure(scrollregion=self.images_canvas.bbox("all"))
        
    def create_image_grid(self, image_ids: List[str]):
        """Создание сетки изображений"""
        columns = 4
        
        for i, image_id in enumerate(image_ids):
            row = i // columns
            col = i % columns
            
            self.create_image_tile(image_id, row, col)
            
    def create_image_tile(self, image_id: str, row: int, col: int):
        """Создание плитки изображения"""
        metadata = self.library.images[image_id]
        
        # Контейнер плитки
        tile_frame = ttk.Frame(self.images_frame, relief=tk.RAISED, borderwidth=1)
        tile_frame.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")
        
        # Загрузка миниатюры
        thumbnail = self.get_thumbnail(image_id)
        
        # Canvas для изображения
        img_canvas = Canvas(tile_frame, width=150, height=150, highlightthickness=0)
        img_canvas.pack()
        
        if thumbnail:
            img_canvas.create_image(75, 75, image=thumbnail)
            
        # Подпись
        name_label = ttk.Label(tile_frame, text=metadata.filename[:20] + "..." if len(metadata.filename) > 20 else metadata.filename,
                              font=("Arial", 8))
        name_label.pack()
        
        # Дополнительная информация
        info_text = f"{metadata.width}×{metadata.height}"
        if metadata.is_favorite:
            info_text = "★ " + info_text
            
        info_label = ttk.Label(tile_frame, text=info_text, font=("Arial", 7), foreground="#666666")
        info_label.pack()
        
        # Обработка событий
        def on_select():
            self.select_image(image_id)
            # Выделение выбранной плитки
            for child in self.images_frame.winfo_children():
                if isinstance(child, ttk.Frame):
                    child.configure(relief=tk.RAISED)
            tile_frame.configure(relief=tk.SUNKEN)
            
        def on_double_click():
            self.apply_to_selected_panel()
            
        tile_frame.bind("<Button-1>", lambda e: on_select())
        img_canvas.bind("<Button-1>", lambda e: on_select())
        name_label.bind("<Button-1>", lambda e: on_select())
        img_canvas.bind("<Double-Button-1>", lambda e: on_double_click())
        
    def create_image_list(self, image_ids: List[str]):
        """Создание списочного представления"""
        for i, image_id in enumerate(image_ids):
            metadata = self.library.images[image_id]
            
            # Строка списка
            row_frame = ttk.Frame(self.images_frame)
            row_frame.pack(fill=tk.X, padx=2, pady=1)
            
            # Маленькая миниатюра
            thumb_label = ttk.Label(row_frame, text="[IMG]", width=8)
            thumb_label.pack(side=tk.LEFT, padx=5)
            
            # Информация
            info_frame = ttk.Frame(row_frame)
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            
            name_label = ttk.Label(info_frame, text=metadata.filename, font=("Arial", 9, "bold"))
            name_label.pack(anchor=tk.W)
            
            details = f"{metadata.width}×{metadata.height} | {metadata.format} | {metadata.file_size // 1024}KB"
            details_label = ttk.Label(info_frame, text=details, font=("Arial", 8))
            details_label.pack(anchor=tk.W)
            
            # Обработка событий
            def on_select(img_id=image_id):
                self.select_image(img_id)
                
            row_frame.bind("<Button-1>", lambda e, img_id=image_id: on_select(img_id))
            
    def get_thumbnail(self, image_id: str) -> Optional[ImageTk.PhotoImage]:
        """Получение миниатюры с кэшированием"""
        if image_id in self.thumbnail_cache:
            return self.thumbnail_cache[image_id]
            
        thumb_path = self.library.get_thumbnail_path(image_id)
        if thumb_path and thumb_path.exists():
            try:
                with Image.open(thumb_path) as img:
                    photo = ImageTk.PhotoImage(img)
                    self.thumbnail_cache[image_id] = photo
                    return photo
            except Exception as e:
                logger.error(f"Ошибка загрузки миниатюры {image_id}: {e}")
                
        return None
        
    def select_image(self, image_id: str):
        """Выбор изображения"""
        self.selected_image_id = image_id
        self.update_preview(image_id)
        self.update_image_info(image_id)
        
    def update_preview(self, image_id: str):
        """Обновление предпросмотра"""
        if not hasattr(self, 'preview_canvas'):
            return
            
        self.preview_canvas.delete("all")
        
        metadata = self.library.images[image_id]
        
        try:
            with Image.open(metadata.cached_path) as img:
                # Изменение размера для предпросмотра
                preview_size = (240, 240)
                img.thumbnail(preview_size, Image.Resampling.LANCZOS)
                
                photo = ImageTk.PhotoImage(img)
                
                # Центрирование на canvas
                x = (250 - img.width) // 2
                y = (250 - img.height) // 2
                
                self.preview_canvas.create_image(x, y, image=photo, anchor="nw")
                
                # Сохранение ссылки для предотвращения сборки мусора
                self.preview_canvas.image = photo
                
        except Exception as e:
            logger.error(f"Ошибка предпросмотра {image_id}: {e}")
            self.preview_canvas.create_text(125, 125, text="Ошибка загрузки", anchor="center")
            
    def update_image_info(self, image_id: str):
        """Обновление информации об изображении"""
        if not hasattr(self, 'info_text'):
            return
            
        metadata = self.library.images[image_id]
        
        info = f"""Файл: {metadata.filename}
Размер: {metadata.width} × {metadata.height}
Формат: {metadata.format}
Размер файла: {metadata.file_size // 1024} KB
Использований: {metadata.usage_count}
Добавлен: {metadata.created_date}
Теги: {', '.join(metadata.tags) if metadata.tags else 'Нет'}
Описание: {metadata.description or 'Нет описания'}"""

        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, info)
        self.info_text.configure(state=tk.DISABLED)
        
    def import_images(self):
        """Импорт изображений"""
        file_types = [
            ("Изображения", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
            ("PNG файлы", "*.png"),
            ("JPEG файлы", "*.jpg *.jpeg"),
            ("Все файлы", "*.*")
        ]
        
        files = filedialog.askopenfilenames(
            title="Выберите изображения",
            filetypes=file_types
        )
        
        if files:
            self.import_files_with_progress(files)
            
    def import_folder(self):
        """Импорт папки с изображениями"""
        folder = filedialog.askdirectory(title="Выберите папку с изображениями")
        
        if folder:
            # Поиск изображений в папке
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}
            files = []
            
            for file_path in Path(folder).rglob("*"):
                if file_path.suffix.lower() in image_extensions:
                    files.append(str(file_path))
                    
            if files:
                self.import_files_with_progress(files)
            else:
                messagebox.showinfo("Информация", "В выбранной папке не найдено изображений")
                
    def import_files_with_progress(self, files: List[str]):
        """Импорт файлов с прогрессом"""
        # Создание окна прогресса
        progress_window = tk.Toplevel(self.image_window)
        progress_window.title("Импорт изображений")
        progress_window.geometry("400x150")
        progress_window.resizable(False, False)
        
        ttk.Label(progress_window, text="Импорт изображений...").pack(pady=10)
        
        progress_var = tk.DoubleVar()
        progress_bar = ttk.Progressbar(progress_window, variable=progress_var, maximum=len(files))
        progress_bar.pack(fill=tk.X, padx=20, pady=10)
        
        status_label = ttk.Label(progress_window, text="")
        status_label.pack()
        
        # Импорт в отдельном потоке
        def import_thread():
            imported = 0
            for i, file_path in enumerate(files):
                try:
                    status_label.config(text=f"Обработка: {Path(file_path).name}")
                    progress_window.update_idletasks()
                    
                    result = self.library.add_image(file_path)
                    if result:
                        imported += 1
                        
                    progress_var.set(i + 1)
                    progress_window.update_idletasks()
                    
                except Exception as e:
                    logger.error(f"Ошибка импорта {file_path}: {e}")
                    
            # Завершение
            progress_window.destroy()
            messagebox.showinfo("Импорт завершён", f"Импортировано изображений: {imported} из {len(files)}")
            self.refresh_image_grid()
            
        threading.Thread(target=import_thread, daemon=True).start()
        
    def apply_to_selected_panel(self):
        """Применение изображения к выбранной панели"""
        if not self.selected_image_id:
            messagebox.showwarning("Предупреждение", "Выберите изображение")
            return
            
        # Получение выбранной панели
        selected_panels = self.app.page_constructor.selected_panels
        if not selected_panels:
            messagebox.showwarning("Предупреждение", "Выберите панель на странице")
            return
            
        panel = selected_panels[0]  # Применяем к первой выбранной панели
        
        # Применение изображения с настройками
        self.apply_image_to_panel(self.selected_image_id, panel)
        
        # Закрытие окна библиотеки
        if self.image_window:
            self.image_window.destroy()
            
    def apply_image_to_panel(self, image_id: str, panel: Panel): # panel теперь типа page_constructor.Panel
        """Применение изображения к панели с обрезкой."""
        try:
            metadata = self.library.images[image_id]
            
            # Настройки обрезки из UI ImageManager'а для ПЕРВОНАЧАЛЬНОГО размещения
            crop_settings = CropSettings(
                mode=CropMode(self.crop_mode_var.get() if hasattr(self, "crop_mode_var") else "smart"),
                apply_filter=ImageFilterType(self.filter_var.get() if hasattr(self, "filter_var") else "none")
            )
            
            # Обработка изображения (масштабирование, фильтры) для ПОЛУЧЕНИЯ ОСНОВНОГО ИЗОБРАЖЕНИЯ ПАНЕЛИ
            # Это изображение будет иметь размеры panel.width и panel.height (в единицах страницы)
            # process_image_for_panel ВОЗВРАЩАЕТ PIL.Image
            processed_pil_image = self.process_image_for_panel(metadata.cached_path, panel, crop_settings)
            
            if processed_pil_image:
                # Сохранение обработанного изображения во временный файл (как раньше)
                # или можно придумать систему кэширования получше, но пока так.
                # Важно, чтобы panel.content_image указывал на этот файл.
                panel_image_filename = f"panel_img_{panel.id}_{image_id}.png" # Уникальное имя
                temp_image_path = get_temp_dir() / panel_image_filename
                
                # Убедимся, что директория существует
                ensure_directory(temp_image_path.parent)
                
                processed_pil_image.save(temp_image_path, "PNG") # Сохраняем в PNG для поддержки прозрачности
                
                # Установка изображения в панель
                panel.content_image = str(temp_image_path)
                panel.reset_image_transform() # Сброс смещения и масштаба кадрирования

                # Обновление кэшей в PageConstructor
                # Очищаем старый PIL Image для этой панели, если был
                self.app.page_constructor.clear_specific_pil_image_cache(panel.id)
                # Загружаем новый PIL Image в кэш PageConstructor
                self.app.page_constructor.pil_image_cache[panel.id] = {
                    'path': panel.content_image, 
                    'image': processed_pil_image.copy()
                }
                # Очищаем кэш PhotoImage, т.к. контент изменился
                self.app.page_constructor.clear_specific_image_tk_cache(panel.id)
                panel.mark_visuals_for_update() # Флаг для перерисовки

                # Увеличение счётчика использования
                metadata.usage_count += 1
                self.library.save_library()
                
                # Обновление отображения
                self.app.page_constructor.save_history_state()
                self.app.page_constructor.redraw()
                self.app.set_status(f"Изображение '{metadata.filename}' применено к панели {panel.id[:8]}")
                self.app.project_modified = True
                self.app.update_title()
                
                logger.info(f"Изображение {image_id} применено к панели {panel.id} как {temp_image_path}")

                # Закрытие окна библиотеки, если оно было вызвано для конкретной панели
                if hasattr(self, '_target_panel_for_image_selection') and self._target_panel_for_image_selection == panel:
                    if self.image_window and self.image_window.winfo_exists():
                        self.image_window.destroy()
                    self._target_panel_for_image_selection = None

            else:
                messagebox.showerror("Ошибка", "Не удалось обработать изображение для панели.")
                
        except Exception as e:
            logger.error(f"Ошибка применения изображения {image_id} к панели {panel.id}: {e}")
            messagebox.showerror("Ошибка", f"Не удалось применить изображение: {e}")
            
    def process_image_for_panel(self, image_path: str, panel: Panel, 
                               settings: CropSettings) -> Optional[Image.Image]:
        """Обработка изображения для панели"""
        try:
            with Image.open(image_path) as img:
                # Целевые размеры панели (в пикселях)
                target_width = int(panel.width)
                target_height = int(panel.height)
                
                # Обрезка в зависимости от режима
                if settings.mode == CropMode.FIT:
                    # Подгонка с сохранением пропорций
                    processed = resize_image_to_fit(image_path, target_width, target_height, True)
                elif settings.mode == CropMode.STRETCH:
                    # Растягивание
                    processed = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                elif settings.mode == CropMode.CENTER:
                    # Центрированная обрезка
                    processed = crop_image_to_panel(img, (0, 0, target_width, target_height), "center")
                elif settings.mode == CropMode.SMART:
                    # Умная обрезка
                    processed = crop_image_to_panel(img, (0, 0, target_width, target_height), "smart")
                else:
                    # Другие режимы обрезки
                    processed = self.apply_directional_crop(img, target_width, target_height, settings.mode)
                    
                # Применение фильтров
                if settings.apply_filter != ImageFilterType.NONE:
                    processed = self.apply_image_filter(processed, settings.apply_filter)
                    
                # Применение коррекций
                if settings.brightness != 1.0:
                    enhancer = ImageEnhance.Brightness(processed)
                    processed = enhancer.enhance(settings.brightness)
                    
                if settings.contrast != 1.0:
                    enhancer = ImageEnhance.Contrast(processed)
                    processed = enhancer.enhance(settings.contrast)
                    
                if settings.saturation != 1.0:
                    enhancer = ImageEnhance.Color(processed)
                    processed = enhancer.enhance(settings.saturation)
                    
                return processed
                
        except Exception as e:
            logger.error(f"Ошибка обработки изображения {image_path}: {e}")
            return None
            
    def apply_directional_crop(self, img: Image.Image, width: int, height: int, mode: CropMode) -> Image.Image:
        """Применение направленной обрезки"""
        # Изменение размера с сохранением пропорций
        img_ratio = img.width / img.height
        target_ratio = width / height
        
        if img_ratio > target_ratio:
            new_height = height
            new_width = int(height * img_ratio)
        else:
            new_width = width
            new_height = int(width / img_ratio)
            
        resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Обрезка в зависимости от направления
        if mode == CropMode.TOP:
            left = (new_width - width) // 2
            top = 0
        elif mode == CropMode.BOTTOM:
            left = (new_width - width) // 2
            top = new_height - height
        elif mode == CropMode.LEFT:
            left = 0
            top = (new_height - height) // 2
        elif mode == CropMode.RIGHT:
            left = new_width - width
            top = (new_height - height) // 2
        else:
            # По умолчанию центр
            left = (new_width - width) // 2
            top = (new_height - height) // 2
            
        return resized.crop((left, top, left + width, top + height))
        
    def apply_image_filter(self,
                        img: Image.Image,
                        filter_type: ImageFilterType) -> Image.Image:
        """
        Применяет выбранный фильтр к изображению.
        filter_type — элемент перечисления ImageFilterType.
        """
        if filter_type == ImageFilterType.GRAYSCALE:
            return ImageOps.grayscale(img).convert("RGB")

        elif filter_type == ImageFilterType.SEPIA:
            # лёгкий тёплый тон
            sepia = ImageOps.colorize(ImageOps.grayscale(img), "#704214", "#FFE4B5")
            return sepia

        elif filter_type == ImageFilterType.HIGH_CONTRAST:
            return ImageEnhance.Contrast(img).enhance(1.5)

        elif filter_type == ImageFilterType.SOFT_BLUR:
            return img.filter(PilImageFilter.GaussianBlur(radius=1))

        elif filter_type == ImageFilterType.SHARPEN:
            return img.filter(PilImageFilter.SHARPEN)

        elif filter_type == ImageFilterType.EDGE_ENHANCE:
            return img.filter(PilImageFilter.EDGE_ENHANCE)

        elif filter_type == ImageFilterType.VINTAGE:
            return ImageEnhance.Color(
                ImageOps.colorize(ImageOps.grayscale(img), "#5f4b32", "#f0e0c0")
            ).enhance(0.8)

        elif filter_type == ImageFilterType.DRAMATIC:
            return ImageEnhance.Color(
                ImageEnhance.Contrast(img).enhance(1.3)
            ).enhance(0.6)

        # ImageFilterType.NONE
        return img
            
    def apply_sepia_filter(self, img: Image.Image) -> Image.Image:
        """Применение сепия фильтра"""
        pixels = img.load()
        width, height = img.size
        
        for py in range(height):
            for px in range(width):
                r, g, b = pixels[px, py][:3]
                
                tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                
                pixels[px, py] = (min(255, tr), min(255, tg), min(255, tb))
                
        return img
        
    def apply_vintage_filter(self, img: Image.Image) -> Image.Image:
        """Применение винтажного фильтра"""
        # Снижение контрастности и добавление тёплых тонов
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(0.8)
        
        brightness = ImageEnhance.Brightness(img)
        img = brightness.enhance(1.1)
        
        # Лёгкое размытие
        img = img.filter(PilImageFilter.GaussianBlur(radius=0.5))
        
        return img
        
    def apply_dramatic_filter(self, img: Image.Image) -> Image.Image:
        """Применение драматического фильтра"""
        # Увеличение контрастности
        contrast = ImageEnhance.Contrast(img)
        img = contrast.enhance(1.3)
        
        # Снижение яркости
        brightness = ImageEnhance.Brightness(img)
        img = brightness.enhance(0.9)
        
        # Увеличение резкости
        img = img.filter(PilImageFilter.SHARPEN)
        
        return img
        
    def open_crop_editor(self):
        """Открытие редактора обрезки"""
        if not self.selected_image_id:
            messagebox.showwarning("Предупреждение", "Выберите изображение")
            return
            
        # Пока заглушка - в будущем можно добавить полноценный редактор
        messagebox.showinfo("В разработке", "Редактор обрезки будет добавлен в следующей версии")
        
    # Обработчики событий
    def on_search_change(self, *args):
        """Обработчик изменения поискового запроса"""
        self.refresh_image_grid()
        
    def on_filter_change(self, event=None):
        """Обработчик изменения фильтра"""
        self.refresh_image_grid()
        
    def change_view_mode(self):
        """Изменение режима просмотра"""
        self.refresh_image_grid()
        
    def delete_selected_images(self):
        """Удаление выбранных изображений"""
        if self.selected_image_id:
            result = messagebox.askyesno("Подтверждение", 
                                       "Удалить выбранное изображение из библиотеки?")
            if result:
                self.library.remove_image(self.selected_image_id)
                self.selected_image_id = None
                self.refresh_image_grid()
                
    def cleanup(self):
        """Очистка ресурсов"""
        # Остановка фонового потока
        self.task_queue.put(None)
        if self.worker_thread:
            self.worker_thread.join(timeout=1)
            
        # Очистка кэша
        self.image_cache.clear()
        self.thumbnail_cache.clear()
        
    def process_image_background(self, *args):
        """Фоновая обработка изображения"""
        # Заглушка для фоновых операций
        pass