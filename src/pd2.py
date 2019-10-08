'''
This file contains code for the Primal Dual research project
'''

import argparse, itertools
from itertools import product, chain, combinations, repeat
from collections import defaultdict

from syntax import *
from logic import *
from pd import check_two_state_implication, check_initial
try:
    import separators
except ModuleNotFoundError:
    pass

from typing import TypeVar, Iterable, FrozenSet, Union, Callable, Generator, Set, Optional, cast, Type, Collection

A = TypeVar('A')
PDState = Tuple[Trace, int]

def eval_predicate(s: PDState, p: Expr) -> bool:
    r = s[0].as_state(s[1]).eval(p)
    assert isinstance(r, bool)
    return r


class FOLSeparator(object):
    '''Class used to call into the folseparators code'''
    def __init__(self,
                 states: List[PDState],  # assumed to only grow
    ) -> None:
        prog = syntax.the_program
        self.states = states
        self.ids: Dict[int, int] = {}
        # TODO: if mypyvy get's a signature class, update this
        self.sig = separators.logic.Signature()
        def sort_to_name(s: Sort) -> str:
            assert isinstance(s, UninterpretedSort)
            return s.name
        for d in prog.decls:
            if isinstance(d, SortDecl):
                self.sig.sorts.add(d.name)
            elif isinstance(d, ConstantDecl):
                self.sig.constants[d.name] = sort_to_name(d.sort)
            elif isinstance(d, RelationDecl):
                self.sig.relations[d.name] = list(sort_to_name(s) for s in d.arity)
            elif isinstance(d, FunctionDecl):
                self.sig.functions[d.name] = (list(sort_to_name(s) for s in d.arity), sort_to_name(d.sort))
        self.separator = separators.separate.GeneralizedSeparator(self.sig, logic=utils.args.logic)

    def _state_id(self, i: int) -> int:
        assert 0 <= i < len(self.states)
        if i not in self.ids:
            # add a new state
            m = self.state_to_model(self.states[i])
            self.ids[i] = self.separator.add_model(m)
        return self.ids[i]

    def separate(self,
                 pos: Collection[int] = (),
                 neg: Collection[int] = (),
                 imp: Collection[Tuple[int, int]] = (),
    ) -> Optional[Expr]:
        mtimer = separators.timer.UnlimitedTimer()
        timer = separators.timer.UnlimitedTimer()
        with timer:
            f = self.separator.separate(
                pos=[self._state_id(i) for i in pos],
                neg=[self._state_id(i) for i in neg],
                imp=[(self._state_id(i), self._state_id(j)) for i, j in imp],
                max_depth=100,
                timer=timer,
                matrix_timer=mtimer,
            )
        if f is None:
            return None
        else:
            p = self.formula_to_predicate(f)
            for i in pos:
               assert eval_predicate(self.states[i], p)
            for i in neg:
               assert not eval_predicate(self.states[i], p)
            for i, j in imp:
               assert (not eval_predicate(self.states[i], p)) or eval_predicate(self.states[j], p)
            return p

    def state_to_model(self, s: PDState) -> separators.logic.Model:
        t, i = s
        relations = dict(itertools.chain(t.immut_rel_interps.items(), t.rel_interps[i].items()))
        constants = dict(itertools.chain(t.immut_const_interps.items(), t.const_interps[i].items()))
        functions = dict(itertools.chain(t.immut_func_interps.items(), t.func_interps[i].items()))
        m = separators.logic.Model(self.sig)
        for sort in sorted(t.univs.keys(),key=str):
            for e in t.univs[sort]:
                m.add_elem(e, sort.name)
        for cd, e in constants.items():
            res = m.add_constant(cd.name, e)
            assert res
        for rd in relations:
            for es, v in relations[rd]:
                if v:
                    m.add_relation(rd.name, es)
        for fd in functions:
            for es, e in functions[fd]:
                m.add_function(fd.name, es, e)
        return m

    def formula_to_predicate(self, f: separators.logic.Formula) -> Expr:

        def helper(f: separators.logic.Formula) -> Expr:
            def term_to_expr(t: separators.logic.Term) -> Expr:
                if isinstance(t, separators.logic.Var):
                    return Id(None, t.var)
                elif isinstance(t, separators.logic.Func):
                    return AppExpr(None, t.f, [term_to_expr(a) for a in t.args])
                else:
                    assert False

            if isinstance(f, separators.logic.And):
                return And(*(helper(a) for a in f.c))
            elif isinstance(f, separators.logic.Or):
                return Or(*(helper(a) for a in f.c))
            elif isinstance(f, separators.logic.Not):
                return Not(helper(f.f))
            elif isinstance(f, separators.logic.Equal):
                return Eq(term_to_expr(f.args[0]), term_to_expr(f.args[1]))
            elif isinstance(f, separators.logic.Relation):
                if len(f.args) == 0:
                    return Id(None, f.rel)
                else:
                    return AppExpr(None, f.rel, [term_to_expr(a) for a in f.args])
            elif isinstance(f, separators.logic.Exists):
                body = helper(f.f)
                v = SortedVar(None, f.var, UninterpretedSort(None, f.sort))
                if isinstance(body, QuantifierExpr) and body.quant == 'EXISTS':
                    return Exists([v] + body.binder.vs, body.body)
                else:
                    return Exists([v], body)
            elif isinstance(f, separators.logic.Forall):
                body = helper(f.f)
                v = SortedVar(None, f.var, UninterpretedSort(None, f.sort))
                if isinstance(body, QuantifierExpr) and body.quant == 'FORALL':
                    return Forall([v] + body.binder.vs, body.body)
                else:
                    return Forall([v], body)
            else:
                assert False

        e = helper(f)
        e.resolve(syntax.the_program.scope, BoolSort)
        return e



