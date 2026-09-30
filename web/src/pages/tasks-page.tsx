import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Filter, Search } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { getAllProjects, getTasks, updateTask, type Task, type TaskListQuery, type TaskStatus } from "@/api/client";
import { PageError, PageLoading } from "@/components/page-state";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { priorityLabel, taskOrderings, taskStatuses } from "@/lib/domain";
import { formatDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const allTaskStatuses = taskStatuses.map((status) => status.value).join(",");

function isTypingTarget(target: EventTarget | null) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement;
}

function InlineStatus({ task }: { task: Task }) {
  const queryClient = useQueryClient();
  const update = useMutation({
    mutationFn: (status: TaskStatus) => updateTask(task.key, { status }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["task", task.key] });
    },
  });

  return (
    <NativeSelect
      aria-label={`${task.key}のステータス`}
      className="h-8 min-w-32 text-xs"
      value={task.status ?? "todo"}
      disabled={update.isPending}
      onClick={(event) => event.stopPropagation()}
      onChange={(event) => update.mutate(event.target.value as TaskStatus)}
    >
      {taskStatuses.map((status) => <option key={status.value} value={status.value}>{status.label}</option>)}
    </NativeSelect>
  );
}

export function TasksPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const [selected, setSelected] = useState(0);
  const query = params.get("q") ?? "";
  const [draftQuery, setDraftQuery] = useState(query);
  const project = params.get("project") ?? "";
  const statuses = (params.get("status") ?? "").split(",").filter(Boolean);
  const showAll = params.get("all") === "1";
  const statusParam = statuses.length > 0 ? statuses.join(",") : showAll ? allTaskStatuses : "";
  const ordering = params.get("ordering") ?? "-priority";
  const page = Math.max(1, Number(params.get("page") || 1));

  const projects = useQuery({ queryKey: ["projects", "all"], queryFn: getAllProjects });
  const taskQuery = useMemo<TaskListQuery>(() => ({
    ...(project ? { project } : {}),
    ...(statusParam ? { status: statusParam } : {}),
    ...(query ? { q: query } : {}),
    ordering: ordering as TaskListQuery["ordering"],
    page,
  }), [ordering, page, project, query, statusParam]);
  const tasks = useQuery({ queryKey: ["tasks", taskQuery], queryFn: () => getTasks(taskQuery) });

  function updateParams(next: Record<string, string | null>, resetPage = true) {
    const updated = new URLSearchParams(params);
    Object.entries(next).forEach(([key, value]) => value ? updated.set(key, value) : updated.delete(key));
    if (resetPage) updated.delete("page");
    setParams(updated);
  }

  useEffect(() => setSelected(0), [tasks.data]);
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey || !tasks.data?.results.length) return;
      if (event.key.toLowerCase() === "j") {
        event.preventDefault();
        setSelected((current) => Math.min(current + 1, tasks.data!.results.length - 1));
      }
      if (event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSelected((current) => Math.max(current - 1, 0));
      }
      if (event.key.toLowerCase() === "e") {
        event.preventDefault();
        const task = tasks.data.results[selected];
        if (task) navigate(`/tasks/${encodeURIComponent(task.key)}?edit=1`);
      }
      if (event.key === "Enter") {
        const task = tasks.data.results[selected];
        if (task) navigate(`/tasks/${encodeURIComponent(task.key)}`);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate, selected, tasks.data]);

  if (tasks.isLoading) return <PageLoading label="タスクを読み込み中" />;
  if (tasks.isError) return <PageError error={tasks.error} retry={() => void tasks.refetch()} />;
  if (!tasks.data) return null;
  const totalPages = Math.max(1, Math.ceil(tasks.data.count / 50));

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-bold tracking-[0.18em] text-primary">TASK REGISTER</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div><h1 className="text-2xl font-black tracking-tight sm:text-3xl">タスク一覧</h1><p className="mt-1 text-sm text-muted-foreground">J / K で移動 · E で編集 · Enter で開く</p></div>
          <Badge variant="outline" className="text-sm tabular-nums">{tasks.data.count}件</Badge>
        </div>
      </div>

      <Card>
        <CardContent className="pt-5">
          <div className="grid gap-3 lg:grid-cols-[minmax(15rem,1fr)_minmax(10rem,.55fr)_auto_minmax(11rem,.55fr)]">
            <form
              className="relative"
              onSubmit={(event) => { event.preventDefault(); updateParams({ q: draftQuery }); }}
            >
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input id="task-search" className="pl-9" value={draftQuery} onChange={(event) => setDraftQuery(event.target.value)} placeholder="タイトルを検索  /" />
            </form>
            <NativeSelect aria-label="プロジェクトで絞り込み" value={project} onChange={(event) => updateParams({ project: event.target.value })}>
              <option value="">すべてのPJ</option>
              {projects.data?.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}
            </NativeSelect>
            <details className="relative">
              <summary className="flex h-10 cursor-pointer list-none items-center gap-2 rounded-md border border-input bg-background px-3 text-sm"><Filter className="size-4" />ステータス{statuses.length > 0 && <Badge>{statuses.length}</Badge>}</summary>
              <div className="absolute right-0 z-20 mt-2 grid min-w-72 gap-2 rounded-lg border border-border bg-card p-3 shadow-xl">
                {taskStatuses.map((status) => (
                  <label key={status.value} className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-sm hover:bg-muted">
                    <input
                      type="checkbox"
                      checked={statuses.includes(status.value)}
                      onChange={(event) => {
                        const next = event.target.checked ? [...statuses, status.value] : statuses.filter((value) => value !== status.value);
                        updateParams({ status: next.join(",") });
                      }}
                    />
                    {status.label}
                  </label>
                ))}
                <label className={cn("mt-1 flex items-start gap-2 border-t border-border px-1 pt-3 text-sm", statuses.length > 0 ? "cursor-not-allowed text-muted-foreground" : "cursor-pointer")}>
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={showAll}
                    disabled={statuses.length > 0}
                    onChange={(event) => updateParams({ all: event.target.checked ? "1" : null })}
                  />
                  <span>すべて表示（完了・キャンセル・バックログも含む）</span>
                </label>
              </div>
            </details>
            <NativeSelect aria-label="並び順" value={ordering} onChange={(event) => updateParams({ ordering: event.target.value })}>
              {taskOrderings.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </NativeSelect>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            {statuses.length > 0
              ? "選択したステータスのみ表示中（すべて表示は個別選択の解除後に適用）"
              : showAll
                ? "すべてのステータスを表示中"
                : "未完了のタスクを表示中です（完了・キャンセル・バックログは非表示）"}
          </p>
          {(project || statuses.length || query || showAll) && (
            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
              <span className="text-muted-foreground">絞り込み:</span>
              {project && <Badge variant="outline">PJ {project}</Badge>}
              {statuses.map((status) => <StatusBadge key={status} status={status} />)}
              {query && <Badge variant="outline">「{query}」</Badge>}
              <button className="ml-1 text-primary hover:underline" onClick={() => { setDraftQuery(""); setParams({}); }}>すべて解除</button>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <div className="hidden grid-cols-[minmax(9rem,.45fr)_minmax(20rem,1.5fr)_minmax(9rem,.55fr)_8rem_9rem] gap-4 border-b bg-muted/40 px-4 py-2 text-xs font-semibold text-muted-foreground md:grid">
          <span>キー / PJ</span><span>タイトル</span><span>ステータス</span><span>優先度</span><span>更新</span>
        </div>
        {tasks.data.results.length === 0 ? (
          <p className="p-10 text-center text-sm text-muted-foreground">条件に合うタスクはありません。</p>
        ) : tasks.data.results.map((task, index) => (
          <div
            key={task.key}
            onMouseEnter={() => setSelected(index)}
            className={cn(
              "grid gap-3 border-b border-border px-4 py-4 last:border-b-0 md:grid-cols-[minmax(9rem,.45fr)_minmax(20rem,1.5fr)_minmax(9rem,.55fr)_8rem_9rem] md:items-center md:gap-4",
              selected === index && "bg-primary/[0.055] ring-1 ring-inset ring-primary/25",
            )}
          >
            <div className="min-w-0"><Link className="font-mono text-xs font-bold text-primary hover:underline" to={`/tasks/${encodeURIComponent(task.key)}`}>{task.key}</Link><p className="truncate text-xs text-muted-foreground">{task.project}</p></div>
            <div className="min-w-0"><Link className="font-semibold leading-7 hover:text-primary" to={`/tasks/${encodeURIComponent(task.key)}`}>{task.title}</Link>{(task.tags ?? []).length > 0 || task.actor_type === "human" ? <div className="mt-1 flex flex-wrap gap-1">{task.actor_type === "human" && <Badge variant="outline">人間が対応</Badge>}{(task.tags ?? []).slice(0, 3).map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>)}</div> : null}</div>
            <div className="flex items-center gap-2 md:block"><span className="md:hidden"><StatusBadge status={task.status ?? "todo"} /></span><InlineStatus task={task} /></div>
            <div><span className={cn("text-sm", task.priority === 3 && "font-bold text-destructive")}>{priorityLabel(task.priority ?? 0)}</span></div>
            <time className="text-xs text-muted-foreground" dateTime={task.updated_at}>{formatDateTime(task.updated_at)}</time>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{page} / {totalPages} ページ</p>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => updateParams({ page: String(page - 1) }, false)}><ChevronLeft className="size-4" />前へ</Button>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => updateParams({ page: String(page + 1) }, false)}>次へ<ChevronRight className="size-4" /></Button>
        </div>
      </div>
    </div>
  );
}
