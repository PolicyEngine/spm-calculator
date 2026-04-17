import metroData from "@/public/data/metro_geoadj.json";
import spmConfig from "@/public/data/spm_config.json";

export async function loadCalculatorData() {
  return {
    ...spmConfig,
    metroAreas: metroData.metroAreas,
    metroDataYear: metroData.year,
    metroSource: metroData.source,
    metroSourceUrl: metroData.sourceUrl,
  };
}
