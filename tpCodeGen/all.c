/*
 * TP Compilation - Mini-langage fonctionnel
 * AST -> Environnement -> Inférence de types -> Code à trois adresses
 *
 * Compilation :  gcc tp_compilation.c -o tp
 * Exécution   :  ./tp      (génère intermediate_code.txt)
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>

/* =====================================================================
 * PARTIE 1 : LES TYPES (int, float, bool, fonction, variable de type)
 * ===================================================================== */

typedef enum { T_INT, T_FLOAT, T_BOOL, T_FUN, T_VAR } TypeKind;

typedef struct Type {
    TypeKind kind;
    struct Type *from, *to;   /* pour T_FUN : from -> to              */
    struct Type *link;        /* pour T_VAR : type découvert (ou NULL) */
    int id;                   /* numéro de la variable de type        */
} Type;

static int var_counter = 0;

Type *new_type(TypeKind k) {
    Type *t = calloc(1, sizeof(Type));
    t->kind = k;
    return t;
}

/* Variable de type = "type pas encore connu" (ex: paramètre d'une fun) */
Type *new_var(void) {
    Type *t = new_type(T_VAR);
    t->id = ++var_counter;
    return t;
}

Type *fun_type(Type *from, Type *to) {
    Type *t = new_type(T_FUN);
    t->from = from;
    t->to = to;
    return t;
}

/* Suit les liens d'une variable de type jusqu'au vrai type */
Type *prune(Type *t) {
    while (t->kind == T_VAR && t->link) t = t->link;
    return t;
}

/* Vérifie qu'une variable v n'apparaît pas dans t (évite les types infinis) */
int occurs(Type *v, Type *t) {
    t = prune(t);
    if (t == v) return 1;
    if (t->kind == T_FUN) return occurs(v, t->from) || occurs(v, t->to);
    return 0;
}

/* UNIFICATION : essaie de rendre a et b identiques. Retourne 1 si OK. */
int unify(Type *a, Type *b) {
    a = prune(a);
    b = prune(b);
    if (a == b) return 1;
    if (a->kind == T_VAR) {
        if (occurs(a, b)) return 0;
        a->link = b;               /* a devient b */
        return 1;
    }
    if (b->kind == T_VAR) return unify(b, a);
    if (a->kind != b->kind) return 0;
    if (a->kind == T_FUN)
        return unify(a->from, b->from) && unify(a->to, b->to);
    return 1;                      /* int/int, float/float, bool/bool */
}

/* Convertit un type en texte (pour l'affichage) */
void type_str(Type *t, char *out) {
    char tmp[32];
    t = prune(t);
    switch (t->kind) {
        case T_INT:   strcat(out, "int");   break;
        case T_FLOAT: strcat(out, "float"); break;
        case T_BOOL:  strcat(out, "bool");  break;
        case T_VAR:   sprintf(tmp, "'t%d", t->id); strcat(out, tmp); break;
        case T_FUN:
            if (prune(t->from)->kind == T_FUN) {
                strcat(out, "("); type_str(t->from, out); strcat(out, ")");
            } else type_str(t->from, out);
            strcat(out, " -> ");
            type_str(t->to, out);
            break;
    }
}

const char *ts(Type *t) {
    static char bufs[4][256];
    static int i = 0;
    char *b = bufs[i];
    i = (i + 1) % 4;
    b[0] = 0;
    type_str(t, b);
    return b;
}

void type_error(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    printf("ERREUR DE TYPE : ");
    vprintf(fmt, ap);
    printf("\n");
    va_end(ap);
    exit(1);
}

/* =====================================================================
 * PARTIE 2 : L'AST (arbre syntaxique abstrait)
 * ===================================================================== */

typedef enum {
    E_INT, E_FLOAT, E_BOOL, E_IDENT,
    E_BINOP,   /* a op b   (+ - * / < > <= >= == !=)  */
    E_APP,     /* a b      (application de fonction)  */
    E_IF,      /* if a then b else c                  */
    E_FUN,     /* fun name -> a                       */
    E_LETIN    /* let name [: annot] = a in b         */
} ExprKind;

typedef struct Expr {
    ExprKind kind;
    int ival;            /* INT ou BOOL (0/1)                      */
    double fval;         /* FLOAT                                  */
    char name[32];       /* IDENT, opérateur, paramètre, variable  */
    Type *annot;         /* annotation de type (LETIN), ou NULL    */
    struct Expr *a, *b, *c;   /* sous-expressions                  */
} Expr;

