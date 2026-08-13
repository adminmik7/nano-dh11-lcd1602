#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Монитор загрузки ПК для Adapter
Отправляет данные о CPU и RAM через USB-порт.
Автоматически находит Adapter по VID/PID.
Поддерживает программный ресет (DTR/RTS) и восстановление при полном отключении.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
import time


def check_python_env():
    """Проверяет, что Python + pip доступны. Если нет — подсказывает решение."""
    errors = []

    # Проверяем python
    python_path = shutil.which("python") or shutil.which("python3")
    if not python_path:
        errors.append(
            "Python не найден в системе.\n"
            "  1. Скачайте Python с https://www.python.org/downloads/\n"
            "  2. При установке обязательно поставьте галку 'Add Python to PATH'\n"
            "  3. Перезапустите терминал после установки"
        )

    # Проверяем pip
    pip_path = shutil.which("pip") or shutil.which("pip3")
    if not pip_path:
        errors.append(
            "pip не найден в PATH.\n"
            "  Это может означать:\n"
            "    • Python установлен, но 'Add Python to PATH' не было отмечено\n"
            "    • pip не установлен (редко для Python 3.4+)\n"
            "\nРешение:\n"
            "  python -m ensurepip --upgrade\n"
            "  Или переустановить Python с галкой 'Add Python to PATH'"
        )

    if errors:
        print("=" * 60)
        print("  ПРЕДУПРЕЖДЕНИЕ: Среда Python не настроена")
        print("=" * 60)
        for err in errors:
            print(f"\n{err}")
        print("\n" + "=" * 60)
        return False
    return True


# --- Функция для безопасной проверки и установки зависимостей ---
def ensure_package_installed(package_name, import_name=None):
    if import_name is None:
        import_name = package_name

    if importlib.util.find_spec(import_name) is not None:
        return True

    print(f"[INFO] Библиотека '{package_name}' не найдена. Устанавливаю...")
    try:
        # sys.executable — это полный путь к текущему python.exe,
        # работает даже если 'python' не в PATH
        pip_cmd = [sys.executable, "-m", "pip", "install", package_name]

        # Если pip тоже найден через shutil.which — добавляем --quiet для чистоты
        result = subprocess.run(
            pip_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode == 0:
            print(f"[SUCCESS] Библиотека '{package_name}' успешно установлена.")
            return True
        else:
            # Показываем ошибку pip для отладки
            err_output = result.stderr.strip() if result.stderr else "неизвестная ошибка"
            print(f"[ERROR] Ошибка установки '{package_name}': {err_output}")
            return False
    except FileNotFoundError:
        print(f"[ERROR] pip не найден по пути: {sys.executable}")
        print("Убедитесь, что Python установлен с галкой 'Add Python to PATH'")
        return False
    except Exception as e:
        print(f"[ERROR] Неожиданная ошибка при установке '{package_name}': {e}")
        return False

required_packages = {"pyserial": "serial", "psutil": "psutil"}
for pkg_name, imp_name in required_packages.items():
    if not ensure_package_installed(pkg_name, imp_name):
        sys.exit("[FATAL] Критическая зависимость не установлена. Завершаю работу.")

import serial
import serial.tools.list_ports
import psutil

# --- Настройки ---
ADAPTER_VID_PID_LIST = [
    "2341:0043", "2341:0001", "1A86:7523", "0403:6001", "10C4:EA60"
]

BAUD_RATE = 9600
RECONNECT_DELAY = 3  # Секунд между попытками

# --- Функция поиска порта ---
def find_adapter_port(vid_pid_list):
    print("\n[SCAN] Поиск Adapter по VID:PID...")
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("[ERROR] Не найдено ни одного последовательного порта.")
        return None

    targets = []
    for vp in vid_pid_list:
        try:
            v, p = vp.split(":")
            targets.append((int(v, 16), int(p, 16)))
        except ValueError:
            continue

    for port in ports:
        if port.vid is not None and port.pid is not None:
            for v, p in targets:
                if port.vid == v and port.pid == p:
                    print(f"[SUCCESS] Adapter найден: {port.device}")
                    return port.device
        for target_str in vid_pid_list:
            if target_str.lower() in port.hwid.lower():
                print(f"[SUCCESS] Adapter найден: {port.device}")
                return port.device

    print("[ERROR] Adapter не найден среди известных VID:PID.")
    return None

# --- Статистика ---
def get_system_stats():
    return psutil.cpu_percent(interval=0.5), psutil.virtual_memory().percent

# --- Программный ресет (теперь устойчив к исчезновению порта) ---
def soft_reset_adapter(port, baud_rate=9600):
    try:
        with serial.Serial(port, baud_rate, timeout=0.5) as ser:
            ser.setDTR(False)
            ser.setRTS(False)
            time.sleep(0.15)
            ser.setDTR(True)
            ser.setRTS(True)
        print("[ℹ️] Отправлен сигнал ресета (DTR/RTS)")
        return True
    except FileNotFoundError:
        print("[⚠️] Порт исчез из системы. Пропуск DTR-ресета.")
        return False
    except serial.SerialException:
        print("[⚠️] Порт недоступен для ресета. Пропуск.")
        return False
    except Exception as e:
        print(f"[⚠️] Ошибка ресета: {e}")
        return False

# --- Основная функция ---
def main():
    # Проверяем среду Python + pip
    if not check_python_env():
        sys.exit("\nУстановите Python с поддержкой pip и запустите скрипт заново.")

    print("🖥️  Мониторинг запущен. Для выхода нажмите Ctrl+C.\n")
    
    while True:
        port = find_adapter_port(ADAPTER_VID_PID_LIST)
        if port is None:
            print(f"[WAIT] Adapter не найден. Повтор через {RECONNECT_DELAY} сек...")
            time.sleep(RECONNECT_DELAY)
            continue

        ser = None
        try:
            ser = serial.Serial(port, BAUD_RATE, timeout=1)
            print(f"\n✅ Подключено к {port} ({BAUD_RATE} бод)")
            print("Отправка данных...\n")
            time.sleep(2)

            while True:
                cpu_val, ram_val = get_system_stats()
                data_str = f"CPU:{int(cpu_val)};RAM:{int(ram_val)}\n"
                ser.write(data_str.encode('utf-8'))
                print(f"📤 Sent: {data_str.strip()}")
                time.sleep(1)

        except (serial.SerialException, OSError) as e:
            print(f"\n⚠️  Соединение потеряно: {e}")
            
            # Безопасно закрываем дескриптор, если он ещё "жив"
            if ser is not None:
                try: ser.close()
                except Exception: pass

            # Пробуем ресет только если порт ещё виден системе
            print("[ℹ️] Проверка доступности порта...")
            ports = [p.device for p in serial.tools.list_ports.comports()]
            if port in ports:
                print("[ℹ️] Порт в системе. Попытка DTR-ресета...")
                soft_reset_adapter(port, BAUD_RATE)
                time.sleep(2)
            else:
                print("[ℹ️] Порт исчез. Ожидание повторного подключения ОС...")

            print("[WAIT] Переподключение...")
        except KeyboardInterrupt:
            print("\n🛑 Программа остановлена.")
            break
        except Exception as e:
            print(f"\n❌ Непредвиденная ошибка: {e}")
            break
        finally:
            if ser is not None:
                try: ser.close()
                except Exception: pass
            time.sleep(RECONNECT_DELAY)

if __name__ == "__main__":
    main()