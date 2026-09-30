import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArchiveRestore, ChevronLeft, ChevronRight, FolderPlus, LoaderCircle, Pencil, Pin, Save } from "lucide-react";
import { Link } from "react-router-dom";

import { createProject, getProjects, updateProject, type Project, type ProjectCreate, type ProjectUpdate } from "@/api/client";
import { CopyButton } from "@/components/copy-button";
import { PageError, PageLoading } from "@/components/page-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

function slugSuggestion(name: string) {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 64);
}

function codeSuggestion(name: string, slug: string) {
  return (slug || name).replace(/[^a-z0-9]/gi, "").toUpperCase().slice(0, 8);
}

function RootPathCopy({ rootPath }: { rootPath: string }) {
  return (
    <div className="mt-3 flex items-center gap-1 rounded bg-muted/45 py-1 pl-3 pr-1">
      <p className="min-w-0 flex-1 truncate font-mono text-xs text-muted-foreground" title={rootPath}>{rootPath}</p>
      <CopyButton text={rootPath} label="ルートパスをコピー" />
    </div>
  );
}

function ProjectCreateDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [name, setName] = useState("");
  const [rootPath, setRootPath] = useState("");
  const [slug, setSlug] = useState("");
  const [code, setCode] = useState("");
  const [customSlug, setCustomSlug] = useState(false);
  const [customCode, setCustomCode] = useState(false);
  const [created, setCreated] = useState<Project | null>(null);
  const queryClient = useQueryClient();

  const suggestedSlug = slugSuggestion(name);
  const suggestedCode = codeSuggestion(name, customSlug ? slug : suggestedSlug);
  useEffect(() => { if (!customSlug) setSlug(suggestedSlug); }, [customSlug, suggestedSlug]);
  useEffect(() => { if (!customCode) setCode(suggestedCode); }, [customCode, suggestedCode]);

  const create = useMutation({
    mutationFn: (body: ProjectCreate) => createProject(body),
    onSuccess: (project) => {
      setCreated(project);
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  function resetAndClose() {
    setName(""); setRootPath(""); setSlug(""); setCode(""); setCustomSlug(false); setCustomCode(false); setCreated(null);
    onOpenChange(false);
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    create.mutate({
      name: name.trim(),
      root_path: rootPath.trim(),
      ...(customSlug && slug ? { slug } : {}),
      ...(customCode && code ? { code } : {}),
    });
  }

  return (
    <Dialog open={open} onOpenChange={(next) => next ? onOpenChange(true) : resetAndClose()}>
      <DialogContent>
        {created ? (
          <>
            <DialogHeader><DialogTitle>プロジェクトを登録しました</DialogTitle><DialogDescription>自動生成された識別子です。タスクはこのコードで採番されます。</DialogDescription></DialogHeader>
            <dl className="grid gap-3 rounded-lg border bg-muted/40 p-4 text-sm"><div><dt className="text-xs text-muted-foreground">slug</dt><dd className="font-mono font-bold">{created.slug}</dd></div><div><dt className="text-xs text-muted-foreground">code</dt><dd className="font-mono font-bold">{created.code}</dd></div></dl>
            <div className="flex justify-end gap-2"><Button asChild variant="outline"><Link to={`/tasks?project=${encodeURIComponent(created.slug)}`}>タスクを見る</Link></Button><Button onClick={resetAndClose}>完了</Button></div>
          </>
        ) : (
          <>
            <DialogHeader><DialogTitle className="flex items-center gap-2"><FolderPlus className="size-5 text-primary" />新しいプロジェクト</DialogTitle><DialogDescription>名前とルートパスだけで登録できます。識別子は自動生成されます。</DialogDescription></DialogHeader>
            <form className="space-y-5" onSubmit={submit}>
              <div className="space-y-2"><Label htmlFor="project-name">名前</Label><Input id="project-name" autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="My App" /></div>
              <div className="space-y-2"><Label htmlFor="project-root">ルートパス</Label><Input id="project-root" value={rootPath} onChange={(event) => setRootPath(event.target.value)} placeholder="プロジェクトのルートディレクトリ" /></div>
              <details className="rounded-lg border border-border bg-muted/25 p-4">
                <summary className="cursor-pointer text-sm font-semibold">識別子を確認・編集</summary>
                <p className="mt-2 text-xs leading-5 text-muted-foreground">空欄のままならサーバーが重複しない値を採番します。日本語名だけの場合も自動採番されます。</p>
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2"><Label htmlFor="project-slug">slug</Label><Input id="project-slug" value={slug} onChange={(event) => { setCustomSlug(true); setSlug(event.target.value.toLowerCase()); }} placeholder="自動採番（pj-XX）" /><button type="button" className="text-xs text-primary hover:underline" onClick={() => setCustomSlug(false)}>自動に戻す</button></div>
                  <div className="space-y-2"><Label htmlFor="project-code">code</Label><Input id="project-code" maxLength={12} value={code} onChange={(event) => { setCustomCode(true); setCode(event.target.value.toUpperCase()); }} placeholder="自動採番（PJXX）" /><button type="button" className="text-xs text-primary hover:underline" onClick={() => setCustomCode(false)}>自動に戻す</button></div>
                </div>
              </details>
              {create.isError && <p role="alert" className="text-sm text-destructive">{create.error.message}</p>}
              <div className="flex justify-end gap-2"><Button type="button" variant="ghost" onClick={resetAndClose}>キャンセル</Button><Button type="submit" disabled={!name.trim() || !rootPath.trim() || create.isPending}>{create.isPending && <LoaderCircle className="size-4 animate-spin" />}登録</Button></div>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ProjectEditDialog({ project, onClose }: { project: Project | null; onClose: () => void }) {
  const [form, setForm] = useState<ProjectUpdate>({});
  const queryClient = useQueryClient();
  useEffect(() => {
    if (project) setForm({ name: project.name, root_path: project.root_path, summary: project.summary, is_active: project.is_active, is_pinned: project.is_pinned, sort_order: project.sort_order, color: project.color });
  }, [project]);

  const update = useMutation({
    mutationFn: (body: ProjectUpdate) => updateProject(project!.slug, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["projects"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      onClose();
    },
  });

  if (!project) return null;
  function submit(event: React.FormEvent) { event.preventDefault(); update.mutate(form); }
  function toggleArchive() { update.mutate({ archived_at: project!.archived_at ? null : new Date().toISOString() }); }

  return (
    <Dialog open={Boolean(project)} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{project.name} を編集</DialogTitle><DialogDescription><span className="font-mono">{project.slug} / {project.code}</span> はタスクキーの整合性を保つため登録後は変更できません。</DialogDescription></DialogHeader>
        <form className="space-y-5" onSubmit={submit}>
          <div className="space-y-2"><Label htmlFor="edit-project-name">名前</Label><Input id="edit-project-name" value={String(form.name ?? "")} onChange={(event) => setForm({ ...form, name: event.target.value })} /></div>
          <div className="space-y-2"><Label htmlFor="edit-project-root">ルートパス</Label><Input id="edit-project-root" value={String(form.root_path ?? "")} onChange={(event) => setForm({ ...form, root_path: event.target.value })} /></div>
          <div className="space-y-2"><Label htmlFor="edit-project-summary">概要</Label><Textarea id="edit-project-summary" className="min-h-24" value={String(form.summary ?? "")} onChange={(event) => setForm({ ...form, summary: event.target.value })} /></div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="edit-project-color">カラー</Label><div className="flex gap-2"><Input id="edit-project-color" type="color" className="w-14 p-1" value={String(form.color ?? "#64748B")} onChange={(event) => setForm({ ...form, color: event.target.value })} /><Input value={String(form.color ?? "")} onChange={(event) => setForm({ ...form, color: event.target.value })} /></div></div>
            <div className="space-y-2"><Label htmlFor="edit-project-order">並び順</Label><Input id="edit-project-order" type="number" value={Number(form.sort_order ?? 0)} onChange={(event) => setForm({ ...form, sort_order: Number(event.target.value) })} /></div>
          </div>
          <div className="flex flex-wrap gap-5 rounded-lg border bg-muted/30 p-4 text-sm"><label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(form.is_active)} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />有効</label><label className="flex items-center gap-2"><input type="checkbox" checked={Boolean(form.is_pinned)} onChange={(event) => setForm({ ...form, is_pinned: event.target.checked })} />ピン留め</label></div>
          {update.isError && <p role="alert" className="text-sm text-destructive">{update.error.message}</p>}
          <div className="flex flex-wrap justify-between gap-3"><Button type="button" variant="outline" onClick={toggleArchive} disabled={update.isPending}>{project.archived_at ? <ArchiveRestore className="size-4" /> : <Archive className="size-4" />}{project.archived_at ? "アーカイブ解除" : "アーカイブ"}</Button><Button type="submit" disabled={!String(form.name ?? "").trim() || !String(form.root_path ?? "").trim() || update.isPending}>{update.isPending && <LoaderCircle className="size-4 animate-spin" />}<Save className="size-4" />保存</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ProjectsPage() {
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<Project | null>(null);
  const projects = useQuery({ queryKey: ["projects", page], queryFn: () => getProjects(page) });
  if (projects.isLoading) return <PageLoading label="プロジェクトを読み込み中" />;
  if (projects.isError) return <PageError error={projects.error} retry={() => void projects.refetch()} />;
  if (!projects.data) return null;
  const totalPages = Math.max(1, Math.ceil(projects.data.count / 50));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><p className="text-xs font-bold tracking-[0.18em] text-primary">PROJECT DIRECTORY</p><h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">PJ管理</h1><p className="mt-1 text-sm text-muted-foreground">登録、運用状態、表示順を管理します</p></div>
        <Button onClick={() => setCreateOpen(true)}><FolderPlus className="size-4" />新規PJ</Button>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {projects.data.results.map((project) => (
          <Card key={project.slug} className={project.archived_at ? "border-dashed opacity-60" : ""}>
            <CardContent className="pt-5">
              <div className="flex items-start gap-3"><span className="mt-1 size-3 shrink-0 rounded-full" style={{ backgroundColor: project.color }} /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><h2 className="truncate font-bold">{project.name}</h2>{project.is_pinned && <Pin className="size-3.5 text-primary" />}{project.archived_at && <Badge variant="outline">アーカイブ</Badge>}{!project.is_active && !project.archived_at && <Badge variant="warning">停止中</Badge>}</div><p className="font-mono text-xs text-muted-foreground">{project.slug} / {project.code}</p></div><Button size="icon" variant="ghost" onClick={() => setEditing(project)} aria-label={`${project.name}を編集`}><Pencil className="size-4" /></Button></div>
              <p className="mt-4 min-h-12 text-sm leading-6 text-muted-foreground">{project.summary || "概要は未設定です。"}</p>
              <RootPathCopy rootPath={project.root_path} />
              <dl className="mt-4 grid grid-cols-3 gap-2 border-t pt-4 text-center"><div><dt className="text-[11px] text-muted-foreground">未処理</dt><dd className="font-bold tabular-nums">{project.open_tasks ?? 0}</dd></div><div><dt className="text-[11px] text-muted-foreground">判断待ち</dt><dd className="font-bold tabular-nums text-amber-600 dark:text-amber-300">{project.awaiting_user ?? 0}</dd></div><div><dt className="text-[11px] text-muted-foreground">作業中</dt><dd className="font-bold tabular-nums text-primary">{project.in_progress ?? 0}</dd></div></dl>
              <Button asChild className="mt-4 w-full" variant="outline" size="sm"><Link to={`/tasks?project=${encodeURIComponent(project.slug)}`}>タスクを見る</Link></Button>
            </CardContent>
          </Card>
        ))}
      </div>
      {projects.data.results.length === 0 && <p className="rounded-xl border border-dashed p-10 text-center text-sm text-muted-foreground">プロジェクトはまだありません。</p>}

      <div className="flex items-center justify-between"><p className="text-sm text-muted-foreground">{projects.data.count} PJ · {page} / {totalPages} ページ</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}><ChevronLeft className="size-4" />前へ</Button><Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((value) => value + 1)}>次へ<ChevronRight className="size-4" /></Button></div></div>
      <ProjectCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
      <ProjectEditDialog project={editing} onClose={() => setEditing(null)} />
    </div>
  );
}
