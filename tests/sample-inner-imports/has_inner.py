"""Module with inner imports (imports inside functions/classes)."""

import os  # this is OK - at module level


def some_function():
    import json  # violation
    from pathlib import Path  # violation
    return json.dumps({})


class SomeClass:
    def method(self):
        import re  # violation
        return re.match(r'.*', '')
