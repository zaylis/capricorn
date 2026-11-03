import os
import shutil
import datetime
import glob
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_config():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except:
        return {}

def make_backup():
    cfg = get_config()
    
    # Берем путь из настроек, если нет — дефолтный
    backup_path = cfg.get("backup_dir", r"G:\Capri_Backups")
    max_backups = int(cfg.get("backup_max_count", 30))
    
    target_dir = backup_path
    if not os.path.exists(target_dir):
        print(f"Флешка/папка не найдена: {target_dir}. Делаю бэкап в локальную папку.")
        target_dir = os.path.join(BASE_DIR, "backups", "usb_backups")
        os.makedirs(target_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = os.path.join(target_dir, f"capricorn_backup_{timestamp}")
    
    print("Создаю бэкап...")
    
    # Исключаем тяжелые папки, чтобы бэкап не весил гигабайты
    def ignore_patterns(path, names):
        return [n for n in names if n in ('.git', '__pycache__', 'models', 'bundled', 'backups')]

    try:
        shutil.make_archive(archive_name, 'zip', BASE_DIR, ignore=ignore_patterns)
        print(f"Бэкап создан: {archive_name}.zip")
    except Exception as e:
        print(f"Ошибка создания бэкапа: {e}")
        return

    # Удаляем старые бэкапы (FIFO)
    backups = sorted(glob.glob(os.path.join(target_dir, "capricorn_backup_*.zip")))
    if len(backups) > max_backups:
        for old_backup in backups[:-max_backups]:
            try:
                os.remove(old_backup)
                print(f"Удален старый бэкап: {os.path.basename(old_backup)}")
            except Exception as e:
                print(f"Не удалось удалить {old_backup}: {e}")

if __name__ == "__main__":
    make_backup()