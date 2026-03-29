import { notFound } from "next/navigation";
import Link from "next/link";
import { hasLocale, getDictionary, LOCALES } from "@/lib/i18n";
import { getLastUpdated } from "@/lib/queries";

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
  const lastUpdated = await getLastUpdated();

  return (
    <html lang={locale}>
      <body style={{ background: "var(--cr-blue-wash)", minHeight: "100vh" }}>
        {/* Navigation */}
        <header
          style={{
            background: "var(--cr-blue)",
            borderBottom: "3px solid var(--cr-red)",
          }}
          className="sticky top-0 z-10"
        >
          <nav className="max-w-6xl mx-auto px-6 flex items-center gap-0"
            style={{ height: "3.75rem" }}>
            {/* Logo with tricolor stripe */}
            <Link
              href={`/${locale}`}
              className="flex items-center gap-3 mr-8 flex-shrink-0"
            >
              <div
                className="tricolor-bar-v flex-shrink-0 rounded-sm"
                style={{ width: "5px", height: "28px" }}
                aria-hidden="true"
              />
              <span
                style={{
                  fontFamily: "'EB Garamond', serif",
                  color: "white",
                  fontWeight: 700,
                  fontSize: "1.15rem",
                  letterSpacing: "0.01em",
                  lineHeight: 1,
                }}
              >
                {t.nav.title}
              </span>
            </Link>

            {/* Nav links */}
            <Link
              href={`/${locale}`}
              style={{ color: "rgba(255,255,255,0.75)" }}
              className="text-sm font-medium tracking-wider uppercase px-3 py-1 rounded transition-colors hover:text-white"
            >
              {t.nav.home}
            </Link>
            <Link
              href={`/${locale}/poslanci`}
              style={{ color: "rgba(255,255,255,0.75)" }}
              className="text-sm font-medium tracking-wider uppercase px-3 py-1 rounded transition-colors hover:text-white"
            >
              {t.nav.mps}
            </Link>
            <Link
              href={`/${locale}/strany`}
              style={{ color: "rgba(255,255,255,0.75)" }}
              className="text-sm font-medium tracking-wider uppercase px-3 py-1 rounded transition-colors hover:text-white"
            >
              {t.nav.parties}
            </Link>
            <Link
              href={`/${locale}/porovnani`}
              style={{ color: "rgba(255,255,255,0.75)" }}
              className="text-sm font-medium tracking-wider uppercase px-3 py-1 rounded transition-colors hover:text-white"
            >
              {t.nav.comparison}
            </Link>

            {/* Language switcher */}
            <div className="ml-auto flex items-center gap-2">
              {LOCALES.map((l) => (
                <Link
                  key={l}
                  href={`/${l}`}
                  style={
                    l === locale
                      ? { background: "var(--cr-red)", color: "white" }
                      : { color: "rgba(255,255,255,0.5)" }
                  }
                  className="text-xs px-3 py-1.5 rounded font-semibold uppercase tracking-widest transition-colors hover:text-white"
                >
                  {l.toUpperCase()}
                </Link>
              ))}
            </div>
          </nav>
        </header>

        {/* Page content */}
        <main className="max-w-6xl mx-auto px-6 py-10">{children}</main>

        {/* Footer */}
        <footer
          style={{ borderTop: "1px solid var(--cr-border)" }}
          className="mt-16 py-8"
        >
          <div className="max-w-6xl mx-auto px-6 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span
                style={{ color: "var(--cr-text-faint)", fontSize: "0.8rem" }}
                className="font-medium tracking-wide uppercase"
              >
                {t.nav.title}
              </span>
              <a
                href="https://www.psp.cz/sqw/hp.sqw?k=1300"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--cr-text-muted)", fontSize: "0.8rem" }}
                className="hover:underline"
              >
                {t.footer.dataSource} ↗
              </a>
              {lastUpdated && (
                <span style={{ color: "var(--cr-text-faint)", fontSize: "0.75rem" }}>
                  {t.footer.lastUpdated}{" "}
                  {new Date(lastUpdated).toLocaleDateString(locale === "cs" ? "cs-CZ" : "en-GB", {
                    day: "numeric",
                    month: "long",
                    year: "numeric",
                  })}
                </span>
              )}
            </div>
            <div className="flex items-center gap-4">
              <a
                href="https://github.com/honzapaces/prover-poslance"
                target="_blank"
                rel="noopener noreferrer"
                style={{ color: "var(--cr-text-muted)", fontSize: "0.8rem" }}
                className="hover:underline"
              >
                {t.footer.sourceCode} ↗
              </a>
              <div
                className="tricolor-bar rounded-sm"
                style={{ width: "36px", height: "4px" }}
                aria-hidden="true"
              />
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