Expr *new_expr(ExprKind k) {
    Expr *e = calloc(1, sizeof(Expr));
    e->kind = k;
    return e;
}

/* ---- Fonctions "constructeurs" pour construire l'arbre facilement ---- */
Expr *e_int(int v)      { Expr *e = new_expr(E_INT);   e->ival = v; return e; }
Expr *e_float(double v) { Expr *e = new_expr(E_FLOAT); e->fval = v; return e; }
Expr *e_bool(int v)     { Expr *e = new_expr(E_BOOL);  e->ival = v; return e; }
Expr *e_ident(const char *n) {
    Expr *e = new_expr(E_IDENT); strcpy(e->name, n); return e;
}
Expr *e_binop(const char *op, Expr *l, Expr *r) {
    Expr *e = new_expr(E_BINOP); strcpy(e->name, op); e->a = l; e->b = r; return e;
}
Expr *e_app(Expr *f, Expr *arg) {
    Expr *e = new_expr(E_APP); e->a = f; e->b = arg; return e;
}
Expr *e_if(Expr *c, Expr *t, Expr *f) {
    Expr *e = new_expr(E_IF); e->a = c; e->b = t; e->c = f; return e;
}
Expr *e_fun(const char *param, Expr *body) {
    Expr *e = new_expr(E_FUN); strcpy(e->name, param); e->a = body; return e;
}
Expr *e_letin(const char *n, Type *annot, Expr *val, Expr *body) {
    Expr *e = new_expr(E_LETIN);
    strcpy(e->name, n); e->annot = annot; e->a = val; e->b = body;
    return e;
}

/* ---- Déclarations ---- */
typedef enum {
    D_LET_TYPED,   /* let x : T = e            */
    D_LET,         /* let x = e                */
    D_LET_REC,     /* let rec f (p : T1) : T2 = e */
    D_EXPR         /* e                        */
} DeclKind;

typedef struct {
    DeclKind kind;
    char name[32];     /* nom de la variable / fonction */
    char param[32];    /* paramètre (let rec)           */
    Type *ptype;       /* type du paramètre (let rec)   */
    Type *type;        /* annotation de type / type de retour */
    Expr *expr;
} Decl;

/* Un programme = une liste de déclarations */
Decl *program[100];
int nb_decl = 0;

void add_decl(Decl *d) { program[nb_decl++] = d; }

Decl *d_let_typed(const char *n, Type *t, Expr *e) {
    Decl *d = calloc(1, sizeof(Decl));
    d->kind = D_LET_TYPED; strcpy(d->name, n); d->type = t; d->expr = e;
    return d;
}
Decl *d_let(const char *n, Expr *e) {
    Decl *d = calloc(1, sizeof(Decl));
    d->kind = D_LET; strcpy(d->name, n); d->expr = e;
    return d;
}
Decl *d_let_rec(const char *f, const char *p, Type *pt, Type *rt, Expr *e) {
    Decl *d = calloc(1, sizeof(Decl));
    d->kind = D_LET_REC; strcpy(d->name, f); strcpy(d->param, p);
    d->ptype = pt; d->type = rt; d->expr = e;
    return d;
}
Decl *d_expr(Expr *e) {
    Decl *d = calloc(1, sizeof(Decl));
    d->kind = D_EXPR; d->expr = e;
    return d;
}

/* =====================================================================
 * PARTIE 3 : AFFICHAGE DE L'AST
 * ===================================================================== */

void indent(int n) { for (int i = 0; i < n; i++) printf("  "); }

void print_expr(Expr *e, int d) {
    indent(d);
    switch (e->kind) {
        case E_INT:   printf("INT %d\n", e->ival); break;
        case E_FLOAT: printf("FLOAT %g\n", e->fval); break;
        case E_BOOL:  printf("BOOL %s\n", e->ival ? "true" : "false"); break;
        case E_IDENT: printf("IDENT %s\n", e->name); break;
        case E_BINOP:
            printf("BINOP '%s'\n", e->name);
            print_expr(e->a, d + 1);
            print_expr(e->b, d + 1);
            break;
        case E_APP:
            printf("APP\n");
            print_expr(e->a, d + 1);
            print_expr(e->b, d + 1);
            break;
        case E_IF:
            printf("IF\n");
            indent(d + 1); printf("cond:\n"); print_expr(e->a, d + 2);
            indent(d + 1); printf("then:\n"); print_expr(e->b, d + 2);
            indent(d + 1); printf("else:\n"); print_expr(e->c, d + 2);
            break;
        case E_FUN:
            printf("FUN param=%s\n", e->name);
            print_expr(e->a, d + 1);
            break;
        case E_LETIN:
            printf("LET_IN %s", e->name);
            if (e->annot) printf(" : %s", ts(e->annot));
            printf("\n");
            indent(d + 1); printf("valeur:\n"); print_expr(e->a, d + 2);
            indent(d + 1); printf("corps:\n");  print_expr(e->b, d + 2);
            break;
    }
}

