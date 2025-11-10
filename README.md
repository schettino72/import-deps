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

