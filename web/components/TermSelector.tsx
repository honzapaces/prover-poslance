"use client";

import { useRouter } from "next/navigation";
import type { TermInfo } from "@/lib/queries";

export function TermSelector({
  terms,
  currentTermId,
}: {
  terms: TermInfo[];
  currentTermId: number;
}) {
  const router = useRouter();

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const value = e.target.value;
    document.cookie = `term_id=${value}; path=/; max-age=31536000; SameSite=Lax`;
    router.refresh();
  }

  return (
    <select
      value={currentTermId}
      onChange={handleChange}
      style={{
        background: "rgba(255,255,255,0.12)",
        color: "rgba(255,255,255,0.9)",
        border: "1px solid rgba(255,255,255,0.25)",
        borderRadius: "4px",
        padding: "0.25rem 0.5rem",
        fontSize: "0.78rem",
        fontWeight: 500,
        cursor: "pointer",
        appearance: "none",
        WebkitAppearance: "none",
        paddingRight: "1.5rem",
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='rgba(255,255,255,0.6)'/%3E%3C/svg%3E\")",
        backgroundRepeat: "no-repeat",
        backgroundPosition: "right 0.4rem center",
      }}
    >
      {terms.map((term) => (
        <option
          key={term.id_organ}
          value={term.id_organ}
          style={{ background: "var(--cr-blue)", color: "white" }}
        >
          {term.nazev_organu_cz}
        </option>
      ))}
    </select>
  );
}
