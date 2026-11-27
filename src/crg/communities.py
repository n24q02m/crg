"""Leiden community detection, optimising modularity, in pure Python.

Implements the algorithm of Traag, Waltman and van Eck, "From Louvain to
Leiden: guaranteeing well-connected communities", Scientific Reports 9, 5233
(2019). Each level runs three phases:

1. **Local moving** (fast, queue based): nodes move to the neighbouring
   community with the largest modularity gain, and only the neighbours of a
   node that moved are revisited.
2. **Refinement**: every community from phase 1 is split into well-connected
   sub-communities. Starting from singletons inside the community, a node
   merges into a well-connected sub-community it is linked to, chosen at
   random with probability proportional to ``exp(gain / theta)``, where the
   gain is measured in edge-weight units (as in igraph's implementation), so
   the default ``theta`` makes the draw close to greedy on any graph size.
   Merges only follow edges, so every refined community is connected.
3. **Aggregation**: refined communities become the nodes of the next level,
   and the phase 1 partition is carried over as that level's start.

Levels repeat until local moving leaves every aggregate node on its own; that
is one pass, the stopping rule of the paper. Passes then repeat from the
previous result, as when the paper iterates the algorithm, until a pass no
longer improves modularity or ``max_passes`` is reached. Because the returned
communities are always unions of refined (connected) pieces, every community
in the result is connected.

Modularity with resolution ``gamma`` is
``Q = sum_c [ L_c / m - gamma * (K_c / 2m)^2 ]`` where ``L_c`` is the edge
weight inside ``c``, ``K_c`` the summed degree of ``c`` and ``m`` the total
edge weight. Edges are treated as undirected; parallel or reciprocal edges
add up. Randomness comes only from ``random.Random(seed)``, so a fixed seed
and the same input graph always give the same partition.
"""

from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import networkx as nx

# Moves must beat the incumbent by more than this, so floating-point noise can
# never make two nodes swap back and forth forever.
_EPS = 1e-10


@dataclass(frozen=True)
class LeidenResult:
    """Partition found by ``leiden_partition``.

    ``passes`` counts full Leiden passes run; ``converged`` is False only when
    ``max_passes`` stopped the search while modularity was still improving.
    """

    communities: list[set[Hashable]]
    modularity: float
    passes: int
    converged: bool


def leiden(
    graph: nx.Graph,
    *,
    resolution: float = 1.0,
    seed: int = 0,
    theta: float = 0.01,
    weight: str = "weight",
    max_passes: int | None = None,
) -> list[set[Hashable]]:
    """Partition ``graph`` into communities with the Leiden algorithm.

    Args:
        graph: Any NetworkX graph. Edge direction is ignored.
        resolution: Modularity resolution ``gamma`` (>= 0). Higher values give
            more, smaller communities; lower values give fewer, larger ones.
        seed: Seed for the node order and the refinement draws.
        theta: Randomness of the refinement phase (> 0), applied to the gain
            of each candidate merge in edge-weight units.
        weight: Edge attribute holding a non-negative weight; missing means 1.
        max_passes: Upper bound on full passes; ``None`` repeats passes until
            modularity stops improving.

    Returns:
        Disjoint, connected node sets covering every node, largest first.
    """
    return leiden_partition(
        graph,
        resolution=resolution,
        seed=seed,
        theta=theta,
        weight=weight,
        max_passes=max_passes,
    ).communities


