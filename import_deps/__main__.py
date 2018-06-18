import sys
import pathlib

from . import PyModule, ModuleSet


def main(base_path, module_path):
    mset = ModuleSet(pathlib.Path(base_path).glob('**/*.py'))
    imports = mset.get_imports(PyModule(module_path), return_path=False)
    print(imports)
    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
