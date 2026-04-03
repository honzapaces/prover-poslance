import { query } from "./db";

export interface MpStats {
  id_poslanec: number;
  id_osoba: number;
  term_id: number;
  votes_total: number;
  votes_present: number;
  votes_cast: number;
  votes_absent: number;
  votes_excused: number;
  participation_pct: number;
  bills_authored: number;
  bills_cosigned: number;
  speeches_count: number;
  interpellations_count: number;
}

export interface MpProfile {
  id_poslanec: number;
  id_osoba: number;
  prijmeni: string;
  jmeno: string;
  pred: string | null;
  za: string | null;
  foto: number;
  term_year: number;
  party_name: string | null;
  party_short: string | null;
}

export type MpWithStats = MpProfile & MpStats;

export interface TermInfo {
  id_organ: number;
  nazev_organu_cz: string;
  nazev_organu_en: string | null;
  term_year: number;
  term_end_year: number | null;
  term_number: number;
}

/** Available terms that have mp_stats data, newest first */
export async function getAvailableTerms(): Promise<TermInfo[]> {
  return query<TermInfo>(`
    SELECT
      o.id_organ,
      o.nazev_organu_cz,
      o.nazev_organu_en,
      CAST(STRFTIME('%Y', o.od_organ) AS INTEGER) AS term_year,
      CAST(STRFTIME('%Y', o.do_organ) AS INTEGER) AS term_end_year,
      ROW_NUMBER() OVER (ORDER BY o.id_organ ASC) AS term_number
    FROM organy o
    WHERE o.id_organ IN (SELECT DISTINCT term_id FROM mp_stats)
    ORDER BY o.id_organ DESC
  `);
}

/** Full MP list with stats for a given term (null = latest) */
export async function getMpList(termId?: number | null): Promise<MpWithStats[]> {
  const t = termId ?? null;
  return query<MpWithStats>(
    `
    SELECT
      p.id_poslanec, p.id_osoba, p.foto,
      CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
      o.prijmeni, o.jmeno, o.pred, o.za,
      party.nazev_organu_cz AS party_name,
      party.zkratka         AS party_short,
      s.votes_total, s.votes_present, s.votes_cast,
      s.votes_absent, s.votes_excused, s.participation_pct,
      s.bills_authored, s.bills_cosigned,
      s.speeches_count, s.interpellations_count,
      s.term_id
    FROM mp_stats s
    JOIN poslanec p  ON p.id_poslanec = s.id_poslanec
    JOIN osoby   o  ON o.id_osoba     = p.id_osoba
    JOIN organy  org ON org.id_organ  = p.id_obdobi
    JOIN (
      SELECT z.id_osoba, o2.nazev_organu_cz, o2.zkratka
      FROM zarazeni z
      JOIN organy o2 ON o2.id_organ = z.id_of
      JOIN typ_organu t ON t.id_typ_org = o2.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
      JOIN organy term_ref ON term_ref.id_organ = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
      WHERE z.cl_funkce = 0
        AND z.od_o <= COALESCE(term_ref.do_organ, '9999-12-31')
        AND (z.do_o IS NULL OR z.do_o >= COALESCE(term_ref.do_organ, '9999-12-31'))
      GROUP BY z.id_osoba
    ) party ON party.id_osoba = p.id_osoba
    WHERE s.term_id = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
    ORDER BY o.prijmeni, o.jmeno
    `,
    [t, t]
  );
}

