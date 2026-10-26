/**
 * Left navigation (A4): workspaces from GET /nav (already permission-filtered, AC-A4-1), a case-insensitive filter
 * (A4.3), "New workspace" (A2, hidden without the capability) and a shared board order (A4.2) changed by drag-and-
 * drop or by the keyboard-reachable Move up / Move down buttons.
 */
import { useCallback, useEffect, useState } from "react";

export interface NavBoard { id: string; name: string }
export interface NavWorkspace {
  id: string;
  name: string;
  kind: "open" | "closed";
  breadcrumb_only: boolean;
  boards: NavBoard[];
}
export interface NavTree { workspaces: NavWorkspace[] }

export interface NavApi {
  nav(): Promise<NavTree>;
  createWorkspace(name: string, kind: "open" | "closed"): Promise<{ id: string; name: string; kind: string }>;
  moveBoard(boardId: string, beforeId: string | null): Promise<void>;
}

export function LeftNav({ api, canCreateWorkspace, onOpenBoard, currentBoard }: {
  api: NavApi;
  canCreateWorkspace: boolean;
  onOpenBoard: (boardId: string) => void;
  currentBoard?: string;
}) {
  const [tree, setTree] = useState<NavTree | null>(null);
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try { setTree(await api.nav()); } catch (e) { setError((e as Error).message); }
  }, [api]);
  useEffect(() => { void reload(); }, [reload]);

  const move = async (boardId: string, beforeId: string | null) => {
    try { await api.moveBoard(boardId, beforeId); await reload(); } catch (e) { setError((e as Error).message); }
  };

  const q = filter.trim().toLowerCase();
  return (
    <nav className="leftnav" data-testid="left-nav" aria-label="Workspaces">
      <input
        className="nav-filter" data-testid="nav-filter" placeholder="Filter boards" aria-label="Filter boards"
        value={filter} onChange={(e) => setFilter(e.target.value)}
      />
      {canCreateWorkspace && (
        <button className="link" data-testid="new-workspace" onClick={() => setCreating(true)}>+ New workspace</button>
      )}
      {creating && (
        <NewWorkspace
          onCancel={() => setCreating(false)}
          onCreate={async (name, kind) => {
            await api.createWorkspace(name, kind);
            setCreating(false);
            await reload();
          }}
        />
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {tree?.workspaces.map((ws) => {
        const boards = q ? ws.boards.filter((b) => b.name.toLowerCase().includes(q)) : ws.boards;
        if (q && boards.length === 0) return null;
        return (
          <section key={ws.id} className="nav-ws">
            <h2 className="nav-ws-name" title={ws.kind === "closed" ? "Closed workspace" : undefined}>
              {ws.kind === "closed" && <span className="lock" aria-hidden="true">🔒</span>}
              <span>{ws.name}</span>
            </h2>
            <ul>
              {boards.map((b) => {
                const i = ws.boards.findIndex((x) => x.id === b.id);
                const prev = ws.boards[i - 1];
                const afterNext = ws.boards[i + 2];
                const next = ws.boards[i + 1];
                return (
                  <li
                    key={b.id}
                    className={b.id === currentBoard ? "current" : undefined}
                    draggable={!q}
                    onDragStart={() => setDragging(b.id)}
                    onDragOver={(e) => { if (dragging && dragging !== b.id) e.preventDefault(); }}
                    onDrop={(e) => { e.preventDefault(); if (dragging && dragging !== b.id) void move(dragging, b.id); setDragging(null); }}
                  >
                    <a href={`?board=${b.id}`} onClick={(e) => { e.preventDefault(); onOpenBoard(b.id); }}>{b.name}</a>
                    {!q && (
                      <span className="nav-move">
                        <button aria-label={`Move ${b.name} up`} data-testid={`move-up-${b.id}`} disabled={!prev}
                                onClick={() => prev && void move(b.id, prev.id)}>↑</button>
                        <button aria-label={`Move ${b.name} down`} data-testid={`move-down-${b.id}`} disabled={!next}
                                onClick={() => next && void move(b.id, afterNext ? afterNext.id : null)}>↓</button>
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </nav>
  );
}

function NewWorkspace({ onCreate, onCancel }: {
  onCreate: (name: string, kind: "open" | "closed") => Promise<void>;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"open" | "closed">("open");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form className="new-ws" onSubmit={async (e) => {
      e.preventDefault(); setBusy(true); setError(null);
      try { await onCreate(name, kind); } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
    }}>
      <label>Workspace name
        <input data-testid="workspace-name" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} required autoFocus />
      </label>
      <fieldset>
        <label><input type="radio" name="kind" data-testid="workspace-open" checked={kind === "open"} onChange={() => setKind("open")} /> Open</label>
        <label><input type="radio" name="kind" data-testid="workspace-closed" checked={kind === "closed"} onChange={() => setKind("closed")} /> Closed</label>
      </fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <button data-testid="workspace-create" disabled={busy}>Create</button>
      <button type="button" className="link" onClick={onCancel}>Cancel</button>
    </form>
  );
}
