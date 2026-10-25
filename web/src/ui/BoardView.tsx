import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Api } from "../api";
import { SyncEngine } from "../sync/engine";
import { Cell } from "./cells";

const ROW_H = 36;

export function BoardView({ api, boardId, stage }: { api: Api; boardId: string; stage: string }) {
  const engine = useMemo(() => new SyncEngine(api, api.sockets(), boardId), [boardId]); // eslint-disable-line
  const [, rerender] = useReducer((x: number) => x + 1, 0);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  useEffect(() => {
    engine.onChange = rerender;
    if (stage !== "prod") (window as unknown as { __tl?: unknown }).__tl = engine; // e2e hook (pause/resume)
    engine.start().then(() => setLive(true)).catch((e: Error) => setError(e.message));
    return () => engine.stop();
  }, [engine]);

  if (error) return <div className="center error">{error}</div>;
  if (!engine.schema) return <div className="center muted">Loading board…</div>;
  const { schema } = engine;
  const groups = new Map(schema.groups.map((g) => [g.id, g]));

  // flat list of rows: group headers + items, windowed (virtualization)
  type Row = { kind: "group"; id: string } | { kind: "item"; id: string };
  const rows: Row[] = [];
  let lastGroup: string | null = null;
  for (const id of engine.order) {
    const it = engine.store.view(id);
    if (!it) continue;
    if (it.group_id !== lastGroup) { rows.push({ kind: "group", id: it.group_id }); lastGroup = it.group_id; }
    rows.push({ kind: "item", id });
  }
  const height = scroller.current?.clientHeight ?? 600;
  const first = Math.max(0, Math.floor(scrollTop / ROW_H) - 10);
  const last = Math.min(rows.length, Math.ceil((scrollTop + height) / ROW_H) + 10);

  const save = async (itemId: string, col: string, value: unknown) => {
    const mid = crypto.randomUUID();
    const rollback = engine.store.setOptimistic(itemId, col, value, mid);
    try {
      const r = await api.setValues(itemId, { [col]: value }, mid);
      engine.store.applyEvent({ item_id: itemId, version: r.version, values: r.values, mutation_id: mid });
    } catch (e) {
      rollback();
      setError(null);
      alertLater((e as Error).message);
    }
  };

  return (
    <main className="board">
      <div className="board-head">
        <h2 data-testid="board-name">{schema.board.name}</h2>
        <span className={live ? "dot live" : "dot"} data-testid="live" title={live ? "Live" : "Connecting"} />
      </div>
      <div className="grid-head" style={{ gridTemplateColumns: cols(schema.columns.length) }}>
        <div>Item</div>
        {schema.columns.map((c) => <div key={c.id}>{c.title}</div>)}
      </div>
      <div className="scroller" ref={scroller} onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}>
        <div style={{ height: rows.length * ROW_H, position: "relative" }}>
          {rows.slice(first, last).map((r, i) => {
            const top = (first + i) * ROW_H;
            if (r.kind === "group") {
              const g = groups.get(r.id);
              return <div key={`g${r.id}`} className="group-row" style={{ top, borderColor: g?.color }}>{g?.title}</div>;
            }
            const it = engine.store.view(r.id)!;
            return (
              <div key={r.id} className="item-row" data-testid={`row-${r.id}`} data-version={it.version}
                   style={{ top, gridTemplateColumns: cols(schema.columns.length) }}>
                <div className="name">{it.name}</div>
                {schema.columns.map((c) => (
                  <Cell key={c.id} itemId={r.id} column={c} value={it.values[c.id]} pending={it.pending.includes(c.id)}
                        onSave={(v) => save(r.id, c.id, v)} />
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </main>
  );
}

const cols = (n: number) => `minmax(200px, 2fr) ${"minmax(140px, 1fr) ".repeat(n)}`;
const alertLater = (msg: string) => setTimeout(() => console.warn(`Save failed: ${msg}`), 0);
