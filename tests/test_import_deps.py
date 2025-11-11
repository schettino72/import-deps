import json
import os
import pathlib

import pytest

from import_deps import ast_imports
from import_deps import PyModule
from import_deps import ModuleSet
from import_deps.__main__ import main


# list of modules in sample folder used for testing
sample_dir = pathlib.Path(__file__).parent / 'sample-import'
class FOO:
    pkg = sample_dir / 'foo'
    init = pkg / '__init__.py'
    a = pkg / 'foo_a.py'
    b = pkg / 'foo_b.py'
    c = pkg / 'foo_c.py'
    d = pkg / 'foo_d.py'
class SUB:
    pkg = FOO.pkg / 'sub'
    init = pkg / '__init__.py'
    a = pkg / 'sub_a.py'
BAR = sample_dir / 'bar.py'
BAZ = sample_dir / 'baz.py'



def test_ast_imports():
    imports = ast_imports(FOO.a)
    # import bar
    assert (None, 'bar', None, None) == imports[0]
    # from foo import foo_b
    assert ('foo', 'foo_b', None, 0) == imports[1]
    # from foo.foo_c import obj_c
    assert ('foo.foo_c', 'obj_c', None, 0) == imports[2]
    # from .. import sample_d
    assert (None, 'sample_d', None, 2) == imports[3]
    # from ..sample_e import jkl
    assert ('sample_e', 'jkl', None, 2) == imports[4]
    # from sample_f import *
    assert ('sample_f', '*', None, 0) == imports[5]
    # import sample_g.other
    assert (None, 'sample_g.other', None, None) == imports[6]
    # TODO test `impors XXX as YYY`
    assert 7 == len(imports)



class Test_PyModule(object):
    def test_repr(self):
        module = PyModule(SUB.a)
        assert "<PyModule {}>".format(SUB.a) == repr(module)

    def test_is_pkg(self):
        assert True == PyModule.is_pkg(FOO.pkg)
        assert False == PyModule.is_pkg(FOO.init)
        assert False == PyModule.is_pkg(FOO.a)
        assert True == PyModule.is_pkg(SUB.pkg)
        assert False == PyModule.is_pkg(SUB.a)

    def test_fqn(self):
        assert ['bar'] == PyModule(BAR).fqn
        assert ['foo', '__init__'] == PyModule(FOO.init).fqn
        assert ['foo', 'foo_a'] == PyModule(FOO.a).fqn
        assert ['foo', 'sub', 'sub_a'] == PyModule(SUB.a).fqn

    def test_pkg_path(self):
        assert sample_dir == PyModule(BAR).pkg_path()
        assert sample_dir == PyModule(SUB.a).pkg_path()

    def test_relative_path(self):
        cwd = os.getcwd()
        try:
            # do not try to get package beyond given relative path
            os.chdir(FOO.pkg.resolve())
            assert ['foo_a'] == PyModule('foo_a.py').fqn
        finally:
            os.chdir(cwd)

class Test_ModuleSet_Init(object):

    def test_init_with_packge(self):
        modset = ModuleSet([FOO.init, FOO.a])
        assert set(['foo']) == modset.pkgs
        assert 2 == len(modset.by_path)
        assert modset.by_path[FOO.init].fqn == ['foo', '__init__']
        assert modset.by_path[FOO.a].fqn == ['foo', 'foo_a']
        assert 2 == len(modset.by_name)
        assert modset.by_name['foo.__init__'].fqn == ['foo', '__init__']
        assert modset.by_name['foo.foo_a'].fqn == ['foo', 'foo_a']

    def test_init_no_packge(self):
        # if a module of a package is added but no __init__.py
        # its packages is not added to the list of packages
        modset = ModuleSet([FOO.a])
        assert 0 == len(modset.pkgs)
        assert 1 == len(modset.by_path)
        assert modset.by_path[FOO.a].fqn == ['foo', 'foo_a']

    def test_init_subpackge(self):
        modset = ModuleSet([FOO.init, SUB.init, SUB.a])
        assert set(['foo', 'foo.sub']) == modset.pkgs
        assert 3 == len(modset.by_path)
        assert modset.by_path[SUB.a].fqn == ['foo', 'sub', 'sub_a']


