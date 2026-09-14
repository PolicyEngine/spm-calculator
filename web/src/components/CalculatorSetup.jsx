"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { Button } from "@policyengine/ui-kit";

export default function CalculatorSetup({ steps, onComplete, advanceRequest }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [furthestIndex, setFurthestIndex] = useState(0);
  const [error, setError] = useState("");
  const headingRef = useRef(null);
  const errorRef = useRef(null);
  const consumedRequest = useRef(null);
  const headingId = useId();
  const errorId = useId();
  const current = steps[activeIndex];
  const lastStep = activeIndex === steps.length - 1;

  useEffect(() => {
    headingRef.current?.focus();
  }, [activeIndex]);

  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error, activeIndex]);

  function goToStep(index) {
    setError("");
    setActiveIndex(index);
  }

  const advance = useCallback(() => {
    if (!current) return;
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
      errorRef.current?.focus();
      return;
    }

    setError("");
    if (lastStep) {
      onComplete();
      return;
    }
    setFurthestIndex((previous) => Math.max(previous, activeIndex + 1));
    setActiveIndex(activeIndex + 1);
  }, [activeIndex, current, lastStep, onComplete, steps]);

  useEffect(() => {
    if (!advanceRequest || advanceRequest === consumedRequest.current) return;
    // The parent replaces this object only for an explicit selection. Consume
    // it even if invalid or stale so revisiting a step cannot replay it.
    consumedRequest.current = advanceRequest;
    if (current?.autoAdvance && advanceRequest.stepId === current.id) {
      advance();
    }
  }, [advanceRequest, current, advance]);

  function handleSubmit(event) {
    event.preventDefault();
    // Search/command-menu Enter events may submit the enclosing form. Only
    // the parent's selection request advances a single-choice step.
    if (current?.autoAdvance) return;
    advance();
  }

  if (!current) return null;

  return (
    <form
      className="mx-auto w-full max-w-xl space-y-8 px-4 py-6 sm:px-0 sm:py-10"
      onSubmit={handleSubmit}
      onKeyDown={(event) => {
        // Let the input/menu handle selection before suppressing the browser's
        // implicit submit, which could target the next step after selection.
        if (
          current.autoAdvance &&
          event.key === "Enter" &&
          event.target.tagName === "INPUT"
        ) {
          event.preventDefault();
        }
      }}
      noValidate
      aria-label="Set up your threshold"
    >
      <nav aria-label="Setup progress" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <p className="font-medium text-primary">SPM threshold calculator</p>
          <p className="text-muted-foreground">
            Step {activeIndex + 1} of {steps.length}
          </p>
        </div>
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
                <span className="block">{step.shortTitle ?? step.title}</span>
                {index <= furthestIndex &&
                  step.valid !== false &&
                  step.summary && (
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
            className="scroll-mt-24 text-3xl font-semibold tracking-tight text-foreground focus:outline-none"
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
            className="scroll-mt-24 border-l-2 border-primary pl-3 text-sm text-foreground focus:outline-2 focus:outline-offset-4 focus:outline-ring"
          >
            {error}
          </p>
        )}
        <div className="space-y-5">{current.content}</div>
      </section>

      {(activeIndex > 0 || !current.autoAdvance) && (
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
          {!current.autoAdvance && (
            <Button
              type="submit"
              className="min-h-11 min-w-36"
              aria-describedby={error ? errorId : undefined}
              disabled={current.valid === false}
            >
              {lastStep ? "View thresholds" : "Continue"}
            </Button>
          )}
        </div>
      )}
    </form>
  );
}
