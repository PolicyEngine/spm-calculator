import { StrictMode, useState } from "react";

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CalculatorSetup from "../src/components/CalculatorSetup";

function ControlledSetup({ onComplete, invalidLocation = false }) {
  const [location, setLocation] = useState(invalidLocation ? "" : "New York");
  const [adults, setAdults] = useState("2");
  const [year, setYear] = useState("2025");

  return (
    <CalculatorSetup
      onComplete={() => onComplete({ location, adults, year })}
      steps={[
        {
          id: "location",
          title: "Choose your location",
          description: "Choose an SPM estimation area.",
          summary: location,
          valid:
            Boolean(location) &&
            !(location === "Historical area" && year === "2026"),
          content: (
            <label>
              Location
              <input
                value={location}
                onChange={(event) => setLocation(event.target.value)}
              />
            </label>
          ),
        },
        {
          id: "household",
          title: "Describe your household",
          description: "Enter the number of adults.",
          summary: `${adults} adults`,
          valid: Number(adults) > 0,
          content: (
            <label>
              Adults
              <input
                value={adults}
                onChange={(event) => setAdults(event.target.value)}
              />
            </label>
          ),
        },
        {
          id: "year",
          title: "Choose a year",
          description: "Choose a threshold year.",
          summary: year,
          valid: Boolean(year),
          content: (
            <label>
              Year
              <select
                value={year}
                onChange={(event) => setYear(event.target.value)}
              >
                <option value="2025">2025</option>
                <option value="2026">2026</option>
              </select>
            </label>
          ),
        },
      ]}
    />
  );
}

function continueSetup() {
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
}

function ExplicitSetup({ onComplete, onSelectionKeyDown }) {
  const [location, setLocation] = useState("");
  const [adults, setAdults] = useState("");
  const [year, setYear] = useState("");
  const [advanceRequest, setAdvanceRequest] = useState(null);

  return (
    <>
      <button type="button" onClick={() => setLocation("Boston")}>
        Restore location without a selection
      </button>
      <CalculatorSetup
        advanceRequest={advanceRequest}
        onComplete={() => onComplete({ location, adults, year })}
        steps={[
          {
            id: "location",
            title: "Choose your location",
            summary: location,
            valid:
              Boolean(location) &&
              !(location === "Historical area" && year === "2026"),
            autoAdvance: true,
            content: (
              <>
                <label>
                  Location
                  <select
                    value={location}
                    onChange={(event) => {
                      setLocation(event.target.value);
                      setAdvanceRequest({ stepId: "location" });
                    }}
                  >
                    <option value="">Choose a location</option>
                    <option value="Boston">Boston</option>
                    <option value="Historical area">Historical area</option>
                  </select>
                </label>
                <input
                  aria-label="Search locations"
                  onKeyDown={(event) => {
                    if (event.key !== "Enter") return;
                    onSelectionKeyDown?.(event.defaultPrevented);
                    setLocation("Boston");
                    setAdvanceRequest({ stepId: "location" });
                  }}
                />
              </>
            ),
          },
          {
            id: "household",
            title: "Describe your household",
            summary: adults ? `${adults} adults` : "",
            valid: Number(adults) > 0,
            content: (
              <label>
                Adults
                <input
                  value={adults}
                  onChange={(event) => setAdults(event.target.value)}
                />
              </label>
            ),
          },
          {
            id: "year",
            title: "Choose a year",
            summary: year,
            valid: Boolean(year),
            autoAdvance: true,
            content: (
              <label>
                Year
                <select
                  value={year}
                  onChange={(event) => {
                    setYear(event.target.value);
                    setAdvanceRequest({ stepId: "year" });
                  }}
                >
                  <option value="">Choose a year</option>
                  <option value="2025">2025</option>
                  <option value="2026">2026</option>
                </select>
              </label>
            ),
          },
        ]}
      />
    </>
  );
}

function chooseLocation(value = "Boston") {
  fireEvent.change(screen.getByLabelText("Location"), { target: { value } });
}

function enterAdults(value = "2") {
  fireEvent.change(screen.getByLabelText("Adults"), { target: { value } });
}

function chooseYear(value = "2025") {
  fireEvent.change(screen.getByLabelText("Year"), { target: { value } });
}

