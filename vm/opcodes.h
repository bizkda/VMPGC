#ifndef OPCODES_H
#define OPCODES_H

/* Generated from OPCODE_LIST in compiler/backend/bytecode.py. Keep the same order. */
enum Opcode {
    OP_PUSH_INT = 1,
    OP_PUSH_NULL = 2,
    OP_POP = 3,
    OP_LOAD_LOCAL = 4,
    OP_STORE_LOCAL = 5,
    OP_ADD = 6,
    OP_SUB = 7,
    OP_MUL = 8,
    OP_DIV = 9,
    OP_MOD = 10,
    OP_NEG = 11,
    OP_NOT = 12,
    OP_EQ = 13,
    OP_NE = 14,
    OP_LT = 15,
    OP_LE = 16,
    OP_GT = 17,
    OP_GE = 18,
    OP_JMP = 19,
    OP_JZ = 20,
    OP_CALL = 21,
    OP_RET = 22,
    OP_NEW = 23,
    OP_NEW_ARRAY = 24,
    OP_GETFIELD = 25,
    OP_PUTFIELD = 26,
    OP_ALOAD = 27,
    OP_ASTORE = 28,
    OP_PRINT_INT = 29,
    OP_PRINT_BOOL = 30,
    OP_COUNT            /* one more than the last opcode */
};

#endif
