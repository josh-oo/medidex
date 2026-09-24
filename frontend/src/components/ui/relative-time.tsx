"use client"

import { useEffect, useState } from "react";
import { formatDistance } from "date-fns";

interface RelativeTimeProps {
  date: string;
  updateIntervalMs?: number;
}

function parseDate(date: string): Date {
  // Treat timezone-less timestamps as UTC so server and client parse identically.
  const hasTimezone = /(?:[zZ]|[+-]\d{2}:\d{2})$/.test(date);
  const normalized = hasTimezone ? date : `${date}Z`;
  return new Date(normalized);
}

export default function RelativeTime({ date, updateIntervalMs = 60000 }: RelativeTimeProps) {
  const [now, setNow] = useState<number | null>(null);
  const dateObj = parseDate(date);
  const isValidDate = !Number.isNaN(dateObj.getTime());
  const isoDate = isValidDate ? dateObj.toISOString() : date;

  useEffect(() => {
    setNow(Date.now());
    const interval = setInterval(() => {
      setNow(Date.now());
    }, updateIntervalMs);
    return () => clearInterval(interval);
  }, [updateIntervalMs]);

  // Keep the initial SSR/CSR markup deterministic to avoid hydration mismatches.
  if (now === null) {
    return <time dateTime={isoDate}>{isoDate.slice(0, 10)}</time>;
  }

  if (!isValidDate) {
    return <time dateTime={isoDate}>{isoDate.slice(0, 10)}</time>;
  }

  return <time dateTime={isoDate}>{formatDistance(dateObj, now, { addSuffix: true })}</time>;
}
