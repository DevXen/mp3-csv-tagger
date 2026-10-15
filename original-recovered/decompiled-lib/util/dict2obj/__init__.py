# uncompyle6 version 3.9.3
# Python bytecode version base 3.7.0 (3394)
# Decompiled from: Python 3.12.3 (main, Aug 31 2026, 10:18:26) [GCC 13.3.0]
# Embedded file name: lib\util\dict2obj\__init__.py


class Dict2Obj(object):
    __doc__ = "\n\n\n    Converts a dictionary into a class so that values can be accessed directly\n    e.g. <object>.<key>.<key>.<key>.\n    Nested dictionaries / values are accessible as well as these are converted\n    at construction of this instance.\n\n    The original dictionary can be copied or this object can be copied as well through\n    the copy_dictionary() and dictionary() methods.\n\n    A get() method is also provided to retrieve a value similar to that of the dict.get() method.\n\n    Reference:\n    https://www.blog.pythonlibrary.org/2014/02/14/python-101-how-to-change-a-dict-into-a-class/\n    "

    def __init__(self, dictionary):
        """Constructor"""
        self._Dict2Obj__dictionary = dictionary
        for key in dictionary:
            v = dictionary[key]
            if isinstance(v, dict):
                v = Dict2Obj(v)
            setattr(self, key, v)

    def to_dict(self):
        result = {}
        for key in self.__dict__:
            if key != "_Dict2Obj__dictionary":
                value = self.__dict__.get(key)
                result[key] = value

        return result

    def __repr__(self):
        """"""
        attrs = str([x for x in self.__dict__])
        return "<Dict2Obj: %s>" % attrs

    def get(self, key):
        if key in self.__dict__:
            return self.__dict__[key]
        return

    def copy_dictionary(self):
        return {**{}, **(self._Dict2Obj__dictionary)}

    def copy(self):
        return Dict2Obj(self.copy_dictionary())

# okay decompiling pyz_out/lib/util/dict2obj/__init__.pyc
