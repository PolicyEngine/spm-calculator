import { fireEvent, render, screen, within } from "@testing-library/react";

export function completeSetup({
  area = "35620",
  adults = 2,
  children = 2,
  year = 2025,
} = {}) {
  // Result tests use an explicit reference-family fixture. Production setup
  // starts blank; never let this helper rely on preselected personal answers.
  fireEvent.change(screen.getByLabelText("Search SPM areas"), {
    target: { value: area },
  });
  fireEvent.click(
    within(
      screen.getByRole("listbox", { name: "Matching SPM areas" }),
    ).getAllByRole("option")[0],
  );
  fireEvent.change(screen.getByLabelText("Adults"), {
    target: { value: String(adults) },
  });
  fireEvent.change(screen.getByLabelText("Children"), {
    target: { value: String(children) },
  });
  fireEvent.mouseDown(
    screen.getByRole("tab", { name: "Renter", exact: true }),
    { button: 0, ctrlKey: false },
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Continue", exact: true }),
  );
  fireEvent.click(
    screen.getByRole("button", {
      name: year > 2025 ? `${year} (forecast)` : String(year),
      exact: true,
    }),
  );
}

export function renderCalculator(ui, options) {
  const result = render(ui, options);
  completeSetup();
  return result;
}
