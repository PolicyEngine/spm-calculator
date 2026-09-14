"use client";

import { useId, useRef, useState } from "react";

const CHART_HEIGHT = 252;
const PLOT_TOP = 18;
const PLOT_BOTTOM = 214;

function currency(value, digits = 0) {
  return Number.isFinite(value)
    ? value.toLocaleString("en-US", {
        style: "currency",
        currency: "USD",
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })
    : "Unavailable";
}

function factor(value, digits = 3) {
  return Number.isFinite(value) ? value.toFixed(digits) : "Unavailable";
}

function nationalStatus(row) {
  if (row.nationalStatus === "published") return "Published national base";
  if (row.nationalStatus === "forecast") return "Forecast national base";
  return "National base status unavailable";
}

// A zero origin preserves the relative size of annual changes. Round the scale
// up in 1/2/5 increments so the four intervals have readable dollar labels.
function axisMaximum(rows) {
  const maximum = Math.max(
    0,
    ...rows.map((row) =>
      Number.isFinite(row.localThreshold) ? row.localThreshold : 0,
    ),
  );
  if (maximum === 0) return 40000;
  const interval = maximum / 4;
  const magnitude = 10 ** Math.floor(Math.log10(interval));
  const rounded = [1, 2, 5, 10].find(
    (multiple) => multiple * magnitude >= interval,
  );
  return rounded * magnitude * 4;
}

function Breakdown({ row, id }) {
  return (
    <div
      id={id}
      role="tooltip"
      data-testid="threshold-history-tooltip"
      className="pointer-events-auto max-w-full rounded-lg border border-border bg-background p-3 text-sm shadow-md"
    >
      <div className="flex items-baseline justify-between gap-4">
        <strong>{row.year}</strong>
        <strong className="text-lg tabular-nums">
          {currency(row.localThreshold)}
        </strong>
      </div>
      <dl className="mt-2 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-xs">
        <dt className="text-muted-foreground">
          National base (2 adults, 2 children)
        </dt>
        <dd className="text-right tabular-nums">
          {currency(row.nationalBase)}
        </dd>
        <dt className="text-muted-foreground">Household scale</dt>
        <dd className="text-right tabular-nums">
          ×{factor(row.equivalenceScale)}
        </dd>
        <dt className="text-muted-foreground">Location factor (GEOADJ)</dt>
        <dd className="text-right tabular-nums">×{factor(row.adjustment)}</dd>
      </dl>
      <p className="mt-2 border-t border-border pt-2 text-xs tabular-nums">
        {currency(row.nationalBase)} × {factor(row.equivalenceScale)} ×{" "}
        {factor(row.adjustment)} ≈ {currency(row.localThreshold)}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        GEOADJ = 1 + housing share × (rent index − 1)
      </p>
      <p className="mt-1 text-xs tabular-nums">
        1 + {factor(row.housingShare)} × ({factor(row.rentIndex)} − 1) ≈{" "}
        {factor(row.adjustment)}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">
        {row.componentStatus || nationalStatus(row)}
      </p>
    </div>
  );
}

/** Annual local thresholds. All calculations and component statuses come from
 * the caller's frozen artifact; this view never fills missing observations. */