def leiden_partition(
    graph: nx.Graph,
    *,
    resolution: float = 1.0,
    seed: int = 0,
    theta: float = 0.01,
    weight: str = "weight",
    max_passes: int | None = None,
) -> LeidenResult:
    """Like ``leiden``, but also report modularity and how the search ended."""
    if not math.isfinite(resolution) or resolution < 0:
        raise ValueError(f"resolution must be a finite number >= 0, got {resolution}")
    if not math.isfinite(theta) or theta <= 0:
        raise ValueError(f"theta must be a finite number > 0, got {theta}")
    if max_passes is not None and max_passes < 1:
        raise ValueError(f"max_passes must be None or >= 1, got {max_passes}")

    nodes = list(graph.nodes)
    adj, loops = _adjacency(graph, nodes, weight)
    degrees = [sum(a.values()) + 2.0 * loops[i] for i, a in enumerate(adj)]
    total = sum(degrees)
    labels = list(range(len(nodes)))
    if total <= 0:
        return LeidenResult(_as_sets(nodes, labels), 0.0, 0, True)
    rng = random.Random(seed)
    best = _quality(adj, loops, degrees, labels, total, resolution)
    passes = 0
    converged = False
    while max_passes is None or passes < max_passes:
        candidate = _leiden_pass(
            adj, loops, degrees, labels, total, resolution, theta, rng
        )
        passes += 1
        score = _quality(adj, loops, degrees, candidate, total, resolution)
        if score <= best + _EPS:
            converged = True
            break
        labels, best = candidate, score
    return LeidenResult(_as_sets(nodes, labels), best, passes, converged)


def modularity(
    graph: nx.Graph,
    communities: Iterable[Iterable[Hashable]],
    *,
    resolution: float = 1.0,
    weight: str = "weight",
) -> float:
    """Modularity of a partition, with the same conventions as ``leiden``.

    Returns 0.0 for a graph without edge weight, where modularity is undefined.
    """
    nodes = list(graph.nodes)
    position = {node: i for i, node in enumerate(nodes)}
    labels = [-1] * len(nodes)
    for label, community in enumerate(communities):
        for node in community:
            labels[position[node]] = label
    if -1 in labels:
        raise ValueError("communities must cover every node of the graph")
    adj, loops = _adjacency(graph, nodes, weight)
    degrees = [sum(a.values()) + 2.0 * loops[i] for i, a in enumerate(adj)]
    total = sum(degrees)
    if total <= 0:
        return 0.0
    return _quality(adj, loops, degrees, labels, total, resolution)


# ---------------------------------------------------------------------------
# Graph representation
# ---------------------------------------------------------------------------


def _adjacency(
    graph: nx.Graph, nodes: list[Hashable], weight: str
) -> tuple[list[dict[int, float]], list[float]]:
    """Symmetric weighted adjacency over node indices, plus self-loop weights."""
    index = {node: i for i, node in enumerate(nodes)}
    adj: list[dict[int, float]] = [{} for _ in nodes]
    loops = [0.0] * len(nodes)
    for u, v, raw in graph.edges(data=weight, default=1.0):
        w = float(raw)
        if not math.isfinite(w) or w < 0:
            raise ValueError(f"edge weight must be finite and >= 0, got {raw!r}")
        if w == 0:
            continue
        i, j = index[u], index[v]
        if i == j:
            loops[i] += w
        else:
            adj[i][j] = adj[i].get(j, 0.0) + w
            adj[j][i] = adj[j].get(i, 0.0) + w
    return adj, loops


def _quality(
    adj: list[dict[int, float]],
    loops: list[float],
    degrees: list[float],
    labels: list[int],
    total: float,
    resolution: float,
) -> float:
    """Modularity of ``labels``; ``total`` is twice the total edge weight."""
    inside: dict[int, float] = {}
    strength: dict[int, float] = {}
    for v, neighbours in enumerate(adj):
        c = labels[v]
        strength[c] = strength.get(c, 0.0) + degrees[v]
        internal = loops[v] + 0.5 * sum(
            w for u, w in neighbours.items() if labels[u] == c
        )
        inside[c] = inside.get(c, 0.0) + internal
    return sum(
        2.0 * inside[c] / total - resolution * (strength[c] / total) ** 2
        for c in strength
    )


def _as_sets(nodes: list[Hashable], labels: list[int]) -> list[set[Hashable]]:
    groups: dict[int, list[int]] = {}
    for i, label in enumerate(labels):
        groups.setdefault(label, []).append(i)
    ordered = sorted(groups.values(), key=lambda idx: (-len(idx), idx[0]))
    return [{nodes[i] for i in idx} for idx in ordered]


