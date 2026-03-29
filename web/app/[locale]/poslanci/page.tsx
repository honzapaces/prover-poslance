export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getMpList } from "@/lib/queries";
import { MpListClient } from "./MpListClient";

export default async function PoslanciPage({ params }: PageProps<"/[locale]/poslanci">) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);
  const mps = await getMpList();

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
          {t.mps.title}
        </h1>
      </div>
      <MpListClient mps={mps} locale={locale} t={t} />
    </div>
  );
}
