import fc from "fast-check";
import { BoardStore } from "./store";
import type { ItemEvent, ServerItem } from "./types";

const base = (id: string, version = 1, values = {}): ServerItem => ({ id, name: id, group_id: "g", version, values });

describe("BoardStore reconciler", () => {
  it("applies the next version, ignores duplicates and stale deliveries", () => {
    const s = new BoardStore();
    s.applyItems([base("1")]);
    s.applyEvent({ item_id: "1", version: 2, values: { status: { l: 1 } } });
    s.applyEvent({ item_id: "1", version: 2, values: { status: { l: 0 } } }); // duplicate
    s.applyEvent({ item_id: "1", version: 1, values: { status: { l: 2 } } }); // stale
    expect(s.view("1")?.values).toEqual({ status: { l: 1 } });
    s.applyEvent({ item_id: "1", version: 3, values: { status: null } });
    expect(s.view("1")?.values).toEqual({});
  });

  it("marks an item stale on a version gap and recovers from a full row", () => {
    const stale: string[][] = [];
    const s = new BoardStore((ids) => stale.push(ids));
    s.applyItems([base("1")]);
    s.applyEvent({ item_id: "1", version: 4, values: { note: "d" } });
    expect(stale).toEqual([["1"]]);
    expect(s.view("1")?.version).toBe(1);
    s.applyItems([base("1", 4, { note: "d", status: { l: 1 } })]);
    expect(s.stale()).toEqual([]);
    expect(s.view("1")?.values).toEqual({ note: "d", status: { l: 1 } });
  });

  it("shows optimistic overlays until the server confirms the same mutation", () => {
    const s = new BoardStore();
    s.applyItems([base("1")]);
    s.setOptimistic("1", "status", { l: 2 }, "m1");
    expect(s.view("1")?.values).toEqual({ status: { l: 2 } });
    expect(s.view("1")?.pending).toEqual(["status"]);
    s.applyEvent({ item_id: "1", version: 2, values: { status: { l: 2 } }, mutation_id: "m1" });
    expect(s.view("1")?.pending).toEqual([]);
    const rollback = s.setOptimistic("1", "note", "x", "m2");
    rollback();
    expect(s.view("1")?.values).toEqual({ status: { l: 2 } });
  });

  it("converges to the server state under reordering, duplicates and drops (property)", () => {
    const cols = ["status", "note", "amount"];
    const write = fc.record({ item: fc.constantFrom("1", "2", "3"), col: fc.constantFrom(...cols),
                              value: fc.option(fc.integer({ min: 0, max: 9 }), { nil: null }) });
    fc.assert(
      fc.property(fc.array(write, { minLength: 1, maxLength: 40 }), fc.integer(), (writes, seed) => {
        // server model: per item version + values; history of events
        const server = new Map<string, ServerItem>(["1", "2", "3"].map((id) => [id, base(id)]));
        const history = new Map<string, ServerItem>(["1", "2", "3"].map((id) => [`${id}@1`, base(id)]));
        const events: ItemEvent[] = [];
        for (const w of writes) {
          const it = server.get(w.item)!;
          const values = { ...it.values } as Record<string, unknown>;
          if (w.value === null) delete values[w.col];
          else values[w.col] = w.value;
          const next = { ...it, version: it.version + 1, values };
          server.set(w.item, next);
          history.set(`${w.item}@${next.version}`, next);
          events.push({ item_id: w.item, version: next.version, values: { [w.col]: w.value } });
        }
        // network: deterministic shuffle + duplicate some + drop some
        let x = seed >>> 0;
        const rnd = () => ((x = (x * 1664525 + 1013904223) >>> 0) / 2 ** 32);
        const delivered = events.flatMap((e) => (rnd() < 0.2 ? [] : rnd() < 0.2 ? [e, e] : [e]));
        for (let i = delivered.length - 1; i > 0; i--) {
          const j = Math.floor(rnd() * (i + 1));
          [delivered[i], delivered[j]] = [delivered[j]!, delivered[i]!];
        }
        const client = new BoardStore((ids) => client.applyItems(ids.map((id) => server.get(id)!)));
        client.applyItems(["1", "2", "3"].map((id) => base(id)));
        // stale refetches during delivery return the *current* server row (as a real fetch would)
        for (const e of delivered) {
          client.applyEvent(e);
          // invariant: the client never shows a state the server never had
          for (const id of ["1", "2", "3"]) {
            const v = client.view(id)!;
            expect(v.values).toEqual(history.get(`${id}@${v.version}`)!.values);
          }
        }
        // gap sync: /changes lists every item changed after the cursor → refetch them
        client.applyItems([...new Set(writes.map((w) => w.item))].map((id) => server.get(id)!));
        for (const id of ["1", "2", "3"]) {
          expect(client.view(id)?.values).toEqual(server.get(id)!.values);
          expect(client.view(id)?.version).toBe(server.get(id)!.version);
        }
      }),
      { numRuns: 300 },
    );
  });

  // --- precise contract (mutation testing, M0B-12): notifications, replace rule, confirmations -----------------
  it("notifies subscribers on every visible change and stops after unsubscribe", () => {
    const s = new BoardStore();
    let n = 0;
    const off = s.subscribe(() => { n += 1; });
    s.applyItems([base("1")]);
    expect(n).toBe(1);
    s.applyEvent({ item_id: "1", version: 2, values: { note: "a" } });
    expect(n).toBe(2);
    s.applyEvent({ item_id: "1", version: 2, values: { note: "a" } }); // duplicate without mutation id: no change
    expect(n).toBe(2);
    off();
    s.applyEvent({ item_id: "1", version: 3, values: { note: "b" } });
    expect(n).toBe(2);
  });

  it("full rows replace on equal or newer version only", () => {
    const s = new BoardStore();
    s.applyItems([base("1", 3, { note: "v3" })]);
    s.applyItems([base("1", 3, { note: "v3-again" })]); // equal: idempotent replace
    expect(s.server("1")?.values).toEqual({ note: "v3-again" });
    s.applyItems([base("1", 2, { note: "old" })]); // older: ignored
    expect(s.server("1")?.values).toEqual({ note: "v3-again" });
    s.applyItems([base("1", 5, { note: "v5" })]);
    expect(s.server("1")?.version).toBe(5);
    expect(s.ids()).toEqual(["1"]);
  });

  it("ignores events for items that are not loaded", () => {
    const stale: string[][] = [];
    const s = new BoardStore((ids) => stale.push(ids));
    s.applyEvent({ item_id: "9", version: 5, values: { note: "x" } });
    expect(s.ids()).toEqual([]);
    expect(stale).toEqual([]);
    expect(s.view("9")).toBeUndefined();
  });

  it("reports a gap once until the full row arrives", () => {
    const stale: string[][] = [];
    const s = new BoardStore((ids) => stale.push(ids));
    s.applyItems([base("1")]);
    s.applyEvent({ item_id: "1", version: 4, values: {} });
    s.applyEvent({ item_id: "1", version: 5, values: {} });
    expect(stale).toEqual([["1"]]);
    expect(s.stale()).toEqual(["1"]);
    s.applyItems([base("1", 5)]);
    s.applyEvent({ item_id: "1", version: 8, values: {} });
    expect(stale).toEqual([["1"], ["1"]]);
  });

  it("confirms an optimistic edit even when its echo is a duplicate or arrives after a gap", () => {
    const s = new BoardStore();
    s.applyItems([base("1", 2)]);
    s.setOptimistic("1", "note", "mine", "m1");
    s.applyEvent({ item_id: "1", version: 2, values: { note: "mine" }, mutation_id: "m1" }); // duplicate echo
    expect(s.view("1")?.pending).toEqual([]);
    s.setOptimistic("1", "note", "again", "m2");
    let n = 0;
    s.subscribe(() => { n += 1; });
    s.applyEvent({ item_id: "1", version: 9, values: { note: "again" }, mutation_id: "m2" }); // gap echo
    expect(s.view("1")?.pending).toEqual([]);
    expect(n).toBe(1); // the overlay removal is a visible change
    s.applyEvent({ item_id: "1", version: 9, values: {}, mutation_id: "m-unknown" });
    expect(n).toBe(1); // nothing to confirm: no notification
  });

  it("clears a column for null and for undefined", () => {
    const s = new BoardStore();
    s.applyItems([base("1", 1, { a: 1, b: 2, c: 3 })]);
    s.applyEvent({ item_id: "1", version: 2, values: { a: null, b: undefined } });
    expect(s.server("1")?.values).toEqual({ c: 3 });
  });

  it("rolls back only its own overlay and shows null overlays as cleared", () => {
    const s = new BoardStore();
    s.applyItems([base("1", 1, { note: "server" })]);
    const undo1 = s.setOptimistic("1", "note", "first", "m1");
    s.setOptimistic("1", "note", null, "m2");
    expect(s.view("1")?.values).toEqual({});
    undo1(); // superseded by m2: no effect
    expect(s.view("1")?.pending).toEqual(["note"]);
    expect(s.setOptimistic("404", "note", "x", "m3")).toBeTypeOf("function");
  });
});
