/**
 * Left navigation (A4, AC-A4-1/2, A2): workspace tree from GET /nav, filter box, "New workspace", board reorder.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LeftNav, type NavApi, type NavTree } from "./LeftNav";

const tree = (extra: NavTree["workspaces"] = []): NavTree => ({
  workspaces: [
    { id: "1", name: "Main workspace", kind: "open", breadcrumb_only: false,
      boards: [{ id: "10", name: "Deals" }, { id: "20", name: "Contacts" }, { id: "30", name: "Leads" }] },
    ...extra,
  ],
});

function fakeApi(initial: NavTree): NavApi & { calls: string[] } {
  let current = initial;
  const calls: string[] = [];
  return {
    calls,
    nav: vi.fn(async () => current),
    createWorkspace: vi.fn(async (name: string, kind: "open" | "closed") => {
      calls.push(`create:${name}:${kind}`);
      current = tree([{ id: "9", name, kind, breadcrumb_only: false, boards: [] }]);
      return { id: "9", name, kind };
    }),
    moveBoard: vi.fn(async (boardId: string, beforeId: string | null) => {
      calls.push(`move:${boardId}:${beforeId}`);
    }),
  };
}

afterEach(cleanup);

describe("LeftNav", () => {
  it("shows workspaces and their boards", async () => {
    render(<LeftNav api={fakeApi(tree())} canCreateWorkspace onOpenBoard={() => {}} />);
    const nav = await screen.findByTestId("left-nav");
    expect(within(nav).getByText("Main workspace")).toBeTruthy();
    expect(within(nav).getAllByRole("link").map((a) => a.textContent)).toEqual(["Deals", "Contacts", "Leads"]);
  });

  it("filters boards by name, case-insensitive (A4.3)", async () => {
    render(<LeftNav api={fakeApi(tree())} canCreateWorkspace onOpenBoard={() => {}} />);
    await screen.findByText("Deals");
    fireEvent.change(screen.getByTestId("nav-filter"), { target: { value: "CON" } });
    expect(screen.getAllByRole("link").map((a) => a.textContent)).toEqual(["Contacts"]);
  });

  it("creates a workspace and shows it (north-star 1a)", async () => {
    const api = fakeApi(tree());
    render(<LeftNav api={api} canCreateWorkspace onOpenBoard={() => {}} />);
    fireEvent.click(await screen.findByTestId("new-workspace"));
    fireEvent.change(screen.getByTestId("workspace-name"), { target: { value: "Sales" } });
    fireEvent.click(screen.getByTestId("workspace-closed"));
    fireEvent.click(screen.getByTestId("workspace-create"));
    await waitFor(() => expect(within(screen.getByTestId("left-nav")).getByText("Sales")).toBeTruthy());
    expect(api.calls).toContain("create:Sales:closed");
  });

  it("hides New workspace without the capability (K1)", async () => {
    render(<LeftNav api={fakeApi(tree())} canCreateWorkspace={false} onOpenBoard={() => {}} />);
    await screen.findByText("Deals");
    expect(screen.queryByTestId("new-workspace")).toBeNull();
  });

  it("moves a board up and down (keyboard-reachable reorder, A4.2)", async () => {
    const api = fakeApi(tree());
    render(<LeftNav api={api} canCreateWorkspace onOpenBoard={() => {}} />);
    await screen.findByText("Leads");
    fireEvent.click(screen.getByTestId("move-up-30"));
    await waitFor(() => expect(api.calls).toContain("move:30:20"));
    fireEvent.click(screen.getByTestId("move-down-10"));
    await waitFor(() => expect(api.calls).toContain("move:10:30"));
  });

  it("opens a board on click", async () => {
    const open = vi.fn();
    render(<LeftNav api={fakeApi(tree())} canCreateWorkspace onOpenBoard={open} />);
    fireEvent.click(await screen.findByText("Contacts"));
    expect(open).toHaveBeenCalledWith("20");
  });
});
