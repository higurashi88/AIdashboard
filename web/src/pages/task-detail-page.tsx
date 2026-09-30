import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CalendarClock, ChevronLeft, ChevronRight, GitBranch, LoaderCircle, Pencil, Save, Tag, Trash2 } from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { deleteTask, getTask, getTaskEvents, updateTask, type Task, type TaskActorType, type TaskPriority, type TaskStatus, type TaskUpdate } from "@/api/client";
import { AwaitingUserResponseForm } from "@/components/awaiting-user-response-form";
import { CopyButton } from "@/components/copy-button";
import { PageError, PageLoading } from "@/components/page-state";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { useProjectRootPath } from "@/hooks/use-project-root-path";
import { actorTypeLabel, priorityLabel, projectOpenCommand, statusLabel, taskActorTypes, taskPriorities, taskStatuses } from "@/lib/domain";
import { formatDateInput, formatDateTime, toIsoOrNull } from "@/lib/format";

interface EditState {
  title: string;
  detail: string;
  status: TaskStatus;
  priority: TaskPriority;
  actorType: TaskActorType;
  dueAt: string;
  tags: string;
  parent: string;
  note: string;
}

function formState(task: Task): EditState {
  return {
    title: task.title,
    detail: task.detail ?? "",
    status: task.status ?? "todo",
    priority: task.priority ?? 0,
    actorType: task.actor_type ?? "agent",
    dueAt: formatDateInput(task.due_at),
    tags: (task.tags ?? []).join(", "),
    parent: task.parent ?? "",
    note: "",
  };
}

