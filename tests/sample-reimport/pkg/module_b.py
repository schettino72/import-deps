# Re-exports foo_func from module_a (this is the middleman)
from .module_a import foo_func, FooClass

def bar_func():
    pass
