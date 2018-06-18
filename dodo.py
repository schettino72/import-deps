from doitpy.pyflakes import Pyflakes
from doitpy.coverage import Coverage, PythonPackage


DOIT_CONFIG = {
    'default_tasks': ['pyflakes'],
    }


def task_pyflakes():
    flaker = Pyflakes()
    yield flaker.tasks('*.py')
    yield flaker.tasks('import_deps/*.py')
    yield flaker.tasks('tests/*.py')


def task_coverage():
    """show coverage for all modules including tests"""
    cov = Coverage(
        [PythonPackage('import_deps', 'tests')],
        config={'branch':True,},
    )
    yield cov.all() # create task `coverage`
    yield cov.src() # create task `coverage_src`