def _compact(labels: list[int]) -> list[int]:
    """Relabel to 0..k-1 in order of first appearance."""
    mapping: dict[int, int] = {}
    return [mapping.setdefault(label, len(mapping)) for label in labels]


# ---------------------------------------------------------------------------
# One Leiden pass
# ---------------------------------------------------------------------------


def _leiden_pass(
    adj: list[dict[int, float]],
    loops: list[float],
    degrees: list[float],
    start: list[int],
    total: float,
    resolution: float,
    theta: float,
    rng: random.Random,
) -> list[int]:
    """Run levels of move/refine/aggregate from ``start``; return node labels."""
    membership = list(range(len(adj)))  # original node -> aggregate node
    labels = _compact(start)
    while True:
        labels = _move_nodes_fast(adj, degrees, labels, total, resolution, rng)
        if len(set(labels)) == len(adj):
            break
        refined = _refine_partition(
            adj,
            degrees,
            labels,
            total=total,
            resolution=resolution,
            theta=theta,
            rng=rng,
        )
        if len(set(refined)) == len(adj):
            # No merge happened. Aggregate on the connected parts of each
            # community instead, so the graph still shrinks and every
            # aggregate node remains a connected set of original nodes.
            refined = _connected_parts(adj, labels)
            if len(set(refined)) == len(adj):
                # Each community is already a set of mutually unreachable
                # nodes; splitting them never lowers modularity.
                labels = refined
                break
        refined = _compact(refined)
        adj, loops, degrees = _aggregate(adj, loops, degrees, refined)
        coarse = [0] * len(adj)
        for node, part in enumerate(refined):
            coarse[part] = labels[node]
        membership = [refined[m] for m in membership]
        labels = _compact(coarse)
    return [labels[m] for m in membership]


def _move_nodes_fast(
    adj: list[dict[int, float]],
    degrees: list[float],
    labels: list[int],
    total: float,
    resolution: float,
    rng: random.Random,
) -> list[int]:
    """Phase 1: queue-based local moving that maximises the modularity gain."""
    n = len(adj)
    labels = list(labels)
    strength = [0.0] * n
    size = [0] * n
    for v, c in enumerate(labels):
        strength[c] += degrees[v]
        size[c] += 1
    empty = [c for c in range(n) if size[c] == 0]
    order = list(range(n))
    rng.shuffle(order)
    queue = deque(order)
    queued = [True] * n
    while queue:
        v = queue.popleft()
        queued[v] = False
        current = labels[v]
        k_v = degrees[v]
        links: dict[int, float] = {}
        for u, w in adj[v].items():
            links[labels[u]] = links.get(labels[u], 0.0) + w
        strength[current] -= k_v
        size[current] -= 1
        scale = resolution * k_v / total
        best = current
        best_gain = links.get(current, 0.0) - scale * strength[current]
        for c, w in links.items():
            gain = w - scale * strength[c]
            if gain > best_gain + _EPS:
                best, best_gain = c, gain
        if best_gain < -_EPS and size[current] > 0:
            # Every neighbouring community costs modularity: start a new one.
            best = empty.pop()
        strength[best] += k_v
        size[best] += 1
        labels[v] = best
        if best == current:
            continue
        if size[current] == 0:
            empty.append(current)
        for u in adj[v]:
            if not queued[u] and labels[u] != best:
                queued[u] = True
                queue.append(u)
    return labels


