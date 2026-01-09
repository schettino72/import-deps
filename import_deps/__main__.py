"""Command-line interface for import_deps."""

import argparse
import json
import pathlib
import sys

from . import __version__, PyModule, ModuleSet
from .core import ast_defined_names, ast_inner_imports
from .graph import ModuleResult, get_all_imports, detect_cycles, topological_sort


def detect_reimports(mset):
    """Detect re-imports: importing a name from a module that re-exports it.

    A re-import is when module C does `from B import foo`, but `foo` is not
    defined in B - it was imported into B from A. The import should come
    from A directly.

    __init__.py files are whitelisted as they commonly re-export for cleaner APIs.

    :param mset: ModuleSet
    :return: list of dicts with keys: module, name, imported_from, original_source
    """
    # Build symbol tables for each module
    # symbol_table[mod_fqn] = {name: 'defined' | ('imported', source_fqn)}
    symbol_table = {}

    for mod_fqn, mod in mset.by_name.items():
        defined = ast_defined_names(mod.path)
        imports = mset.get_imports_detailed(mod)

        symbols = {}
        for name in defined:
            symbols[name] = 'defined'
        for name, source_fqn in imports:
            if name not in symbols:  # defined takes precedence
                symbols[name] = ('imported', source_fqn)

        symbol_table[mod_fqn] = symbols

    # Find original source for a name (trace through re-exports)
    def find_original(name, source_fqn, visited=None):
        if visited is None:
            visited = set()
        if source_fqn in visited:
            return source_fqn  # Cycle, just return current
        visited.add(source_fqn)

        if source_fqn not in symbol_table:
            return source_fqn  # External module

        entry = symbol_table[source_fqn].get(name)
        if entry == 'defined':
            return source_fqn
        elif entry and entry[0] == 'imported':
            return find_original(name, entry[1], visited)
        else:
            return source_fqn  # Name not found, assume defined

    # Check each module for re-imports
    violations = []
    for mod_fqn, mod in mset.by_name.items():
        imports = mset.get_imports_detailed(mod)

        for name, source_fqn in imports:
            # Skip if importing from __init__.py (whitelisted)
            if source_fqn.endswith('.__init__'):
                continue

            if source_fqn not in symbol_table:
                continue  # External module

            entry = symbol_table[source_fqn].get(name)
            if entry and entry != 'defined' and entry[0] == 'imported':
                # This is a re-import
                original = find_original(name, entry[1])
                # Clean up __init__ suffix for display
                display_original = original
                if display_original.endswith('.__init__'):
                    display_original = display_original[:-9]
                violations.append({
                    'module': mod_fqn,
                    'name': name,
                    'imported_from': source_fqn,
                    'original_source': display_original
                })

    return violations


def format_dot(results: list[ModuleResult], highlight_cycles: bool = True) -> str:
    """Format results as DOT graph for graphviz."""
    lines = ['digraph imports {']
    lines.append('    rankdir=LR;')
    lines.append('    node [shape=box, style="rounded,filled", fillcolor=lightblue, fontname="Arial"];')
    lines.append('    edge [fontname="Arial"];')

    # Detect cycles
    cycle_edges = detect_cycles(results) if highlight_cycles else set()

    # Group modules by package
    packages = {}
    all_modules = set()

    for result in results:
        module = result['module']
        all_modules.add(module)
        # Extract package hierarchy
        parts = module.split('.')
        if len(parts) > 1:
            # Get package path (everything except last part)
            pkg = '.'.join(parts[:-1])
            if pkg not in packages:
                packages[pkg] = []
            packages[pkg].append(module)

    # Create subgraphs for packages
    def create_subgraph(pkg_name, modules, indent=1):
        ind = '    ' * indent
        lines.append(f'{ind}subgraph cluster_{pkg_name.replace(".", "_")} {{')
        lines.append(f'{ind}    label = "{pkg_name}";')
        lines.append(f'{ind}    style = "rounded,dashed";')
        lines.append(f'{ind}    color = gray40;')
        lines.append(f'{ind}    fontsize = 11;')
        lines.append(f'{ind}    fontcolor = gray20;')
        lines.append(f'{ind}    penwidth = 1.5;')

        # Find direct children of this package
        for mod in sorted(modules):
            if mod.rsplit('.', 1)[0] == pkg_name:
                lines.append(f'{ind}    "{mod}";')

        # Find sub-packages
        sub_pkgs = {}
        for other_pkg, other_modules in packages.items():
            if other_pkg.startswith(pkg_name + '.') and other_pkg.count('.') == pkg_name.count('.') + 1:
                sub_pkgs[other_pkg] = other_modules

        for sub_pkg in sorted(sub_pkgs.keys()):
            create_subgraph(sub_pkg, sub_pkgs[sub_pkg], indent + 1)

        lines.append(f'{ind}}}')

    # Create top-level packages
    top_level_pkgs = set()
    for pkg in packages:
        top = pkg.split('.')[0]
        top_level_pkgs.add(top)

    for top_pkg in sorted(top_level_pkgs):
        pkg_modules = [m for pkg, modules in packages.items()
                       if pkg.startswith(top_pkg)
                       for m in modules]
        if pkg_modules:
            create_subgraph(top_pkg, pkg_modules)

    # Add edges with cycle detection
    lines.append('')
    for result in results:
        module = result['module']

        for imp in result['imports']:
            # Check if this edge is part of a cycle
            if (module, imp) in cycle_edges:
                lines.append(f'    "{module}" -> "{imp}" [color=red, penwidth=2.0];')
            else:
                lines.append(f'    "{module}" -> "{imp}";')

    lines.append('}')
    return '\n'.join(lines)


