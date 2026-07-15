import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useAuth } from "../auth/AuthContext";
import { setDisplayLocale } from "../lib/format";
import { translate, type TranslationKey } from "./translations";
import type { Locale, TranslationParams } from "./types";

interface LocaleValue {
  locale: Locale;
  dateLocale: "en-US" | "ko-KR";
  t: (key: TranslationKey, params?: TranslationParams) => string;
}

const LocaleContext = createContext<LocaleValue | null>(null);

export function LocaleProvider({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const locale: Locale = auth.user?.locale === "KO" ? "KO" : "EN";
  const dateLocale = locale === "KO" ? "ko-KR" : "en-US";
  setDisplayLocale(dateLocale);

  useEffect(() => {
    document.documentElement.lang = locale === "KO" ? "ko" : "en";
  }, [locale]);

  const value = useMemo<LocaleValue>(() => ({
    locale,
    dateLocale,
    t: (key, params) => translate(locale, key, params),
  }), [dateLocale, locale]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n(): LocaleValue {
  const value = useContext(LocaleContext);
  if (!value) throw new Error("useI18n must be used inside LocaleProvider");
  return value;
}
