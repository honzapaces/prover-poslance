export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getMpList, getMpById } from "@/lib/queries";
import { ComparisonClient } from "./ComparisonClient";

export default async function PorovnaniPage({
  params,
  searchParams,
}: PageProps<"/[locale]/porovnani"> & {
  searchParams: Promise<{ a?: string; b?: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);
  const cookieStore = await cookies();
  const termId = cookieStore.get("term_id")?.value ? Number(cookieStore.get("term_id")!.value) : null;

  const { a, b } = await searchParams;
  const [mps, mp1, mp2] = await Promise.all([
    getMpList(termId),
    a ? getMpById(Number(a)) : Promise.resolve(null),
    b ? getMpById(Number(b)) : Promise.resolve(null),
  ]);

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
          {t.comparison.title}
        </h1>
      </div>
      <ComparisonClient
        mps={mps}
        mp1={mp1}
        mp2={mp2}
        locale={locale}
        t={t}
        selectedA={a ?? ""}
        selectedB={b ?? ""}
      />
    </div>
  );
}
