import { useEffect, useState } from 'react';

export const asArray = (v) => (Array.isArray(v) ? v : []);

export const dateLabel = (v) =>
  new Date(v).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

export const timeLabel = (v) =>
  v ? new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';

const DAY = 864e5;

/** Groups conversations into Today / Yesterday / Previous 7 days / Older. */
export function groupByDate(items) {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  const today = start.getTime();
  const groups = [
    ['Today', []],
    ['Yesterday', []],
    ['Previous 7 days', []],
    ['Older', []],
  ];
  for (const c of items) {
    const t = new Date(c.created_at).getTime();
    const i = t >= today ? 0 : t >= today - DAY ? 1 : t >= today - 7 * DAY ? 2 : 3;
    groups[i][1].push(c);
  }
  return groups.filter(([, list]) => list.length);
}

export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    onChange();
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, [query]);
  return matches;
}

export function readFlag(key) {
  try { return localStorage.getItem(key) === '1'; } catch { return false; }
}
export function writeFlag(key, on) {
  try { localStorage.setItem(key, on ? '1' : '0'); } catch { /* storage unavailable */ }
}