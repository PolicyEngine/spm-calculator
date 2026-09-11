import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CalculatorWorkbench from "../src/components/CalculatorWorkbench";
import RootLayout from "../app/layout";
import {
  AVAILABLE_YEARS,
  FORECAST_CONTENT_SHA256,
  HISTORICAL_AREA_ID,
  MODELED_AREA_ID,
  makeRollingCalculatorData,
} from "./fixtures/rollingCalculatorData";

const selectYear = (year) =>
  fireEvent.change(screen.getByLabelText("Threshold year"), {
    target: { value: String(year) },
  });

function renderLayout(data = makeRollingCalculatorData()) {
  const layout = RootLayout({ children: <CalculatorWorkbench data={data} /> });
  render(
    layout.props.children.find((child) => child.type === "body").props.children,
  );
}

describe("canonical calculator controls and shared layout", () => {
  it("renders one actual shared navigation header and keeps app methodology in the results footnote", () => {
    renderLayout();
    selectYear(2026);
    expect(
      screen.getAllByRole("button", { name: "Toggle navigation" }),
    ).toHaveLength(1);
    const footnote = screen.getByTestId("results-footnote");
    expect(footnote).toContainElement(screen.getByTestId("methodology-card"));
    expect(footnote).toContainElement(screen.getByTestId("version-footer"));
    expect(footnote).toContainElement(
      screen.getByTestId("forecast-provenance"),
    );
    expect(footnote).toHaveTextContent(FORECAST_CONTENT_SHA256);
    const sharedHeader = document.querySelector("main").previousElementSibling;
    expect(sharedHeader).toContainElement(
      screen.getByRole("button", { name: "Toggle navigation" }),
    );
    const sharedChrome = [
      sharedHeader,
      ...Array.from(document.querySelectorAll("header, footer")).filter(
        (element) => !footnote.contains(element),
      ),
    ];
    expect(sharedChrome.length).toBeGreaterThan(0);
    for (const element of sharedChrome) {
      expect(element).not.toHaveTextContent(
        /SHA-256|rolling_ce_acs_v1|research forecast|equivalence_scale|load_forecast/i,
      );
      expect(element).not.toHaveTextContent(FORECAST_CONTENT_SHA256);
    }
  });

  it("shows matching search results and selects an area with a click", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    fireEvent.change(screen.getByLabelText("Search SPM areas"), {
      target: { value: "san jose" },
    });
    const matches = screen.getByRole("listbox", { name: "Matching SPM areas" });
    expect(within(matches).getAllByRole("option")).toHaveLength(1);
    fireEvent.click(
      within(matches).getByRole("option", {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      }),
    );
    expect(
      screen.getByRole("heading", {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      }),
    ).toBeTruthy();
    expect(screen.getByLabelText("SPM estimation area")).toHaveValue("41940");
    expect(screen.getByLabelText("Search SPM areas")).toHaveValue("");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$58,381");
  });

  it("selects an area code with Enter and preserves the selected area after an empty search", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    fireEvent.change(search, { target: { value: "1002" } });
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(
      screen.getByRole("heading", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    fireEvent.change(search, { target: { value: "no matching place" } });
    expect(screen.getByText("No SPM areas match your search.")).toBeTruthy();
    const matches = screen.getByRole("listbox", { name: "Matching SPM areas" });
    expect(within(matches).queryAllByRole("option")).toHaveLength(0);
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(screen.getByLabelText("SPM estimation area")).toHaveValue("1002");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$33,360");
    fireEvent.change(search, { target: { value: "" } });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("offers all 2022–2035 years and only actual SPM estimation geography types", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    expect(
      Array.from(screen.getByLabelText("Threshold year").options, (option) =>
        Number(option.value),
      ).sort((a, b) => a - b),
    ).toEqual(AVAILABLE_YEARS);
    for (const year of AVAILABLE_YEARS.filter((year) => year > 2025)) {
      expect(
        screen.getByRole("option", { name: `${year} (forecast)` }),
      ).toBeTruthy();
    }
    expect(screen.queryByLabelText("Geography type")).toBeNull();
    const areas = screen.getByLabelText("SPM estimation area");
    expect(
      within(areas).getByRole("option", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    expect(
      within(areas).getByRole("option", { name: /Alabama residual Metro/ }),
    ).toHaveValue(MODELED_AREA_ID);
    for (const name of [
      "National average",
      "State",
      "County",
      "Congressional district",
    ]) {
      expect(
        within(areas).queryByRole("option", { name, exact: true }),
      ).toBeNull();
    }
  });

  it("restricts search and menu to each year and preserves an unavailable selection until explicitly changed", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const areas = screen.getByLabelText("SPM estimation area");
    const search = screen.getByLabelText("Search SPM areas");
    expect(
      within(areas).queryByRole("option", { name: "Historical Metro Group" }),
    ).toBeNull();
    selectYear(2022);
    fireEvent.change(areas, { target: { value: HISTORICAL_AREA_ID } });
    expect(
      screen.getByRole("heading", { name: "Historical Metro Group" }),
    ).toBeTruthy();
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
      "Unavailable",
    );
    selectYear(2023);
    const unavailable = within(areas).getByRole("option", {
      name: "Selected area unavailable in 2023",
    });
    expect(unavailable).toBeDisabled();
    expect(areas).toHaveValue("");
    expect(
      within(areas).queryByRole("option", { name: "Historical Metro Group" }),
    ).toBeNull();
    expect(screen.getByTestId("primary-result")).toHaveTextContent(
      "Unavailable",
    );
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(/\$/);
    fireEvent.change(search, { target: { value: "historical" } });
    expect(screen.getByText("No SPM areas match your search.")).toBeTruthy();
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(areas).toHaveValue("");
    selectYear(2022);
    expect(areas).toHaveValue(HISTORICAL_AREA_ID);
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
      "Unavailable",
    );
    selectYear(2023);
    fireEvent.change(areas, { target: { value: "1002" } });
    expect(areas).toHaveValue("1002");
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
      "Unavailable",
    );
  });

  it("labels local preview packages honestly and retains the preview API link", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const footer = screen.getByTestId("results-footnote");
    expect(footer).toHaveTextContent(/local build|local preview/i);
    expect(footer).toHaveTextContent("0.3.0");
    expect(footer.querySelector('a[href*="pypi.org"]')).toBeNull();
    expect(
      footer.querySelector(
        'a[href="https://github.com/PolicyEngine/spm-calculator/pull/36"]',
      ),
    ).not.toBeNull();
  });

  it.each(["", "/us/spm-calculator"])(
    "offers the hash-pinned full audit download with base path '%s'",
    (basePath) => {
      const data = makeRollingCalculatorData();
      const name = `rolling-forecast-${FORECAST_CONTENT_SHA256}.json`;
      data.forecast.auditArtifact = {
        name,
        url: `/data/canonical/${name}`,
      };
      vi.stubEnv("NEXT_PUBLIC_BASE_PATH", basePath);
      try {
        render(<CalculatorWorkbench data={data} />);
        const link = screen.getByRole("link", {
          name: "Download full canonical audit data (JSON)",
        });
        expect(link).toHaveAttribute(
          "href",
          `${basePath}/data/canonical/${name}`,
        );
        expect(link).toHaveAttribute("download", name);
        expect(screen.getByTestId("forecast-provenance")).toHaveTextContent(
          FORECAST_CONTENT_SHA256,
        );
        expect(screen.getByTestId("version-footer")).toHaveTextContent(
          "Publication on PyPI is not confirmed for this build",
        );
      } finally {
        vi.unstubAllEnvs();
      }
    },
  );

  it("links the published package only when the configured publication matches the installed version", () => {
    const data = makeRollingCalculatorData();
    data.packageDistribution = {
      status: "published",
      version: "0.3.0",
      publishedVersion: "0.3.0",
      pypiUrl: "https://pypi.org/project/spm-calculator/0.3.0/",
    };
    const { rerender } = render(<CalculatorWorkbench data={data} />);
    const footer = screen.getByTestId("results-footnote");
    expect(
      footer.querySelector(
        'a[href="https://pypi.org/project/spm-calculator/0.3.0/"]',
      ),
    ).not.toBeNull();
    expect(footer).not.toHaveTextContent(
      /local build|local preview|preview Python API/i,
    );
    expect(footer.querySelector('a[href*="/pull/36"]')).toBeNull();
    rerender(
      <CalculatorWorkbench data={{ ...data, packageVersion: "0.4.0" }} />,
    );
    expect(footer.querySelector('a[href*="pypi.org"]')).toBeNull();
    expect(footer).toHaveTextContent(/local build|local preview/i);
  });

  it("explains the formula and selected published housing shares", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    selectYear(2024);
    const methodology = screen.getByTestId("methodology-card");
    expect(methodology).toHaveTextContent(/base\[tenure\]/);
    expect(methodology).toHaveTextContent(/equivalence_scale/);
    expect(methodology).toHaveTextContent(/geoadj\[tenure\]/);
    for (const share of ["0.443", "0.434", "0.323"])
      expect(methodology).toHaveTextContent(share);
    expect(
      methodology.querySelector(
        'a[href*="bls.gov/pir/spm/garner_spm_choices"]',
      ),
    ).not.toBeNull();
    expect(
      methodology.querySelector(
        'a[href*="census.gov/library/publications/2025/demo/p60-287"]',
      ),
    ).not.toBeNull();
  });
});
