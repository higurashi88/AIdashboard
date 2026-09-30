import { useQuery } from "@tanstack/react-query";
import { Activity, Bot, CheckCircle2, ChevronDown, CircleAlert, Clock3, FolderKanban, GitBranch, PauseCircle, Pin, PlayCircle, UserRound } from "lucide-react";
import { Link } from "react-router-dom";

import { getDashboardSummary, type DashboardSummary } from "@/api/client";
import { AwaitingUserResponseForm } from "@/components/awaiting-user-response-form";
import { PageError, PageLoading } from "@/components/page-state";
import { TaskLinkCard } from "@/components/task-link-card";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { formatDateTime, formatDuration } from "@/lib/format";
import { cn } from "@/lib/utils";

function SectionHeading({ number, title, count, icon: Icon }: { number: string; title: string; count?: number; icon: React.ComponentType<{ className?: string }>; }) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-xs font-bold tracking-widest text-primary">{number}</span>
      <Icon className="size-5 text-muted-foreground" />
      <h2 className="text-lg font-bold tracking-tight">{title}</h2>
      {count !== undefined && <Badge variant="outline" className="ml-auto tabular-nums">{count}件</Badge>}
    </div>
  );
}

function AutomationRows({ automations }: { automations: DashboardSummary["automations"] }) {
  return (
    <div className="divide-y divide-border">
      {automations.map((automation) => (
        <div key={automation.key} className="grid gap-2 py-3 first:pt-0 last:pb-0 md:grid-cols-[minmax(15rem,1fr)_minmax(9rem,.6fr)_minmax(12rem,.8fr)] md:items-center">
          <div className="min-w-0">
            <p className="truncate font-semibold">{automation.name}</p>
            <p className="truncate font-mono text-xs text-muted-foreground">{automation.key}</p>
          </div>
          <p className="text-sm text-muted-foreground">{automation.schedule || "スケジュールなし"}</p>
          <div className="text-sm">
            {automation.last_run ? (
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={automation.last_run.status === "succeeded" ? "success" : automation.last_run.status === "failed" ? "danger" : "default"}>{automation.last_run.status}</Badge>
                <span className="text-muted-foreground">{formatDateTime(automation.last_run.started_at)} · {formatDuration(automation.last_run.duration_sec)}</span>
              </div>
            ) : <span className="text-muted-foreground">実行記録なし</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

type Repository = DashboardSummary["repositories"][number];

// 収集スクリプトは15分ごと。2回分以上届いていなければ、止まっている可能性がある。
const STALE_COLLECTION_MS = 45 * 60 * 1000;

function repositoryFlags(repository: Repository, now: number) {
  const flags: { label: string; variant: "warning" | "danger" | "outline" }[] = [];
  if (repository.status_error) return [{ label: "エラー", variant: "danger" as const }];
  const dirty = (repository.changed_files ?? 0) + (repository.untracked_files ?? 0);
  if (dirty > 0) flags.push({ label: `未コミット ${dirty}`, variant: "warning" });
  if ((repository.ahead ?? 0) > 0) flags.push({ label: `未push ${repository.ahead}`, variant: "warning" });
  if ((repository.behind ?? 0) > 0) flags.push({ label: `遅れ ${repository.behind}`, variant: "outline" });
  if (!repository.upstream && repository.collected_at) flags.push({ label: "追跡ブランチなし", variant: "outline" });
  if (!repository.collected_at) flags.push({ label: "未収集", variant: "outline" });
  else if (now - new Date(repository.collected_at).getTime() > STALE_COLLECTION_MS) flags.push({ label: "収集が古い", variant: "outline" });
  return flags;
}

function RepositoryRows({ repositories, projects }: { repositories: Repository[]; projects: DashboardSummary["projects"] }) {
  const now = Date.now();
  const projectNames = new Map(projects.map((project) => [project.slug, project.name]));
  return (
    <div className="divide-y divide-border">
      {repositories.map((repository) => {
        const flags = repositoryFlags(repository, now);
        return (
          <div key={repository.path} className="grid gap-2 py-3 first:pt-0 last:pb-0 md:grid-cols-[minmax(14rem,1fr)_minmax(12rem,.9fr)_minmax(14rem,1.1fr)] md:items-center">
            <div className="min-w-0">
              <p className="truncate font-semibold">{repository.name}</p>
              <p className="truncate text-xs text-muted-foreground">
                {repository.project ? projectNames.get(repository.project) ?? repository.project : "PJなし"}
                <span className="font-mono"> · {repository.path}</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {repository.branch && <span className="inline-flex items-center gap-1 font-mono text-xs"><GitBranch className="size-3.5 text-muted-foreground" />{repository.branch}</span>}
              {flags.length ? flags.map((flag) => <Badge key={flag.label} variant={flag.variant}>{flag.label}</Badge>) : <Badge variant="success">同期済み</Badge>}
            </div>
            <div className="min-w-0 text-sm">
              {repository.status_error ? (
                <p className="truncate text-red-700 dark:text-red-300" title={repository.status_error}>{repository.status_error}</p>
              ) : (
                <>
                  <p className="truncate" title={repository.last_commit_subject}>{repository.last_commit_subject || "コミットなし"}</p>
                  <p className="text-xs text-muted-foreground">最終コミット {formatDateTime(repository.last_commit_at)}</p>
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ProjectCards({ projects }: { projects: DashboardSummary["projects"] }) {
  const visible = projects.slice(0, 8);
  const hidden = projects.slice(8);
  const render = (project: DashboardSummary["projects"][number]) => (
    <Link
      key={project.slug}
      to={`/tasks?project=${encodeURIComponent(project.slug)}`}
      className={cn(
        "group rounded-lg border border-border bg-background/60 p-4 transition hover:border-primary/40",
        project.is_stale && "opacity-55 grayscale",
        !project.is_active && "border-dashed",
      )}
    >
      <div className="flex items-start gap-3">
        <span className="mt-1 size-2.5 shrink-0 rounded-full" style={{ backgroundColor: project.color }} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate font-bold">{project.name}</p>
            {project.is_pinned && <Pin className="size-3.5 text-primary" />}
            {!project.is_active && <Badge variant="outline">停止中</Badge>}
          </div>
          <p className="mt-0.5 font-mono text-xs text-muted-foreground">{project.code}</p>
        </div>
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-2 text-center">
        <div><dt className="text-[11px] text-muted-foreground">未処理</dt><dd className="mt-0.5 text-lg font-bold tabular-nums">{project.open_tasks}</dd></div>
        <div><dt className="text-[11px] text-muted-foreground">判断待ち</dt><dd className="mt-0.5 text-lg font-bold tabular-nums text-amber-600 dark:text-amber-300">{project.awaiting_user}</dd></div>
        <div><dt className="text-[11px] text-muted-foreground">作業中</dt><dd className="mt-0.5 text-lg font-bold tabular-nums text-primary">{project.in_progress}</dd></div>
      </dl>
      <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground"><Clock3 className="size-3" />最終更新 {formatDateTime(project.last_activity_at)}</p>
    </Link>
  );

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{visible.map(render)}</div>
      {hidden.length > 0 && (
        <details className="group mt-3">
          <summary className="flex cursor-pointer list-none items-center justify-center gap-2 rounded-lg border border-dashed border-border py-3 text-sm font-medium text-muted-foreground hover:text-foreground">
            残り {hidden.length} PJを表示 <ChevronDown className="size-4 transition group-open:rotate-180" />
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{hidden.map(render)}</div>
        </details>
      )}
    </>
  );
}

export function DashboardPage() {
  const summary = useQuery({ queryKey: ["dashboard"], queryFn: getDashboardSummary });
  if (summary.isLoading) return <PageLoading label="ホームを読み込み中" />;
  if (summary.isError) return <PageError error={summary.error} retry={() => void summary.refetch()} />;
  if (!summary.data) return null;

  const activeAutomations = summary.data.automations.filter((item) => item.state === "active");
  const inactiveAutomations = summary.data.automations.filter((item) => item.state !== "active");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs font-bold tracking-[0.18em] text-primary">TODAY&apos;S CONTROL DESK</p>
          <h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">全体の状況</h1>
          <p className="mt-1 text-sm text-muted-foreground">30秒ごとに自動更新 · {new Intl.DateTimeFormat("ja-JP", { dateStyle: "long" }).format(new Date())}</p>
        </div>
      </div>

      <Card className="border-amber-500/30 bg-amber-500/[0.035]">
        <CardHeader><SectionHeading number="01" title="あなたの判断待ち" count={summary.data.awaiting_user.length} icon={CircleAlert} /></CardHeader>
        <CardContent>
          {summary.data.awaiting_user.length === 0 ? (
            <div className="flex items-center gap-3 rounded-lg border border-dashed border-emerald-500/30 bg-emerald-500/5 px-4 py-5 text-sm text-emerald-700 dark:text-emerald-300">
              <CheckCircle2 className="size-5" />判断待ちはありません
            </div>
          ) : (
            <div className="grid gap-3 lg:grid-cols-2">{summary.data.awaiting_user.map((task) => <TaskLinkCard key={task.key} task={task}><AwaitingUserResponseForm taskKey={task.key} /></TaskLinkCard>)}</div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><SectionHeading number="02" title="人間が対応するタスク" count={summary.data.human_tasks.length} icon={UserRound} /><CardDescription>自動実行の対象外。あなたが主体で進めるタスク</CardDescription></CardHeader>
        <CardContent>
          {summary.data.human_tasks.length ? <div className="grid gap-3 lg:grid-cols-2">{summary.data.human_tasks.map((task) => <TaskLinkCard key={task.key} task={task} showStatus />)}</div> : <p className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">人間が対応するタスクはありません。</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><SectionHeading number="03" title="作業中" count={summary.data.in_progress.length} icon={PlayCircle} /></CardHeader>
        <CardContent>
          {summary.data.in_progress.length ? <div className="grid gap-3 lg:grid-cols-2">{summary.data.in_progress.map((task) => <TaskLinkCard key={task.key} task={task} />)}</div> : <p className="rounded-lg border border-dashed p-5 text-sm text-muted-foreground">現在作業中のタスクはありません。</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><SectionHeading number="04" title="自動実行" icon={Bot} /><CardDescription>稼働中の定義と直近の実行結果</CardDescription></CardHeader>
        <CardContent>
          {activeAutomations.length ? <AutomationRows automations={activeAutomations} /> : <p className="text-sm text-muted-foreground">稼働中の自動実行はありません。</p>}
          {inactiveAutomations.length > 0 && (
            <details className="group mt-4 border-t border-border pt-4">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-muted-foreground"><PauseCircle className="size-4" />停止中 {inactiveAutomations.length}件<ChevronDown className="ml-auto size-4 transition group-open:rotate-180" /></summary>
              <div className="mt-4"><AutomationRows automations={inactiveAutomations} /></div>
            </details>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <SectionHeading number="05" title="リポジトリ" count={summary.data.repositories.length} icon={GitBranch} />
          <CardDescription>
            ローカルの Git の状態（15分ごとに収集 · 最終 {formatDateTime(summary.data.repositories.map((item) => item.collected_at).filter(Boolean).sort().at(-1))}）
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summary.data.repositories.length ? <RepositoryRows repositories={summary.data.repositories} projects={summary.data.projects} /> : <p className="text-sm text-muted-foreground">登録済みのリポジトリはありません（config/projects.toml の [[repository]]）。</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><SectionHeading number="06" title="PJ別サマリ" count={summary.data.projects.length} icon={FolderKanban} /><CardDescription>ピン留め、未処理あり、設定した並び順で表示</CardDescription></CardHeader>
        <CardContent><ProjectCards projects={summary.data.projects} /></CardContent>
      </Card>

      <Card>
        <CardHeader><SectionHeading number="07" title="最近の動き" count={summary.data.recent_activity.length} icon={Activity} /></CardHeader>
        <CardContent>
          {summary.data.recent_activity.length ? (
            <ol className="relative ml-2 border-l border-border">
              {summary.data.recent_activity.slice(0, 10).map((item, index) => (
                <li key={`${item.at}-${item.task_key ?? index}`} className="relative pb-5 pl-6 last:pb-0">
                  <span className="absolute -left-1 top-2 size-2 rounded-full bg-primary ring-4 ring-card" />
                  <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <p className="font-medium leading-7">{item.body}</p>
                    {item.task_key && <Link className="font-mono text-xs text-primary hover:underline" to={`/tasks/${encodeURIComponent(item.task_key)}`}>{item.task_key}</Link>}
                  </div>
                  <p className="text-xs text-muted-foreground">{formatDateTime(item.at)} · {item.project} · {item.actor}</p>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted-foreground">最近の活動はありません。</p>}
        </CardContent>
      </Card>
    </div>
  );
}
