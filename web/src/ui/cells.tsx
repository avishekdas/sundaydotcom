import { useEffect, useRef, useState } from "react";

interface Column { id: string; title: string; type: string; settings: Record<string, unknown> }
interface Label { id: number; text: string; color: string }

export function Cell(p: { itemId: string; column: Column; value: unknown; pending: boolean; onSave: (v: unknown) => void }) {
  const cls = `cell${p.pending ? " pending" : ""}`;
  const testid = `cell-${p.itemId}-${p.column.id}`;
  if (p.column.type === "status") return <StatusCell {...p} cls={cls} testid={testid} />;
  return <TextCell {...p} cls={cls} testid={testid} numeric={p.column.type === "numbers"} />;
}

function StatusCell({ column, value, onSave, cls, testid }: { column: Column; value: unknown; onSave: (v: unknown) => void; cls: string; testid: string }) {
  const [open, setOpen] = useState(false);
  const labels = (column.settings.labels as Label[] | undefined) ?? [];
  const cur = labels.find((l) => l.id === (value as { l?: number } | undefined)?.l);
  return (
    <div className={`${cls} status`}>
      <button data-testid={testid} data-label={cur?.text ?? ""} className="status-pill"
              style={{ background: cur?.color ?? "#c4c4c4" }} onClick={() => setOpen((o) => !o)}>
        {cur?.text ?? " "}
      </button>
      {open && (
        <ul className="menu" role="menu">
          {labels.map((l) => (
            <li key={l.id}>
              <button role="menuitem" data-testid={`${testid}-opt-${l.id}`} style={{ background: l.color }}
                      onClick={() => { setOpen(false); onSave({ l: l.id }); }}>{l.text}</button>
            </li>
          ))}
          <li><button role="menuitem" className="clear" onClick={() => { setOpen(false); onSave(null); }}>Clear</button></li>
        </ul>
      )}
    </div>
  );
}

function TextCell({ value, onSave, cls, testid, numeric }: { value: unknown; onSave: (v: unknown) => void; cls: string; testid: string; numeric: boolean }) {
  const shown = value == null ? "" : String(value);
  const [draft, setDraft] = useState(shown);
  const focused = useRef(false);
  useEffect(() => { if (!focused.current) setDraft(shown); }, [shown]);
  return (
    <div className={cls}>
      <input data-testid={testid} value={draft} inputMode={numeric ? "decimal" : undefined}
             className={numeric ? "num" : undefined}
             onFocus={() => (focused.current = true)}
             onChange={(e) => setDraft(e.target.value)}
             onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
             onBlur={() => { focused.current = false; if (draft !== shown) onSave(draft === "" ? null : draft); }} />
    </div>
  );
}
