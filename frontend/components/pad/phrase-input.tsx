"use client";

/**
 * The input that makes the pad fast: type two letters, pick a phrase.
 *
 * Suggestions come from the catalogue — phrases this hospital's staff have
 * actually signed before, most used first. Nobody curates it. It is the
 * single biggest reason the old system felt quick, and the reason a doctor
 * here types "B/L OA" once and never again.
 *
 * Keyboard-first, because the people using it are: arrows move, Enter adds,
 * Escape closes the list without also sending the page back — the global
 * shortcut handler listens for Escape on the window, so it is stopped here.
 */
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { CatalogueSuggestion } from "@/lib/types/pad";
import { cn } from "@/lib/utils";

export function PhraseInput({
  category,
  placeholder,
  existing,
  onAdd,
  disabled = false,
}: {
  /** Catalogue category. Without one, the input is plain free text. */
  category?: string | null;
  placeholder?: string | null;
  /** Items already on the section, which are not offered again. */
  existing: string[];
  onAdd: (phrase: string) => void;
  disabled?: boolean;
}) {
  const [value, setValue] = useState("");
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<CatalogueSuggestion[]>([]);
  const [highlight, setHighlight] = useState(-1);
  const requestRef = useRef(0);
  const listId = useId();

  // Debounced lookup. Every request is numbered so a slow reply for "kn"
  // cannot overwrite the faster reply for "knee" that arrived first.
  useEffect(() => {
    if (!category || !open) return;
    const ticket = ++requestRef.current;
    const timer = setTimeout(async () => {
      try {
        const found = await staffApi.padCatalogue(category, value.trim());
        if (ticket === requestRef.current) {
          setSuggestions(found);
          setHighlight(-1);
        }
      } catch {
        // Suggestions are a convenience. If they fail the doctor still types.
        if (ticket === requestRef.current) setSuggestions([]);
      }
    }, 160);
    return () => clearTimeout(timer);
  }, [category, open, value]);

  const taken = new Set(existing.map((item) => item.toLowerCase()));
  const offered = suggestions.filter((item) => !taken.has(item.text.toLowerCase()));

  const add = useCallback(
    (phrase: string) => {
      const clean = phrase.replace(/\s+/g, " ").trim();
      if (!clean) return;
      onAdd(clean);
      setValue("");
      setHighlight(-1);
    },
    [onAdd]
  );

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown" && offered.length) {
      event.preventDefault();
      setOpen(true);
      setHighlight((current) => (current + 1) % offered.length);
    } else if (event.key === "ArrowUp" && offered.length) {
      event.preventDefault();
      setHighlight((current) => (current <= 0 ? offered.length - 1 : current - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      add(highlight >= 0 && offered[highlight] ? offered[highlight].text : value);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      event.stopPropagation();
      event.nativeEvent.stopImmediatePropagation();
      setOpen(false);
    }
  }

  const showList = open && offered.length > 0;

  return (
    <div className="relative">
      <div className="flex items-center gap-1.5">
        <input
          type="text"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={highlight >= 0 ? `${listId}-${highlight}` : undefined}
          value={value}
          disabled={disabled}
          placeholder={placeholder ?? "Add"}
          onChange={(event) => {
            setValue(event.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          // Delay so a click on a suggestion lands before the list unmounts.
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKeyDown}
          className="h-8 w-full rounded-md border border-input bg-white px-2.5 text-sm text-ink placeholder:text-ink-faint focus-visible:border-pine focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/20 disabled:opacity-50"
        />
        <button
          type="button"
          disabled={disabled || !value.trim()}
          onClick={() => add(value)}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-input text-pine transition hover:bg-mint disabled:opacity-40"
          aria-label="Add"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>

      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-9 top-9 z-30 max-h-56 overflow-auto rounded-md border border-border bg-white py-1 shadow-card"
        >
          {offered.map((item, index) => (
            <li
              key={item.text}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === highlight}
              // mousedown, not click: it fires before the input's blur.
              onMouseDown={(event) => {
                event.preventDefault();
                add(item.text);
              }}
              onMouseEnter={() => setHighlight(index)}
              className={cn(
                "flex cursor-pointer items-center justify-between gap-3 px-2.5 py-1.5 text-sm text-ink",
                index === highlight && "bg-mint"
              )}
            >
              <span className="truncate">{item.text}</span>
              {item.use_count > 1 && (
                <span className="tabular shrink-0 text-[10px] text-ink-faint">
                  ×{item.use_count}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
