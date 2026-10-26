import type { BoardApi, Schema, Socket, SocketFactory } from "./sync/engine";
import type { ServerItem } from "./sync/types";
import type { AppConfig } from "./config";
import type { NavTree } from "./ui/LeftNav";
import type { AdminUser, Role } from "./ui/UsersAdmin";

export class ApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string, readonly fields?: Record<string, string>) {
    super(message);
  }
}

export class Api implements BoardApi {
  constructor(private readonly cfg: AppConfig, private readonly token: () => Promise<string>) {}

  private async call<T>(method: string, path: string, body?: unknown): Promise<T> {
    const r = await fetch(`${this.cfg.apiBase}${path}`, {
      method,
      headers: { authorization: `Bearer ${await this.token()}`, "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = r.status === 204 ? null : await r.json().catch(() => null);
    if (!r.ok) {
      const e = data?.error ?? {};
      throw new ApiError(r.status, e.code ?? "error", e.message ?? r.statusText, e.fields);
    }
    return data as T;
  }

  me() {
    return this.call<{ id: string; name: string; email: string; role: string; capabilities: string[] }>("GET", "/me");
  }
  nav() { return this.call<NavTree>("GET", "/nav"); }
  async listUsers() { return (await this.call<{ users: AdminUser[] }>("GET", "/users")).users; }
  inviteUser(email: string, name: string, role: Role) {
    return this.call<AdminUser>("POST", "/users", { email, name, role });
  }
  updateUser(id: string, patch: Partial<Pick<AdminUser, "role" | "status">>) {
    return this.call<AdminUser>("PATCH", `/users/${id}`, patch);
  }
  async resendInvite(id: string) { await this.call<unknown>("POST", `/users/${id}/resend-invite`); }
  async revokeInvite(id: string) { await this.call<unknown>("DELETE", `/users/${id}`); }
  createWorkspace(name: string, kind: "open" | "closed") {
    return this.call<{ id: string; name: string; kind: string }>("POST", "/workspaces", { name, kind });
  }
  async moveBoard(boardId: string, beforeId: string | null) {
    await this.call<unknown>("POST", `/boards/${boardId}/move`, { before_id: beforeId });
  }
  schema(b: string) { return this.call<Schema>("GET", `/boards/${b}/schema`); }
  query(b: string) { return this.call<{ ids: string[]; groups: { id: string; count: number }[] }>("POST", `/boards/${b}/query`, {}); }
  async fetch(b: string, ids: string[]) {
    return (await this.call<{ items: ServerItem[] }>("POST", `/boards/${b}/items:fetch`, { ids })).items;
  }
  changes(b: string, since: string | null) {
    return this.call<{ next_since_xmin: string; db_generation: number; changes: { item_id: string }[] }>(
      "POST", `/boards/${b}/changes`, since === null ? {} : { since_xmin: since });
  }
  setValues(itemId: string, values: Record<string, unknown>, mutationId: string) {
    return this.call<{ id: string; version: number; values: Record<string, unknown> }>(
      "PATCH", `/items/${itemId}/values`, { values, mutation_id: mutationId });
  }
  ticket() { return this.call<{ ticket: string; url: string }>("POST", "/realtime/ticket", {}); }

  /** WebSocket via the same origin (CloudFront /ws), authenticated by a single-use ticket. */
  sockets(): SocketFactory {
    return {
      open: async (h) => {
        const { ticket, url } = await this.ticket();
        const base = url.startsWith("/") ? `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${url}` : url;
        const ws = new WebSocket(`${base}?ticket=${encodeURIComponent(ticket)}`);
        let ping: ReturnType<typeof setInterval> | undefined;
        await new Promise<void>((resolve, reject) => {
          ws.onopen = () => { h.onOpen(); resolve(); };
          ws.onerror = () => reject(new Error("WebSocket failed"));
        });
        ws.onmessage = (m) => { try { h.onMessage(JSON.parse(m.data as string)); } catch { /* ignore */ } };
        ws.onclose = () => { if (ping) clearInterval(ping); h.onClose(); };
        ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ action: "ping" })), 5 * 60_000);
        const sock: Socket = { send: (msg) => ws.send(JSON.stringify(msg)), close: () => ws.close() };
        return sock;
      },
    };
  }
}