/** Single MP with stats */
export async function getMpById(id: number): Promise<MpWithStats | null> {
  const rows = await query<MpWithStats>(
    `
    SELECT
      p.id_poslanec, p.id_osoba, p.foto,
      CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
      p.web, p.email, p.telefon, p.obec, p.ulice, p.psc,
      o.prijmeni, o.jmeno, o.pred, o.za, o.narozeni,
      (
        SELECT o2.nazev_organu_cz
        FROM zarazeni z2
        JOIN organy o2 ON o2.id_organ = z2.id_of
        JOIN typ_organu t2 ON t2.id_typ_org = o2.id_typ_organu AND t2.nazev_typ_org_cz LIKE '%klub%'
        WHERE z2.id_osoba = p.id_osoba AND z2.cl_funkce = 0
          AND z2.od_o <= COALESCE(org.do_organ, '9999-12-31')
          AND (z2.do_o IS NULL OR z2.do_o >= COALESCE(org.do_organ, '9999-12-31'))
        LIMIT 1
      ) AS party_name,
      (
        SELECT o2.zkratka
        FROM zarazeni z2
        JOIN organy o2 ON o2.id_organ = z2.id_of
        JOIN typ_organu t2 ON t2.id_typ_org = o2.id_typ_organu AND t2.nazev_typ_org_cz LIKE '%klub%'
        WHERE z2.id_osoba = p.id_osoba AND z2.cl_funkce = 0
          AND z2.od_o <= COALESCE(org.do_organ, '9999-12-31')
          AND (z2.do_o IS NULL OR z2.do_o >= COALESCE(org.do_organ, '9999-12-31'))
        LIMIT 1
      ) AS party_short,
      s.votes_total, s.votes_present, s.votes_cast,
      s.votes_absent, s.votes_excused, s.participation_pct,
      s.bills_authored, s.bills_cosigned,
      s.speeches_count, s.interpellations_count,
      s.term_id
    FROM mp_stats s
    JOIN poslanec p  ON p.id_poslanec = s.id_poslanec
    JOIN osoby   o  ON o.id_osoba     = p.id_osoba
    JOIN organy  org ON org.id_organ  = p.id_obdobi
    WHERE p.id_poslanec = ?
  `,
    [id]
  );
  return rows[0] ?? null;
}

export interface PartyStats {
  id_organ: number;
  party_short: string;
  party_name: string;
  mp_count: number;
  avg_participation: number;
  total_bills: number;
  total_speeches: number;
  total_interpellations: number;
}

export interface MonthlyAttendance {
  month: string; // "YYYY-MM"
  votes_total: number;
  votes_present: number;
  attendance_pct: number;
}

/** Party aggregate stats for a given term (null = latest) */
export async function getPartyList(termId?: number | null): Promise<PartyStats[]> {
  const t = termId ?? null;
  return query<PartyStats>(
    `
    SELECT
      o.id_organ,
      o.zkratka                                    AS party_short,
      o.nazev_organu_cz                            AS party_name,
      COUNT(DISTINCT p.id_poslanec)                AS mp_count,
      ROUND(AVG(s.participation_pct), 1)           AS avg_participation,
      SUM(s.bills_authored)                        AS total_bills,
      SUM(s.speeches_count)                        AS total_speeches,
      SUM(s.interpellations_count)                 AS total_interpellations
    FROM organy o
    JOIN typ_organu t  ON t.id_typ_org   = o.id_typ_organu
                      AND t.nazev_typ_org_cz LIKE '%klub%'
    JOIN organy term_ref ON term_ref.id_organ = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
    JOIN zarazeni z    ON z.id_of        = o.id_organ
                      AND z.cl_funkce    = 0
                      AND z.od_o <= COALESCE(term_ref.do_organ, '9999-12-31')
                      AND (z.do_o IS NULL OR z.do_o >= COALESCE(term_ref.do_organ, '9999-12-31'))
    JOIN poslanec p    ON p.id_osoba     = z.id_osoba
    JOIN mp_stats s    ON s.id_poslanec  = p.id_poslanec
                      AND s.term_id      = term_ref.id_organ
    GROUP BY o.id_organ, o.zkratka, o.nazev_organu_cz
    ORDER BY avg_participation DESC
    `,
    [t]
  );
}

