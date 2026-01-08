"""Graph algorithms for dependency analysis."""

from typing import NamedTuple, TypedDict


class ModuleResult(TypedDict, total=False):
    """Result dict for a single module's import analysis.

    Attributes:
        module: Fully qualified module name (e.g., "foo.bar.baz")
        filepath: Path to the module file
        imports: List of direct imports as fully qualified names
        all_imports: List of all transitive imports (only present with --all-imports)
    """
    module: str
    filepath: str
    imports: list[str]
    all_imports: list[str]  # optional, added by --all-imports


class SortResult(NamedTuple):
    """Result of topological sort.

    Attributes:
        modules: Module names in topological order
        filepaths: Dict of module -> filepath
        levels: Dict of module -> level (distance from sources)
        depths: Dict of module -> depth (distance from sinks)
    """
    modules: list[str]
    filepaths: dict[str, str]
    levels: dict[str, int]
    depths: dict[str, int]


def get_all_imports(results: list[ModuleResult]) -> dict[str, set[str]]:
    """Calculate transitive imports for all modules."""
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


def detect_cycles(results: list[ModuleResult]) -> set[tuple[str, str]]:
    """Detect circular dependencies using DFS."""
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


def topological_sort(results: list[ModuleResult]) -> SortResult:
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
    """
    # Collect all modules and filepaths
    all_modules = set(result['module'] for result in results)
    filepaths = {r['module']: r.get('filepath', '') for r in results}

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

    def detect_cycles_internal(node, visiting, rec_path):
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
            detect_cycles_internal(dep, visiting, rec_path)
        rec_path.pop()
        visiting.remove(node)

    for module in all_modules:
        detect_cycles_internal(module, set(), [])

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

    return SortResult(modules=sorted_list, filepaths=filepaths, levels=levels, depths=depths)