void print_program(void) {
    for (int i = 0; i < nb_decl; i++) {
        Decl *d = program[i];
        printf("Declaration %d : ", i + 1);
        switch (d->kind) {
            case D_LET_TYPED: printf("let %s : %s\n", d->name, ts(d->type)); break;
            case D_LET:       printf("let %s\n", d->name); break;
            case D_LET_REC:   printf("let rec %s (%s : %s) : %s\n",
                                     d->name, d->param, ts(d->ptype), ts(d->type)); break;
            case D_EXPR:      printf("expression\n"); break;
        }
        print_expr(d->expr, 1);
    }
}

/* =====================================================================
 * PARTIE 4 : L'ENVIRONNEMENT (liste chaînée nom -> type)
 * ===================================================================== */

typedef struct Env {
    char name[32];
    Type *type;
    struct Env *next;
} Env;

/* Ajoute en tête (on ne modifie pas l'ancien env : pratique pour les portées) */
Env *env_add(Env *env, const char *name, Type *type) {
    Env *n = malloc(sizeof(Env));
    strcpy(n->name, name);
    n->type = type;
    n->next = env;
    return n;
}

Type *env_find(Env *env, const char *name) {
    for (; env; env = env->next)
        if (strcmp(env->name, name) == 0) return env->type;
    return NULL;
}

void print_env(Env *env) {
    for (; env; env = env->next)
        printf("  %-10s : %s\n", env->name, ts(env->type));
}

/* =====================================================================
 * PARTIE 5 : INFÉRENCE ET VÉRIFICATION DES TYPES
 * ===================================================================== */

Type *infer(Expr *e, Env *env) {
    switch (e->kind) {
        case E_INT:   return new_type(T_INT);
        case E_FLOAT: return new_type(T_FLOAT);
        case E_BOOL:  return new_type(T_BOOL);

        case E_IDENT: {
            Type *t = env_find(env, e->name);
            if (!t) type_error("identificateur '%s' non declare", e->name);
            return t;
        }

        case E_BINOP: {
            Type *l = infer(e->a, env);
            Type *r = infer(e->b, env);
            if (!unify(l, r))
                type_error("operandes de '%s' de types differents (%s et %s)",
                           e->name, ts(l), ts(r));
            Type *t = prune(l);
            int is_eq  = (!strcmp(e->name, "==") || !strcmp(e->name, "!="));
            int is_cmp = (e->name[0] == '<' || e->name[0] == '>' || is_eq);
            if (t->kind == T_FUN)
                type_error("operateur '%s' impossible sur une fonction", e->name);
            if (t->kind == T_BOOL && !is_eq)
                type_error("operateur '%s' impossible sur des bool", e->name);
            return is_cmp ? new_type(T_BOOL) : l;
        }

        case E_APP: {
            Type *tf  = infer(e->a, env);
            Type *arg = infer(e->b, env);
            Type *res = new_var();
            if (!unify(tf, fun_type(arg, res)))
                type_error("application invalide : fonction de type %s appliquee a %s",
                           ts(tf), ts(arg));
            return res;
        }

        case E_IF: {
            Type *c = infer(e->a, env);
            if (!unify(c, new_type(T_BOOL)))
                type_error("la condition du if doit etre bool (trouve %s)", ts(c));
            Type *t1 = infer(e->b, env);
            Type *t2 = infer(e->c, env);
            if (!unify(t1, t2))
                type_error("then (%s) et else (%s) ont des types differents",
                           ts(t1), ts(t2));
            return t1;
        }

        case E_FUN: {
            Type *pv = new_var();                       /* type inconnu du param */
            Type *body = infer(e->a, env_add(env, e->name, pv));
            return fun_type(pv, body);
        }

        case E_LETIN: {
            Type *tv = infer(e->a, env);
            if (e->annot && !unify(tv, e->annot))
                type_error("let %s : %s mais la valeur est de type %s",
                           e->name, ts(e->annot), ts(tv));
            return infer(e->b, env_add(env, e->name, tv));
        }
    }
    return NULL;
}

