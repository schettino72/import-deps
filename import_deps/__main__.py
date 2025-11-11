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


def topological_sort(results):
    """Topological sort of modules (dependencies before dependents).
    Uses Kahn's algorithm with rank-based ordering for stability.
    Rank is defined as the longest path from any leaf node (module that imports but isn't imported).
    When multiple nodes become available, nodes with higher rank are output first.

    Handles circular dependencies gracefully:
    - Nodes actually in cycles are identified and processed last
    - Nodes that depend on cycles (but aren't in them) are processed normally
    - Isolated nodes (no dependencies, no dependents) are placed last

    Returns list of module names in topological order (dependencies before dependents).
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

    # Calculate rank for each node (longest path from any leaf node)
    # Leaf nodes are those that have no dependents (nothing imports them)
    # Detect cycles using DFS with recursion stack
    rank = {}
    in_cycle = set()

    def calculate_rank(node, visiting=None, rec_path=None):
        if visiting is None:
            visiting = set()
        if rec_path is None:
            rec_path = []

        if node in rank:
            return rank[node]

        if node in visiting:
            # Cycle detected - mark all nodes in the cycle path
            cycle_start = rec_path.index(node)
            for i in range(cycle_start, len(rec_path)):
                in_cycle.add(rec_path[i])
            in_cycle.add(node)
            return -1  # Special value for cycles

        visiting.add(node)
        rec_path.append(node)
        deps = dependents[node]  # Use dependents (who imports this node)

        if not deps:
            rank[node] = 1  # Leaf nodes (not imported by anyone) have rank 1
        else:
            dep_ranks = []
            for dep in deps:
                dep_rank = calculate_rank(dep, visiting, rec_path)
                if dep_rank == -1:
                    # Dependent is in cycle
                    pass
                else:
                    dep_ranks.append(dep_rank)

            # Only mark as cycle if this node is actually in the cycle
            if node in in_cycle:
                rank[node] = -1
            elif dep_ranks:
                rank[node] = max(dep_ranks) + 1
            else:
                # All dependents are in cycles, but this node isn't
                rank[node] = 2

        rec_path.pop()
        visiting.remove(node)
        return rank[node]

    for module in all_modules:
        if module not in rank:
            calculate_rank(module)

    # Topological sort: start with roots (nodes with no dependencies)
    # in_degree tracks how many unprocessed dependencies each node has
    in_degree = {module: len(dependencies[module]) for module in all_modules}

    # Separate cycle nodes and isolated nodes from regular nodes
    cycle_nodes = {node for node in all_modules if rank[node] == -1}
    isolated_nodes = {node for node in all_modules
                      if len(dependencies[node]) == 0 and len(dependents[node]) == 0}

    non_cycle_roots = [node for node in all_modules
                       if in_degree[node] == 0
                       and node not in cycle_nodes
                       and node not in isolated_nodes]

    # Initial queue: non-cycle, non-isolated roots, sorted by rank DESC then name ASC
    queue = sorted(non_cycle_roots, key=lambda x: (-rank[x], x))
    sorted_list = []

    while queue:
        node = queue.pop(0)
        sorted_list.append(node)

        # Process all dependents of this node (nodes that import this node)
        for dependent in dependents[node]:
            if dependent not in cycle_nodes and dependent not in isolated_nodes:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    # Insert maintaining rank order (higher rank first)
                    # Within same rank, maintain FIFO order
                    dep_rank = rank[dependent]
                    insert_idx = len(queue)
                    for i, queued_node in enumerate(queue):
                        if rank[queued_node] < dep_rank:
                            insert_idx = i
                            break
                    queue.insert(insert_idx, dependent)

    # Handle remaining nodes (cycles and nodes not yet processed, but not isolated)
    remaining = all_modules - set(sorted_list) - isolated_nodes
    if remaining:
        # Add remaining nodes sorted alphabetically
        sorted_list.extend(sorted(remaining))

    # Add isolated nodes last (sorted alphabetically)
    if isolated_nodes:
        sorted_list.extend(sorted(isolated_nodes))

    return sorted_list


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
    parser.add_argument('path', metavar='PATH',
                        help='Python file or package directory to analyze')
    parser.add_argument('--json', action='store_true',
                        help='Output results in JSON format')
    parser.add_argument('--dot', action='store_true',
                        help='Output results in DOT format for graphviz')
    parser.add_argument('--check', action='store_true',
                        help='Check for circular dependencies and exit with error if found')
    parser.add_argument('--sort', action='store_true',
                        help='Output modules in topological sort order (dependencies first)')
    parser.add_argument('--version', action='version',
                        version='.'.join(str(i) for i in __version__))
    config = parser.parse_args(argv[1:])

    # Check for mutually exclusive flags
    output_flags = sum([config.json, config.dot, config.sort])
    if output_flags > 1:
        print("Error: --json, --dot, and --sort are mutually exclusive", file=sys.stderr)
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
    elif config.sort:
        sorted_modules = topological_sort(results)
        for module in sorted_modules:
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
