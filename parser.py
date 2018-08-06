import ply
import ply.lex
import ply.yacc
import ast
from typing import Any

reserved = {
    'modifies': 'MODIFIES',
    'sort': 'SORT',
    'mutable': 'MUTABLE',
    'immutable': 'IMMUTABLE',
    'relation': 'RELATION',
    'constant': 'CONSTANT',
    'init': 'INIT',
    'transition': 'TRANSITION',
    'invariant': 'INVARIANT',
    'axiom': 'AXIOM',
    'old': 'OLD',
    'modifies': 'MODIFIES',
    'forall': 'FORALL',
    'exists': 'EXISTS',
    'true': 'TRUE',
    'false': 'FALSE'
}

tokens = [
    'LPAREN',
    'RPAREN',
    'LBRACKET',
    'RBRACKET',
    'DOT',
    'COLON',
    'BANG',
    'IFF',
    'IMPLIES',
    'PIPE',
    'EQUAL',
    'NOTEQ',
    'COMMA',
    'AMPERSAND',
    'ID'
] + list(reserved.values())


def t_ID(t):
    r'[a-zA-Z_][a-zA-Z_0-9]*'
    t.type = reserved.get(t.value,'ID')    # Check for reserved words
    return t

t_LPAREN = r'\('
t_RPAREN = r'\)'
t_LBRACKET = r'\['
t_RBRACKET = r'\]'
t_DOT = r'\.'
t_COLON = r':'
t_BANG = r'\!'
t_IMPLIES = r'->'
t_IFF = r'<->'
t_PIPE = r'\|'
t_EQUAL = r'='
t_NOTEQ = r'\!='
t_COMMA = r','
t_AMPERSAND = r'&'
t_ignore_COMMENT = r'\#.*'

# Define a rule so we can track line numbers
def t_newline(t):
    r'\n+'
    t.lexer.lineno += len(t.value)
    t.lexer.bol = t.lexpos

t_ignore  = ' \t'

def t_error(t):
    pass

lexer = ply.lex.lex()


precedence = (
    ('right','DOT'),
    ('nonassoc','IFF'),
    ('right','IMPLIES'),
    ('left','PIPE'),
    ('left','AMPERSAND'),
    ('nonassoc', 'EQUAL', 'NOTEQ'),
    ('right','BANG')
)

def p_program(p): # type: (Any) -> None
    'program : decls'
    p[0] = ast.Program(p[1])

def p_decls_empty(p): # type: (Any) -> None
    'decls : empty'
    p[0] = []

def p_decls_decl(p): # type: (Any) -> None
    'decls : decls decl'
    p[0] = p[1] + [p[2]]

def p_id(p): # type: (Any) -> None
    'id : ID'
    p[0] = p.slice[1]

def p_decl_sort(p): # type: (Any) -> None
    'decl : SORT id'
    p[0] = ast.SortDecl(p.slice[1], p[2].value)

def p_decl_mut(p): # type: (Any) -> None
    '''mut : MUTABLE
           | IMMUTABLE'''
    p[0] = p[1] == 'mutable'

def p_arity_empty(p): # type: (Any) -> None
    'arity : empty'
    p[0] = []

def p_arity_nonempty(p): # type: (Any) -> None
    'arity : arity_nonempty'
    p[0] = p[1]

def p_arity_nonempty_one(p): # type: (Any) -> None
    'arity_nonempty : sort'
    p[0] = [p[1]]

def p_arity_nonempty_more(p): # type: (Any) -> None
    'arity_nonempty : arity_nonempty COMMA sort'
    p[0] = p[1] + [p[3]]

def p_sort(p): # type: (Any) -> None
    'sort : id'
    p[0] = ast.UninterpretedSort(p[1], p[1].value)

def p_decl_relation(p): # type: (Any) -> None
    'decl : mut RELATION id LPAREN arity RPAREN'
    p[0] = ast.RelationDecl(p.slice[2], p[3].value, p[5], p[1])

def p_decl_constant(p): # type: (Any) -> None
    'decl : mut CONSTANT id COLON sort'
    p[0] = ast.ConstantDecl(p.slice[2], p[3].value, p[5], p[1])

def p_decl_axiom(p): # type: (Any) -> None
    'decl : AXIOM opt_name expr'
    p[0] = ast.AxiomDecl(p.slice[1], p[2], p[3])

def p_decl_init(p): # type: (Any) -> None
    'decl : INIT opt_name expr'
    p[0] = ast.InitDecl(p.slice[1], p[2], p[3])

def p_decl_invariant(p): # type: (Any) -> None
    'decl : INVARIANT opt_name expr'
    p[0] = ast.InvariantDecl(p.slice[1], p[2], p[3])

def p_opt_name_none(p): # type: (Any) -> None
    'opt_name : empty'
    pass

def p_opt_name_some(p): # type: (Any) -> None
    'opt_name : LBRACKET id RBRACKET'
    p[0] = p[2].value

