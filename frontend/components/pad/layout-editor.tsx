"use client";

/**
 * Editing what a pad looks like: which sections, in what order, called what,
 * shown on screen or on paper, and the fields inside them.
 *
 * A doctor saves their own layout; a department's or the hospital's layout
 * needs an administrator. Sections the system reads when a document is signed
 * — the discharge summary's final diagnosis, the pre-op checks — can be moved
 * and renamed but not removed, and certificates, consent forms and radiology
 * reports are not offered at all: their fields decide their printed wording.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronDown, Loader2, Lock, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type {
  FieldSpec,
  FieldType,
  LayoutScope,
  PadDocumentTypeInfo,
  PadLayout,
  SectionKind,
  SectionSpec,
} from "@/lib/padTypes";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SELECT =
  "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

const KIND_LABEL: Record<SectionKind, string> = {
  text: "Free text", list: "List", fields: "Fields", ai: "AI draft",
};
const FIELD_TYPES: { key: FieldType; label: string }[] = [
  { key: "text", label: "Short text" }, { key: "textarea", label: "Long text" },
  { key: "number", label: "Number" }, { key: "date", label: "Date" },
  { key: "select", label: "Choose one" }, { key: "multiselect", label: "Choose several" },
  { key: "checkbox", label: "Tick box" },
];

function slug(label: string, taken: Set<string>, fallback: string): string {
  let base = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40);
  if (!/^[a-z]/.test(base)) base = `${fallback}_${base}`.replace(/_+$/, "").slice(0, 40);
  let key = base;
  let counter = 2;
  while (taken.has(key)) key = `${base}_${counter++}`.slice(0, 47);
  return key;
}

function moved<T>(items: T[], index: number, by: number): T[] {
  const target = index + by;
  if (target < 0 || target >= items.length) return items;
  const next = [...items];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function LayoutEditor() {
  const { user } = useAuth();
  const administrator = user?.role === "admin";
  const [types, setTypes] = useState<PadDocumentTypeInfo[]>([]);
  const [documentType, setDocumentType] = useState("opd_visit");
  const [layout, setLayout] = useState<PadLayout | null>(null);
  const [sections, setSections] = useState<SectionSpec[]>([]);
  const [scope, setScope] = useState<LayoutScope>("personal");
  const [name, setName] = useState("");
  const [dirty, setDirty] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [newKind, setNewKind] = useState<SectionKind>("text");
  const [confirmReset, setConfirmReset] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void staffApi.padDocumentTypes()
      .then((result) => setTypes(result.items.filter((item) => !item.family)))
      .catch(() => undefined);
  }, []);

  const load = useCallback(async () => {
    try {
      const result = await staffApi.padLayout(documentType);
      setLayout(result);
      setSections(result.sections.map((section) => ({ ...section, fields: [...(section.fields ?? [])] })));
      setName(result.name);
      setDirty(false);
      setError(null);
      setNotice(null);
      setConfirmReset(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The layout could not be loaded.");
    }
  }, [documentType]);

  useEffect(() => {
    void load();
  }, [load]);

  const protectedSections = useMemo(() => layout?.protected ?? {}, [layout]);

  function change(next: SectionSpec[]) {
    setSections(next);
    setDirty(true);
    setNotice(null);
  }
  const updateSection = (index: number, patch: Partial<SectionSpec>) =>
    change(sections.map((section, i) => (i === index ? { ...section, ...patch } : section)));
  const updateField = (sectionIndex: number, fieldIndex: number, patch: Partial<FieldSpec>) =>
    updateSection(sectionIndex, {
      fields: sections[sectionIndex].fields.map((field, i) => (i === fieldIndex ? { ...field, ...patch } : field)),
    });

  function addSection() {
    const title = newTitle.trim();
    if (!title) return;
    const key = slug(title, new Set(sections.map((section) => section.key)), "section");
    const section: SectionSpec = {
      key, title, kind: newKind, visible_in_pad: true, visible_in_print: true, carry_forward: false,
      fields: newKind === "fields" ? [{ key: "value", label: "Value", type: "text", options: [], required: false }] : [],
    };
    change([...sections, section]);
    setExpanded(key);
    setNewTitle("");
  }

  function addField(sectionIndex: number) {
    const section = sections[sectionIndex];
    const key = slug("new field", new Set(section.fields.map((field) => field.key)), "field");
    updateSection(sectionIndex, {
      fields: [...section.fields, { key, label: "New field", type: "text", options: [], required: false }],
    });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const saved = await staffApi.savePadLayout(documentType, { scope, name, sections });
      setLayout(saved);
      setSections(saved.sections.map((section) => ({ ...section, fields: [...(section.fields ?? [])] })));
      setDirty(false);
      setNotice(`Saved as the ${scope === "personal" ? "your own" : scope} layout (revision ${saved.revision}).`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The layout could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.resetPadLayout(documentType, scope);
      await load();
      setNotice(`The ${scope === "personal" ? "your own" : scope} layout was removed; the next one out now applies.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The layout could not be reset.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-wrap items-end gap-3 p-4">
          <label className="space-y-1 text-xs text-ink-muted">
            Document
            <select className={cn(SELECT, "block w-64")} value={documentType}
                    onChange={(event) => setDocumentType(event.target.value)}>
              {types.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
            </select>
          </label>
          <label className="space-y-1 text-xs text-ink-muted">
            Save as
            <select className={cn(SELECT, "block w-48")} value={scope}
                    onChange={(event) => setScope(event.target.value as LayoutScope)}>
              <option value="personal">My own layout</option>
              <option value="department" disabled={!administrator}>My department&apos;s layout</option>
              <option value="hospital" disabled={!administrator}>The hospital&apos;s layout</option>
            </select>
          </label>
          <label className="space-y-1 text-xs text-ink-muted">
            Name
            <Input className="w-56" value={name} onChange={(event) => { setName(event.target.value); setDirty(true); }} />
          </label>
          <div className="ml-auto flex gap-2">
            {confirmReset ? (
              <>
                <Button size="sm" variant="ghost" onClick={() => setConfirmReset(false)}>Keep it</Button>
                <Button size="sm" variant="outline" className="text-clay" disabled={busy} onClick={() => void reset()}>
                  Remove this layout
                </Button>
              </>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setConfirmReset(true)}>
                <RotateCcw className="h-4 w-4" /> Reset
              </Button>
            )}
            <Button size="sm" disabled={busy || !dirty} onClick={() => void save()}>
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Save
            </Button>
          </div>
          {layout && (
            <p className="w-full text-xs text-ink-faint">
              Showing the {layout.scope === "default" ? "built-in" : layout.scope} layout
              {layout.updated_by_name ? `, last changed by ${layout.updated_by_name}` : ""}. Doctors see their own
              layout first, then their department&apos;s, then the hospital&apos;s. Documents already written keep
              the layout they were written with.
            </p>
          )}
          {error && <p className="w-full text-sm text-clay">{error}</p>}
          {notice && <p className="w-full text-sm text-pine">{notice}</p>}
        </CardContent>
      </Card>

      <div className="space-y-2">
        {sections.map((section, index) => {
          const guard = protectedSections[section.key];
          const open = expanded === section.key;
          return (
            <Card key={section.key} className={cn(!section.visible_in_pad && "opacity-70")}>
              <CardContent className="space-y-3 p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <div className="flex flex-col">
                    <button className="rounded p-0.5 text-ink-faint hover:text-pine disabled:opacity-30" disabled={index === 0}
                            aria-label="Move up" onClick={() => change(moved(sections, index, -1))}>
                      <ArrowUp className="h-3.5 w-3.5" />
                    </button>
                    <button className="rounded p-0.5 text-ink-faint hover:text-pine disabled:opacity-30"
                            disabled={index === sections.length - 1} aria-label="Move down"
                            onClick={() => change(moved(sections, index, 1))}>
                      <ArrowDown className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <Input className="h-8 w-64" value={section.title} maxLength={80}
                         onChange={(event) => updateSection(index, { title: event.target.value })} />
                  <Badge variant="outline" size="sm">{KIND_LABEL[section.kind]}</Badge>
                  {guard && (
                    <span className="flex items-center gap-1 text-xs text-ink-faint" title="Used when the document is signed">
                      <Lock className="h-3 w-3" /> Needed when signing
                    </span>
                  )}
                  <div className="ml-auto flex flex-wrap items-center gap-3 text-xs text-ink-muted">
                    <label className="flex items-center gap-1">
                      <input type="checkbox" checked={section.visible_in_pad}
                             onChange={(event) => updateSection(index, { visible_in_pad: event.target.checked })} />
                      On screen
                    </label>
                    <label className="flex items-center gap-1">
                      <input type="checkbox" checked={section.visible_in_print}
                             onChange={(event) => updateSection(index, { visible_in_print: event.target.checked })} />
                      Printed
                    </label>
                    <label className="flex items-center gap-1">
                      <input type="checkbox" checked={section.carry_forward}
                             onChange={(event) => updateSection(index, { carry_forward: event.target.checked })} />
                      Copy to next visit
                    </label>
                    {(section.kind === "fields" || section.kind === "text" || section.kind === "list") && (
                      <button className="rounded p-1 text-ink-faint hover:text-pine" aria-label="Details"
                              onClick={() => setExpanded(open ? null : section.key)}>
                        <ChevronDown className={cn("h-4 w-4 transition", open && "rotate-180")} />
                      </button>
                    )}
                    <button className="rounded p-1 text-ink-faint hover:text-clay disabled:opacity-30" disabled={Boolean(guard)}
                            aria-label={`Remove ${section.title}`}
                            onClick={() => change(sections.filter((_, i) => i !== index))}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {open && section.kind !== "fields" && (
                  <label className="block space-y-1 text-xs text-ink-muted">
                    Hint shown in the empty box
                    <Input value={section.placeholder ?? ""} maxLength={160}
                           onChange={(event) => updateSection(index, { placeholder: event.target.value || null })} />
                  </label>
                )}

                {open && section.kind === "fields" && (
                  <div className="space-y-2 rounded-lg bg-mint/40 p-2">
                    {section.fields.map((field, fieldIndex) => {
                      const locked = Boolean(guard?.includes(field.key));
                      return (
                        <div key={field.key} className="flex flex-wrap items-center gap-2">
                          <div className="flex">
                            <button className="rounded p-0.5 text-ink-faint hover:text-pine disabled:opacity-30"
                                    disabled={fieldIndex === 0} aria-label="Move field up"
                                    onClick={() => updateSection(index, { fields: moved(section.fields, fieldIndex, -1) })}>
                              <ArrowUp className="h-3.5 w-3.5" />
                            </button>
                            <button className="rounded p-0.5 text-ink-faint hover:text-pine disabled:opacity-30"
                                    disabled={fieldIndex === section.fields.length - 1} aria-label="Move field down"
                                    onClick={() => updateSection(index, { fields: moved(section.fields, fieldIndex, 1) })}>
                              <ArrowDown className="h-3.5 w-3.5" />
                            </button>
                          </div>
                          <Input className="h-8 w-52" value={field.label} maxLength={80}
                                 onChange={(event) => updateField(index, fieldIndex, { label: event.target.value })} />
                          <select className={cn(SELECT, "h-8")} value={field.type} disabled={locked}
                                  onChange={(event) => updateField(index, fieldIndex, { type: event.target.value as FieldType })}>
                            {FIELD_TYPES.map((kind) => <option key={kind.key} value={kind.key}>{kind.label}</option>)}
                          </select>
                          {(field.type === "number" || field.type === "text") && (
                            <Input className="h-8 w-20" placeholder="Unit" value={field.unit ?? ""} maxLength={24}
                                   onChange={(event) => updateField(index, fieldIndex, { unit: event.target.value || null })} />
                          )}
                          {(field.type === "select" || field.type === "multiselect") && (
                            <Input className="h-8 w-72" placeholder="Choices, separated by commas"
                                   value={field.options.join(", ")}
                                   onChange={(event) => updateField(index, fieldIndex, {
                                     options: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
                                   })} />
                          )}
                          <label className="flex items-center gap-1 text-xs text-ink-muted">
                            <input type="checkbox" checked={field.required} disabled={locked}
                                   onChange={(event) => updateField(index, fieldIndex, { required: event.target.checked })} />
                            Required
                          </label>
                          {locked && <Lock className="h-3 w-3 text-ink-faint" />}
                          <button className="rounded p-1 text-ink-faint hover:text-clay disabled:opacity-30"
                                  disabled={locked || section.fields.length === 1} aria-label={`Remove ${field.label}`}
                                  onClick={() => updateSection(index, { fields: section.fields.filter((_, i) => i !== fieldIndex) })}>
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      );
                    })}
                    <Button size="sm" variant="ghost" onClick={() => addField(index)}>
                      <Plus className="h-3.5 w-3.5" /> Add a field
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle>Add a section</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap items-center gap-2">
          <Input className="w-64" placeholder="Title, e.g. Local examination" value={newTitle} maxLength={80}
                 onChange={(event) => setNewTitle(event.target.value)} />
          <select className={SELECT} value={newKind} onChange={(event) => setNewKind(event.target.value as SectionKind)}>
            <option value="text">Free text</option>
            <option value="list">List</option>
            <option value="fields">Fields</option>
          </select>
          <Button size="sm" variant="outline" disabled={!newTitle.trim()} onClick={addSection}>
            <Plus className="h-4 w-4" /> Add
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
