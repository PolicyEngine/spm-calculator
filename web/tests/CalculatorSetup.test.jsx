import { useState } from "react";

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

    continueSetup();
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
});
