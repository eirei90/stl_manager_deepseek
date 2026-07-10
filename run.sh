#!/bin/bash
# run.sh - запуск STL Manager с правильными настройками

# Отключаем OpenGL ошибки
export MESA_GL_VERSION_OVERRIDE=3.3
export EGL_PLATFORM=surfaceless
export PYVISTA_OFF_SCREEN=true
export VTK_OPENGL_HAS_EGL=1
export DISPLAY=:0

# Запускаем приложение
cd /home/eirei/PycharmProjects/stl_manager
python3 app.py 2>/dev/null