class Test_ModuleSet_GetImports(object):

    def test_import_module(self):
        # foo_a  =>  import bar
        modset = ModuleSet([FOO.a, BAR])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 1
        assert BAR in got

    def test_import_not_tracked(self):
        modset = ModuleSet([FOO.a])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 0

    def test_import_pkg(self):
        # bar  =>  import foo
        modset = ModuleSet([FOO.init, BAR])
        got = modset.get_imports(modset.by_name['bar'])
        assert len(got) == 1
        assert FOO.init in got

    def test_from_pkg_import_module(self):
        # foo_a  =>  from foo import foo_b
        modset = ModuleSet([FOO.init, FOO.a, FOO.b])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 1
        assert FOO.b in got

    def test_from_import_object(self):
        # foo_a  =>  from foo.foo_c import obj_c
        modset = ModuleSet([FOO.init, FOO.a, FOO.b, FOO.c])
        got = modset.get_imports(modset.by_name['foo.foo_a'])
        assert len(got) == 2
        assert FOO.b in got # doesnt matter for this test
        assert FOO.c in got

    def test_from_pkg_import_obj(self):
        # baz  =>  from foo import obj_1
        modset = ModuleSet([FOO.init, BAZ])
        got = modset.get_imports(modset.by_name['baz'])
        assert len(got) == 1
        assert FOO.init in got

    def test_import_obj(self):
        # foo_b  =>  import baz.obj_baz
        modset = ModuleSet([FOO.b, BAZ])
        got = modset.get_imports(modset.by_name['foo.foo_b'])
        assert len(got) == 1
        assert BAZ in got

    def test_relative_intra_import_pkg_obj(self):
        # foo_c  =>  from . import foo_i
        modset = ModuleSet([FOO.init, FOO.c])
        got = modset.get_imports(modset.by_name['foo.foo_c'])
        assert len(got) == 1
        assert FOO.init in got

    def test_relative_intra_import_module(self):
        # foo_d  =>  from . import foo_c
        modset = ModuleSet([FOO.init, FOO.c, FOO.d])
        got = modset.get_imports(modset.by_name['foo.foo_d'])
        assert len(got) == 1
        assert FOO.c in got

    def test_relative_parent(self):
        # foo.sub.sub_a  =>  from .. import foo_d
        modset = ModuleSet([FOO.init, FOO.d, SUB.init, SUB.a])
        got = modset.get_imports(modset.by_name['foo.sub.sub_a'])
        assert len(got) == 1
        assert FOO.d in got

    def test_return_module_name(self):
        # foo_a  =>  import bar
        modset = ModuleSet([FOO.a, BAR])
        got = modset.get_imports(modset.by_name['foo.foo_a'],
                                 return_fqn=True)
        name = got.pop()
        assert len(got) == 0
        assert name == 'bar'



    def test_mod_imports(self):
        # foo_a  =>  import bar
        modset = ModuleSet([FOO.init, FOO.a, FOO.b, FOO.c, BAR])
        got = modset.mod_imports('foo.foo_a')
        imports = list(sorted(got))
        assert imports == ['bar', 'foo.foo_b', 'foo.foo_c']


