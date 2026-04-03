export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { cookies } from "next/headers";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getDashboardOutliers } from "@/lib/queries";

interface OutlierRow {
  id_poslanec: number;
  id_osoba: number;
  term_year: number;
  prijmeni: string;
  jmeno: string;
  foto: number;
  party_short?: string | null;
  participation_pct?: number;
  bills_authored?: number;
  speeches_count?: number;
  interpellations_count?: number;
}

function OutlierList({
  title,
  rows,
  metricKey,
  locale,
  format,
}: {
  title: string;
  rows: OutlierRow[];
  metricKey: keyof OutlierRow;
  metricLabel: string;
  locale: string;
  format?: (v: number) => string;
}) {
  return (
    <div
      className="cr-card flex flex-col"
      style={{ overflow: "hidden" }}
    >
      {/* Card header */}
      <div
        style={{
          background: "var(--cr-blue)",
          padding: "0.875rem 1.25rem",
        }}
      >
        <h3
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "white",
            fontWeight: 600,
            fontSize: "1rem",
            letterSpacing: "0.01em",
          }}
        >
          {title}
        </h3>
      </div>

      {/* Rows */}
      <ol className="flex flex-col" style={{ padding: "0.5rem 0" }}>
        {rows.map((r, i) => {
          const val = r[metricKey] as number;
          const display = format ? format(val) : String(val);
          const photoUrl = r.foto && r.term_year && r.id_osoba
            ? `https://www.psp.cz/eknih/cdrom/${r.term_year}ps/eknih/${r.term_year}ps/poslanci/i${r.id_osoba}.jpg`
            : null;

          return (
            <li
              key={r.id_poslanec}
              style={{
                borderBottom: i < rows.length - 1 ? "1px solid var(--cr-blue-tint)" : "none",
              }}
            >
              <Link
                href={`/${locale}/poslanec/${r.id_poslanec}`}
                className="outlier-row flex items-center gap-3 px-4 py-2.5 transition-colors"
                style={{ textDecoration: "none" }}
              >
                {/* Rank */}
                <span
                  style={{
                    color: i === 0 ? "var(--cr-red)" : "var(--cr-text-faint)",
                    fontWeight: i === 0 ? 700 : 400,
                    fontSize: "0.8rem",
                    width: "1rem",
                    flexShrink: 0,
                    fontFamily: "'EB Garamond', serif",
                  }}
                >
                  {i + 1}
                </span>

                {/* Photo */}
                <div
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    overflow: "hidden",
                    flexShrink: 0,
                    background: "var(--cr-blue-tint)",
                    border: "1.5px solid var(--cr-border)",
                  }}
                >
                  {photoUrl ? (
                    <Image
                      src={photoUrl}
                      alt={`${r.prijmeni} ${r.jmeno}`}
                      width={32}
                      height={32}
                      className="w-full h-full object-cover"
                      unoptimized
                    />
                  ) : (
                    <div
                      className="w-full h-full flex items-center justify-center"
                      style={{
                        color: "var(--cr-text-muted)",
                        fontSize: "0.7rem",
                        fontWeight: 600,
                      }}
                    >
                      {r.prijmeni[0]}
                    </div>
                  )}
                </div>

                {/* Name + party */}
                <div className="flex-1 min-w-0">
                  <p
                    className="truncate"
                    style={{
                      color: "var(--cr-text)",
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      lineHeight: 1.3,
                    }}
                  >
                    {r.prijmeni} {r.jmeno}
                  </p>
                  {r.party_short && (
                    <p
                      style={{
                        color: "var(--cr-text-muted)",
                        fontSize: "0.7rem",
                        letterSpacing: "0.03em",
                      }}
                    >
                      {r.party_short}
                    </p>
                  )}
                </div>

                {/* Metric */}
                <span
                  style={{
                    color: "var(--cr-red)",
                    fontWeight: 700,
                    fontSize: "0.875rem",
                    flexShrink: 0,
                    fontFamily: "'EB Garamond', serif",
                  }}
                >
                  {display}
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default async function DashboardPage({
  params,
}: PageProps<"/[locale]">) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);
  const cookieStore = await cookies();
  const termId = cookieStore.get("term_id")?.value ? Number(cookieStore.get("term_id")!.value) : null;
  const data = await getDashboardOutliers(termId);

  return (
    <div>
      {/* Page header */}
      <div className="mb-10">
        <div className="section-accent">
          <h1
            style={{
              fontFamily: "'EB Garamond', serif",
              color: "var(--cr-text)",
              fontWeight: 700,
              fontSize: "2rem",
              lineHeight: 1.2,
            }}
          >
            {t.home.title}
          </h1>
        </div>
        <p
          style={{
            color: "var(--cr-text-muted)",
            marginTop: "0.5rem",
            fontSize: "0.95rem",
          }}
        >
          {t.home.subtitle}
        </p>
      </div>

      {/* Outlier grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        <OutlierList
          title={t.stats.topParticipation}
          rows={data.topParticipation as OutlierRow[]}
          metricKey="participation_pct"
          metricLabel={t.mp.participation}
          locale={locale}
          format={(v) => `${v.toFixed(1)} %`}
        />
        <OutlierList
          title={t.stats.bottomParticipation}
          rows={data.bottomParticipation as OutlierRow[]}
          metricKey="participation_pct"
          metricLabel={t.mp.participation}
          locale={locale}
          format={(v) => `${v.toFixed(1)} %`}
        />
        <OutlierList
          title={t.stats.topBills}
          rows={data.topBills as OutlierRow[]}
          metricKey="bills_authored"
          metricLabel={t.mp.billsAuthored}
          locale={locale}
        />
        <OutlierList
          title={t.stats.topSpeeches}
          rows={data.topSpeeches as OutlierRow[]}
          metricKey="speeches_count"
          metricLabel={t.mp.speeches}
          locale={locale}
        />
        <OutlierList
          title={t.stats.topInterpellations}
          rows={data.topInterpellations as OutlierRow[]}
          metricKey="interpellations_count"
          metricLabel={t.mp.interpellations}
          locale={locale}
        />
      </div>
    </div>
  );
}
