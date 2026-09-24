import { ComparisonGroup } from "@/types/comparisons";

const createComparisonId = () => `comparison-${Math.random().toString(36).slice(2, 9)}`;

const normalizeSide = (items?: string[]) => {
  if (items && items.length > 0) {
    const cleaned = items.map((value) => value.trim()).filter(Boolean);
    if (cleaned.length > 0) {
      return cleaned;
    }
  }
  return [];
};

export const createComparisonGroup = (
  overrides?: Partial<Omit<ComparisonGroup, "id">>
): ComparisonGroup => ({
  id: createComparisonId(),
  a: normalizeSide(overrides?.a),
  b: normalizeSide(overrides?.b),
});

const serializeSide = (items: string[]) =>
  items
    .map((value) => value.trim())
    .filter(Boolean)
    .join(" + ");

export const formatComparisonGroups = (groups: ComparisonGroup[]): string => {
  const formatted = groups
    .map((group) => {
      const left = serializeSide(group.a);
      const right = serializeSide(group.b);
      if (left && right) {
        return `${left} vs ${right}`;
      }
      if (left) {
        return left;
      }
      if (right) {
        return right;
      }
      return "";
    })
    .filter(Boolean);

  return formatted.join("; ");
};

export const hasValidComparisonGroups = (groups: ComparisonGroup[]): boolean =>
  groups.some(
    (group) =>
      group.a.some((value) => value.trim().length > 0) &&
      group.b.some((value) => value.trim().length > 0)
  );
