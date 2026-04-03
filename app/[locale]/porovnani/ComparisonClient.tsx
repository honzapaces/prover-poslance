"use client";

import { useRouter } from "next/navigation";
import Image from "next/image";
import type { MpWithStats } from "@/lib/queries";
import type { getDictionary } from "@/lib/i18n";

interface Props {
  mps: MpWithStats[];
  mp1: MpWithStats | null;
  mp2: MpWithStats | null;
  locale: string;
  t: ReturnType<typeof getDictionary>;
  selectedA: string;
  selectedB: string;
}

function photoUrl(mp: MpWithStats) {
  if (mp.foto && mp.term_year && mp.id_osoba) {
    return `https://www.psp.cz/eknih/cdrom/${mp.term_year}ps/eknih/${mp.term_year}ps/poslanci/i${mp.id_osoba}.jpg`;
  }
  return null;
}

function MpColumn({
  mp,
  locale,
  t,
  otherMp,
}: {
  mp: MpWithStats;
  locale: string;
  t: ReturnType<typeof getDictionary>;
  otherMp: MpWithStats | null;
}) {
  const photo = photoUrl(mp);
  const fullName = [mp.pred, mp.jmeno, mp.prijmeni, mp.za].filter(Boolean).join(" ");

  function winner(a: number, b: number | null) {
    if (b === null) return false;
    return a > b;
  }

  const metrics: { label: string; value: number; max: number; unit?: string }[] = [
    { label: t.mp.participation, value: mp.participation_pct, max: 100, unit: " %" },
    { label: t.mp.billsAuthored, value: mp.bills_authored, max: Math.max(mp.bills_authored, otherMp?.bills_authored ?? 0, 1) },
    { label: t.mp.speeches, value: mp.speeches_count, max: Math.max(mp.speeches_count, otherMp?.speeches_count ?? 0, 1) },
    { label: t.mp.interpellations, value: mp.interpellations_count, max: Math.max(mp.interpellations_count, otherMp?.interpellations_count ?? 0, 1) },
  ];
  const otherMetrics = otherMp
    ? [otherMp.participation_pct, otherMp.bills_authored, otherMp.speeches_count, otherMp.interpellations_count]
    : [null, null, null, null];

  return (
    <div className="cr-card p-5 flex-1 min-w-0">
      {/* Photo + name */}
      <div className="flex items-center gap-3 mb-5">
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: "6px",
            overflow: "hidden",
            flexShrink: 0,
            background: "var(--cr-blue-mid)",
            border: "2px solid var(--cr-blue)",
          }}
        >
          {photo ? (
            <Image src={photo} alt={fullName} width={56} height={56} className="w-full h-full object-cover" unoptimized />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center"
              style={{ color: "white", fontFamily: "'EB Garamond', serif", fontWeight: 700, fontSize: "1.5rem", background: "var(--cr-blue)" }}
            >
              {mp.prijmeni[0]}
            </div>
          )}
        </div>
        <div className="min-w-0">
          <p style={{ fontWeight: 700, color: "var(--cr-text)", fontSize: "1rem", lineHeight: 1.2 }} className="truncate">
            {fullName}
          </p>
          {mp.party_short && (
            <span
              style={{
                fontSize: "0.7rem",
                background: "var(--cr-blue-wash)",
                color: "var(--cr-blue)",
                border: "1px solid var(--cr-blue-tint)",
                borderRadius: "3px",
                padding: "0.1rem 0.4rem",
                fontWeight: 600,
                letterSpacing: "0.04em",
              }}
            >
              {mp.party_short}
            </span>
          )}
        </div>
      </div>

      {/* Metrics */}
      <div className="space-y-4">
        {metrics.map((m, i) => {
          const pct = m.max > 0 ? Math.min((m.value / m.max) * 100, 100) : 0;
          const isWinner = winner(m.value, otherMetrics[i]);
          return (
            <div key={m.label}>
              <div className="flex justify-between mb-1" style={{ fontSize: "0.8rem" }}>
                <span style={{ color: "var(--cr-text-muted)" }}>{m.label}</span>
                <span
                  style={{
                    fontWeight: 700,
                    color: isWinner ? "var(--cr-blue)" : "var(--cr-text)",
                    fontSize: isWinner ? "0.9rem" : "0.8rem",
                  }}
                >
                  {m.value}{m.unit ?? ""}
                  {isWinner && " ▲"}
                </span>
              </div>
              <div className="stat-bar-track" style={{ height: "4px" }}>
                <div className="stat-bar-fill" style={{ width: `${pct}%`, height: "4px" }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function ComparisonClient({ mps, mp1, mp2, locale, t, selectedA, selectedB }: Props) {
  const router = useRouter();

  function handleChange(which: "a" | "b", value: string) {
    const a = which === "a" ? value : selectedA;
    const b = which === "b" ? value : selectedB;
    const params = new URLSearchParams();
    if (a) params.set("a", a);
    if (b) params.set("b", b);
    router.push(`/${locale}/porovnani?${params.toString()}`);
  }

  const selectStyle: React.CSSProperties = {
    background: "var(--cr-white)",
    border: "1px solid var(--cr-border)",
    borderRadius: "4px",
    padding: "0.5rem 0.75rem",
    fontSize: "0.875rem",
    color: "var(--cr-text)",
    width: "100%",
    maxWidth: "22rem",
  };

  return (
    <div>
      {/* Selectors */}
      <div className="flex flex-wrap gap-6 mb-8">
        {(["a", "b"] as const).map((which) => (
          <div key={which} style={{ flex: "1 1 18rem" }}>
            <label
              style={{
                display: "block",
                fontSize: "0.75rem",
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--cr-text-muted)",
                marginBottom: "0.375rem",
              }}
            >
              {which === "a" ? t.comparison.selectFirst : t.comparison.selectSecond}
            </label>
            <select
              value={which === "a" ? selectedA : selectedB}
              onChange={(e) => handleChange(which, e.target.value)}
              style={selectStyle}
            >
              <option value="">{t.comparison.selectPlaceholder}</option>
              {mps.map((mp) => {
                const name = `${mp.prijmeni} ${mp.jmeno}${mp.party_short ? ` (${mp.party_short})` : ""}`;
                return (
                  <option key={mp.id_poslanec} value={mp.id_poslanec}>
                    {name}
                  </option>
                );
              })}
            </select>
          </div>
        ))}
      </div>

      {/* Comparison columns */}
      {mp1 && mp2 ? (
        <div className="flex flex-col sm:flex-row gap-4">
          <MpColumn mp={mp1} locale={locale} t={t} otherMp={mp2} />
          <MpColumn mp={mp2} locale={locale} t={t} otherMp={mp1} />
        </div>
      ) : (
        <p style={{ color: "var(--cr-text-faint)", fontSize: "0.9rem" }}>
          {t.comparison.selectPlaceholder}
        </p>
      )}
    </div>
  );
}