def main(argv=sys.argv):
    parser = argparse.ArgumentParser(prog='import_deps')
    parser.add_argument('path', metavar='PATH', nargs='+',
                        help='Python file(s) or package directory(s) to analyze')
    parser.add_argument('--json', action='store_true',
                        help='Output results in JSON format')
    parser.add_argument('--dot', action='store_true',
                        help='Output results in DOT format for graphviz')
    parser.add_argument('--check', nargs='?', const='all', metavar='TYPE',
                        choices=['all', 'circular', 'reimports', 'inner'],
                        help='Run checks: all (default), circular, reimports, or inner. '
                             'Use --check=all before PATH, or --check after PATH')
    parser.add_argument('--sort', action='store_true',
                        help='Output modules in topological sort order (dependencies first)')
    parser.add_argument('--all-imports', action='store_true',
                        help='Include transitive imports in JSON output (requires --json)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Show additional details (e.g., level/depth with --sort)')
    parser.add_argument('--version', action='version',
                        version='.'.join(str(i) for i in __version__))
    config = parser.parse_args(argv[1:])

    # Check for mutually exclusive flags
    output_flags = sum([config.json, config.dot, config.sort])
    if output_flags > 1:
        print("Error: --json, --dot, and --sort are mutually exclusive", file=sys.stderr)
        sys.exit(1)

    # --all-imports requires --json
    if config.all_imports and not config.json:
        print("Error: --all-imports requires --json", file=sys.stderr)
        sys.exit(1)

    # Collect all .py files from provided paths
    # requested_files: files to analyze (output results for)
    # py_files: all files for ModuleSet (includes package context for import resolution)
    py_files = []
    requested_files = set()
    for p in config.path:
        path = pathlib.Path(p)
        if path.is_file():
            # For files, include entire package to detect intra-package imports
            requested_files.add(path.resolve())
            module = PyModule(path)
            pkg_path = module.pkg_path().resolve()
            py_files.extend(pkg_path.glob('**/*.py'))
        elif path.is_dir():
            dir_files = list(path.glob('**/*.py'))
            py_files.extend(dir_files)
            requested_files.update(f.resolve() for f in dir_files)
        else:
            print(f"Error: {p} is not a valid file or directory", file=sys.stderr)
            sys.exit(1)

    mset = ModuleSet(py_files)

    results = []
    for mod_name in sorted(mset.by_name.keys()):
        mod = mset.by_name[mod_name]
        if mod.path.resolve() not in requested_files:
            continue
        imports = mset.get_imports(mod, return_fqn=True)
        results.append({
            'module': mod_name,
            'filepath': str(mod.path),
            'imports': sorted(imports)
        })

    # Add transitive imports if requested
    if config.all_imports:
        all_imports_map = get_all_imports(results)
        for result in results:
            result['all_imports'] = sorted(all_imports_map.get(result['module'], set()))

    # Run checks
    if config.check:
        check_type = config.check
        has_errors = False

        # Check circular dependencies
        if check_type in ('all', 'circular'):
            cycle_edges = detect_cycles(results)
            if cycle_edges:
                has_errors = True
                print("Circular dependencies detected:", file=sys.stderr)
                cycles_by_module = {}
                for src, dst in cycle_edges:
                    if src not in cycles_by_module:
                        cycles_by_module[src] = []
                    cycles_by_module[src].append(dst)
                for src in sorted(cycles_by_module.keys()):
                    for dst in sorted(cycles_by_module[src]):
                        print(f"  {src} -> {dst}", file=sys.stderr)
            elif check_type == 'circular':
                print("No circular dependencies found.")

        # Check re-imports
        if check_type in ('all', 'reimports'):
            violations = detect_reimports(mset)
            if violations:
                has_errors = True
                print("Re-imports detected:", file=sys.stderr)
                for v in sorted(violations, key=lambda x: (x['module'], x['name'])):
                    print(f"  {v['module']}: '{v['name']}' imported from {v['imported_from']}", file=sys.stderr)
                    print(f"    -> should import from {v['original_source']}", file=sys.stderr)
            elif check_type == 'reimports':
                print("No re-imports found.")

        # Check inner imports
        if check_type in ('all', 'inner'):
            violations = []
            for result in results:
                inner = ast_inner_imports(result['filepath'])
                for line, col, module in inner:
                    violations.append({
                        'file': result['filepath'],
                        'line': line,
                        'col': col,
                        'import': module
                    })
            if violations:
                has_errors = True
                print("Inner imports detected:", file=sys.stderr)
                for v in sorted(violations, key=lambda x: (x['file'], x['line'])):
                    print(f"  {v['file']}:{v['line']}:{v['col']}: {v['import']}", file=sys.stderr)
            elif check_type == 'inner':
                print("No inner imports found.")

        if check_type == 'all' and not has_errors:
            print("All checks passed.")

        sys.exit(1 if has_errors else 0)

    # Output results
    if config.json:
        print(json.dumps(results, indent=2))
    elif config.dot:
        print(format_dot(results))
    elif config.sort:
        sort_result = topological_sort(results)
        for module in sort_result.modules:
            if config.verbose:
                print(f"{module}\t{sort_result.levels[module]}\t{sort_result.depths[module]}")
            else:
                print(module)
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
