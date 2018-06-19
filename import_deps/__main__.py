import sys

from . import PyModule, ModuleSet


def main(module_path):
    module = PyModule(module_path)
    base_path = module.pkg_path().resolve()
    mset = ModuleSet(base_path.glob('**/*.py'))
    imports = mset.get_imports(module, return_fqn=True)
    print('\n'.join(sorted(imports)))
    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv[1])
