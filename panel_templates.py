#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - библиотека профессиональных шаблонов
Профессиональные макеты страниц, композиции и готовые решения для манги
"""

import tkinter as tk
from tkinter import ttk, Canvas, filedialog, messagebox
import os
import math
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from pathlib import Path
import json

# Импорт из наших модулей
from page_constructor import Panel, PanelType, PanelStyle
from utils import logger, PAGE_SIZES, PANEL_TRANSITIONS, PANEL_EFFECTS


class TemplateCategory(Enum):
    """Категории шаблонов"""
    CLASSIC = "classic"           # Классические макеты
    ACTION = "action"             # Экшн сцены
    DIALOGUE = "dialogue"         # Диалоги
    EMOTIONAL = "emotional"       # Эмоциональные сцены
    ESTABLISHING = "establishing" # Обзорные планы
    SPLASH = "splash"            # Панели на всю страницу
    EXPERIMENTAL = "experimental" # Экспериментальные
    USER_CUSTOM = "user_custom"   # Пользовательские


@dataclass
class TemplateMetadata:
    """Метаданные шаблона"""
    name: str
    description: str
    category: TemplateCategory
    difficulty: str  # "beginner", "intermediate", "advanced"
    emotional_tone: str  # "calm", "tense", "dramatic", "comedic"
    reading_pace: str  # "slow", "medium", "fast"
    best_for: List[str]  # Типы сцен, для которых подходит
    panel_count: int
    transitions: List[str]  # Типы переходов
    

@dataclass
class PanelTemplate:
    """Шаблон отдельной панели"""
    x_ratio: float  # Позиция как процент от ширины страницы
    y_ratio: float  # Позиция как процент от высоты страницы
    width_ratio: float
    height_ratio: float
    panel_type: PanelType
    style_preset: str = "default"
    layer: int = 0
    content_hint: str = ""  # Подсказка о содержимом
    emotional_weight: float = 1.0  # Эмоциональная важность (1.0 = нормальная)


@dataclass
class PageTemplate:
    """Шаблон всей страницы"""
    metadata: TemplateMetadata
    panels: List[PanelTemplate]
    gutters: Dict[str, float] = field(default_factory=lambda: {"horizontal": 12, "vertical": 15, "margin": 20})
    reading_flow: List[int] = field(default_factory=list)  # Порядок чтения панелей
    thumbnail: Optional[str] = None  # Путь к превью


class PanelTemplatesLibrary:
    """Библиотека шаблонов панелей манги"""
    
    def __init__(self, parent_frame: ttk.Frame, app_instance):
        self.parent = parent_frame
        self.app = app_instance
        
        # Коллекция шаблонов
        self.templates: Dict[str, PageTemplate] = {}
        self.current_category = TemplateCategory.CLASSIC
        self.filtered_templates: List[str] = []
        
        # Создание предустановленных шаблонов
        self.create_builtin_templates()
        
        # Инициализация UI
        self.setup_ui()
        self.refresh_template_list()
        
    def setup_ui(self):
        """Настройка пользовательского интерфейса"""
        # Заголовок
        title_label = ttk.Label(self.parent, text="Шаблоны панелей", style='Title.TLabel')
        title_label.pack(anchor=tk.W, padx=5, pady=(5, 0))
        
        # Фильтр по категориям
        filter_frame = ttk.LabelFrame(self.parent, text="Категория")
        filter_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.category_var = tk.StringVar(value="classic")
        categories = [
            ("Классические", "classic"),
            ("Экшн", "action"),
            ("Диалоги", "dialogue"),
            ("Эмоциональные", "emotional"),
            ("Обзорные", "establishing"),
            ("Splash", "splash"),
            ("Эксперимент", "experimental"),
            ("Мои шаблоны", "user_custom")
        ]
        
        for i, (text, value) in enumerate(categories):
            rb = ttk.Radiobutton(filter_frame, text=text, variable=self.category_var, 
                               value=value, command=self.on_category_change)
            rb.grid(row=i//2, column=i%2, sticky=tk.W, padx=2, pady=1)
            
        # Список шаблонов с превью
        templates_frame = ttk.LabelFrame(self.parent, text="Доступные шаблоны")
        templates_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Canvas для списка с прокруткой
        self.templates_canvas = Canvas(templates_frame, bg="white")
        scrollbar = ttk.Scrollbar(templates_frame, orient=tk.VERTICAL, command=self.templates_canvas.yview)
        self.scrollable_frame = ttk.Frame(self.templates_canvas)
        
        self.canvas_window_item_id = self.templates_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # При изменении размера templates_canvas, обновляем ширину scrollable_frame и scrollregion
        self.templates_canvas.bind("<Configure>", self._on_templates_canvas_configure_changed)

        self.templates_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.templates_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопки действий
        actions_frame = ttk.Frame(self.parent)
        actions_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(actions_frame, text="Применить", command=self.apply_selected_template).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_frame, text="Предпросмотр", command=self.preview_template).pack(side=tk.LEFT, padx=2)
        ttk.Button(actions_frame, text="Сохранить как шаблон", command=self.save_current_as_template).pack(side=tk.LEFT, padx=2)
        
        # Информация о выбранном шаблоне
        self.info_frame = ttk.LabelFrame(self.parent, text="Информация")
        self.info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.info_text = tk.Text(self.info_frame, height=4, wrap=tk.WORD, state=tk.DISABLED)
        self.info_text.pack(fill=tk.X, padx=5, pady=5)
        
        # Переменные состояния
        self.selected_template = None
        
    def create_builtin_templates(self):
        """Создание встроенных шаблонов"""
        
        # === КЛАССИЧЕСКИЕ ШАБЛОНЫ ===
        
        # 4-панельный классический
        self.templates["classic_4panel"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Классический 4-панельный",
                description="Стандартный макет из 4 панелей для спокойного повествования",
                category=TemplateCategory.CLASSIC,
                difficulty="beginner",
                emotional_tone="calm",
                reading_pace="medium",
                best_for=["Диалог", "Обычные сцены", "Повествование"],
                panel_count=4,
                transitions=["action_to_action", "subject_to_subject"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.42, 0.25, PanelType.RECTANGULAR, content_hint="Обзорный план"),
                PanelTemplate(0.53, 0.05, 0.42, 0.25, PanelType.RECTANGULAR, content_hint="Реакция персонажа"),
                PanelTemplate(0.05, 0.35, 0.42, 0.25, PanelType.RECTANGULAR, content_hint="Диалог"),
                PanelTemplate(0.53, 0.35, 0.42, 0.25, PanelType.RECTANGULAR, content_hint="Крупный план")
            ]
        )
        
        # 6-панельный классический
        self.templates["classic_6panel"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Классический 6-панельный",
                description="Детальный макет для сложных сцен с множественными действиями",
                category=TemplateCategory.CLASSIC,
                difficulty="intermediate",
                emotional_tone="calm",
                reading_pace="slow",
                best_for=["Сложные диалоги", "Пошаговые действия"],
                panel_count=6,
                transitions=["moment_to_moment", "action_to_action"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.42, 0.18, PanelType.RECTANGULAR),
                PanelTemplate(0.53, 0.05, 0.42, 0.18, PanelType.RECTANGULAR),
                PanelTemplate(0.05, 0.27, 0.42, 0.18, PanelType.RECTANGULAR),
                PanelTemplate(0.53, 0.27, 0.42, 0.18, PanelType.RECTANGULAR),
                PanelTemplate(0.05, 0.49, 0.42, 0.18, PanelType.RECTANGULAR),
                PanelTemplate(0.53, 0.49, 0.42, 0.18, PanelType.RECTANGULAR)
            ]
        )
        
        # === ЭКШН ШАБЛОНЫ ===
        
        # Динамический экшн
        self.templates["action_dynamic"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Динамический экшн",
                description="Ассиметричный макет для сцен с высокой динамикой",
                category=TemplateCategory.ACTION,
                difficulty="intermediate",
                emotional_tone="tense",
                reading_pace="fast",
                best_for=["Боевые сцены", "Погони", "Взрывы"],
                panel_count=5,
                transitions=["action_to_action", "aspect_to_aspect"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.6, 0.3, PanelType.RECTANGULAR, emotional_weight=1.5),
                PanelTemplate(0.7, 0.05, 0.25, 0.15, PanelType.RECTANGULAR, emotional_weight=0.8),
                PanelTemplate(0.7, 0.22, 0.25, 0.13, PanelType.RECTANGULAR, emotional_weight=0.8),
                PanelTemplate(0.05, 0.4, 0.4, 0.25, PanelType.RECTANGULAR, emotional_weight=1.2),
                PanelTemplate(0.5, 0.4, 0.45, 0.25, PanelType.RECTANGULAR, emotional_weight=1.3)
            ]
        )
        
        # Splash с деталями
        self.templates["action_splash"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Splash с деталями",
                description="Большая splash-панель с мелкими деталями",
                category=TemplateCategory.ACTION,
                difficulty="advanced",
                emotional_tone="dramatic",
                reading_pace="fast",
                best_for=["Кульминационные моменты", "Трансформации", "Откровения"],
                panel_count=4,
                transitions=["scene_to_scene", "aspect_to_aspect"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.9, 0.5, PanelType.SPLASH, emotional_weight=2.0),
                PanelTemplate(0.05, 0.6, 0.28, 0.15, PanelType.ROUND, emotional_weight=0.7),
                PanelTemplate(0.36, 0.6, 0.28, 0.15, PanelType.ROUND, emotional_weight=0.7),
                PanelTemplate(0.67, 0.6, 0.28, 0.15, PanelType.ROUND, emotional_weight=0.7)
            ]
        )
        
        # === ДИАЛОГОВЫЕ ШАБЛОНЫ ===
        
        # Разговор двух персонажей
        self.templates["dialogue_conversation"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Диалог двух персонажей",
                description="Оптимизированный макет для разговора между двумя персонажами",
                category=TemplateCategory.DIALOGUE,
                difficulty="beginner",
                emotional_tone="calm",
                reading_pace="slow",
                best_for=["Диалоги", "Разговоры", "Интервью"],
                panel_count=6,
                transitions=["subject_to_subject", "moment_to_moment"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.9, 0.15, PanelType.RECTANGULAR, content_hint="Обзорный план разговора"),
                PanelTemplate(0.05, 0.23, 0.42, 0.2, PanelType.SPEECH_BUBBLE, content_hint="Персонаж A"),
                PanelTemplate(0.53, 0.23, 0.42, 0.2, PanelType.SPEECH_BUBBLE, content_hint="Персонаж B"),
                PanelTemplate(0.05, 0.46, 0.42, 0.2, PanelType.SPEECH_BUBBLE, content_hint="Персонаж A"),
                PanelTemplate(0.53, 0.46, 0.42, 0.2, PanelType.SPEECH_BUBBLE, content_hint="Персонаж B"),
                PanelTemplate(0.05, 0.69, 0.9, 0.15, PanelType.RECTANGULAR, content_hint="Заключительная реакция")
            ]
        )
        
        # === ЭМОЦИОНАЛЬНЫЕ ШАБЛОНЫ ===
        
        # Эмоциональное открытие
        self.templates["emotional_revelation"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Эмоциональное открытие",
                description="Макет для эмоционально насыщенных сцен и откровений",
                category=TemplateCategory.EMOTIONAL,
                difficulty="advanced",
                emotional_tone="dramatic",
                reading_pace="slow",
                best_for=["Откровения", "Эмоциональные моменты", "Воспоминания"],
                panel_count=5,
                transitions=["aspect_to_aspect", "moment_to_moment"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.25, 0.4, PanelType.RECTANGULAR, emotional_weight=0.8),
                PanelTemplate(0.35, 0.05, 0.6, 0.25, PanelType.RECTANGULAR, emotional_weight=1.5),
                PanelTemplate(0.35, 0.33, 0.28, 0.12, PanelType.ROUND, emotional_weight=0.9),
                PanelTemplate(0.67, 0.33, 0.28, 0.12, PanelType.ROUND, emotional_weight=0.9),
                PanelTemplate(0.05, 0.5, 0.9, 0.3, PanelType.RECTANGULAR, emotional_weight=2.0)
            ]
        )
        
        # Воспоминание/флешбек
        self.templates["emotional_flashback"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Флешбек",
                description="Макет для сцен воспоминаний с размытыми границами",
                category=TemplateCategory.EMOTIONAL,
                difficulty="intermediate",
                emotional_tone="nostalgic",
                reading_pace="slow",
                best_for=["Воспоминания", "Флешбеки", "Сны"],
                panel_count=4,
                transitions=["scene_to_scene", "non_sequitur"]
            ),
            panels=[
                PanelTemplate(0.1, 0.1, 0.8, 0.25, PanelType.ROUND, style_preset="wavy", emotional_weight=1.3),
                PanelTemplate(0.05, 0.4, 0.35, 0.2, PanelType.ROUND, style_preset="wavy", emotional_weight=1.0),
                PanelTemplate(0.45, 0.4, 0.5, 0.2, PanelType.ROUND, style_preset="wavy", emotional_weight=1.0),
                PanelTemplate(0.1, 0.65, 0.8, 0.25, PanelType.ROUND, style_preset="wavy", emotional_weight=1.3)
            ]
        )
        
        # === ЭКСПЕРИМЕНТАЛЬНЫЕ ШАБЛОНЫ ===
        
        # Спиральная композиция
        self.templates["experimental_spiral"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Спиральная композиция",
                description="Экспериментальный макет со спиральным расположением панелей",
                category=TemplateCategory.EXPERIMENTAL,
                difficulty="advanced",
                emotional_tone="surreal",
                reading_pace="slow",
                best_for=["Сюрреалистичные сцены", "Головокружение", "Дезориентация"],
                panel_count=7,
                transitions=["non_sequitur", "aspect_to_aspect"]
            ),
            panels=[
                PanelTemplate(0.4, 0.4, 0.2, 0.2, PanelType.ROUND, emotional_weight=2.0),  # Центр
                PanelTemplate(0.45, 0.15, 0.15, 0.15, PanelType.ROUND, emotional_weight=1.0),
                PanelTemplate(0.7, 0.3, 0.15, 0.15, PanelType.ROUND, emotional_weight=1.0),
                PanelTemplate(0.65, 0.65, 0.15, 0.15, PanelType.ROUND, emotional_weight=1.0),
                PanelTemplate(0.3, 0.7, 0.15, 0.15, PanelType.ROUND, emotional_weight=1.0),
                PanelTemplate(0.1, 0.5, 0.15, 0.15, PanelType.ROUND, emotional_weight=1.0),
                PanelTemplate(0.2, 0.2, 0.15, 0.15, PanelType.ROUND, emotional_weight=1.0)
            ]
        )
        
        # Мозаичная композиция
        self.templates["experimental_mosaic"] = PageTemplate(
            metadata=TemplateMetadata(
                name="Мозаичная композиция",
                description="Нерегулярная мозаика панелей для хаотичных сцен",
                category=TemplateCategory.EXPERIMENTAL,
                difficulty="expert",
                emotional_tone="chaotic",
                reading_pace="fast",
                best_for=["Хаос", "Битвы", "Паника", "Множественные действия"],
                panel_count=9,
                transitions=["action_to_action", "non_sequitur"]
            ),
            panels=[
                PanelTemplate(0.05, 0.05, 0.3, 0.2, PanelType.IRREGULAR),
                PanelTemplate(0.4, 0.05, 0.25, 0.15, PanelType.RECTANGULAR),
                PanelTemplate(0.7, 0.05, 0.25, 0.25, PanelType.IRREGULAR),
                PanelTemplate(0.05, 0.3, 0.2, 0.3, PanelType.RECTANGULAR),
                PanelTemplate(0.3, 0.25, 0.35, 0.2, PanelType.IRREGULAR),
                PanelTemplate(0.7, 0.35, 0.25, 0.2, PanelType.RECTANGULAR),
                PanelTemplate(0.05, 0.65, 0.35, 0.25, PanelType.IRREGULAR),
                PanelTemplate(0.45, 0.5, 0.2, 0.4, PanelType.RECTANGULAR),
                PanelTemplate(0.7, 0.6, 0.25, 0.3, PanelType.IRREGULAR)
            ]
        )
        
        logger.info(f"Создано {len(self.templates)} встроенных шаблонов")
        
    def on_category_change(self):
        """Обработчик изменения категории"""
        category_value = self.category_var.get()
        self.current_category = TemplateCategory(category_value)
        self.refresh_template_list()

    def _on_templates_canvas_configure_changed(self, event):
        """Вызывается при изменении размера templates_canvas."""
        # Исправлено: добавлена проверка на готовность виджетов
        try:
            canvas_width = event.width
            if hasattr(self, 'canvas_window_item_id') and self.canvas_window_item_id:
                self.templates_canvas.itemconfig(self.canvas_window_item_id, width=canvas_width)
            
            # Обновляем область прокрутки только если она существует
            if self.templates_canvas.winfo_exists():
                self.templates_canvas.configure(scrollregion=self.templates_canvas.bbox("all"))
        except (tk.TclError, AttributeError):
            # Игнорируем ошибки при инициализации
            pass
        
    def refresh_template_list(self):
        """Обновление списка шаблонов"""
        # Очистка текущего списка
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
            
        # Фильтрация шаблонов по категории
        filtered_templates = [
            (template_id, template) for template_id, template in self.templates.items()
            if template.metadata.category == self.current_category
        ]
        
        if not filtered_templates:
            no_templates_label = ttk.Label(self.scrollable_frame, 
                                         text="Нет шаблонов в данной категории")
            no_templates_label.pack(pady=20)
            return
            
        # Создание элементов списка
        for i, (template_id, template) in enumerate(filtered_templates):
            self.create_template_item(template_id, template, i)
            
        # Обновление области прокрутки
        self.templates_canvas.update_idletasks()
        
    def create_template_item(self, template_id: str, template: PageTemplate, index: int):
        """Создание элемента списка шаблонов"""
        # Контейнер для шаблона
        item_frame = ttk.Frame(self.scrollable_frame, relief=tk.RAISED, borderwidth=1)
        item_frame.pack(fill=tk.X, expand=True, padx=2, pady=2)
        
        # Клик по элементу
        def on_select():
            self.selected_template = template_id
            self.update_template_info(template)
            # Выделение выбранного элемента
            for child in self.scrollable_frame.winfo_children():
                if isinstance(child, ttk.Frame):
                    child.configure(relief=tk.RAISED)
            item_frame.configure(relief=tk.SUNKEN)
            
        item_frame.bind("<Button-1>", lambda e: on_select())
        
        # Левая часть - превью
        preview_frame = ttk.Frame(item_frame)
        preview_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        preview_canvas = Canvas(preview_frame, width=80, height=100, bg="white", 
                               highlightthickness=1, highlightbackground="#CCCCCC")
        preview_canvas.pack()
        
        # Рисование превью шаблона
        self.draw_template_preview(preview_canvas, template)
        preview_canvas.bind("<Button-1>", lambda e: on_select())
        
        # Правая часть - информация
        info_frame = ttk.Frame(item_frame)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Название
        name_label = ttk.Label(info_frame, text=template.metadata.name, font=("Arial", 10, "bold"))
        name_label.pack(anchor=tk.W)
        name_label.bind("<Button-1>", lambda e: on_select())
        
        # Описание
        desc_label = ttk.Label(info_frame, text=template.metadata.description, 
                            font=("Arial", 8)) # Убрали wraplength=200
        # Теперь desc_label будет использовать свою ширину для переноса.
        # Чтобы он растягивался, добавим fill=tk.X и expand=True
        desc_label.pack(anchor=tk.W, pady=(2, 0), fill=tk.X, expand=True) 
        desc_label.bind("<Button-1>", lambda e: on_select())
        
        # Дополнительная информация
        details = f"Панелей: {template.metadata.panel_count} | Темп: {template.metadata.reading_pace}"
        details_label = ttk.Label(info_frame, text=details, font=("Arial", 7), foreground="#666666")
        details_label.pack(anchor=tk.W, pady=(2, 0))
        details_label.bind("<Button-1>", lambda e: on_select())
        
        # Кнопки действий
        buttons_frame = ttk.Frame(item_frame)
        buttons_frame.pack(side=tk.RIGHT, padx=5, pady=5)
        
        apply_btn = ttk.Button(buttons_frame, text="Применить", width=10,
                              command=lambda: self.apply_template(template_id))
        apply_btn.pack(pady=1)
        
        preview_btn = ttk.Button(buttons_frame, text="Превью", width=10,
                                command=lambda: self.preview_template(template_id))
        preview_btn.pack(pady=1)
        
    def draw_template_preview(self, canvas: Canvas, template: PageTemplate):
        """Рисование превью шаблона"""
        canvas_width = 80
        canvas_height = 100
        
        # Рисование панелей
        for panel in template.panels:
            x1 = panel.x_ratio * canvas_width
            y1 = panel.y_ratio * canvas_height
            x2 = x1 + (panel.width_ratio * canvas_width)
            y2 = y1 + (panel.height_ratio * canvas_height)
            
            # Цвет в зависимости от типа панели
            colors = {
                PanelType.RECTANGULAR: "#E8F4FD",
                PanelType.ROUND: "#FFF2CC",
                PanelType.SPEECH_BUBBLE: "#E1F5FE",
                PanelType.THOUGHT_BUBBLE: "#F3E5F5",
                PanelType.SPLASH: "#FFEBEE",
                PanelType.IRREGULAR: "#E8F5E8"
            }
            
            fill_color = colors.get(panel.panel_type, "#F5F5F5")
            
            # Рисование в зависимости от типа
            if panel.panel_type == PanelType.ROUND:
                canvas.create_oval(x1, y1, x2, y2, fill=fill_color, outline="#333333", width=1)
            else:
                canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline="#333333", width=1)
                
            # Индикатор эмоционального веса
            if panel.emotional_weight > 1.2:
                # Красная точка для высокого эмоционального воздействия
                center_x = (x1 + x2) / 2
                center_y = (y1 + y2) / 2
                canvas.create_oval(center_x - 2, center_y - 2, center_x + 2, center_y + 2, 
                                 fill="#FF0000", outline="")
                                 
    def update_template_info(self, template: PageTemplate):
        """Обновление информации о выбранном шаблоне"""
        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete(1.0, tk.END)
        
        info_text = f"""Название: {template.metadata.name}