describe("calculator setup", () => {
  it("shows one focused step, permits visited navigation, and retains parent-controlled answers", () => {
    const onComplete = vi.fn();
    render(<ControlledSetup onComplete={onComplete} />);
    const progress = screen.getByRole("navigation", { name: "Setup progress" });

    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Choose your location" }),
    ).toHaveFocus();
    expect(screen.queryByLabelText("Adults")).not.toBeInTheDocument();
    expect(
      within(progress).getByRole("button", { name: "Choose a year" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "Boston" },
    });
    continueSetup();

    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Describe your household" }),
    ).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Adults"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("Location")).toHaveValue("Boston");
    fireEvent.click(
      within(progress).getByRole("button", { name: /Describe your household/ }),
    );
    expect(screen.getByLabelText("Adults")).toHaveValue("3");
    continueSetup();

    expect(screen.getByText("Step 3 of 3")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Choose a year" }),
    ).toHaveFocus();
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Year"), {
      target: { value: "2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "View thresholds" }));
    expect(onComplete).toHaveBeenCalledExactlyOnceWith({
      location: "Boston",
      adults: "3",
      year: "2026",
    });
  });

  it("blocks an invalid step, focuses its explanation, and continues after correction", () => {
    const onComplete = vi.fn();
    render(<ControlledSetup onComplete={onComplete} invalidLocation />);

    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    fireEvent.submit(
      screen.getByRole("form", { name: "Set up your threshold" }),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Review your answers in this step before continuing.",
    );
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "Boston" },
    });
    continueSetup();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Describe your household" }),
    ).toHaveFocus();
  });

  it("rechecks earlier choices when a later year makes the selected area unavailable", () => {
    const onComplete = vi.fn();
    render(<ControlledSetup onComplete={onComplete} />);
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "Historical area" },
    });
    continueSetup();
    continueSetup();
    fireEvent.change(screen.getByLabelText("Year"), {
      target: { value: "2026" },
    });
    fireEvent.click(screen.getByRole("button", { name: "View thresholds" }));

    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveValue("Historical area");
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Review your answers in this step before viewing thresholds.",
    );
    expect(screen.getByRole("alert")).toHaveFocus();
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: "Boston" },
    });
    fireEvent.click(
      within(
        screen.getByRole("navigation", { name: "Setup progress" }),
      ).getByRole("button", { name: /Choose a year/ }),
    );
    expect(screen.getByLabelText("Year")).toHaveValue("2026");
    fireEvent.click(screen.getByRole("button", { name: "View thresholds" }));
    expect(onComplete).toHaveBeenCalledExactlyOnceWith({
      location: "Boston",
      adults: "2",
      year: "2026",
    });
  });

  it("prevents progress navigation from bypassing a newly invalid earlier answer", () => {
    const onComplete = vi.fn();
    render(<ControlledSetup onComplete={onComplete} />);
    continueSetup();
    continueSetup();
    const progress = screen.getByRole("navigation", { name: "Setup progress" });
    fireEvent.click(
      within(progress).getByRole("button", { name: /Describe your household/ }),
    );
    fireEvent.change(screen.getByLabelText("Adults"), {
      target: { value: "0" },
    });
    fireEvent.click(
      within(progress).getByRole("button", { name: /Choose a year/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: "View thresholds" }));

    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Adults")).toHaveValue("0");
    expect(screen.getByRole("alert")).toHaveFocus();
  });

  it("advances only after explicit selections and completes with the answers updated in that event", () => {
    const onComplete = vi.fn();
    render(
      <StrictMode>
        <ExplicitSetup onComplete={onComplete} />
      </StrictMode>,
    );

    expect(screen.getByLabelText("Location")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
    chooseLocation();
    expect(
      screen.getByRole("heading", { name: "Describe your household" }),
    ).toHaveFocus();
    expect(screen.getByRole("button", { name: "Continue" })).toBeDisabled();
    enterAdults("3");
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    continueSetup();
    expect(screen.getByLabelText("Year")).toHaveValue("");
    expect(
      screen.queryByRole("button", { name: "View thresholds" }),
    ).toBeNull();
    chooseYear("2026");

    expect(onComplete).toHaveBeenCalledExactlyOnceWith({
      location: "Boston",
      adults: "3",
      year: "2026",
    });
  });

  it("consumes a selection once so Back and visited progress do not advance again", () => {
    const onComplete = vi.fn();
    render(<ExplicitSetup onComplete={onComplete} />);
    chooseLocation();
    enterAdults();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(screen.getByLabelText("Location")).toHaveValue("Boston");
    expect(
      screen.getByRole("heading", { name: "Choose your location" }),
    ).toHaveFocus();
    fireEvent.click(
      within(
        screen.getByRole("navigation", { name: "Setup progress" }),
      ).getByRole("button", { name: /Describe your household/ }),
    );
    expect(screen.getByLabelText("Adults")).toHaveValue("2");
    continueSetup();
    chooseYear();
    expect(onComplete).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    continueSetup();
    expect(screen.getByLabelText("Year")).toHaveValue("2025");
    expect(onComplete).toHaveBeenCalledTimes(1);
    chooseYear("2026");
    expect(onComplete).toHaveBeenCalledTimes(2);
  });

  it("does not advance when validity changes without a selection or when the search form submits", () => {
    const onComplete = vi.fn();
    render(<ExplicitSetup onComplete={onComplete} />);
    fireEvent.click(
      screen.getByRole("button", {
        name: "Restore location without a selection",
      }),
    );
    expect(screen.getByLabelText("Location")).toHaveValue("Boston");
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    fireEvent.submit(
      screen.getByRole("form", { name: "Set up your threshold" }),
    );
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("consumes an invalid selection without advancing when the answer later becomes valid", () => {
    const onComplete = vi.fn();
    render(<ExplicitSetup onComplete={onComplete} />);
    chooseLocation("");
    expect(screen.getByRole("alert")).toHaveFocus();
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Restore location without a selection",
      }),
    );
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
    chooseLocation("Boston");
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("cancels an input selection's Enter default after its handler runs and focuses the household step", () => {
    const onComplete = vi.fn();
    const onSelectionKeyDown = vi.fn();
    render(
      <ExplicitSetup
        onComplete={onComplete}
        onSelectionKeyDown={onSelectionKeyDown}
      />,
    );
    chooseLocation();
    enterAdults("3");
    fireEvent.click(screen.getByRole("button", { name: "Back" }));

    const defaultAllowed = fireEvent.keyDown(
      screen.getByLabelText("Search locations"),
      { key: "Enter" },
    );
    expect(onSelectionKeyDown).toHaveBeenCalledExactlyOnceWith(false);
    expect(defaultAllowed).toBe(false);
    expect(screen.getByText("Step 2 of 3")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Describe your household" }),
    ).toHaveFocus();
    expect(screen.getByLabelText("Adults")).toHaveValue("3");
    expect(screen.getByRole("button", { name: "Continue" })).toBeEnabled();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it("preserves Enter's default keyboard activation for single-choice buttons", () => {
    const onSelect = vi.fn();
    render(
      <CalculatorSetup
        onComplete={vi.fn()}
        steps={[
          {
            id: "year",
            title: "Choose a year",
            valid: true,
            autoAdvance: true,
            content: (
              <button type="button" onClick={onSelect}>
                2025
              </button>
            ),
          },
        ]}
      />,
    );
    const button = screen.getByRole("button", { name: "2025" });
    expect(fireEvent.keyDown(button, { key: "Enter" })).toBe(true);
    fireEvent.click(button);
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("revalidates earlier answers after the final explicit selection and focuses the invalid step", () => {
    const onComplete = vi.fn();
    render(<ExplicitSetup onComplete={onComplete} />);
    chooseLocation("Historical area");
    enterAdults();
    continueSetup();
    chooseYear("2026");

    expect(onComplete).not.toHaveBeenCalled();
    expect(screen.getByText("Step 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Review your answers in this step before viewing thresholds.",
    );
    expect(screen.getByRole("alert")).toHaveFocus();
    chooseLocation("Boston");
    expect(screen.queryByRole("alert")).toBeNull();
    continueSetup();
    expect(screen.getByLabelText("Year")).toHaveValue("2026");
    expect(onComplete).not.toHaveBeenCalled();
    chooseYear("2025");
    expect(onComplete).toHaveBeenCalledExactlyOnceWith({
      location: "Boston",
      adults: "2",
      year: "2025",
    });
  });
});
