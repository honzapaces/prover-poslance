import { NextRequest, NextResponse } from "next/server";
import { regionNameFromNominatim } from "@/lib/kraj";

export async function GET(req: NextRequest) {
  const lat = req.nextUrl.searchParams.get("lat");
  const lon = req.nextUrl.searchParams.get("lon");

  if (!lat || !lon) {
    return NextResponse.json({ error: "Missing lat/lon" }, { status: 400 });
  }

  const url =
    `https://nominatim.openstreetmap.org/reverse` +
    `?format=json&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&addressdetails=1`;

  let data: { address?: Record<string, string> };
  try {
    const res = await fetch(url, {
      headers: { "User-Agent": "prover-poslance/1.0 (https://github.com/honzapaces/prover-poslance)" },
      next: { revalidate: 3600 },
    });
    if (!res.ok) throw new Error(`Nominatim ${res.status}`);
    data = await res.json();
  } catch (err) {
    return NextResponse.json({ error: String(err) }, { status: 502 });
  }

  const regionName = data.address ? regionNameFromNominatim(data.address) : null;
  return NextResponse.json({ regionName, address: data.address });
}
