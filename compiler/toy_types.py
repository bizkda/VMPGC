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
    """True for struct and array types, and for the type of `null`
    (all of them are values the GC has to look at)."""
    return type_ == NULL or isinstance(type_, (StructType, ArrayType))


def is_compatible(source, target) -> bool:
    """Can a value of type `source` be used where `target` is expected?
    Equal types, or `null` for any reference type."""
    return source == target or (source == NULL and is_reference(target))


if __name__ == "__main__":
    node = StructType("Node")
    print(is_reference(INT), is_reference(node), is_reference(ArrayType(INT)))
    print(is_compatible(INT, INT), is_compatible(INT, BOOL))
    print(is_compatible(NULL, node), is_compatible(NULL, INT))
    print(is_compatible(node, StructType("Other")))
    print(ArrayType(node))
    print(is_reference(NULL), is_compatible(NULL, NULL), is_compatible(node, NULL))
    # rule T8 (== and !=) on references: null == p, p == null, null == null
    def comparable(a, b):
        return is_reference(a) and is_reference(b) and (is_compatible(a, b) or is_compatible(b, a))
    print(comparable(NULL, node), comparable(node, NULL), comparable(NULL, NULL),
          comparable(node, StructType("Other")), comparable(INT, NULL))
