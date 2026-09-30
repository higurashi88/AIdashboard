import type { TaskActorType, TaskPriority, TaskStatus } from "@/api/client";

export const taskStatuses = [
  { value: "backlog", label: "バックログ" },
  { value: "todo", label: "未着手" },
  { value: "in_progress", label: "作業中" },
  { value: "awaiting_user", label: "判断待ち" },
  { value: "blocked", label: "ブロック中" },
  { value: "done", label: "完了" },
  { value: "cancelled", label: "キャンセル" },
] as const satisfies ReadonlyArray<{ value: TaskStatus; label: string }>;

export const taskPriorities = [
  { value: 0, label: "なし" },
  { value: 1, label: "低" },
  { value: 2, label: "中" },
  { value: 3, label: "高" },
] as const satisfies ReadonlyArray<{ value: TaskPriority; label: string }>;

export const taskActorTypes = [
  { value: "agent", label: "AI（自動実行の対象）" },
  { value: "human", label: "人間が対応" },
] as const satisfies ReadonlyArray<{ value: TaskActorType; label: string }>;

export const taskOrderings = [
  { value: "-priority", label: "優先度（高い順）" },
  { value: "priority", label: "優先度（低い順）" },
  { value: "-updated_at", label: "更新（新しい順）" },
  { value: "updated_at", label: "更新（古い順）" },
  { value: "-created_at", label: "作成（新しい順）" },
  { value: "created_at", label: "作成（古い順）" },
] as const;

export function statusLabel(status: string) {
  return taskStatuses.find((item) => item.value === status)?.label ?? status;
}

export function priorityLabel(priority: number) {
  return taskPriorities.find((item) => item.value === priority)?.label ?? String(priority);
}

export function actorTypeLabel(actorType: string) {
  return taskActorTypes.find((item) => item.value === actorType)?.label ?? actorType;
}

export function projectOpenCommand(rootPath: string) {
  return `cd "${rootPath}"; claude`;
}

export function statusTone(status: string) {
  if (status === "awaiting_user") return "warning" as const;
  if (status === "done") return "success" as const;
  if (status === "blocked" || status === "cancelled") return "danger" as const;
  if (status === "in_progress") return "default" as const;
  return "secondary" as const;
}
