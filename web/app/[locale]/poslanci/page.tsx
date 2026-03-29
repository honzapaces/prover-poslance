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
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t.mps.title}</h1>
      </div>
      <MpListClient mps={mps} locale={locale} t={t} />
    </div>
  );
}
