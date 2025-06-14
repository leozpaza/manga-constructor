#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Конструктор страниц манги - главный модуль
Профессиональный инструмент для создания страниц манги и комиксов
"""

import tkinter as tk
import uuid
import webbrowser
import pickle
import json
import copy
from datetime import datetime
from tkinter import ttk, messagebox, filedialog
import os
import sys
from pathlib import Path
import time # Добавлено для сплэш-скрина

# Добавляем текущую директорию в путь для импорта модулей
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    # Если splash_screen.py в той же директории:
    from splash_screen import SplashScreen
    # Если класс SplashScreen добавлен прямо в main.py, эта строка не нужна.

    from page_constructor import PageConstructor
    from panel_templates import PanelTemplatesLibrary
    from image_manager import ImageManager
    from export_manager import ExportManager
    from settings import SettingsManager
    from utils import load_icon, create_tooltip, PAGE_SIZES, ORIENTATIONS
except ImportError as e:
    print(f"Ошибка импорта модулей: {e}")
    print("Убедитесь, что все файлы находятся в одной директории или пути настроены корректно.")
    sys.exit(1) # Выход, если критические модули не найдены


class MangaConstructorApp:
    """Главное приложение конструктора манги"""
    
    def __init__(self):
        # 1. Создаем root окно, но пока скрываем его
        self.root = tk.Tk()
        self.root.withdraw() # Скрываем основное окно

        # 2. Создаем и показываем SplashScreen
        # Передаем self.root для контекста стилей ttk
        self.splash = SplashScreen(self.root) # Убрал title, т.к. он задан по умолчанию в SplashScreen
        self.splash.update_progress(0, "Запуск...")

        splash_start_time = time.time()

        # --- Этапы инициализации с обновлением сплэша ---
        total_steps = 11 # Увеличил на 1 для финальной настройки UI
        current_step = 0

        def advance_splash(text, increment=True):
            nonlocal current_step
            if increment:
                current_step += 1
            progress_value = (current_step / total_steps) * 100
            if hasattr(self, 'splash') and self.splash.winfo_exists(): # Проверка на существование сплэша
                self.splash.update_progress(progress_value, text)
                # Добавляем явный self.splash.update() здесь
                try:
                    self.splash.update()
                except tk.TclError:
                    pass # Сплэш мог быть закрыт из-за ошибки

        advance_splash("Настройка основного окна...")
        self.setup_window()

        advance_splash("Инициализация переменных...")
        self.setup_variables()

        advance_splash("Создание главного меню...")
        self.create_menu()

        advance_splash("Создание панели инструментов...")
        self.create_toolbar()

        advance_splash("Создание основного интерфейса...")
        self.create_main_interface() # page_constructor создается здесь

        advance_splash("Создание статусной строки...")
        self.create_status_bar()

        advance_splash("Привязка событий...")
        self.bind_events()

        advance_splash("Инициализация менеджера настроек...")
        self.settings_manager = SettingsManager()
        advance_splash("Загрузка пользовательских настроек...")
        self.load_settings() # Загружаем настройки ДО инициализации других менеджеров

        advance_splash("Инициализация менеджера изображений...")
        self.image_manager = ImageManager(self)

        advance_splash("Инициализация менеджера экспорта...")
        self.export_manager = ExportManager(self)

        # Инициализация PageConstructor и связанных UI элементов после всех менеджеров
        advance_splash("Финальная настройка интерфейса...", increment=False) # Не увеличиваем шаг, т.к. следующий шаг для этого
        self.root.update_idletasks() # Даем Tk обработать очередь событий
        self._initial_ui_setup() # Это может занять время

        # Установка размеров страницы после того, как PageConstructor точно создан
        advance_splash("Установка размеров страницы...")
        self.on_page_setup_change() # Первоначальная установка размеров страницы

        # --- Завершение инициализации ---
        min_splash_duration = 2.0 # секунды (можно настроить)
        elapsed_time = time.time() - splash_start_time
        if elapsed_time < min_splash_duration:
            time.sleep(min_splash_duration - elapsed_time)

        self.splash.update_progress(100, "Завершено!")
        # Уменьшим задержку перед закрытием, если не нужна
        # time.sleep(0.3) 
        
        if hasattr(self, 'splash') and self.splash.winfo_exists():
            self.splash.close()
        
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        # Вызов установки sashpos и zoom_to_fit через after_idle
        self.root.after_idle(self._finalize_ui_layout) # Новый метод

    def _finalize_ui_layout(self):
        """Метод для финальных настроек UI после того, как окно стало видимым."""
        self.root.update_idletasks() # Убедимся, что все размеры актуальны

        # Установка начальных позиций разделителей для main_paned
        try:
            if hasattr(self, 'main_paned') and self.main_paned.winfo_exists():
                total_width = self.main_paned.winfo_width()
                if total_width > 100: # Убедимся, что ширина корректна
                    sash1_pos = int(total_width * (1/6))
                    sash2_pos = int(total_width * (5/6))
                    self.main_paned.sashpos(0, sash1_pos)
                    self.main_paned.sashpos(1, sash2_pos)
        except tk.TclError as e:
            print(f"Ошибка при установке sashpos: {e}") # Отладочный вывод
            pass # Игнорируем, если что-то пошло не так

        if hasattr(self, 'page_constructor') and self.page_constructor:
            self.page_constructor.zoom_to_fit()

    def _initial_ui_setup(self):
        """Начальная настройка UI."""
        self.root.update_idletasks()
        
    def setup_window(self):
        """Настройка главного окна"""
        # self.root уже создан
        self.root.title("Конструктор страниц манги v1.0")
        # Геометрия будет применена из настроек или по умолчанию, если настроек нет
        # self.root.geometry("1400x900") # Это будет установлено в load_settings или останется как есть
        self.root.minsize(1000, 700)

        try:
            # Путь к иконке должен быть правильным или обработан try-except
            icon_path = "manga_icon.ico"
            if os.path.exists(icon_path):
                icon = load_icon(icon_path)
                if icon:
                    self.root.iconphoto(True, icon)
            else:
                print(f"Предупреждение: Файл иконки не найден: {icon_path}")
        except Exception as e:
            print(f"Ошибка загрузки иконки: {e}")

        # Центрирование окна будет выполнено после установки геометрии
        # self.center_window() # Вызывается после установки геометрии

        self.setup_styles()
        
    def setup_styles(self):
        """Настройка стилей интерфейса"""
        style = ttk.Style()
        
        # Настройка темы
        try:
            style.theme_use('clam')  # Современная тема
        except:
            style.theme_use('default')
            
        # Кастомные стили
        style.configure('Title.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Subtitle.TLabel', font=('Arial', 10))
        style.configure('Tool.TButton', padding=5)
        
    def center_window(self):
        """Центрирование окна на экране"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        
    def setup_variables(self):
        """Инициализация переменных"""
        self.current_project = None
        self.project_modified = False
        self.zoom_level = tk.DoubleVar(value=1.0)
        self.snap_to_grid_var = tk.BooleanVar(value=False)
        self.show_grid_display_var = tk.BooleanVar(value=False)
        self.show_guides_display_var = tk.BooleanVar(value=False)
        self.manga_mode = tk.BooleanVar(value=True)  # True для манги (справа налево)
        self.current_page_size_name = tk.StringVar(value="B5")
        self.current_page_orientation_name = tk.StringVar(value="Портретный")
        self.custom_page_width_var = tk.StringVar(value=str(PAGE_SIZES["Пользовательский"][0]))
        self.custom_page_height_var = tk.StringVar(value=str(PAGE_SIZES["Пользовательский"][1]))
        
    def create_menu(self):
        """Создание главного меню"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # Меню "Файл"
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Файл", menu=file_menu)
        file_menu.add_command(label="Новый проект", command=self.new_project, accelerator="Ctrl+N")
        file_menu.add_command(label="Открыть проект", command=self.open_project, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Сохранить", command=self.save_project, accelerator="Ctrl+S")
        file_menu.add_command(label="Сохранить как...", command=self.save_project_as, accelerator="Ctrl+Shift+S")
        file_menu.add_separator()
        file_menu.add_command(label="Экспорт страницы", command=self.export_page, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="Выход", command=self.quit_application, accelerator="Alt+F4")
        
        # Меню "Правка"
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Правка", menu=edit_menu)
        edit_menu.add_command(label="Отменить", command=self.undo, accelerator="Ctrl+Z")
        edit_menu.add_command(label="Повторить", command=self.redo, accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Копировать", command=self.copy_panel, accelerator="Ctrl+C")
        edit_menu.add_command(label="Вставить", command=self.paste_panel, accelerator="Ctrl+V")
        edit_menu.add_command(label="Удалить", command=self.delete_panel, accelerator="Delete")
        edit_menu.add_separator()
        edit_menu.add_command(label="Выделить все", command=self.select_all, accelerator="Ctrl+A")
        
        # Меню "Вид"
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Вид", menu=view_menu)
        view_menu.add_checkbutton(label="Отображать сетку", variable=self.show_grid_display_var, command=self.toggle_grid_display)
        view_menu.add_checkbutton(label="Отображать направляющие", variable=self.show_guides_display_var, command=self.toggle_guides_display)
        view_menu.add_checkbutton(label="Привязка к сетке", variable=self.snap_to_grid_var, command=self.toggle_snap_to_grid)
        view_menu.add_separator()
        view_menu.add_command(label="Увеличить", command=self.zoom_in, accelerator="Ctrl++")
        view_menu.add_command(label="Уменьшить", command=self.zoom_out, accelerator="Ctrl+-")
        view_menu.add_command(label="Реальный размер", command=self.zoom_actual, accelerator="Ctrl+0")
        view_menu.add_command(label="По размеру окна", command=self.zoom_fit, accelerator="Ctrl+Shift+0")
        
        # Меню "Инструменты"
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Инструменты", menu=tools_menu)
        tools_menu.add_checkbutton(label="Режим манги (справа налево)", variable=self.manga_mode, command=self.toggle_manga_mode)
        tools_menu.add_separator()
        tools_menu.add_command(label="Настройки", command=self.open_settings)
        
        # Меню "Помощь"
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Помощь", menu=help_menu)
        help_menu.add_command(label="Руководство пользователя", command=self.show_help)
        help_menu.add_command(label="Горячие клавиши", command=self.show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self.show_about)
        
    def create_toolbar(self):
        """Создание панели инструментов"""
        self.toolbar_frame = ttk.Frame(self.root)
        self.toolbar_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)
        
        # Основные инструменты
        tool_frame = ttk.LabelFrame(self.toolbar_frame, text="Инструменты")
        tool_frame.pack(side=tk.LEFT, padx=5)
        
        self.tool_buttons = {}
        tools = [
            ("select", "Выбор", self.select_tool),
            ("panel", "Добавить панель", self.panel_tool),
            ("text", "Текст", self.text_tool),
            ("speech", "Речевой пузырь", self.speech_tool)
        ]
        
        for tool_id, tooltip, command in tools:
            btn = tk.Button(tool_frame, text=tool_id.title(), command=command, 
                          relief=tk.RAISED, borderwidth=1, padx=8, pady=4)
            btn.pack(side=tk.LEFT, padx=2)
            self.tool_buttons[tool_id] = btn
            create_tooltip(btn, tooltip)
            
        # Инструменты масштабирования
        zoom_frame = ttk.LabelFrame(self.toolbar_frame, text="Масштаб")
        zoom_frame.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(zoom_frame, text="-", command=self.zoom_out, width=3).pack(side=tk.LEFT)
        
        zoom_scale = ttk.Scale(zoom_frame, from_=0.1, to=3.0, variable=self.zoom_level, 
                              orient=tk.HORIZONTAL, length=100, command=self.on_zoom_change)
        zoom_scale.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(zoom_frame, text="+", command=self.zoom_in, width=3).pack(side=tk.LEFT)
        
        self.zoom_label = ttk.Label(zoom_frame, text="100%")
        self.zoom_label.pack(side=tk.LEFT, padx=5)
        
        # Настройки страницы
        page_frame = ttk.LabelFrame(self.toolbar_frame, text="Страница")
        page_frame.pack(side=tk.LEFT, padx=5)

        ttk.Label(page_frame, text="Размер:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.page_size_combo = ttk.Combobox(page_frame, textvariable=self.current_page_size_name,
                                        values=list(PAGE_SIZES.keys()),
                                        state="readonly", width=15)
        self.page_size_combo.set("B5") # Установка значения по умолчанию
        self.page_size_combo.grid(row=0, column=1, sticky=tk.W, padx=2, pady=2)
        self.page_size_combo.bind("<<ComboboxSelected>>", self.on_page_setup_change)

        ttk.Label(page_frame, text="Ориентация:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.page_orientation_combo = ttk.Combobox(page_frame, textvariable=self.current_page_orientation_name,
                                                values=list(ORIENTATIONS.keys()),
                                                state="readonly", width=15)
        self.page_orientation_combo.set("Портретный") # Установка значения по умолчанию
        self.page_orientation_combo.grid(row=1, column=1, sticky=tk.W, padx=2, pady=2)
        self.page_orientation_combo.bind("<<ComboboxSelected>>", self.on_page_setup_change)

        # Поля для пользовательского размера (изначально скрыты или неактивны)
        self.custom_size_frame = ttk.Frame(page_frame)
        # self.custom_size_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=2) # Пока не гридуем, покажем при выборе "Пользовательский"

        ttk.Label(self.custom_size_frame, text="Шир (px):").grid(row=0, column=0)
        custom_width_entry = ttk.Entry(self.custom_size_frame, textvariable=self.custom_page_width_var, width=7)
        custom_width_entry.grid(row=0, column=1)
        custom_width_entry.bind("<FocusOut>", self.on_page_setup_change)
        custom_width_entry.bind("<Return>", self.on_page_setup_change)


        ttk.Label(self.custom_size_frame, text="Выс (px):").grid(row=0, column=2)
        custom_height_entry = ttk.Entry(self.custom_size_frame, textvariable=self.custom_page_height_var, width=7)
        custom_height_entry.grid(row=0, column=3)
        custom_height_entry.bind("<FocusOut>", self.on_page_setup_change)
        custom_height_entry.bind("<Return>", self.on_page_setup_change)

        # Установка инструмента выбора как активного по умолчанию
        self.update_tool_buttons('select')

        
    def create_main_interface(self):
        """Создание основного интерфейса"""
        # Главная рабочая область
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Левая панель - библиотека шаблонов
        self.left_panel = ttk.Frame(self.main_paned)
        self.main_paned.add(self.left_panel, weight=1)
        
        # Инициализация библиотеки шаблонов
        self.templates_library = PanelTemplatesLibrary(self.left_panel, self)
        
        # Центральная область - конструктор страниц
        self.center_frame = ttk.Frame(self.main_paned)
        self.main_paned.add(self.center_frame, weight=4)
        
        # Инициализация конструктора страниц
        self.page_constructor = PageConstructor(self.center_frame, self)
        
        # Правая панель - свойства и слои
        self.right_panel = ttk.Frame(self.main_paned)
        self.main_paned.add(self.right_panel, weight=1)
        
        self.create_properties_panel()
        
    def create_properties_panel(self):
        """Создание панели свойств"""
        # Панель свойств объекта
        properties_frame = ttk.LabelFrame(self.right_panel, text="Свойства")
        properties_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Свойства позиции
        pos_frame = ttk.LabelFrame(properties_frame, text="Позиция")
        pos_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(pos_frame, text="X:").grid(row=0, column=0, sticky=tk.W)
        self.pos_x_var = tk.StringVar()
        ttk.Entry(pos_frame, textvariable=self.pos_x_var, width=8).grid(row=0, column=1, padx=2)
        
        ttk.Label(pos_frame, text="Y:").grid(row=0, column=2, sticky=tk.W, padx=(10,0))
        self.pos_y_var = tk.StringVar()
        ttk.Entry(pos_frame, textvariable=self.pos_y_var, width=8).grid(row=0, column=3, padx=2)
        
        # Свойства размера
        size_frame = ttk.LabelFrame(properties_frame, text="Размер")
        size_frame.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Label(size_frame, text="Ширина:").grid(row=0, column=0, sticky=tk.W)
        self.width_var = tk.StringVar()
        ttk.Entry(size_frame, textvariable=self.width_var, width=8).grid(row=0, column=1, padx=2)
        
        ttk.Label(size_frame, text="Высота:").grid(row=1, column=0, sticky=tk.W)
        self.height_var = tk.StringVar()
        ttk.Entry(size_frame, textvariable=self.height_var, width=8).grid(row=1, column=1, padx=2)
        
        # Панель слоев
        layers_frame = ttk.LabelFrame(self.right_panel, text="Слои")
        layers_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Список слоев
        self.layers_listbox = tk.Listbox(layers_frame, height=6)
        self.layers_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Кнопки управления слоями
        layers_buttons = ttk.Frame(layers_frame)
        layers_buttons.pack(fill=tk.X, padx=5, pady=2)
        
        ttk.Button(layers_buttons, text="↑", width=3, command=self.move_layer_up).pack(side=tk.LEFT)
        ttk.Button(layers_buttons, text="↓", width=3, command=self.move_layer_down).pack(side=tk.LEFT, padx=2)
        ttk.Button(layers_buttons, text="Удалить", command=self.delete_layer).pack(side=tk.RIGHT)
        
    def create_status_bar(self):
        """Создание статусной строки"""
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.status_label = ttk.Label(self.status_frame, text="Готов к работе")
        self.status_label.pack(side=tk.LEFT, padx=5)
        
        # Информация о координатах курсора
        self.coords_label = ttk.Label(self.status_frame, text="X: 0, Y: 0")
        self.coords_label.pack(side=tk.RIGHT, padx=5)
        
    def bind_events(self):
        """Привязка глобальных и локальных событий GUI."""
        # ── Горячие клавиши проекта ───────────────────────────────────────
        self.root.bind('<Control-n>', lambda e: self.new_project())
        self.root.bind('<Control-o>', lambda e: self.open_project())
        self.root.bind('<Control-s>', lambda e: self.save_project())
        self.root.bind('<Control-Shift-S>', lambda e: self.save_project_as())
        self.root.bind('<Control-equal>', lambda e: self.zoom_in())
        self.root.bind('<Control-minus>', lambda e: self.zoom_out())
        self.root.bind('<Control-0>', lambda e: self.zoom_actual())

        # ── Глобальные сочетания (Ctrl + C/V/A/Z/Y) в любой раскладке ─────
        def _on_global_shortcuts(event):
            # Требуется именно Ctrl
            if not event.state & 0x0004:
                return

            # 1. Пробуем обычный keysym (английская раскладка)
            sym = event.keysym.lower()

            # 2. Конвертируем имена вида "Cyrillic_es" → 'c'
            if sym.startswith("cyrillic_"):
                ru_name = sym.split("_")[1]          # es, em, ya …
                translit = {
                    "es": "c",  # с
                    "em": "v",  # м
                    "ya": "z",  # я
                    "en": "y",  # н
                    "ef": "a",  # ф
                }
                sym = translit.get(ru_name, sym)

            # 3. Фолбек на keycode – работает в любой раскладке
            if sym not in ("c", "v", "a", "z", "y"):
                keycode_map = {
                    # Windows-коды
                    67: "c", 86: "v", 65: "a", 90: "z", 89: "y",
                    # Типичные X11-коды (Wayland такие же)
                    54: "c", 55: "v", 38: "a", 52: "z", 21: "y",
                }
                sym = keycode_map.get(event.keycode, sym)

            # --- Выполняем команду ---------------------------------------
            if   sym == "c":  self.copy_panel()
            elif sym == "v":  self.paste_panel()
            elif sym == "a":  self.select_all()
            elif sym == "z":  self.undo()
            elif sym == "y":  self.redo()
            else:
                return                    # не наша комбинация

            return "break"                # событие обработано

        # Регистрируем обработчик, не перезаписывая чужие бинды
        self.root.bind_all("<KeyPress>", _on_global_shortcuts, add="+")

        # Системное событие закрытия окна
        self.root.protocol("WM_DELETE_WINDOW", self.quit_application)

    def on_page_setup_change(self, event=None):
        selected_size_key = self.current_page_size_name.get()
        selected_orientation_key = self.current_page_orientation_name.get()
        
        orientation_val = ORIENTATIONS.get(selected_orientation_key, "portrait")

        if selected_size_key == "Пользовательский":
            if not self.custom_size_frame.winfo_ismapped(): # Если еще не отображено
                self.custom_size_frame.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=2)
            try:
                # Используем значения из полей для пользовательского размера
                page_w_base = int(self.custom_page_width_var.get())
                page_h_base = int(self.custom_page_height_var.get())
                # Обновляем значение в PAGE_SIZES для "Пользовательский"
                PAGE_SIZES["Пользовательский"] = (page_w_base, page_h_base)
            except ValueError:
                # Если некорректный ввод, используем текущие значения из PAGE_SIZES
                page_w_base, page_h_base = PAGE_SIZES.get(selected_size_key, PAGE_SIZES["B5"])
                self.custom_page_width_var.set(str(page_w_base))
                self.custom_page_height_var.set(str(page_h_base))
        else:
            if self.custom_size_frame.winfo_ismapped(): # Скрываем если было отображено
                self.custom_size_frame.grid_remove()
            page_w_base, page_h_base = PAGE_SIZES.get(selected_size_key, PAGE_SIZES["B5"])
            # Обновляем поля пользовательского ввода, чтобы они соответствовали выбранному пресету
            # (на случай если пользователь потом выберет "Пользовательский")
            self.custom_page_width_var.set(str(page_w_base))
            self.custom_page_height_var.set(str(page_h_base))


        if orientation_val == "landscape":
            final_page_w, final_page_h = page_h_base, page_w_base
        else: # portrait
            final_page_w, final_page_h = page_w_base, page_h_base
        
        if hasattr(self, 'page_constructor') and self.page_constructor:
            # Устанавливаем размеры PageConstructor в ПИКСЕЛЯХ ПРИ 300 DPI
            self.page_constructor.page_width = final_page_w
            self.page_constructor.page_height = final_page_h
            self.page_constructor.update_scroll_region()
            self.page_constructor.redraw()

        self.project_modified = True # Считаем это изменением проекта
        self.update_title()
        if event: # Чтобы не вызывалось при инициализации без явного действия пользователя
            self.set_status(f"Размер страницы: {selected_size_key} ({final_page_w}x{final_page_h}), {selected_orientation_key}")

    def toggle_grid_display(self):
        """Переключение отображения сетки."""
        if hasattr(self, 'page_constructor') and self.page_constructor:
            self.page_constructor.show_grid = self.show_grid_display_var.get()
            self.page_constructor.redraw()
            status = "включена" if self.page_constructor.show_grid else "отключена"
            self.set_status(f"Отображение сетки {status}")

    def toggle_guides_display(self):
        """Переключение отображения направляющих."""
        if hasattr(self, 'page_constructor') and self.page_constructor:
            self.page_constructor.show_guides = self.show_guides_display_var.get()
            self.page_constructor.redraw()
            status = "включены" if self.page_constructor.show_guides else "отключены"
            self.set_status(f"Отображение направляющих {status}")

    def toggle_snap_to_grid(self):
        """Переключение привязки к сетке."""
        if hasattr(self, 'page_constructor') and self.page_constructor:
            self.page_constructor.snap_to_grid = self.snap_to_grid_var.get()
            # Перерисовка не нужна, но статус обновим
            status = "включена" if self.page_constructor.snap_to_grid else "отключена"
            self.set_status(f"Привязка к сетке {status}")
        
    # Методы работы с проектом
    def new_project(self):
        """Создание нового проекта"""
        if self.check_unsaved_changes():
            self.current_project = None
            self.project_modified = False
            self.page_constructor.clear_page()
            self.templates_library.refresh()
            self.update_title()
            self.set_status("Создан новый проект")
            
    def open_project(self):
        """Открытие проекта"""
        if self.check_unsaved_changes():
            filename = filedialog.askopenfilename(
                title="Открыть проект",
                filetypes=[("Проекты манги", "*.manga"), ("Все файлы", "*.*")]
            )
            if filename:
                self.load_project(filename)
                
    def save_project(self):
        """Сохранение проекта"""
        if self.current_project:
            self.save_project_file(self.current_project)
        else:
            self.save_project_as()
            
    def save_project_as(self):
        """Сохранение проекта как"""
        filename = filedialog.asksaveasfilename(
            title="Сохранить проект как",
            defaultextension=".manga",
            filetypes=[("Проекты манги", "*.manga"), ("Все файлы", "*.*")]
        )
        if filename:
            self.save_project_file(filename)
            self.current_project = filename
            
    # Методы инструментов
    def select_tool(self):
        """Активация инструмента выбора"""
        self.page_constructor.set_tool('select')
        self.update_tool_buttons('select')
        self.set_status("Инструмент выбора активен")

    def update_properties_panel(self):
        """Обновление панели свойств выбранной панели"""
        if not hasattr(self, 'pos_x_var'):
            return
            
        if self.page_constructor.selected_panels:
            panel = self.page_constructor.selected_panels[0]
            self.pos_x_var.set(f"{panel.x:.1f}")
            self.pos_y_var.set(f"{panel.y:.1f}")
            self.width_var.set(f"{panel.width:.1f}")
            self.height_var.set(f"{panel.height:.1f}")
        else:
            self.pos_x_var.set("")
            self.pos_y_var.set("")
            self.width_var.set("")
            self.height_var.set("")

    def update_layers_list(self):
        """Обновляет список слоев в правой панели."""
        if not hasattr(self, 'layers_listbox') or not self.layers_listbox.winfo_exists():
            return

        self.layers_listbox.delete(0, tk.END)
        
        # Группируем панели по слоям
        layers_dict = {}
        for panel in self.page_constructor.panels:
            if panel.layer not in layers_dict:
                layers_dict[panel.layer] = []
            layers_dict[panel.layer].append(panel)
        
        # Сортируем слои от верхних к нижним (для отображения)
        sorted_layers = sorted(layers_dict.keys(), reverse=True)
        
        for layer_num in sorted_layers:
            panels_in_layer = layers_dict[layer_num]
            
            # Добавляем заголовок слоя
            layer_name = f"═══ Слой {layer_num} ═══"
            self.layers_listbox.insert(tk.END, layer_name)
            self.layers_listbox.itemconfig(tk.END, {'bg': '#f0f0f0', 'fg': '#000080'})
            
            # Добавляем панели этого слоя
            for panel in panels_in_layer:
                panel_id_short = panel.id.split('-')[0][:8]
                text_preview = f": {panel.content_text[:15]}..." if panel.content_text else ""
                item_text = f"  └ {panel.panel_type.value.capitalize()} ({panel_id_short}){text_preview}"
                
                self.layers_listbox.insert(tk.END, item_text)
                
                # Подсветка выбранной панели
                if panel.selected:
                    self.layers_listbox.itemconfig(tk.END, {'bg': '#e0e8f0'})
                else:
                    self.layers_listbox.itemconfig(tk.END, {'bg': 'white'})

        # Обновляем также панель свойств
        self.update_properties_panel()
        
    def panel_tool(self):
        """Активация инструмента добавления панели"""
        self.page_constructor.set_tool('panel')
        self.update_tool_buttons('panel')
        self.set_status("Инструмент панели активен - кликните и перетащите для создания панели")
        
    def text_tool(self):
        """Активация инструмента текста"""
        self.page_constructor.set_tool('text')
        self.update_tool_buttons('text')
        self.set_status("Инструмент текста активен")
        
    def speech_tool(self):
        """Активация инструмента речевого пузыря"""
        self.page_constructor.set_tool('speech')
        self.update_tool_buttons('speech')
        self.set_status("Инструмент речевого пузыря активен")

    def update_tool_buttons(self, active_tool):
        """Обновление внешнего вида кнопок инструментов"""
        for tool_id, btn in self.tool_buttons.items():
            if tool_id == active_tool:
                btn.configure(relief=tk.SUNKEN, bg='#E0E0E0')
            else:
                btn.configure(relief=tk.RAISED, bg='SystemButtonFace')
        
    # Методы масштабирования
    def zoom_in(self):
        """Увеличение масштаба"""
        current = self.zoom_level.get()
        new_zoom = min(3.0, current * 1.2)
        self.zoom_level.set(new_zoom)
        self.apply_zoom()
        
    def zoom_out(self):
        """Уменьшение масштаба"""
        current = self.zoom_level.get()
        new_zoom = max(0.1, current / 1.2)
        self.zoom_level.set(new_zoom)
        self.apply_zoom()
        
    def zoom_actual(self):
        """Реальный размер (100%)"""
        self.zoom_level.set(1.0)
        self.apply_zoom()
        
    def zoom_fit(self):
        """Масштаб по размеру окна"""
        self.page_constructor.zoom_to_fit()
        
    def on_zoom_change(self, value):
        """Обработчик изменения масштаба"""
        self.apply_zoom()
        
    def apply_zoom(self):
        """Применение масштаба"""
        zoom = self.zoom_level.get()
        self.page_constructor.set_zoom(zoom)
        self.zoom_label.config(text=f"{int(zoom * 100)}%")
        
    # Утилиты
    def set_status(self, message):
        """Установка текста в статусной строке"""
        self.status_label.config(text=message)
        
    def update_title(self):
        """Обновление заголовка окна"""
        title = "Конструктор страниц манги v1.0"
        if self.current_project:
            project_name = os.path.basename(self.current_project)
            title += f" - {project_name}"
        if self.project_modified:
            title += "*"
        self.root.title(title)
        
    def check_unsaved_changes(self):
        """Проверка несохраненных изменений"""
        if self.project_modified:
            result = messagebox.askyesnocancel(
                "Несохраненные изменения",
                "Проект был изменен. Сохранить изменения?"
            )
            if result is True:
                self.save_project()
                return True
            elif result is False:
                return True
            else:
                return False
        return True
        
    def load_settings(self):
        """Загрузка настроек"""
        # settings_manager уже должен быть инициализирован
        settings = self.settings_manager.settings # Загружаем настройки один раз

        # Применение геометрии окна
        if settings.window_maximized:
            self.root.state('zoomed')
        elif settings.window_geometry:
            try:
                self.root.geometry(settings.window_geometry)
            except tk.TclError:
                print(f"Ошибка применения геометрии окна: {settings.window_geometry}. Используется размер по умолчанию.")
                self.root.geometry("1400x900")
        else:
            self.root.geometry("1400x900") # Размер по умолчанию

        self.root.update_idletasks() # Обновляем, чтобы размеры применились
        self.center_window() # Центрируем после установки геометрии

        # Применение других настроек интерфейса (примеры)
        # Например, тема, язык, шрифты (если они влияют на UI до полного отображения)
        # self.manga_mode.set(settings.project.manga_mode) # Если это глобальная настройка

        # Настройки для PageConstructor (если они не применяются через on_page_setup_change)
        if hasattr(self, 'page_constructor'):
            self.page_constructor.snap_to_grid = settings.panels.snap_to_grid
            self.page_constructor.grid_size = settings.canvas.grid_size
            # и т.д.
        
        # Устанавливаем значения для элементов управления размером страницы из настроек
        self.current_page_size_name.set(settings.project.default_page_size)
        # Ориентация может быть не сохранена в settings.project, если она определяется размерами.
        # Для простоты, оставим значение по умолчанию или определим по default_page_size.
        
        default_w, default_h = PAGE_SIZES.get(settings.project.default_page_size, PAGE_SIZES["B5"])
        if default_w > default_h and settings.project.default_page_size != "Пользовательский":
            self.current_page_orientation_name.set("Альбомный")
        else:
            self.current_page_orientation_name.set("Портретный")

        if settings.project.default_page_size == "Пользовательский":
             # Если в настройках нет явных пользовательских размеров, используем из PAGE_SIZES["Пользовательский"]
            user_w, user_h = PAGE_SIZES["Пользовательский"]
            self.custom_page_width_var.set(str(user_w)) # Предполагаем, что в PAGE_SIZES["Пользовательский"] актуальные значения
            self.custom_page_height_var.set(str(user_h))
        else:
            # Если выбран стандартный размер, поля для пользовательского заполняем им
            self.custom_page_width_var.set(str(default_w))
            self.custom_page_height_var.set(str(default_h))
        
    def quit_application(self):
        """Выход из приложения"""
        if self.check_unsaved_changes():
            self.settings_manager.save_settings()
            self.root.quit()
            
    # Заглушки для методов, которые будут реализованы в других модулях
    def import_images(self):
        """Импорт изображений в проект"""
        if not self.image_manager:
            messagebox.showerror("Ошибка", "Менеджер изображений не инициализирован")
            return
            
        self.image_manager.show_image_library()

    def export_page(self):
        """Экспорт текущей страницы"""
        if not self.page_constructor.panels:
            messagebox.showwarning("Предупреждение", "Нет панелей для экспорта")
            return
            
        self.export_manager.show_export_dialog()

    def undo(self):
        """Отмена последнего действия"""
        if hasattr(self.page_constructor, 'undo_action') and self.page_constructor.undo_action():
            self.project_modified = True # Отмена считается модификацией
            self.update_title()
            self.set_status("Отменено")
            # Обновление UI уже происходит в _post_history_change_update
        else:
            self.set_status("Нечего отменять")

    def redo(self):
        """Повтор отмененного действия"""
        if hasattr(self.page_constructor, 'redo_action') and self.page_constructor.redo_action():
            self.project_modified = True # Повтор считается модификацией
            self.update_title()
            self.set_status("Повторено")
            # Обновление UI уже происходит в _post_history_change_update
        else:
            self.set_status("Нечего повторять")

    def copy_panel(self):
        """Копирование выделенных панелей"""
        if not self.page_constructor.selected_panels:
            self.set_status("Нет выделенных панелей для копирования")
            return
            
        # Сохранение панелей в буфер обмена
        import copy
        self.clipboard_panels = copy.deepcopy(self.page_constructor.selected_panels)
        self.set_status(f"Скопировано панелей: {len(self.clipboard_panels)}")

    def paste_panel(self):
        """Вставка панелей из буфера обмена"""
        if not hasattr(self, 'clipboard_panels') or not self.clipboard_panels:
            self.set_status("Буфер обмена пуст")
            return
            
        import copy
        
        # Очистка текущего выделения
        self.page_constructor.clear_selection()
        
        # Вставка панелей со смещением
        offset_x = 20
        offset_y = 20
        
        for panel in self.clipboard_panels:
            new_panel = copy.deepcopy(panel)
            new_panel.id = str(uuid.uuid4())  # Новый ID
            new_panel.x += offset_x
            new_panel.y += offset_y
            new_panel.selected = True
            
            # Проверка границ страницы
            if new_panel.x + new_panel.width > self.page_constructor.page_width:
                new_panel.x = self.page_constructor.page_width - new_panel.width
            if new_panel.y + new_panel.height > self.page_constructor.page_height:
                new_panel.y = self.page_constructor.page_height - new_panel.height
                
            self.page_constructor.panels.append(new_panel)
            self.page_constructor.selected_panels.append(new_panel)
            
        new_panel.layer = max(p.layer for p in self.page_constructor.panels) + 1

        self.page_constructor.save_history_state()
        self.page_constructor.redraw()
        self.project_modified = True
        self.update_title()
        self.set_status(f"Вставлено панелей: {len(self.clipboard_panels)}")

    def delete_panel(self):
        """Удаление выделенных панелей"""
        if not self.page_constructor.selected_panels:
            self.set_status("Нет выделенных панелей для удаления")
            return
            
        # Подтверждение удаления
        count = len(self.page_constructor.selected_panels)
        if count > 1:
            result = messagebox.askyesno("Подтверждение", 
                                    f"Удалить {count} выделенных панелей?")
            if not result:
                return
                
        # Удаление панелей
        for panel in self.page_constructor.selected_panels:
            if panel in self.page_constructor.panels:
                self.page_constructor.panels.remove(panel)
                
        self.page_constructor.clear_selection()
        self.page_constructor.save_history_state()
        self.page_constructor.redraw()
        self.project_modified = True
        self.update_title()
        self.set_status(f"Удалено панелей: {count}")

    def select_all(self):
        """Выделение всех панелей"""
        self.page_constructor.clear_selection()
        
        for panel in self.page_constructor.panels:
            self.page_constructor.select_panel(panel)
            
        self.page_constructor.redraw()
        self.set_status(f"Выделено панелей: {len(self.page_constructor.panels)}")
    def toggle_grid(self):
        """Переключение отображения сетки"""
        self.page_constructor.show_grid = self.show_grid_display_var.get()
        self.page_constructor.redraw()
        status = "включена" if self.page_constructor.show_grid else "отключена"
        self.set_status(f"Сетка {status}")

    def toggle_guides(self):
        """Переключение отображения направляющих"""
        self.page_constructor.show_guides = self.show_guides.get()
        self.page_constructor.redraw()
        status = "включены" if self.page_constructor.show_guides else "отключены"
        self.set_status(f"Направляющие {status}")
    def toggle_manga_mode(self):
        """Переключение режима манги"""
        manga_mode = self.manga_mode.get()
        # Здесь можно добавить логику изменения направления чтения
        # Например, изменение порядка панелей или интерфейса
        
        mode_text = "справа налево" if manga_mode else "слева направо"
        self.set_status(f"Режим чтения: {mode_text}")

    def open_settings(self):
        """Открытие окна настроек"""
        self.settings_manager.show_settings_dialog(self.root)
    def show_help(self):
        """Показ справки"""
        help_window = tk.Toplevel(self.root)
        help_window.title("Руководство пользователя")
        help_window.geometry("600x500")
        
        # Создание текстового виджета с прокруткой
        text_frame = tk.Frame(help_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Arial", 10))
        scrollbar = tk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Содержание справки
        help_content = """КОНСТРУКТОР СТРАНИЦ МАНГИ - РУКОВОДСТВО ПОЛЬЗОВАТЕЛЯ

    ОСНОВЫ РАБОТЫ:
    1. Создание новой страницы: Файл → Новый проект
    2. Добавление панелей: Выберите инструмент "Панель" и нарисуйте прямоугольник
    3. Изменение размера: Выделите панель и перетащите маркеры
    4. Перемещение: Перетащите панель мышью

    ИНСТРУМЕНТЫ:
    • Выбор (V) - выделение и перемещение объектов
    • Панель (P) - создание новых панелей
    • Текст (T) - добавление текста
    • Речевой пузырь (S) - создание диалогов

    ПАНЕЛИ:
    • Прямоугольные - обычные панели
    • Круглые - для снов, воспоминаний
    • Речевые пузыри - для диалогов
    • Splash - большие эффектные панели

    РАБОТА С ИЗОБРАЖЕНИЯМИ:
    1. Ctrl+I - импорт изображений в библиотеку
    2. Выделите панель
    3. Выберите изображение из библиотеки
    4. Настройте обрезку (центр, умная, подгонка)

    ШАБЛОНЫ:
    • Используйте готовые профессиональные макеты
    • Классические - для обычных сцен
    • Экшн - для динамичных моментов
    • Диалоговые - для разговоров
    • Эмоциональные - для драматических сцен

    ЭКСПОРТ:
    1. Ctrl+E - открыть диалог экспорта
    2. Выберите формат (PNG, JPEG, PDF, CBZ)
    3. Настройте качество и DPI
    4. Добавьте водяной знак при необходимости

    ГОРЯЧИЕ КЛАВИШИ:
    Ctrl+N - Новый проект
    Ctrl+O - Открыть
    Ctrl+S - Сохранить
    Ctrl+Z - Отменить
    Ctrl+Y - Повторить
    Ctrl+C - Копировать
    Ctrl+V - Вставить
    Delete - Удалить
    Ctrl+A - Выделить все
    Ctrl+G - Переключить сетку

    СОВЕТЫ:
    • Используйте сетку для точного позиционирования
    • Экспериментируйте с шаблонами
    • Настройте автосохранение в настройках
    • Используйте слои для сложных композиций"""

        text_widget.insert(1.0, help_content)
        text_widget.configure(state=tk.DISABLED)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Кнопка закрытия
        tk.Button(help_window, text="Закрыть", command=help_window.destroy).pack(pady=10)

    def show_shortcuts(self):
        """Показ горячих клавиш"""
        shortcuts_window = tk.Toplevel(self.root)
        shortcuts_window.title("Горячие клавиши")
        shortcuts_window.geometry("400x500")
        
        # Создание таблицы горячих клавиш
        frame = tk.Frame(shortcuts_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Заголовки
        tk.Label(frame, text="Действие", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        tk.Label(frame, text="Горячая клавиша", font=("Arial", 10, "bold")).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        
        # Список горячих клавиш
        shortcuts = [
            ("Новый проект", "Ctrl+N"),
            ("Открыть проект", "Ctrl+O"),
            ("Сохранить", "Ctrl+S"),
            ("Сохранить как", "Ctrl+Shift+S"),
            ("Отменить", "Ctrl+Z"),
            ("Повторить", "Ctrl+Y"),
            ("Копировать", "Ctrl+C"),
            ("Вставить", "Ctrl+V"),
            ("Удалить", "Delete"),
            ("Выделить все", "Ctrl+A"),
            ("Импорт изображений", "Ctrl+I"),
            ("Экспорт страницы", "Ctrl+E"),
            ("Увеличить", "Ctrl++"),
            ("Уменьшить", "Ctrl+-"),
            ("Реальный размер", "Ctrl+0"),
            ("Переключить сетку", "Ctrl+G"),
            ("Инструмент выбора", "V"),
            ("Инструмент панели", "P"),
            ("Инструмент текста", "T"),
            ("Речевой пузырь", "S")
        ]
        
        for i, (action, shortcut) in enumerate(shortcuts, 1):
            tk.Label(frame, text=action).grid(row=i, column=0, sticky="w", padx=5, pady=2)
            tk.Label(frame, text=shortcut, font=("Arial", 9, "bold")).grid(row=i, column=1, sticky="w", padx=5, pady=2)
        
        # Кнопка закрытия
        tk.Button(shortcuts_window, text="Закрыть", command=shortcuts_window.destroy).pack(pady=10)

    def show_about(self):
        """О программе"""
        about_window = tk.Toplevel(self.root)
        about_window.title("О программе")
        about_window.geometry("400x300")
        about_window.resizable(False, False)
        
        # Центрирование окна
        about_window.transient(self.root)
        about_window.grab_set()
        
        # Содержимое
        main_frame = tk.Frame(about_window)
        main_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
        
        # Заголовок
        title_label = tk.Label(main_frame, text="Конструктор страниц манги", 
                            font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # Версия
        version_label = tk.Label(main_frame, text="Версия 1.0", 
                                font=("Arial", 12))
        version_label.pack()
        
        # Описание
        desc_text = """Профессиональный инструмент для создания 
    страниц манги и комиксов

    Особенности:
    • Библиотека профессиональных шаблонов
    • Умная система обрезки изображений
    • Поддержка различных типов панелей
    • Экспорт в популярные форматы
    • Специальные инструменты для манги"""
        
        desc_label = tk.Label(main_frame, text=desc_text, 
                            font=("Arial", 10), justify=tk.CENTER)
        desc_label.pack(pady=15)
        
        # Авторство
        author_label = tk.Label(main_frame, text="Создано с помощью Claude AI", 
                            font=("Arial", 9), fg="#666666")
        author_label.pack()
        
        # Кнопки
        buttons_frame = tk.Frame(main_frame)
        buttons_frame.pack(pady=15)
        
        tk.Button(buttons_frame, text="GitHub", 
                command=lambda: webbrowser.open("https://github.com")).pack(side=tk.LEFT, padx=5)
        tk.Button(buttons_frame, text="Закрыть", 
                command=about_window.destroy).pack(side=tk.LEFT, padx=5)
    def load_project(self, filename):
        """Загрузка проекта из файла"""
        try:
            with open(filename, 'rb') as f:
                project_data = pickle.load(f)
                
            # Восстановление состояния
            if 'panels' in project_data:
                self.page_constructor.panels = project_data['panels']
                
            if 'page_size' in project_data:
                page_width, page_height = project_data['page_size']
                self.page_constructor.page_width = page_width
                self.page_constructor.page_height = page_height
                
            if 'settings' in project_data:
                # Восстановление настроек проекта
                pass
                
            self.page_constructor.undo_stack.clear()
            self.page_constructor.redo_stack.clear()
            self.page_constructor.save_history_state()
            
            # Обновление интерфейса
            self.page_constructor.clear_selection()
            self.page_constructor.redraw()
            self.page_constructor.zoom_to_fit()

            self.update_layers_list()
            
            self.current_project = filename
            self.project_modified = False
            self.update_title()
            
            # Добавление в список недавних файлов
            self.settings_manager.add_recent_file(filename)
            
            self.set_status(f"Проект загружен: {os.path.basename(filename)}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить проект:\n{e}")

    def save_project_file(self, filename):
        """Сохранение проекта в файл"""
        try:
            # Подготовка данных для сохранения
            project_data = {
                'version': '1.0',
                'panels': self.page_constructor.panels,
                'page_size': (self.page_constructor.page_width, self.page_constructor.page_height),
                'settings': {
                    'manga_mode': self.manga_mode.get(),
                    'show_grid': self.snap_to_grid.get(),
                    'show_guides': self.show_guides.get(),
                    'zoom_level': self.zoom_level.get()
                },
                'metadata': {
                    'created': datetime.now().isoformat(),
                    'app_version': '1.0'
                }
            }
            
            # Сохранение
            with open(filename, 'wb') as f:
                pickle.dump(project_data, f)
                
            self.project_modified = False
            self.update_title()
            
            # Добавление в список недавних файлов
            self.settings_manager.add_recent_file(filename)
            
            self.set_status(f"Проект сохранён: {os.path.basename(filename)}")
            
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить проект:\n{e}")
    def move_layer_up(self):
        if not self.page_constructor.selected_panels:
            self.set_status("Нет выделенных панелей")
            return
            
        panel = self.page_constructor.selected_panels[0]
        
        # Просто увеличиваем номер слоя. Сортировка при отрисовке сделает остальное.
        panel.layer += 1
        
        self.page_constructor.redraw()
        self.project_modified = True
        self.update_title()
        self.update_layers_list() # Этот метод должен корректно обработать обновленные слои
        self.set_status(f"Панель '{panel.id[:8]}' перемещена на слой {panel.layer}")

    def move_layer_down(self):
        if not self.page_constructor.selected_panels:
            self.set_status("Нет выделенных панелей")
            return
            
        panel = self.page_constructor.selected_panels[0]

        if panel.layer > 0: # Нельзя опустить ниже 0-го слоя
            panel.layer -= 1
        else:
            self.set_status("Панель уже на нижнем слое (0)")
            return

        self.page_constructor.redraw()
        self.project_modified = True
        self.update_title()
        self.update_layers_list()
        self.set_status(f"Панель '{panel.id[:8]}' перемещена на слой {panel.layer}")

    def delete_layer(self):
        """Удалить выделенные панели (аналог delete_panel)"""
        self.delete_panel()


def main():
    """Точка входа в программу"""
    app = None # Для доступа в блоке except
    try:
        app = MangaConstructorApp()
        app.root.mainloop()
    except Exception as e:
        if app and hasattr(app, 'splash') and app.splash.winfo_exists():
            app.splash.close()
        messagebox.showerror("Критическая ошибка", f"Критическая ошибка приложения:\n{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()