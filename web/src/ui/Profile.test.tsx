/** Profile page (A16): name, title, phone, timezone (blank = account default). */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Profile, type Me, type ProfileApi } from "./Profile";

afterEach(cleanup);

describe("Profile", () => {
  it("saves changed fields and clears the timezone to the account default", async () => {
    let me: Me = { id: "45", email: "r@example.com", name: "Raj", title: null, phone: null, timezone: "Asia/Kolkata",
                   effective_timezone: "Asia/Kolkata", role: "member", capabilities: [] };
    const saves: Partial<Me>[] = [];
    const api: ProfileApi = {
      me: vi.fn(async () => me),
      updateMe: vi.fn(async (p: Partial<Me>) => { saves.push(p); me = { ...me, ...p }; return me; }),
    };
    render(<Profile api={api} />);
    fireEvent.change(await screen.findByTestId("profile-title"), { target: { value: "Sales rep" } });
    fireEvent.change(screen.getByTestId("profile-timezone"), { target: { value: "" } });
    fireEvent.click(screen.getByTestId("profile-save"));
    await waitFor(() => expect(saves).toEqual([{ title: "Sales rep", timezone: null }]));
  });
});
