"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { MonthlyAttendance } from "@/lib/queries";

function barColor(pct: number) {
  if (pct >= 80) return "var(--cr-blue)";
  if (pct >= 60) return "#C9882A";
  return "var(--cr-red)";
}

function formatMonth(month: string) {
  const [y, m] = month.split("-");
  return `${m}/${y.slice(2)}`;
}

export function AttendanceChart({
  data,
  label,
}: {
  data: MonthlyAttendance[];
  label: string;
}) {
  if (data.length === 0) return null;

  const formatted = data.map((d) => ({
    ...d,
    label: formatMonth(d.month),
  }));

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={formatted} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: "var(--cr-text-faint)" }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 10, fill: "var(--cr-text-faint)" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v) => `${v}%`}
        />
        <Tooltip
          formatter={(value) => [`${value} %`, label]}
          contentStyle={{
            fontSize: "0.75rem",
            border: "1px solid var(--cr-border)",
            borderRadius: "4px",
          }}
          cursor={{ fill: "var(--cr-blue-wash)" }}
        />
        <Bar dataKey="attendance_pct" radius={[2, 2, 0, 0]} maxBarSize={28}>
          {formatted.map((entry, i) => (
            <Cell key={i} fill={barColor(entry.attendance_pct)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
