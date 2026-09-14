import { fireEvent, render, screen } from "@testing-library/react";

export function completeSetup() {
  fireEvent.click(
    screen.getByRole("button", { name: "Continue", exact: true }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Continue", exact: true }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "View thresholds", exact: true }),
  );
}

export function renderCalculator(ui, options) {
  const result = render(ui, options);
  completeSetup();
  return result;
}
