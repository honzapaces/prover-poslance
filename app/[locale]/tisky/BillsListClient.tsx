"use client";

import { useState, useMemo } from "react";
import type { BillRow } from "@/lib/queries";
import type { getDictionary } from "@/lib/i18n";

interface Props {
  bills: BillRow[];
  locale: string;
  t: ReturnType<typeof getDictionary>;
}

const controlStyle: React.CSSProperties = {
  border: "1px solid var(--cr-border)",
  borderRadius: "4px",
  padding: "0.5rem 0.75rem",
  fontSize: "0.875rem",
  color: "var(--cr-text)",
  background: "var(--cr-white)",
  outline: "none",
  fontFamily: "'Barlow', sans-serif",
  fontWeight: 400,
};

export function BillsListClient({ bills, locale, t }: Props) {
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [passedFilter, setPassedFilter] = useState<"all" | "passed" | "pending">("all");

  const billTypes = useMemo(() => {
    const set = new Set<string>();
    for (const b of bills) {
      if (b.bill_type) set.add(b.bill_type);
    }
    return Array.from(set).sort();
  }, [bills]);

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    return bills.filter((b) => {
      const matchSearch =
        !q ||
        b.title.toLowerCase().includes(q) ||
        (b.submitter_name ?? "").toLowerCase().includes(q);
      const matchType = typeFilter === "all" || b.bill_type === typeFilter;
      const matchPassed =
        passedFilter === "all" ||
        (passedFilter === "passed" && b.passed === 1) ||
        (passedFilter === "pending" && b.passed === 0);
      return matchSearch && matchType && matchPassed;
    });
  }, [bills, search, typeFilter, passedFilter]);

  const dateStr = (s: string | null) => {
    if (!s) return "";
    return new Date(s).toLocaleDateString(locale === "cs" ? "cs-CZ" : "en-GB", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  return (
    <div>
      {/* Controls */}
      <div
        className="cr-card flex flex-wrap items-center gap-3 p-4 mb-6"
        style={{ background: "var(--cr-white)" }}
      >
        <input
          type="search"
          placeholder={t.bills.search}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ ...controlStyle, width: "15rem" }}
          onFocus={(e) => (e.target.style.borderColor = "var(--cr-blue)")}
          onBlur={(e) => (e.target.style.borderColor = "var(--cr-border)")}
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          style={controlStyle}
          onFocus={(e) => (e.target.style.borderColor = "var(--cr-blue)")}
          onBlur={(e) => (e.target.style.borderColor = "var(--cr-border)")}
        >
          <option value="all">{t.bills.allTypes}</option>
          {billTypes.map((bt) => (
            <option key={bt} value={bt}>
              {bt}
            </option>
          ))}
        </select>
        <select
          value={passedFilter}
          onChange={(e) => setPassedFilter(e.target.value as typeof passedFilter)}
          style={controlStyle}
          onFocus={(e) => (e.target.style.borderColor = "var(--cr-blue)")}
          onBlur={(e) => (e.target.style.borderColor = "var(--cr-border)")}
        >
          <option value="all">{t.bills.allStatuses}</option>
          <option value="passed">{t.bills.passed}</option>
          <option value="pending">{t.bills.pending}</option>
        </select>

        <span style={{ marginLeft: "auto", color: "var(--cr-text-muted)", fontSize: "0.8rem" }}>
          <strong style={{ color: "var(--cr-red)", fontWeight: 700 }}>{filtered.length}</strong>
          <span style={{ color: "var(--cr-text-faint)" }}> / {bills.length}</span>
        </span>
      </div>

      {/* Table */}
      <div className="cr-card" style={{ overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid var(--cr-border)" }}>
              {[t.bills.colTitle, t.bills.colType, t.bills.colSubmitter, t.bills.colDate, t.bills.colStatus].map((h) => (
                <th
                  key={h}
                  style={{
                    padding: "0.75rem 1rem",
                    textAlign: "left",
                    color: "var(--cr-text-muted)",
                    fontWeight: 600,
                    fontSize: "0.75rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    whiteSpace: "nowrap",
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((bill, i) => (
              <tr
                key={bill.id_tisk}
                style={{
                  borderBottom: i < filtered.length - 1 ? "1px solid var(--cr-border)" : "none",
                  background: bill.passed === 1 ? "var(--cr-blue-wash)" : "transparent",
                }}
              >
                <td style={{ padding: "0.75rem 1rem", maxWidth: "28rem" }}>
                  <a
                    href={`https://www.psp.cz/sqw/tisky.sqw?O=10&PT=${bill.id_tisk}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      color: "var(--cr-blue)",
                      textDecoration: "none",
                      fontWeight: 500,
                      lineHeight: 1.4,
                      display: "block",
                    }}
                    className="hover:underline"
                  >
                    {bill.title}
                  </a>
                </td>
                <td
                  style={{
                    padding: "0.75rem 1rem",
                    color: "var(--cr-text-muted)",
                    whiteSpace: "nowrap",
                    fontSize: "0.8rem",
                  }}
                >
                  {bill.bill_type ?? "—"}
                </td>
                <td style={{ padding: "0.75rem 1rem", color: "var(--cr-text)", whiteSpace: "nowrap" }}>
                  {bill.submitter_name ?? "—"}
                </td>
                <td
                  style={{
                    padding: "0.75rem 1rem",
                    color: "var(--cr-text-muted)",
                    whiteSpace: "nowrap",
                    fontSize: "0.8rem",
                  }}
                >
                  {dateStr(bill.submitted_at)}
                </td>
                <td style={{ padding: "0.75rem 1rem" }}>
                  {bill.passed === 1 ? (
                    <span
                      style={{
                        fontSize: "0.7rem",
                        fontWeight: 600,
                        color: "var(--cr-blue)",
                        background: "var(--cr-blue-tint)",
                        padding: "0.2rem 0.5rem",
                        borderRadius: "3px",
                        textTransform: "uppercase",
                        letterSpacing: "0.04em",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {t.bills.passed}
                    </span>
                  ) : (
                    <span style={{ color: "var(--cr-text-faint)", fontSize: "0.8rem" }}>
                      {t.bills.pending}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p
            style={{
              padding: "2rem",
              textAlign: "center",
              color: "var(--cr-text-faint)",
              fontSize: "0.875rem",
            }}
          >
            {t.bills.noResults}
          </p>
        )}
      </div>
    </div>
  );
}
