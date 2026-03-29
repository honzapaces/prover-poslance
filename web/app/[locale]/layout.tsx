import { notFound } from "next/navigation";
import Link from "next/link";
import { hasLocale, getDictionary, LOCALES } from "@/lib/i18n";

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: LayoutProps<"/[locale]"> & { children: React.ReactNode }) {
  const { locale } = await params;
  if (!hasLocale(locale)) notFound();
  const t = getDictionary(locale);

  return (
    <html lang={locale}>
      <body className="min-h-screen bg-gray-50">
        <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
          <nav className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
            <Link
              href={`/${locale}`}
              className="font-semibold text-gray-900 text-sm"
            >
              {t.nav.title}
            </Link>
            <Link
              href={`/${locale}`}
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              {t.nav.home}
            </Link>
            <Link
              href={`/${locale}/poslanci`}
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              {t.nav.mps}
            </Link>
            <div className="ml-auto flex items-center gap-2">
              {LOCALES.map((l) => (
                <Link
                  key={l}
                  href={`/${l}`}
                  className={`text-xs px-2 py-1 rounded ${
                    l === locale
                      ? "bg-gray-900 text-white"
                      : "text-gray-500 hover:text-gray-900"
                  }`}
                >
                  {l.toUpperCase()}
                </Link>
              ))}
            </div>
          </nav>
        </header>
        <main className="max-w-6xl mx-auto px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
