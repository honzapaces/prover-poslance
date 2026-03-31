import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Prověř poslance",
  description: "Transparentní přehled práce poslanců Parlamentu ČR",
};

// Root layout is minimal — the [locale] layout provides html/body with the correct lang attribute.
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