def p_quant(p): # type: (Any) -> None
    '''quant : FORALL
             | EXISTS'''
    p[0] = p.slice[1]

def p_expr_quantifier(p): # type: (Any) -> None
    'expr : quant sortedvars DOT expr'
    p[0] = ast.QuantifierExpr(p[1], p[1].type, p[2], p[4])

def p_sortedvar(p): # type: (Any) -> None
    'sortedvar : id COLON sort'
    p[0] = ast.SortedVar(p[1], p[1].value, p[3])

def p_sortedvar_nosort(p): # type: (Any) -> None
    'sortedvar : id'
    p[0] = ast.SortedVar(p[1], p[1].value, None)

def p_sortedvars0_one(p): # type: (Any) -> None
    'sortedvars0 : sortedvars'
    p[0] = p[1]

def p_sortedvars0_zero(p): # type: (Any) -> None
    'sortedvars0 : empty'
    p[0] = []

def p_sortedvars_one(p): # type: (Any) -> None
    'sortedvars : sortedvar'
    p[0] = [p[1]]

def p_sortedvars_more(p): # type: (Any) -> None
    'sortedvars : sortedvars COMMA sortedvar'
    p[0] = p[1] + [p[3]]

def p_expr_true(p): # type: (Any) -> None
    'expr : TRUE'
    p[0] = ast.Bool(p.slice[1], True)

def p_expr_false(p): # type: (Any) -> None
    'expr : FALSE'
    p[0] = ast.Bool(p.slice[1], False)

def p_expr_not(p): # type: (Any) -> None
    'expr : BANG expr'
    p[0] = ast.UnaryExpr(p.slice[1], 'NOT', p[2])

def p_expr_app(p): # type: (Any) -> None
    'expr : id LPAREN args RPAREN'
    p[0] = ast.AppExpr(p[1], p[1].value, p[3])

def p_expr_and(p): # type: (Any) -> None
    'expr : expr AMPERSAND expr'
    p[0] = ast.BinaryExpr(p.slice[2], 'AND', p[1], p[3])

def p_expr_or(p): # type: (Any) -> None
    'expr : expr PIPE expr'
    p[0] = ast.BinaryExpr(p.slice[2], 'OR', p[1], p[3])

def p_expr_iff(p): # type: (Any) -> None
    'expr : expr IFF expr'
    p[0] = ast.BinaryExpr(p.slice[2], 'IFF', p[1], p[3])
    
def p_expr_implies(p): # type: (Any) -> None
    'expr : expr IMPLIES expr'
    p[0] = ast.BinaryExpr(p.slice[2], 'IMPLIES', p[1], p[3])

def p_expr_eq(p): # type: (Any) -> None
    'expr : expr EQUAL expr'
    p[0] = ast.BinaryExpr(p.slice[2], 'EQUAL', p[1], p[3])

def p_expr_noteq(p): # type: (Any) -> None
    'expr : expr NOTEQ expr'
    p[0] = ast.BinaryExpr(p.slice[2], 'NOTEQ', p[1], p[3])


def p_expr_old(p): # type: (Any) -> None
    'expr : OLD LPAREN expr RPAREN'
    p[0] = ast.UnaryExpr(p.slice[1], 'OLD', p[3])

def p_args_empty(p): # type: (Any) -> None
    'args : empty'
    p[0] = []

def p_args_at_least_one(p): # type: (Any) -> None
    'args : args1'
    p[0] = p[1]

def p_args1_one(p): # type: (Any) -> None
    'args1 : expr'
    p[0] = [p[1]]

def p_args1_more(p): # type: (Any) -> None
    'args1 : args1 COMMA expr'
    p[0] = p[1] + [p[3]]

def p_expr_id(p): # type: (Any) -> None
    'expr : id'
    p[0] = ast.Id(p[1], p[1].value)

def p_expr_paren(p): # type: (Any) -> None
    'expr : LPAREN expr RPAREN'
    p[0] = p[2]

def p_params(p): # type: (Any) -> None
    'params : sortedvars0'
    p[0] = p[1]

def p_mod(p): # type: (Any) -> None
    'mod : id'
    p[0] = ast.ModifiesClause(p[1], p[1].value)

def p_modlist_one(p): # type: (Any) -> None
    'modlist : mod'
    p[0] = [p[1]]

def p_modlist_more(p): # type: (Any) -> None
    'modlist : modlist COMMA mod'
    p[0] = p[1] + [p[3]]

def p_mods(p): # type: (Any) -> None
    'mods : MODIFIES modlist'
    p[0] = p[2]

def p_decl_transition(p): # type: (Any) -> None
    'decl : TRANSITION id LPAREN params RPAREN mods expr'
    p[0] = ast.TransitionDecl(p[2], p[2].value, p[4], p[6], p[7])

def p_empty(p): # type: (Any) -> None
    'empty :'
    pass

def p_error(t):
    print '%s:%s syntax error at %s' % (t.lineno, t.lexpos - t.lexer.bol, t.value)

parser = ply.yacc.yacc()
