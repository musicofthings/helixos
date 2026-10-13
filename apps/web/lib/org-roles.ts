import type { OrgRole } from "@helixos/types";

export const ORG_ROLES: Array<{ value: OrgRole; label: string; hint: string }> = [
  { value: "admin", label: "Admin", hint: "Manages members; full access" },
  { value: "pi", label: "Principal investigator", hint: "Full access to lab data" },
  { value: "scientist", label: "Scientist", hint: "Creates and edits lab data" },
  { value: "technician", label: "Technician", hint: "Edits data; cannot sign off or manage workspaces" },
  { value: "qa_reviewer", label: "QA reviewer", hint: "Read-only; can sign off experiments" },
  { value: "external_collaborator", label: "External collaborator", hint: "Sees only what is shared with them" }
];

export function roleLabel(role: OrgRole): string {
  return ORG_ROLES.find((item) => item.value === role)?.label ?? role;
}
