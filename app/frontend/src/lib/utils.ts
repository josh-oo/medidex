import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** The initials of a name for an avatar: of its first two words, or its first two letters. */
export function getInitials(name: string) {
  const names = name.split(" ")
  if (names.length >= 2) {
    return `${names[0][0]}${names[1][0]}`.toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}