/* Vérifie une déclaration et met à jour l'environnement global */
Env *check_decl(Decl *d, Env *env) {
    switch (d->kind) {
        case D_LET_TYPED: {
            Type *t = infer(d->expr, env);
            if (!unify(t, d->type))
                type_error("%s declare %s mais valeur de type %s",
                           d->name, ts(d->type), ts(t));
            env = env_add(env, d->name, d->type);
            printf("  %s : %s\n", d->name, ts(d->type));
            break;
        }
        case D_LET: {
            Type *t = infer(d->expr, env);
            env = env_add(env, d->name, t);
            printf("  %s : %s\n", d->name, ts(t));
            break;
        }
        case D_LET_REC: {
            Type *ft = fun_type(d->ptype, d->type);
            /* f est ajoutée AVANT de vérifier le corps (pour l'appel récursif) */
            Env *env2 = env_add(env, d->name, ft);
            Env *env3 = env_add(env2, d->param, d->ptype);
            Type *body = infer(d->expr, env3);
            if (!unify(body, d->type))
                type_error("corps de %s de type %s, attendu %s",
                           d->name, ts(body), ts(d->type));
            env = env2;
            printf("  %s : %s\n", d->name, ts(ft));
            break;
        }
        case D_EXPR: {
            Type *t = infer(d->expr, env);
            printf("  (expression) : %s\n", ts(t));
            break;
        }
    }
    return env;
}

/* =====================================================================
 * PARTIE 6 : GÉNÉRATION DU CODE À TROIS ADRESSES
 * ===================================================================== */

typedef struct { char text[8192]; } Buf;

Buf main_code, func_code;       /* code principal / code des fonctions */
Buf *cur = &main_code;          /* buffer dans lequel on écrit         */

int temp_count = 0, label_count = 0, anon_count = 0;

