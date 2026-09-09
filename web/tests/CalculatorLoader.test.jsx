import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import Page from "../app/page";
import {
  expandCalculatorData,
  loadCalculatorData,
} from "../lib/loadCalculatorData";
import CalculatorLoader from "../src/components/CalculatorLoader";
import { makeRollingCalculatorData } from "./fixtures/rollingCalculatorData";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
});

function compactFixture(data = makeRollingCalculatorData()) {
  const { areasByYear = {}, forecast, ...metadata } = data;
  const areaMenus = [];
  const areaMenuByYear = {};
  for (const [year, areas] of Object.entries(areasByYear)) {
    areaMenuByYear[year] = areaMenus.length;
    areaMenus.push(areas);
  }
  const geographies = [];
  const scenarios = Object.fromEntries(
    Object.entries(forecast.scenarios).map(([id, scenario]) => [
      id,
      {
        ...scenario,
        years: Object.fromEntries(
          Object.entries(scenario.years).map(([year, entry]) => {
            const {
              rent_indices,
              geography_by_area,
              median_diagnostics,
              ...inputs
            } = entry;
            const geographyRef = geographies.length;
            geographies.push({
              rent_indices,
              geography_by_area,
              median_diagnostics,
            });
            return [year, { ...inputs, geographyRef }];
          }),
        ),
      },
    ]),
  );
  return {
    ...metadata,
    uiSchemaVersion: 1,
    areaMenus,
    areaMenuByYear,
    geographies,
    forecast: { ...forecast, scenarios },
  };
}

function mockDataResponse(data = makeRollingCalculatorData()) {
  return { ok: true, json: vi.fn().mockResolvedValue(compactFixture(data)) };
}

