"use client";

import { useState, useMemo } from "react";
import type { MpWithStats } from "@/lib/queries";
import type { getDictionary } from "@/lib/i18n";
import { MpCard } from "@/components/MpCard";

type SortKey = "participation_pct" | "bills_authored" | "speeches_count" | "interpellations_count";

interface Props {
  mps: MpWithStats[];
  locale: string;
  t: ReturnType<typeof getDictionary>;
}

export function MpListClient({ mps, locale, t }: Props) {
  const [search, setSearch] = useState("");
  const [party, setParty] = useState("all");
  const [sortKey, setSortKey] = useState<SortKey>("participation_pct");

  const parties = useMemo(() => {
    const set = new Set<string>();
    for (const mp of mps) {
      if (mp.party_short) set.add(mp.party_short);
    }
    return Array.from(set).sort();
  }, [mps]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return mps
      .filter((mp) => {
        const name = `${mp.prijmeni} ${mp.jmeno}`.toLowerCase();
        const matchSearch = !q || name.includes(q);
        const matchParty = party === "all" || mp.party_short === party;
        return matchSearch && matchParty;
      })
      .sort((a, b) => (b[sortKey] ?? 0) - (a[sortKey] ?? 0));
  }, [mps, search, party, sortKey]);

  const sortOptions: { key: SortKey; label: string }[] = [
    { key: "participation_pct", label: t.mps.participation },
    { key: "bills_authored", label: t.mps.bills },
    { key: "speeches_count", label: t.mps.speeches },
    { key: "interpellations_count", label: t.mps.interpellations },
  ];

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-wrap gap-3 mb-6">
        <input
          type="search"
          placeholder={t.mps.search}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm w-56 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={party}
          onChange={(e) => setParty(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">{t.mps.allParties}</option>
          {parties.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {sortOptions.map((o) => (
            <option key={o.key} value={o.key}>
              {t.mps.sortBy}: {o.label}
            </option>
          ))}
        </select>
        <span className="text-sm text-gray-500 self-center">
          {filtered.length} / {mps.length}
        </span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {filtered.map((mp) => (
          <MpCard key={mp.id_poslanec} mp={mp} locale={locale} t={t} />
        ))}
      </div>
    </div>
  );
}
