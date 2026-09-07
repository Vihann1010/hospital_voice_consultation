"use client";

/**
 * Investigation picker: search, categories, favourites, recently used,
 * templates and common panels, with multi-select and request generation.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Clock, FlaskConical, Layers, Loader2, Search, Star, Trash2, X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type {
  Catalog, Investigation, InvestigationPriority, Panel, Workspace,
} from "@/lib/investigationTypes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type Tab = "all" | "favorites" | "recent" | "templates" | "panels";

const TABS: { key: Tab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: "all", label: "All", icon: Search },
  { key: "favorites", label: "Favourites", icon: Star },
  { key: "recent", label: "Recent", icon: Clock },
  { key: "templates", label: "Templates", icon: Layers },
  { key: "panels", label: "Panels", icon: FlaskConical },
];

export function InvestigationPicker({
  open,
  onOpenChange,
  patientId,
  consultationId,
  onOrdered,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
  patientId: string;
  consultationId?: string | null;
  onOrdered: () => void;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [tab, setTab] = useState<Tab>("all");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, Investigation>>({});
  const [priority, setPriority] = useState<InvestigationPriority>("routine");
  const [notes, setNotes] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveTemplateName, setSaveTemplateName] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);

  const reloadWorkspace = useCallback(() => {
    staffApi.investigationWorkspace().then(setWorkspace).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!open) return;
    reloadWorkspace();
  }, [open, reloadWorkspace]);

  useEffect(() => {
    if (!open) return;
    const timer = setTimeout(() => {
      staffApi
        .catalog({ q: search || undefined, category: category || undefined })
        .then(setCatalog)
        .catch((err) => setError(err instanceof Error ? err.message : "Catalog unavailable."));
    }, search ? 200 : 0);
    return () => clearTimeout(timer);
  }, [open, search, category]);

  const byCode = useMemo(() => {
    const map: Record<string, Investigation> = {};
    for (const item of catalog?.investigations ?? []) map[item.code] = item;
    for (const panel of catalog?.panels ?? []) {
      for (const member of panel.members) map[member.code] = member;
    }
    return map;
  }, [catalog]);

  const selectedList = Object.values(selected);

  function toggle(item: Investigation) {
    setSelected((current) => {
      const next = { ...current };
      if (next[item.code]) delete next[item.code];
      else next[item.code] = item;
      return next;
    });
  }

  function addMany(items: Investigation[]) {
    setSelected((current) => {
      const next = { ...current };
      for (const item of items) next[item.code] = item;
      return next;
    });
  }

  async function toggleFavorite(code: string, makeFavorite: boolean) {
    try {
      const favorites = await staffApi.toggleFavorite(code, makeFavorite);
      setWorkspace((current) => (current ? { ...current, favorites } : current));
    } catch {
      /* non-blocking */
    }
  }

  async function submit() {
    if (selectedList.length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await staffApi.createOrder({
        patient_id: patientId,
        consultation_id: consultationId ?? null,
        codes: selectedList.map((item) => item.code),
        priority,
        clinical_notes: notes.trim() || undefined,
        provisional_diagnosis: diagnosis.trim() || undefined,
      });
      setSelected({});
      setNotes("");
      setDiagnosis("");
      onOrdered();
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate the request.");
    } finally {
      setSubmitting(false);
    }
  }

  async function saveTemplate() {
    if (!saveTemplateName.trim() || selectedList.length === 0) return;
    setSavingTemplate(true);
    try {
      await staffApi.createTemplate({
        name: saveTemplateName.trim(),
        codes: selectedList.map((item) => item.code),
      });
      setSaveTemplateName("");
      reloadWorkspace();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save the template.");
    } finally {
      setSavingTemplate(false);
    }
  }

  const favorites = workspace?.favorites ?? [];

  function InvestigationRow({ item }: { item: Investigation }) {
    const isSelected = Boolean(selected[item.code]);
    const isFavorite = favorites.includes(item.code);
    return (
      <div
        className={cn(
          "group flex items-start gap-3 rounded-lg border p-3 transition",
          isSelected ? "border-pine bg-pine/[0.04]" : "border-border bg-white hover:border-pine/30"
        )}
      >
        <button
          onClick={() => toggle(item)}
          className={cn(
            "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border transition",
            isSelected ? "border-pine bg-pine text-mint" : "border-ink-faint/50 bg-white"
          )}
          aria-label={isSelected ? `Remove ${item.name}` : `Add ${item.name}`}
          aria-pressed={isSelected}
        >
          {isSelected && (
            <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" fill="none">
              <path d="M2 6.2l2.6 2.6L10 3.4" stroke="currentColor" strokeWidth="2"
                    strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </button>

        <button onClick={() => toggle(item)} className="min-w-0 flex-1 text-left">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium text-ink">{item.name}</span>
            <Badge variant="outline" size="sm">{item.category_label}</Badge>
          </div>
          {(item.specimen_or_site || item.turnaround) && (
            <p className="mt-0.5 text-xs text-ink-muted">
              {[item.specimen_or_site, item.turnaround].filter(Boolean).join(" · ")}
            </p>
          )}
          {item.preparation && (
            <p className="mt-0.5 text-xs text-marigold-deep">Prep: {item.preparation}</p>
          )}
        </button>

        <Tooltip>
          <TooltipTrigger asChild>
            <button
              onClick={() => toggleFavorite(item.code, !isFavorite)}
              className="shrink-0 rounded p-1 transition hover:bg-mint"
              aria-label={isFavorite ? "Remove from favourites" : "Add to favourites"}
            >
              <Star
                className={cn(
                  "h-4 w-4",
                  isFavorite ? "fill-marigold text-marigold" : "text-ink-faint opacity-0 group-hover:opacity-100"
                )}
              />
            </button>
          </TooltipTrigger>
          <TooltipContent>{isFavorite ? "Remove favourite" : "Add favourite"}</TooltipContent>
        </Tooltip>
      </div>
    );
  }

  function renderList() {
    if (!catalog) {
      return (
        <div className="space-y-2">
          {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16 w-full rounded-lg" />)}
        </div>
      );
    }

    if (tab === "favorites") {
      const items = favorites.map((code) => byCode[code]).filter(Boolean);
      return items.length ? (
        <div className="space-y-2">{items.map((i) => <InvestigationRow key={i.code} item={i} />)}</div>
      ) : (
        <Empty text="No favourites yet. Tap the star on any investigation to keep it here." />
      );
    }

    if (tab === "recent") {
      const items = (workspace?.recent ?? []).map((r) => byCode[r.code]).filter(Boolean);
      return items.length ? (
        <div className="space-y-2">{items.map((i) => <InvestigationRow key={i.code} item={i} />)}</div>
      ) : (
        <Empty text="Nothing ordered yet. Your recent investigations will collect here." />
      );
    }

    if (tab === "templates") {
      const templates = workspace?.templates ?? [];
      return templates.length ? (
        <div className="space-y-2">
          {templates.map((template) => {
            const members = template.codes.map((code) => byCode[code]).filter(Boolean);
            return (
              <div key={template.id} className="rounded-lg border border-border bg-white p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-pine">{template.name}</span>
                      {template.shared && <Badge variant="secondary" size="sm">Shared</Badge>}
                    </div>
                    {template.description && (
                      <p className="mt-0.5 text-xs text-ink-muted">{template.description}</p>
                    )}
                    <p className="mt-1 text-xs text-ink-faint">
                      {members.map((m) => m.name).join(", ") || template.codes.join(", ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <Button size="sm" variant="outline" onClick={() => addMany(members)}>
                      Add all
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="Delete template"
                      onClick={async () => {
                        await staffApi.deleteTemplate(template.id).catch(() => undefined);
                        reloadWorkspace();
                      }}
                    >
                      <Trash2 className="h-4 w-4 text-ink-faint" />
                    </Button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty text="No templates yet. Select investigations, then save them as a template below." />
      );
    }

    if (tab === "panels") {
      return (
        <div className="space-y-2">
          {catalog.panels.map((panel: Panel) => (
            <div key={panel.code} className="rounded-lg border border-border bg-white p-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <span className="text-sm font-semibold text-pine">{panel.name}</span>
                  <p className="mt-0.5 text-xs text-ink-muted">{panel.description}</p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {panel.members.map((member) => (
                      <Badge key={member.code} variant="secondary" size="sm">{member.name}</Badge>
                    ))}
                  </div>
                </div>
                <Button size="sm" variant="outline" className="shrink-0"
                        onClick={() => addMany(panel.members)}>
                  Add panel
                </Button>
              </div>
            </div>
          ))}
        </div>
      );
    }

    return catalog.investigations.length ? (
      <div className="space-y-2">
        {catalog.investigations.map((item) => <InvestigationRow key={item.code} item={item} />)}
      </div>
    ) : (
      <Empty text={`No investigations match "${search}".`} />
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[86vh] max-h-[860px] w-[96vw] max-w-6xl flex-col gap-0 p-0">
        <DialogHeader className="border-b border-border px-5 py-4">
          <DialogTitle>Order investigations</DialogTitle>
          <DialogDescription>
            Search or browse by category, then generate one request slip.
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          {/* Browse */}
          <div className="flex min-h-0 flex-1 flex-col border-b border-border lg:border-b-0 lg:border-r">
            <div className="space-y-3 px-5 py-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
                <Input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search investigations — name, abbreviation or site…"
                  className="pl-9"
                  autoFocus
                />
              </div>

              <div className="flex flex-wrap gap-1">
                {TABS.map((entry) => (
                  <button
                    key={entry.key}
                    onClick={() => setTab(entry.key)}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition",
                      tab === entry.key
                        ? "bg-pine text-mint"
                        : "bg-mint text-ink-muted hover:text-pine"
                    )}
                  >
                    <entry.icon className="h-3.5 w-3.5" />
                    {entry.label}
                  </button>
                ))}
              </div>

              {tab === "all" && catalog && (
                <div className="flex flex-wrap gap-1">
                  <button
                    onClick={() => setCategory(null)}
                    className={cn(
                      "rounded-full px-2.5 py-1 text-xs font-medium transition",
                      category === null ? "bg-pine text-mint" : "bg-mint text-ink-muted hover:text-pine"
                    )}
                  >
                    All
                  </button>
                  {catalog.categories.map((entry) => (
                    <button
                      key={entry.value}
                      onClick={() => setCategory(entry.value)}
                      className={cn(
                        "rounded-full px-2.5 py-1 text-xs font-medium transition",
                        category === entry.value
                          ? "bg-pine text-mint"
                          : "bg-mint text-ink-muted hover:text-pine"
                      )}
                    >
                      {entry.label}
                      <span className="ml-1 tabular opacity-60">{entry.count}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="thin-scroll min-h-0 flex-1 overflow-y-auto px-5 pb-5">{renderList()}</div>
          </div>

          {/* Selection & request */}
          <div className="flex w-full min-h-0 flex-col bg-mint/40 lg:w-[380px]">
            <div className="border-b border-border px-5 py-3">
              <p className="font-display text-sm font-semibold text-pine">
                Selected
                <span className="tabular ml-2 rounded-full bg-pine px-2 py-0.5 text-xs text-mint">
                  {selectedList.length}
                </span>
              </p>
            </div>

            <div className="thin-scroll min-h-0 flex-1 space-y-1.5 overflow-y-auto px-5 py-3">
              <AnimatePresence initial={false}>
                {selectedList.length === 0 ? (
                  <p className="py-8 text-center text-sm text-ink-faint">
                    Nothing selected yet.
                  </p>
                ) : (
                  selectedList.map((item) => (
                    <motion.div
                      key={item.code}
                      initial={{ opacity: 0, x: 8 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.14 }}
                      className="flex items-center gap-2 rounded-md bg-white px-2.5 py-2"
                    >
                      <span className="min-w-0 flex-1 truncate text-xs text-ink">{item.name}</span>
                      <button
                        onClick={() => toggle(item)}
                        className="shrink-0 rounded p-0.5 text-ink-faint transition hover:bg-mint hover:text-clay"
                        aria-label={`Remove ${item.name}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </motion.div>
                  ))
                )}
              </AnimatePresence>
            </div>

            <div className="space-y-3 border-t border-border px-5 py-4">
              <div>
                <label className="field-label" htmlFor="priority">Priority</label>
                <div className="flex gap-1">
                  {(["routine", "urgent", "stat"] as InvestigationPriority[]).map((value) => (
                    <button
                      key={value}
                      onClick={() => setPriority(value)}
                      className={cn(
                        "flex-1 rounded-md px-2 py-1.5 text-xs font-semibold capitalize transition",
                        priority === value
                          ? value === "stat"
                            ? "bg-clay text-white"
                            : value === "urgent"
                              ? "bg-marigold text-pine-deep"
                              : "bg-pine text-mint"
                          : "bg-white text-ink-muted hover:text-pine"
                      )}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="field-label" htmlFor="diagnosis">Provisional diagnosis</label>
                <Input
                  id="diagnosis"
                  value={diagnosis}
                  onChange={(event) => setDiagnosis(event.target.value)}
                  placeholder="e.g. ? iron deficiency anaemia"
                  className="h-9 bg-white text-sm"
                />
              </div>

              <div>
                <label className="field-label" htmlFor="notes">Clinical notes for the lab</label>
                <textarea
                  id="notes"
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  rows={2}
                  placeholder="Anything the lab or radiologist should know"
                  className="field-input resize-none text-sm"
                />
              </div>

              {selectedList.length > 0 && (
                <div className="flex gap-1.5">
                  <Input
                    value={saveTemplateName}
                    onChange={(event) => setSaveTemplateName(event.target.value)}
                    placeholder="Save as template…"
                    className="h-9 bg-white text-xs"
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-9 shrink-0"
                    onClick={saveTemplate}
                    disabled={savingTemplate || !saveTemplateName.trim()}
                  >
                    {savingTemplate ? <Loader2 className="animate-spin" /> : "Save"}
                  </Button>
                </div>
              )}

              {error && (
                <p role="alert" className="rounded-md bg-clay/10 px-3 py-2 text-xs text-clay">
                  {error}
                </p>
              )}

              <Button
                className="w-full"
                size="lg"
                onClick={submit}
                disabled={submitting || selectedList.length === 0}
              >
                {submitting ? <Loader2 className="animate-spin" /> : <FlaskConical />}
                Generate request ({selectedList.length})
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="py-12 text-center text-sm text-ink-faint">{text}</p>;
}
