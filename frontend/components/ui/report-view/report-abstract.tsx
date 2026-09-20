import styles from './Abstract.module.css';

interface AbstractProps {
  text: string | null;
}

export function Abstract({ text }: AbstractProps) {
  return (
    <div 
      className={`${styles.container} leading-relaxed text-gray-900`}
      dangerouslySetInnerHTML={{ __html: text ?? "" }} 
    />
  );
}