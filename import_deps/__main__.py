import argparse
import json
import pathlib
import sys

from . import __version__, PyModule, ModuleSet, ast_defined_names


def get_all_imports(results):
    """Calculate transitive imports for all modules.
    Returns dict of module -> set of all imports (direct + transitive)
    """
    graph = {r['module']: set(r['imports']) for r in results}
    all_imports = {}

    for module in graph:
        visited = set()
        queue = list(graph.get(module, []))
        while queue:
            dep = queue.pop(0)
            if dep not in visited:
                visited.add(dep)
                queue.extend(graph.get(dep, []))
        visited.discard(module)  # Exclude self
        all_imports[module] = visited

    return all_imports


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


def topological_sort(results):
    """Topological sort of modules with lexicographic ranking.

    Uses Kahn's algorithm with two ranking metrics:
    - level: reverse topological level (distance from sources/entry points)
    - depth: topological level (distance from sinks/leaf dependencies)

    Terminology:
    - Sources: nodes not imported by anyone (entry points)
    - Sinks: nodes that import nothing (leaf dependencies)

    Handles circular dependencies gracefully:
    - Nodes in cycles get level=-1 and depth=-1
    - Nodes that depend on cycles are processed normally

    Returns (sorted_list, levels, depths):
    - sorted_list: module names in topological order
    - levels: dict of module -> level (distance from sources)
    - depths: dict of module -> depth (distance from sinks)
    """
    # Collect all modules
    all_modules = set(result['module'] for result in results)

    # Build dependencies: module -> list of modules it imports (its dependencies)
    dependencies = {module: [] for module in all_modules}
    for result in results:
        module = result['module']
        dependencies[module] = [imp for imp in result['imports'] if imp in all_modules]

    # Build reverse graph: module -> list of modules that import it (its dependents)
    dependents = {module: [] for module in all_modules}
    for module in all_modules:
        for dep in dependencies[module]:
            dependents[dep].append(module)

    # Detect cycles first using DFS
    in_cycle = set()

    def detect_cycles(node, visiting, rec_path):
        if node in visiting:
            cycle_start = rec_path.index(node)
            for i in range(cycle_start, len(rec_path)):
                in_cycle.add(rec_path[i])
            in_cycle.add(node)
            return
        if node in in_cycle:
            return
        visiting.add(node)
        rec_path.append(node)
        for dep in dependencies[node]:
            detect_cycles(dep, visiting, rec_path)
        rec_path.pop()
        visiting.remove(node)

    for module in all_modules:
        detect_cycles(module, set(), [])

    # Calculate depth: distance from sinks (nodes with no dependencies)
    # Sinks have depth 1, increases toward sources
    depths = {}

    def calculate_depth(node):
        if node in depths:
            return depths[node]
        if node in in_cycle:
            depths[node] = -1
            return -1

        deps = dependencies[node]
        if not deps:
            depths[node] = 1  # Sink/leaf node
        else:
            dep_depths = [calculate_depth(d) for d in deps if d not in in_cycle]
            if dep_depths:
                depths[node] = max(dep_depths) + 1
            else:
                depths[node] = 2  # All deps in cycle
        return depths[node]

    for module in all_modules:
        calculate_depth(module)

    # Calculate level: distance from sources (nodes not imported by anyone)
    # Sources have level 1, increases toward sinks
    levels = {}

    def calculate_level(node):
        if node in levels:
            return levels[node]
        if node in in_cycle:
            levels[node] = -1
            return -1

        deps = dependents[node]  # Who imports this node
        if not deps:
            levels[node] = 1  # Source/root node
        else:
            dep_levels = [calculate_level(d) for d in deps if d not in in_cycle]
            if dep_levels:
                levels[node] = max(dep_levels) + 1
            else:
                levels[node] = 2  # All dependents in cycle
        return levels[node]

    for module in all_modules:
        calculate_level(module)

    # Topological sort using Kahn's algorithm
    in_degree = {module: len(dependencies[module]) for module in all_modules}

    cycle_nodes = {node for node in all_modules if node in in_cycle}

    non_cycle_roots = [node for node in all_modules
                       if in_degree[node] == 0
                       and node not in cycle_nodes]

    # Sort by level DESC (deep dependencies first), depth ASC (simpler first), then name ASC
    queue = sorted(non_cycle_roots, key=lambda x: (-levels[x], depths[x], x))
    sorted_list = []

    while queue:
        node = queue.pop(0)
        sorted_list.append(node)

        for dependent in dependents[node]:
            if dependent not in cycle_nodes:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    # Insert maintaining sort order
                    key = (-levels[dependent], depths[dependent], dependent)
                    insert_idx = len(queue)
                    for i, queued_node in enumerate(queue):
                        queued_key = (-levels[queued_node], depths[queued_node], queued_node)
                        if queued_key > key:
                            insert_idx = i
                            break
                    queue.insert(insert_idx, dependent)

    # Handle remaining nodes (cycles)
    remaining = all_modules - set(sorted_list)
    if remaining:
        sorted_list.extend(sorted(remaining))

    return sorted_list, levels, depths


def format_dot(results, highlight_cycles=True):
    """Format results as DOT graph for graphviz"""
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
    parser.add_argument('--check', action='store_true',
                        help='Check for circular dependencies and exit with error if found')
    parser.add_argument('--check-reimports', action='store_true',
                        help='Check for re-imports (importing from re-exporting module instead of original)')
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
            'imports': sorted(imports)
        })

    # Add transitive imports if requested
    if config.all_imports:
        all_imports_map = get_all_imports(results)
        for result in results:
            result['all_imports'] = sorted(all_imports_map.get(result['module'], set()))

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

    # Check for re-imports
    if config.check_reimports:
        violations = detect_reimports(mset)
        if violations:
            print("Re-imports detected:", file=sys.stderr)
            for v in sorted(violations, key=lambda x: (x['module'], x['name'])):
                print(f"  {v['module']}: '{v['name']}' imported from {v['imported_from']}", file=sys.stderr)
                print(f"    -> should import from {v['original_source']}", file=sys.stderr)
            sys.exit(1)
        else:
            print("No re-imports found.")
            sys.exit(0)

    # Output results
    if config.json:
        print(json.dumps(results, indent=2))
    elif config.dot:
        print(format_dot(results))
    elif config.sort:
        sorted_modules, levels, depths = topological_sort(results)
        for module in sorted_modules:
            if config.verbose:
                print(f"{module}\t{levels[module]}\t{depths[module]}")
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