/* Ajoute une instruction (indentée) */
void emit(const char *fmt, ...) {
    char line[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    strcat(cur->text, "    ");
    strcat(cur->text, line);
    strcat(cur->text, "\n");
}

/* Ajoute une étiquette / titre (non indenté) */
void emit_label(const char *fmt, ...) {
    char line[256];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    strcat(cur->text, line);
    strcat(cur->text, "\n");
}

void new_temp(char *out)  { sprintf(out, "t%d", ++temp_count); }
void new_label(char *out) { sprintf(out, "L%d", ++label_count); }

void gen_expr(Expr *e, char *res);

/* Génère le code d'une fonction (anonyme ou nommée) dans func_code */
void gen_function(const char *fname, const char *param, Expr *body) {
    Buf *local = calloc(1, sizeof(Buf));   /* on écrit dans un buffer à part */
    Buf *saved = cur;                      /* (utile si fonctions imbriquées) */
    cur = local;

    char r[64];
    emit_label("FUNC %s(%s):", fname, param);
    gen_expr(body, r);
    emit("return %s", r);
    emit_label("END %s\n", fname);

    cur = saved;
    strcat(func_code.text, local->text);
    free(local);
}

/* Génère le code de e ; res reçoit le nom du résultat (temporaire/constante) */
void gen_expr(Expr *e, char *res) {
    char a[64], b[64], t[64];
    switch (e->kind) {
        case E_INT:   sprintf(res, "%d", e->ival); break;
        case E_FLOAT: sprintf(res, "%.2f", e->fval); break;
        case E_BOOL:  strcpy(res, e->ival ? "true" : "false"); break;
        case E_IDENT: strcpy(res, e->name); break;

        case E_BINOP:
            gen_expr(e->a, a);
            gen_expr(e->b, b);
            new_temp(t);
            emit("%s = %s %s %s", t, a, e->name, b);
            strcpy(res, t);
            break;

        case E_APP:                         /* f x  ->  param x ; t = call f, 1 */
            gen_expr(e->a, a);
            gen_expr(e->b, b);
            new_temp(t);
            emit("param %s", b);
            emit("%s = call %s, 1", t, a);
            strcpy(res, t);
            break;

        case E_IF: {
            char Lelse[16], Lend[16];
            new_temp(t);                    /* t contiendra le résultat */
            new_label(Lelse);
            new_label(Lend);
            gen_expr(e->a, a);
            emit("ifFalse %s goto %s", a, Lelse);
            gen_expr(e->b, b);
            emit("%s = %s", t, b);
            emit("goto %s", Lend);
            emit_label("%s:", Lelse);
            gen_expr(e->c, b);
            emit("%s = %s", t, b);
            emit_label("%s:", Lend);
            strcpy(res, t);
            break;
        }

        case E_FUN: {                       /* fonction anonyme -> anonN */
            sprintf(t, "anon%d", ++anon_count);
            gen_function(t, e->name, e->a);
            strcpy(res, t);                 /* la valeur est le nom de la fonction */
            break;
        }

        case E_LETIN:
            gen_expr(e->a, a);
            emit("%s = %s", e->name, a);
            gen_expr(e->b, res);
            break;
    }
}

void gen_decl(Decl *d) {
    char r[64];
    switch (d->kind) {
        case D_LET_TYPED:
        case D_LET:
            gen_expr(d->expr, r);
            emit("%s = %s", d->name, r);
            break;
        case D_LET_REC:
            gen_function(d->name, d->param, d->expr);
            break;
        case D_EXPR:
            gen_expr(d->expr, r);
            emit("# resultat : %s", r);
            break;
    }
}

/* =====================================================================
 * PARTIE 7 : PROGRAMME PRINCIPAL (construction de l'exemple)
 * ===================================================================== */

#define INT   new_type(T_INT)
#define FLOAT new_type(T_FLOAT)

int main(void) {
    /* let x : int = 5 */
    add_decl(d_let_typed("x", INT, e_int(5)));

    /* let y = x + 3 */
    add_decl(d_let("y", e_binop("+", e_ident("x"), e_int(3))));

    /* let r : float = 2.5 * 2.0 */
    add_decl(d_let_typed("r", FLOAT, e_binop("*", e_float(2.5), e_float(2.0))));

    /* let rec fact (n : int) : int =
           if n <= 1 then 1 else n * fact (n - 1) */
    add_decl(d_let_rec("fact", "n", INT, INT,
        e_if(e_binop("<=", e_ident("n"), e_int(1)),
             e_int(1),
             e_binop("*", e_ident("n"),
                     e_app(e_ident("fact"),
                           e_binop("-", e_ident("n"), e_int(1)))))));

    /* let inc = fun a -> a + 1 */
    add_decl(d_let("inc", e_fun("a", e_binop("+", e_ident("a"), e_int(1)))));

    /* let z = inc 4 */
    add_decl(d_let("z", e_app(e_ident("inc"), e_int(4))));

    /* let w = fact 5 */
    add_decl(d_let("w", e_app(e_ident("fact"), e_int(5))));

    /* let v = let u = 2 in u * u + 1 */
    add_decl(d_let("v",
        e_letin("u", NULL, e_int(2),
                e_binop("+", e_binop("*", e_ident("u"), e_ident("u")), e_int(1)))));

    /* if x > 3 then y else 0 */
    add_decl(d_expr(e_if(e_binop(">", e_ident("x"), e_int(3)),
                         e_ident("y"), e_int(0))));

    /* --- 1 et 2 : AST --- */
    printf("===== 1-2. ARBRE SYNTAXIQUE ABSTRAIT =====\n");
    print_program();

    /* --- 3, 4, 5 : environnement + types --- */
    printf("\n===== 3-5. INFERENCE DES TYPES =====\n");
    Env *env = NULL;
    for (int i = 0; i < nb_decl; i++)
        env = check_decl(program[i], env);

    printf("\n===== ENVIRONNEMENT FINAL =====\n");
    print_env(env);

    /* --- 6, 7, 8, 9 : code intermédiaire --- */
    for (int i = 0; i < nb_decl; i++)
        gen_decl(program[i]);

    printf("\n===== 6-9. CODE A TROIS ADRESSES =====\n");
    printf("# ---- Fonctions ----\n%s", func_code.text);
    printf("# ---- Programme principal ----\n%s", main_code.text);

    /* --- 10 : sauvegarde dans un fichier --- */
    FILE *f = fopen("intermediate_code.txt", "w");
    if (!f) { printf("Impossible de creer le fichier\n"); return 1; }
    fprintf(f, "# ---- Fonctions ----\n%s", func_code.text);
    fprintf(f, "# ---- Programme principal ----\n%s", main_code.text);
    fclose(f);
    printf("\nCode sauvegarde dans intermediate_code.txt\n");

    return 0;
}
