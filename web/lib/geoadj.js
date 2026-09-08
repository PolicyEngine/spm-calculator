/** Apply a Census area rent index to the housing share of the national base. */
export function calculateGeoadj({ rentIndex, housingShare }) {
  if (
    !Number.isFinite(rentIndex) || rentIndex <= 0 ||
    !Number.isFinite(housingShare) || housingShare <= 0 || housingShare >= 1
  ) {
    throw new Error("Rent index and housing share must be valid positive values.");
  }
  return 1 - housingShare + housingShare * rentIndex;
}
