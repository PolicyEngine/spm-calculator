import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ThresholdHistoryChart from "../src/components/ThresholdHistoryChart";

function row(year, overrides = {}) {
  return {
    year,
    nationalBase: 40000,
    adjustment: 1.1,
    localThreshold: 35200,
    nationalStatus: year <= 2025 ? "published" : "forecast",
    componentStatus:
      year <= 2025
        ? "Published national base; modeled geography; published shares"
        : "Forecast national base; modeled geography; modeled shares",
    housingShare: 0.4,
    rentIndex: 1.25,
    equivalenceScale: 0.8,
    ...overrides,
  };
}

describe("annual threshold chart", () => {
  it("keeps desktop breakdowns below the shared sticky header while scrolling and resizing", () => {
    let chartTop = -30;
    let popupMode = "absolute";
    let popupHeight = 260;
    const originalStyle = window.getComputedStyle;
    const originalBounds = Element.prototype.getBoundingClientRect;
    const styleSpy = vi
      .spyOn(window, "getComputedStyle")
      .mockImplementation((element, ...args) =>
        element.dataset?.testid === "threshold-history-popup"
          ? { position: popupMode }
          : originalStyle(element, ...args),
      );
    const boundsSpy = vi
      .spyOn(Element.prototype, "getBoundingClientRect")
      .mockImplementation(function () {
        if (this.dataset?.testid === "shared-header")
          return new DOMRect(0, 0, 1280, 58);
        if (this.dataset?.testid === "threshold-history-popup")
          return new DOMRect(0, 0, 320, popupHeight);
        if (
          this.querySelector(
            ':scope > [aria-label="Year-by-year threshold chart"]',
          )
        )
          return new DOMRect(360, chartTop, 880, 252);
        return originalBounds.call(this);
      });
    vi.stubGlobal("innerHeight", 720);
    try {
      render(
        <div>
          <div
            data-testid="shared-header"
            style={{ position: "sticky", top: 0 }}
          />
          <main>
            <aside />
            <main>
              <ThresholdHistoryChart data={[row(2025), row(2026)]} />
            </main>
          </main>
        </div>,
      );
      fireEvent.click(screen.getByTestId("threshold-year-2025"));
      const popup = screen.getByTestId("threshold-history-popup");
      expect(popup.style.top).toBe("96px"); // -30 chart top + 96 = 58 header + 8 gap.
      expect(popup.style.maxHeight).toBe("646px");

      chartTop = -70;
      fireEvent.scroll(window);
      expect(popup.style.top).toBe("136px");

      chartTop = 320;
      vi.stubGlobal("innerHeight", 400);
      fireEvent.resize(window);
      expect(Number.parseFloat(popup.style.top) + chartTop + popupHeight).toBe(
        392,
      );

      popupHeight = 500;
      fireEvent.resize(window);
      expect(popup.style.maxHeight).toBe("326px");
      expect(Number.parseFloat(popup.style.top) + chartTop).toBe(66);
      expect(popup.style.overflowY).toBe("auto");

      popupMode = "relative";
      fireEvent.resize(window);
      expect(popup.style.top).toBe("");
      expect(popup.style.maxHeight).toBe("");
    } finally {
      styleSpy.mockRestore();
      boundsSpy.mockRestore();
      vi.unstubAllGlobals();
    }
  });

  it("shows the complete breakdown on hover and preserves component status", () => {
    render(
      <ThresholdHistoryChart
        data={[row(2025), row(2026)]}
        selectedYear={2025}
      />,
    );
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.mouseEnter(screen.getByTestId("threshold-year-2025"));
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toHaveTextContent("2025");
    expect(tooltip).toHaveTextContent("$40,000 × 0.800 × 1.100 ≈ $35,200");
    expect(tooltip).toHaveTextContent(
      "GEOADJ = 1 + housing share × (rent index − 1)",
    );
    expect(tooltip).toHaveTextContent("1 + 0.400 × (1.250 − 1) ≈ 1.100");
    expect(tooltip).toHaveTextContent(
      "Published national base; modeled geography; published shares",
    );
    expect(screen.getByTestId("threshold-year-2025")).toHaveAttribute(
      "aria-describedby",
      tooltip.id,
    );
  });

  it("distinguishes published national inputs from forecasts at the boundary", () => {
    render(
      <ThresholdHistoryChart
        data={[row(2024), row(2025), row(2026), row(2027)]}
      />,
    );
    const segments = screen.getAllByTestId("threshold-history-segment");
    expect(segments).toHaveLength(3);
    expect(segments[0]).toHaveAttribute("data-from-year", "2024");
    expect(segments[0]).toHaveAttribute("data-status", "published");
    expect(segments[0]).not.toHaveAttribute("stroke-dasharray");
    for (const segment of segments.slice(1)) {
      expect(segment).toHaveAttribute("data-status", "forecast");
      expect(segment).toHaveAttribute("stroke-dasharray", "6 5");
    }
    expect(
      screen.getByText("Published national base", { exact: true }),
    ).toBeVisible();
    expect(screen.queryByText(/official local threshold/i)).toBeNull();
  });

  it("breaks the line at missing values and absent calendar years without inserting zeros", () => {
    render(
      <ThresholdHistoryChart
        data={[
          row(2022),
          row(2023, {
            localThreshold: null,
            adjustment: null,
            componentStatus: "Area unavailable",
          }),
          row(2024),
          row(2026),
          row(2027),
        ]}
      />,
    );
    const segments = screen.getAllByTestId("threshold-history-segment");
    expect(segments).toHaveLength(1);
    expect(segments[0]).toHaveAttribute("data-from-year", "2026");
    expect(segments[0]).toHaveAttribute("data-to-year", "2027");
    const missing = screen.getByTestId("threshold-year-2023");
    expect(missing).toHaveAccessibleName("2023: Unavailable. Area unavailable");
    expect(missing.querySelectorAll("circle")).toHaveLength(1); // Focus ring only.
    fireEvent.click(missing);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Unavailable");
    expect(screen.getByRole("tooltip")).not.toHaveTextContent("$0");
    expect(screen.getByText(/Gaps indicate unavailable/)).toBeVisible();
  });

  it("supports keyboard exploration, selection, and Escape without changing a year on arrow keys", () => {
    const onSelectYear = vi.fn();
    render(
      <ThresholdHistoryChart
        data={[row(2024), row(2025), row(2026)]}
        selectedYear={2025}
        onSelectYear={onSelectYear}
      />,
    );
    const selected = screen.getByTestId("threshold-year-2025");
    expect(selected).toHaveAttribute("tabindex", "0");
    expect(selected).toHaveAttribute("aria-current", "date");
    fireEvent.focus(selected);
    expect(screen.getByRole("tooltip")).toHaveTextContent("2025");
    fireEvent.keyDown(selected, { key: "ArrowRight" });
    const next = screen.getByTestId("threshold-year-2026");
    expect(next).toHaveFocus();
    expect(screen.getByRole("tooltip")).toHaveTextContent("2026");
    expect(onSelectYear).not.toHaveBeenCalled();
    fireEvent.keyDown(next, { key: "Enter" });
    expect(onSelectYear).toHaveBeenLastCalledWith(2026);
    fireEvent.keyDown(next, { key: "Home" });
    const first = screen.getByTestId("threshold-year-2024");
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: " " });
    expect(onSelectYear).toHaveBeenLastCalledWith(2024);
    fireEvent.keyDown(first, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("pins the same breakdown on tap and updates it when the input values change", () => {
    const onSelectYear = vi.fn();
    const { rerender } = render(
      <ThresholdHistoryChart data={[row(2026)]} onSelectYear={onSelectYear} />,
    );
    fireEvent.click(screen.getByTestId("threshold-year-2026"));
    expect(onSelectYear).toHaveBeenCalledWith(2026);
    expect(screen.getByRole("tooltip")).toHaveTextContent("$35,200");
    rerender(
      <ThresholdHistoryChart
        data={[row(2026, { localThreshold: 44000, equivalenceScale: 1 })]}
        onSelectYear={onSelectYear}
      />,
    );
    expect(screen.getByRole("tooltip")).toHaveTextContent(
      "$40,000 × 1.000 × 1.100 ≈ $44,000",
    );
  });

  it("keeps the exact comparison table collapsed and ordered by calendar year", () => {
    render(
      <ThresholdHistoryChart
        data={[row(2026), row(2024), row(2025)]}
        selectedYear={2025}
      />,
    );
    const details = screen.getByTestId("threshold-history-values");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByText("Show values")).toBeVisible();
    expect(screen.getByRole("table")).not.toBeVisible();
    fireEvent.click(screen.getByText("Show values"));
    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map(
        (element) => within(element).getAllByRole("cell")[0].textContent,
      ),
    ).toEqual(["2024", "2025", "2026"]);
    expect(
      within(rows[0])
        .getAllByRole("cell")
        .slice(0, 5)
        .map((cell) => cell.textContent),
    ).toEqual([
      "2024",
      "$40,000",
      "×1.100",
      "$35,200",
      "Published national base; modeled geography; published shares",
    ]);
    expect(rows[0]).toHaveTextContent("0.400000");
    expect(rows[0]).toHaveTextContent("1.250000");
    expect(rows[0]).toHaveTextContent("0.800000");
  });

  it("normalizes object-key year strings before drawing annual segments and highlighting selection", () => {
    const onSelectYear = vi.fn();
    const data = Array.from({ length: 14 }, (_, index) =>
      row(String(2022 + index)),
    );
    render(
      <ThresholdHistoryChart
        data={data}
        selectedYear="2025"
        onSelectYear={onSelectYear}
      />,
    );
    expect(screen.getAllByTestId("threshold-history-segment")).toHaveLength(13);
    const selected = screen.getByTestId("threshold-year-2025");
    expect(selected).toHaveAttribute("aria-current", "date");
    expect(selected).toHaveAttribute("tabindex", "0");
    expect(selected.querySelector('circle[r="5"]')).not.toBeNull();
    fireEvent.click(screen.getByTestId("threshold-year-2026"));
    expect(onSelectYear).toHaveBeenCalledWith(2026);
  });

  it("handles an entirely unavailable series and an empty series", () => {
    const { rerender } = render(
      <ThresholdHistoryChart
        data={[
          row(2025, { localThreshold: null }),
          row(2026, { localThreshold: NaN }),
        ]}
      />,
    );
    expect(screen.queryAllByTestId("threshold-history-segment")).toHaveLength(
      0,
    );
    expect(screen.getAllByRole("button")).toHaveLength(2);
    rerender(<ThresholdHistoryChart data={[]} />);
    expect(screen.getByText("No annual thresholds available.")).toBeVisible();
    expect(screen.queryByRole("group")).toBeNull();
  });
});
