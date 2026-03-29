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
      <div
        className="flex justify-between mb-1.5"
        style={{ fontSize: "0.875rem" }}
      >
        <span style={{ color: "var(--cr-text-muted)" }}>{label}</span>
        <span style={{ fontWeight: 600, color: "var(--cr-text)" }}>
          {value}
          {unit}
        </span>
      </div>
      <div className="stat-bar-track" style={{ height: "4px" }}>
        <div
          className="stat-bar-fill"
          style={{ width: `${pct}%`, height: "4px" }}
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

  const photoUrl = mp.foto && mp.term_year && mp.id_osoba
    ? `https://www.psp.cz/eknih/cdrom/${mp.term_year}ps/eknih/${mp.term_year}ps/poslanci/i${mp.id_osoba}.jpg`
    : null;

  const totalPresent = mp.votes_total > 0 ? mp.votes_total : 1;

  return (
    <div style={{ maxWidth: "48rem" }}>
      {/* Back link */}
      <Link
        href={`/${locale}/poslanci`}
        style={{
          color: "var(--cr-blue)",
          fontSize: "0.875rem",
          textDecoration: "none",
          display: "inline-flex",
          alignItems: "center",
          gap: "0.25rem",
          marginBottom: "1.75rem",
        }}
        className="hover:underline"
      >
        ← {t.mps.title}
      </Link>

      {/* Profile hero */}
      <div
        style={{
          background: "var(--cr-blue)",
          borderRadius: "8px",
          padding: "2rem",
          marginBottom: "1.5rem",
          display: "flex",
          alignItems: "flex-start",
          gap: "1.75rem",
        }}
      >
        {/* Photo */}
        <div
          style={{
            width: 96,
            height: 96,
            borderRadius: "6px",
            overflow: "hidden",
            flexShrink: 0,
            background: "var(--cr-blue-mid)",
            border: "2px solid rgba(255,255,255,0.2)",
          }}
        >
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
            <div
              className="w-full h-full flex items-center justify-center"
              style={{
                color: "rgba(255,255,255,0.5)",
                fontFamily: "'EB Garamond', serif",
                fontWeight: 700,
                fontSize: "2.5rem",
              }}
            >
              {mp.prijmeni[0]}
            </div>
          )}
        </div>

        {/* Name, party, links */}
        <div className="flex-1 min-w-0">
          <h1
            style={{
              fontFamily: "'EB Garamond', serif",
              color: "white",
              fontWeight: 700,
              fontSize: "1.75rem",
              lineHeight: 1.2,
              marginBottom: "0.375rem",
            }}
          >
            {fullName}
          </h1>
          {mp.party_name && (
            <p
              style={{
                color: "rgba(255,255,255,0.7)",
                fontSize: "0.95rem",
                marginBottom: "0.875rem",
              }}
            >
              {mp.party_name}
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            {typeof (mp as unknown as Record<string, unknown>).web === "string" && (
              <a
                href={String((mp as unknown as Record<string, unknown>).web)}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "rgba(255,255,255,0.8)",
                  fontSize: "0.8rem",
                  textDecoration: "none",
                  background: "rgba(255,255,255,0.12)",
                  padding: "0.25rem 0.75rem",
                  borderRadius: "3px",
                  fontWeight: 500,
                }}
                className="hover:bg-white/20 transition-colors"
              >
                Web
              </a>
            )}
            {typeof (mp as unknown as Record<string, unknown>).email === "string" && (
              <a
                href={`mailto:${(mp as unknown as Record<string, unknown>).email}`}
                style={{
                  color: "rgba(255,255,255,0.8)",
                  fontSize: "0.8rem",
                  textDecoration: "none",
                  background: "rgba(255,255,255,0.12)",
                  padding: "0.25rem 0.75rem",
                  borderRadius: "3px",
                  fontWeight: 500,
                }}
                className="hover:bg-white/20 transition-colors"
              >
                Email
              </a>
            )}
            <a
              href={`https://www.psp.cz/sqw/detail.sqw?id=${mp.id_osoba}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: "rgba(255,255,255,0.8)",
                fontSize: "0.8rem",
                textDecoration: "none",
                background: "rgba(255,255,255,0.12)",
                padding: "0.25rem 0.75rem",
                borderRadius: "3px",
                fontWeight: 500,
              }}
              className="hover:bg-white/20 transition-colors"
            >
              psp.cz ↗
            </a>
          </div>
        </div>
      </div>

      {/* Voting stats */}
      <div
        className="cr-card p-6 mb-4"
      >
        <h2
          className="section-accent"
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--cr-text)",
            fontWeight: 700,
            fontSize: "1.2rem",
            marginBottom: "1.25rem",
          }}
        >
          {t.mp.participation}
        </h2>

        {/* Vote counts */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          {(
            [
              [t.mp.votesTotal, mp.votes_total],
              [t.mp.votesPresent, mp.votes_present],
              [t.mp.votesAbsent, mp.votes_absent],
              [t.mp.votesExcused, mp.votes_excused],
            ] as [string, number][]
          ).map(([label, value]) => (
            <div
              key={label}
              className="text-center"
              style={{
                padding: "1rem 0.5rem",
                background: "var(--cr-blue-wash)",
                borderRadius: "4px",
                border: "1px solid var(--cr-blue-tint)",
              }}
            >
              <p
                style={{
                  fontFamily: "'EB Garamond', serif",
                  fontSize: "2rem",
                  fontWeight: 700,
                  color: "var(--cr-text)",
                  lineHeight: 1,
                  marginBottom: "0.25rem",
                }}
              >
                {value.toLocaleString()}
              </p>
              <p
                style={{
                  color: "var(--cr-text-muted)",
                  fontSize: "0.7rem",
                  textTransform: "uppercase",
                  letterSpacing: "0.05em",
                  fontWeight: 500,
                }}
              >
                {label}
              </p>
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
      <div className="cr-card p-6">
        <h2
          className="section-accent"
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--cr-text)",
            fontWeight: 700,
            fontSize: "1.2rem",
            marginBottom: "1.25rem",
          }}
        >
          Aktivita
        </h2>
        <div className="space-y-5">
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
