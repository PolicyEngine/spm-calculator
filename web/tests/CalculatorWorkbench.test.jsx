import {
  renderCalculator as render,
  selectArea as chooseArea,
} from "./helpers/renderCalculator";
import {
  act,
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
  it("does not select or advance when Enter follows focus without a query or navigation", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    act(() => search.focus());
    expect(search).toHaveValue("");
    expect(screen.getByRole("listbox", { name: "Matching SPM areas" })).toBeVisible();
    expect(fireEvent.keyDown(search, { key: "Enter", code: "Enter" })).toBe(false);
    expect(search).toHaveValue("");
    expect(search).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("heading", { name: "Where do you live?" })).toBeVisible();
    expect(screen.queryByLabelText("Adults")).toBeNull();
    expect(screen.queryByTestId("primary-result")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("allows an explicit arrow choice from the full initial area list", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    act(() => search.focus());
    const list = screen.getByRole("listbox", { name: "Matching SPM areas" });
    const firstOption = within(list).getAllByRole("option")[0];
    const firstName = firstOption.textContent;
    fireEvent.keyDown(search, { key: "ArrowDown", code: "ArrowDown" });
    expect(firstOption).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(screen.getByRole("heading", { name: "Who is in your household?" })).toBeVisible();
    expect(screen.getByRole("navigation", { name: "Setup progress" })).toHaveTextContent(firstName);
    expect(screen.getByLabelText("Adults")).toHaveValue(null);
  });

  it.each([
    ["Home", { key: "Home", code: "Home" }],
    ["End", { key: "End", code: "End" }],
    ["Ctrl+n", { key: "n", code: "KeyN", ctrlKey: true }],
    ["Ctrl+j", { key: "j", code: "KeyJ", ctrlKey: true }],
    ["Ctrl+p", { key: "p", code: "KeyP", ctrlKey: true }],
    ["Ctrl+k", { key: "k", code: "KeyK", ctrlKey: true }],
  ])("commits an empty-query area choice made with %s then Enter", (_, key) => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    act(() => search.focus());
    const list = screen.getByRole("listbox", { name: "Matching SPM areas" });
    fireEvent.keyDown(search, key);
    expect(search).toHaveValue("");
    const selected = within(list).getByRole("option", { selected: true });
    const name = selected.textContent;
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(
      screen.getByRole("heading", { name: "Who is in your household?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Setup progress" }),
    ).toHaveTextContent(name);
  });

  it("commits a pointer-highlighted empty-query area choice with Enter", () => {
    renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    act(() => search.focus());
    const option = screen.getByRole("option", {
      name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      exact: true,
    });
    fireEvent.pointerMove(option, { pointerType: "mouse" });
    expect(search).toHaveFocus();
    expect(search).toHaveValue("");
    expect(option).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(
      screen.getByRole("heading", { name: "Who is in your household?" }),
    ).toBeVisible();
    expect(
      screen.getByRole("navigation", { name: "Setup progress" }),
    ).toHaveTextContent("San Jose-Sunnyvale-Santa Clara, CA MSA");
  });

  it.each([{ keyCode: 229 }, { isComposing: true }])(
    "leaves composition Enter to the input method during setup %j",
    (composition) => {
      renderSetup(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
      const search = screen.getByLabelText("Search SPM areas");
      act(() => search.focus());
      fireEvent.change(search, { target: { value: "1002" } });
      expect(
        fireEvent.keyDown(search, { key: "Enter", code: "Enter", ...composition }),
      ).toBe(true);
      expect(search).toHaveValue("1002");
      expect(screen.getByRole("heading", { name: "Where do you live?" })).toBeVisible();
      expect(screen.queryByLabelText("Adults")).toBeNull();
      fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
      expect(screen.getByRole("heading", { name: "Who is in your household?" })).toBeVisible();
    },
  );

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
    expect(screen.getByLabelText("Search SPM areas")).toHaveValue(
      "San Jose-Sunnyvale-Santa Clara, CA MSA",
    );
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
        name: /^Household/,
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
    const areaControl = screen.getByLabelText("Search SPM areas");
    areaControl.focus();
    chooseArea("1002");
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
  it("preserves the committed area after focus or click followed by an empty Enter", () => {
    const data = makeRollingCalculatorData();
    render(<CalculatorWorkbench data={data} />);
    const search = screen.getByLabelText("Search SPM areas");
    const name = data.areasByYear[2025]["35620"].name;
    const result = screen.getByTestId("primary-result").textContent;
    for (const open of [() => act(() => search.focus()), () => fireEvent.click(search)]) {
      open();
      expect(search).toHaveValue("");
      expect(search).toHaveAttribute("aria-expanded", "true");
      expect(fireEvent.keyDown(search, { key: "Enter", code: "Enter" })).toBe(false);
      expect(search).toHaveValue(name);
      expect(search).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByTestId("primary-result").textContent).toBe(result);
    }
  });

  it("preserves a draft when focus moves within the open area selector", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    act(() => search.focus());
    fireEvent.change(search, { target: { value: "san jose" } });
    const list = screen.getByRole("listbox", { name: "Matching SPM areas" });
    fireEvent.blur(search, { relatedTarget: list });
    fireEvent.focus(list, { relatedTarget: search });
    fireEvent.blur(list, { relatedTarget: search });
    fireEvent.focus(search, { relatedTarget: list });
    expect(search).toHaveValue("san jose");
    expect(search).toHaveAttribute("aria-expanded", "true");
    expect(within(list).getAllByRole("option")).toHaveLength(1);
    expect(within(list).getByRole("option", {
      name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
      exact: true,
    })).toHaveAttribute("data-value", "41940");
  });

  it.each([
    { keyCode: 229 },
    { isComposing: true },
  ])("does not intercept an idle printable key during composition %j", (composition) => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    act(() => search.focus());
    fireEvent.change(search, { target: { value: "1002" } });
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(search).toHaveFocus();
    expect(search).toHaveValue("Alabama Nonmetro");
    const result = screen.getByTestId("primary-result").textContent;
    expect(fireEvent.keyDown(search, { key: "s", code: "KeyS", ...composition })).toBe(true);
    expect(search).toHaveValue("Alabama Nonmetro");
    expect(search).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("primary-result").textContent).toBe(result);
  });

  it.each([
    ["Adults", 2, "2 adults, 2 children"],
    ["Children", 0, "2 adults, 0 children"],
  ])(
    "keeps the threshold and family-size breakdown unavailable while %s is blank",
    (label, restoredValue, household) => {
      render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
      const familySize = screen
        .getByText("Family size", { exact: true })
        .closest('[data-slot="card"]');
      expect(familySize).not.toBeNull();
      enterCount(label, "");
      expect(screen.getByLabelText(label)).toHaveValue(null);
      expect(screen.getByTestId("primary-result")).toHaveTextContent(
        "Unavailable",
      );
      expect(screen.getByTestId("primary-result")).not.toHaveTextContent(/\$/);
      for (const field of ["Formula", "Normalized scale", "Household"]) {
        expect(
          within(familySize).getByText(field, { exact: true }).parentElement,
        ).toHaveTextContent("Unavailable");
      }
      expect(familySize).not.toHaveTextContent("0.000");
      enterCount(label, restoredValue);
      expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
        "Unavailable",
      );
      expect(screen.getByTestId("primary-result")).toHaveTextContent(
        /\$[\d,]+/,
      );
      expect(familySize).not.toHaveTextContent("Unavailable");
      expect(familySize).toHaveTextContent(household);
    },
  );

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
    expect(screen.queryByLabelText("SPM estimation area")).toBeNull();
    expect(screen.getByLabelText("Search SPM areas")).toHaveValue(
      "San Jose-Sunnyvale-Santa Clara, CA MSA",
    );
    expect(screen.queryByRole("listbox", { name: "Matching SPM areas" })).toBeNull();
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$58,381");
  });

  it("selects an area code with Enter and preserves the selected area after a search with no matches", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    fireEvent.change(search, { target: { value: "1002" } });
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(
      screen.getByRole("heading", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    expect(search).toHaveValue("Alabama Nonmetro");
    expect(screen.queryByRole("listbox", { name: "Matching SPM areas" })).toBeNull();
    fireEvent.change(search, { target: { value: "no matching place" } });
    expect(screen.getByText("No SPM areas match your search.")).toBeTruthy();
    const matches = screen.getByRole("listbox", { name: "Matching SPM areas" });
    expect(within(matches).queryAllByRole("option")).toHaveLength(0);
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(search).toHaveValue("no matching place");
    expect(screen.getByTestId("primary-result")).toHaveTextContent("$33,360");
    fireEvent.change(search, { target: { value: "" } });
    expect(
      within(
        screen.getByRole("listbox", { name: "Matching SPM areas" }),
      ).getAllByRole("option"),
    ).toHaveLength(4);
    fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
    expect(search).toHaveValue("Alabama Nonmetro");
    expect(screen.queryByRole("listbox", { name: "Matching SPM areas" })).toBeNull();
  });

  it.each(["Enter", "click"])(
    "starts a fresh query when typing or pasting after selecting with %s",
    (selection) => {
      render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
      const search = screen.getByLabelText("Search SPM areas");
      act(() => search.focus());
      fireEvent.change(search, { target: { value: "1002" } });
      if (selection === "Enter") {
        fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
      } else {
        const option = screen.getByRole("option", {
          name: "Alabama Nonmetro",
          exact: true,
        });
        expect(option).toHaveAttribute("data-value", "1002");
        fireEvent.mouseDown(option);
        fireEvent.click(option);
      }
      expect(search).toHaveFocus();
      expect(search).toHaveValue("Alabama Nonmetro");
      expect(search).toHaveAttribute("aria-expanded", "false");
      const result = screen.getByTestId("primary-result").textContent;

      // Exercise the first actual keystroke while the committed name is shown.
      // Its default insertion must be canceled so the name cannot be appended to.
      expect(fireEvent.keyDown(search, { key: "s", code: "KeyS" })).toBe(false);
      expect(search).toHaveValue("s");
      expect(search).toHaveAttribute("aria-expanded", "true");
      expect(
        screen.getByRole("option", {
          name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
          exact: true,
        }),
      ).toHaveAttribute("data-value", "41940");
      expect(screen.getByTestId("primary-result").textContent).toBe(result);
      fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
      expect(search).toHaveValue("Alabama Nonmetro");
      expect(search).toHaveFocus();

      expect(
        fireEvent.paste(search, {
          clipboardData: { getData: () => "san jose" },
        }),
      ).toBe(false);
      expect(search).toHaveValue("san jose");
      expect(
        within(
          screen.getByRole("listbox", { name: "Matching SPM areas" }),
        ).getAllByRole("option"),
      ).toHaveLength(1);
      fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
      expect(search).toHaveValue("Alabama Nonmetro");
      expect(search).toHaveAttribute("aria-expanded", "false");
      expect(screen.getByTestId("primary-result").textContent).toBe(result);
    },
  );

  it("uses one area selector and opens all yearly options without changing the current result", () => {
    const data = makeRollingCalculatorData();
    render(<CalculatorWorkbench data={data} />);
    const name = data.areasByYear[2025]["35620"].name;
    const search = screen.getByLabelText("Search SPM areas");
    const result = screen.getByTestId("primary-result").textContent;
    expect(screen.getAllByLabelText("Search SPM areas")).toHaveLength(1);
    expect(screen.queryByLabelText("SPM estimation area")).toBeNull();
    expect(screen.queryByRole("button", { name, exact: true })).toBeNull();
    expect(search).toHaveValue(name);
    expect(search).toHaveAttribute("aria-expanded", "false");
    expect(search).not.toHaveAttribute("aria-controls");
    expect(search).not.toHaveAttribute("aria-activedescendant");
    expect(screen.queryByRole("listbox", { name: "Matching SPM areas" })).toBeNull();

    fireEvent.focus(search);
    expect(search).toHaveValue("");
    expect(search).toHaveAttribute("aria-expanded", "true");
    const list = screen.getByRole("listbox", { name: "Matching SPM areas" });
    expect(search).toHaveAttribute("aria-controls", list.id);
    const options = within(list).getAllByRole("option");
    expect(
      options.map((option) => option.getAttribute("data-value")).sort(),
    ).toEqual(Object.keys(data.areasByYear[2025]).sort());
    for (const option of options) {
      expect(option.textContent).toBe(
        data.areasByYear[2025][option.getAttribute("data-value")].name,
      );
    }
    expect(screen.getByTestId("primary-result").textContent).toBe(result);
    fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
    expect(search).toHaveValue(name);
    expect(search).toHaveAttribute("aria-expanded", "false");
    expect(search).not.toHaveAttribute("aria-controls");
    expect(search).not.toHaveAttribute("aria-activedescendant");
    expect(screen.queryByRole("listbox", { name: "Matching SPM areas" })).toBeNull();
    expect(screen.getByTestId("primary-result").textContent).toBe(result);
  });

  it.each(["Escape", "blur"])(
    "discards a matching draft on %s without committing an area",
    (dismiss) => {
      const data = makeRollingCalculatorData();
      render(<CalculatorWorkbench data={data} />);
      const search = screen.getByLabelText("Search SPM areas");
      const result = screen.getByTestId("primary-result").textContent;
      fireEvent.focus(search);
      fireEvent.change(search, { target: { value: "san jose" } });
      expect(
        screen.getByRole("option", {
          name: "San Jose-Sunnyvale-Santa Clara, CA MSA",
          exact: true,
        }),
      ).toHaveAttribute("data-value", "41940");
      if (dismiss === "Escape") {
        fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
      } else {
        fireEvent.blur(search, {
          relatedTarget: screen.getByLabelText("Threshold year"),
        });
      }
      expect(search).toHaveValue(data.areasByYear[2025]["35620"].name);
      expect(
        screen.queryByRole("listbox", { name: "Matching SPM areas" }),
      ).toBeNull();
      expect(screen.getByTestId("primary-result").textContent).toBe(result);
    },
  );

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
    const search = screen.getByLabelText("Search SPM areas");
    fireEvent.focus(search);
    const areas = screen.getByRole("listbox", { name: "Matching SPM areas" });
    expect(
      within(areas).getByRole("option", { name: "Alabama Nonmetro" }),
    ).toBeTruthy();
    expect(
      within(areas).getByRole("option", { name: /Alabama residual Metro/ }),
    ).toHaveAttribute("data-value", MODELED_AREA_ID);
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
    fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
  });

  it("restricts search and menu to each year and preserves an unavailable selection until explicitly changed", () => {
    render(<CalculatorWorkbench data={makeRollingCalculatorData()} />);
    const search = screen.getByLabelText("Search SPM areas");
    fireEvent.focus(search);
    expect(
      within(
        screen.getByRole("listbox", { name: "Matching SPM areas" }),
      ).queryByRole("option", { name: "Historical Metro Group" }),
    ).toBeNull();
    fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
    selectYear(2022);
    chooseArea(HISTORICAL_AREA_ID);
    expect(
      screen.getByRole("heading", { name: "Historical Metro Group" }),
    ).toBeTruthy();
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
      "Unavailable",
    );
    selectYear(2023);
    expect(search).toHaveAttribute(
      "placeholder", "Selected area unavailable in 2023",
    );
    expect(search).toHaveValue("");
    fireEvent.focus(search);
    expect(
      within(
        screen.getByRole("listbox", { name: "Matching SPM areas" }),
      ).queryByRole("option", { name: "Historical Metro Group" }),
    ).toBeNull();
    expect(screen.getByTestId("primary-result")).toHaveTextContent(
      "Unavailable",
    );
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(/\$/);
    fireEvent.change(search, { target: { value: "historical" } });
    expect(screen.getByText("No SPM areas match your search.")).toBeTruthy();
    fireEvent.keyDown(search, { key: "Enter", code: "Enter" });
    expect(screen.getByTestId("primary-result")).toHaveTextContent("Unavailable");
    fireEvent.keyDown(search, { key: "Escape", code: "Escape" });
    expect(search).toHaveValue("");
    selectYear(2022);
    expect(search).toHaveValue("Historical Metro Group");
    expect(screen.getByTestId("primary-result")).not.toHaveTextContent(
      "Unavailable",
    );
    selectYear(2023);
    chooseArea("1002");
    expect(search).toHaveValue("Alabama Nonmetro");
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
