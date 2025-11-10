import argparse
import json
import pathlib
import sys

from . import __version__, PyModule, ModuleSet


def format_dot(results):
    """Format results as DOT graph for graphviz"""
    lines = ['digraph imports {']
    for result in results:
        module = result['module']
        for imp in result['imports']:
            lines.append(f'    "{module}" -> "{imp}";')
    lines.append('}')
    return '\n'.join(lines)


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(prog='import_deps')
    parser.add_argument('path', metavar='PATH',
                        help='Python file or package directory to analyze')
    parser.add_argument('--json', action='store_true',
                        help='Output results in JSON format')
    parser.add_argument('--dot', action='store_true',
                        help='Output results in DOT format for graphviz')
    parser.add_argument('--version', action='version',
                        version='.'.join(str(i) for i in __version__))
    config = parser.parse_args(argv[1:])

    if config.json and config.dot:
        print("Error: --json and --dot are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    path = pathlib.Path(config.path)

    # Collect data
    if path.is_file():
        # Single file analysis
        module = PyModule(config.path)
        base_path = module.pkg_path().resolve()
        mset = ModuleSet(base_path.glob('**/*.py'))
        imports = mset.get_imports(module, return_fqn=True)

        results = [{
            'module': '.'.join(module.fqn),
            'imports': sorted(imports)
        }]

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

    else:
        print(f"Error: {config.path} is not a valid file or directory", file=sys.stderr)
        sys.exit(1)

    # Output results
    if config.json:
        print(json.dumps(results, indent=2))
    elif config.dot:
        print(format_dot(results))
    else:
        # Text format
        if len(results) == 1:
            # Single file - just list imports
            print('\n'.join(results[0]['imports']))
        else:
            # Multiple modules - show module names with imports
            for result in results:
                print(f"{result['module']}:")
                for imp in result['imports']:
                    print(f"  {imp}")

    sys.exit(0)

if __name__ == '__main__':
    main(sys.argv)
