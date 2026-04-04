export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getMpList } from "@/lib/queries";
import { WhoRepresentsMe } from "./WhoRepresentsMe";

export default async function MujKrajPage({ params }: PageProps<"/[locale]/muj-kraj">) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);
  const cookieStore = await cookies();
  const termId = cookieStore.get("term_id")?.value ? Number(cookieStore.get("term_id")!.value) : null;
  const mps = await getMpList(termId);

  return (
    <div style={{ maxWidth: "56rem" }}>
      <div className="mb-8 section-accent">
        <h1
          style={{
            fontFamily: "'EB Garamond', serif",
            color: "var(--cr-text)",
            fontWeight: 700,
            fontSize: "2rem",
            lineHeight: 1.2,
            marginBottom: "0.4rem",
          }}
        >
          {t.myRegion.title}
        </h1>
        <p style={{ color: "var(--cr-text-muted)", fontSize: "0.95rem" }}>
          {t.myRegion.subtitle}
        </p>
      </div>
      <WhoRepresentsMe mps={mps} locale={locale} t={t} />
    </div>
  );
}
