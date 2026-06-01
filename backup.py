"""
💾 BACKUP.PY - Скрипт для создания и восстановления бэкапов
Используйте: python backup.py
"""

import os
import shutil
import sqlite3
import json
from datetime import datetime
from pathlib import Path

# Параметры
DB_FILE = 'game_data.db'
BACKUP_DIR = 'backups'
BACKUP_PREFIX = 'backup_'

def ensure_backup_dir():
    """Создает папку для бэкапов если её нет"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        print(f"✅ Создана папка {BACKUP_DIR}")

def create_backup():
    """Создает бэкап базы данных"""
    
    if not os.path.exists(DB_FILE):
        print(f"❌ Файл {DB_FILE} не найден!")
        return False
    
    ensure_backup_dir()
    
    # Генерируем имя файла с временем
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"{BACKUP_PREFIX}{timestamp}.db")
    
    try:
        # Копируем базу данных
        shutil.copy2(DB_FILE, backup_file)
        
        # Получаем информацию о бэкапе
        file_size = os.path.getsize(backup_file)
        file_size_mb = file_size / (1024 * 1024)
        
        print(f"✅ Бэкап создан успешно!")
        print(f"📁 Файл: {backup_file}")
        print(f"📊 Размер: {file_size_mb:.2f} MB")
        print(f"⏰ Время: {timestamp}")
        
        # Создаем info файл
        info_file = f"{backup_file}.info"
        with open(info_file, 'w', encoding='utf-8') as f:
            f.write(f"Backup: {timestamp}\n")
            f.write(f"Original: {DB_FILE}\n")
            f.write(f"Size: {file_size} bytes\n")
            f.write(f"Created: {datetime.now().isoformat()}\n")
        
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при создании бэкапа: {e}")
        return False

def list_backups():
    """Выводит список всех бэкапов"""
    
    ensure_backup_dir()
    
    backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')])
    
    if not backups:
        print("❌ Бэкапов не найдено!")
        return
    
    print("\n📋 Доступные бэкапы:\n")
    
    for i, backup in enumerate(backups, 1):
        backup_path = os.path.join(BACKUP_DIR, backup)
        file_size = os.path.getsize(backup_path) / (1024 * 1024)
        creation_time = datetime.fromtimestamp(os.path.getctime(backup_path))
        
        print(f"{i}. {backup}")
        print(f"   📊 Размер: {file_size:.2f} MB")
        print(f"   ⏰ Создан: {creation_time.strftime('%d.%m.%Y %H:%M:%S')}")
        print()

def restore_backup(backup_name=None):
    """Восстанавливает данные из бэкапа"""
    
    ensure_backup_dir()
    
    # Если бэкап не указан, выбираем последний
    if not backup_name:
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')])
        
        if not backups:
            print("❌ Бэкапов не найдено!")
            return False
        
        backup_name = backups[-1]
    
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_path):
        print(f"❌ Бэкап {backup_name} не найден!")
        return False
    
    # Проверяем целостность базы данных
    try:
        conn = sqlite3.connect(backup_path)
        conn.execute('SELECT 1')
        conn.close()
    except Exception as e:
        print(f"❌ Бэкап повреждена: {e}")
        return False
    
    # Создаем резервную копию текущей БД
    if os.path.exists(DB_FILE):
        broken_backup = os.path.join(BACKUP_DIR, f"broken_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        shutil.copy2(DB_FILE, broken_backup)
        print(f"📁 Текущая БД сохранена как: {broken_backup}")
    
    # Восстанавливаем БД
    try:
        shutil.copy2(backup_path, DB_FILE)
        
        # Получаем информацию
        file_size = os.path.getsize(DB_FILE) / (1024 * 1024)
        
        print(f"✅ Восстановление успешно!")
        print(f"📁 Восстановлено из: {backup_name}")
        print(f"📊 Размер: {file_size:.2f} MB")
        
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при восстановлении: {e}")
        return False

def export_data():
    """Экспортирует данные в JSON для безопасности"""
    
    if not os.path.exists(DB_FILE):
        print(f"❌ Файл {DB_FILE} не найден!")
        return False
    
    try:
        ensure_backup_dir()
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        data = {}
        
        # Экспортируем все таблицы
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT * FROM {table_name}")
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            
            data[table_name] = {
                'columns': columns,
                'rows': rows
            }
        
        conn.close()
        
        # Сохраняем в JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = os.path.join(BACKUP_DIR, f"export_{timestamp}.json")
        
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        file_size = os.path.getsize(export_file) / 1024
        
        print(f"✅ Экспорт успешен!")
        print(f"📁 Файл: {export_file}")
        print(f"📊 Размер: {file_size:.2f} KB")
        
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при экспорте: {e}")
        return False

def delete_backup(backup_name):
    """Удаляет бэкап"""
    
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    if not os.path.exists(backup_path):
        print(f"❌ Бэкап {backup_name} не найден!")
        return False
    
    try:
        os.remove(backup_path)
        
        # Удаляем info файл если существует
        info_file = f"{backup_path}.info"
        if os.path.exists(info_file):
            os.remove(info_file)
        
        print(f"✅ Бэкап {backup_name} удален")
        return True
    
    except Exception as e:
        print(f"❌ Ошибка при удалении: {e}")
        return False

def auto_backup():
    """Создает автоматический бэкап"""
    ensure_backup_dir()
    
    # Удаляем старые бэкапы (старше 30 дней)
    backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.db')]
    
    for backup in backups:
        backup_path = os.path.join(BACKUP_DIR, backup)
        creation_time = datetime.fromtimestamp(os.path.getctime(backup_path))
        age_days = (datetime.now() - creation_time).days
        
        if age_days > 30:
            try:
                os.remove(backup_path)
                print(f"🗑️ Удален старый бэкап: {backup}")
            except:
                pass
    
    # Создаем новый бэкап
    return create_backup()

def show_menu():
    """Выводит меню"""
    
    print("\n" + "="*50)
    print("💾 BACKUP MANAGER - Управление бэкапами")
    print("="*50)
    print("\n1️⃣  Создать бэкап")
    print("2️⃣  Список бэкапов")
    print("3️⃣  Восстановить последний бэкап")
    print("4️⃣  Экспортировать данные в JSON")
    print("5️⃣  Удалить бэкап")
    print("0️⃣  Выход")
    print("\n" + "="*50)

def main():
    """Главное меню"""
    
    while True:
        show_menu()
        choice = input("\nВыберите действие (0-5): ").strip()
        
        if choice == '1':
            print()
            create_backup()
        
        elif choice == '2':
            print()
            list_backups()
        
        elif choice == '3':
            print()
            confirm = input("Вы уверены? Это перепишет текущую БД (y/n): ").strip().lower()
            if confirm == 'y':
                restore_backup()
        
        elif choice == '4':
            print()
            export_data()
        
        elif choice == '5':
            print()
            list_backups()
            backup_name = input("\nВведите имя бэкапа для удаления: ").strip()
            if backup_name:
                confirm = input(f"Удалить {backup_name}? (y/n): ").strip().lower()
                if confirm == 'y':
                    delete_backup(backup_name)
        
        elif choice == '0':
            print("\n👋 До свидания!")
            break
        
        else:
            print("\n❌ Неверный выбор!")
        
        input("\nНажмите Enter для продолжения...")

if __name__ == "__main__":
    main()
