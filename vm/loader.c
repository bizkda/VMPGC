/* Reading and checking a .tbc file. A file that passes these checks can be run safely:
 * every jump, local, function, type and stack map it mentions exists. */
#include <stdarg.h>
#include <string.h>

#include "vm.h"

typedef struct {
    const uint8_t *data;
    size_t size, position;
    int failed;
} Reader;

static uint64_t read_unsigned(Reader *reader, size_t bytes) {
    if (reader->failed || reader->position + bytes > reader->size) {
        reader->failed = 1;
        return 0;
    }
    uint64_t value = 0;
    for (size_t i = 0; i < bytes; i++)
        value |= (uint64_t)reader->data[reader->position + i] << (8 * i);
    reader->position += bytes;
    return value;
}

static uint8_t  read_u8(Reader *r)  { return (uint8_t)read_unsigned(r, 1); }
static uint16_t read_u16(Reader *r) { return (uint16_t)read_unsigned(r, 2); }
static uint32_t read_u32(Reader *r) { return (uint32_t)read_unsigned(r, 4); }
static uint64_t read_u64(Reader *r) { return read_unsigned(r, 8); }

static void fail(char *error, size_t size, const char *format, ...) {
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(error, size, format, arguments);
    va_end(arguments);
}

void free_program(Program *program) {
    free(program->types);
    if (program->functions) {
        for (uint32_t i = 0; i < program->function_count; i++)
            free(program->functions[i].name);
    }
    free(program->functions);
    free(program->code);
    free(program->maps);
    free(program->map_at_pc);
    memset(program, 0, sizeof *program);
}

static int has_operand_that_is_a_local(uint8_t op) { return op == OP_LOAD_LOCAL || op == OP_STORE_LOCAL; }
static int is_safepoint(uint8_t op) { return op == OP_NEW || op == OP_NEW_ARRAY || op == OP_CALL; }

/* Everything about the content of the file that cannot be checked while reading. */
static int validate(Program *program, char *error, size_t error_size) {
    uint32_t function_count = program->function_count;

    if (function_count == 0) { fail(error, error_size, "no function in the file"); return -1; }
    if (program->main_index >= function_count) { fail(error, error_size, "main is not a function of the file"); return -1; }
    if (program->functions[program->main_index].parameter_count != 0) {
        fail(error, error_size, "main must have no parameters");
        return -1;
    }
    if (program->functions[0].start != 0) { fail(error, error_size, "the first function must start at instruction 0"); return -1; }
    for (uint32_t i = 0; i < function_count; i++) {
        Function *function = &program->functions[i];
        if (function->local_count > MAX_LOCALS || function->parameter_count > function->local_count) {
            fail(error, error_size, "function '%s' has an invalid number of locals", function->name);
            return -1;
        }
        if (function->start >= program->code_count ||
            (i > 0 && function->start <= program->functions[i - 1].start)) {
            fail(error, error_size, "function '%s' has an invalid start", function->name);
            return -1;
        }
    }

    program->map_at_pc = malloc((size_t)program->code_count * sizeof(int32_t));
    if (!program->map_at_pc) { fail(error, error_size, "out of memory"); return -1; }
    for (uint32_t pc = 0; pc < program->code_count; pc++) program->map_at_pc[pc] = -1;

    /* one function after the other, check each instruction in its own function */
    for (uint32_t f = 0; f < function_count; f++) {
        Function *function = &program->functions[f];
        uint32_t end = (f + 1 < function_count) ? program->functions[f + 1].start : program->code_count;
        for (uint32_t pc = function->start; pc < end; pc++) {
            const Instr *instruction = &program->code[pc];
            int32_t arg = instruction->arg;
            if (has_operand_that_is_a_local(instruction->op) && (arg < 0 || (uint32_t)arg >= function->local_count)) {
                fail(error, error_size, "instruction %u: local %d does not exist in '%s'", pc, arg, function->name);
                return -1;
            }
            if ((instruction->op == OP_JMP || instruction->op == OP_JZ) &&
                (arg < 0 || (uint32_t)arg < function->start || (uint32_t)arg >= end)) {
                fail(error, error_size, "instruction %u: jump target %d leaves function '%s'", pc, arg, function->name);
                return -1;
            }
            if (instruction->op == OP_CALL && (arg < 0 || (uint32_t)arg >= function_count)) {
                fail(error, error_size, "instruction %u: call to a function that does not exist", pc);
                return -1;
            }
            if (instruction->op == OP_NEW || instruction->op == OP_NEW_ARRAY) {
                int wanted_struct = instruction->op == OP_NEW;
                if (arg < 1 || (uint32_t)arg > program->type_count) {
                    fail(error, error_size, "instruction %u: type %d does not exist", pc, arg);
                    return -1;
                }
                int is_struct = program->types[arg - 1].kind == KIND_STRUCT;
                if (is_struct != wanted_struct) {
                    fail(error, error_size, "instruction %u: type %d has the wrong kind", pc, arg);
                    return -1;
                }
            }
            if ((instruction->op == OP_GETFIELD || instruction->op == OP_PUTFIELD) && arg < 0) {
                fail(error, error_size, "instruction %u: negative field index", pc);
                return -1;
            }
        }
    }

    /* stack maps: exactly one per safepoint */
    for (uint32_t m = 0; m < program->map_count; m++) {
        StackMap *map = &program->maps[m];
        if (map->pc >= program->code_count || !is_safepoint(program->code[map->pc].op)) {
            fail(error, error_size, "stack map %u is not at an allocation or a call", m);
            return -1;
        }
        if (program->map_at_pc[map->pc] != -1) {
            fail(error, error_size, "two stack maps at instruction %u", map->pc);
            return -1;
        }
        program->map_at_pc[map->pc] = (int32_t)m;
        if (map->depth > MAX_STACK_DEPTH || (map->depth < 64 && (map->stack_mask >> map->depth) != 0)) {
            fail(error, error_size, "stack map %u has an invalid stack part", m);
            return -1;
        }
        /* which function owns this instruction? */
        uint32_t owner = 0;
        while (owner + 1 < function_count && program->functions[owner + 1].start <= map->pc) owner++;
        uint32_t locals = program->functions[owner].local_count;
        if (locals < 64 && (map->locals_mask >> locals) != 0) {
            fail(error, error_size, "stack map %u marks a local that does not exist", m);
            return -1;
        }
    }
    for (uint32_t pc = 0; pc < program->code_count; pc++) {
        if (is_safepoint(program->code[pc].op) && program->map_at_pc[pc] < 0) {
            fail(error, error_size, "instruction %u has no stack map", pc);
            return -1;
        }
    }
    return 0;
}

