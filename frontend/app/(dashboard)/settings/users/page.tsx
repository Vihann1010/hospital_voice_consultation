"use client";

/**
 * Staff accounts.
 *
 * Two things happen on this screen, and they are deliberately side by side:
 * creating an account, and understanding what the role you are about to give
 * it can actually do. Assigning "supervisor" without being told that means
 * refunds is how authorisation mistakes get made, so the roles are shown with
 * their powers rather than as a bare dropdown.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { KeyRound, Loader2, ShieldCheck, UserPlus, Users } from "lucide-react";
import { ApiError, staffApi } from "@/lib/staffApi";
import { DEPARTMENTS, type Department, type StaffRole, type User } from "@/lib/types/core";
import { DEPARTMENT_FULL_LABEL } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const ROLE_ORDER: User["role"][] = [
  "admin",
  "manager",
  "doctor",
  "supervisor",
  "reception",
  "nurse",
  "lab",
];

/** Permission strings are for the API; this is for the person assigning them. */
const PERMISSION_LABELS: Record<string, string> = {
  "patient:read": "Open patient records",
  "consultation:read": "Read consultations",
  "report:read": "Read reports",
  "prescription:read": "Read prescriptions",
  "audit:read": "Read the audit trail",
  "consultation:review": "Sign off consultations",
  "copilot:use": "Use the AI copilot",
  "order:create": "Order investigations",
  "prescription:create": "Write prescriptions",
  "prescription:send": "Send prescriptions",
  "template:manage": "Manage templates",
  "report:upload": "Upload reports",
  "system:admin": "Administer staff accounts",
  "patient:register": "Register patients",
  "visit:create": "Open visits",
  "invoice:create": "Raise bills",
  "invoice:read": "Read and reprint bills",
  "payment:collect": "Take payment",
  "refund:issue": "Issue refunds",
  "invoice:cancel": "Cancel bills",
  "finance:read": "See hospital revenue",
  "tariff:manage": "Change the price list",
  "lab:register": "Register lab tests",
  "lab:result": "Enter lab results",
  "lab:verify": "Verify lab results",
  "lab:master": "Edit lab tests and ranges",
};

function RoleCard({
  role,
  selected,
  onSelect,
}: {
  role: StaffRole;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cn(
        "flex w-full flex-col gap-2 rounded-xl border p-4 text-left transition",
        selected
          ? "border-pine bg-mint shadow-card"
          : "border-border bg-card hover:border-pine/40"
      )}
    >
      <div className="flex items-center gap-2">
        <span className="font-display text-sm font-semibold capitalize text-pine">
          {role.role}
        </span>
        <Badge variant="secondary" className="tabular">
          {role.permissions.length}
        </Badge>
        <span className="ml-auto text-[11px] text-ink-faint">
          {role.user_count} {role.user_count === 1 ? "person" : "people"}
        </span>
      </div>
      <p className="text-xs leading-relaxed text-ink-muted">{role.summary}</p>
    </button>
  );
}

