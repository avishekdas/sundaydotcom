import { SyncEngine, type BoardApi, type SocketFactory } from "./engine";
import type { ServerItem } from "./types";

/** In-memory server with an xid-like change log. */
class FakeServer implements BoardApi {
  items = new Map<string, ServerItem>();
  log: { xid: number; item_id: string }[] = [];
  xid = 100;
  calls: string[] = [];
  generation = 1;
  constructor() {
    for (const id of ["1", "2"]) this.items.set(id, { id, name: id, group_id: "g", version: 1, values: {} });
  }
  write(id: string, col: string, value: unknown) {
    const it = this.items.get(id)!;
    const next = { ...it, version: it.version + 1, values: { ...it.values, [col]: value } };
    this.items.set(id, next);
    this.log.push({ xid: this.xid++, item_id: id });
    return { item_id: id, version: next.version, values: { [col]: value }, type: "item.values_changed", board_id: "10" };
  }
  async schema() { this.calls.push("schema"); return { board: { id: "10", name: "B" }, groups: [], columns: [] }; }
  async query() { this.calls.push("query"); return { ids: [...this.items.keys()], groups: [] }; }
  async fetch(_b: string, ids: string[]) { this.calls.push("fetch"); return ids.map((i) => structuredClone(this.items.get(i)!)); }
  async changes(_b: string, since: string | null) {
    this.calls.push("changes");
    const next = String(this.xid);
    const changes = since === null ? [] : this.log.filter((l) => l.xid >= Number(since)).map((l) => ({ item_id: l.item_id }));
    return { next_since_xmin: next, db_generation: this.generation, changes };
  }
}

function sockets(calls: string[]) {
  const live: { onMessage: (m: Record<string, unknown>) => void; onClose: () => void }[] = [];
  const f: SocketFactory = {
    async open(h) {
      calls.push("ws.open");
      live.push(h);
      h.onOpen();
      return { send: (m) => calls.push(`ws.send:${JSON.stringify(m)}`), close: () => {} };
    },
  };
  return { f, live };
}

describe("SyncEngine", () => {
  it("subscribes, takes the cursor, then loads", async () => {
    const srv = new FakeServer();
    const { f } = sockets(srv.calls);
    const e = new SyncEngine(srv, f, "10", async () => {});
    await e.start();
    expect(srv.calls.slice(0, 4)).toEqual(["ws.open", 'ws.send:{"action":"subscribe","board_id":"10"}', "changes", "schema"]);
    expect(e.store.view("1")?.version).toBe(1);
  });

  it("applies pushed edits and converges after missing 10 edits while disconnected", async () => {
    const srv = new FakeServer();
    const { f, live } = sockets(srv.calls);
    const e = new SyncEngine(srv, f, "10", async () => {});
    await e.start();
    live[0]!.onMessage(srv.write("1", "status", { l: 1 }));
    expect(e.store.view("1")?.values).toEqual({ status: { l: 1 } });
    // disconnect; 10 edits happen that this client never receives
    for (let k = 0; k < 10; k++) srv.write(k % 2 ? "1" : "2", "note", `n${k}`);
    live[0]!.onClose();
    await new Promise((r) => setTimeout(r, 0));
    await new Promise((r) => setTimeout(r, 0));
    for (const id of ["1", "2"]) expect(e.store.view(id)).toMatchObject(srv.items.get(id)!);
  });

  it("reloads fully when the database generation changes (restore)", async () => {
    const srv = new FakeServer();
    const { f } = sockets(srv.calls);
    const e = new SyncEngine(srv, f, "10", async () => {});
    await e.start();
    srv.generation = 2;
    srv.items.set("3", { id: "3", name: "3", group_id: "g", version: 1, values: {} });
    await e.gapSync();
    expect(e.order).toEqual(["1", "2", "3"]);
  });

  it("pause/resume: stays offline while paused, converges on resume", async () => {
    const srv = new FakeServer();
    const { f, live } = sockets(srv.calls);
    const e = new SyncEngine(srv, f, "10", async () => {});
    await e.start();
    e.pause();
    live[0]!.onClose();
    for (let k = 0; k < 10; k++) srv.write("1", "note", `n${k}`);
    await new Promise((r) => setTimeout(r, 0));
    expect(live.length).toBe(1);               // no reconnect while paused
    await e.resume();
    expect(live.length).toBe(2);
    expect(e.store.view("1")).toMatchObject(srv.items.get("1")!);
  });

  it("follows paged changes and reloads on an expired cursor (410)", async () => {
    const srv = new FakeServer();
    const { f } = sockets(srv.calls);
    const e = new SyncEngine(srv, f, "10", async () => {});
    await e.start();
    for (let k = 0; k < 5; k++) srv.write("1", "note", `n${k}`);
    const real = srv.changes.bind(srv);
    let calls = 0;
    srv.changes = async (b, since) => {               // first page says "more"
      const r = await real(b, since);
      return ++calls === 1 ? { ...r, more: true, next_since_xmin: since! } : r;
    };
    await e.gapSync();
    expect(calls).toBe(2);
    expect(e.store.view("1")).toMatchObject(srv.items.get("1")!);
    srv.changes = async (b, since) => { if (since !== null) throw Object.assign(new Error("gone"), { status: 410 }); return real(b, since); };
    srv.items.set("3", { id: "3", name: "3", group_id: "g", version: 1, values: {} });
    await e.gapSync();
    expect(e.order).toEqual(["1", "2", "3"]);
  });

  it("recovers a lost push while connected via the periodic gap sync (M0B-4)", async () => {
    vi.useFakeTimers();
    try {
      const srv = new FakeServer();
      const { f } = sockets(srv.calls);
      const e = new SyncEngine(srv, f, "10", async () => {});
      await e.start();
      srv.write("2", "note", "lost push");          // never delivered over the socket
      await vi.advanceTimersByTimeAsync(SyncEngine.GAP_SYNC_MS + 10);
      expect(e.store.view("2")).toMatchObject(srv.items.get("2")!);
      e.stop();
    } finally {
      vi.useRealTimers();
    }
  });
});
