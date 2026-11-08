import { useMemo } from 'react';
import { sanitizeHtml } from '@/lib/sanitize-html';
import styles from './Abstract.module.css';

interface AbstractProps {
  text: string | null;
}

export function Abstract({ text }: AbstractProps) {
  // An abstract is HTML from an uploaded bibliography or a register: rendered only after it is sanitized.
  const html = useMemo(() => sanitizeHtml(text ?? ""), [text]);
  return (
    <div
      className={`${styles.container} leading-relaxed text-gray-900`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
