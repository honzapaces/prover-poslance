"use client";

import { useState, useMemo } from "react";
import type { MpWithStats } from "@/lib/queries";
import type { getDictionary } from "@/lib/i18n";
import { MpCard } from "@/components/MpCard";

type Status = "idle" | "locating" | "geocoding" | "done" | "denied" | "error";

interface Props {
  mps: MpWithStats[];
  locale: string;
  t: ReturnType<typeof getDictionary>;
}

export function WhoRepresentsMe({ mps, locale, t }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [krajId, setKrajId] = useState<number | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Derive distinct regions from actual MP data
  const regions = useMemo(() => {
    const map = new Map<number, { cs: string; en: string }>();
    for (const mp of mps) {
      if (mp.id_kraj != null && !map.has(mp.id_kraj)) {
        map.set(mp.id_kraj, {
          cs: mp.kraj_name_cs ?? String(mp.id_kraj),
          en: mp.kraj_name_en ?? String(mp.id_kraj),
        });
      }
    }
    const lang = locale === "cs" ? "cs" : "en";
    return Array.from(map.entries())
      .sort((a, b) => a[1][lang].localeCompare(b[1][lang]))
      .map(([id, names]) => ({ id, name: names[lang] }));
  }, [mps, locale]);

  const regionMps = useMemo(
    () => (krajId != null ? mps.filter((mp) => mp.id_kraj === krajId) : []),
    [mps, krajId]
  );

  const regionLabel = useMemo(
    () => regions.find((r) => r.id === krajId)?.name ?? null,
    [regions, krajId]
  );

  async function locate() {
    if (!navigator.geolocation) {
      setStatus("denied");
      return;
    }
    setStatus("locating");
    setErrorMsg(null);

    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        setStatus("geocoding");
        try {
          const res = await fetch(
            `/api/geocode?lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`
          );
          const data = await res.json();
          if (data.regionName) {
            const needle = (data.regionName as string).toLowerCase();
            // Match against both cs and en names from actual MP data
            const match = regions.find((r) => {
              const mp = mps.find((m) => m.id_kraj === r.id);
              return (
                mp?.kraj_name_cs?.toLowerCase() === needle ||
                mp?.kraj_name_en?.toLowerCase() === needle ||
                r.name.toLowerCase() === needle
              );
            });
            if (match) {
              setKrajId(match.id);
              setStatus("done");
            } else {
              setStatus("denied");
            }
          } else {
            setStatus("denied");
          }
        } catch {
          setStatus("error");
          setErrorMsg(t.myRegion.errorGeocode);
        }
      },
      (err) => {
        if (err.code === err.PERMISSION_DENIED) {
          setStatus("denied");
        } else {
          setStatus("error");
          setErrorMsg(t.myRegion.errorLocation);
        }
      },
      { timeout: 10_000 }
    );
  }

  return (
    <div>
      {/* Locate / status card */}
      <div
        className="cr-card p-6 mb-8"
        style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}
      >
        {/* Top row: button + status */}
        <div className="flex flex-wrap items-center gap-4">
          <button
            onClick={locate}
            disabled={status === "locating" || status === "geocoding"}
            style={{
              background: "var(--cr-blue)",
              color: "white",
              border: "none",
              borderRadius: "4px",
              padding: "0.625rem 1.25rem",
              fontFamily: "'Barlow', sans-serif",
              fontSize: "0.9rem",
              fontWeight: 600,
              cursor: status === "locating" || status === "geocoding" ? "not-allowed" : "pointer",
              opacity: status === "locating" || status === "geocoding" ? 0.7 : 1,
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              transition: "opacity 0.15s",
            }}
          >
            <span aria-hidden>📍</span>
            {status === "locating"
              ? t.myRegion.locating
              : status === "geocoding"
              ? t.myRegion.geocoding
              : t.myRegion.locateMe}
          </button>

          {status === "done" && regionLabel && (
            <span
              style={{
                color: "var(--cr-text-muted)",
                fontSize: "0.875rem",
                display: "flex",
                alignItems: "center",
                gap: "0.375rem",
              }}
            >
              <span style={{ color: "var(--cr-blue)", fontWeight: 600 }}>✓</span>
              {t.myRegion.detectedRegion}: <strong style={{ color: "var(--cr-text)" }}>{regionLabel}</strong>
            </span>
          )}

          {status === "error" && (
            <span style={{ color: "var(--cr-red)", fontSize: "0.875rem" }}>
              {errorMsg ?? t.myRegion.errorLocation}
            </span>
          )}
        </div>

        {/* Manual region picker — always shown, pre-selected after geolocation */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          <label
            style={{
              fontSize: "0.8rem",
              fontWeight: 600,
              color: "var(--cr-text-muted)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            {status === "denied"
              ? t.myRegion.chooseRegionFallback
              : t.myRegion.chooseRegion}
          </label>
          <select
            value={krajId ?? ""}
            onChange={(e) => {
              const v = Number(e.target.value);
              setKrajId(v || null);
              if (v) setStatus("done");
            }}
            style={{
              border: "1px solid var(--cr-border)",
              borderRadius: "4px",
              padding: "0.5rem 0.75rem",
              fontSize: "0.875rem",
              color: krajId ? "var(--cr-text)" : "var(--cr-text-faint)",
              background: "var(--cr-white)",
              outline: "none",
              fontFamily: "'Barlow', sans-serif",
              maxWidth: "22rem",
              cursor: "pointer",
            }}
          >
            <option value="">{t.myRegion.selectPlaceholder}</option>
            {regions.map(({ id, name }) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* MP grid */}
      {krajId != null && (
        <div>
          <p
            style={{
              color: "var(--cr-text-muted)",
              fontSize: "0.85rem",
              marginBottom: "1.25rem",
            }}
          >
            {regionMps.length === 0
              ? t.myRegion.noMps
              : t.myRegion.mpCount
                  .replace("{count}", String(regionMps.length))
                  .replace("{region}", regionLabel ?? "")}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
            {regionMps.map((mp) => (
              <MpCard key={mp.id_poslanec} mp={mp} locale={locale} t={t} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
