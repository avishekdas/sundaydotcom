/**
 * Board sync engine (arch 09 §9.3, AR-18, DX-3): subscribe-then-load, push via WebSocket, gap sync on
 * reconnect via POST /boards/{id}/changes with an xid cursor taken *before* the snapshot, so no change is lost
 * between the snapshot and the first pushed event.
 */
import { BoardStore } from "./store";
import type { ItemEvent, ServerItem } from "./types";

export interface Schema {
  board: { id: string; name: string };
  groups: { id: string; title: string; color: string }[];
  columns: { id: string; title: string; type: string; settings: Record<string, unknown> }[];
}

export interface BoardApi {
  schema(boardId: string): Promise<Schema>;
  query(boardId: string): Promise<{ ids: string[]; groups: { id: string; count: number }[] }>;
  fetch(boardId: string, ids: string[]): Promise<ServerItem[]>;
  /** Opaque cursor; `more` = another page follows. Rejects with `{ status: 410 }` when the cursor expired. */
  changes(boardId: string, since: string | null): Promise<{ next_since_xmin: string; db_generation: number;
                                                            more?: boolean; changes: { item_id: string }[] }>;
}

export interface Socket {
  send(msg: unknown): void;
  close(): void;
}

export interface SocketFactory {
  open(handlers: { onMessage: (m: Record<string, unknown>) => void; onOpen: () => void; onClose: () => void }):
    Promise<Socket>;
}

export class SyncEngine {
  readonly store: BoardStore;
  schema: Schema | null = null;
  order: string[] = [];
  private cursor: string | null = null;
  private generation: number | null = null;
  private socket: Socket | null = null;
  private stopped = false;
  private reconnectDelay = 500;
  onChange: () => void = () => {};

  constructor(private readonly api: BoardApi, private readonly sockets: SocketFactory, readonly boardId: string,
              private readonly sleep: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms))) {
    this.store = new BoardStore((ids) => void this.refetch(ids));
    this.store.subscribe(() => this.onChange());
  }

  async start(): Promise<void> {
    await this.connect();             // 1. subscribe first …
    const c = await this.api.changes(this.boardId, null); // 2. … take the cursor …
    this.cursor = c.next_since_xmin;
    this.generation = c.db_generation;
    await this.load();                // 3. … then load the snapshot
  }

  private async load(): Promise<void> {
    const [schema, q] = await Promise.all([this.api.schema(this.boardId), this.api.query(this.boardId)]);
    this.schema = schema;
    this.order = q.ids;
    await this.refetch(q.ids);
    this.onChange();
  }

  private async refetch(ids: string[]): Promise<void> {
    for (let i = 0; i < ids.length; i += 200) {
      this.store.applyItems(await this.api.fetch(this.boardId, ids.slice(i, i + 200)));
    }
  }

  private async connect(): Promise<void> {
    this.socket = await this.sockets.open({   // resolves once the socket is open
      onOpen: () => {},
      onMessage: (m) => {
        if (m.type === "item.values_changed" && m.board_id === this.boardId) this.store.applyEvent(m as unknown as ItemEvent);
      },
      onClose: () => void this.reconnect(),
    });
    this.socket.send({ action: "subscribe", board_id: this.boardId });
  }

  private async reconnect(): Promise<void> {
    if (this.stopped || this.paused) return;
    await this.sleep(this.reconnectDelay);
    this.reconnectDelay = Math.min(this.reconnectDelay * 2, 15_000);
    try {
      await this.connect();
      this.reconnectDelay = 500;
      await this.gapSync();
    } catch {
      void this.reconnect();
    }
  }

  /** Re-fetch everything that changed since the cursor; full reload on a new db_generation (OPS-10). */
  async gapSync(): Promise<void> {
    const ids = new Set<string>();
    for (;;) {
      let c;
      try {
        c = await this.api.changes(this.boardId, this.cursor);
      } catch (e) {
        if ((e as { status?: number }).status === 410) return this.reload(); // cursor older than retention
        throw e;
      }
      if (this.generation !== null && c.db_generation !== this.generation) {
        this.generation = c.db_generation;
        return this.reload();
      }
      this.cursor = c.next_since_xmin;
      for (const x of c.changes) ids.add(x.item_id);
      if (!c.more) break;
    }
    if (ids.size) await this.refetch([...ids]);
  }

  private async reload(): Promise<void> {
    const c = await this.api.changes(this.boardId, null);
    this.cursor = c.next_since_xmin;
    this.generation = c.db_generation;
    await this.load();
  }

  stop(): void {
    this.stopped = true;
    this.socket?.close();
  }

  /** Test hook (non-prod only): drop the socket and stay offline until resume(). */
  private paused = false;
  pause(): void {
    this.paused = true;
    this.socket?.close();
  }

  async resume(): Promise<void> {
    this.paused = false;
    await this.connect();
    await this.gapSync();
  }
}
