"""Module without inner imports - all imports at module level."""

import os
import json
from pathlib import Path
import re


def some_function():
    return json.dumps({})


class SomeClass:
    def method(self):
        return re.match(r'.*', '')
