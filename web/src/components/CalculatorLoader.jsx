"use client";

import { useEffect, useState } from "react";
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@policyengine/ui-kit";

import { loadCalculatorData } from "@/lib/loadCalculatorData";
import CalculatorWorkbench from "./CalculatorWorkbench";

export default function CalculatorLoader() {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ data: null, error: false });

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => {
      controller.abort();
      setState({ data: null, error: true });
    }, 30_000);

    loadCalculatorData({ signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, error: false });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState({ data: null, error: true });
        }
      })
      .finally(() => clearTimeout(timeout));

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  if (state.data) return <CalculatorWorkbench data={state.data} />;

  return (
    <div className="mx-auto w-full max-w-7xl px-4 py-12 sm:px-6">
      <Card aria-busy={!state.error} aria-labelledby="calculator-loading-title">
        <CardHeader>
          <CardTitle id="calculator-loading-title">SPM calculator</CardTitle>
        </CardHeader>
        <CardContent>
          {state.error ? (
            <div>
              <p role="alert" className="mb-4">
                We couldn’t load the calculator data. Check your connection and
                try again.
              </p>
              <Button
                type="button"
                onClick={() => {
                  setState({ data: null, error: false });
                  setAttempt((value) => value + 1);
                }}
              >
                Try again
              </Button>
            </div>
          ) : (
            <p role="status">Loading thresholds and geographic inputs…</p>
          )}
        </CardContent>
      </Card>
      <noscript>Enable JavaScript to use the SPM calculator.</noscript>
    </div>
  );
}
