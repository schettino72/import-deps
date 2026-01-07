# GOOD: importing from __init__.py is allowed (whitelisted)
from . import foo_func

def use_it():
    foo_func()
