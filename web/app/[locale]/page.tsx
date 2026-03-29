export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
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
  metricLabel,
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
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h3 className="font-semibold text-gray-900 mb-4 text-sm">{title}</h3>
      <ol className="space-y-3">
        {rows.map((r, i) => {
          const val = r[metricKey] as number;
          const display = format ? format(val) : String(val);
          const photoUrl = r.foto && r.term_year && r.id_osoba
            ? `https://www.psp.cz/eknih/cdrom/${r.term_year}ps/eknih/${r.term_year}ps/poslanci/i${r.id_osoba}.jpg`
            : null;
          return (
            <li key={r.id_poslanec} className="flex items-center gap-3">
              <span className="text-xs text-gray-400 w-4">{i + 1}</span>
              <div className="w-8 h-8 rounded-full bg-gray-100 overflow-hidden flex-shrink-0">
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
                  <div className="w-full h-full flex items-center justify-center text-gray-400 text-xs">
                    {r.prijmeni[0]}
                  </div>
                )}
              </div>
              <Link
                href={`/${locale}/poslanec/${r.id_poslanec}`}
                className="flex-1 min-w-0"
              >
                <p className="text-sm text-gray-900 hover:text-blue-600 truncate">
                  {r.prijmeni} {r.jmeno}
                </p>
                {r.party_short && (
                  <p className="text-xs text-gray-400">{r.party_short}</p>
                )}
              </Link>
              <span className="text-sm font-medium text-gray-900 shrink-0">
                {display}
              </span>
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
  const data = await getDashboardOutliers();

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">{t.home.title}</h1>
        <p className="mt-1 text-gray-500 text-sm">{t.home.subtitle}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
