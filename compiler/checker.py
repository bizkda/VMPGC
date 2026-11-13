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
        # TODO 4: record every struct name (empty field table for now)
        for struct in self.program.structs:
            if struct.name in self.struct_fields:
                self.error(f"duplicate struct '{struct.name}'", struct)
            self.struct_fields[struct.name] = {}
        # TODO 5: now that all names are known, resolve the fields
        for struct in self.program.structs:
            fields = self.struct_fields[struct.name]
            for field in struct.fields:
                if field.name in fields:
                    self.error(f"duplicate field '{field.name}' in struct '{struct.name}'", field)
                fields[field.name] = self.resolve_type(field.type)
        # TODO 6: function signatures
        for function in self.program.functions:
            if function.name in self.functions:
                self.error(f"duplicate function '{function.name}'", function)
            parameter_types = [self.resolve_type(p.type) for p in function.params]
            return_type = self.resolve_type(function.return_type)
            self.functions[function.name] = FunctionSignature(
                function.name, parameter_types, return_type)
        # TODO 7: main must exist, take no parameters and return int
        main_node = next((f for f in self.program.functions if f.name == "main"), None)
        if main_node is None:
            raise ToyError("missing function 'main'", 1, 1)
        main_signature = self.functions["main"]
        if main_signature.parameter_types or main_signature.return_type != INT:
            self.error("'main' must have no parameters and return int", main_node)

        