import { describe, expect, it, vi } from "vitest";

import type { CoreState, Snapshot } from "./core";

let stateCb: ((state: CoreState) => void) | null = null;
let resolveSnapshot: ((snapshot: Snapshot) => void) | null = null;

vi.mock("./core", () => ({
  onState: (cb: (state: CoreState) => void) => {
    stateCb = cb;
    return Promise.resolve(() => {});
  },
  onSubtitles: () => Promise.resolve(() => {}),
  onExited: () => Promise.resolve(() => {}),
  snapshot: () =>
    new Promise<Snapshot>((resolve) => {
      resolveSnapshot = resolve;
    }),
}));

function fakeState(title: string): CoreState {
  return {
    app: { statusTitle: title },
    settings: {},
    models: {},
  } as unknown as CoreState;
}

describe("initStore ordering", () => {
  it("an event arriving before the snapshot resolves wins", async () => {
    const { core, initStore } = await import("./store.svelte");
    const pending = initStore();

    await vi.waitFor(() => expect(stateCb).not.toBeNull());
    await vi.waitFor(() => expect(resolveSnapshot).not.toBeNull());

    // Event lands while the snapshot request is still in flight.
    const fresh = fakeState("event-wins");
    stateCb!(fresh);
    resolveSnapshot!({ state: fakeState("stale"), subtitles: [] });

    await pending;
    expect(core.state).toBe(fresh);
    expect(core.state?.app.statusTitle).toBe("event-wins");
  });
});
