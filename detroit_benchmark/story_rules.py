"""Story Rules: what the story allows next, given what a Run has done so far.

``StoryRules(graph)`` answers which options a choice offers (``offered``) and where every
other node leads (``resolve``), over ``Facts``: the Run's flags laid over the story's
starting flags, and the nodes it has passed. Inside a Run a node never passed is simply
not seen; only ``reachable``, a walk outside any Run, treats a Seen Condition (and any
flag it is not given) as unknown.
"""

from __future__ import annotations

import operator
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field

# How a condition node picks its branch: a Quick-Time Event always succeeds,
# a rule is evaluated over earlier choices' flags, unknown falls back to default.
QTE, RULE, UNKNOWN = CONDITION_RESOLUTIONS = ("qte", "rule", "unknown")

COMPARISONS = {
    "gte": operator.ge,
    "gt": operator.gt,
    "lte": operator.le,
    "lt": operator.lt,
}


@dataclass(frozen=True)
class Facts:
    """What a Run has done so far: its flags and the remembered nodes it has passed."""

    flags: Mapping = field(default_factory=dict)
    seen: Collection[str] = frozenset()


@dataclass(frozen=True)
class Step:
    """Where a node leads. ``assumed`` is true when the Run's facts could not decide
    it and the story's default was taken."""

    next: str | None
    branch_index: int | None = None
    values: tuple = ()
    assumed: bool = False
    # A final route's flag value: the Run's, or the route's default when assumed.
    value: bool | None = None


class StoryRules:
    def __init__(self, graph: dict):
        self._nodes = graph["nodes"]
        self._initial = dict(graph.get("initial_flags") or {})
        self._remembered = {
            name
            for node in self._nodes.values()
            for _, expr in _expressions(node)
            for name in _seen_names(expr)
        }

    def remembers(self, node_id: str) -> bool:
        """Whether a Run must remember passing this node: a Seen Condition names it."""
        return node_id in self._remembered

    def successors(self, node_id: str) -> list[str]:
        """Every node this one can lead to, whatever the Run has done."""
        return _edges(self._nodes[node_id])

    def reachable(self, start: str, flags: Mapping | None = None) -> list[str]:
        """Nodes reachable from ``start`` in visiting order, outside any Run.

        With ``flags``, a condition whose branch they decide follows only that
        branch; everything else follows every edge. Being outside a Run, the walk
        knows only the flags it is given, not the story's starting flags, and never
        what the Run has seen: it shows every scene that could follow.
        """
        known = None if flags is None else dict(flags)
        order, visited, queue = [], {start}, [start]
        while queue:
            nid = queue.pop(0)
            if nid not in self._nodes:
                continue
            order.append(nid)
            node = self._nodes[nid]
            dests = _edges(node)
            if known is not None and node.get("type") == "condition":
                idx, _, unknown = _pick_branch(node, known, None)
                if idx is not None:
                    dests = [node["branches"][idx]["next"]]
                elif not unknown and node.get("next"):
                    dests = [node["next"]]
            for dest in dests:
                if dest not in visited:
                    visited.add(dest)
                    queue.append(dest)
        return order

    def offered(self, node_id: str, facts: Facts) -> list[tuple[dict, bool]]:
        """The options a choice offers, in order, each with whether it is unverified:
        its Unlock Requirement is one the story does not track, or the transcripts
        only describe it. An option whose requirement was not met is left out. Raises
        when nothing is left to offer."""
        flags = {**self._initial, **facts.flags}
        offered = []
        for option in self._nodes[node_id]["options"]:
            results = [
                _evaluate(x, flags, facts.seen) for x in option.get("requires", [])
            ]
            if False in results:
                continue
            unverified = None in results or bool(option.get("requirements_unverified"))
            offered.append((option, unverified))
        if not offered:
            raise RuntimeError(
                f"No available actions at {node_id}. Check state predicates."
            )
        return offered

    def resolve(self, node_id: str, facts: Facts) -> Step:
        """Where any node but a choice leads. A Quick-Time Event always succeeds; a rule
        takes the one branch whose condition holds, or its fall-through ``next``; a
        final route follows its flag. Raises on a story error: two branches holding at
        once, or a condition with nowhere to go."""
        node = self._nodes[node_id]
        kind = node.get("type")
        if kind == "choice":
            raise ValueError(f"{node_id} is a choice: ask which options it offers")
        if kind == "ending":
            return Step(None)
        if kind not in ("route", "condition"):
            return Step(node.get("next"))
        flags = {**self._initial, **facts.flags}
        if kind == "route":
            value = flags.get(node["flag"])
            assumed = value is None
            if assumed:
                value = node["default"]
            return Step(
                node["if_true"] if value else node["if_false"],
                value=value,
                assumed=assumed,
            )
        if node.get("resolution") == QTE:
            return Step(*_qte_success(node))
        idx, values, unknown = _pick_branch(node, flags, facts.seen)
        if values.count(True) > 1:
            matches = [i for i, v in enumerate(values) if v is True]
            raise RuntimeError(f"Overlapping conditions at {node_id}: {matches}")
        if unknown:
            idx = node.get("default_branch", 0)
        dest = node["branches"][idx]["next"] if idx is not None else node.get("next")
        if dest is None:
            raise RuntimeError(f"Unconnected condition at {node_id}")
        return Step(dest, idx, tuple(values), assumed=unknown)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _evaluate(
    cond: dict | None, flags: Mapping, seen: Collection[str] | None
) -> bool | None:
    """True, False, or None when unknown. Without ``seen`` (no Run, e.g. a
    reachability walk) a Seen Condition is unknown."""
    if cond is None:
        return None
    if "all" in cond:
        results = [_evaluate(x, flags, seen) for x in cond["all"]]
        return None if None in results else all(results)
    if "any" in cond:
        results = [_evaluate(x, flags, seen) for x in cond["any"]]
        if True in results:
            return True
        return None if None in results else False
    if "not" in cond:
        result = _evaluate(cond["not"], flags, seen)
        return None if result is None else not result
    if "seen" in cond:
        return None if seen is None else cond["seen"] in seen
    if "flag" in cond:
        if cond["flag"] not in flags:
            return None
        value = flags[cond["flag"]]
        compared = [op for op in COMPARISONS if op in cond]
        if compared:
            # A Running Score compared with a number, e.g. {"flag": ..., "gte": 80}.
            return _is_number(value) and all(
                COMPARISONS[op](value, cond[op]) for op in compared
            )
        return value == cond.get("equals", True)
    raise ValueError(f"Unsupported condition expression {cond}")


