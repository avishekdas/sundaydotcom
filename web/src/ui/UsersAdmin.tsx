/**
 * Admin "Users" page (F1, K1): invite by email with a role (Cognito emails a temporary password, D-054), change
 * roles, deactivate / reactivate (sessions revoked, F1.3), resend or revoke a pending invite. Server rules (last
 * admin, duplicates) come back as errors shown in place.
 */
import { useCallback, useEffect, useState } from "react";

export type Role = "admin" | "member" | "viewer";
export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  status: "invited" | "active" | "deactivated";
}

export interface UsersApi {
  listUsers(): Promise<AdminUser[]>;
  inviteUser(email: string, name: string, role: Role): Promise<AdminUser>;
  updateUser(id: string, patch: Partial<Pick<AdminUser, "role" | "status">>): Promise<AdminUser>;
  resendInvite(id: string): Promise<void>;
  revokeInvite(id: string): Promise<void>;
}

const ROLES: Role[] = ["admin", "member", "viewer"];

export function UsersAdmin({ api }: { api: UsersApi }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState<Role>("member");

  const reload = useCallback(async () => {
    try { setUsers(await api.listUsers()); } catch (e) { setError((e as Error).message); }
  }, [api]);
  useEffect(() => { void reload(); }, [reload]);

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try { await fn(); await reload(); } catch (e) { setError((e as Error).message); }
  };

  return (
    <section className="admin">
      <h1>Users</h1>
      <form className="invite" onSubmit={(e) => {
        e.preventDefault();
        void act(async () => { await api.inviteUser(email, name, role); setEmail(""); setName(""); });
      }}>
        <input data-testid="invite-email" type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <input data-testid="invite-name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <select data-testid="invite-role" value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Role">
          {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <button data-testid="invite-send">Invite</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      <table className="users">
        <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th /></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} data-testid={`user-${u.id}`} className={u.status}>
              <td>{u.name}</td>
              <td>{u.email}</td>
              <td>
                <select data-testid={`role-${u.id}`} aria-label={`Role of ${u.name}`} value={u.role}
                        onChange={(e) => void act(() => api.updateUser(u.id, { role: e.target.value as Role }))}>
                  {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </td>
              <td>{u.status === "invited" ? "Invited" : u.status === "active" ? "Active" : "Deactivated"}</td>
              <td className="actions">
                {u.status === "invited" && <>
                  <button className="small" data-testid={`resend-${u.id}`} onClick={() => void act(() => api.resendInvite(u.id))}>Resend</button>
                  <button className="small" data-testid={`revoke-${u.id}`} onClick={() => void act(() => api.revokeInvite(u.id))}>Revoke</button>
                </>}
                {u.status === "active" && (
                  <button className="small" data-testid={`deactivate-${u.id}`} onClick={() => void act(() => api.updateUser(u.id, { status: "deactivated" }))}>Deactivate</button>
                )}
                {u.status === "deactivated" && (
                  <button className="small" data-testid={`reactivate-${u.id}`} onClick={() => void act(() => api.updateUser(u.id, { status: "active" }))}>Reactivate</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
