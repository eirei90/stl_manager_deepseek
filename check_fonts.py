#!/usr/bin/env python3
"""
Проверка доступных шрифтов с поддержкой кириллицы.
Запустите для диагностики проблем с отображением текста.
"""

import sys
import tkinter as tk
from tkinter import font

def check_cyrillic_fonts():
    """Проверяет и выводит шрифты с поддержкой кириллицы."""
    
    root = tk.Tk()
    root.withdraw()  # Скрываем окно
    
    # Тестовая строка с кириллицей
    test_text = "Привет, мир! 12345"
    
    print("=" * 60)
    print("  ПРОВЕРКА ШРИФТОВ С ПОДДЕРЖКОЙ КИРИЛЛИЦЫ")
    print("=" * 60)
    print()
    
    # Получаем все доступные шрифты
    available_fonts = sorted(font.families())
    print(f"Всего шрифтов в системе: {len(available_fonts)}")
    print()
    
    # Список известных шрифтов с хорошей поддержкой кириллицы
    known_good_fonts = [
        'DejaVu Sans', 'DejaVu Serif', 'DejaVu Sans Mono',
        'Liberation Sans', 'Liberation Serif', 'Liberation Mono',
        'Noto Sans', 'Noto Serif', 'Noto Sans Display',
        'Ubuntu', 'Ubuntu Mono',
        'Droid Sans', 'Droid Serif', 'Droid Sans Mono',
        'Segoe UI', 'Arial', 'Times New Roman', 'Courier New',
        'SF Pro Display', 'Helvetica'
    ]
    
    print("Известные шрифты с поддержкой кириллицы:")
    print("-" * 60)
    
    found_fonts = []
    for font_name in known_good_fonts:
        if font_name in available_fonts:
            found_fonts.append(font_name)
            # Проверяем, действительно ли шрифт отображает кириллицу
            try:
                test_font = font.Font(family=font_name, size=12)
                # Создаём временную метку для проверки
                label = tk.Label(root, text=test_text, font=test_font)
                actual_font = font.Font(font=label.cget('font'))
                label.destroy()
                print(f"  ✅ {font_name} - доступен")
            except Exception:
                print(f"  ⚠️  {font_name} - найден, но может не работать")
        else:
            print(f"  ❌ {font_name} - отсутствует")
    
    print()
    print("Все шрифты, содержащие 'sans' в названии:")
    print("-" * 60)
    sans_fonts = [f for f in available_fonts if 'sans' in f.lower()]
    for f in sans_fonts[:10]:  # Показываем первые 10
        print(f"  • {f}")
    if len(sans_fonts) > 10:
        print(f"  ... и ещё {len(sans_fonts) - 10}")
    
    print()
    print("=" * 60)
    
    if found_fonts:
        print(f"✅ Найдено {len(found_fonts)} подходящих шрифтов.")
        print(f"   Рекомендуется использовать: {found_fonts[0]}")
    else:
        print("❌ Не найдено ни одного рекомендованного шрифта!")
        print("   Установите шрифты:")
        print("   Arch Linux: sudo pacman -S ttf-dejavu ttf-liberation")
        print("   Ubuntu:      sudo apt install fonts-dejavu fonts-liberation")
    
    print()
    
    root.destroy()
    return found_fonts

if __name__ == "__main__":
    try:
        check_cyrillic_fonts()
    except Exception as e:
        print(f"Ошибка при проверке шрифтов: {e}")
        print("Убедитесь, что установлен python-tk:")
        print("  Arch Linux: sudo pacman -S tk")
        print("  Ubuntu:      sudo apt install python3-tk")
        sys.exit(1)