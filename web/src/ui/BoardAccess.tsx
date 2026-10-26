/** Board access for owners (B2, B3, K3): kind, permission set and members. Making a private board Main asks first. */
import { useCallback, useEffect, useState } from "react";

export type BoardKind = "main" | "private";
export type PermissionSet = "edit_everything" | "edit_content" | "view_comment";
export interface BoardMember { user_id: string; name: string; role: "owner" | "member"; subscribed: boolean }
export interface BoardInfo { id: string; name: string; kind: BoardKind; permission_set: PermissionSet; members: BoardMember[] }

export interface BoardAccessApi {
  board(id: string): Promise<BoardInfo>;
  updateBoard(id: string, patch: Partial<Pick<BoardInfo, "kind" | "permission_set">>): Promise<BoardInfo>;
  putBoardMember(id: string, userId: string, role: "owner" | "member"): Promise<BoardInfo>;
  removeBoardMember(id: string, userId: string): Promise<void>;
  listUsers(): Promise<{ id: string; name: string; email: string }[]>;
}

const SETS: [PermissionSet, string][] = [
  ["edit_everything", "Edit everything"], ["edit_content", "Only edit content"], ["view_comment", "View and comment"],
];

export function BoardAccess({ api, boardId }: { api: BoardAccessApi; boardId: string }) {
  const [board, setBoard] = useState<BoardInfo | null>(null);
  const [people, setPeople] = useState<{ id: string; name: string; email: string }[]>([]);
  const [pick, setPick] = useState("");
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try { setBoard(await api.board(boardId)); } catch (e) { setError((e as Error).message); }
  }, [api, boardId]);
  useEffect(() => { void reload(); api.listUsers().then(setPeople).catch(() => setPeople([])); }, [api, reload]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); await reload(); } catch (e) { setError((e as Error).message); }
  };
  if (!board) return <section className="access">{error ?? "Loading…"}</section>;
  const memberIds = new Set(board.members.map((m) => m.user_id));
  return (
    <section className="access" aria-label="Board access">
      <h2>Access to {board.name}</h2>
      <label>Board type
        <select data-testid="board-kind" value={board.kind} onChange={(e) => {
          const kind = e.target.value as BoardKind;
          if (kind === "main" && board.kind === "private"
              && !window.confirm("Make this board visible to everyone in the workspace?")) return;
          void act(() => api.updateBoard(boardId, { kind }));
        }}>
          <option value="main">Main (everyone in the workspace)</option>
          <option value="private">Private (invited people)</option>
        </select>
      </label>
      <label>What non-owners can do
        <select data-testid="board-permission-set" value={board.permission_set}
                onChange={(e) => void act(() => api.updateBoard(boardId, { permission_set: e.target.value as PermissionSet }))}>
          {SETS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </label>
      <ul className="members">
        {board.members.map((m) => (
          <li key={m.user_id}>
            <span>{m.name}</span>
            <select aria-label={`Role of ${m.name}`} value={m.role}
                    onChange={(e) => void act(() => api.putBoardMember(boardId, m.user_id, e.target.value as "owner" | "member"))}>
              <option value="owner">Owner</option><option value="member">Member</option>
            </select>
            <button className="small" onClick={() => void act(() => api.removeBoardMember(boardId, m.user_id))}>Remove</button>
          </li>
        ))}
      </ul>
      <div className="add-member">
        <select data-testid="member-pick" aria-label="Person to add" value={pick} onChange={(e) => setPick(e.target.value)}>
          <option value="">Add a person…</option>
          {people.filter((p) => !memberIds.has(p.id)).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.email})</option>)}
        </select>
        <button className="small" data-testid="member-add" disabled={!pick}
                onClick={() => void act(async () => { await api.putBoardMember(boardId, pick, "member"); setPick(""); })}>Add</button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
