export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getMpById } from "@/lib/queries";

function StatBar({
  label,
  value,
  max,
  unit,
}: {
  label: string;
  value: number;
  max: number;
  unit?: string;
}) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-sm mb-1">
        <span className="text-gray-600">{label}</span>
        <span className="font-medium">
          {value}
          {unit}
        </span>
      </div>
      <div className="w-full bg-gray-100 rounded-full h-2">
        <div
          className="bg-blue-500 h-2 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default async function MpProfilePage({
  params,
}: PageProps<"/[locale]/poslanec/[id]">) {
  const { locale, id } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);

  const mp = await getMpById(Number(id));
  if (!mp) notFound();

  const fullName = [mp.pred, mp.jmeno, mp.prijmeni, mp.za]
    .filter(Boolean)
    .join(" ");

  const photoUrl = mp.foto
    ? `https://www.psp.cz/eknih/cdrom/web/poslanci/${mp.id_poslanec}/foto.jpg`
    : null;

  const totalPresent = mp.votes_total > 0 ? mp.votes_total : 1;

  return (
    <div className="max-w-3xl">
      {/* Back */}
      <Link
        href={`/${locale}/poslanci`}
        className="text-sm text-blue-600 hover:text-blue-800 mb-6 inline-block"
      >
        ← {t.mps.title}
      </Link>

      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 flex items-start gap-5">
        <div className="w-24 h-24 rounded-xl bg-gray-100 overflow-hidden flex-shrink-0">
          {photoUrl ? (
            <Image
              src={photoUrl}
              alt={fullName}
              width={96}
              height={96}
              className="w-full h-full object-cover"
              unoptimized
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400 text-3xl">
              {mp.prijmeni[0]}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-gray-900">{fullName}</h1>
          {mp.party_name && (
            <p className="text-gray-500 mt-1">{mp.party_name}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-3">
            {typeof (mp as unknown as Record<string, unknown>).web === "string" && (
              <a
                href={String((mp as unknown as Record<string, unknown>).web)}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-blue-600 hover:underline"
              >
                Web
              </a>
            )}
            {typeof (mp as unknown as Record<string, unknown>).email === "string" && (
              <a
                href={`mailto:${(mp as unknown as Record<string, unknown>).email}`}
                className="text-sm text-blue-600 hover:underline"
              >
                Email
              </a>
            )}
            <a
              href={`https://www.psp.cz/sqw/detail.sqw?id=${mp.id_osoba}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 hover:underline"
            >
              psp.cz
            </a>
          </div>
        </div>
      </div>

      {/* Voting stats */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 className="font-semibold text-gray-900 mb-5">
          {t.mp.participation}
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          {(
            [
              [t.mp.votesTotal, mp.votes_total],
              [t.mp.votesPresent, mp.votes_present],
              [t.mp.votesAbsent, mp.votes_absent],
              [t.mp.votesExcused, mp.votes_excused],
            ] as [string, number][]
          ).map(([label, value]) => (
            <div key={label} className="text-center">
              <p className="text-2xl font-bold text-gray-900">
                {value.toLocaleString()}
              </p>
              <p className="text-xs text-gray-500 mt-1">{label}</p>
            </div>
          ))}
        </div>
        <StatBar
          label={t.mp.participation}
          value={mp.participation_pct}
          max={100}
          unit=" %"
        />
      </div>

      {/* Activity stats */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="font-semibold text-gray-900 mb-5">Aktivita</h2>
        <div className="space-y-4">
          <StatBar
            label={t.mp.billsAuthored}
            value={mp.bills_authored}
            max={Math.max(mp.bills_authored, 50)}
          />
          <StatBar
            label={t.mp.billsCosigned}
            value={mp.bills_cosigned}
            max={Math.max(mp.bills_cosigned, 50)}
          />
          <StatBar
            label={t.mp.speeches}
            value={mp.speeches_count}
            max={Math.max(mp.speeches_count, 100)}
          />
          <StatBar
            label={t.mp.interpellations}
            value={mp.interpellations_count}
            max={Math.max(mp.interpellations_count, 20)}
          />
        </div>
      </div>
    </div>
  );
}