class Test_CLI(object):
    def test_single_file(self, capsys):
        # Test single file analysis
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.a)])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        lines = captured.out.strip().split('\n')
        assert 'bar' in lines
        assert 'foo.foo_b' in lines
        assert 'foo.foo_c' in lines

    def test_single_file_json(self, capsys):
        # Test single file with JSON output
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.a), '--json'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        assert len(result) == 1
        assert result[0]['module'] == 'foo.foo_a'
        assert 'bar' in result[0]['imports']
        assert 'foo.foo_b' in result[0]['imports']
        assert 'foo.foo_c' in result[0]['imports']

    def test_directory(self, capsys):
        # Test directory analysis
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg)])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = captured.out

        # Should contain module names and their imports
        assert 'foo.foo_a:' in output
        assert 'foo.foo_d:' in output
        assert 'foo.sub.sub_a:' in output

    def test_directory_json(self, capsys):
        # Test directory with JSON output
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg), '--json'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        result = json.loads(captured.out)

        # Should have multiple modules
        assert len(result) > 1

        # Find foo.foo_a module
        foo_a = next((m for m in result if m['module'] == 'foo.foo_a'), None)
        assert foo_a is not None
        assert 'foo.foo_b' in foo_a['imports']
        assert 'foo.foo_c' in foo_a['imports']

        # Find foo.sub.sub_a module
        sub_a = next((m for m in result if m['module'] == 'foo.sub.sub_a'), None)
        assert sub_a is not None
        assert 'foo.foo_d' in sub_a['imports']

    def test_single_file_dot(self, capsys):
        # Test single file with DOT output
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.a), '--dot'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = captured.out

        # Check DOT format structure
        assert 'digraph imports {' in output
        assert '}' in output
        assert '"foo.foo_a" -> "foo.foo_b";' in output
        assert '"foo.foo_a" -> "foo.foo_c";' in output

    def test_directory_dot(self, capsys):
        # Test directory with DOT output
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg), '--dot'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = captured.out

        # Check DOT format structure
        assert 'digraph imports {' in output
        assert '}' in output
        assert '"foo.foo_a" -> "foo.foo_b";' in output
        assert '"foo.foo_c" -> "foo.__init__";' in output
        assert '"foo.sub.sub_a" -> "foo.foo_d";' in output

    def test_mutually_exclusive_flags(self, capsys):
        # Test that --json and --dot are mutually exclusive
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.a), '--json', '--dot'])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'mutually exclusive' in captured.err

    def test_no_cycles_in_sample(self, capsys):
        # Test that sample data has no circular dependencies
        # So no red edges should appear in DOT output
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg), '--dot'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        output = captured.out

        # Normal dependencies should not have color attribute
        assert '"foo.sub.sub_a" -> "foo.foo_d";' in output
        assert '"foo.foo_c" -> "foo.__init__";' in output

        # No cycles in sample data, so no red edges
        assert 'color=red' not in output

    def test_check_no_cycles(self, capsys):
        # Test --check on data without cycles
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg), '--check'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert 'No circular dependencies found' in captured.out

    def test_sort(self, capsys):
        # Test --sort topological ordering
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg), '--sort'])

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        modules = captured.out.strip().split('\n')

        # Verify all modules are present
        assert 'foo.__init__' in modules
        assert 'foo.foo_a' in modules
        assert 'foo.foo_b' in modules
        assert 'foo.foo_c' in modules
        assert 'foo.foo_d' in modules
        assert 'foo.sub.__init__' in modules
        assert 'foo.sub.sub_a' in modules

        # Verify topological order: dependencies come before dependents
        # foo.foo_a depends on foo.foo_b and foo.foo_c
        assert modules.index('foo.foo_b') < modules.index('foo.foo_a')
        assert modules.index('foo.foo_c') < modules.index('foo.foo_a')

        # foo.foo_c depends on foo.__init__
        assert modules.index('foo.__init__') < modules.index('foo.foo_c')

        # foo.foo_d depends on foo.foo_c
        assert modules.index('foo.foo_c') < modules.index('foo.foo_d')

        # foo.sub.sub_a depends on foo.foo_d
        assert modules.index('foo.foo_d') < modules.index('foo.sub.sub_a')

    def test_sort_mutually_exclusive(self, capsys):
        # Test that --sort and --json are mutually exclusive
        with pytest.raises(SystemExit) as exc_info:
            main(['import_deps', str(FOO.pkg), '--sort', '--json'])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'mutually exclusive' in captured.err
