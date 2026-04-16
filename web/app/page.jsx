import { Suspense } from "react";

import { loadCalculatorData } from "@/lib/loadCalculatorData";
import CalculatorWorkbench from "@/src/components/CalculatorWorkbench";

export default async function Page() {
  const data = await loadCalculatorData();

  return (
    <Suspense fallback={null}>
      <CalculatorWorkbench data={data} />
    </Suspense>
  );
}
