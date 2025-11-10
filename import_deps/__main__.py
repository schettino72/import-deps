import argparse
import json
import pathlib
import sys

from . import __version__, PyModule, ModuleSet


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(prog='import_deps')
    parser.add_argument('path', metavar='PATH',
                        help='Python file or package directory to analyze')
    parser.add_argument('--json', action='store_true',
                        help='Output results in JSON format')
    parser.add_argument('--version', action='version',
                        version='.'.join(str(i) for i in __version__))
    config = parser.parse_args(argv[1:])

    path = pathlib.Path(config.path)

    # Determine if path is a file or directory
    if path.is_file():
        # Single file analysis
        module = PyModule(config.path)
        base_path = module.pkg_path().resolve()
        mset = ModuleSet(base_path.glob('**/*.py'))
        imports = mset.get_imports(module, return_fqn=True)

        if config.json:
            result = [{
                'module': '.'.join(module.fqn),
                'imports': sorted(imports)
            }]
            print(json.dumps(result, indent=2))
        else:
            print('\n'.join(sorted(imports)))

    elif path.is_dir():
        # Package analysis
        base_path = path.resolve()
        py_files = list(base_path.glob('**/*.py'))
        mset = ModuleSet(py_files)

        results = []
        for mod_name in sorted(mset.by_name.keys()):
            mod = mset.by_name[mod_name]
            imports = mset.get_imports(mod, return_fqn=True)
            results.append({
                'module': mod_name,
                'imports': sorted(imports)
            })

        if config.json:
            print(json.dumps(results, indent=2))
        else:
            for result in results:
                print(f"{result['module']}:")
                for imp in result['imports']:
                    print(f"  {imp}")

    else:
        print(f"Error: {config.path} is not a valid file or directory", file=sys.stderr)
        sys.exit(1)

    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv)
