# import_deps

[![PyPI version](https://img.shields.io/pypi/v/import-deps.svg)](https://pypi.org/project/import-deps/)
[![Python versions](https://img.shields.io/pypi/pyversions/import-deps.svg)](https://pypi.org/project/import-deps/)
[![CI Github actions](https://github.com/schettino72/import-deps/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/schettino72/import-deps/actions/workflows/test.yml?query=branch%3Amaster)

Find python module's import dependencies.

`import_deps` is based on [ast module](https://docs.python.org/3/library/ast.html) from standard library,
so the modules being analysed are *not* executed.


## Install

```
pip install import_deps
```


## Usage

`import_deps` is designed to track only imports within a known set of package and modules.

Given a package with the modules:

- `foo/__init__.py`
- `foo/foo_a.py`
- `foo/foo_b.py`
- `foo/foo_c.py`

Where `foo_a.py` has the following imports:

```python3
from . import foo_b
from .foo_c import obj_c
```

## Usage (CLI)

### Analyze a single file

```bash
> import_deps foo/foo_a.py
foo.foo_b
foo.foo_c
```

### Analyze a package directory

```bash
> import_deps foo/
foo.__init__:
foo.foo_a:
  foo.foo_b
  foo.foo_c
foo.foo_b:
foo.foo_c:
  foo.__init__
```

### JSON output

Use the `--json` flag to get results in JSON format:

```bash
> import_deps foo/foo_a.py --json
[
  {
    "module": "foo.foo_a",
    "imports": [
      "foo.foo_b",
      "foo.foo_c"
    ]
  }
]
```

For package analysis with JSON:

```bash
> import_deps foo/ --json
[
  {
    "module": "foo.__init__",
    "imports": []
  },
  {
    "module": "foo.foo_a",
    "imports": [
      "foo.foo_b",
      "foo.foo_c"
    ]
  },
  ...
]
```

### Transitive imports

Use `--all-imports` with `--json` to include all transitive dependencies (not just direct imports):

```bash
> import_deps foo/ --json --all-imports
[
  {
    "module": "foo.foo_a",
    "imports": [
      "foo.foo_b",
      "foo.foo_c"
    ],
    "all_imports": [
      "foo.__init__",
      "foo.foo_b",
      "foo.foo_c"
    ]
  },
  ...
]
```

The `all_imports` field contains all modules that a module depends on, directly or indirectly. This is useful for understanding the full dependency tree of a module.

### DOT output for visualization

Use the `--dot` flag to generate a dependency graph in DOT format for graphviz:

```bash
> import_deps foo/ --dot
digraph imports {
    "foo.foo_a" -> "foo.foo_b";
    "foo.foo_a" -> "foo.foo_c";
    "foo.foo_c" -> "foo.__init__";
    "foo.foo_d" -> "foo.foo_c";
    "foo.sub.sub_a" -> "foo.foo_d";
}
```

You can visualize the graph using graphviz:

```bash
> import_deps foo/ --dot | dot -Tpng > dependencies.png
> import_deps foo/ --dot | dot -Tsvg > dependencies.svg
```

The DOT output features:
- Modules displayed as light blue rounded boxes
- Packages grouped with dashed gray borders (clearly distinct from arrows)
- Sub-packages nested hierarchically
- Circular dependencies highlighted in **bold red arrows**

### Checks

Use `--check` to run all checks, or `--check=TYPE` for a specific check:

| Flag | Check |
|------|-------|
| `--check` | Run all checks |
| `--check=circular` | Circular dependencies only |
| `--check=reimports` | Re-imports only |
| `--check=inner` | Inner imports only |

```bash
> import_deps foo/ --check
All checks passed.

# Or run a specific check:
> import_deps foo/ --check=circular
No circular dependencies found.
```

**Note:** When using `--check` without a type before PATH, use `--check=all`:
```bash
> import_deps --check=all foo/   # OK
> import_deps foo/ --check       # OK
```

This is useful for CI/CD pipelines to enforce code quality rules.

### Check for circular dependencies

Use `--check=circular` to detect circular dependencies:

```bash
> import_deps foo/ --check=circular
Circular dependencies detected:
  foo.module_a -> foo.module_b
  foo.module_b -> foo.module_a
# (exits with code 1)
```

### Check for re-imports

Use `--check=reimports` to detect re-imports. A re-import occurs when you import a name from a module that itself imported it from somewhere else, rather than importing from the original source.

```python
# pkg/module_a.py - defines foo_func
def foo_func():
    pass

# pkg/module_b.py - re-exports foo_func
from .module_a import foo_func  # re-export

# pkg/module_c.py - BAD: imports from module_b instead of module_a
from .module_b import foo_func  # re-import!
```

```bash
> import_deps pkg/ --check=reimports
Re-imports detected:
  pkg.module_c: 'foo_func' imported from pkg.module_b
    -> should import from pkg.module_a
# (exits with code 1)

# If no re-imports:
> import_deps pkg/ --check=reimports
No re-imports found.
```

**Note:** `__init__.py` files are whitelisted since they commonly re-export symbols to provide a cleaner public API.

This is useful for:
- Enforcing clean import hygiene in your codebase
- Making dependencies explicit and traceable
- Avoiding confusion about where symbols are actually defined

### Check for inner imports

Use `--check=inner` to detect imports inside functions or classes (not at module level).

```python
# pkg/module.py
import os  # OK - at module level

def some_function():
    import json  # BAD - inner import
    from pathlib import Path  # BAD - inner import
```

```bash
> import_deps pkg/ --check=inner
Inner imports detected:
  pkg/module.py:5:4: json
  pkg/module.py:6:4: pathlib
# (exits with code 1)

# If no inner imports:
> import_deps pkg/ --check=inner
No inner imports found.
```

This is useful for:
- Enforcing consistent import style (all imports at module level)
- Improving code readability and maintainability
- Making dependencies visible at the top of each file

### Topological sort

Use the `--sort` flag to output modules in topological order (dependencies before dependents):

```bash
> import_deps foo/ --sort
foo.__init__
foo.foo_c
bar
foo.foo_b
foo.foo_d
foo.sub.__init__
foo.foo_a
foo.sub.sub_a
```

Add `-v/--verbose` to show level and depth rankings:

```bash
> import_deps foo/ --sort -v
foo.__init__	4	1
foo.foo_c	3	2
bar	2	2
foo.foo_b	2	3
foo.foo_d	2	3
foo.sub.__init__	1	1
foo.foo_a	1	4
foo.sub.sub_a	1	4
```

The verbose output is tab-separated: `module\tlevel\tdepth`

**Terminology:**
- **Sources**: modules not imported by anyone (entry points)
- **Sinks**: modules that import nothing (leaf dependencies)
- **Level**: distance from sources (reverse topological level)
- **Depth**: distance from sinks (longest dependency chain)

**Ordering:**
- Sorted by level DESC (deep dependencies first), then depth ASC (simpler modules first), then name
- Dependencies always appear before modules that import them
- Circular dependencies are handled gracefully (level=-1, depth=-1)

#### Handling circular dependencies

When circular dependencies exist, the sort handles them gracefully:
```bash
# If you have: A -> C -> B -> A (circular); D -> B; E (isolated)
> import_deps circular_package/ --sort -v
E	1	1
A	-1	-1
B	-1	-1
C	-1	-1
D	1	2
```

The ordering is:
1. A, B, C first (nodes in the cycle, level=-1, depth=-1)
2. D next (source with level=1, imports B which is in cycle)
3. E last (isolated node with level=1, depth=1)


## Usage (lib)

```python3
import pathlib
from import_deps import ModuleSet

# First initialise a ModuleSet instance with a list str of modules to track
pkg_paths = pathlib.Path('foo').glob('**/*.py')
module_set = ModuleSet([str(p) for p in pkg_paths])

# then you can get the set of imports
for imported in module_set.mod_imports('foo.foo_a'):
    print(imported)

# foo.foo_c
# foo.foo_b
```

### ModuleSet

You can get a list of  all modules in a `ModuleSet` by path or module's full qualified name.

`by_path`

Note that key for `by_path` must be exactly the as provided on ModuleSet initialization.

```python3
for mod in sorted(module_set.by_path.keys()):
    print(mod)

# results in:
# foo/__init__.py
# foo/foo_a.py
# foo/foo_b.py
# foo/foo_c.py
```

`by_name`

```python3
for mod in sorted(module_set.by_name.keys()):
    print(mod)

# results in:
# foo.__init__
# foo.foo_a
# foo.foo_b
# foo.foo_c
```



### ast_imports(file_path)

`ast_imports` is a low level function that returns a list of entries for import statement in the module.
The parameter `file_path` can be a string or `pathlib.Path` instance.

The return value is a list of 4-tuple items with values:
 - module name (of the "from" statement, `None` if a plain `import`)
 - object name
 - as name
 - level of relative import (number of parent, `None` if plain `import`)


```python3
from import_deps import ast_imports

ast_imports('foo.py')
```


```python3
# import datetime
(None, 'datetime', None, None)

# from datetime import time
('datetime', 'time', None, 0)

# from datetime import datetime as dt
('datetime', 'datetime', 'dt', 0)

# from .. import bar
(None, 'bar', None, 2)

# from .acme import baz
('acme', 'baz', None, 1)


# note that a single statement will contain one entry per imported "name"
# from datetime import time, timedelta
('datetime', 'time', None, 0)
('datetime', 'timedelta', None, 0)
```

