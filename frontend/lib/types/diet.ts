/** Diet orders and the kitchen sheet — mirrors app/api/v1/routes/diet.py. */

export interface DietMode {
  id: string;
  code: string;
  name: string;
  description: string | null;
  is_nil_by_mouth: boolean;
  position: number;
  is_active: boolean;
}

export interface DietOrder {
  id: string;
  mode_id: string | null;
  mode_name: string;
  is_nil_by_mouth: boolean;
  instructions: string | null;
  starts_at: string;
  ends_at: string | null;
  ordered_by_name: string;
  ended_by_name: string | null;
  end_reason: string | null;
  created_at: string;
  in_effect: boolean;
  upcoming: boolean;
}

export interface AdmissionDiet {
  current: DietOrder | null;
  upcoming: DietOrder | null;
  orders: DietOrder[];
}

export type MealState = "diet" | "no_order" | "on_leave" | "absent";

export interface KitchenMealCell {
  state: MealState;
  diet: string | null;
  nil_by_mouth: boolean;
  instructions: string | null;
}

export interface KitchenRow {
  admission_id: string;
  ip_number: string;
  patient_name: string;
  age: number | null;
  gender: string | null;
  allergies: string[];
  ward: string;
  bed: string;
  meals: Record<string, KitchenMealCell>;
  instructions: string | null;
}

export interface KitchenSheet {
  on: string;
  meals: { label: string; at: string }[];
  rows: KitchenRow[];
  counts: Record<string, Record<string, number>>;
}

/** Ordering a diet is the doctor's and the nurse's; the list is management's. */
export const canOrderDiet = (role?: string) => ["admin", "doctor", "nurse"].includes(role ?? "");
export const canManageDiets = (role?: string) => ["admin", "manager"].includes(role ?? "");
