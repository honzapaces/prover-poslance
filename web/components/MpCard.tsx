import Image from "next/image";
import Link from "next/link";
import type { MpWithStats } from "@/lib/queries";
import type { getDictionary } from "@/lib/i18n";

interface Props {
  mp: Partial<MpWithStats> & {
    id_poslanec: number;
    prijmeni: string;
    jmeno: string;
    foto: number;
    party_short?: string | null;
  };
  locale: string;
  t: ReturnType<typeof getDictionary>;
}

export function MpCard({ mp, locale, t }: Props) {
  const name = `${mp.prijmeni} ${mp.jmeno}`;
  const photoUrl = mp.foto && mp.term_year && mp.id_osoba
    ? `https://www.psp.cz/eknih/cdrom/${mp.term_year}ps/eknih/${mp.term_year}ps/poslanci/i${mp.id_osoba}.jpg`
    : null;
  const pct = (mp as MpWithStats).participation_pct ?? null;

  return (
    <Link
      href={`/${locale}/poslanec/${mp.id_poslanec}`}
      className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col gap-3 hover:shadow-md transition-shadow"
    >
      <div className="flex items-start gap-3">
        <div className="w-14 h-14 rounded-full bg-gray-100 overflow-hidden flex-shrink-0">
          {photoUrl ? (
            <Image
              src={photoUrl}
              alt={name}
              width={56}
              height={56}
              className="w-full h-full object-cover"
              unoptimized
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-400 text-xl">
              {mp.prijmeni[0]}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-medium text-gray-900 text-sm truncate">{name}</p>
          {mp.party_short && (
            <span className="inline-block mt-1 px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full">
              {mp.party_short}
            </span>
          )}
        </div>
      </div>
      {pct !== null && (
        <div>
          <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
            <span>{t.mp.participation}</span>
            <span className="font-medium text-gray-900">{pct.toFixed(1)} %</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-1.5">
            <div
              className="bg-blue-500 h-1.5 rounded-full"
              style={{ width: `${Math.min(pct, 100)}%` }}
            />
          </div>
        </div>
      )}
    </Link>
  );
}
