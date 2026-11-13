from lexer import ToyError
from ast_nodes import *
from toy_types import INT, BOOL, NULL, StructType, ArrayType, is_reference, is_compatible


class FunctionSignature:
    def __init__(self, name, parameter_types, return_type):
        self.name = name
        self.parameter_types = parameter_types
        self.return_type = return_type


class Checker:
    def __init__(self, program):
        self.program = program
        self.struct_fields = {}      # struct name -> {field name: type}
        self.functions = {}          # function name -> FunctionSignature

    def error(self, message, node):
        raise ToyError(message, node.line, node.column)

    # ---------- turning a written type (TypeRef) into a real type ----------
    def resolve_type(self, type_ref):
        """TypeRef('Node', dimension_count=1)  ->  ArrayType(StructType('Node'))"""
        if type_ref.dimension_count > 1:
            self.error("arrays of arrays are not supported", type_ref)

        if type_ref.base_type == "int": 
            base_type = INT
        elif type_ref.base_type == "bool":  
            base_type = BOOL
        elif type_ref.base_type in self.struct_fields:
            base_type = StructType(type_ref.base_type)
        else:
            self.error(f"unknown type '{type_ref.base_type}'", type_ref)

        if type_ref.dimension_count == 1:
            return ArrayType(base_type)
        return base_type
        
    # ---------- pass 1: structs and functions ----------
    def collect_declarations(self):
        # TODO 4: first loop over self.program.structs:
        #         duplicate name -> "duplicate struct 'X'"
        #         register the name with an empty dict so recursive structs work
        #         (struct Node { next: Node; } must not fail)
        # TODO 5: second loop over the structs: fill each field dict
        #         with resolve_type(field.type); duplicate field -> "duplicate field 'x' in struct 'S'"
        # TODO 6: loop over self.program.functions: build a FunctionSignature,
        #         duplicate name -> "duplicate function 'f'"
        # TODO 7: if "main" is missing -> raise ToyError("missing function 'main'", 1, 1)
        #         main must have no parameters and return int
        pass
        while self.program.structs:
            struct = self.program.structs.pop(0)
            if struct.name in self.struct_fields:
                self.error(f"duplicate struct '{struct.name}'", struct)
            self.struct_fields[struct.name] = {}   

        