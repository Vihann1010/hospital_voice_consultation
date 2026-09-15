"use client";

/**
 * The laboratory's test list and its short lists.
 *
 * A test is its result lines; a numeric line carries the reference ranges
 * every flag on a report is computed from. Changing a range, a unit or which
 * choices count as normal clears the test's review, and an unreviewed test
 * cannot be verified — so a range typed wrongly here stops reports going out
 * rather than quietly mis-flagging them.
 *
 * A line removed from a test is retired, not deleted: results already entered
 * against it still name it.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, Loader2, Plus, Search, Trash2, Undo2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { LabMaster, LabOptions, LabTest, MasterKind, ResultType } from "@/lib/types/lab";
import { canEditLabTests, canVerifyLab } from "@/lib/types/lab";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

interface RangeForm {
  sex: "" | "male" | "female";
  min_age: string;
  max_age: string;
  low: string;
  high: string;
  critical_low: string;
  critical_high: string;
}

interface ParamForm {
  key: string;
  id: string | null;
  name: string;
  analyte_key: string;
  result_type: ResultType;
  unit: string;
  method: string;
  choices: string;
  normal_values: string;
  ranges: RangeForm[];
  range_text: string;
  print_default: boolean;
  is_active: boolean;
  open: boolean;
}

interface TestForm {
  id: string | null;
  code: string;
  name: string;
  group_name: string;
  specimen: string;
  service_code: string;
  catalog_code: string;
  is_culture: boolean;
  turnaround_hours: string;
  interpretation: string;
  is_active: boolean;
  notes: string;
  parameters: ParamForm[];
}

let sequence = 0;
const nextKey = () => `line-${++sequence}`;
const text = (value: number | string | null | undefined) => (value === null || value === undefined ? "" : String(value));

const blankRange = (): RangeForm => ({ sex: "", min_age: "0", max_age: "120", low: "", high: "", critical_low: "", critical_high: "" });

const blankParam = (): ParamForm => ({
  key: nextKey(), id: null, name: "", analyte_key: "", result_type: "numeric", unit: "", method: "", choices: "",
  normal_values: "", ranges: [], range_text: "", print_default: true, is_active: true, open: true,
});

function toForm(test: LabTest | null): TestForm {
  if (!test) {
    return {
      id: null, code: "", name: "", group_name: "", specimen: "", service_code: "", catalog_code: "", is_culture: false,
      turnaround_hours: "24", interpretation: "", is_active: true, notes: "", parameters: [blankParam()],
    };
  }
  return {
    id: test.id,
    code: test.code,
    name: test.name,
    group_name: test.group_name,
    specimen: test.specimen ?? "",
    service_code: test.service_code ?? "",
    catalog_code: test.catalog_code ?? "",
    is_culture: test.is_culture,
    turnaround_hours: String(test.turnaround_hours),
    interpretation: test.interpretation ?? "",
    is_active: test.is_active,
    notes: test.notes ?? "",
    parameters: test.parameters.map((p) => ({
      key: nextKey(),
      id: p.id,
      name: p.name,
      analyte_key: p.analyte_key ?? "",
      result_type: p.result_type,
      unit: p.unit ?? "",
      method: p.method ?? "",
      choices: p.choices.join(", "),
      normal_values: p.normal_values.join(", "),
      ranges: p.ranges.map((r) => ({
        sex: (r.sex ?? "") as RangeForm["sex"],
        min_age: text(r.min_age), max_age: text(r.max_age), low: text(r.low), high: text(r.high),
        critical_low: text(r.critical_low), critical_high: text(r.critical_high),
      })),
      range_text: p.range_text ?? "",
      print_default: p.print_default,
      is_active: p.is_active,
      open: false,
    })),
  };
}

const split = (value: string) => value.split(",").map((entry) => entry.trim()).filter(Boolean);

function numberOrNull(value: string): number | null | "bad" {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : "bad";
}

function toPayload(form: TestForm): { payload?: Record<string, unknown>; problem?: string } {
  const parameters = [];
  for (const p of form.parameters) {
    const ranges = [];
    if (p.result_type === "numeric") {
      for (const r of p.ranges) {
        const numbers = [r.low, r.high, r.critical_low, r.critical_high, r.min_age, r.max_age].map(numberOrNull);
        if (numbers.includes("bad")) return { problem: `${p.name || "A line"}: range values must be numbers` };
        const [low, high, criticalLow, criticalHigh, minAge, maxAge] = numbers as (number | null)[];
        ranges.push({
          sex: r.sex || null, min_age: minAge ?? 0, max_age: maxAge ?? 120, low, high,
          critical_low: criticalLow, critical_high: criticalHigh,
        });
      }
    }
    parameters.push({
      id: p.id,
      name: p.name.trim(),
      analyte_key: p.analyte_key.trim() || null,
      result_type: p.result_type,
      unit: p.unit.trim() || null,
      method: p.method.trim() || null,
      choices: p.result_type === "choice" ? split(p.choices) : [],
      normal_values: p.result_type === "choice" ? split(p.normal_values) : [],
      ranges,
      range_text: p.range_text.trim() || null,
      print_default: p.print_default,
      is_active: p.is_active,
    });
  }
  return {
    payload: {
      code: form.code.trim(),
      name: form.name.trim(),
      group_name: form.group_name.trim() || "General",
      specimen: form.specimen.trim() || null,
      service_code: form.service_code.trim() || null,
      catalog_code: form.catalog_code.trim() || null,
      is_culture: form.is_culture,
      turnaround_hours: Number(form.turnaround_hours) || 24,
      interpretation: form.interpretation.trim() || null,
      is_active: form.is_active,
      notes: form.notes.trim() || null,
      parameters,
    },
  };
}

function Field({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cn("block space-y-1", className)}>
      <span className="text-xs font-medium text-ink-muted">{label}</span>
      {children}
    </label>
  );
}

// ----------------------------------------------------------- short lists
const KIND_LABEL: Record<MasterKind, string> = {
  group: "Report groups",
  unit: "Units",
  method: "Methods",
  specimen: "Specimens",
  antibiotic: "Antibiotics",
  organism: "Organisms",
};

function ListsEditor({ lists, editable, onSaved }: { lists: Record<string, LabMaster[]>; editable: boolean; onSaved: () => void }) {
  const [kind, setKind] = useState<MasterKind>("antibiotic");
  const [drafts, setDrafts] = useState<Record<string, { name: string; category: string; is_active: boolean }>>({});
  const [adding, setAdding] = useState({ name: "", category: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const entries = lists[kind] ?? [];

  async function save(entry: LabMaster | null) {
    const draft = entry ? drafts[entry.id] : { ...adding, is_active: true };
    if (!draft || !draft.name.trim()) return;
    setBusy(entry?.id ?? "new");
    setError(null);
    try {
      await staffApi.saveLabMaster(
        {
          kind,
          name: draft.name.trim(),
          code: entry?.code ?? null,
          category: draft.category.trim() || null,
          position: entry?.position ?? entries.length,
          is_active: draft.is_active,
        },
        entry?.id
      );
      if (entry) {
        setDrafts((current) => {
          const next = { ...current };
          delete next[entry.id];
          return next;
        });
      } else {
        setAdding({ name: "", category: "" });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That entry could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(KIND_LABEL) as MasterKind[]).map((value) => (
            <button
              key={value}
              onClick={() => setKind(value)}
              className={cn(
                "rounded-full border px-3 py-1 text-xs font-medium",
                kind === value ? "border-pine bg-pine text-mint" : "border-border text-ink-muted hover:border-pine/40"
              )}
            >
              {KIND_LABEL[value]} ({(lists[value] ?? []).length})
            </button>
          ))}
        </div>
        {error && <p className="text-sm text-clay">{error}</p>}
        <div className="divide-y divide-border">
          {entries.map((entry) => {
            const draft = drafts[entry.id] ?? { name: entry.name, category: entry.category ?? "", is_active: entry.is_active };
            const changed = Boolean(drafts[entry.id]);
            const setDraft = (patch: Partial<typeof draft>) =>
              setDrafts((current) => ({ ...current, [entry.id]: { ...draft, ...patch } }));
            return (
              <div key={entry.id} className="flex flex-wrap items-center gap-2 py-1.5">
                <Input className="h-8 max-w-xs" disabled={!editable} value={draft.name} onChange={(event) => setDraft({ name: event.target.value })} />
                {kind === "antibiotic" && (
                  <Input
                    className="h-8 max-w-[14rem]"
                    disabled={!editable}
                    placeholder="Class"
                    value={draft.category}
                    onChange={(event) => setDraft({ category: event.target.value })}
                  />
                )}
                <label className="flex items-center gap-1 text-xs text-ink-muted">
                  <input type="checkbox" disabled={!editable} checked={draft.is_active} onChange={(event) => setDraft({ is_active: event.target.checked })} />
                  In use
                </label>
                {editable && changed && (
                  <Button size="sm" disabled={busy !== null} onClick={() => void save(entry)}>
                    {busy === entry.id && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                  </Button>
                )}
              </div>
            );
          })}
        </div>
        {editable && (
          <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
            <Input className="h-8 max-w-xs" placeholder={`Add to ${KIND_LABEL[kind].toLowerCase()}`} value={adding.name} onChange={(event) => setAdding({ ...adding, name: event.target.value })} />
            {kind === "antibiotic" && (
              <Input className="h-8 max-w-[14rem]" placeholder="Class" value={adding.category} onChange={(event) => setAdding({ ...adding, category: event.target.value })} />
            )}
            <Button size="sm" variant="outline" disabled={busy !== null || !adding.name.trim()} onClick={() => void save(null)}>
              <Plus className="h-3.5 w-3.5" /> Add
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------ tests
export function LabTestList() {
  const { user } = useAuth();
  const editable = canEditLabTests(user?.role);
  const reviewer = canVerifyLab(user?.role);
  const [tab, setTab] = useState<"tests" | "lists">("tests");
  const [tests, setTests] = useState<LabTest[]>([]);
  const [lists, setLists] = useState<Record<string, LabMaster[]>>({});
  const [options, setOptions] = useState<LabOptions | null>(null);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<LabTest | null>(null);
  const [form, setForm] = useState<TestForm | null>(null);
  const [busy, setBusy] = useState<"save" | "review" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadTests = useCallback(async () => {
    setTests(await staffApi.labTests({ include_inactive: true }));
  }, []);
  const loadLists = useCallback(async () => {
    const all = await staffApi.labMasters({ include_inactive: true });
    const grouped: Record<string, LabMaster[]> = {};
    for (const entry of all) (grouped[entry.kind] = grouped[entry.kind] || []).push(entry);
    setLists(grouped);
  }, []);

  useEffect(() => {
    void loadTests().catch((err) => setError(err instanceof Error ? err.message : "The test list could not be loaded."));
    void loadLists().catch(() => undefined);
    void staffApi.labOptions().then(setOptions).catch(() => undefined);
  }, [loadTests, loadLists]);

  const grouped = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const map = new Map<string, LabTest[]>();
    for (const test of tests) {
      if (needle && !test.name.toLowerCase().includes(needle) && !test.code.toLowerCase().includes(needle)) continue;
      const list = map.get(test.group_name) ?? [];
      list.push(test);
      map.set(test.group_name, list);
    }
    return Array.from(map.entries());
  }, [tests, search]);

  function choose(test: LabTest | null) {
    setSelected(test);
    setForm(toForm(test));
    setError(null);
    setMessage(null);
  }

  function setParam(key: string, patch: Partial<ParamForm>) {
    setForm((current) =>
      current ? { ...current, parameters: current.parameters.map((p) => (p.key === key ? { ...p, ...patch } : p)) } : current
    );
  }

  function moveParam(key: string, offset: number) {
    setForm((current) => {
      if (!current) return current;
      const index = current.parameters.findIndex((p) => p.key === key);
      const target = index + offset;
      if (index < 0 || target < 0 || target >= current.parameters.length) return current;
      const next = [...current.parameters];
      const [moved] = next.splice(index, 1);
      next.splice(target, 0, moved);
      return { ...current, parameters: next };
    });
  }

  function setRange(key: string, index: number, patch: Partial<RangeForm>) {
    setForm((current) =>
      current
        ? {
            ...current,
            parameters: current.parameters.map((p) =>
              p.key === key ? { ...p, ranges: p.ranges.map((r, position) => (position === index ? { ...r, ...patch } : r)) } : p
            ),
          }
        : current
    );
  }

  async function save() {
    if (!form) return;
    const { payload, problem } = toPayload(form);
    if (problem || !payload) {
      setError(problem ?? "Check the form.");
      return;
    }
    setBusy("save");
    setError(null);
    setMessage(null);
    try {
      const saved = await staffApi.saveLabTest(payload, form.id ?? undefined);
      await loadTests();
      setSelected(saved);
      setForm(toForm(saved));
      setMessage(
        saved.is_culture || saved.ranges_reviewed_at
          ? "Saved."
          : "Saved. The ranges need a doctor's review before results for this test can be verified."
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The test could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  async function review() {
    if (!selected) return;
    setBusy("review");
    setError(null);
    try {
      const saved = await staffApi.reviewLabTest(selected.id);
      await loadTests();
      setSelected(saved);
      setMessage("Ranges reviewed. Results for this test can now be verified.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The review could not be recorded.");
    } finally {
      setBusy(null);
    }
  }

  const units = lists.unit ?? [];
  const methods = lists.method ?? [];
  const specimens = lists.specimen ?? [];
  const groups = options?.groups ?? [];
  const dirty = form !== null && JSON.stringify(form) !== JSON.stringify(toFormStable(selected, form));

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["tests", "lists"] as const).map((value) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={cn("rounded-lg px-3 py-1.5 text-sm font-medium", tab === value ? "bg-pine text-mint" : "text-ink-muted hover:bg-white")}
          >
            {value === "tests" ? "Tests" : "Short lists"}
          </button>
        ))}
      </div>

      {tab === "lists" && <ListsEditor lists={lists} editable={editable} onSaved={() => void loadLists()} />}

      {tab === "tests" && (
        <div className="grid gap-4 xl:grid-cols-[20rem_1fr]">
          <Card className="h-fit">
            <CardContent className="space-y-3 p-3">
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-faint" />
                  <Input className="pl-8" placeholder="Search tests" value={search} onChange={(event) => setSearch(event.target.value)} />
                </div>
                {editable && (
                  <Button size="sm" variant="outline" onClick={() => choose(null)}>
                    <Plus className="h-4 w-4" /> New
                  </Button>
                )}
              </div>
              <div className="max-h-[70dvh] space-y-3 overflow-y-auto pr-1">
                {grouped.map(([group, members]) => (
                  <div key={group}>
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{group}</p>
                    {members.map((test) => (
                      <button
                        key={test.id}
                        onClick={() => choose(test)}
                        className={cn(
                          "flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm",
                          selected?.id === test.id ? "bg-pine/10 text-pine" : "hover:bg-mint",
                          !test.is_active && "text-ink-faint line-through"
                        )}
                      >
                        <span className="truncate">{test.name}</span>
                        <span className="flex shrink-0 items-center gap-1">
                          {!test.service_code && <span className="text-[10px] text-marigold-deep">no price</span>}
                          {test.is_culture ? (
                            <span className="text-[10px] text-ink-faint">culture</span>
                          ) : test.ranges_reviewed_at ? (
                            <CheckCircle2 className="h-3.5 w-3.5 text-pine" aria-label="Ranges reviewed" />
                          ) : (
                            <AlertTriangle className="h-3.5 w-3.5 text-clay" aria-label="Ranges not reviewed" />
                          )}
                        </span>
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {form ? (
            <Card>
              <CardContent className="space-y-4 p-4">
                <datalist id="lab-units">{units.map((u) => <option key={u.id} value={u.name} />)}</datalist>
                <datalist id="lab-methods">{methods.map((m) => <option key={m.id} value={m.name} />)}</datalist>
                <datalist id="lab-specimens">{specimens.map((s) => <option key={s.id} value={s.name} />)}</datalist>

                {selected && !selected.is_culture && (
                  <div
                    className={cn(
                      "flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm",
                      selected.ranges_reviewed_at ? "bg-pine/10 text-pine" : "bg-clay/10 text-clay"
                    )}
                  >
                    <span>
                      {selected.ranges_reviewed_at
                        ? `Ranges reviewed by ${selected.ranges_reviewed_by_name} on ${formatDateTime(selected.ranges_reviewed_at)}.`
                        : "Ranges not reviewed. Results for this test cannot be verified until a doctor reviews them against this laboratory's analyser and kits."}
                    </span>
                    {reviewer && !selected.ranges_reviewed_at && (
                      <Button size="sm" disabled={busy !== null || dirty} onClick={() => void review()}>
                        {busy === "review" && <Loader2 className="h-3.5 w-3.5 animate-spin" />} I have checked these ranges
                      </Button>
                    )}
                  </div>
                )}

                <fieldset disabled={!editable} className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-3">
                    <Field label="Code">
                      <Input value={form.code} onChange={(event) => setForm({ ...form, code: event.target.value })} />
                    </Field>
                    <Field label="Name" className="sm:col-span-2">
                      <Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
                    </Field>
                    <Field label="Report group">
                      <Input list="lab-groups" value={form.group_name} onChange={(event) => setForm({ ...form, group_name: event.target.value })} />
                      <datalist id="lab-groups">{groups.map((g) => <option key={g} value={g} />)}</datalist>
                    </Field>
                    <Field label="Specimen">
                      <Input list="lab-specimens" value={form.specimen} onChange={(event) => setForm({ ...form, specimen: event.target.value })} />
                    </Field>
                    <Field label="Promised turnaround (hours)">
                      <Input inputMode="numeric" value={form.turnaround_hours} onChange={(event) => setForm({ ...form, turnaround_hours: event.target.value })} />
                    </Field>
                    <Field label="Price-list code">
                      <Input value={form.service_code} onChange={(event) => setForm({ ...form, service_code: event.target.value })} placeholder="e.g. INV-CBC" />
                    </Field>
                    <Field label="Doctor's order code">
                      <Input value={form.catalog_code} onChange={(event) => setForm({ ...form, catalog_code: event.target.value })} placeholder="e.g. CBC" />
                    </Field>
                    <div className="flex items-end gap-4 pb-2 text-sm">
                      <label className="flex items-center gap-1.5">
                        <input type="checkbox" checked={form.is_culture} onChange={(event) => setForm({ ...form, is_culture: event.target.checked })} />
                        Culture &amp; sensitivity
                      </label>
                      <label className="flex items-center gap-1.5">
                        <input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />
                        Offered
                      </label>
                    </div>
                  </div>
                  <Field label="Printed under the results (interpretation, method notes)">
                    <Input value={form.interpretation} onChange={(event) => setForm({ ...form, interpretation: event.target.value })} />
                  </Field>

                  {!form.is_culture && (
                    <div className="space-y-2">
                      <p className="text-sm font-semibold text-ink">Result lines</p>
                      {form.parameters.map((p, index) => (
                        <div key={p.key} className={cn("rounded-lg border border-border p-2", !p.is_active && "opacity-50")}>
                          <div className="grid items-center gap-2 md:grid-cols-[1.4fr_7rem_7rem_1fr_auto]">
                            <Input placeholder="Line name" value={p.name} onChange={(event) => setParam(p.key, { name: event.target.value })} />
                            <select className={SELECT} value={p.result_type} onChange={(event) => setParam(p.key, { result_type: event.target.value as ResultType })}>
                              <option value="numeric">Number</option>
                              <option value="choice">Choice</option>
                              <option value="text">Text</option>
                              <option value="heading">Heading</option>
                            </select>
                            <Input list="lab-units" placeholder="Unit" disabled={p.result_type === "heading"} value={p.unit} onChange={(event) => setParam(p.key, { unit: event.target.value })} />
                            <Input list="lab-methods" placeholder="Method" disabled={p.result_type === "heading"} value={p.method} onChange={(event) => setParam(p.key, { method: event.target.value })} />
                            <div className="flex items-center gap-0.5">
                              <button type="button" className="rounded p-1 text-ink-faint hover:text-pine" onClick={() => moveParam(p.key, -1)} disabled={index === 0} aria-label="Move up">
                                <ArrowUp className="h-3.5 w-3.5" />
                              </button>
                              <button type="button" className="rounded p-1 text-ink-faint hover:text-pine" onClick={() => moveParam(p.key, 1)} disabled={index === form.parameters.length - 1} aria-label="Move down">
                                <ArrowDown className="h-3.5 w-3.5" />
                              </button>
                              {p.id ? (
                                <button
                                  type="button"
                                  className="rounded p-1 text-ink-faint hover:text-clay"
                                  onClick={() => setParam(p.key, { is_active: !p.is_active })}
                                  aria-label={p.is_active ? "Retire line" : "Restore line"}
                                >
                                  {p.is_active ? <Trash2 className="h-3.5 w-3.5" /> : <Undo2 className="h-3.5 w-3.5" />}
                                </button>
                              ) : (
                                <button
                                  type="button"
                                  className="rounded p-1 text-ink-faint hover:text-clay"
                                  onClick={() => setForm({ ...form, parameters: form.parameters.filter((entry) => entry.key !== p.key) })}
                                  aria-label="Remove line"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              )}
                            </div>
                          </div>

                          {p.result_type !== "heading" && (
                            <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
                              <label className="flex items-center gap-1">
                                <input type="checkbox" checked={p.print_default} onChange={(event) => setParam(p.key, { print_default: event.target.checked })} />
                                Printed by default
                              </label>
                              {p.result_type === "numeric" && (
                                <button type="button" className="text-pine underline" onClick={() => setParam(p.key, { open: !p.open })}>
                                  {p.ranges.length ? `${p.ranges.length} range${p.ranges.length === 1 ? "" : "s"}` : "No range"} — {p.open ? "hide" : "edit"}
                                </button>
                              )}
                              <span>Printout name key: </span>
                              <Input className="h-7 w-40" placeholder="e.g. hemoglobin" value={p.analyte_key} onChange={(event) => setParam(p.key, { analyte_key: event.target.value })} />
                            </div>
                          )}

                          {p.result_type === "choice" && (
                            <div className="mt-2 grid gap-2 sm:grid-cols-2">
                              <Input placeholder="Choices, separated by commas" value={p.choices} onChange={(event) => setParam(p.key, { choices: event.target.value })} />
                              <Input placeholder="Which choices are normal (blank: none flagged)" value={p.normal_values} onChange={(event) => setParam(p.key, { normal_values: event.target.value })} />
                            </div>
                          )}

                          {p.result_type === "numeric" && p.open && (
                            <div className="mt-2 space-y-1.5 rounded-md bg-mint/40 p-2">
                              <div className="grid grid-cols-[7rem_repeat(6,minmax(0,1fr))_auto] gap-1 text-[10px] uppercase tracking-wide text-ink-faint">
                                <span>Sex</span><span>Age from</span><span>Age to</span><span>Low</span><span>High</span><span>Critical low</span><span>Critical high</span><span />
                              </div>
                              {p.ranges.map((r, rangeIndex) => (
                                <div key={rangeIndex} className="grid grid-cols-[7rem_repeat(6,minmax(0,1fr))_auto] gap-1">
                                  <select className={cn(SELECT, "h-8")} value={r.sex} onChange={(event) => setRange(p.key, rangeIndex, { sex: event.target.value as RangeForm["sex"] })}>
                                    <option value="">Everyone</option>
                                    <option value="male">Male</option>
                                    <option value="female">Female</option>
                                  </select>
                                  {(["min_age", "max_age", "low", "high", "critical_low", "critical_high"] as const).map((field) => (
                                    <Input key={field} className="h-8" inputMode="decimal" value={r[field]} onChange={(event) => setRange(p.key, rangeIndex, { [field]: event.target.value })} />
                                  ))}
                                  <button
                                    type="button"
                                    className="rounded p-1 text-ink-faint hover:text-clay"
                                    onClick={() => setParam(p.key, { ranges: p.ranges.filter((_, position) => position !== rangeIndex) })}
                                    aria-label="Remove range"
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </button>
                                </div>
                              ))}
                              <div className="flex flex-wrap items-center gap-2">
                                <Button size="sm" variant="ghost" onClick={() => setParam(p.key, { ranges: [...p.ranges, blankRange()] })}>
                                  <Plus className="h-3.5 w-3.5" /> Range
                                </Button>
                                <Input
                                  className="h-8 max-w-sm"
                                  placeholder="Printed instead of the range (optional), e.g. Desirable < 200"
                                  value={p.range_text}
                                  onChange={(event) => setParam(p.key, { range_text: event.target.value })}
                                />
                              </div>
                              <p className="text-[11px] text-ink-faint">
                                A patient who is neither male nor female is matched only against ranges for everyone. Ages are in years.
                              </p>
                            </div>
                          )}
                        </div>
                      ))}
                      <Button size="sm" variant="outline" onClick={() => setForm({ ...form, parameters: [...form.parameters, blankParam()] })}>
                        <Plus className="h-3.5 w-3.5" /> Result line
                      </Button>
                    </div>
                  )}
                </fieldset>

                {error && <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p>}
                {message && <p className="rounded-md bg-pine/10 px-3 py-2 text-sm text-pine">{message}</p>}
                {editable && (
                  <div className="flex items-center gap-2">
                    <Button disabled={busy !== null || !form.code.trim() || !form.name.trim()} onClick={() => void save()}>
                      {busy === "save" && <Loader2 className="h-4 w-4 animate-spin" />} Save test
                    </Button>
                    {dirty && <span className="text-xs text-marigold-deep">Unsaved changes</span>}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-6 text-sm text-ink-muted">Choose a test to see its result lines and ranges.</CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

/** The form a saved test would produce, keeping the current row keys so a comparison ignores them. */
function toFormStable(test: LabTest | null, current: TestForm): TestForm {
  const base = toForm(test);
  if (!test) return { ...base, parameters: current.parameters.length ? base.parameters : base.parameters };
  return {
    ...base,
    parameters: base.parameters.map((p, index) => ({
      ...p,
      key: current.parameters[index]?.key ?? p.key,
      open: current.parameters[index]?.open ?? false,
    })),
  };
}
