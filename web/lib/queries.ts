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

/** Full MP list with stats for current term */
export async function getMpList(): Promise<MpWithStats[]> {
  return query<MpWithStats>(`
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
    LEFT JOIN (
      SELECT z.id_osoba, o.nazev_organu_cz, o.zkratka
      FROM zarazeni z
      JOIN organy o ON o.id_organ = z.id_of
      JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
      WHERE z.cl_funkce = 0 AND z.do_o IS NULL
    ) party ON party.id_osoba = p.id_osoba
    ORDER BY o.prijmeni, o.jmeno
  `);
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
    LEFT JOIN (
      SELECT z.id_osoba, o.nazev_organu_cz, o.zkratka
      FROM zarazeni z
      JOIN organy o ON o.id_organ = z.id_of
      JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
      WHERE z.cl_funkce = 0 AND z.do_o IS NULL
    ) party ON party.id_osoba = p.id_osoba
    WHERE p.id_poslanec = ?
  `,
    [id]
  );
  return rows[0] ?? null;
}

/** Last ETL run timestamp (ISO string or null) */
export async function getLastUpdated(): Promise<string | null> {
  const rows = await query<{ last_updated: string | null }>(
    `SELECT MAX(updated_at) AS last_updated FROM mp_stats`
  );
  return rows[0]?.last_updated ?? null;
}

/** Dashboard: top/bottom 5 per metric */
export async function getDashboardOutliers() {
  const [topParticipation, bottomParticipation, topBills, topSpeeches, topInterpellations] =
    await Promise.all([
      query<MpWithStats>(`
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.participation_pct
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        LEFT JOIN (
          SELECT z.id_osoba, o.zkratka
          FROM zarazeni z
          JOIN organy o ON o.id_organ = z.id_of
          JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
          WHERE z.cl_funkce = 0 AND z.do_o IS NULL
        ) party ON party.id_osoba = p.id_osoba
        WHERE s.votes_total > 0
        ORDER BY s.participation_pct DESC LIMIT 5
      `),
      query<MpWithStats>(`
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.participation_pct
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        LEFT JOIN (
          SELECT z.id_osoba, o.zkratka
          FROM zarazeni z
          JOIN organy o ON o.id_organ = z.id_of
          JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
          WHERE z.cl_funkce = 0 AND z.do_o IS NULL
        ) party ON party.id_osoba = p.id_osoba
        WHERE s.votes_total > 0
        ORDER BY s.participation_pct ASC LIMIT 5
      `),
      query<MpWithStats>(`
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.bills_authored
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        LEFT JOIN (
          SELECT z.id_osoba, o.zkratka
          FROM zarazeni z
          JOIN organy o ON o.id_organ = z.id_of
          JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
          WHERE z.cl_funkce = 0 AND z.do_o IS NULL
        ) party ON party.id_osoba = p.id_osoba
        ORDER BY s.bills_authored DESC LIMIT 5
      `),
      query<MpWithStats>(`
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.speeches_count
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        LEFT JOIN (
          SELECT z.id_osoba, o.zkratka
          FROM zarazeni z
          JOIN organy o ON o.id_organ = z.id_of
          JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
          WHERE z.cl_funkce = 0 AND z.do_o IS NULL
        ) party ON party.id_osoba = p.id_osoba
        ORDER BY s.speeches_count DESC LIMIT 5
      `),
      query<MpWithStats>(`
        SELECT p.id_poslanec, p.id_osoba, o.prijmeni, o.jmeno, p.foto,
               CAST(STRFTIME('%Y', org.od_organ) AS INTEGER) AS term_year,
               party.zkratka AS party_short,
               s.interpellations_count
        FROM mp_stats s
        JOIN poslanec p ON p.id_poslanec = s.id_poslanec
        JOIN osoby o ON o.id_osoba = p.id_osoba
        JOIN organy org ON org.id_organ = p.id_obdobi
        LEFT JOIN (
          SELECT z.id_osoba, o.zkratka
          FROM zarazeni z
          JOIN organy o ON o.id_organ = z.id_of
          JOIN typ_organu t ON t.id_typ_org = o.id_typ_organu AND t.nazev_typ_org_cz LIKE '%klub%'
          WHERE z.cl_funkce = 0 AND z.do_o IS NULL
        ) party ON party.id_osoba = p.id_osoba
        ORDER BY s.interpellations_count DESC LIMIT 5
      `),
    ]);

  return { topParticipation, bottomParticipation, topBills, topSpeeches, topInterpellations };
}
