import argparse
import sys

from . import __version__, PyModule, ModuleSet


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(prog='import_deps')
    parser.add_argument('module_path', metavar='PATH/TO/FILE.py',
                        help='Python file to analyze')
    parser.add_argument('--version', action='version',
                        version='.'.join(str(i) for i in __version__))
    config = parser.parse_args(argv[1:])

    module = PyModule(config.module_path)
    base_path = module.pkg_path().resolve()
    mset = ModuleSet(base_path.glob('**/*.py'))
    imports = mset.get_imports(module, return_fqn=True)
    print('\n'.join(sorted(imports)))
    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv)