export function TaskDetailPage() {
  const { key = "" } = useParams();
  const decodedKey = decodeURIComponent(key);
  const [searchParams, setSearchParams] = useSearchParams();
  const [editing, setEditing] = useState(searchParams.get("edit") === "1");
  const [eventPage, setEventPage] = useState(1);
  const [form, setForm] = useState<EditState | null>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const task = useQuery({ queryKey: ["task", decodedKey], queryFn: () => getTask(decodedKey), enabled: Boolean(decodedKey) });
  const events = useQuery({ queryKey: ["task-events", decodedKey, eventPage], queryFn: () => getTaskEvents(decodedKey, eventPage), enabled: Boolean(decodedKey) });
  const rootPath = useProjectRootPath(task.data?.project ?? "");

  useEffect(() => {
    if (task.data && !form) setForm(formState(task.data));
  }, [form, task.data]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
      if (event.key.toLowerCase() === "e") {
        event.preventDefault();
        setEditing(true);
        setSearchParams({ edit: "1" }, { replace: true });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setSearchParams]);

  const save = useMutation({
    mutationFn: (body: TaskUpdate) => updateTask(decodedKey, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(["task", decodedKey], updated);
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      void queryClient.invalidateQueries({ queryKey: ["task-events", decodedKey] });
      setForm(formState(updated));
      setEditing(false);
      setSearchParams({}, { replace: true });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteTask(decodedKey),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      navigate("/tasks", { replace: true });
    },
  });

  if (task.isLoading) return <PageLoading label="タスクを読み込み中" />;
  if (task.isError) return <PageError error={task.error} retry={() => void task.refetch()} />;
  if (!task.data || !form) return null;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    save.mutate({
      title: form.title.trim(),
      detail: form.detail,
      status: form.status,
      priority: form.priority,
      actor_type: form.actorType,
      due_at: toIsoOrNull(form.dueAt),
      tags: form.tags.split(",").map((tag) => tag.trim()).filter(Boolean),
      parent: form.parent.trim() || null,
      ...(form.note.trim() ? { note: form.note.trim() } : {}),
    });
  }

  function quickStatus(status: TaskStatus) {
    save.mutate({ status });
  }

  function confirmDelete() {
    if (window.confirm(`${task.data!.key} を削除します。この操作は取り消せません。`)) remove.mutate();
  }

  const totalEventPages = events.data ? Math.max(1, Math.ceil(events.data.count / 50)) : 1;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start gap-4">
        <Button asChild variant="ghost" size="sm"><Link to="/tasks"><ArrowLeft className="size-4" />一覧へ</Link></Button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="font-mono text-sm font-bold text-primary">{task.data.key}</span><StatusBadge status={task.data.status ?? "todo"} /><Badge variant="outline">{task.data.project}</Badge>{rootPath && <CopyButton text={projectOpenCommand(rootPath)} label="PJを開くコマンドをコピー" />}</div>
          <h1 className="mt-2 text-2xl font-black leading-tight tracking-tight sm:text-3xl">{task.data.title}</h1>
        </div>
        <Button variant="outline" onClick={() => { setForm(formState(task.data!)); setEditing((current) => !current); }}><Pencil className="size-4" />{editing ? "表示へ戻る" : "編集"}</Button>
      </div>

      {task.data.status === "awaiting_user" && (
        <Card className="border-amber-500/30 bg-amber-500/[0.035]">
          <CardHeader><CardTitle>判断待ちに回答</CardTitle><CardDescription>補足・条件を添えて承認または非承認を記録し、未着手へ戻します。</CardDescription></CardHeader>
          <CardContent><AwaitingUserResponseForm taskKey={task.data.key} /></CardContent>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.35fr)_minmax(22rem,.65fr)]">
        <Card>
          <CardHeader><CardTitle>{editing ? "タスクを編集" : "詳細"}</CardTitle><CardDescription>登録内容と進行状況</CardDescription></CardHeader>
          <CardContent>
            {editing ? (
              <form className="space-y-5" onSubmit={submit}>
                <div className="space-y-2"><Label htmlFor="task-title">タイトル</Label><Input id="task-title" autoFocus value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></div>
                <div className="space-y-2"><Label htmlFor="task-detail">詳細</Label><Textarea id="task-detail" value={form.detail} onChange={(event) => setForm({ ...form, detail: event.target.value })} placeholder="背景、完了条件、参考情報" /></div>
                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="space-y-2"><Label htmlFor="task-status">ステータス</Label><NativeSelect id="task-status" value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as TaskStatus })}>{taskStatuses.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</NativeSelect></div>
                  <div className="space-y-2"><Label htmlFor="task-priority">優先度</Label><NativeSelect id="task-priority" value={form.priority} onChange={(event) => setForm({ ...form, priority: Number(event.target.value) as TaskPriority })}>{taskPriorities.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</NativeSelect></div>
                  <div className="space-y-2"><Label htmlFor="task-actor-type">主体</Label><NativeSelect id="task-actor-type" value={form.actorType} onChange={(event) => setForm({ ...form, actorType: event.target.value as TaskActorType })}>{taskActorTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</NativeSelect></div>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2"><Label htmlFor="task-due">期限</Label><Input id="task-due" type="datetime-local" value={form.dueAt} onChange={(event) => setForm({ ...form, dueAt: event.target.value })} /></div>
                  <div className="space-y-2"><Label htmlFor="task-parent">親タスクのキー</Label><Input id="task-parent" value={form.parent} onChange={(event) => setForm({ ...form, parent: event.target.value })} placeholder="空欄なら親なし" /></div>
                </div>
                <div className="space-y-2"><Label htmlFor="task-tags">タグ</Label><Input id="task-tags" value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} placeholder="カンマ区切り" /></div>
                <div className="space-y-2"><Label htmlFor="task-note">更新メモ（任意）</Label><Textarea id="task-note" className="min-h-20" value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} placeholder="タイムラインに残すメモ" /></div>
                {save.isError && <p role="alert" className="text-sm text-destructive">{save.error.message}</p>}
                <div className="flex flex-wrap justify-between gap-3">
                  <Button type="button" variant="destructive" onClick={confirmDelete} disabled={remove.isPending}><Trash2 className="size-4" />削除</Button>
                  <Button type="submit" disabled={!form.title.trim() || save.isPending}>{save.isPending && <LoaderCircle className="size-4 animate-spin" />}<Save className="size-4" />保存</Button>
                </div>
              </form>
            ) : (
              <div className="space-y-6">
                <div className="rounded-lg border border-border bg-background/55 p-4"><p className="whitespace-pre-wrap text-sm leading-8">{task.data.detail || "詳細はまだありません。"}</p></div>
                <dl className="grid gap-4 text-sm sm:grid-cols-2">
                  <div><dt className="text-xs text-muted-foreground">ステータス</dt><dd className="mt-1 font-semibold">{statusLabel(task.data.status ?? "todo")}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">優先度</dt><dd className="mt-1 font-semibold">{priorityLabel(task.data.priority ?? 0)}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">主体</dt><dd className="mt-1 font-semibold">{actorTypeLabel(task.data.actor_type ?? "agent")}</dd></div>
                  <div><dt className="flex items-center gap-1 text-xs text-muted-foreground"><CalendarClock className="size-3" />期限</dt><dd className="mt-1">{formatDateTime(task.data.due_at)}</dd></div>
                  <div><dt className="flex items-center gap-1 text-xs text-muted-foreground"><GitBranch className="size-3" />親タスク</dt><dd className="mt-1">{task.data.parent ? <Link className="font-mono text-primary hover:underline" to={`/tasks/${encodeURIComponent(task.data.parent)}`}>{task.data.parent}</Link> : "—"}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">作成</dt><dd className="mt-1">{formatDateTime(task.data.created_at)} · {task.data.created_by}</dd></div>
                  <div><dt className="text-xs text-muted-foreground">更新</dt><dd className="mt-1">{formatDateTime(task.data.updated_at)}</dd></div>
                </dl>
                <div><p className="mb-2 flex items-center gap-1 text-xs text-muted-foreground"><Tag className="size-3" />タグ</p><div className="flex flex-wrap gap-2">{(task.data.tags ?? []).length ? (task.data.tags ?? []).map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>) : <span className="text-sm text-muted-foreground">なし</span>}</div></div>
                <div className="border-t border-border pt-5"><p className="mb-3 text-xs font-semibold text-muted-foreground">ステータスを変更</p><div className="flex flex-wrap gap-2">{taskStatuses.map((item) => <Button key={item.value} size="sm" variant={item.value === task.data!.status ? "default" : "outline"} disabled={save.isPending || item.value === task.data!.status} onClick={() => quickStatus(item.value)}>{item.label}</Button>)}</div></div>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>タイムライン</CardTitle><CardDescription>更新イベントとメモ</CardDescription></CardHeader>
          <CardContent>
            {events.isLoading ? <PageLoading label="履歴を読み込み中" /> : events.isError ? <PageError error={events.error} retry={() => void events.refetch()} /> : (
              <>
                <ol className="relative ml-2 border-l border-border">
                  {events.data?.results.map((event) => (
                    <li key={event.id} className="relative pb-6 pl-6 last:pb-0"><span className="absolute -left-1 top-2 size-2 rounded-full bg-primary ring-4 ring-card" /><div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{event.event_type}</Badge><span className="text-xs text-muted-foreground">{event.actor}</span></div><p className="mt-2 whitespace-pre-wrap text-sm leading-7">{event.body || "更新"}</p><time className="mt-1 block text-xs text-muted-foreground" dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time></li>
                  ))}
                </ol>
                {events.data?.results.length === 0 && <p className="text-sm text-muted-foreground">イベントはありません。</p>}
                {totalEventPages > 1 && <div className="mt-6 flex items-center justify-between border-t pt-4"><span className="text-xs text-muted-foreground">{eventPage} / {totalEventPages}</span><div className="flex gap-2"><Button size="icon" variant="outline" disabled={eventPage <= 1} onClick={() => setEventPage((value) => value - 1)}><ChevronLeft className="size-4" /></Button><Button size="icon" variant="outline" disabled={eventPage >= totalEventPages} onClick={() => setEventPage((value) => value + 1)}><ChevronRight className="size-4" /></Button></div></div>}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
