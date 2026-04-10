import importlib.util
import sys
import os
import json
from pathlib import Path

class PluginManager:
    
    def __init__(self, plugins_dir="plugins"):
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(exist_ok=True)
        # Словник завантажених плагінів: {"назва": модуль}
        self.loaded: dict = {}
    
    def load(self, name: str):
        """Завантажити або перезавантажити плагін по імені."""
        path = self.plugins_dir / f"{name}.py"
        if not path.exists():
            return False, f"Файл {name}.py не знайдено"
        
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        self.loaded[name] = module
        return True, module
    
    def run(self, name: str, jarvis):
        """Запустити плагін."""
        if name not in self.loaded:
            ok, result = self.load(name)
            if not ok:
                return False, result
        
        try:
            self.loaded[name].run(jarvis)
            return True, "OK"
        except Exception as e:
            return False, str(e)
    
    def list_plugins(self) -> list:
        """Список всіх доступних плагінів."""
        return [f.stem for f in self.plugins_dir.glob("*.py")]