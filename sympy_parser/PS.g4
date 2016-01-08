grammar PS;

options {
    language=Python2;
}

WS: [ \t\r\n]+ -> skip;

ADD: '+';
SUB: '-';
MUL: '*';
DIV: '/';

EXP: '**';

L_PAREN: '(';
R_PAREN: ')';
L_BRACE: '{';
R_BRACE: '}';
L_BRACKET: '[';
R_BRACKET: ']';

BAR: '|';

FUNC_INT:  '\\int';
FUNC_SUM:  '\\sum';
FUNC_PROD: '\\prod';

FUNC_LOG:  '\\log';
FUNC_LN:   '\\ln';
FUNC_SIN:  '\\sin';
FUNC_COS:  '\\cos';
FUNC_TAN:  '\\tan';
FUNC_CSC:  '\\csc';
FUNC_SEC:  '\\sec';
FUNC_COT:  '\\cot';

FUNC_ARCSIN: '\\arcsin';
FUNC_ARCCOS: '\\arccos';
FUNC_ARCTAN: '\\arctan';
FUNC_ARCCSC: '\\arccsc';
FUNC_ARCSEC: '\\arcsec';
FUNC_ARCCOT: '\\arccot';

FUNC_SQRT: '\\sqrt';

CMD_TIMES: '\\times';
CMD_CDOT:  '\\cdot';
CMD_DIV:   '\\div';
CMD_FRAC:  '\\frac';

UNDERSCORE: '_';
CARET: '^';

LETTER: [a-zA-Z];
fragment DIGIT: [0-9];
NUMBER:
    DIGIT+
    | DIGIT* '.' DIGIT+;

EQUAL: '=';
LT: '<';
LTE: '\\leq';
GT: '>';
GTE: '\\geq';

BANG: '!';

SYMBOL: '\\' [a-zA-Z]+;

math: relation;

relation:
    relation (EQUAL | LT | LTE | GT | GTE) relation
    | expr;

equality:
    expr EQUAL expr;

expr: additive;

additive:
    additive ADD additive
    | additive SUB additive
    | mp;

// mult part
mp:
    mp (MUL | CMD_TIMES | CMD_CDOT) mp
    | mp (DIV | CMD_DIV) mp
    | unary;

unary:
    (ADD | SUB) unary
    | postfix+;

postfix: exp BANG?;

exp:
    exp EXP exp
    | exp CARET L_BRACE expr R_BRACE subexpr?
    | comp;

comp:
    group
    | abs_group
    | atom
    | frac
    | func;

group:
    L_PAREN expr R_PAREN 
    | L_BRACKET expr R_BRACKET;

abs_group: BAR expr BAR;

atom: (LETTER | SYMBOL) subexpr? | NUMBER;

frac:
    CMD_FRAC L_BRACE
    (letter1=LETTER | (letter1=LETTER? upper=expr))
    R_BRACE L_BRACE
    ((letter2=LETTER (wrt_letter=LETTER | wrt_sym=SYMBOL)) | lower=expr)
    R_BRACE;

func_normal:
    FUNC_LOG | FUNC_LN
    | FUNC_SIN | FUNC_COS | FUNC_TAN
    | FUNC_CSC | FUNC_SEC | FUNC_COT
    | FUNC_ARCSIN | FUNC_ARCCOS | FUNC_ARCTAN
    | FUNC_ARCCSC | FUNC_ARCSEC | FUNC_ARCCOT;

func:
    func_normal
    (subexpr? supexpr? | supexpr? subexpr?)
    func_arg

    | FUNC_INT
    (subexpr supexpr | supexpr subexpr)?
    mp

    | FUNC_SQRT L_BRACE expr R_BRACE

    | (FUNC_SUM | FUNC_PROD)
    (subeq supexpr | supexpr subeq)
    mp;


func_arg: atom+ | comp;

subexpr: UNDERSCORE L_BRACE expr R_BRACE;
supexpr: CARET L_BRACE expr R_BRACE;

subeq: UNDERSCORE L_BRACE equality R_BRACE;
supeq: UNDERSCORE L_BRACE equality R_BRACE;
