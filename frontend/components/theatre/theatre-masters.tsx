"use client";

/**
 * Theatre rooms and the operation list.
 *
 * The operation list sets a case's default duration and, through its price
 * code, what the patient is charged when they are wheeled out — so it is kept
 * by management, like the consultant register. Everyone else may read it.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { Operation, TheatreOptions, TheatreRoom } from "@/lib/theatreTypes";
import { canMaintainTheatre } from "@/lib/theatreTypes";
import { DEPARTMENT_LABEL } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

interface RoomForm { id?: string; code: string; name: string; is_active: boolean }
interface OperationForm {
  id?: string; code: string; name: string; department: string; grade: string;
  default_minutes: string; service_code: string; is_active: boolean;
}

const EMPTY_ROOM: RoomForm = { code: "", name: "", is_active: true };
const EMPTY_OPERATION: OperationForm = {
  code: "", name: "", department: "", grade: "", default_minutes: "60", service_code: "", is_active: true,
};

export function TheatreMasters() {
  const { user } = useAuth();
  const editable = canMaintainTheatre(user?.role);
  const [options, setOptions] = useState<TheatreOptions | null>(null);
  const [rooms, setRooms] = useState<TheatreRoom[]>([]);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [search, setSearch] = useState("");
  const [room, setRoom] = useState<RoomForm | null>(null);
  const [operation, setOperation] = useState<OperationForm | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadRooms = useCallback(async () => {
    setRooms(await staffApi.theatreRooms(true));
  }, []);
  const loadOperations = useCallback(async () => {
    setOperations(await staffApi.theatreOperations({ q: search || undefined, include_inactive: true, limit: 200 }));
  }, [search]);

  useEffect(() => {
    void staffApi.theatreOptions().then(setOptions).catch(() => undefined);
    void loadRooms().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [loadRooms]);

  useEffect(() => {
    const timer = setTimeout(() => void loadOperations().catch(() => undefined), 250);
    return () => clearTimeout(timer);
  }, [loadOperations]);

  async function saveRoom() {
    if (!room) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveTheatreRoom(
        { code: room.code, name: room.name, is_active: room.is_active, notes: null }, room.id
      );
      setRoom(null);
      await loadRooms();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The room could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function saveOperation() {
    if (!operation) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveOperation(
        {
          code: operation.code,
          name: operation.name,
          department: (operation.department || null) as Operation["department"],
          grade: operation.grade || null,
          default_minutes: Number(operation.default_minutes) || 60,
          service_code: operation.service_code || null,
          is_active: operation.is_active,
          notes: null,
        },
        operation.id
      );
      setOperation(null);
      await loadOperations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The operation could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[22rem_1fr]">
      {error && <p className="text-sm text-clay xl:col-span-2">{error}</p>}

      <Card className="h-fit">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle>Theatres</CardTitle>
          {editable && !room && (
            <Button size="sm" variant="outline" onClick={() => setRoom({ ...EMPTY_ROOM })}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {room && (
            <div className="space-y-2 rounded-lg border border-border p-3">
              <Input placeholder="Code, e.g. OT1" value={room.code} onChange={(e) => setRoom({ ...room, code: e.target.value })} />
              <Input placeholder="Name, e.g. Main theatre" value={room.name} onChange={(e) => setRoom({ ...room, name: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={room.is_active} onChange={(e) => setRoom({ ...room, is_active: e.target.checked })} />
                In use
              </label>
              <div className="flex gap-2">
                <Button size="sm" disabled={busy || !room.code || !room.name} onClick={() => void saveRoom()}>
                  {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setRoom(null)}>Cancel</Button>
              </div>
            </div>
          )}
          {rooms.length === 0 && !room && <p className="text-sm text-ink-muted">No theatres yet.</p>}
          {rooms.map((item) => (
            <div key={item.id} className="flex items-center gap-2 text-sm">
              <span className="w-14 font-mono text-xs text-ink-faint">{item.code}</span>
              <span className="flex-1 text-ink">{item.name}</span>
              {!item.is_active && <Badge variant="outline" size="sm">Not in use</Badge>}
              {editable && (
                <button className="rounded p-1 text-ink-faint hover:text-pine" aria-label={`Edit ${item.name}`}
                        onClick={() => setRoom({ id: item.id, code: item.code, name: item.name, is_active: item.is_active })}>
                  <Pencil className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center gap-2 pb-2">
          <CardTitle className="mr-auto">Operation list</CardTitle>
          <Input className="h-8 w-56" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
          {editable && !operation && (
            <Button size="sm" variant="outline" onClick={() => setOperation({ ...EMPTY_OPERATION })}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {operation && (
            <div className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-3">
              <Input placeholder="Code" value={operation.code} onChange={(e) => setOperation({ ...operation, code: e.target.value })} />
              <Input className="sm:col-span-2" placeholder="Name" value={operation.name} onChange={(e) => setOperation({ ...operation, name: e.target.value })} />
              <select className={SELECT} value={operation.department} onChange={(e) => setOperation({ ...operation, department: e.target.value })}>
                <option value="">Any department</option>
                {Object.entries(DEPARTMENT_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
              </select>
              <select className={SELECT} value={operation.grade} onChange={(e) => setOperation({ ...operation, grade: e.target.value })}>
                <option value="">No grade</option>
                {(options?.grades ?? []).map((grade) => <option key={grade} value={grade}>{grade}</option>)}
              </select>
              <Input type="number" min={5} max={1440} placeholder="Minutes" value={operation.default_minutes}
                     onChange={(e) => setOperation({ ...operation, default_minutes: e.target.value })} />
              <Input placeholder="Price-list code (for billing)" value={operation.service_code}
                     onChange={(e) => setOperation({ ...operation, service_code: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={operation.is_active} onChange={(e) => setOperation({ ...operation, is_active: e.target.checked })} />
                On the list
              </label>
              <div className="flex gap-2">
                <Button size="sm" disabled={busy || !operation.code || !operation.name} onClick={() => void saveOperation()}>
                  {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setOperation(null)}>Cancel</Button>
              </div>
            </div>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-muted">
                  <th className="py-1.5 pr-3 font-medium">Code</th>
                  <th className="py-1.5 pr-3 font-medium">Operation</th>
                  <th className="py-1.5 pr-3 font-medium">Department</th>
                  <th className="py-1.5 pr-3 font-medium">Grade</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Minutes</th>
                  <th className="py-1.5 pr-3 font-medium">Price code</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {operations.map((item) => (
                  <tr key={item.id} className={item.is_active ? "" : "opacity-50"}>
                    <td className="py-1.5 pr-3 font-mono text-xs">{item.code}</td>
                    <td className="py-1.5 pr-3 text-ink">{item.name}</td>
                    <td className="py-1.5 pr-3">{item.department ? DEPARTMENT_LABEL[item.department] : "Any"}</td>
                    <td className="py-1.5 pr-3 capitalize">{item.grade ?? "—"}</td>
                    <td className="tabular py-1.5 pr-3 text-right">{item.default_minutes}</td>
                    <td className="py-1.5 pr-3">
                      {item.service_code ?? <span className="text-marigold-deep">None — not billed</span>}
                    </td>
                    <td className="py-1.5 text-right">
                      {editable && (
                        <button className="rounded p-1 text-ink-faint hover:text-pine" aria-label={`Edit ${item.name}`}
                                onClick={() => setOperation({
                                  id: item.id, code: item.code, name: item.name, department: item.department ?? "",
                                  grade: item.grade ?? "", default_minutes: String(item.default_minutes),
                                  service_code: item.service_code ?? "", is_active: item.is_active,
                                })}>
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {operations.length === 0 && <p className="py-3 text-sm text-ink-muted">No operations found.</p>}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
