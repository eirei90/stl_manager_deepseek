#!/usr/bin/env python3
"""
Скрипт диагностики шрифтов Tkinter.
Показывает все доступные шрифты и проверяет поддержку кириллицы.
"""

import tkinter as tk
import tkinter.font as tkfont  # Явный импорт модуля font
import subprocess
import os
import sys


def main():
    print("=" * 60)
    print("  ДИАГНОСТИКА ШРИФТОВ TKINTER")
    print("=" * 60)
    print(f"  Версия Python: {sys.version}")
    print(f"  Версия Tkinter: {tk.TkVersion}")
    print("=" * 60)
    print()

    # 1. Системные шрифты через fc-list
    print("1. Системные шрифты с кириллицей (fc-list):")
    print("-" * 40)
    try:
        result = subprocess.run(
            ['fc-list', ':lang=ru', 'family'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            fonts = list(set(result.stdout.strip().split('\n')))
            fonts = [f.split(',')[0].strip() for f in fonts if f.strip()]
            for font in sorted(fonts)[:15]:
                print(f"   • {font}")
            if len(fonts) > 15:
                print(f"   ... и ещё {len(fonts) - 15}")
        else:
            print("   ❌ Не удалось получить список шрифтов через fc-list")
    except FileNotFoundError:
        print("   ⚠ fc-list не найден (установите fontconfig)")
    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

    print()

    # 2. Директории со шрифтами
    print("2. Директории со шрифтами:")
    print("-" * 40)
    font_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
    ]

    total_fonts = 0
    for d in font_dirs:
        if os.path.exists(d):
            ttf_files = []
            for root, dirs, files in os.walk(d):
                for f in files:
                    if f.endswith(('.ttf', '.otf', '.ttc')):
                        ttf_files.append(os.path.join(root, f))

            if ttf_files:
                print(f"   ✅ {d} ({len(ttf_files)} файлов шрифтов)")
                total_fonts += len(ttf_files)
                # Показываем примеры
                for f in ttf_files[:3]:
                    print(f"      - {os.path.basename(f)}")
                if len(ttf_files) > 3:
                    print(f"      ... и ещё {len(ttf_files) - 3}")
            else:
                print(f"   📁 {d} (пусто)")
        else:
            print(f"   ❌ {d} (не существует)")

    print(f"   Всего найдено файлов шрифтов: {total_fonts}")
    print()

    # 3. Шрифты, доступные в Tkinter
    print("3. Шрифты, доступные в Tkinter:")
    print("-" * 40)

    root = tk.Tk()
    root.withdraw()

    try:
        # Используем правильный импорт tkinter.font
        available_fonts = sorted(tkfont.families())
        print(f"   Всего шрифтов в Tkinter: {len(available_fonts)}")
        print()

        # Показываем первые 20 шрифтов для примера
        print("   Примеры доступных шрифтов:")
        for font in available_fonts[:20]:
            print(f"   • {font}")
        if len(available_fonts) > 20:
            print(f"   ... и ещё {len(available_fonts) - 20}")

        print()

        # Ищем шрифты с поддержкой кириллицы
        cyrillic_patterns = [
            'DejaVu', 'Liberation', 'Ubuntu', 'Noto',
            'FreeSans', 'FreeSerif', 'Arial', 'Helvetica',
            'Sans', 'Serif', 'Mono'
        ]

        print("   Поиск шрифтов с потенциальной поддержкой кириллицы:")
        found_any = False
        for pattern in cyrillic_patterns:
            found = [f for f in available_fonts if pattern.lower() in f.lower()]
            if found:
                found_any = True
                print(f"   ✅ Содержащие '{pattern}': {', '.join(found[:5])}")
                if len(found) > 5:
                    print(f"      ... и ещё {len(found) - 5}")

        if not found_any:
            print("   ❌ Не найдено ни одного известного шрифта!")

        print()

        # 4. Тест отображения кириллицы
        print("4. Тест отображения кириллицы:")
        print("-" * 40)

        test_text = "Привет мир! Русский текст 12345"

        test_fonts = []
        for pattern in ['DejaVu Sans', 'Liberation Sans', 'Ubuntu', 'Noto Sans', 'Arial']:
            for font in available_fonts:
                if pattern.lower() in font.lower():
                    test_fonts.append(font)
                    break

        if not test_fonts:
            # Берём первые 3 доступных шрифта
            test_fonts = available_fonts[:3]

        test_fonts.append('TkDefaultFont')

        for font_name in test_fonts:
            if font_name in available_fonts or font_name == 'TkDefaultFont':
                try:
                    test_font = tkfont.Font(family=font_name, size=12)
                    label = tk.Label(root, text=test_text, font=test_font)
                    # Проверяем, что шрифт создался
                    actual_family = test_font.actual('family')
                    print(f"   ✅ {font_name} -> реальный шрифт: {actual_family}")
                    label.destroy()
                except Exception as e:
                    print(f"   ⚠ {font_name}: ошибка создания - {e}")
            else:
                print(f"   ❌ {font_name}: недоступен в Tkinter")

        print()

        # 5. Переменные окружения, влияющие на шрифты
        print("5. Переменные окружения:")
        print("-" * 40)
        env_vars = ['XDG_DATA_DIRS', 'FONTCONFIG_PATH', 'FONTCONFIG_FILE']
        for var in env_vars:
            value = os.environ.get(var, 'не установлена')
            print(f"   {var}={value}")

    finally:
        root.destroy()

    print()
    print("=" * 60)
    print("  ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 60)

    # Рекомендации
    print()
    print("Рекомендации:")
    print("-" * 40)

    if total_fonts == 0:
        print("❌ Шрифты не найдены в системе!")
        print("   Установите шрифты:")
        print("   sudo pacman -S ttf-dejavu ttf-liberation noto-fonts")
    elif len(available_fonts) < 10:
        print("⚠ Tkinter видит мало шрифтов.")
        print("   Возможные решения:")
        print("   1. Установите tk: sudo pacman -S tk")
        print("   2. Обновите кэш шрифтов: fc-cache -fv")
        print("   3. Перезапустите приложение")
    else:
        print("✅ Система шрифтов настроена корректно")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)