import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing } from "lucide-react";

import { getAllProjects, updateSettings, type AppSettings } from "@/api/client";
import { FieldHint, SaveRow, SettingsSection } from "@/components/settings/settings-section";

type NotificationForm = AppSettings["notifications"];

const KINDS: { field: "awaiting_user" | "failed_runs" | "daily_summary"; label: string; description: string }[] = [
  { field: "awaiting_user", label: "判断待ち", description: "タスクが「本人待ち」になったとき、判断事項のメモと一緒に" },
  { field: "failed_runs", label: "自動実行の失敗", description: "自動実行が失敗で終わったとき、要約とログのパスと一緒に" },
  { field: "daily_summary", label: "朝のまとめ", description: "毎朝、判断待ちの一覧・PJ別の件数・直近24時間の自動実行" },
];

function sameProjects(a: string[], b: string[]) {
  return a.length === b.length && [...a].sort().join("\n") === [...b].sort().join("\n");
}

export function NotificationSettings({ settings }: { settings: AppSettings }) {
  const [form, setForm] = useState<NotificationForm>(settings.notifications);
  const [saved, setSaved] = useState(false);
  const queryClient = useQueryClient();
  const projects = useQuery({ queryKey: ["projects", "all"], queryFn: getAllProjects });

  const current = settings.notifications;
  const dirty = KINDS.some(({ field }) => form[field] !== current[field]) || !sameProjects(form.projects, current.projects);

  const save = useMutation({
    mutationFn: () => updateSettings({ notifications: form }),
    onSuccess: (next) => {
      queryClient.setQueryData(["settings"], next);
      setForm(next.notifications);
      setSaved(true);
    },
  });

  function change(next: NotificationForm) {
    setSaved(false);
    setForm(next);
  }

  function toggleProject(slug: string, checked: boolean) {
    change({ ...form, projects: checked ? [...form.projects, slug] : form.projects.filter((item) => item !== slug) });
  }

  const visibleProjects = (projects.data ?? []).filter(
    (project) => (project.is_active && !project.archived_at) || form.projects.includes(project.slug),
  );

  return (
    <SettingsSection id="notifications" icon={BellRing} title="通知の種類と対象" description="Discord に送る通知を種類ごとに切り替え、対象のプロジェクトを絞り込みます。">
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <div className="grid gap-3 md:grid-cols-3">
          {KINDS.map(({ field, label, description }) => (
            <label key={field} className="flex cursor-pointer gap-3 rounded-lg border bg-muted/25 p-4 has-[:checked]:border-primary/50 has-[:checked]:bg-primary/5">
              <input type="checkbox" className="mt-1" checked={form[field]} onChange={(event) => change({ ...form, [field]: event.target.checked })} />
              <span><span className="block text-sm font-semibold">{label}</span><span className="block text-xs leading-5 text-muted-foreground">{description}</span></span>
            </label>
          ))}
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap items-baseline gap-2">
            <p className="text-sm font-semibold">対象のプロジェクト</p>
            <span className="text-xs text-muted-foreground">{form.projects.length === 0 ? "すべてのプロジェクトを通知します" : `${form.projects.length}件だけ通知します`}</span>
            {form.projects.length > 0 && <button type="button" className="text-xs text-primary hover:underline" onClick={() => change({ ...form, projects: [] })}>すべてに戻す</button>}
          </div>
          {projects.isLoading && <FieldHint>プロジェクトを読み込み中…</FieldHint>}
          {projects.isError && <p className="text-sm text-destructive">{projects.error.message}</p>}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {visibleProjects.map((project) => (
              <label key={project.slug} className="flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm has-[:checked]:border-primary/50">
                <input type="checkbox" checked={form.projects.includes(project.slug)} onChange={(event) => toggleProject(project.slug, event.target.checked)} />
                <span className="size-2.5 shrink-0 rounded-full" style={{ backgroundColor: project.color }} />
                <span className="min-w-0 truncate">{project.name}</span>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">{project.code}</span>
              </label>
            ))}
          </div>
          <FieldHint>1つも選ばなければ全プロジェクトが対象です（新しく登録したPJも自動で含まれます）。朝のまとめも選んだPJだけに絞ります。</FieldHint>
        </div>

        <SaveRow pending={save.isPending} error={save.error} saved={saved && !dirty} disabled={!dirty} note="15秒ほどで bot に反映されます" />
      </form>
    </SettingsSection>
  );
}
