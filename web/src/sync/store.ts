/**
 * Entity store + reconciler (arch 09 §9.3, AR-2, D-010).
 *
 * Version rule: every item carries the server `version`. A pushed change with version v applies only when
 * v === local + 1 (it carries changed columns only); v <= local is a duplicate/stale delivery and is ignored;
 * v > local + 1 means we missed something — the item is marked stale and re-fetched (full row wins when its
 * version is newer). Optimistic edits are overlays keyed by mutation id, removed when the server confirms.
 */
import type { ItemEvent, ServerItem, Values } from "./types";

interface Entry {
  item: ServerItem;
  overlays: Map<string, { value: unknown; mutationId: string }>;
}

export type Listener = () => void;

export class BoardStore {
  private entries = new Map<string, Entry>();
  private listeners = new Set<Listener>();
  private staleIds = new Set<string>();

  constructor(private readonly onStale: (ids: string[]) => void = () => {}) {}

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit(): void {
    for (const fn of this.listeners) fn();
  }

  /** Full rows from items:fetch: replace when newer or equal (equal = idempotent). */
  applyItems(items: ServerItem[]): void {
    for (const it of items) {
      const cur = this.entries.get(it.id);
      if (!cur) {
        this.entries.set(it.id, { item: structuredClone(it), overlays: new Map() });
      } else if (it.version >= cur.item.version) {
        cur.item = structuredClone(it);
      }
      this.staleIds.delete(it.id);
    }
    this.emit();
  }

  applyEvent(ev: ItemEvent): void {
    const cur = this.entries.get(ev.item_id);
    if (!cur) return; // not loaded (other view/page) — hydration will bring it
    const local = cur.item.version;
    if (ev.version <= local) {
      this.confirm(cur, ev);
      return;
    }
    if (ev.version > local + 1) {
      if (!this.staleIds.has(ev.item_id)) {
        this.staleIds.add(ev.item_id);
        this.onStale([ev.item_id]);
      }
      this.confirm(cur, ev);
      return;
    }
    const values: Values = { ...cur.item.values };
    for (const [k, v] of Object.entries(ev.values)) {
      if (v === null || v === undefined) delete values[k];
      else values[k] = v;
    }
    cur.item = { ...cur.item, version: ev.version, values };
    this.confirm(cur, ev);
    this.emit();
  }

  private confirm(cur: Entry, ev: ItemEvent): void {
    if (!ev.mutation_id) return;
    let changed = false;
    for (const [col, o] of cur.overlays) {
      if (o.mutationId === ev.mutation_id) {
        cur.overlays.delete(col);
        changed = true;
      }
    }
    if (changed) this.emit();
  }

  /** Optimistic local edit; returns a rollback for when the request fails. */
  setOptimistic(itemId: string, col: string, value: unknown, mutationId: string): () => void {
    const cur = this.entries.get(itemId);
    if (!cur) return () => {};
    cur.overlays.set(col, { value, mutationId });
    this.emit();
    return () => {
      const o = cur.overlays.get(col);
      if (o?.mutationId === mutationId) {
        cur.overlays.delete(col);
        this.emit();
      }
    };
  }

  /** What the UI shows: server values with pending optimistic overlays on top. */
  view(itemId: string): (ServerItem & { pending: string[] }) | undefined {
    const cur = this.entries.get(itemId);
    if (!cur) return undefined;
    const values: Values = { ...cur.item.values };
    for (const [col, o] of cur.overlays) {
      if (o.value === null) delete values[col];
      else values[col] = o.value;
    }
    return { ...cur.item, values, pending: [...cur.overlays.keys()] };
  }

  server(itemId: string): ServerItem | undefined {
    return this.entries.get(itemId)?.item;
  }

  ids(): string[] {
    return [...this.entries.keys()];
  }

  stale(): string[] {
    return [...this.staleIds];
  }
}
