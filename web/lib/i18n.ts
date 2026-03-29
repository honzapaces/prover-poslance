import csMessages from "@/messages/cs.json";
import enMessages from "@/messages/en.json";

export const LOCALES = ["cs", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "cs";

const messages = { cs: csMessages, en: enMessages };

export function hasLocale(locale: string): locale is Locale {
  return LOCALES.includes(locale as Locale);
}

export function getDictionary(locale: Locale) {
  return messages[locale];
}
