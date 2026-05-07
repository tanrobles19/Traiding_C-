// Cell value formatters used by the AG Grid columns.

import type { ColumnDef } from "@/lib/tables";

// Display all timestamps in Costa Rica local time (UTC-6) — same
// convention the C++ trading system uses (see ../cpp_ultra_low_latency
// CLAUDE.md).
const DISPLAY_TIMEZONE = "America/Costa_Rica";

// Swedish locale renders "YYYY-MM-DD HH:MM:SS" naturally with a space
// separator, which is exactly what we want.
const dateTimeFormatter = new Intl.DateTimeFormat("sv-SE", {
  timeZone: DISPLAY_TIMEZONE,
  year:   "numeric",
  month:  "2-digit",
  day:    "2-digit",
  hour:   "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

// HH:MM:SS only, same locale + timezone as the full formatter.
const timeOnlyFormatter = new Intl.DateTimeFormat("sv-SE", {
  timeZone: DISPLAY_TIMEZONE,
  hour:   "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

// Build the calendar portion ("YYYY-MM-DD HH:MM:SS") by feeding only the
// integer-seconds part through Date(). This avoids the JS Date losing
// sub-millisecond precision when the source column is DECIMAL(20,7).
function formatCalendarSeconds(integerSeconds: number): string {
  return dateTimeFormatter.format(new Date(integerSeconds * 1000));
}

// Preserve every fractional digit the database returned. mysql2 returns
// DECIMAL columns as strings precisely so this precision survives — we
// must NOT round-trip through a JavaScript number.
function preserveFractional(str: string, minDigits = 3): string {
  const dot = str.indexOf(".");
  if (dot === -1) return "0".repeat(minDigits);
  const fractional = str.slice(dot + 1);
  return fractional.length >= minDigits
    ? fractional
    : fractional.padEnd(minDigits, "0");
}

// Source format: unix epoch SECONDS as a string or number, optionally
// with a fractional part of arbitrary length (1–9 digits typical).
// Used for both `datetime_double_seconds` (signals.timestamp) and
// `datetime_decimal_seconds` (orders.start_timestamp / end_timestamp).
export function formatTimestampSeconds(s: number | string | null | undefined): string {
  if (s === null || s === undefined || s === "") return "";
  const str = typeof s === "string" ? s : s.toString();
  if (!Number.isFinite(Number(str))) return "";

  const dot = str.indexOf(".");
  const integerSecondsStr = dot === -1 ? str : str.slice(0, dot);
  const integerSeconds = Number(integerSecondsStr);
  if (!Number.isFinite(integerSeconds)) return "";

  const calendar   = formatCalendarSeconds(integerSeconds);
  const fractional = preserveFractional(str, 3);
  return `${calendar}.${fractional}`;
}

// Source format: ISO 8601 string already in local time with an offset
// suffix, e.g. "2026-04-23T07:01:00.687668-06:00". The three helpers
// below read the same string but each returns a different slice. We
// never re-parse through Date() because that would round microseconds
// → milliseconds.

function stripTzAndT(v: string): string {
  // Drop "Z" or "±HH:MM" tz offset.
  return v.replace(/(Z|[+-]\d{2}:?\d{2})$/, "");
}

// Full timestamp: "2026-04-23 07:01:00.687668"
export function formatIsoLocalTimestamp(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  return stripTzAndT(String(v)).replace("T", " ");
}

// Date only: "2026-04-23"
export function formatIsoLocalDate(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const tIndex = String(v).indexOf("T");
  return tIndex === -1 ? String(v) : String(v).slice(0, tIndex);
}

// Time only: "07:01:00.687668"
export function formatIsoLocalTime(v: string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const stripped = stripTzAndT(String(v));
  const tIndex = stripped.indexOf("T");
  return tIndex === -1 ? stripped : stripped.slice(tIndex + 1);
}

// Source format: unix epoch MILLISECONDS as a number or numeric string.
// Less precision than the seconds variant — we only have ms resolution.
export function formatTimestampMs(ms: number | string | null | undefined): string {
  if (ms === null || ms === undefined || ms === "") return "";
  const n = typeof ms === "string" ? Number(ms) : ms;
  if (!Number.isFinite(n)) return "";
  const d = new Date(n);
  const fractional = String(d.getUTCMilliseconds()).padStart(3, "0");
  return `${dateTimeFormatter.format(d)}.${fractional}`;
}

// "HH:MM:SS.uuuuuu" — drops the date and shows microsecond precision.
// Two trades that happen in the same SIP millisecond can still be
// distinguished by their Local Time (captured at ns and stored as
// DOUBLE seconds, ~µs effective precision).

// Source: unix seconds with optional fraction (e.g. "1745678400.012345").
export function formatLocalTimeFromSeconds(s: number | string | null | undefined): string {
  if (s === null || s === undefined || s === "") return "";
  const str = typeof s === "string" ? s : s.toString();
  if (!Number.isFinite(Number(str))) return "";

  const dot = str.indexOf(".");
  const integerSecondsStr = dot === -1 ? str : str.slice(0, dot);
  const integerSeconds = Number(integerSecondsStr);
  if (!Number.isFinite(integerSeconds)) return "";

  const time = timeOnlyFormatter.format(new Date(integerSeconds * 1000));
  // 6 digits → microsecond precision (the limit DOUBLE seconds can carry
  // for a 10-digit unix epoch).
  const fractional = preserveFractional(str, 6).slice(0, 6);
  return `${time}.${fractional}`;
}

// Source: unix epoch ms (number or numeric string). The source data
// only has millisecond precision, so the last 3 digits are always 000 —
// we still render 6 digits so the column visually aligns with Local
// Time and so the operator sees the precision floor explicitly.
export function formatLocalTimeFromMs(ms: number | string | null | undefined): string {
  if (ms === null || ms === undefined || ms === "") return "";
  const n = typeof ms === "string" ? Number(ms) : ms;
  if (!Number.isFinite(n)) return "";
  const d = new Date(n);
  const millis = String(d.getUTCMilliseconds()).padStart(3, "0");
  return `${timeOnlyFormatter.format(d)}.${millis}000`;
}

// Source: DECIMAL(20,7) unix seconds string from MySQL — keeps every
// fractional digit the column carries (typically 7 → 100 ns precision).
// Used by the Orders page where sub-µs matters for the Duration column.
export function formatLocalTimeFromDecimalSeconds(s: number | string | null | undefined): string {
  if (s === null || s === undefined || s === "") return "";
  const str = typeof s === "string" ? s : s.toString();
  if (!Number.isFinite(Number(str))) return "";

  const dot = str.indexOf(".");
  const integerSecondsStr = dot === -1 ? str : str.slice(0, dot);
  const integerSeconds = Number(integerSecondsStr);
  if (!Number.isFinite(integerSeconds)) return "";

  const time = timeOnlyFormatter.format(new Date(integerSeconds * 1000));
  const fractional = preserveFractional(str, 3);
  return `${time}.${fractional}`;
}

export function formatDecimal(v: number | string | null | undefined, digits = 4): string {
  if (v === null || v === undefined || v === "") return "";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "";
  return n.toFixed(digits);
}

export function formatInteger(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "";
  return n.toLocaleString("en-US");
}

// Compact human-readable representation for large counts:
//   < 1,000           → as-is with locale separators ("834")
//   ≥ 1,000 < 1M      → "980K"   (rounded to nearest, no decimal)
//   ≥ 1M < 1B         → "1.5M" / "78M" (one decimal, trailing .0 stripped)
//   ≥ 1B              → "1.5B" / "78B" (one decimal, trailing .0 stripped)
// Used by Stocks / Low Float columns where exact ones-place precision
// adds noise without value.
function stripTrailingZero(s: string): string {
  return s.endsWith(".0") ? s.slice(0, -2) : s;
}

export function formatAbbreviatedNumber(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "";
  const n = typeof v === "string" ? Number(v) : v;
  if (!Number.isFinite(n)) return "";
  const abs = Math.abs(n);
  if (abs >= 1e9) return `${stripTrailingZero((n / 1e9).toFixed(1))}B`;
  if (abs >= 1e6) return `${stripTrailingZero((n / 1e6).toFixed(1))}M`;
  if (abs >= 1e3) return `${Math.round(n / 1e3).toLocaleString("en-US")}K`;
  return n.toLocaleString("en-US");
}

// Pick the right formatter for a given column type. Wraps the type
// formatter with `col.prefix` and `col.suffix` (when set) so they
// flow through to both the plain valueFormatter path AND any
// cellRenderer that reads `valueFormatted` (e.g. the highlightAbove
// renderer). Empty strings stay empty — affixes are not added to
// blank cells.
export function formatterFor(col: ColumnDef): (v: unknown) => string {
  const base = formatterForType(col);
  const prefix = col.prefix;
  const suffix = col.suffix;
  if (!prefix && !suffix) return base;
  return (v) => {
    const s = base(v);
    if (s === "") return "";
    return (prefix ?? "") + s + (suffix ?? "");
  };
}

function formatterForType(col: ColumnDef): (v: unknown) => string {
  switch (col.type) {
    case "datetime_ms":               return (v) => formatTimestampMs(v as number | string);
    case "datetime_double_seconds":   return (v) => formatTimestampSeconds(v as number | string);
    case "datetime_decimal_seconds":  return (v) => formatTimestampSeconds(v as number | string);
    case "local_time_ms":             return (v) => formatLocalTimeFromMs(v as number | string);
    case "local_time_double_seconds": return (v) => formatLocalTimeFromSeconds(v as number | string);
    case "local_time_decimal_seconds":return (v) => formatLocalTimeFromDecimalSeconds(v as number | string);
    case "iso_local_timestamp":       return (v) => formatIsoLocalTimestamp(v as string);
    case "iso_local_date":            return (v) => formatIsoLocalDate(v as string);
    case "iso_local_time":            return (v) => formatIsoLocalTime(v as string);
    case "decimal":                   return (v) => formatDecimal(v as number | string, col.decimals ?? 4);
    case "number":                    return (v) => formatInteger(v as number | string);
    case "number_abbreviated":        return (v) => formatAbbreviatedNumber(v as number | string);
    default:                          return (v) => (v == null ? "" : String(v));
  }
}
