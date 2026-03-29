export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import Link from "next/link";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getPartyList } from "@/lib/queries";

export default async function StranyPage({ params }: PageProps<"/[locale]/strany">) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);
  const parties = await getPartyList();

  return (
    <div>
      <div className="mb-8 section-accent">
        <h1
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--cr-text)",
            fontWeight: 700,
            fontSize: "2rem",
            lineHeight: 1.2,
          }}
        >
          {t.parties.title}
        </h1>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {parties.map((party) => {
          const pct = party.avg_participation ?? 0;
          return (
            <Link
              key={party.id_organ}
              href={`/${locale}/poslanci`}
              style={{ textDecoration: "none" }}
            >
              <div
                className="cr-card p-5 h-full"
                style={{ cursor: "pointer", transition: "box-shadow 0.15s" }}
              >
                {/* Party header */}
                <div className="flex items-baseline gap-3 mb-4">
                  <span
                    style={{
                      fontFamily: "'EB Garamond', serif",
                      fontSize: "1.75rem",
                      fontWeight: 700,
                      color: "var(--cr-blue)",
                      lineHeight: 1,
                    }}
                  >
                    {party.party_short}
                  </span>
                  <span
                    style={{
                      fontSize: "0.8rem",
                      color: "var(--cr-text-muted)",
                      fontWeight: 500,
                    }}
                    className="truncate"
                  >
                    {party.party_name}
                  </span>
                </div>

                {/* MP count */}
                <p
                  style={{
                    fontSize: "0.8rem",
                    color: "var(--cr-text-faint)",
                    marginBottom: "0.875rem",
                    textTransform: "uppercase",
                    letterSpacing: "0.04em",
                    fontWeight: 500,
                  }}
                >
                  {party.mp_count} {t.parties.mpCount}
                </p>

                {/* Participation bar */}
                <div className="mb-4">
                  <div
                    className="flex justify-between mb-1"
                    style={{ fontSize: "0.8rem" }}
                  >
                    <span style={{ color: "var(--cr-text-muted)" }}>
                      {t.parties.avgParticipation}
                    </span>
                    <span style={{ fontWeight: 600, color: "var(--cr-text)" }}>
                      {pct.toFixed(1)} %
                    </span>
                  </div>
                  <div className="stat-bar-track" style={{ height: "4px" }}>
                    <div
                      className="stat-bar-fill"
                      style={{ width: `${pct}%`, height: "4px" }}
                    />
                  </div>
                </div>

                {/* Activity totals */}
                <div
                  className="flex gap-4"
                  style={{ fontSize: "0.78rem", color: "var(--cr-text-muted)" }}
                >
                  <span>
                    <strong style={{ color: "var(--cr-text)" }}>
                      {party.total_bills}
                    </strong>{" "}
                    {t.parties.bills}
                  </span>
                  <span>
                    <strong style={{ color: "var(--cr-text)" }}>
                      {party.total_speeches}
                    </strong>{" "}
                    {t.parties.speeches}
                  </span>
                  <span>
                    <strong style={{ color: "var(--cr-text)" }}>
                      {party.total_interpellations}
                    </strong>{" "}
                    {t.parties.interpellations}
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
