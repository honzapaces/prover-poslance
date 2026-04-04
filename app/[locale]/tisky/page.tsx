export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import { hasLocale, getDictionary } from "@/lib/i18n";
import { getBillsList } from "@/lib/queries";
import { BillsListClient } from "./BillsListClient";

export default async function TiskyPage({ params }: PageProps<"/[locale]/tisky">) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);
  const cookieStore = await cookies();
  const termId = cookieStore.get("term_id")?.value ? Number(cookieStore.get("term_id")!.value) : null;
  const bills = await getBillsList(termId);

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
          {t.bills.title}
        </h1>
      </div>
      <BillsListClient bills={bills} locale={locale} t={t} />
    </div>
  );
}
