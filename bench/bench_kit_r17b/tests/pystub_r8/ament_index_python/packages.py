# pystub_r8/ament_index_python/packages.py - ТОЛЬКО ДЛЯ ТЕСТОВ: папка share пакета берётся из BB_R8_SHARE (нет переменной - пакет не найден)
import os


class PackageNotFoundError(KeyError):
    pass


def get_package_share_directory(name):
    d = os.environ.get('BB_R8_SHARE', '')
    if not d:
        raise PackageNotFoundError(name)
    return os.path.join(d, name)
