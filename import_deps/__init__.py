__version__ = (0, 2, 0)

import ast
import pathlib


class _ImportsFinder(ast.NodeVisitor):
    """find all imports
    :ivar imports: (list - tuple) (module, name, asname, level)
    """
    def __init__(self):
        ast.NodeVisitor.__init__(self)
        self.imports = []

    def visit_Import(self, node):
        """callback for 'import' statement"""
        self.imports.extend((None, n.name, n.asname, None)
                            for n in node.names)
        ast.NodeVisitor.generic_visit(self, node)

    def visit_ImportFrom(self, node):
        """callback for 'import from' statement"""
        self.imports.extend((node.module, n.name, n.asname, node.level)
                            for n in node.names)
        ast.NodeVisitor.generic_visit(self, node)

def ast_imports(file_path):
    """get list of import from python module
    :return: (list - tuple) (module, name, asname, level)
    """
    with pathlib.Path(file_path).open('r') as fp:
        text = fp.read()
    mod_ast = ast.parse(text, str(file_path))
    finder = _ImportsFinder()
    finder.visit(mod_ast)
    return finder.imports


##########


class PyModule(object):
    """Represents a python module

    :ivar path: (pathlib.Path) module's path
    :ivar fqn: (list - str) full qualified name as list of strings
    """
    def __init__(self, path):
        self.path = pathlib.Path(path)
        assert self.path.suffix == '.py'
        self.fqn = self._get_fqn(self.path)

    def __repr__(self):
        return "<PyModule {}>".format(self.path)

    @staticmethod
    def is_pkg(path):
        """return True if path is a python package"""
        return (path.is_dir() and (path / '__init__.py').exists())

    def pkg_path(self):
        """return pathlib.Path that contains top-most package/module
        Path that is supposed to be part of PYTHONPATH
        """
        return self.path.parents[len(self.fqn)-1]

    @classmethod
    def _get_fqn(cls, path):
        """get full qualified name as list of strings
        :return: (list - str) of path segments from top package to given path
        """
        name_list = [path.stem]
        current_path = path
        # move to parent path until parent path is a python package
        while True:
            parent = current_path.parent
            if parent.name in ('', '.', '..'):
                break
            if not cls.is_pkg(parent):
                break
            name_list.append(parent.name)
            current_path = parent
        return list(reversed(name_list))



class ModuleSet(object):
    """helper to filter import list only from within packages"""
    def __init__(self, path_list):
        self.pkgs = set() # str of fqn (dot separed)
        self.by_path = {} # module by path
        self.by_name = {} # module by name (dot separated)

        for path in path_list:
            # create modules object
            mod = PyModule(path)
            if mod.fqn[-1] == '__init__':
                self.pkgs.add('.'.join(mod.fqn[:-1]))
            self.by_path[path] = mod
            self.by_name['.'.join(mod.fqn)] = mod


    def _get_imported_module(self, module_name):
        """try to get imported module reference by its name"""
        # if imported module on module_set add to list
        imp_mod = self.by_name.get(module_name)
        if imp_mod:
            return imp_mod

        # last part of import section might not be a module
        # remove last section
        no_obj = module_name.rsplit('.', 1)[0]
        imp_mod2 = self.by_name.get(no_obj)
        if imp_mod2:
            return imp_mod2

        # special case for __init__
        if module_name in self.pkgs:
            pkg_name = module_name  + ".__init__"
            return self.by_name[pkg_name]

        if no_obj in self.pkgs:
            pkg_name = no_obj +  ".__init__"
            return self.by_name[pkg_name]


    def get_imports(self, module, return_fqn=False):
        """return set of imported modules that are in self
        :param module: PyModule
        :return: (set - Path)
                 (set - str) if return_fqn == True
        """
        # print('####', module.fqn)
        # print(self.by_name.keys(), '\n\n')
        imports = set()
        raw_imports = ast_imports(module.path)
        for import_entry in raw_imports:
            # join 'from' and 'import' part of import statement
            full = ".".join(s for s in import_entry[:2] if s)

            import_level = import_entry[3]
            if import_level:
                # intra package imports
                intra = '.'.join(module.fqn[:-import_level] + [full])
                imported = self._get_imported_module(intra)
            else:
                imported = self._get_imported_module(full)

            if imported:
                if return_fqn:
                    imports.add('.'.join(imported.fqn))
                else:
                    imports.add(imported.path)
        return imports


    # higher level API
    def mod_imports(self, mod_fqn):
        mod = self.by_name[mod_fqn]
        return self.get_imports(mod, return_fqn=True)
