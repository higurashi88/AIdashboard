import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";

import { getSettings } from "@/api/client";
import { PageError, PageLoading } from "@/components/page-state";
import { ApiKeySettings } from "@/components/settings/api-key-settings";
import { BackupSettings } from "@/components/settings/backup-settings";
import { DiscordSettings } from "@/components/settings/discord-settings";
import { NotificationSettings } from "@/components/settings/notification-settings";
import { RepositorySettings } from "@/components/settings/repository-settings";

const SECTIONS = [
  { id: "discord", label: "Discord" },
  { id: "notifications", label: "通知" },
  { id: "repositories", label: "リポジトリ" },
  { id: "api-keys", label: "APIキー" },
  { id: "backup", label: "バックアップ" },
];

export function SettingsPage() {
  // bot の状態表示を新しく保つため定期的に読み直す（フォームの入力中の値は上書きしない）
  const settings = useQuery({ queryKey: ["settings"], queryFn: getSettings, refetchInterval: 15_000 });
  if (settings.isLoading) return <PageLoading label="設定を読み込み中" />;
  if (settings.isError) return <PageError error={settings.error} retry={() => void settings.refetch()} />;
  if (!settings.data) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <p className="text-xs font-bold tracking-[0.18em] text-primary">SETTINGS</p>
        <h1 className="mt-1 text-2xl font-black tracking-tight sm:text-3xl">設定</h1>
        <p className="mt-1 text-sm text-muted-foreground">通知・監視対象・APIキー・バックアップを画面から変更します。</p>
      </div>

      <nav aria-label="設定の項目" className="flex flex-wrap gap-2">
        {SECTIONS.map((section) => (
          <a key={section.id} href={`#${section.id}`} className="rounded-full border bg-background px-3 py-1 text-xs font-medium text-muted-foreground hover:text-foreground">{section.label}</a>
        ))}
      </nav>

      <DiscordSettings settings={settings.data} />
      <NotificationSettings settings={settings.data} />
      <RepositorySettings />
      <ApiKeySettings />
      <BackupSettings settings={settings.data} />

      <div className="flex gap-3 rounded-xl border border-dashed p-4 text-sm leading-6 text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-5 shrink-0" />
        <p>
          DB のパスワード、<code className="rounded bg-muted px-1">DJANGO_SECRET_KEY</code>、許可ホスト（<code className="rounded bg-muted px-1">DJANGO_ALLOWED_HOSTS</code> / <code className="rounded bg-muted px-1">MCP_ALLOWED_*</code>）、この画面用の APIキー、レート制限は、起動とセキュリティの土台なので <code className="rounded bg-muted px-1">.env</code> で管理します（画面から壊すと画面ごと使えなくなるため）。プロジェクトの登録・編集は「PJ管理」から行えます。
        </p>
      </div>
    </div>
  );
}
