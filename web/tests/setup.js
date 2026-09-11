import "@testing-library/jest-dom/vitest";

// Next.js's useSearchParams() is imported from next/navigation, which
// pulls in the full Next runtime. Stub it with a deterministic empty
// URLSearchParams so the workbench component renders under jsdom.
import { vi } from "vitest";

// jsdom has no layout engine. The shared command palette uses these
// browser APIs only to size and scroll its visible result list.
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
HTMLElement.prototype.scrollIntoView = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
