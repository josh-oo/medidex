import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { BookOpen, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { matchValues, useTagCatalogs } from "@/hooks/use-tag-catalog";
import { searchStudies } from "@/lib/api/studiesApi";
import { colorClasses } from "@/lib/colors";
import { iconByName } from "@/lib/icons";
import type { StudyFilter } from "@/lib/study-filters";
import { cn } from "@/lib/utils";
import type { StudyDto, TagCategorySchemaDto } from "@/types/apiDTOs";

// Suggestions start with the second letter; studies (a request per pause in typing) with the third, as the
// search endpoint needs three.
const MIN_TAG_TEXT = 2;
const MIN_STUDY_TEXT = 3;
const TAGS_PER_CATEGORY = 3;
const MAX_TAGS = 8;
const MAX_STUDIES = 4;

type Suggestion =
  | { kind: "text"; text: string }
  | { kind: "tag"; category: TagCategorySchemaDto; value: string }
  | { kind: "study"; study: StudyDto };

interface StudySearchBarProps {
  /** The text searched last; the input follows it. */
  text: string;
  onSearch: (text: string) => void;
  /** A term of the vocabulary picked from the suggestions. */
  onAddFilter: (filter: StudyFilter) => void;
  /** Closes the search (the button at the end of the bar, or Escape). */
  onClear?: () => void;
  /** The ids of the databases searched; the suggestions only come from them (all of them if empty). */
  databases?: number[];
  /** Shown at the start of the bar, e.g. the choice of databases. */
  leading?: ReactNode;
  /** `hero` is the large bar of the start page. */
  size?: "hero" | "compact";
  autoFocus?: boolean;
}

const NO_DATABASES: number[] = [];

/** The search field with suggestions from the vocabulary of the tag categories and the names of studies. */
export function StudySearchBar({
  text,
  onSearch,
  onAddFilter,
  onClear,
  databases = NO_DATABASES,
  leading,
  size = "compact",
  autoFocus,
}: StudySearchBarProps) {
  const [value, setValue] = useState(text);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [studies, setStudies] = useState<StudyDto[]>([]);
  const [focused, setFocused] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const hero = size === "hero";

  // The vocabulary is loaded the first time the field is used.
  const catalogs = useTagCatalogs(focused, databases);
  const trimmed = value.trim();
  const debounced = useDebouncedValue(trimmed, 250);

  useEffect(() => setValue(text), [text]);

  useEffect(() => {
    if (!open || debounced.length < MIN_STUDY_TEXT) {
      setStudies([]);
      return;
    }
    let active = true;
    searchStudies({ q: debounced, limit: MAX_STUDIES, databases })
      .then((page) => active && setStudies(page.items))
      .catch(() => active && setStudies([]));
    return () => {
      active = false;
    };
  }, [debounced, open, databases]);

  const suggestions = useMemo<Suggestion[]>(() => {
    if (trimmed.length < MIN_TAG_TEXT) return [];
    const tags = catalogs
      .flatMap(({ category, values }) =>
        matchValues(values, trimmed, TAGS_PER_CATEGORY).map((tag) => ({ kind: "tag" as const, category, value: tag }))
      )
      .slice(0, MAX_TAGS);
    return [
      { kind: "text", text: trimmed },
      ...tags,
      ...studies.map((study) => ({ kind: "study" as const, study })),
    ];
  }, [catalogs, studies, trimmed]);

  const showList = open && suggestions.length > 1;

  const choose = (suggestion: Suggestion) => {
    setOpen(false);
    setActiveIndex(-1);
    if (suggestion.kind === "tag") {
      setValue("");
      onAddFilter({ field: suggestion.category.searchField, value: suggestion.value });
    } else if (suggestion.kind === "study") {
      onSearch(suggestion.study.shortName);
    } else {
      onSearch(suggestion.text);
    }
    inputRef.current?.blur();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && suggestions.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => (index + 1) % suggestions.length);
    } else if (event.key === "ArrowUp" && suggestions.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? suggestions.length - 1 : index - 1));
    } else if (event.key === "Escape") {
      // The first Escape closes the suggestions, the next one the search.
      if (showList) {
        setOpen(false);
        setActiveIndex(-1);
      } else {
        onClear?.();
      }
    } else if (event.key === "Enter") {
      event.preventDefault();
      const suggestion = showList && activeIndex >= 0 ? suggestions[activeIndex] : null;
      if (suggestion) choose(suggestion);
      else if (trimmed) choose({ kind: "text", text: trimmed });
    }
  };

  return (
    <div className="relative w-full">
      <div
        className={cn(
          "flex items-center gap-2 rounded-full border bg-card transition-[box-shadow,padding] duration-500 focus-within:ring-2 focus-within:ring-ring/40",
          hero ? "p-1.5 shadow-md" : "p-1 shadow-xs",
          // With a control at the start the bar is padded evenly on both ends.
          !leading && (hero ? "pl-4" : "pl-3.5")
        )}
      >
        {leading}
        <Search className={cn("h-4 w-4 shrink-0 text-muted-foreground", leading && "ml-1.5")} aria-hidden />
        <input
          ref={inputRef}
          type="text"
          role="combobox"
          aria-label="Search studies"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showList && activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
          value={value}
          autoFocus={autoFocus}
          onChange={(event) => {
            setValue(event.target.value);
            setOpen(true);
            setActiveIndex(-1);
          }}
          onFocus={() => {
            setFocused(true);
            setOpen(true);
          }}
          onBlur={() => setOpen(false)}
          onKeyDown={handleKeyDown}
          placeholder="Search by intervention, condition, trial ID, author…"
          className={cn(
            "min-w-0 flex-1 bg-transparent text-[15px] outline-none transition-[height] duration-500 placeholder:text-muted-foreground",
            hero ? "h-10" : "h-8"
          )}
        />
        {onClear && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            aria-label="Close the search"
            title="Close the search (Esc)"
            className="h-8 shrink-0 gap-1 rounded-full px-2.5 text-xs text-muted-foreground"
            onClick={() => {
              setValue("");
              onClear();
            }}
          >
            <X className="h-4 w-4" />
            <span className="hidden sm:inline">Close</span>
          </Button>
        )}
        <Button
          type="button"
          size={hero ? "default" : "sm"}
          className={cn("shrink-0 rounded-full transition-[height,padding] duration-500", hero && "h-10 px-5")}
          onClick={() => trimmed && choose({ kind: "text", text: trimmed })}
        >
          Search
        </Button>
      </div>

      {showList && (
        <ul
          id={listId}
          role="listbox"
          aria-label="Suggestions"
          className="absolute left-0 right-0 top-full z-30 mt-2 max-h-96 overflow-y-auto rounded-2xl border bg-popover p-1.5 text-left shadow-lg"
        >
          {suggestions.map((suggestion, index) => (
            <li
              key={suggestionKey(suggestion)}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              // Keeps the focus in the input, so the list does not close before the click.
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => choose(suggestion)}
              onMouseEnter={() => setActiveIndex(index)}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-sm",
                index === activeIndex && "bg-muted"
              )}
            >
              <SuggestionContent suggestion={suggestion} text={trimmed} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const suggestionKey = (suggestion: Suggestion) =>
  suggestion.kind === "tag"
    ? `tag-${suggestion.category.key}-${suggestion.value}`
    : suggestion.kind === "study"
      ? `study-${suggestion.study.studyId}`
      : "text";

function SuggestionContent({ suggestion, text }: { suggestion: Suggestion; text: string }) {
  if (suggestion.kind === "text") {
    return (
      <>
        <Search className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="truncate">
          Search for <span className="font-medium">&ldquo;{suggestion.text}&rdquo;</span>
        </span>
      </>
    );
  }
  if (suggestion.kind === "study") {
    return (
      <>
        <BookOpen className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate">
          <Highlight text={suggestion.study.shortName} terms={[text]} />
        </span>
        {suggestion.study.trialId && (
          <span className="shrink-0 font-mono text-xs text-muted-foreground">{suggestion.study.trialId}</span>
        )}
        <span className="shrink-0 text-xs text-muted-foreground">Study</span>
      </>
    );
  }
  const Icon = iconByName(suggestion.category.icon);
  const colors = colorClasses(suggestion.category.color);
  return (
    <>
      <span className={cn("grid h-6 w-6 shrink-0 place-items-center rounded-md", colors.bg)}>
        <Icon className={cn("h-3.5 w-3.5", colors.accent)} aria-hidden />
      </span>
      <span className="min-w-0 flex-1 truncate">
        <Highlight text={suggestion.value} terms={[text]} />
      </span>
      <span className="shrink-0 text-xs text-muted-foreground">{suggestion.category.label}</span>
    </>
  );
}

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** `text` with the occurrences of `terms` marked. */
export function Highlight({ text, terms }: { text: string; terms: string[] }) {
  const pattern = terms
    .map((term) => term.trim())
    .filter((term) => term.length >= 2)
    .map(escapeRegExp)
    .join("|");
  if (!pattern) return <>{text}</>;
  const parts = text.split(new RegExp(`(${pattern})`, "gi"));
  return (
    <>
      {parts.map((part, index) =>
        index % 2 === 1 ? (
          <mark key={index} className="rounded-sm bg-amber-100 px-0.5 font-medium text-inherit dark:bg-amber-500/25">
            {part}
          </mark>
        ) : (
          part
        )
      )}
    </>
  );
}
