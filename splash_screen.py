import tkinter as tk
from tkinter import ttk
import time # Для минимального времени показа

class SplashScreen(tk.Toplevel):
    def __init__(self, parent_for_style_context, width=450, height=300, title="Загрузка Конструктора Манги..."):
        super().__init__() # Создаем как Toplevel без явного родителя initially
        self.overrideredirect(True)  # Убираем рамку окна

        # Центрирование на экране
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

        self.configure(bg="#2E2E2E") # Темно-серый фон

        # Используем стиль от основного root, если он уже создан
        style = ttk.Style(parent_for_style_context)
        try:
            # Попробуем использовать тему, если доступна
            current_theme = style.theme_use()
            if not current_theme: # Если тема не была установлена
                 style.theme_use(style.theme_names()[0] if style.theme_names() else 'default')
        except tk.TclError:
             style.theme_use(style.theme_names()[0] if style.theme_names() else 'default')


        style.configure("Splash.TFrame", background="#2E2E2E")

        # --- Начало исправленного блока для Progressbar ---
        try:
            # 1. Получаем структуру (layout) стандартного горизонтального прогресс-бара для текущей темы
            default_horizontal_layout = style.layout('Horizontal.TProgressbar')

            if default_horizontal_layout:
                # 2. Определяем layout для нашего кастомного стиля, копируя его из стандартного
                # Это гарантирует, что ttk знает, как рисовать наш кастомный прогресс-бар
                style.layout('Horizontal.Splash.TProgressbar', default_horizontal_layout)
            else:
                # Этот случай маловероятен, если ttk работает, но для надежности
                print("Предупреждение: Не удалось получить стандартный layout для Horizontal.TProgressbar.")
                # Прогресс-бар может выглядеть стандартно или не стилизоваться.

            # 3. Теперь конфигурируем свойства нашего кастомного стиля.
            # Так как layout уже определен, это должно работать.
            style.configure("Horizontal.Splash.TProgressbar",
                            thickness=20,
                            troughcolor='#404040',  # Цвет "желоба" под полосой
                            background='#007ACC')   # Цвет самой полосы прогресса
        except tk.TclError as e:
            # Если даже 'Horizontal.TProgressbar' не найден (очень редкий случай, проблема с Tk/ttk или темой)
            print(f"Критическая ошибка стилизации прогресс-бара: {e}. Прогресс-бар не будет кастомно стилизован.")
            # В этом случае прогресс-бар будет создан со стилем по умолчанию.

        # --- Конец исправленного блока для Progressbar ---

        style.configure("Splash.TLabel", background="#2E2E2E", foreground="#E0E0E0")
        style.configure("Splash.Title.TLabel", background="#2E2E2E", foreground="#FFFFFF", font=("Arial", 16, "bold"))
        style.configure("Splash.Logo.TLabel", background="#2E2E2E", foreground="#B0B0B0", font=("Arial", 24, "italic"))


        main_frame = ttk.Frame(self, style="Splash.TFrame")
        main_frame.pack(expand=True, fill=tk.BOTH, padx=2, pady=2) # Небольшая "рамка"

        self.title_label = ttk.Label(main_frame, text=title, style="Splash.Title.TLabel")
        self.title_label.pack(pady=(30, 15))

        # Место для логотипа (можно добавить иконку приложения, если она есть)
        # self.app_icon = tk.PhotoImage(file="path_to_your_icon.png") # Если есть иконка
        # self.logo_icon_label = ttk.Label(main_frame, image=self.app_icon, style="Splash.TLabel")
        # self.logo_icon_label.pack(pady=10)

        self.logo_text_label = ttk.Label(main_frame, text="Manga Constructor", style="Splash.Logo.TLabel")
        self.logo_text_label.pack(pady=10)

        self.status_label = ttk.Label(main_frame, text="Инициализация...", font=("Arial", 10), style="Splash.TLabel")
        self.status_label.pack(pady=(15, 5))

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var,
                                            maximum=100, length=width-80, mode='determinate',
                                            style="Splash.TProgressbar") # Используем базовое имя стиля "Splash.TProgressbar"
        self.progress_bar.pack(pady=(5, 30))

        self.lift() # Поверх других окон
        self.update_idletasks() # Обновляем, чтобы окно сразу отрисовалось

    def update_progress(self, value: float, text: str):
        self.progress_var.set(value)
        self.status_label.config(text=text)
        # Заменяем update_idletasks() на update() для более активной перерисовки
        try:
            if self.winfo_exists(): # Проверяем, существует ли еще окно
                self.update()
        except tk.TclError:
            pass # Окно могло быть уничтожено

    def close(self):
        # Добавим проверку перед уничтожением
        try:
            if self.winfo_exists():
                self.destroy()
        except tk.TclError:
            pass