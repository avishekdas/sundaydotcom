/** Admin "Users" page (F1, K1): list, invite, change role, deactivate / reactivate, resend or revoke an invite. */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UsersAdmin, type AdminUser, type UsersApi } from "./UsersAdmin";

function fakeApi(): UsersApi & { calls: string[] } {
  let users: AdminUser[] = [
    { id: "1", email: "ada@example.com", name: "Ada", role: "admin", status: "active" },
    { id: "2", email: "raj@example.com", name: "Raj", role: "member", status: "active" },
    { id: "3", email: "new@example.com", name: "New", role: "viewer", status: "invited" },
  ];
  const calls: string[] = [];
  return {
    calls,
    listUsers: vi.fn(async () => users),
    inviteUser: vi.fn(async (email: string, name: string, role: string) => {
      calls.push(`invite:${email}:${role}`);
      const u = { id: "9", email, name, role, status: "invited" } as AdminUser;
      users = [...users, u];
      return u;
    }),
    updateUser: vi.fn(async (id: string, patch: Partial<AdminUser>) => {
      calls.push(`patch:${id}:${JSON.stringify(patch)}`);
      users = users.map((u) => (u.id === id ? { ...u, ...patch } : u));
      return users.find((u) => u.id === id)!;
    }),
    resendInvite: vi.fn(async (id: string) => { calls.push(`resend:${id}`); }),
    revokeInvite: vi.fn(async (id: string) => { calls.push(`revoke:${id}`); users = users.filter((u) => u.id !== id); }),
  };
}

afterEach(cleanup);

describe("UsersAdmin", () => {
  it("lists users with role and status", async () => {
    render(<UsersAdmin api={fakeApi()} />);
    const row = await screen.findByTestId("user-2");
    expect(within(row).getByText("raj@example.com")).toBeTruthy();
    expect(within(screen.getByTestId("user-3")).getByText(/invited/i)).toBeTruthy();
  });

  it("invites a user", async () => {
    const api = fakeApi();
    render(<UsersAdmin api={api} />);
    await screen.findByTestId("user-1");
    fireEvent.change(screen.getByTestId("invite-email"), { target: { value: "sam@example.com" } });
    fireEvent.change(screen.getByTestId("invite-name"), { target: { value: "Sam" } });
    fireEvent.change(screen.getByTestId("invite-role"), { target: { value: "viewer" } });
    fireEvent.click(screen.getByTestId("invite-send"));
    await waitFor(() => expect(api.calls).toContain("invite:sam@example.com:viewer"));
    expect(await screen.findByTestId("user-9")).toBeTruthy();
  });

  it("changes a role and deactivates / reactivates", async () => {
    const api = fakeApi();
    render(<UsersAdmin api={api} />);
    await screen.findByTestId("user-2");
    fireEvent.change(screen.getByTestId("role-2"), { target: { value: "viewer" } });
    await waitFor(() => expect(api.calls).toContain('patch:2:{"role":"viewer"}'));
    fireEvent.click(screen.getByTestId("deactivate-2"));
    await waitFor(() => expect(api.calls).toContain('patch:2:{"status":"deactivated"}'));
    fireEvent.click(await screen.findByTestId("reactivate-2"));
    await waitFor(() => expect(api.calls).toContain('patch:2:{"status":"active"}'));
  });

  it("resends or revokes a pending invite", async () => {
    const api = fakeApi();
    render(<UsersAdmin api={api} />);
    fireEvent.click(await screen.findByTestId("resend-3"));
    await waitFor(() => expect(api.calls).toContain("resend:3"));
    fireEvent.click(screen.getByTestId("revoke-3"));
    await waitFor(() => expect(screen.queryByTestId("user-3")).toBeNull());
  });

  it("shows server errors (e.g. last admin)", async () => {
    const api = fakeApi();
    api.updateUser = vi.fn(async () => { throw new Error("A workspace needs at least one admin"); });
    render(<UsersAdmin api={api} />);
    await screen.findByTestId("user-1");
    fireEvent.click(screen.getByTestId("deactivate-1"));
    expect((await screen.findByRole("alert")).textContent).toContain("at least one admin");
  });
});
