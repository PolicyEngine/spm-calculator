import "@testing-library/jest-dom/vitest";

// Next.js's useSearchParams() is imported from next/navigation, which
// pulls in the full Next runtime. Stub it with a deterministic empty
// URLSearchParams so the workbench component renders under jsdom.
import { vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
