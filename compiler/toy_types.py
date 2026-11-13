from dataclasses import dataclass


@dataclass(frozen=True)
class IntType:
    def __str__(self):
        return "int"


@dataclass(frozen=True)
class BoolType:
    def __str__(self):
        return "bool"


@dataclass(frozen=True)
class NullType:
    """The type of the literal `null`."""
    def __str__(self):
        return "null"


@dataclass(frozen=True)
class StructType:
    name: str

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class ArrayType:
    element: object      # IntType, BoolType or StructType (no arrays of arrays)

    def __str__(self):
        return f"{self.element}[]"


INT, BOOL, NULL = IntType(), BoolType(), NullType()


def is_reference(type_) -> bool:
    """True for struct and array types (the values the GC must follow)."""
    if(type_ is NULL or isinstance(type_, (StructType, ArrayType))):
        return True
    return False


def is_compatible(source, target) -> bool:
    """Can a value of type `source` be used where `target` is expected?
    (rule from the specifications: equal types, or null for a reference type)"""
    if source == target:
        return True
    if source is NULL and is_reference(target):
        return True
    return False