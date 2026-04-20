import { Suspense } from "react";

import { loadCalculatorData } from "@/lib/loadCalculatorData";
import CalculatorWorkbench from "@/src/components/CalculatorWorkbench";

export default async function Page() {
  const data = await loadCalculatorData();

  return (
    <main>
      <h1 className="sr-only">
        SPM Threshold Calculator — Supplemental Poverty Measure by PolicyEngine
      </h1>
      <Suspense fallback={null}>
        <CalculatorWorkbench data={data} />
      </Suspense>
    </main>
  );
}
