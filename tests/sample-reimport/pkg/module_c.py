# BAD: imports foo_func from module_b, but it's defined in module_a
from .module_b import foo_func, FooClass

# GOOD: imports bar_func from module_b where it's defined
from .module_b import bar_func

def use_them():
    foo_func()
    bar_func()