export default function ThresholdHistoryChart({
  data = [],
  selectedYear,
  onSelectYear,
}) {
  const id = useId();
  const pointRefs = useRef(new Map());
  const [hoverYear, setHoverYear] = useState(null);
  const [focusYear, setFocusYear] = useState(null);
  const [pinnedYear, setPinnedYear] = useState(null);
  const rows = data
    .map((row) => ({ ...row, year: Number(row.year) }))
    .sort((left, right) => left.year - right.year);
  const numericSelectedYear = Number(selectedYear);
  const activeYear = hoverYear ?? focusYear ?? pinnedYear;
  const activeRow = rows.find((row) => row.year === activeYear);
  const tabYear = rows.some((row) => row.year === numericSelectedYear)
    ? numericSelectedYear
    : rows[0]?.year;
  const maximum = axisMaximum(rows);
  const firstYear = rows[0]?.year;
  const lastYear = rows.at(-1)?.year;
  const positionX = (year) =>
    rows.length === 1
      ? 50
      : ((year - firstYear) / (lastYear - firstYear)) * 100;
  const positionY = (value) =>
    PLOT_BOTTOM - (value / maximum) * (PLOT_BOTTOM - PLOT_TOP);
  const hasMissing = rows.some((row) => !Number.isFinite(row.localThreshold));
  const tickYears = new Set(
    rows
      .filter(
        (_, index) =>
          index % Math.max(1, Math.ceil((rows.length - 1) / 3)) === 0 ||
          index === rows.length - 1,
      )
      .map((row) => row.year),
  );

  function dismiss() {
    setHoverYear(null);
    setFocusYear(null);
    setPinnedYear(null);
  }

  function handleKey(event, index) {
    const destinations = {
      ArrowLeft: Math.max(0, index - 1),
      ArrowDown: Math.max(0, index - 1),
      ArrowRight: Math.min(rows.length - 1, index + 1),
      ArrowUp: Math.min(rows.length - 1, index + 1),
      Home: 0,
      End: rows.length - 1,
    };
    if (event.key in destinations) {
      event.preventDefault();
      const nextYear = rows[destinations[event.key]].year;
      setHoverYear(null);
      setFocusYear(nextYear);
      pointRefs.current.get(nextYear)?.focus();
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setPinnedYear(rows[index].year);
      onSelectYear?.(rows[index].year);
    } else if (event.key === "Escape") {
      event.preventDefault();
      dismiss();
    }
  }

  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No annual thresholds available.
      </p>
    );
  }

  return (
    <div data-testid="threshold-history-chart" className="min-w-0">
      <div className="mb-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-2">
          <span className="w-5 border-t-2 border-primary" aria-hidden="true" />
          Published national base
        </span>
        <span className="inline-flex items-center gap-2">
          <span
            className="w-5 border-t-2 border-dashed border-primary"
            aria-hidden="true"
          />
          Forecast national base
        </span>
      </div>
      <p id={`${id}-instructions`} className="sr-only">
        Local thresholds by year. Hover, focus, or tap a year for its breakdown.
        Use arrow keys to move between years
        {onSelectYear ? ", then Enter to select" : ""}. Press Escape to close
        the breakdown. Component status distinguishes published inputs from
        modeled geography and shares.
      </p>
      <div className="relative" onMouseLeave={() => setHoverYear(null)}>
        <svg
          role="group"
          aria-label="Year-by-year threshold chart"
          aria-describedby={`${id}-instructions`}
          width="100%"
          height={CHART_HEIGHT}
          className="overflow-visible"
        >
          {[0, 1, 2, 3, 4].map((index) => {
            const value = (maximum * index) / 4;
            const y = positionY(value);
            return (
              <g key={value} aria-hidden="true">
                <text
                  x={46}
                  y={y}
                  dy="0.32em"
                  textAnchor="end"
                  fill="var(--muted-foreground)"
                  fontSize={11}
                >
                  {value === 0
                    ? "$0"
                    : `$${(value / 1000).toLocaleString("en-US")}k`}
                </text>
                <line x1={56} x2="100%" y1={y} y2={y} stroke="var(--border)" />
              </g>
            );
          })}
          <svg
            x={68}
            width="calc(100% - 92px)"
            height={CHART_HEIGHT}
            overflow="visible"
          >
            {rows.slice(1).map((row, index) => {
              const previous = rows[index];
              if (
                !Number.isFinite(previous.localThreshold) ||
                !Number.isFinite(row.localThreshold) ||
                row.year !== previous.year + 1
              )
                return null;
              const published =
                row.nationalStatus === "published" &&
                previous.nationalStatus === "published";
              return (
                <line
                  key={`${previous.year}-${row.year}`}
                  data-testid="threshold-history-segment"
                  data-from-year={previous.year}
                  data-to-year={row.year}
                  data-status={published ? "published" : "forecast"}
                  x1={`${positionX(previous.year)}%`}
                  x2={`${positionX(row.year)}%`}
                  y1={positionY(previous.localThreshold)}
                  y2={positionY(row.localThreshold)}
                  stroke="var(--primary)"
                  strokeWidth={2.5}
                  strokeDasharray={published ? undefined : "6 5"}
                  aria-hidden="true"
                />
              );
            })}
            {rows.map((row, index) => {
              const x = `${positionX(row.year)}%`;
              const available = Number.isFinite(row.localThreshold);
              const y = available ? positionY(row.localThreshold) : PLOT_BOTTOM;
              const highlighted =
                row.year === activeYear || row.year === numericSelectedYear;
              return (
                <g key={row.year}>
                  {tickYears.has(row.year) && (
                    <text
                      x={x}
                      y={238}
                      textAnchor="middle"
                      fill="var(--muted-foreground)"
                      fontSize={12}
                      aria-hidden="true"
                    >
                      {row.year}
                    </text>
                  )}
                  <g
                    role="button"
                    ref={(element) => {
                      if (element) pointRefs.current.set(row.year, element);
                      else pointRefs.current.delete(row.year);
                    }}
                    tabIndex={row.year === (focusYear ?? tabYear) ? 0 : -1}
                    aria-label={`${row.year}: ${currency(row.localThreshold)}. ${row.componentStatus || nationalStatus(row)}`}
                    aria-current={
                      row.year === numericSelectedYear ? "date" : undefined
                    }
                    aria-describedby={
                      row.year === activeYear ? `${id}-tooltip` : undefined
                    }
                    data-testid={`threshold-year-${row.year}`}
                    className="group cursor-pointer outline-none"
                    onMouseEnter={() => setHoverYear(row.year)}
                    onFocus={() => {
                      setHoverYear(null);
                      setFocusYear(row.year);
                    }}
                    onBlur={() => setFocusYear(null)}
                    onClick={() => {
                      setPinnedYear(row.year);
                      onSelectYear?.(row.year);
                    }}
                    onKeyDown={(event) => handleKey(event, index)}
                  >
                    <rect
                      x={`${positionX(row.year) - (rows.length === 1 ? 50 : 50 / (lastYear - firstYear))}%`}
                      y={PLOT_TOP - 8}
                      width={`${rows.length === 1 ? 100 : 100 / (lastYear - firstYear)}%`}
                      height={PLOT_BOTTOM - PLOT_TOP + 30}
                      fill="transparent"
                    />
                    <circle
                      cx={x}
                      cy={y}
                      r={10}
                      fill="none"
                      stroke="var(--ring)"
                      strokeWidth={2}
                      className="opacity-0 group-focus-visible:opacity-100"
                    />
                    {available ? (
                      <circle
                        cx={x}
                        cy={y}
                        r={highlighted ? 5 : 3.5}
                        fill={
                          row.nationalStatus === "published"
                            ? "var(--primary)"
                            : "var(--background)"
                        }
                        stroke="var(--primary)"
                        strokeWidth={2}
                      />
                    ) : (
                      <text
                        x={x}
                        y={y}
                        dy="0.32em"
                        textAnchor="middle"
                        fill="var(--muted-foreground)"
                        fontSize={16}
                      >
                        ×
                      </text>
                    )}
                  </g>
                </g>
              );
            })}
          </svg>
        </svg>
        {activeRow && (
          <div
            className={`relative z-10 mb-2 w-80 max-w-full sm:absolute sm:top-1 sm:mb-0 ${positionX(activeRow.year) < 50 ? "right-0" : "left-0"}`}
            onKeyDown={(event) => {
              if (event.key === "Escape") dismiss();
            }}
          >
            <Breakdown row={activeRow} id={`${id}-tooltip`} />
            <button
              type="button"
              onClick={dismiss}
              className="mt-1 text-xs text-primary underline underline-offset-2"
              aria-label="Close threshold breakdown"
            >
              Close breakdown
            </button>
          </div>
        )}
      </div>
      <p className="text-xs text-muted-foreground">
        Hover, focus, or tap a year for the breakdown.
        {hasMissing ? " Gaps indicate unavailable thresholds." : ""}
      </p>
      <details className="mt-3 text-sm" data-testid="threshold-history-values">
        <summary className="w-fit cursor-pointer text-primary underline-offset-4 hover:underline">
          Show values
        </summary>
        <div
          className="mt-3 overflow-x-auto"
          role="region"
          aria-label="Year-by-year thresholds"
          tabIndex={0}
        >
          <table className="w-full text-left text-xs">
            <caption className="sr-only">
              Annual threshold inputs and local thresholds
            </caption>
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                {[
                  "Year",
                  "National base",
                  "Location factor",
                  "Local threshold",
                  "Component status",
                  "Household scale",
                  "Housing share",
                  "Rent index",
                ].map((heading) => (
                  <th
                    key={heading}
                    scope="col"
                    className="px-2 py-2 font-medium"
                  >
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.year} className="border-b border-border align-top">
                  <td
                    aria-current={
                      row.year === numericSelectedYear ? "date" : undefined
                    }
                    className="px-2 py-2 font-medium"
                  >
                    {row.year}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 tabular-nums">
                    {currency(row.nationalBase)}
                  </td>
                  <td className="px-2 py-2 tabular-nums">
                    {Number.isFinite(row.adjustment)
                      ? `×${factor(row.adjustment)}`
                      : "Unavailable"}
                  </td>
                  <td className="whitespace-nowrap px-2 py-2 tabular-nums">
                    {currency(row.localThreshold)}
                  </td>
                  <td className="min-w-48 px-2 py-2">
                    {row.componentStatus || nationalStatus(row)}
                  </td>
                  <td className="px-2 py-2 tabular-nums">
                    {factor(row.equivalenceScale, 6)}
                  </td>
                  <td className="px-2 py-2 tabular-nums">
                    {factor(row.housingShare, 6)}
                  </td>
                  <td className="px-2 py-2 tabular-nums">
                    {factor(row.rentIndex, 6)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
