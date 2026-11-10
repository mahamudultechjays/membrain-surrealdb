"""Promotion scoring: statements in, scores per value out. Pure, no I/O.

Within one fact group (topic), a "for" statement of value V counts for V and
against every other value in the group; an "against" statement of V counts
against V only. Each person's n-th statement for (or against) one value weighs
first * repeat_factor**(n-1), so one person adds at most about 2 (spec section 6).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

Stance = Literal["for", "against"]


@dataclass(frozen=True, slots=True)
class Weights:
    first: float
    repeat_factor: float


@dataclass(frozen=True, slots=True)
class ScoredStatement:
    user: str
    group_id: int
    value: str
    stance: Stance
    said_at: str
    # The statement's id in our store, so evidence can show its text.
    ref: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    """One person's statements for (or against) a value, oldest first."""

    user: str
    weights: tuple[float, ...]
    said_at: tuple[str, ...]
    # What they said: the value, or "not <value>" for an explicit denial.
    value: str
    refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValueScore:
    group_id: int
    value: str
    for_score: float
    against_score: float
    team_score: float
    # Users with at least one "for" statement, sorted.
    holders: tuple[str, ...]
    # User -> own for minus own against.
    personal: dict[str, float] = field(default_factory=dict)
    # User -> said_at of the statement that made it their personal rule.
    personal_rule_since: dict[str, str] = field(default_factory=dict)


def weight(n: int, w: Weights) -> float:
    """Weight of a person's n-th statement (1-based)."""
    return w.first * w.repeat_factor ** (n - 1)


def norm(value: str) -> str:
    return " ".join(value.casefold().split()).rstrip(" .;,")


def same_value(a: str, b: str) -> bool:
    return norm(a) == norm(b)


_PREFIX = re.compile(r"^.*/")


def clean_subject(name: str) -> str:
    """'organisation/Cobalt_Ridge' -> 'cobalt ridge'."""
    name = _PREFIX.sub("", name.strip())
    return " ".join(name.replace("_", " ").lower().split())


def _r(x: float) -> float:
    return round(x, 6)


def score(
    statements: Iterable[ScoredStatement],
    w: Weights,
    *,
    personal_rule_at: float,
    extra: Iterable[tuple[int, str]] = (),
) -> list[ValueScore]:
    """`extra`: (group, value) pairs to score even with no "for" statement left,
    such as active team rules, so a rule everyone moved away from can be flagged."""
    rows = sorted(statements, key=lambda r: r.said_at)
    # (group, normalised value) -> first spelling seen.
    spelling: dict[tuple[int, str], str] = {}
    for r in rows:
        spelling.setdefault((r.group_id, norm(r.value)), r.value)
    keep = set()
    for group, value in extra:
        spelling.setdefault((group, norm(value)), value)
        keep.add((group, norm(value)))

    out: list[ValueScore] = []
    for (group, key), shown in spelling.items():
        in_group = [r for r in rows if r.group_id == group]
        users = sorted({r.user for r in in_group})
        total_for = total_against = 0.0
        personal: dict[str, float] = {}
        since: dict[str, str] = {}
        holders: list[str] = []
        for user in users:
            n_for = n_against = 0
            own = 0.0
            for r in (r for r in in_group if r.user == user):
                mine = norm(r.value) == key
                if r.stance == "for" and mine:
                    n_for += 1
                    gain = weight(n_for, w)
                    total_for += gain
                    own += gain
                elif (r.stance == "for" and not mine) or (r.stance == "against" and mine):
                    n_against += 1
                    loss = weight(n_against, w)
                    total_against += loss
                    own -= loss
                else:
                    continue
                if user not in since and _r(own) >= personal_rule_at:
                    since[user] = r.said_at
                elif user in since and _r(own) < personal_rule_at:
                    del since[user]
            if n_for:
                holders.append(user)
            if n_for or n_against:
                personal[user] = _r(own)
        if not holders and (group, key) not in keep:
            # Only "against" statements: no value to report on its own.
            continue
        out.append(
            ValueScore(
                group_id=group,
                value=shown,
                for_score=_r(total_for),
                against_score=_r(total_against),
                team_score=_r(total_for - total_against),
                holders=tuple(holders),
                personal=personal,
                personal_rule_since=since,
            )
        )
    return out


def evidence(
    statements: Iterable[ScoredStatement], group_id: int, value: str, w: Weights
) -> tuple[list[EvidenceRow], list[EvidenceRow]]:
    """Who counts for and against `value` in one group, with each statement's
    weight, in the same way score() counts them."""
    key = norm(value)
    rows = sorted((r for r in statements if r.group_id == group_id), key=lambda r: r.said_at)
    found_for: list[EvidenceRow] = []
    found_against: list[EvidenceRow] = []
    for user in sorted({r.user for r in rows}):
        mine = [r for r in rows if r.user == user]
        pro = [r for r in mine if r.stance == "for" and norm(r.value) == key]
        con = [
            r for r in mine
            if (r.stance == "for" and norm(r.value) != key)
            or (r.stance == "against" and norm(r.value) == key)
        ]  # fmt: skip
        if pro:
            found_for.append(_row(user, pro, w, pro[-1].value))
        if con:
            last = con[-1]
            said = last.value if last.stance == "for" else f"not {last.value}"
            found_against.append(_row(user, con, w, said))
    return found_for, found_against


def _row(user: str, rows: list[ScoredStatement], w: Weights, said: str) -> EvidenceRow:
    return EvidenceRow(
        user=user,
        weights=tuple(weight(n, w) for n in range(1, len(rows) + 1)),
        said_at=tuple(r.said_at for r in rows),
        value=said,
        refs=tuple(r.ref for r in rows),
    )
