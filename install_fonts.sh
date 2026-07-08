#!/bin/bash
# Установка шрифтов с поддержкой кириллицы для Linux
# Поддерживает: Arch Linux, Debian/Ubuntu, Fedora/RHEL, openSUSE

set -e  # Выход при ошибке

echo "========================================"
echo "  Установка шрифтов с кириллицей"
echo "========================================"
echo ""

# Определение пакетного менеджера
detect_package_manager() {
    if command -v pacman &> /dev/null; then
        echo "arch"
    elif command -v apt-get &> /dev/null; then
        echo "debian"
    elif command -v dnf &> /dev/null; then
        echo "fedora"
    elif command -v zypper &> /dev/null; then
        echo "suse"
    else
        echo "unknown"
    fi
}

PKG_MANAGER=$(detect_package_manager)
echo "Определён пакетный менеджер: $PKG_MANAGER"
echo ""

case $PKG_MANAGER in
    arch)
        echo ">>> Установка шрифтов для Arch Linux..."
        echo ""
        
        # Основные шрифты с кириллицей
        FONTS=(
            "ttf-dejavu"           # DejaVu Sans/Serif/Mono
            "ttf-liberation"       # Liberation Sans/Serif/Mono
            "ttf-droid"            # Droid Sans/Serif/Mono
            "ttf-ubuntu-font-family" # Ubuntu Font Family
            "noto-fonts"           # Google Noto (полная поддержка Unicode)
            "noto-fonts-cjk"       # Китайские, японские, корейские
            "noto-fonts-emoji"     # Эмодзи
            "ttf-hack"             # Моноширинный для кода
        )
        
        # Обновление репозиториев
        echo "Обновление списка пакетов..."
        sudo pacman -Sy --noconfirm
        
        # Установка шрифтов
        echo "Установка шрифтов..."
        for font in "${FONTS[@]}"; do
            echo "  - Установка $font..."
            sudo pacman -S --noconfirm --needed "$font" 2>/dev/null || echo "    (пропущен - возможно уже установлен)"
        done
        
        # Обновление кэша шрифтов
        echo ""
        echo "Обновление кэша шрифтов..."
        fc-cache -fv
        ;;
        
    debian)
        echo ">>> Установка шрифтов для Debian/Ubuntu..."
        echo ""
        
        sudo apt-get update
        sudo apt-get install -y \
            fonts-dejavu-core \
            fonts-dejavu-extra \
            fonts-liberation \
            fonts-liberation2 \
            fonts-droid-fallback \
            fonts-ubuntu \
            fonts-noto \
            fonts-noto-cjk \
            fonts-noto-color-emoji \
            fonts-hack-ttf
        
        fc-cache -fv
        ;;
        
    fedora)
        echo ">>> Установка шрифтов для Fedora/RHEL..."
        echo ""
        
        sudo dnf install -y \
            dejavu-sans-fonts \
            dejavu-serif-fonts \
            dejavu-sans-mono-fonts \
            liberation-fonts \
            liberation-mono-fonts \
            liberation-sans-fonts \
            liberation-serif-fonts \
            google-droid-sans-fonts \
            google-noto-sans-fonts \
            google-noto-serif-fonts \
            google-noto-mono-fonts \
            google-noto-emoji-fonts \
            ubuntu-family-fonts \
            hack-fonts
        
        fc-cache -fv
        ;;
        
    suse)
        echo ">>> Установка шрифтов для openSUSE..."
        echo ""
        
        sudo zypper refresh
        sudo zypper install -y \
            dejavu-fonts \
            liberation-fonts \
            google-droid-fonts \
            noto-sans-fonts \
            noto-serif-fonts \
            noto-mono-fonts \
            noto-emoji-fonts \
            ubuntu-fonts \
            hack-fonts
        
        fc-cache -fv
        ;;
        
    *)
        echo "❌ Не удалось определить пакетный менеджер."
        echo ""
        echo "Пожалуйста, установите следующие шрифты вручную:"
        echo "  - DejaVu Sans/Serif/Mono"
        echo "  - Liberation Sans/Serif/Mono"
        echo "  - Noto Sans/Serif"
        echo ""
        echo "Для установки вручную (примеры):"
        echo "  Arch:      sudo pacman -S ttf-dejavu ttf-liberation noto-fonts"
        echo "  Debian:    sudo apt install fonts-dejavu fonts-liberation fonts-noto"
        echo "  Fedora:    sudo dnf install dejavu-sans-fonts liberation-fonts google-noto-sans-fonts"
        echo ""
        exit 1
        ;;
esac

echo ""
echo "========================================"
echo "  Установка завершена!"
echo "========================================"
echo ""
echo "Установленные шрифты:"

# Показываем установленные шрифты с кириллицей
echo ""
echo "DejaVu Sans:"
fc-list | grep -i "dejavu sans" | grep -v "Mono\|Serif" | head -3

echo ""
echo "Liberation Sans:"
fc-list | grep -i "liberation sans" | grep -v "Mono\|Serif" | head -3

echo ""
echo "Noto Sans:"
fc-list | grep -i "noto sans" | grep -v "Mono\|Serif\|CJK" | head -3

echo ""
echo "Проверка поддержки кириллицы в DejaVu Sans..."
# Создаём тестовую строку с кириллицей
python3 -c "
import sys
try:
    from tkinter import Tk, Label, font
    root = Tk()
    root.withdraw()
    
    # Проверяем доступность шрифта
    available = [f for f in font.families() if 'DejaVu' in f]
    if available:
        print(f'✅ Доступны шрифты: {available[:3]}')
    else:
        print('⚠ DejaVu не найден в Tkinter, но может быть доступен в системе')
    
    root.destroy()
except Exception as e:
    print(f'⚠ Не удалось проверить через Tkinter: {e}')
    print('  (это нормально, если python-tk ещё не установлен)')
" 2>/dev/null || echo "  (Tkinter не установлен - установите: sudo pacman -S tk)"

echo ""
echo "Для перезагрузки системы введите: reboot"
echo "Или просто перезапустите приложение STL Manager."
echo ""