def _refine_partition(
    adj: list[dict[int, float]],
    degrees: list[float],
    labels: list[int],
    *,
    total: float,
    resolution: float,
    theta: float,
    rng: random.Random,
) -> list[int]:
    """Phase 2: split every community into well-connected sub-communities.

    A node is considered only while it is still a singleton and only if it is
    well connected to its community (``E(v, S - v) >= gamma * k_v * (K_S - k_v)
    / 2m``). It may join a neighbouring sub-community ``C`` that is itself well
    connected and whose merge does not lower modularity; the choice is drawn
    with probability proportional to ``exp(gain / theta)``, where
    ``gain = E(v, C) - gamma * k_v * K_C / 2m`` (``m * delta_Q``, in edge-weight
    units), and staying alone has gain 0.
    """
    n = len(adj)
    members: dict[int, list[int]] = {}
    for v, c in enumerate(labels):
        members.setdefault(c, []).append(v)
    refined = list(range(n))
    ref_strength = list(degrees)
    ref_size = [1] * n
    # Edge weight from each sub-community to the rest of its community.
    ref_external = [0.0] * n
    for v in range(n):
        ref_external[v] = sum(w for u, w in adj[v].items() if labels[u] == labels[v])
    node_external = list(ref_external)

    for community, nodes in members.items():
        if len(nodes) == 1:
            continue
        community_strength = sum(degrees[v] for v in nodes)
        order = list(nodes)
        rng.shuffle(order)
        for v in order:
            if ref_size[refined[v]] != 1:
                continue
            k_v = degrees[v]
            if (
                node_external[v]
                < resolution * k_v * (community_strength - k_v) / total - _EPS
            ):
                continue
            links: dict[int, float] = {}
            for u, w in adj[v].items():
                if labels[u] == community:
                    links[refined[u]] = links.get(refined[u], 0.0) + w
            own = refined[v]
            choices = [own]
            gains = [0.0]
            for part, w in links.items():
                part_strength = ref_strength[part]
                well_connected = (
                    ref_external[part]
                    >= resolution
                    * part_strength
                    * (community_strength - part_strength)
                    / total
                    - _EPS
                )
                gain = w - resolution * k_v * part_strength / total
                if well_connected and gain >= 0:
                    choices.append(part)
                    gains.append(gain)
            if len(choices) == 1:
                continue
            target = _draw(choices, gains, theta, rng)
            if target == own:
                continue
            ref_external[target] += node_external[v] - 2.0 * links[target]
            ref_strength[target] += k_v
            ref_size[target] += 1
            ref_size[own] = 0
            refined[v] = target
    return refined


def _draw(
    choices: list[int], gains: list[float], theta: float, rng: random.Random
) -> int:
    """Pick one choice with probability proportional to ``exp(gain / theta)``."""
    top = max(gains)
    weights = [math.exp((g - top) / theta) for g in gains]
    point = rng.random() * sum(weights)
    for choice, w in zip(choices, weights, strict=True):
        point -= w
        if point < 0:
            return choice
    return choices[-1]


def _connected_parts(adj: list[dict[int, float]], labels: list[int]) -> list[int]:
    """Label each connected piece of every community separately."""
    parts = [-1] * len(adj)
    next_part = 0
    for start in range(len(adj)):
        if parts[start] != -1:
            continue
        parts[start] = next_part
        stack = [start]
        while stack:
            v = stack.pop()
            for u in adj[v]:
                if parts[u] == -1 and labels[u] == labels[start]:
                    parts[u] = next_part
                    stack.append(u)
        next_part += 1
    return parts


def _aggregate(
    adj: list[dict[int, float]],
    loops: list[float],
    degrees: list[float],
    parts: list[int],
) -> tuple[list[dict[int, float]], list[float], list[float]]:
    """Phase 3: collapse each part into one node of the next level."""
    count = max(parts) + 1
    new_adj: list[dict[int, float]] = [{} for _ in range(count)]
    new_loops = [0.0] * count
    new_degrees = [0.0] * count
    for v, neighbours in enumerate(adj):
        p = parts[v]
        new_degrees[p] += degrees[v]
        new_loops[p] += loops[v]
        row = new_adj[p]
        for u, w in neighbours.items():
            q = parts[u]
            if q == p:
                # Seen from both endpoints, so each half counts once.
                new_loops[p] += 0.5 * w
            else:
                row[q] = row.get(q, 0.0) + w
    return new_adj, new_loops, new_degrees
