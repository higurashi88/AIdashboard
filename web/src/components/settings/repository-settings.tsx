import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderGit2, LoaderCircle, Pencil, Plus, Save, Trash2 } from "lucide-react";

import {
  createRepository,
  deleteRepository,
  getAllProjects,
  getRepositories,
  updateRepository,
  type Project,
  type Repository,
} from "@/api/client";
import { CopyButton } from "@/components/copy-button";
import { FieldHint, SettingsSection, relativeTime } from "@/components/settings/settings-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";

type RepositoryForm = {
  path: string;
  name: string;
  project: string;
  is_active: boolean;
  sort_order: number;
};

const EMPTY_FORM: RepositoryForm = { path: "", name: "", project: "", is_active: true, sort_order: 0 };

function formFrom(repository: Repository): RepositoryForm {
  return {
    path: repository.path,
    name: repository.name,
    project: repository.project ?? "",
    is_active: repository.is_active ?? true,
    sort_order: repository.sort_order ?? 0,
  };
}

function ProjectSelect({ id, value, onChange, projects }: { id: string; value: string; onChange: (value: string) => void; projects: Project[] }) {
  return (
    <NativeSelect id={id} value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="">（ひもづけない）</option>
      {projects.map((project) => <option key={project.slug} value={project.slug}>{project.name}（{project.code}）</option>)}
    </NativeSelect>
  );
}

function RepositoryDialog({
  repository,
  open,
  onClose,
  projects,
}: {
  repository: Repository | null;
  open: boolean;
  onClose: () => void;
  projects: Project[];
}) {
  const [form, setForm] = useState<RepositoryForm>(repository ? formFrom(repository) : EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const queryClient = useQueryClient();

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["repositories"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  }

  const save = useMutation({
    mutationFn: () => {
      const body = { ...form, path: form.path.trim(), name: form.name.trim(), project: form.project || null };
      return repository ? updateRepository(repository.id, body) : createRepository(body);
    },
    onSuccess: () => { refresh(); onClose(); },
  });
  const remove = useMutation({
    mutationFn: () => deleteRepository(repository!.id),
    onSuccess: () => { refresh(); onClose(); },
  });

  const error = save.error ?? remove.error;
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{repository ? `${repository.name} を編集` : "リポジトリを追加"}</DialogTitle>
          <DialogDescription>ホストの収集スクリプト（15分ごと）が、ここに登録したフォルダの git の状態を読みに行きます。</DialogDescription>
        </DialogHeader>
        <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
          <div className="space-y-2">
            <Label htmlFor="repository-path">フォルダの絶対パス</Label>
            <Input id="repository-path" autoFocus className="font-mono" value={form.path} onChange={(event) => setForm({ ...form, path: event.target.value })} placeholder="C:\Users\you\src\my-app" />
            {repository && form.path.trim() !== repository.path && <FieldHint>パスを変えると、次の収集まで状態が空になります。</FieldHint>}
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="repository-name">表示名</Label>
              <Input id="repository-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="空欄ならフォルダ名" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="repository-project">プロジェクト</Label>
              <ProjectSelect id="repository-project" value={form.project} onChange={(project) => setForm({ ...form, project })} projects={projects} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="repository-order">並び順</Label>
              <Input id="repository-order" type="number" value={form.sort_order} onChange={(event) => setForm({ ...form, sort_order: Number(event.target.value) })} />
            </div>
            <label className="flex items-center gap-2 self-end rounded-lg border bg-muted/30 p-2.5 text-sm">
              <input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />収集する（オフでホームの一覧からも外れる）
            </label>
          </div>
          {error && <p role="alert" className="text-sm text-destructive">{error.message}</p>}
          <div className="flex flex-wrap items-center justify-between gap-3">
            {repository ? (
              confirmDelete ? (
                <div className="flex items-center gap-2">
                  <Button type="button" variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>{remove.isPending && <LoaderCircle className="size-4 animate-spin" />}本当に削除</Button>
                  <Button type="button" variant="ghost" onClick={() => setConfirmDelete(false)}>やめる</Button>
                </div>
              ) : (
                <Button type="button" variant="outline" onClick={() => setConfirmDelete(true)}><Trash2 className="size-4" />登録を削除</Button>
              )
            ) : <span />}
            <Button type="submit" disabled={!form.path.trim() || save.isPending}>{save.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}{repository ? "保存" : "追加"}</Button>
          </div>
          {repository && <FieldHint>登録を削除してもフォルダやリポジトリには何もしません（ダッシュボードの監視対象から外すだけ）。</FieldHint>}
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RepositorySettings() {
  const [editing, setEditing] = useState<Repository | null>(null);
  const [creating, setCreating] = useState(false);
  const repositories = useQuery({ queryKey: ["repositories", "all"], queryFn: getRepositories });
  const projects = useQuery({ queryKey: ["projects", "all"], queryFn: getAllProjects });
  const projectList = (projects.data ?? []).filter((project) => !project.archived_at);
  const projectNames = new Map((projects.data ?? []).map((project) => [project.slug, project.name]));
  const now = Date.now();

  return (
    <SettingsSection
      id="repositories"
      icon={FolderGit2}
      title="監視するリポジトリ"
      description={<>ホームの「リポジトリ」欄に状態を出すローカル Git リポジトリです。変更は次の収集（15分以内）から反映されます。収集はホスト側の <code className="rounded bg-muted px-1">scripts\collect_repo_status.ps1</code> が行います。</>}
    >
      <div className="space-y-4">
        {repositories.isLoading && <FieldHint>読み込み中…</FieldHint>}
        {repositories.isError && <p className="text-sm text-destructive">{repositories.error.message}</p>}
        {repositories.data && repositories.data.length === 0 && <p className="rounded-lg border border-dashed p-6 text-center text-sm text-muted-foreground">まだ登録がありません。</p>}
        <div className="divide-y rounded-lg border">
          {repositories.data?.map((repository) => (
            <div key={repository.id} className="flex items-center gap-3 p-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="truncate font-semibold">{repository.name}</p>
                  {!repository.is_active && <Badge variant="outline">収集停止</Badge>}
                  {repository.project && <Badge variant="secondary">{projectNames.get(repository.project) ?? repository.project}</Badge>}
                  {repository.status_error && <Badge variant="danger">エラー</Badge>}
                </div>
                <div className="flex items-center gap-1">
                  <p className="min-w-0 truncate font-mono text-xs text-muted-foreground" title={repository.path}>{repository.path}</p>
                  <CopyButton text={repository.path} label="パスをコピー" />
                </div>
              </div>
              <span className="hidden text-xs text-muted-foreground sm:block">収集 {relativeTime(repository.collected_at, now)}</span>
              <Button size="icon" variant="ghost" onClick={() => setEditing(repository)} aria-label={`${repository.name}を編集`}><Pencil className="size-4" /></Button>
            </div>
          ))}
        </div>
        <Button variant="outline" onClick={() => setCreating(true)}><Plus className="size-4" />リポジトリを追加</Button>
      </div>
      {creating && <RepositoryDialog repository={null} open onClose={() => setCreating(false)} projects={projectList} />}
      {editing && <RepositoryDialog key={editing.id} repository={editing} open onClose={() => setEditing(null)} projects={projectList} />}
    </SettingsSection>
  );
}
