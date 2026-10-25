"""InProcessBus (arch 10 §10.3, DX-8): sync mode is deterministic; chaos mode reorders, duplicates and delays
but honours FIFO groups — so flow tests prove consumers are idempotent and order-tolerant."""
from tasklane.platform.bus import Event, InProcessBus


def _events(n: int, group: str | None = None) -> list[Event]:
    return [Event(type="item.values_changed", event_id=f"e{i}", payload={"i": i}, group=group) for i in range(n)]


def test_sync_mode_delivers_in_order_exactly_once() -> None:
    bus = InProcessBus()
    seen: list[int] = []
    bus.subscribe("item.*", lambda e: seen.append(e.payload["i"]))
    for e in _events(5):
        bus.publish(e)
    bus.drain()
    assert seen == [0, 1, 2, 3, 4]


def test_subscription_patterns_filter_types() -> None:
    bus = InProcessBus()
    seen: list[str] = []
    bus.subscribe("board.*", lambda e: seen.append(e.type))
    bus.publish(Event(type="item.created", event_id="a", payload={}))
    bus.publish(Event(type="board.structure_changed", event_id="b", payload={}))
    bus.drain()
    assert seen == ["board.structure_changed"]


def test_consumers_can_publish_while_draining() -> None:
    bus = InProcessBus()
    seen: list[str] = []

    def chain(e: Event) -> None:
        seen.append(e.type)
        if e.type == "item.created":
            bus.publish(Event(type="item.values_changed", event_id="c", payload={}))

    bus.subscribe("item.*", chain)
    bus.publish(Event(type="item.created", event_id="a", payload={}))
    bus.drain()
    assert seen == ["item.created", "item.values_changed"]


def test_chaos_is_reproducible_per_seed() -> None:
    def run(seed: int) -> list[str]:
        bus = InProcessBus(chaos_seed=seed)
        seen: list[str] = []
        bus.subscribe("item.*", lambda e: seen.append(e.event_id))
        for e in _events(30):
            bus.publish(e)
        bus.drain()
        return seen

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_chaos_delivers_every_event_at_least_once_and_some_twice() -> None:
    bus = InProcessBus(chaos_seed=3)
    seen: list[str] = []
    bus.subscribe("item.*", lambda e: seen.append(e.event_id))
    for e in _events(200):
        bus.publish(e)
    bus.drain()
    assert set(seen) == {f"e{i}" for i in range(200)}
    assert len(seen) > 200  # duplicates happen
    assert seen != sorted(seen, key=lambda s: int(s[1:]))  # reordering happens


def test_chaos_keeps_fifo_order_within_a_group() -> None:
    bus = InProcessBus(chaos_seed=11)
    seen: list[int] = []
    bus.subscribe("item.*", lambda e: seen.append(e.payload["i"]))
    for e in _events(50, group="auto:1:42"):
        bus.publish(e)
    bus.drain()
    firsts: list[int] = []
    for i in seen:  # duplicates allowed, but first deliveries must be in order
        if i not in firsts:
            firsts.append(i)
    assert firsts == list(range(50))
