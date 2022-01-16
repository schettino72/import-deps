import os
import pathlib

from import_deps import ast_imports
from import_deps import PyModule
from import_deps import ModuleSet


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
