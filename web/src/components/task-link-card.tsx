import type { ReactNode } from "react";
import { ArrowUpRight, Clock3, Folder } from "lucide-react";
import { Link } from "react-router-dom";

import type { Task } from "@/api/client";
import { CopyButton } from "@/components/copy-button";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { useProjectRootPath } from "@/hooks/use-project-root-path";
import { projectOpenCommand } from "@/lib/domain";
import { formatDateTime } from "@/lib/format";

function TaskLinkCardContent({ task, showStatus }: { task: Task; showStatus: boolean }) {
  return (
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs font-semibold text-primary">{task.key}</span>
          {showStatus && task.status && <StatusBadge status={task.status} />}
          {task.actor_type === "human" && <Badge variant="outline">人間が対応</Badge>}
          {(task.priority ?? 0) > 0 && <Badge variant={task.priority === 3 ? "danger" : "outline"}>優先度 {task.priority}</Badge>}
        </div>
        <p className="font-semibold leading-7 text-foreground">{task.title}</p>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><Folder className="size-3" />{task.project}</span>
          <span className="flex items-center gap-1"><Clock3 className="size-3" />{formatDateTime(task.updated_at)}</span>
        </div>
      </div>
      <ArrowUpRight className="mt-1 size-4 shrink-0 text-muted-foreground transition group-hover:text-primary" />
    </div>
  );
}

export function TaskLinkCard({ task, showStatus = false, children }: { task: Task; showStatus?: boolean; children?: ReactNode }) {
  const to = `/tasks/${encodeURIComponent(task.key)}`;
  const rootPath = useProjectRootPath(task.project);

  return (
    <div className="rounded-lg border border-border bg-background/65 transition hover:-translate-y-0.5 hover:border-primary/45 hover:shadow-md">
      <Link to={to} className="group block p-4"><TaskLinkCardContent task={task} showStatus={showStatus} /></Link>
      {rootPath && (
        <div className="flex items-center gap-2 border-t border-border px-4 py-2">
          <p className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground" title={rootPath}>{rootPath}</p>
          <CopyButton text={projectOpenCommand(rootPath)} label="PJを開くコマンドをコピー" />
        </div>
      )}
      {children && <div className="border-t border-border p-4">{children}</div>}
    </div>
  );
}