/** Monthly attendance for a single MP (current term: 2021–2026) */
export async function getMpAttendanceByMonth(id: number): Promise<MonthlyAttendance[]> {
  return query<MonthlyAttendance>(
    `
    SELECT
      SUBSTR(hh.datum, 1, 7)                                                        AS month,
      COUNT(*)                                                                       AS votes_total,
      SUM(CASE WHEN hp.vysledek IN ('A','B','N','C','F','K') THEN 1 ELSE 0 END)    AS votes_present,
      ROUND(
        100.0 * SUM(CASE WHEN hp.vysledek IN ('A','B','N','C','F','K') THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0), 1
      )                                                                              AS attendance_pct
    FROM hl_poslanec hp
    JOIN (
      SELECT id_hlasovani, datum FROM hl2021s
      UNION ALL SELECT id_hlasovani, datum FROM hl2022s
      UNION ALL SELECT id_hlasovani, datum FROM hl2023s
      UNION ALL SELECT id_hlasovani, datum FROM hl2024s
      UNION ALL SELECT id_hlasovani, datum FROM hl2025s
      UNION ALL SELECT id_hlasovani, datum FROM hl2026s
    ) hh ON hh.id_hlasovani = hp.id_hlasovani
    WHERE hp.id_poslanec = ?
      AND hh.datum IS NOT NULL
    GROUP BY SUBSTR(hh.datum, 1, 7)
    ORDER BY month ASC
    `,
    [id]
  );
}

/** Last ETL run timestamp (ISO string or null) */
export async function getLastUpdated(): Promise<string | null> {
  const rows = await query<{ last_updated: string | null }>(
    `SELECT MAX(updated_at) AS last_updated FROM mp_stats`
  );
  return rows[0]?.last_updated ?? null;
}

/** Dashboard: top/bottom 5 per metric for a given term (null = latest) */
export async function getDashboardOutliers(termId?: number | null) {
  const t = termId ?? null;

  // party subquery always takes one ? binding (the term_ref coalesce)
  const partySql = `
    SELECT z.id_osoba, o2.zkratka
    FROM zarazeni z
    JOIN organy o2 ON o2.id_organ = z.id_of
    JOIN typ_organu t2 ON t2.id_typ_org = o2.id_typ_organu AND t2.nazev_typ_org_cz LIKE '%klub%'
    JOIN organy term_ref ON term_ref.id_organ = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
    WHERE z.cl_funkce = 0
      AND z.od_o <= COALESCE(term_ref.do_organ, '9999-12-31')
      AND (z.do_o IS NULL OR z.do_o >= COALESCE(term_ref.do_organ, '9999-12-31'))
    GROUP BY z.id_osoba
  `;

  // args: [party_term, where_term]
  const args = [t, t];

  const [topParticipation, bottomParticipation, topBills, topSpeeches, topInterpellations] =
    await Promise.all([
      query<MpWithStats>(
        `
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.participation_pct
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        JOIN (${partySql}) party ON party.id_osoba = p.id_osoba
        WHERE s.votes_total > 0
          AND s.term_id = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
        ORDER BY s.participation_pct DESC LIMIT 5
        `,
        args
      ),
      query<MpWithStats>(
        `
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.participation_pct
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        JOIN (${partySql}) party ON party.id_osoba = p.id_osoba
        WHERE s.votes_total > 0
          AND s.term_id = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
        ORDER BY s.participation_pct ASC LIMIT 5
        `,
        args
      ),
      query<MpWithStats>(
        `
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.bills_authored
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        JOIN (${partySql}) party ON party.id_osoba = p.id_osoba
        WHERE s.term_id = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
        ORDER BY s.bills_authored DESC LIMIT 5
        `,
        args
      ),
      query<MpWithStats>(
        `
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.speeches_count
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        JOIN (${partySql}) party ON party.id_osoba = p.id_osoba
        WHERE s.term_id = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
        ORDER BY s.speeches_count DESC LIMIT 5
        `,
        args
      ),
      query<MpWithStats>(
        `
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.interpellations_count
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        JOIN (${partySql}) party ON party.id_osoba = p.id_osoba
        WHERE s.term_id = COALESCE(?, (SELECT MAX(term_id) FROM mp_stats))
        ORDER BY s.interpellations_count DESC LIMIT 5
        `,
        args
      ),
    ]);

  return { topParticipation, bottomParticipation, topBills, topSpeeches, topInterpellations };
}