def _pick_branch(
    node: dict, flags: Mapping, seen: Collection[str] | None
) -> tuple[int | None, list, bool]:
    """Which branch a condition takes: ``(index, values, unknown)``.

    The single branch whose ``when`` is true wins. With none true, the index is
    None: the fall-through ``next`` when every value is known, else ``unknown``.
    """
    values = [_evaluate(b.get("when"), flags, seen) for b in node["branches"]]
    idx = values.index(True) if True in values else None
    return idx, values, idx is None and None in values


def _qte_success(node: dict) -> tuple[str | None, int | None]:
    """Where a Quick-Time Event's success leads, and through which branch.

    A null ``default_branch`` means every branch is a failure: success is the
    fall-through ``next``. With no such branch, success leads nowhere (None).
    """
    idx = node.get("default_branch", 0)
    if idx is None:
        return node.get("next"), None
    branches = node.get("branches", [])
    if not 0 <= idx < len(branches):
        return None, idx
    return branches[idx].get("next"), idx


def _edges(node: dict) -> list[str]:
    typ = node.get("type")
    if typ == "choice":
        found = [o.get("next") for o in node.get("options", [])]
    elif typ == "condition":
        found = [b.get("next") for b in node.get("branches", [])] + [node.get("next")]
    elif typ == "route":
        found = [node.get("if_true"), node.get("if_false")]
    elif typ == "ending":
        found = []
    else:
        found = [node.get("next")]
    return [dest for dest in found if dest is not None]


def _expressions(node: dict):
    """Every condition expression in a node: branch whens and option requirements."""
    for i, branch in enumerate(node.get("branches", [])):
        if branch.get("when") is not None:
            yield f"branch {i}", branch["when"]
    for option in node.get("options", []):
        for expr in option.get("requires") or []:
            yield f"{option.get('id')} requires", expr


def _seen_names(expr) -> list[str]:
    """The story nodes every Seen Condition in ``expr`` names."""
    if not isinstance(expr, dict):
        return []
    if "seen" in expr:
        return [expr["seen"]]
    inner = (
        expr.get("all") or expr.get("any") or ([expr["not"]] if "not" in expr else [])
    )
    return [name for x in inner for name in _seen_names(x)]
