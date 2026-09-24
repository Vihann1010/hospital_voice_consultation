"use client";

/**
 * Tests advised, written on the Visit Pad itself.
 *
 * Signing the pad places the order, so what is written here is what the
 * laboratory and the radiology desk receive. A test picked from the catalogue
 * carries its code and becomes a real order; one typed as free text still
 * prints as advice, but nothing is sent to a department that could not act on
 * it — which is said on screen rather than left to be discovered.
 */
import { useEffect, useState } from "react";
import { Plus, Sparkles, Trash2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PadInvestigation } from "@/lib/types/pad";
import type { Investigation } from "@/lib/types/investigations";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function InvestigationSection({
  investigations,
  suggestions,
  editable,
  department,
  onChange,
}: {
  investigations: PadInvestigation[];
  suggestions: PadInvestigation[];
  editable: boolean;
  department?: string;
  onChange: (next: {
    investigations: PadInvestigation[];
    suggestions: PadInvestigation[];
  }) => void;
}) {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Investigation[]>([]);

  const set = (
    next: Partial<{ investigations: PadInvestigation[]; suggestions: PadInvestigation[] }>
  ) => onChange({ investigations, suggestions, ...next });

  useEffect(() => {
    if (query.trim().length < 2) {
      setMatches([]);
      return;
    }
    const timer = setTimeout(() => {
      staffApi
        .catalog({ q: query.trim(), department })
        .then((result) => setMatches(result.investigations.slice(0, 8)))
        .catch(() => setMatches([]));
    }, 200);
    return () => clearTimeout(timer);
  }, [query, department]);

  const add = (row: PadInvestigation) => {
    if (investigations.some((item) => item.name.toLowerCase() === row.name.toLowerCase())) return;
    set({
      investigations: [...investigations, row],
      suggestions: suggestions.filter((item) => item !== row),
    });
  };

  return (
    <div className="space-y-2">
      <ul className="space-y-1">
        {investigations.map((row, index) => (
          <li key={index} className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-sm text-ink">
                {row.name}
                {!row.code && (
                  <span className="ml-1.5 text-[11px] text-marigold-deep">
                    advice only — no order placed
                  </span>
                )}
              </p>
              {editable ? (
                <Input
                  className="mt-0.5 h-7 text-xs"
                  value={row.note ?? ""}
                  placeholder="Why, or what to look for"
                  aria-label={`Note for ${row.name}`}
                  onChange={(event) =>
                    set({
                      investigations: investigations.map((item, at) =>
                        at === index ? { ...item, note: event.target.value } : item
                      ),
                    })
                  }
                />
              ) : (
                row.note && <p className="text-xs text-ink-muted">{row.note}</p>
              )}
            </div>
            {editable && (
              <button
                type="button"
                aria-label={`Remove ${row.name}`}
                className="rounded p-1 text-ink-faint hover:text-clay"
                onClick={() =>
                  set({ investigations: investigations.filter((_, at) => at !== index) })
                }
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </li>
        ))}
      </ul>

      {investigations.length === 0 && !editable && (
        <p className="text-sm text-ink-faint">No investigations advised.</p>
      )}

      {editable && suggestions.length > 0 && (
        <div className="rounded-lg border border-dashed border-pine/40 bg-pine/5 p-2">
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="flex items-center gap-1 text-[11px] font-medium text-pine">
              <Sparkles className="h-3 w-3" />
              Suggested from the intake — tap to advise
            </p>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 text-[11px]"
              onClick={() =>
                set({ investigations: [...investigations, ...suggestions], suggestions: [] })
              }
            >
              Add all
            </Button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestions.map((row, index) => (
              <button
                key={index}
                type="button"
                className="rounded-full border border-pine/30 bg-white px-2.5 py-1 text-xs text-ink hover:border-pine hover:bg-mint"
                onClick={() => add(row)}
                title={row.note ?? undefined}
              >
                <Plus className="mr-1 inline h-3 w-3 text-pine" />
                {row.name}
              </button>
            ))}
          </div>
        </div>
      )}

      {editable && (
        <div className="relative">
          <Input
            className="h-8 text-sm"
            value={query}
            placeholder="Search a test to advise…"
            aria-label="Search investigations"
            onChange={(event) => setQuery(event.target.value)}
          />
          {matches.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-border bg-white shadow-lg">
              {matches.map((item) => (
                <li key={item.code}>
                  <button
                    type="button"
                    className="block w-full px-2.5 py-1.5 text-left text-xs hover:bg-mint"
                    onClick={() => {
                      add({ code: item.code, name: item.name });
                      setQuery("");
                      setMatches([]);
                    }}
                  >
                    <span className="font-medium text-ink">{item.name}</span>{" "}
                    <span className="text-ink-muted">{item.category}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
