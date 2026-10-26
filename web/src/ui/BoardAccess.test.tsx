/** Board access panel for owners (B2, B3, K3): kind, permission set, members; Private → Main asks first (B2.4). */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BoardAccess, type BoardAccessApi, type BoardInfo } from "./BoardAccess";

afterEach(cleanup);

function fakeApi(): BoardAccessApi & { calls: string[] } {
  let b: BoardInfo = { id: "90", name: "Deals", kind: "private", permission_set: "edit_everything",
    members: [{ user_id: "44", name: "Mia", role: "owner", subscribed: true }] };
  const calls: string[] = [];
  return {
    calls,
    board: vi.fn(async () => b),
    updateBoard: vi.fn(async (_id: string, p: Partial<BoardInfo>) => { calls.push(`patch:${JSON.stringify(p)}`); b = { ...b, ...p }; return b; }),
    putBoardMember: vi.fn(async (_id: string, user: string, role: string) => { calls.push(`put:${user}:${role}`);
      b = { ...b, members: [...b.members, { user_id: user, name: "Raj", role: role as "owner" | "member", subscribed: true }] }; return b; }),
    removeBoardMember: vi.fn(async (_id: string, user: string) => { calls.push(`del:${user}`); }),
    listUsers: vi.fn(async () => [{ id: "45", name: "Raj", email: "r@example.com" }]),
  };
}

describe("BoardAccess", () => {
  it("changes the permission set and adds a member", async () => {
    const api = fakeApi();
    render(<BoardAccess api={api} boardId="90" />);
    fireEvent.change(await screen.findByTestId("board-permission-set"), { target: { value: "edit_content" } });
    await waitFor(() => expect(api.calls).toContain('patch:{"permission_set":"edit_content"}'));
    fireEvent.change(screen.getByTestId("member-pick"), { target: { value: "45" } });
    fireEvent.click(screen.getByTestId("member-add"));
    await waitFor(() => expect(api.calls).toContain("put:45:member"));
  });

  it("asks before making a private board Main (B2.4)", async () => {
    const api = fakeApi();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<BoardAccess api={api} boardId="90" />);
    fireEvent.change(await screen.findByTestId("board-kind"), { target: { value: "main" } });
    expect(api.calls).toEqual([]);
    fireEvent.change(screen.getByTestId("board-kind"), { target: { value: "main" } });
    await waitFor(() => expect(api.calls).toContain('patch:{"kind":"main"}'));
    expect(confirm).toHaveBeenCalledTimes(2);
  });
});