Описание: {template.metadata.description}
Сложность: {template.metadata.difficulty}
Эмоциональный тон: {template.metadata.emotional_tone}
Темп чтения: {template.metadata.reading_pace}
Подходит для: {', '.join(template.metadata.best_for)}
Переходы: {', '.join(template.metadata.transitions)}"""
        
        self.info_text.insert(1.0, info_text)
        self.info_text.configure(state=tk.DISABLED)
        
    def apply_selected_template(self):
        """Применение выбранного шаблона"""
        if self.selected_template:
            self.apply_template(self.selected_template)
        else:
            tk.messagebox.showwarning("Предупреждение", "Выберите шаблон для применения")
            
    def apply_template(self, template_id: str):
        """Применение шаблона к странице"""
        if template_id not in self.templates:
            logger.error(f"Шаблон {template_id} не найден")
            return
            
        template = self.templates[template_id]
        
        # Получение размеров страницы
        page_width = self.app.page_constructor.page_width
        page_height = self.app.page_constructor.page_height
        
        # Очистка текущих панелей (с подтверждением)
        if self.app.page_constructor.panels:
            result = tk.messagebox.askyesno(
                "Подтверждение", 
                "Применение шаблона удалит все существующие панели. Продолжить?"
            )
            if not result:
                return
                
        self.app.page_constructor.clear_page()
        self.app.update_layers_list()
        
        # Создание панелей на основе шаблона
        for panel_template in template.panels:
            x = panel_template.x_ratio * page_width
            y = panel_template.y_ratio * page_height
            width = panel_template.width_ratio * page_width
            height = panel_template.height_ratio * page_height
            
            # Создание панели
            panel = self.app.page_constructor.create_panel(x, y, width, height, panel_template.panel_type)
            panel.layer = panel_template.layer
            panel.content_text = panel_template.content_hint
            
            # Применение стиля
            if panel_template.style_preset != "default":
                self.apply_style_preset(panel, panel_template.style_preset)
                
        # Сортировка панелей по слоям
        self.app.page_constructor.panels.sort(key=lambda p: p.layer)
        
        # Установка порядка чтения
        if template.reading_flow:
            self.set_reading_flow(template.reading_flow)
            
        # Обновление отображения
        self.app.page_constructor.redraw()
        self.app.update_layers_list()
        self.app.set_status(f"Применён шаблон: {template.metadata.name}")
        
        logger.info(f"Применён шаблон {template_id}")
        
    def apply_style_preset(self, panel: Panel, preset: str):
        """Применение предустановленного стиля"""
        if preset == "wavy":
            panel.style.border_color = "#8A2BE2"
            panel.style.corner_radius = 15
            panel.style.shadow = True
        elif preset == "jagged":
            panel.style.border_color = "#FF4500"
            panel.style.border_width = 3
        elif preset == "burst":
            panel.style.border_color = "#FFD700"
            panel.style.border_width = 4
            panel.style.shadow = True
            panel.style.shadow_color = "#FFA500"
            
    def preview_template(self, template_id: str = None):
        """Предпросмотр шаблона в отдельном окне"""
        if not template_id:
            template_id = self.selected_template
            
        if not template_id or template_id not in self.templates:
            tk.messagebox.showwarning("Предупреждение", "Выберите шаблон для предпросмотра")
            return
            
        template = self.templates[template_id]
        
        # Создание окна предпросмотра
        preview_window = tk.Toplevel(self.parent)
        preview_window.title(f"Предпросмотр: {template.metadata.name}")
        preview_window.geometry("400x500")
        
        # Canvas для предпросмотра
        preview_canvas = Canvas(preview_window, width=350, height=450, bg="white")
        preview_canvas.pack(padx=25, pady=25)
        
        # Рисование детального превью
        self.draw_detailed_preview(preview_canvas, template)
        
        # Информация о шаблоне
        info_frame = ttk.Frame(preview_window)
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        info_label = ttk.Label(info_frame, text=template.metadata.description, wraplength=380)
        info_label.pack()
        
        # Кнопка применения
        apply_btn = ttk.Button(preview_window, text="Применить этот шаблон",
                              command=lambda: [self.apply_template(template_id), preview_window.destroy()])
        apply_btn.pack(pady=10)
        
    def draw_detailed_preview(self, canvas: Canvas, template: PageTemplate):
        """Рисование детального превью шаблона"""
        canvas_width = 350
        canvas_height = 450
        
        # Фон страницы
        canvas.create_rectangle(10, 10, canvas_width-10, canvas_height-10, 
                               fill="white", outline="#888888", width=2)
        
        # Рисование панелей
        for i, panel in enumerate(template.panels):
            x1 = 10 + (panel.x_ratio * (canvas_width - 20))
            y1 = 10 + (panel.y_ratio * (canvas_height - 20))
            x2 = x1 + (panel.width_ratio * (canvas_width - 20))
            y2 = y1 + (panel.height_ratio * (canvas_height - 20))
            
            # Цвет панели в зависимости от эмоционального веса
            if panel.emotional_weight > 1.5:
                fill_color = "#FFEBEE"  # Красноватый для высокого воздействия
            elif panel.emotional_weight > 1.2:
                fill_color = "#FFF3E0"  # Оранжевый для среднего воздействия
            else:
                fill_color = "#F5F5F5"  # Серый для обычных панелей
                
            # Рисование панели
            if panel.panel_type == PanelType.ROUND:
                canvas.create_oval(x1, y1, x2, y2, fill=fill_color, outline="#333333", width=2)
            elif panel.panel_type == PanelType.SPLASH:
                canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline="#FF6B6B", width=3)
            else:
                canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline="#333333", width=2)
                
            # Номер панели для понимания порядка чтения
            center_x = (x1 + x2) / 2
            center_y = (y1 + y2) / 2
            canvas.create_text(center_x, center_y, text=str(i+1), font=("Arial", 12, "bold"))
            
            # Подсказка о содержимом
            if panel.content_hint:
                canvas.create_text(center_x, center_y + 15, text=panel.content_hint, 
                                 font=("Arial", 8), fill="#666666")
                                 
    def save_current_as_template(self):
        """Сохранение текущей страницы как шаблона"""
        if not self.app.page_constructor.panels:
            tk.messagebox.showwarning("Предупреждение", "Нет панелей для сохранения")
            return
            
        # Диалог создания шаблона
        self.show_template_creation_dialog()
        
    def show_template_creation_dialog(self):
        """Диалог создания пользовательского шаблона"""
        dialog = tk.Toplevel(self.parent)
        dialog.title("Создание шаблона")
        dialog.geometry("400x500")
        dialog.resizable(False, False)
        
        # Центрирование диалога
        dialog.transient(self.parent)
        dialog.grab_set()
        
        # Поля ввода
        ttk.Label(dialog, text="Название шаблона:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        name_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=name_var, width=50).pack(padx=10, pady=5)
        
        ttk.Label(dialog, text="Описание:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        desc_text = tk.Text(dialog, height=3, width=50)
        desc_text.pack(padx=10, pady=5)
        
        ttk.Label(dialog, text="Сложность:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        difficulty_var = tk.StringVar(value="intermediate")
        difficulty_combo = ttk.Combobox(dialog, textvariable=difficulty_var, 
                                       values=["beginner", "intermediate", "advanced", "expert"],
                                       state="readonly")
        difficulty_combo.pack(padx=10, pady=5)
        
        ttk.Label(dialog, text="Эмоциональный тон:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        tone_var = tk.StringVar(value="calm")
        tone_combo = ttk.Combobox(dialog, textvariable=tone_var, 
                                 values=["calm", "tense", "dramatic", "comedic", "nostalgic", "surreal", "chaotic"],
                                 state="readonly")
        tone_combo.pack(padx=10, pady=5)
        
        ttk.Label(dialog, text="Темп чтения:").pack(anchor=tk.W, padx=10, pady=(10, 0))
        pace_var = tk.StringVar(value="medium")
        pace_combo = ttk.Combobox(dialog, textvariable=pace_var, 
                                 values=["slow", "medium", "fast"],
                                 state="readonly")
        pace_combo.pack(padx=10, pady=5)
        
        ttk.Label(dialog, text="Лучше всего подходит для (через запятую):").pack(anchor=tk.W, padx=10, pady=(10, 0))
        best_for_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=best_for_var, width=50).pack(padx=10, pady=5)
        
        # Кнопки
        buttons_frame = ttk.Frame(dialog)
        buttons_frame.pack(pady=20)
        
        def save_template():
            name = name_var.get().strip()
            if not name:
                tk.messagebox.showerror("Ошибка", "Введите название шаблона")
                return
                
            # Создание шаблона из текущих панелей
            self.create_template_from_current_page(
                name=name,
                description=desc_text.get(1.0, tk.END).strip(),
                difficulty=difficulty_var.get(),
                emotional_tone=tone_var.get(),
                reading_pace=pace_var.get(),
                best_for=[item.strip() for item in best_for_var.get().split(',') if item.strip()]
            )
            
            dialog.destroy()
            tk.messagebox.showinfo("Успех", f"Шаблон '{name}' сохранён")
            
        ttk.Button(buttons_frame, text="Сохранить", command=save_template).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Отмена", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
    def create_template_from_current_page(self, name: str, description: str, difficulty: str, 
                                        emotional_tone: str, reading_pace: str, best_for: List[str]):
        """Создание шаблона из текущей страницы"""
        page_width = self.app.page_constructor.page_width
        page_height = self.app.page_constructor.page_height
        
        # Конвертация панелей в шаблоны
        panel_templates = []
        for panel in self.app.page_constructor.panels:
            panel_template = PanelTemplate(
                x_ratio=panel.x / page_width,
                y_ratio=panel.y / page_height,
                width_ratio=panel.width / page_width,
                height_ratio=panel.height / page_height,
                panel_type=panel.panel_type,
                layer=panel.layer,
                content_hint=panel.content_text or ""
            )
            panel_templates.append(panel_template)
            
        # Создание метаданных
        metadata = TemplateMetadata(
            name=name,
            description=description,
            category=TemplateCategory.USER_CUSTOM,
            difficulty=difficulty,
            emotional_tone=emotional_tone,
            reading_pace=reading_pace,
            best_for=best_for,
            panel_count=len(panel_templates),
            transitions=["user_defined"]
        )
        
        # Сохранение шаблона
        template_id = f"user_{name.lower().replace(' ', '_')}"
        self.templates[template_id] = PageTemplate(
            metadata=metadata,
            panels=panel_templates
        )
        
        # Обновление списка если текущая категория - пользовательские шаблоны
        if self.current_category == TemplateCategory.USER_CUSTOM:
            self.refresh_template_list()
            
        logger.info(f"Создан пользовательский шаблон {template_id}")
        
    def set_reading_flow(self, flow: List[int]):
        """Установка порядка чтения панелей"""
        # Пока просто сохраняем, позже можно использовать для анимации или подсказок
        self.reading_flow = flow
        
    def refresh(self):
        """Обновление библиотеки"""
        self.refresh_template_list()
        
    # Методы для будущего расширения
    def export_template(self, template_id: str):
        """Экспорт шаблона в файл"""
        if template_id not in self.templates:
            messagebox.showerror("Ошибка", "Шаблон не найден")
            return
            
        template = self.templates[template_id]
        
        # Диалог сохранения файла
        filename = filedialog.asksaveasfilename(
            title="Экспорт шаблона",
            defaultextension=".manga_template",
            filetypes=[
                ("Шаблоны манги", "*.manga_template"),
                ("JSON файлы", "*.json"),
                ("Все файлы", "*.*")
            ],
            initialvalue=f"{template.metadata.name}.manga_template"
        )
        
        if not filename:
            return
            
        try:
            # Подготовка данных для экспорта
            export_data = {
                "version": "1.0",
                "type": "manga_page_template",
                "metadata": {
                    "name": template.metadata.name,
                    "description": template.metadata.description,
                    "category": template.metadata.category.value,
                    "difficulty": template.metadata.difficulty,
                    "emotional_tone": template.metadata.emotional_tone,
                    "reading_pace": template.metadata.reading_pace,
                    "best_for": template.metadata.best_for,
                    "panel_count": template.metadata.panel_count,
                    "transitions": template.metadata.transitions,
                    "exported_date": datetime.now().isoformat(),
                    "exported_by": "Manga Constructor v1.0"
                },
                "panels": [
                    {
                        "x_ratio": panel.x_ratio,
                        "y_ratio": panel.y_ratio,
                        "width_ratio": panel.width_ratio,
                        "height_ratio": panel.height_ratio,
                        "panel_type": panel.panel_type.value,
                        "style_preset": panel.style_preset,
                        "layer": panel.layer,
                        "content_hint": panel.content_hint,
                        "emotional_weight": panel.emotional_weight
                    }
                    for panel in template.panels
                ],
                "gutters": template.gutters,
                "reading_flow": template.reading_flow
            }
            
            # Сохранение файла
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            messagebox.showinfo("Экспорт завершён", 
                            f"Шаблон '{template.metadata.name}' экспортирован в:\n{filename}")
            
            logger.info(f"Шаблон {template_id} экспортирован в {filename}")
            
        except Exception as e:
            logger.error(f"Ошибка экспорта шаблона {template_id}: {e}")
            messagebox.showerror("Ошибка экспорта", f"Не удалось экспортировать шаблон:\n{e}")
        
    def import_template(self, file_path: str = None):
        """Импорт шаблона из файла"""
        if not file_path:
            file_path = filedialog.askopenfilename(
                title="Импорт шаблона",
                filetypes=[
                    ("Шаблоны манги", "*.manga_template"),
                    ("JSON файлы", "*.json"),
                    ("Все файлы", "*.*")
                ]
            )
            
        if not file_path:
            return
            
        try:
            # Загрузка файла
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
                
            # Проверка формата
            if import_data.get("type") != "manga_page_template":
                messagebox.showerror("Ошибка", "Неверный формат файла шаблона")
                return
                
            # Проверка версии
            version = import_data.get("version", "1.0")
            if version != "1.0":
                result = messagebox.askyesno("Предупреждение", 
                                        f"Версия шаблона {version} может быть несовместима. Продолжить?")
                if not result:
                    return
                    
            # Извлечение метаданных
            metadata_dict = import_data["metadata"]
            
            # Создание метаданных
            metadata = TemplateMetadata(
                name=metadata_dict["name"],
                description=metadata_dict["description"],
                category=TemplateCategory(metadata_dict["category"]),
                difficulty=metadata_dict["difficulty"],
                emotional_tone=metadata_dict["emotional_tone"],
                reading_pace=metadata_dict["reading_pace"],
                best_for=metadata_dict["best_for"],
                panel_count=metadata_dict["panel_count"],
                transitions=metadata_dict["transitions"]
            )
            
            # Создание панелей
            panels = []
            for panel_data in import_data["panels"]:
                panel = PanelTemplate(
                    x_ratio=panel_data["x_ratio"],
                    y_ratio=panel_data["y_ratio"],
                    width_ratio=panel_data["width_ratio"],
                    height_ratio=panel_data["height_ratio"],
                    panel_type=PanelType(panel_data["panel_type"]),
                    style_preset=panel_data.get("style_preset", "default"),
                    layer=panel_data.get("layer", 0),
                    content_hint=panel_data.get("content_hint", ""),
                    emotional_weight=panel_data.get("emotional_weight", 1.0)
                )
                panels.append(panel)
                
            # Проверка существования шаблона с таким именем
            existing_id = None
            for template_id, template in self.templates.items():
                if template.metadata.name == metadata.name:
                    existing_id = template_id
                    break
                    
            if existing_id:
                result = messagebox.askyesnocancel("Шаблон существует", 
                                                f"Шаблон '{metadata.name}' уже существует.\n"
                                                "Заменить существующий?")
                if result is None:  # Отмена
                    return
                elif result is False:  # Создать новый с другим именем
                    base_name = metadata.name
                    counter = 1
                    while any(t.metadata.name == f"{base_name} ({counter})" for t in self.templates.values()):
                        counter += 1
                    metadata.name = f"{base_name} ({counter})"
                    
            # Создание шаблона
            template = PageTemplate(
                metadata=metadata,
                panels=panels,
                gutters=import_data.get("gutters", {"horizontal": 12, "vertical": 15, "margin": 20}),
                reading_flow=import_data.get("reading_flow", [])
            )
            
            # Генерация ID для шаблона
            if existing_id and messagebox.askyesno("Подтверждение", "Заменить существующий шаблон?"):
                template_id = existing_id
            else:
                # Создание нового ID
                base_id = f"imported_{metadata.name.lower().replace(' ', '_')}"
                template_id = base_id
                counter = 1
                while template_id in self.templates:
                    template_id = f"{base_id}_{counter}"
                    counter += 1
                    
            # Установка категории как пользовательский, если не системный
            if not existing_id or metadata.category != TemplateCategory.USER_CUSTOM:
                metadata.category = TemplateCategory.USER_CUSTOM
                
            # Сохранение шаблона
            self.templates[template_id] = template
            
            # Обновление интерфейса если текущая категория совпадает
            if self.current_category == metadata.category:
                self.refresh_template_list()
                
            messagebox.showinfo("Импорт завершён", 
                            f"Шаблон '{metadata.name}' успешно импортирован")
            
            logger.info(f"Шаблон импортирован из {file_path} как {template_id}")
            
        except Exception as e:
            logger.error(f"Ошибка импорта шаблона из {file_path}: {e}")
            messagebox.showerror("Ошибка импорта", f"Не удалось импортировать шаблон:\n{e}")
        
    def delete_user_template(self, template_id: str):
        """Удаление пользовательского шаблона"""
        if template_id not in self.templates:
            messagebox.showerror("Ошибка", "Шаблон не найден")
            return
            
        template = self.templates[template_id]
        
        # Проверка, что это пользовательский шаблон
        if template.metadata.category != TemplateCategory.USER_CUSTOM:
            messagebox.showerror("Ошибка", "Можно удалять только пользовательские шаблоны")
            return
            
        # Подтверждение удаления
        result = messagebox.askyesno("Подтверждение удаления", 
                                f"Вы уверены, что хотите удалить шаблон '{template.metadata.name}'?\n"
                                "Это действие нельзя отменить.")
        
        if not result:
            return
            
        try:
            # Удаление шаблона
            del self.templates[template_id]
            
            # Обновление интерфейса
            self.refresh_template_list()
            
            # Очистка информации о шаблоне
            if self.selected_template == template_id:
                self.selected_template = None
                self.info_text.configure(state=tk.NORMAL)
                self.info_text.delete(1.0, tk.END)
                self.info_text.configure(state=tk.DISABLED)
                
            messagebox.showinfo("Удаление завершено", 
                            f"Шаблон '{template.metadata.name}' удалён")
            
            logger.info(f"Пользовательский шаблон {template_id} удалён")
            
        except Exception as e:
            logger.error(f"Ошибка удаления шаблона {template_id}: {e}")
            messagebox.showerror("Ошибка удаления", f"Не удалось удалить шаблон:\n{e}")

    def export_all_user_templates(self):
        """Экспорт всех пользовательских шаблонов"""
        # Получение пользовательских шаблонов
        user_templates = {
            template_id: template for template_id, template in self.templates.items()
            if template.metadata.category == TemplateCategory.USER_CUSTOM
        }
        
        if not user_templates:
            messagebox.showinfo("Информация", "Нет пользовательских шаблонов для экспорта")
            return
            
        # Диалог выбора директории
        directory = filedialog.askdirectory(title="Выберите папку для экспорта шаблонов")
        
        if not directory:
            return
            
        try:
            exported_count = 0
            
            for template_id, template in user_templates.items():
                # Формирование имени файла
                safe_name = "".join(c for c in template.metadata.name if c.isalnum() or c in (' ', '-', '_')).strip()
                filename = f"{safe_name}.manga_template"
                filepath = os.path.join(directory, filename)
                
                # Проверка существования файла
                if os.path.exists(filepath):
                    result = messagebox.askyesnocancel("Файл существует", 
                                                    f"Файл '{filename}' уже существует. Заменить?")
                    if result is None:  # Отмена всего процесса
                        break
                    elif result is False:  # Пропустить этот файл
                        continue
                        
                # Экспорт шаблона
                self.export_template_to_file(template, filepath)
                exported_count += 1
                
            if exported_count > 0:
                messagebox.showinfo("Экспорт завершён", 
                                f"Экспортировано шаблонов: {exported_count}")
            else:
                messagebox.showinfo("Экспорт отменён", "Не было экспортировано ни одного шаблона")
                
        except Exception as e:
            logger.error(f"Ошибка пакетного экспорта шаблонов: {e}")
            messagebox.showerror("Ошибка экспорта", f"Ошибка при экспорте шаблонов:\n{e}")

    def export_template_to_file(self, template: PageTemplate, filepath: str):
        """Экспорт конкретного шаблона в файл"""
        export_data = {
            "version": "1.0",
            "type": "manga_page_template",
            "metadata": {
                "name": template.metadata.name,
                "description": template.metadata.description,
                "category": template.metadata.category.value,
                "difficulty": template.metadata.difficulty,
                "emotional_tone": template.metadata.emotional_tone,
                "reading_pace": template.metadata.reading_pace,
                "best_for": template.metadata.best_for,
                "panel_count": template.metadata.panel_count,
                "transitions": template.metadata.transitions,
                "exported_date": datetime.now().isoformat(),
                "exported_by": "Manga Constructor v1.0"
            },
            "panels": [
                {
                    "x_ratio": panel.x_ratio,
                    "y_ratio": panel.y_ratio,
                    "width_ratio": panel.width_ratio,
                    "height_ratio": panel.height_ratio,
                    "panel_type": panel.panel_type.value,
                    "style_preset": panel.style_preset,
                    "layer": panel.layer,
                    "content_hint": panel.content_hint,
                    "emotional_weight": panel.emotional_weight
                }
                for panel in template.panels
            ],
            "gutters": template.gutters,
            "reading_flow": template.reading_flow
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    def import_multiple_templates(self):
        """Импорт нескольких шаблонов"""
        file_paths = filedialog.askopenfilenames(
            title="Импорт шаблонов",
            filetypes=[
                ("Шаблоны манги", "*.manga_template"),
                ("JSON файлы", "*.json"),
                ("Все файлы", "*.*")
            ]
        )
        
        if not file_paths:
            return
            
        imported_count = 0
        failed_count = 0
        
        for file_path in file_paths:
            try:
                self.import_template(file_path)
                imported_count += 1
            except Exception as e:
                logger.error(f"Ошибка импорта {file_path}: {e}")
                failed_count += 1
                
        # Показ результатов
        if imported_count > 0:
            message = f"Импортировано шаблонов: {imported_count}"
            if failed_count > 0:
                message += f"\nОшибок: {failed_count}"
            messagebox.showinfo("Импорт завершён", message)
        else:
            messagebox.showerror("Ошибка импорта", "Не удалось импортировать ни одного шаблона")

    def backup_user_templates(self):
        """Создание резервной копии пользовательских шаблонов"""
        user_templates = {
            template_id: template for template_id, template in self.templates.items()
            if template.metadata.category == TemplateCategory.USER_CUSTOM
        }
        
        if not user_templates:
            messagebox.showinfo("Информация", "Нет пользовательских шаблонов для резервного копирования")
            return
            
        # Диалог сохранения резервной копии
        filename = filedialog.asksaveasfilename(
            title="Создать резервную копию шаблонов",
            defaultextension=".manga_backup",
            filetypes=[
                ("Резервные копии манги", "*.manga_backup"),
                ("JSON файлы", "*.json"),
                ("Все файлы", "*.*")
            ],
            initialvalue=f"templates_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.manga_backup"
        )
        
        if not filename:
            return
            
        try:
            # Подготовка данных резервной копии
            backup_data = {
                "version": "1.0",
                "type": "manga_templates_backup",
                "created_date": datetime.now().isoformat(),
                "created_by": "Manga Constructor v1.0",
                "template_count": len(user_templates),
                "templates": {}
            }
            
            # Добавление шаблонов
            for template_id, template in user_templates.items():
                backup_data["templates"][template_id] = {
                    "metadata": {
                        "name": template.metadata.name,
                        "description": template.metadata.description,
                        "category": template.metadata.category.value,
                        "difficulty": template.metadata.difficulty,
                        "emotional_tone": template.metadata.emotional_tone,
                        "reading_pace": template.metadata.reading_pace,
                        "best_for": template.metadata.best_for,
                        "panel_count": template.metadata.panel_count,
                        "transitions": template.metadata.transitions
                    },
                    "panels": [
                        {
                            "x_ratio": panel.x_ratio,
                            "y_ratio": panel.y_ratio,
                            "width_ratio": panel.width_ratio,
                            "height_ratio": panel.height_ratio,
                            "panel_type": panel.panel_type.value,
                            "style_preset": panel.style_preset,
                            "layer": panel.layer,
                            "content_hint": panel.content_hint,
                            "emotional_weight": panel.emotional_weight
                        }
                        for panel in template.panels
                    ],
                    "gutters": template.gutters,
                    "reading_flow": template.reading_flow
                }
                
            # Сохранение резервной копии
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
                
            messagebox.showinfo("Резервная копия создана", 
                            f"Резервная копия {len(user_templates)} шаблонов создана:\n{filename}")
            
            logger.info(f"Резервная копия шаблонов создана: {filename}")
            
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            messagebox.showerror("Ошибка", f"Не удалось создать резервную копию:\n{e}")

    def restore_from_backup(self):
        """Восстановление шаблонов из резервной копии"""
        file_path = filedialog.askopenfilename(
            title="Восстановить из резервной копии",
            filetypes=[
                ("Резервные копии манги", "*.manga_backup"),
                ("JSON файлы", "*.json"),
                ("Все файлы", "*.*")
            ]
        )
        
        if not file_path:
            return
            
        try:
            # Загрузка резервной копии
            with open(file_path, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
                
            # Проверка формата
            if backup_data.get("type") != "manga_templates_backup":
                messagebox.showerror("Ошибка", "Неверный формат файла резервной копии")
                return
                
            # Подтверждение восстановления
            template_count = backup_data.get("template_count", 0)
            result = messagebox.askyesno("Подтверждение восстановления", 
                                    f"Восстановить {template_count} шаблонов из резервной копии?\n"
                                    "Существующие шаблоны с такими же именами будут заменены.")
            
            if not result:
                return
                
            # Восстановление шаблонов
            restored_count = 0
            
            for template_id, template_data in backup_data["templates"].items():
                try:
                    # Создание метаданных
                    metadata_dict = template_data["metadata"]
                    metadata = TemplateMetadata(
                        name=metadata_dict["name"],
                        description=metadata_dict["description"],
                        category=TemplateCategory(metadata_dict["category"]),
                        difficulty=metadata_dict["difficulty"],
                        emotional_tone=metadata_dict["emotional_tone"],
                        reading_pace=metadata_dict["reading_pace"],
                        best_for=metadata_dict["best_for"],
                        panel_count=metadata_dict["panel_count"],
                        transitions=metadata_dict["transitions"]
                    )
                    
                    # Создание панелей
                    panels = []
                    for panel_data in template_data["panels"]:
                        panel = PanelTemplate(
                            x_ratio=panel_data["x_ratio"],
                            y_ratio=panel_data["y_ratio"],
                            width_ratio=panel_data["width_ratio"],
                            height_ratio=panel_data["height_ratio"],
                            panel_type=PanelType(panel_data["panel_type"]),
                            style_preset=panel_data.get("style_preset", "default"),
                            layer=panel_data.get("layer", 0),
                            content_hint=panel_data.get("content_hint", ""),
                            emotional_weight=panel_data.get("emotional_weight", 1.0)
                        )
                        panels.append(panel)
                        
                    # Создание шаблона
                    template = PageTemplate(
                        metadata=metadata,
                        panels=panels,
                        gutters=template_data.get("gutters", {"horizontal": 12, "vertical": 15, "margin": 20}),
                        reading_flow=template_data.get("reading_flow", [])
                    )
                    
                    # Сохранение шаблона
                    self.templates[template_id] = template
                    restored_count += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка восстановления шаблона {template_id}: {e}")
                    
            # Обновление интерфейса
            self.refresh_template_list()
            
            messagebox.showinfo("Восстановление завершено", 
                            f"Восстановлено шаблонов: {restored_count} из {template_count}")
            
            logger.info(f"Восстановлено {restored_count} шаблонов из резервной копии {file_path}")
            
        except Exception as e:
            logger.error(f"Ошибка восстановления из резервной копии {file_path}: {e}")
            messagebox.showerror("Ошибка восстановления", f"Не удалось восстановить из резервной копии:\n{e}")