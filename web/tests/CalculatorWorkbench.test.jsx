import { renderCalculator as render } from "./helpers/renderCalculator";
import {
  fireEvent,
  render as renderSetup,
  screen,
  within,
} from "@testing-library/react";
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

const chooseArea = (id) => {
  fireEvent.change(screen.getByLabelText("Search SPM areas"), {
    target: { value: id },
  });
  fireEvent.click(
    within(
      screen.getByRole("listbox", { name: "Matching SPM areas" }),
    ).getAllByRole("option")[0],
  );
};
const chooseSetupYear = (year) =>
  fireEvent.click(
    screen.getByRole("button", {
      name: year > 2025 ? `${year} (forecast)` : String(year),
      exact: true,
    }),
  );
const enterCount = (label, value) =>
  fireEvent.change(screen.getByLabelText(label), {
    target: { value: String(value) },
  });
const continueHousehold = () =>
  fireEvent.click(
    screen.getByRole("button", { name: "Continue", exact: true }),
  );

describe("explicit personal setup", () => {
  it("starts with no selected area or result and waits for an explicit search selection", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    expect(
      screen.getByRole("heading", { name: "Where do you live?" }),
    ).toHaveFocus();
    expect(screen.queryByLabelText("SPM estimation area")).toBeNull();
    expect(screen.getByLabelText("Search SPM areas")).toHaveValue("");
    expect(
      screen.queryByRole("button", { name: "Continue", exact: true }),
    ).toBeNull();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    expect(screen.queryByLabelText("Threshold year")).toBeNull();
    const search = screen.getByLabelText("Search SPM areas");
    // A historical identity must remain discoverable before any year exists.
    fireEvent.change(search, { target: { value: "historical" } });
    expect(
      screen.getByRole("option", { name: "Historical Metro Group" }),
    ).toBeVisible();
    fireEvent.change(search, { target: { value: "san jose" } });
    expect(
      screen.getByRole("heading", { name: "Where do you live?" }),
    ).toBeVisible();
    expect(screen.queryByLabelText("Adults")).toBeNull();
    const matches = screen.getByRole("listbox", { name: "Matching SPM areas" });
    fireEvent.click(
      within(matches).getByRole("option", {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Who is in your household?" }),
    ).toHaveFocus();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    expect(screen.getByLabelText("Adults")).toHaveValue(null);
    expect(screen.getByLabelText("Children")).toHaveValue(null);
    for (const tab of screen.getAllByRole("tab"))
      expect(tab).toHaveAttribute("aria-selected", "false");
  });

  it("advances a keyboard-selected area and requires explicit counts, zero children and tenure", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    fireEvent.change(search, { target: { value: "1002" } });
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(
      screen.getByRole("heading", { name: "Who is in your household?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Continue", exact: true }),
    ).toBeDisabled();
    continueHousehold();
    expect(screen.queryByLabelText("Threshold year")).toBeNull();
    enterCount("Adults", 1);
    expect(
      screen.getByRole("button", { name: "Continue", exact: true }),
    ).toBeDisabled();
    continueHousehold();
    expect(screen.queryByLabelText("Threshold year")).toBeNull();
    enterCount("Children", 0);
    expect(
      screen.getByRole("button", { name: "Continue", exact: true }),
    ).toBeDisabled();
    continueHousehold();
    expect(screen.queryByLabelText("Threshold year")).toBeNull();
    const renter = screen.getByRole("tab", { name: "Renter", exact: true });
    fireEvent.focus(renter);
    expect(renter).toHaveAttribute("aria-selected", "false");
    expect(
      screen.getByRole("button", { name: "Continue", exact: true }),
    ).toBeDisabled();
    fireEvent.keyDown(renter, { key: "Enter", code: "Enter" });
    expect(renter).toHaveAttribute("aria-selected", "true");
    expect(
      screen.getByRole("button", { name: "Continue", exact: true }),
    ).toBeEnabled();
    enterCount("Children", "");
    expect(screen.getByLabelText("Children")).toHaveValue(null);
    expect(
      screen.getByRole("button", { name: "Continue", exact: true }),
    ).toBeDisabled();
    enterCount("Children", 0);
    continueHousehold();
    expect(screen.getByRole("heading", { name: "Which year?" })).toHaveFocus();
    expect(screen.queryByLabelText("Threshold year")).toBeNull();
    expect(
      screen.getByRole("button", { name: "2025", exact: true }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "2035 (forecast)", exact: true }),
    ).toBeVisible();
    expect(
      screen.queryByRole("button", { name: "View thresholds", exact: true }),
    ).toBeNull();
    expect(screen.queryByLabelText("Real spending")).toBeNull();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    chooseSetupYear(2025);
    expect(screen.getByTestId("primary-result")).toHaveTextContent(
      "Alabama Nonmetro",
    );
    expect(
      within(screen.getByTestId("primary-result")).getByRole("heading", {
        name: "Alabama Nonmetro",
      }),
    ).toHaveFocus();
    expect(screen.getByLabelText("Children")).toHaveValue(0);
    expect(
      screen.queryByRole("form", { name: "Set up your threshold" }),
    ).toBeNull();
  });

  it("retains answers when going back without replaying automatic advancement", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    chooseArea("41940");
    enterCount("Adults", 3);
    enterCount("Children", 0);
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: "Mortgage", exact: true }),
      { button: 0, ctrlKey: false },
    );
    continueHousehold();
    fireEvent.click(screen.getByRole("button", { name: "Back", exact: true }));
    expect(
      screen.getByRole("heading", { name: "Who is in your household?" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Adults")).toHaveValue(3);
    expect(screen.getByLabelText("Children")).toHaveValue(0);
    expect(
      screen.getByRole("tab", { name: "Mortgage", exact: true }),
    ).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("button", { name: "Back", exact: true }));
    expect(
      screen.getByRole("heading", { name: "Where do you live?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", {
        name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
        exact: true,
      }),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Search SPM areas"), {
      target: { value: "no matching place" },
    });
    fireEvent.keyDown(screen.getByLabelText("Search SPM areas"), {
      key: "Enter",
      code: "Enter",
    });
    expect(
      screen.getByRole("heading", { name: "Where do you live?" }),
    ).toBeVisible();
    const progress = screen.getByRole("navigation", { name: "Setup progress" });
    fireEvent.click(
      within(progress).getByRole("button", {
        name: /Who is in your household/,
      }),
    );
    expect(screen.getByLabelText("Adults")).toHaveValue(3);
    continueHousehold();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    chooseSetupYear(2030);
    expect(screen.getByTestId("primary-result")).toHaveTextContent("San Jose");
    expect(
      within(screen.getByTestId("primary-result")).getByRole("heading"),
    ).toHaveFocus();
    expect(screen.getByLabelText("Real spending")).toHaveValue("ce_trend");
    fireEvent.change(screen.getByLabelText("Real spending"), {
      target: { value: "zero_real" },
    });
    const yearControl = screen.getByLabelText("Threshold year");
    yearControl.focus();
    selectYear(2025);
    expect(yearControl).toHaveFocus();
    const areaControl = screen.getByLabelText("SPM estimation area");
    areaControl.focus();
    fireEvent.change(areaControl, { target: { value: "1002" } });
    expect(areaControl).toHaveFocus();
    expect(
      within(screen.getByTestId("primary-result")).getByRole("heading", {
        name: "Alabama Nonmetro",
      }),
    ).not.toHaveFocus();
    expect(screen.queryByLabelText("Real spending")).toBeNull();
    enterCount("Adults", 2);
    expect(screen.getByTestId("primary-result")).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "Where do you live?" }),
    ).toBeNull();
    selectYear(2030);
    expect(screen.getByLabelText("Real spending")).toHaveValue("zero_real");
  });

  it("returns to location when the chosen year excludes the selected historical area", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    chooseArea(HISTORICAL_AREA_ID);
    enterCount("Adults", 2);
    enterCount("Children", 2);
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: "Renter", exact: true }),
      { button: 0, ctrlKey: false },
    );
    continueHousehold();
    chooseSetupYear(2023);
    expect(
      screen.getByRole("heading", { name: "Where do you live?" }),
    ).toBeVisible();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    expect(screen.getAllByRole("alert").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", {
        name: "New York-Newark-Jersey City, NY-NJ-PA MSA",
        exact: true,
      }),
    ).toBeNull();
    fireEvent.change(screen.getByLabelText("Search SPM areas"), {
      target: { value: "historical" },
    });
    expect(
      screen.queryByRole("option", { name: "Historical Metro Group" }),
    ).toBeNull();
    chooseArea("1002");
    expect(
      screen.getByRole("heading", { name: "Who is in your household?" }),
    ).toBeVisible();
    expect(screen.getByLabelText("Adults")).toHaveValue(2);
    continueHousehold();
    expect(screen.getByRole("heading", { name: "Which year?" })).toBeVisible();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    chooseSetupYear(2023);
    expect(screen.getByTestId("primary-result")).toHaveTextContent(
      "Alabama Nonmetro",
    );
  });
});

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
      Array.from(screen.getByLabelText("Threshold year").options)
        .filter((option) => option.value)
        .map((option) => Number(option.value))
        .sort((a, b) => a - b),
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