int load_program(const char *path, Program *program, char *error, size_t error_size) {
    memset(program, 0, sizeof *program);

    FILE *file = fopen(path, "rb");
    if (!file) { fail(error, error_size, "cannot open '%s'", path); return -1; }
    fseek(file, 0, SEEK_END);
    long length = ftell(file);
    fseek(file, 0, SEEK_SET);
    if (length < 0 || length > (1L << 30)) { fclose(file); fail(error, error_size, "bad file size"); return -1; }
    uint8_t *data = malloc((size_t)length + 1);
    if (!data || fread(data, 1, (size_t)length, file) != (size_t)length) {
        free(data);
        fclose(file);
        fail(error, error_size, "cannot read '%s'", path);
        return -1;
    }
    fclose(file);

    Reader reader = { data, (size_t)length, 0, 0 };
    if (length < 4 || memcmp(data, "TBC1", 4) != 0) {
        free(data);
        fail(error, error_size, "not a .tbc file (bad magic number)");
        return -1;
    }
    reader.position = 4;

    /* every count is checked against the bytes that remain, so a damaged file cannot make us allocate a lot */
    uint32_t type_count = read_u32(&reader);
    if (reader.failed || (uint64_t)type_count * 13 > reader.size - reader.position) goto truncated;
    program->type_count = type_count;
    program->types = calloc(type_count ? type_count : 1, sizeof(TypeInfo));
    for (uint32_t i = 0; i < type_count; i++) {
        TypeInfo *type = &program->types[i];
        type->kind = read_u8(&reader);
        type->field_count = read_u32(&reader);
        type->pointer_mask = read_u64(&reader);
        if (type->kind < KIND_STRUCT || type->kind > KIND_ARRAY_REFERENCES || type->field_count > MAX_FIELDS ||
            (type->kind != KIND_STRUCT && (type->field_count != 0 || type->pointer_mask != 0)) ||
            (type->field_count < 64 && (type->pointer_mask >> type->field_count) != 0)) {
            fail(error, error_size, "type %u is invalid", i + 1);
            goto invalid;
        }
    }

    uint32_t function_count = read_u32(&reader);
    if (reader.failed || (uint64_t)function_count * 14 > reader.size - reader.position) goto truncated;
    program->function_count = function_count;
    program->functions = calloc(function_count ? function_count : 1, sizeof(Function));
    for (uint32_t i = 0; i < function_count; i++) {
        Function *function = &program->functions[i];
        function->start = read_u32(&reader);
        function->parameter_count = read_u32(&reader);
        function->local_count = read_u32(&reader);
        uint16_t name_length = read_u16(&reader);
        if (reader.failed || reader.position + name_length > reader.size) goto truncated;
        function->name = malloc((size_t)name_length + 1);
        memcpy(function->name, data + reader.position, name_length);
        function->name[name_length] = '\0';
        reader.position += name_length;
    }
    program->main_index = read_u32(&reader);

    uint32_t code_count = read_u32(&reader);
    if (reader.failed || (uint64_t)code_count * 8 > reader.size - reader.position || code_count == 0) goto truncated;
    program->code_count = code_count;
    program->code = malloc((size_t)code_count * sizeof(Instr));
    for (uint32_t pc = 0; pc < code_count; pc++) {
        uint8_t opcode = read_u8(&reader);
        read_unsigned(&reader, 3);                       /* padding */
        program->code[pc].op = opcode;
        program->code[pc].arg = (int32_t)read_u32(&reader);
        if (opcode < 1 || opcode >= OP_COUNT) {
            fail(error, error_size, "instruction %u: invalid opcode %u", pc, opcode);
            goto invalid;
        }
    }

    uint32_t map_count = read_u32(&reader);
    if (reader.failed || (uint64_t)map_count * 24 > reader.size - reader.position) goto truncated;
    program->map_count = map_count;
    program->maps = calloc(map_count ? map_count : 1, sizeof(StackMap));
    for (uint32_t i = 0; i < map_count; i++) {
        program->maps[i].pc = read_u32(&reader);
        program->maps[i].depth = read_u32(&reader);
        program->maps[i].locals_mask = read_u64(&reader);
        program->maps[i].stack_mask = read_u64(&reader);
    }

    if (reader.failed) goto truncated;
    if (reader.position != reader.size) { fail(error, error_size, "unexpected data at the end of the file"); goto invalid; }
    free(data);
    if (validate(program, error, error_size) != 0) { free_program(program); return -1; }
    return 0;

truncated:
    fail(error, error_size, "the file is truncated or damaged");
invalid:
    free(data);
    free_program(program);
    return -1;
}
