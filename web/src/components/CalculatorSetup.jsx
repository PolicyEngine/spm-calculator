"use client";

import { useEffect, useId, useRef, useState } from "react";

import { Button } from "@policyengine/ui-kit";

export default function CalculatorSetup({ steps, onComplete }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [furthestIndex, setFurthestIndex] = useState(0);
  const [error, setError] = useState("");
  const headingRef = useRef(null);
  const errorRef = useRef(null);
  const headingId = useId();
  const errorId = useId();
  const current = steps[activeIndex];
  const lastStep = activeIndex === steps.length - 1;

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, [activeIndex]);

  useEffect(() => {
    if (error) errorRef.current?.focus({ preventScroll: true });
  }, [error, activeIndex]);

  function goToStep(index) {
    setError("");
    setActiveIndex(index);
  }

  function handleSubmit(event) {
    event.preventDefault();
    // Later answers can invalidate an earlier choice, such as an area that is
    // unavailable in the selected year. Recheck every step before completion.
    const invalidIndex = lastStep
      ? steps.findIndex((step) => step.valid === false)
      : current.valid === false
        ? activeIndex
        : -1;

    if (invalidIndex !== -1) {
      setActiveIndex(invalidIndex);
      setError(
        lastStep
          ? "Review your answers in this step before viewing thresholds."
          : "Review your answers in this step before continuing.",
      );
      errorRef.current?.focus({ preventScroll: true });
      return;
    }

    setError("");
    if (lastStep) {
      onComplete();
      return;
    }
    setFurthestIndex((previous) => Math.max(previous, activeIndex + 1));
    setActiveIndex(activeIndex + 1);
  }

  if (!current) return null;

  return (
    <form
      className="mx-auto w-full max-w-3xl space-y-8 py-4 sm:py-8"
      onSubmit={handleSubmit}
      noValidate
      aria-label="Set up your threshold"
    >
      <nav aria-label="Setup progress" className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Step {activeIndex + 1} of {steps.length}
        </p>
        <ol className="flex gap-3 sm:gap-5">
          {steps.map((step, index) => (
            <li key={step.id} className="min-w-0 flex-1">
              <button
                type="button"
                aria-current={index === activeIndex ? "step" : undefined}
                disabled={index > furthestIndex}
                onClick={() => goToStep(index)}
                className={`min-h-11 w-full border-t-2 pt-3 text-left text-sm transition-colors motion-reduce:transition-none focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-ring disabled:cursor-default ${
                  index === activeIndex
                    ? "border-primary font-semibold text-primary"
                    : index <= furthestIndex
                      ? "border-primary text-foreground hover:text-primary"
                      : "border-border text-muted-foreground"
                }`}
              >
                <span className="block">{step.title}</span>
                {index <= furthestIndex && step.summary && (
                  <span className="mt-1 hidden text-xs font-normal text-muted-foreground sm:block">
                    {step.summary}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ol>
      </nav>

      <section aria-labelledby={headingId} className="space-y-5">
        <div className="space-y-2">
          <h2
            ref={headingRef}
            id={headingId}
            tabIndex={-1}
            className="text-2xl font-semibold tracking-tight text-foreground focus:outline-none"
          >
            {current.title}
          </h2>
          {current.description && (
            <p className="text-sm leading-relaxed text-muted-foreground">
              {current.description}
            </p>
          )}
        </div>
        {error && (
          <p
            ref={errorRef}
            id={errorId}
            role="alert"
            tabIndex={-1}
            className="border-l-2 border-primary pl-3 text-sm text-foreground focus:outline-2 focus:outline-offset-4 focus:outline-ring"
          >
            {error}
          </p>
        )}
        <div className="space-y-5">{current.content}</div>
      </section>

      <div className="flex items-center justify-end gap-3 border-t border-border pt-5">
        {activeIndex > 0 && (
          <Button
            type="button"
            variant="outline"
            className="mr-auto min-h-11"
            onClick={() => goToStep(activeIndex - 1)}
          >
            Back
          </Button>
        )}
        <Button
          type="submit"
          className="min-h-11 min-w-36"
          aria-describedby={error ? errorId : undefined}
        >
          {lastStep ? "View thresholds" : "Continue"}
        </Button>
      </div>
    </form>
  );
}
