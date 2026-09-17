"use client";

/**
 * The diet list the ward orders from. Kept by management; everyone reads it.
 * A retired diet stays on the orders that used it and simply stops being
 * offered.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { DietMode } from "@/lib/types/diet";
import { canManageDiets } from "@/lib/types/diet";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface ModeForm {
  id?: string;
  code: string;
  name: string;
  description: string;
  is_nil_by_mouth: boolean;
  position: string;
  is_active: boolean;
}

const EMPTY: ModeForm = { code: "", name: "", description: "", is_nil_by_mouth: false, position: "0", is_active: true };

export function DietModesAdmin() {
  const { user } = useAuth();
  const editable = canManageDiets(user?.role);
  const [modes, setModes] = useState<DietMode[]>([]);
  const [form, setForm] = useState<ModeForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setModes(await staffApi.dietModes(true));
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [load]);

  async function save() {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveDietMode(
        {
          code: form.code.trim(), name: form.name.trim(), description: form.description.trim() || null,
          is_nil_by_mouth: form.is_nil_by_mouth, position: Number(form.position) || 0, is_active: form.is_active,
        },
        form.id
      );
      setForm(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The diet could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="max-w-3xl">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle>Diets</CardTitle>
        {editable && !form && (
          <Button size="sm" variant="outline" onClick={() => setForm({ ...EMPTY })}>
            <Plus className="h-4 w-4" /> Add diet
          </Button>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {error && <p className="text-sm text-clay">{error}</p>}
        {form && (
          <div className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-2">
            <Input placeholder="Code, e.g. SOFT" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
            <Input placeholder="Name, e.g. Soft diet" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input className="sm:col-span-2" placeholder="What the kitchen serves (optional)" value={form.description}
                   onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <Input type="number" min={0} placeholder="Order in list" value={form.position}
                   onChange={(e) => setForm({ ...form, position: e.target.value })} />
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.is_nil_by_mouth}
                       onChange={(e) => setForm({ ...form, is_nil_by_mouth: e.target.checked })} />
                Nil by mouth
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.is_active}
                       onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                In use
              </label>
            </div>
            <div className="flex gap-2 sm:col-span-2">
              <Button size="sm" disabled={busy || !form.code.trim() || form.name.trim().length < 2} onClick={() => void save()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setForm(null)}>Cancel</Button>
            </div>
          </div>
        )}
        {modes.length === 0 && !form && <p className="text-sm text-ink-muted">No diets yet.</p>}
        <ul className="divide-y divide-border rounded-lg border border-border">
          {modes.map((mode) => (
            <li key={mode.id} className="flex items-center gap-3 px-3 py-2 text-sm">
              <span className="w-24 font-mono text-xs text-ink-muted">{mode.code}</span>
              <span className="flex-1">
                <span className="font-medium">{mode.name}</span>
                {mode.description && <span className="block text-xs text-ink-muted">{mode.description}</span>}
              </span>
              {mode.is_nil_by_mouth && <Badge variant="outline">Nil by mouth</Badge>}
              {!mode.is_active && <Badge variant="outline">Retired</Badge>}
              {editable && (
                <Button size="sm" variant="ghost" aria-label={`Edit ${mode.name}`} onClick={() => setForm({
                  id: mode.id, code: mode.code, name: mode.name, description: mode.description ?? "",
                  is_nil_by_mouth: mode.is_nil_by_mouth, position: String(mode.position), is_active: mode.is_active,
                })}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
