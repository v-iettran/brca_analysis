/** Normalize METABRIC IHC labels, including the dataset's "Positve" typo. */
export function cleanClinicalStatus(value?: string | null): string {
  if (!value) return "n/a";
  const normalized = value.trim();
  if (normalized.toLowerCase() === "positve") return "Positive";
  return normalized;
}
