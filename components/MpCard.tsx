import Image from "next/image";
import Link from "next/link";
import type { MpWithStats } from "@/lib/queries";
import type { getDictionary } from "@/lib/i18n";

interface Props {
  mp: Partial<MpWithStats> & {
    id_poslanec: number;
    id_osoba?: number;
    term_year?: number;
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
      className="cr-card flex flex-col gap-3 p-4 block"
      style={{
        textDecoration: "none",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Red top accent on hover — using a pseudo-element via inline div */}
      <div
        aria-hidden="true"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "3px",
          background: "var(--cr-red)",
          opacity: 0,
          transition: "opacity 0.18s ease",
        }}
        className="card-red-top"
      />

      {/* Header: photo + name */}
      <div className="flex items-start gap-3">
        <div
          style={{
            width: 52,
            height: 52,
            borderRadius: "4px",
            overflow: "hidden",
            flexShrink: 0,
            background: "var(--cr-blue-tint)",
            border: "1.5px solid var(--cr-border)",
          }}
        >
          {photoUrl ? (
            <Image
              src={photoUrl}
              alt={name}
              width={52}
              height={52}
              className="w-full h-full object-cover"
              unoptimized
            />
          ) : (
            <div
              className="w-full h-full flex items-center justify-center"
              style={{
                color: "var(--cr-blue)",
                fontFamily: "'EB Garamond', serif",
                fontWeight: 700,
                fontSize: "1.25rem",
              }}
            >
              {mp.prijmeni[0]}
            </div>
          )}
        </div>

        <div className="flex-1 min-w-0">
          <p
            className="truncate"
            style={{
              color: "var(--cr-text)",
              fontWeight: 600,
              fontSize: "0.9rem",
              lineHeight: 1.3,
            }}
          >
            {name}
          </p>
          {mp.party_short && (
            <span
              style={{
                display: "inline-block",
                marginTop: "0.25rem",
                padding: "0.1rem 0.5rem",
                background: "var(--cr-blue)",
                color: "white",
                fontSize: "0.65rem",
                fontWeight: 600,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                borderRadius: "2px",
              }}
            >
              {mp.party_short}
            </span>
          )}
        </div>
      </div>

      {/* Participation bar */}
      {pct !== null && (
        <div>
          <div
            className="flex items-center justify-between mb-1"
            style={{ fontSize: "0.72rem" }}
          >
            <span style={{ color: "var(--cr-text-muted)" }}>
              {t.mp.participation}
            </span>
            <span
              style={{ color: "var(--cr-text)", fontWeight: 600 }}
            >
              {pct.toFixed(1)} %
            </span>
          </div>
          <div className="stat-bar-track" style={{ height: "3px" }}>
            <div
              className="stat-bar-fill"
              style={{ width: `${Math.min(pct, 100)}%`, height: "3px" }}
            />
          </div>
        </div>
      )}
    </Link>
  );
}