export default function StaffAccountsPage() {
  const toast = useToast();
  const { user: me } = useAuth();

  const [roles, setRoles] = useState<StaffRole[] | null>(null);
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [role, setRole] = useState<User["role"]>("reception");
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [department, setDepartment] = useState<Department>("orthopedics");
  const [creating, setCreating] = useState(false);

  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [r, u] = await Promise.all([staffApi.staffRoles(), staffApi.staffUsers()]);
      setRoles(r);
      setUsers(u);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? "Only an administrator can manage staff accounts."
          : err instanceof Error
            ? err.message
            : "Could not load staff accounts."
      );
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selectedRole = useMemo(
    () => roles?.find((r) => r.role === role) ?? null,
    [roles, role]
  );

  const canCreate =
    email.trim().length > 3 && fullName.trim().length > 1 && password.length >= 8;

  async function create() {
    setCreating(true);
    try {
      const created = await staffApi.createStaffUser({
        email: email.trim().toLowerCase(),
        full_name: fullName.trim(),
        password,
        role,
        department: role === "doctor" ? department : null,
      });
      toast.success(
        `${created.full_name} added`,
        `Signs in as ${created.email} with the ${created.role} role.`
      );
      setEmail("");
      setFullName("");
      setPassword("");
      await load();
    } catch (err) {
      toast.error(
        "Could not create the account",
        err instanceof Error ? err.message : undefined
      );
    } finally {
      setCreating(false);
    }
  }

  async function changeRole(target: User, next: User["role"]) {
    setBusyId(target.id);
    try {
      await staffApi.updateStaffUser(target.id, { role: next });
      toast.success(`${target.full_name} is now ${next}`);
      await load();
    } catch (err) {
      toast.error(
        "Could not change the role",
        err instanceof Error ? err.message : undefined
      );
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function toggleActive(target: User) {
    setBusyId(target.id);
    try {
      await staffApi.updateStaffUser(target.id, { is_active: !target.is_active });
      toast.success(
        target.is_active
          ? `${target.full_name} can no longer sign in`
          : `${target.full_name} can sign in again`
      );
      await load();
    } catch (err) {
      toast.error(
        "Could not change the account",
        err instanceof Error ? err.message : undefined
      );
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function resetPassword(target: User) {
    const next = window.prompt(
      `New password for ${target.full_name} (at least 8 characters).\n\nHand it to them directly — it is not emailed.`
    );
    if (!next) return;
    if (next.length < 8) {
      toast.error("Password too short", "It must be at least 8 characters.");
      return;
    }
    setBusyId(target.id);
    try {
      await staffApi.resetStaffPassword(target.id, next);
      toast.success(`Password changed for ${target.full_name}`);
    } catch (err) {
      toast.error(
        "Could not change the password",
        err instanceof Error ? err.message : undefined
      );
    } finally {
      setBusyId(null);
    }
  }

  if (error) {
    return (
      <Card className="border-clay/30 bg-clay/5">
        <CardContent className="p-6 text-sm text-clay">{error}</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-pine">Staff accounts</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Who can sign in, and what each of them is allowed to do.
        </p>
      </div>

      {/* Roles, with their powers stated before one is assigned */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-pine" />
          <h2 className="font-display text-sm font-semibold text-pine">Roles</h2>
          <span className="text-[11px] text-ink-faint">
            Select one to see exactly what it can do
          </span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {(roles ?? []).map((r) => (
            <RoleCard
              key={r.role}
              role={r}
              selected={r.role === role}
              onSelect={() => setRole(r.role)}
            />
          ))}
          {roles === null && (
            <p className="text-sm text-ink-faint">Loading roles…</p>
          )}
        </div>

        {selectedRole && (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="capitalize">
                What {selectedRole.role} can do
              </CardTitle>
            </CardHeader>
            <CardContent className="grid gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3">
              {Object.keys(PERMISSION_LABELS).map((key) => {
                const held = selectedRole.permissions.includes(key);
                return (
                  <p
                    key={key}
                    className={cn(
                      "flex items-baseline gap-2 text-xs",
                      held ? "text-ink" : "text-ink-faint"
                    )}
                  >
                    <span className={held ? "text-pine" : "text-ink-faint"}>
                      {held ? "✓" : "—"}
                    </span>
                    {PERMISSION_LABELS[key]}
                  </p>
                );
              })}
            </CardContent>
          </Card>
        )}
      </section>

      {/* Create */}
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
          <UserPlus className="h-4 w-4 text-pine" />
          <CardTitle>Add a member of staff</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="su-name">Full name</label>
              <Input
                id="su-name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Sunita Verma"
              />
            </div>
            <div>
              <label className="field-label" htmlFor="su-email">Work email</label>
              <Input
                id="su-email"
                value={email}
                inputMode="email"
                onChange={(e) => setEmail(e.target.value)}
                placeholder="sunita@satyahospital.in"
              />
            </div>
            <div>
              <label className="field-label" htmlFor="su-role">Role</label>
              <select
                id="su-role"
                className="field-input capitalize"
                value={role}
                onChange={(e) => setRole(e.target.value as User["role"])}
              >
                {ROLE_ORDER.map((r) => (
                  <option key={r} value={r} className="capitalize">
                    {r}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="field-label" htmlFor="su-pwd">First password</label>
              <Input
                id="su-pwd"
                value={password}
                type="password"
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
              />
            </div>
            {/* Only a doctor's records are scoped to a department. */}
            {role === "doctor" && (
              <div>
                <label className="field-label" htmlFor="su-dept">Department</label>
                <select
                  id="su-dept"
                  className="field-input"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value as Department)}
                >
                  {DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>{DEPARTMENT_FULL_LABEL[d] ?? d}</option>
                  ))}
                  <option value="gynecology">Maternity &amp; Gynecology</option>
                </select>
              </div>
            )}
          </div>

          <p className="text-xs text-ink-muted">
            Hand the password over in person and ask them to change it. There is no
            reset email.
          </p>

          <Button onClick={create} disabled={!canCreate || creating}>
            {creating ? <Loader2 className="animate-spin" /> : <UserPlus />}
            Add to staff
          </Button>
        </CardContent>
      </Card>

      {/* Existing staff */}
      <Card>
        <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
          <Users className="h-4 w-4 text-pine" />
          <CardTitle>Everyone with an account</CardTitle>
          {users && (
            <span className="ml-auto text-[11px] text-ink-faint">
              {users.filter((u) => u.is_active).length} active of {users.length}
            </span>
          )}
        </CardHeader>
        <CardContent className="space-y-2">
          {users === null && <p className="text-sm text-ink-faint">Loading…</p>}
          {(users ?? []).map((u) => (
            <div
              key={u.id}
              className={cn(
                "flex flex-wrap items-center gap-3 rounded-lg border border-border px-4 py-3",
                !u.is_active && "opacity-60"
              )}
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-ink">
                  {u.full_name}
                  {u.id === me?.id && (
                    <span className="ml-2 text-[11px] text-ink-faint">(you)</span>
                  )}
                </p>
                <p className="truncate text-xs text-ink-faint">
                  {u.email}
                  {u.department ? ` · ${u.department}` : ""}
                  {u.is_active ? "" : " · cannot sign in"}
                </p>
              </div>

              <select
                className="field-input h-9 w-auto capitalize"
                value={u.role}
                disabled={busyId === u.id}
                onChange={(e) => void changeRole(u, e.target.value as User["role"])}
                aria-label={`Role for ${u.full_name}`}
              >
                {ROLE_ORDER.map((r) => (
                  <option key={r} value={r} className="capitalize">
                    {r}
                  </option>
                ))}
              </select>

              <Button
                variant="ghost"
                size="sm"
                disabled={busyId === u.id}
                onClick={() => void resetPassword(u)}
              >
                <KeyRound /> Password
              </Button>

              <Button
                variant="outline"
                size="sm"
                disabled={busyId === u.id}
                onClick={() => void toggleActive(u)}
              >
                {u.is_active ? "Suspend" : "Restore"}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
