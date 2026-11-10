"""Turn sanitized trace spans into an accessible call hierarchy and bounded waterfall geometry, without new I/O."""

from dataclasses import dataclass

from nimbus.trace_view import TraceView, safe_parent_indices

KINDS = {"Agent": "agent", "Model": "model", "Tool": "tool", "Step": "step", "Memory": "memory"}
STATUSES = {"Completed": "completed", "Failed": "failed", "Running": "running", "Unknown": "unknown"}
BAR_SCALE = 1000


@dataclass(frozen=True)
class PresentedSpan:
    """One displayed call with page-local identity, safe strings, verified ancestry and bounded SVG geometry."""

    key: int
    parent_index: int | None
    ancestor_keys: tuple[int, ...]
    depth: int
    label: str
    kind: str
    kind_slug: str
    status: str
    status_slug: str
    duration: str
    duration_exact: str
    start: str
    start_exact: str
    offset_ms: int
    elapsed_ms: int | None
    bar_x: int
    bar_width: int
    has_children: bool
    error: str | None
    outcome: str
    cache_reason: str
    similarity_score: str
    similarity_threshold: str


@dataclass(frozen=True)
class TracePresentation:
    """Summary counts describe displayed spans; elapsed time is the root duration, never a sum of children."""

    rows: tuple[PresentedSpan, ...]
    duration: str
    duration_exact: str
    duration_ms: int | None
    timeline_ms: int
    ticks: tuple[str, str, str]
    model_count: int
    tool_count: int
    memory_count: int
    memory_root: bool
    failed_count: int
    running_count: int
    total_count: int
    status: str
    status_slug: str


def duration_label(value: int | None) -> str:
    """Use milliseconds below a second and compact seconds above it; missing values remain explicitly unknown."""
    if value is None:
        return "Unknown"
    if value < 1000:
        return f"{max(0, value):,} ms"
    return f"{value / 1000:,.2f}".rstrip("0").rstrip(".") + " s"


def exact_duration(value: int | None) -> str:
    """Keep the original millisecond precision available in the inspector and accessible labels."""
    return "Unknown" if value is None else f"{max(0, value):,} ms"


def present_trace(trace: TraceView) -> TracePresentation:
    """Arrange real parent relationships in preorder with chronological siblings and prepare a shared time axis."""
    rows = trace.rows if trace.status == "ready" else ()
    parents = safe_parent_indices([row.parent_index for row in rows])
    children: dict[int | None, list[int]] = {None: []}
    for index, parent in enumerate(parents):
        children.setdefault(parent, []).append(index)
    for siblings in children.values():
        siblings.sort(key=lambda index: (max(0, rows[index].offset_ms), index))
    root = next(
        (row for index, row in enumerate(rows) if row.kind in {"Agent", "Memory"} and parents[index] is None), None
    )
    elapsed = root.elapsed_ms if root and root.elapsed_ms is not None and root.elapsed_ms >= 0 else None
    timeline_ms = max((max(0, row.offset_ms) + max(0, row.elapsed_ms or 0) for row in rows), default=0)
    failed = sum(row.status == "Failed" for row in rows)
    running = sum(row.status == "Running" for row in rows)
    # A recovered child failure still deserves a visible warning; it does not relabel a completed root as failed.
    status = root.status if root and root.status in STATUSES else "Unknown"
    presented: list[PresentedSpan] = []

    def visit(index: int, ancestors: tuple[int, ...]) -> None:
        """Emit each call once; its actual descendants stay together even when parallel branches interleave."""
        row = rows[index]
        start = max(0, row.offset_ms)
        took = row.elapsed_ms if row.elapsed_ms is not None and row.elapsed_ms >= 0 else None
        x = min(BAR_SCALE, round(BAR_SCALE * start / max(1, timeline_ms)))
        width = min(BAR_SCALE - x, round(BAR_SCALE * max(0, took or 0) / max(1, timeline_ms)))
        kind = row.kind if row.kind in KINDS else "Step"
        row_status = row.status if row.status in STATUSES else "Unknown"
        presented.append(
            PresentedSpan(
                key=index,
                parent_index=parents[index],
                ancestor_keys=ancestors,
                depth=len(ancestors),
                label=row.label,
                kind=kind,
                kind_slug=KINDS[kind],
                status=row_status,
                status_slug=STATUSES[row_status],
                duration=duration_label(took),
                duration_exact=exact_duration(took),
                start="+" + duration_label(start),
                start_exact="+" + exact_duration(start),
                offset_ms=start,
                elapsed_ms=took,
                bar_x=x,
                bar_width=width,
                has_children=bool(children.get(index)),
                error=row.error,
                outcome=row.outcome,
                cache_reason=row.cache_reason,
                similarity_score="" if row.similarity_score is None else f"{row.similarity_score:.3f}",
                similarity_threshold="" if row.similarity_threshold is None else f"{row.similarity_threshold:.3f}",
            )
        )
        for child in children.get(index, ()):
            visit(child, (*ancestors, index))

    for index in children[None]:
        visit(index, ())
    return TracePresentation(
        rows=tuple(presented),
        duration=duration_label(elapsed),
        duration_exact=exact_duration(elapsed),
        duration_ms=elapsed,
        timeline_ms=timeline_ms,
        ticks=("0 ms", duration_label(timeline_ms // 2), duration_label(timeline_ms)),
        model_count=sum(row.kind == "Model" for row in rows),
        tool_count=sum(row.kind == "Tool" for row in rows),
        memory_count=sum(row.kind == "Memory" for row in rows),
        # A Mem0 operation's own trace, rather than a chat request that read Mem0 as one of its steps.
        memory_root=root is not None and root.kind == "Memory",
        failed_count=failed,
        running_count=running,
        total_count=len(rows),
        status=status,
        status_slug=STATUSES[status],
    )
