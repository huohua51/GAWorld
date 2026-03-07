import importlib.util
import sys

_REAL_PATH = '/opt/homebrew/Caskroom/miniconda/base/lib/python3.12/site-packages/typing_extensions.py'
_spec = importlib.util.spec_from_file_location('_real_typing_extensions', _REAL_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f'Cannot load real typing_extensions from {_REAL_PATH}')
_real = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_real)

for _name in dir(_real):
    if not _name.startswith('__') or _name in {'__all__', '__doc__', '__file__', '__name__', '__package__'}:
        globals()[_name] = getattr(_real, _name)

if 'Sentinel' not in globals():
    class Sentinel:
        def __init__(self, name: str, repr: str | None = None):
            self._name = name
            self._repr = repr if repr is not None else name

        def __repr__(self):
            return self._repr

        def __reduce__(self):
            return (Sentinel, (self._name, self._repr))

    globals()['Sentinel'] = Sentinel
    if '__all__' in globals() and isinstance(__all__, list) and 'Sentinel' not in __all__:
        __all__.append('Sentinel')
