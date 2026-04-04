/**
 * Extract a Czech region name from a Nominatim address object.
 * Strips " kraj" suffix and normalizes Praha variants so the result
 * can be matched against nazev_organu_cz values in osoba_organy.
 */
export function regionNameFromNominatim(address: Record<string, string>): string | null {
  const candidates = [address.state, address.city, address.county].filter(Boolean);
  for (const name of candidates) {
    if (!name) continue;
    if (name.toLowerCase().includes("kraj") ||
        name === "Praha" || name === "Hlavní město Praha" ||
        name.toLowerCase().includes("vysočina")) {
      // Strip " kraj" suffix and normalize Praha
      const normalized = name
        .replace(/\s+kraj$/i, "")
        .replace(/^Praha$/, "Hlavní město Praha")
        .replace(/^Kraj\s+/i, "");
      return normalized;
    }
  }
  return null;
}