def fol_pd_houdini(solver: Solver) -> None:
    induction_width = 1
    prog = syntax.the_program

    # algorithm state
    states: List[PDState] = []
    abstractly_reachable_states: Set[int] = set() # indices into state which are known to be reachable
    transitions: Set[Tuple[int, int]] = set() # known transitions between states

    # all predicates should be true in the initial states
    predicates: List[Expr] = []  
    inductive_predicates: Set[int] = set()
    DualTransition = Tuple[FrozenSet[int], FrozenSet[int]]
    dual_transitions: Set[DualTransition] = set()

    def add_state(s: PDState) -> int:
        for i, (t, index) in enumerate(states):
            if t is s[0] and index == s[1]:
                return i

        k = len(states)
        states.append(s)
        return k

    def add_predicate(p: Expr) -> int:
        for i, pred in enumerate(predicates):
            if pred == p:
                return i

        k = len(predicates)
        predicates.append(p)
        return k

    # end of algorithm state

    def houdini(live_predicates: Set[int]) -> Tuple[Set[Tuple[int, int]], Set[int]]: # ctis, inductive subset of live
        live = set(live_predicates)
        ctis: Set[Tuple[int,int]] = set()
        while True:
            # check if conjunction is inductive.
            assumptions = [predicates[i] for i in sorted(live)]
            for a in sorted(live):
                res = check_two_state_implication(solver, assumptions, predicates[a])
                if res is not None:
                    pre, post = (res[0], 0), (res[1], 0)
                    pre_i = add_state(pre)
                    post_i = add_state(post)
                    ctis.add((pre_i, post_i))
                    live = set(l for l in live if eval_predicate(post, predicates[l]))
                    break
            else:
                # live is inductive
                return (ctis, live)
    
    def check_dual_edge(p: List[Expr], q: List[Expr]) -> Optional[Tuple[PDState, PDState]]:
        r = check_two_state_implication(solver, p+q, Implies(And(*p), And(*q)))
        if r is None: return None
        return (r[0],0), (r[1],0)
        

    def dual_edge(live: Set[int], a: int, induction_width: int) -> Optional[Tuple[List[Expr], List[Expr]]]:
        # find conjunctions p,q such that:
        # - forall l in live. states[l] |= p
        # - p ^ q -> wp(p -> q)
        # - !(states[a] |= q)
        # or return None if no such p,q exist where |q| <= induction_width
        p: List[Expr] = [predicates[i] for i in sorted(inductive_predicates)]
        internal_ctis: Set[Tuple[int, int]] = set() # W, could 
        separator = FOLSeparator(states)
        while True:
            q = separator.separate(pos=list(sorted(abstractly_reachable_states)),
                                   neg=[a],
                                   imp=list(sorted(internal_ctis)))
            if q is not None:
                # check for inductiveness
                res = check_initial(solver, q)
                if res is not None:
                    i = add_state((res,0))
                    abstractly_reachable_states.add(i)
                    continue
                res1 = check_dual_edge(p, [q])
                if res1 is not None:
                    (pre, post) = res1
                    a_i, b_i = add_state(pre), add_state(post)
                    internal_ctis.add((a_i, b_i))
                    continue
                # q is inductive relative to p
                return (p,[q])
            else:
                for t in chain(*sorted(internal_ctis)):
                    while True:
                        p_new_conj = separator.separate(
                            pos=list(sorted(abstractly_reachable_states.union(live))),
                            neg=[t]
                        )
                        if p_new_conj is None:
                            # couldn't strengthen p
                            break
                        # check if it satisfied initially
                        res2 = check_initial(solver, p_new_conj)
                        if res2 is not None:
                            i = add_state((res2,0))
                            abstractly_reachable_states.add(i)
                        else:
                            break    
                    if p_new_conj is None:
                        continue
                    # strengthen p
                    p.append(p_new_conj)
                    # make sure all CTIs satisfy p in both initial and post state
                    internal_ctis = set(c for c in internal_ctis if eval_predicate(states[c[0]], p_new_conj) and eval_predicate(states[c[1]], p_new_conj))
                    break
                else:
                    return None
                
    def dual_houdini(live_states: Set[int], induction_width: int) -> Tuple[Set[DualTransition], Set[int]]: # dual cits, subset of "abstractly" reachable states
        live = set(live_states)
        dual_ctis: Set[DualTransition] = set()
        while True:
            for a in sorted(live):
                res = dual_edge(live, a, induction_width)
                if res is not None:
                    (p, q) = res
                    p_i = frozenset(add_predicate(p_conj) for p_conj in p)
                    q_i = frozenset(add_predicate(q_conj) for q_conj in q)
                    dual_ctis.add((p_i, q_i))
                    live = set(l for l in live if all(eval_predicate(states[l], q_conj) for q_conj in q))
                    break
            else:
                # there is no dual edge, so live is all abstractly reachable in the current induction width
                return (dual_ctis, live)

    safety: Set[int] = set()
    for inv in prog.invs():
        if inv.is_safety:
            # Here, could call as_clauses to split apart inv.expr so that we have more fine grained predicates
            safety.add(add_predicate(inv.expr))

    live_predicates: Set[int] = set(safety)
    live_states: Set[int] = set() # states that are "live"
    print([str(predicates[x]) for x in safety])
    while True:
        (ctis, inductive) = houdini(live_predicates)
        inductive_predicates.update(inductive)
        live_states.update(x for cti in ctis for x in cti)
        # filter live_states
        if safety <= inductive_predicates:
            print("safety is inductive!")
            for i in inductive_predicates:
                print(str(predicates[i]))
            break

        (dual_ctis, abstractly_reachable) = dual_houdini(live_states, induction_width)
        abstractly_reachable_states.update(abstractly_reachable)
        live_predicates.update(x for cti in dual_ctis for y in cti for x in y)
        # filter live_predicates
        if not safety <= live_predicates:
            print("found abstractly reachable state(s) violating safety!")
            break