describe("calculator data loading", () => {
  it("expands pooled data without changing inputs or retaining wire-only fields", () => {
    const data = makeRollingCalculatorData();
    const wire = compactFixture(data);
    const expanded = expandCalculatorData(wire);
    expect(expanded).toEqual(data);
    const scenario =
      expanded.forecast.scenarios[expanded.forecast.defaultScenario];
    expect(scenario.years[2022].rent_indices).toBe(
      wire.geographies[0].rent_indices,
    );
    expect(expanded.areasByYear[2022]).toBe(wire.areaMenus[0]);
    expect(expanded).not.toHaveProperty("geographies");
    expect(expanded).not.toHaveProperty("areaMenus");
    expect(expanded).not.toHaveProperty("areaMenuByYear");
    expect(scenario.years[2022]).not.toHaveProperty("geographyRef");
  });

  it.each(["version", "menu", "geography", "negative", "fractional"])(
    "rejects an invalid compact %s reference or version",
    (invalid) => {
      const wire = compactFixture();
      if (invalid === "version") wire.uiSchemaVersion = 2;
      if (invalid === "menu") wire.areaMenuByYear[2022] = 999;
      const year =
        wire.forecast.scenarios[wire.forecast.defaultScenario].years[2022];
      if (invalid === "geography") year.geographyRef = 999;
      if (invalid === "negative") year.geographyRef = -1;
      if (invalid === "fractional") year.geographyRef = 0.5;
      expect(() => expandCalculatorData(wire)).toThrow(/format|reference/);
    },
  );

  it.each(["", "/us/spm-calculator", "/us/spm-calculator/"])(
    "requests compact data with the configured base path %j",
    async (basePath) => {
      vi.stubEnv("NEXT_PUBLIC_BASE_PATH", basePath);
      const data = makeRollingCalculatorData();
      const fetch = vi.fn().mockResolvedValue(mockDataResponse(data));
      vi.stubGlobal("fetch", fetch);
      const controller = new AbortController();

      await expect(
        loadCalculatorData({ signal: controller.signal }),
      ).resolves.toEqual(data);
      expect(fetch).toHaveBeenCalledExactlyOnceWith(
        `${basePath.replace(/\/+$/, "")}/data/release_config.json`,
        { signal: controller.signal, cache: "no-cache" },
      );
    },
  );

  it("rejects unsuccessful HTTP responses before reading their body", async () => {
    const json = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, json }),
    );
    await expect(loadCalculatorData()).rejects.toThrow("failed (404)");
    expect(json).not.toHaveBeenCalled();
  });

  it.each(["schema", "scenario", "year", "areas"])(
    "rejects an incomplete %s payload before rendering the calculator",
    async (missing) => {
      const data = makeRollingCalculatorData();
      if (missing === "schema") data.schemaVersion = 999;
      if (missing === "scenario") data.forecast.defaultScenario = "missing";
      if (missing === "year") {
        delete data.forecast.scenarios[data.forecast.defaultScenario]
          .years[2035];
      }
      if (missing === "areas") delete data.areasByYear[2022];
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(mockDataResponse(data)));
      await expect(loadCalculatorData()).rejects.toThrow("incomplete");
    },
  );

  it("server-renders a small loading shell without fetching or embedding calculator inputs", () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const html = renderToString(<Page />);
    expect(html).toContain("Loading thresholds and geographic inputs");
    expect(html).toContain("Enable JavaScript");
    expect(html).not.toMatch(/rent_indices|contentSha256|ce_trend/);
    expect(html.length).toBeLessThan(10_000);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("announces loading and renders the real calculator after one successful request", async () => {
    let resolveResponse;
    const fetch = vi.fn().mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveResponse = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetch);
    render(<CalculatorLoader />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading thresholds");
    expect(screen.queryByLabelText("Threshold year")).toBeNull();

    await act(async () => resolveResponse(mockDataResponse()));
    expect(await screen.findByLabelText("Threshold year")).toHaveValue("2025");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$50,041");
    expect(screen.queryByRole("status")).toBeNull();
    fireEvent.change(screen.getByLabelText("Threshold year"), {
      target: { value: "2035" },
    });
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
      "Unavailable",
    );
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it.each(["network", "http", "json", "invalid"])(
    "shows an accessible error after a %s failure and retries successfully",
    async (failure) => {
      const fetch = vi.fn();
      if (failure === "network")
        fetch.mockRejectedValueOnce(new TypeError("Offline"));
      if (failure === "http")
        fetch.mockResolvedValueOnce({ ok: false, status: 503 });
      if (failure === "json")
        fetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.reject(new SyntaxError("Invalid JSON")),
        });
      if (failure === "invalid")
        fetch.mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ schemaVersion: 2 }),
        });
      fetch.mockResolvedValueOnce(mockDataResponse());
      vi.stubGlobal("fetch", fetch);
      render(<CalculatorLoader />);

      expect(await screen.findByRole("alert")).toHaveTextContent(
        "We couldn’t load the calculator data",
      );
      expect(screen.queryByLabelText("Threshold year")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));
      expect(screen.getByRole("status")).toHaveTextContent(
        "Loading thresholds",
      );
      expect(await screen.findByLabelText("Threshold year")).toHaveValue(
        "2025",
      );
      expect(screen.queryByRole("alert")).toBeNull();
      expect(fetch).toHaveBeenCalledTimes(2);
      expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    },
  );

  it("aborts an unfinished request when the loader unmounts", async () => {
    const fetch = vi.fn().mockImplementation(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetch);
    const { unmount } = render(<CalculatorLoader />);
    await waitFor(() => expect(fetch).toHaveBeenCalledOnce());
    const signal = fetch.mock.calls[0][1].signal;
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it("ends a stalled request after 30 seconds and permits a fresh retry", async () => {
    vi.useFakeTimers();
    const fetch = vi
      .fn()
      .mockImplementationOnce(() => new Promise(() => {}))
      .mockResolvedValueOnce(mockDataResponse());
    vi.stubGlobal("fetch", fetch);
    render(<CalculatorLoader />);
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(screen.getByRole("alert")).toHaveTextContent("We couldn’t load");
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Try again" })),
    );
    expect(screen.getByLabelText("Threshold year")).toHaveValue("2025");
    expect(fetch).toHaveBeenCalledTimes(2);
  });
});
