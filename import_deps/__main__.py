import argparse
import json
import pathlib
import sys

from . import __version__, PyModule, ModuleSet


def detect_cycles(results):
    """Detect circular dependencies using DFS
    Returns set of edges (module, import) that create cycles
    """
    # Build adjacency list
    graph = {}
    for result in results:
        module = result['module']
        graph[module] = result['imports']

    cycle_edges = set()
    visited = set()
    rec_stack = set()

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if neighbor in graph:  # Only follow if it's in our tracked modules
                    dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Found a cycle - mark all edges in the cycle
                cycle_start_idx = path.index(neighbor)
                for i in range(cycle_start_idx, len(path)):
                    if i + 1 < len(path):
                        cycle_edges.add((path[i], path[i + 1]))
                # Add the back edge
                cycle_edges.add((node, neighbor))

        rec_stack.remove(node)
        path.pop()

    for module in graph:
        if module not in visited:
            dfs(module, [])

    return cycle_edges


def format_dot(results, highlight_cycles=True):
    """Format results as DOT graph for graphviz"""
    lines = ['digraph imports {']
    lines.append('    rankdir=LR;')

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
        lines.append(f'{ind}    style = rounded;')

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
    parser.add_argument('path', metavar='PATH',
                        help='Python file or package directory to analyze')
    parser.add_argument('--json', action='store_true',
                        help='Output results in JSON format')
    parser.add_argument('--dot', action='store_true',
                        help='Output results in DOT format for graphviz')
    parser.add_argument('--check', action='store_true',
                        help='Check for circular dependencies and exit with error if found')
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

    # Check for circular dependencies
    if config.check:
        cycle_edges = detect_cycles(results)
        if cycle_edges:
            print("Circular dependencies detected:", file=sys.stderr)

            # Group cycles by modules involved
            cycles_by_module = {}
            for src, dst in cycle_edges:
                if src not in cycles_by_module:
                    cycles_by_module[src] = []
                cycles_by_module[src].append(dst)

            for src in sorted(cycles_by_module.keys()):
                for dst in sorted(cycles_by_module[src]):
                    print(f"  {src} -> {dst}", file=sys.stderr)

            sys.exit(1)
        else:
            print("No circular dependencies found.")
            sys.exit(0)

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
