import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeySquare, LoaderCircle, Plus } from "lucide-react";

import { createApiKey, getApiKeys, updateApiKey, type ApiKeyCreated, type ApiKeyItem, type ApiKeyScope } from "@/api/client";
import { CopyButton } from "@/components/copy-button";
import { FieldHint, SettingsSection, relativeTime } from "@/components/settings/settings-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";

const SCOPES: { value: ApiKeyScope; label: string; usage: string }[] = [
  {
    value: "mcp",
    label: "MCP（Claude Code など）",
    usage: 'claude mcp add --scope user --transport http dashboard http://127.0.0.1:8770/mcp --header "Authorization: Api-Key <キー>"',
  },
  {
    value: "pipeline",
    label: "パイプライン（ホストのスクリプト）",
    usage: "[Environment]::SetEnvironmentVariable('DASHBOARD_API_KEY_PIPELINE', '<キー>', 'User')",
  },
  {
    value: "discord",
    label: "Discord bot",
    usage: ".env の DASHBOARD_DISCORD_API_KEY=<キー> に書き、docker compose -f compose.yaml up -d discord-bot",
  },
  {
    value: "web",
    label: "画面（nginx）",
    usage: ".env の DASHBOARD_WEB_API_KEY=<キー> に書き、docker compose -f compose.yaml up -d proxy",
  },
];

const SCOPE_LABELS = new Map(SCOPES.map((scope) => [scope.value, scope.label]));

function CreatedKeyDialog({ created, onClose }: { created: ApiKeyCreated | null; onClose: () => void }) {
  if (!created) return null;
  // 既定ポート（8770）以外で動かしている場合も、開いている画面の URL に合わせる
  const origin = window.location.origin.replace("//localhost", "//127.0.0.1");
  const usage = SCOPES.find((scope) => scope.value === created.scope)?.usage
    .replace("<キー>", created.key)
    .replace("http://127.0.0.1:8770", origin);
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>APIキーを発行しました</DialogTitle>
          <DialogDescription>このキーは<strong>今だけ</strong>表示されます。閉じる前に控えてください（ダッシュボードにはハッシュしか残りません）。</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex items-center gap-1 rounded-lg border bg-muted/40 py-2 pl-3 pr-1">
            <code className="min-w-0 flex-1 break-all font-mono text-sm">{created.key}</code>
            <CopyButton text={created.key} label="キーをコピー" />
          </div>
          {usage && (
            <div className="space-y-1">
              <p className="text-sm font-semibold">使い方（{SCOPE_LABELS.get(created.scope as ApiKeyScope)}）</p>
              <div className="flex items-start gap-1 rounded-lg border bg-muted/25 py-2 pl-3 pr-1">
                <code className="min-w-0 flex-1 break-all font-mono text-xs leading-5">{usage}</code>
                <CopyButton text={usage} label="コマンドをコピー" />
              </div>
            </div>
          )}
          <div className="flex justify-end"><Button onClick={onClose}>控えたので閉じる</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function KeyRow({ apiKey }: { apiKey: ApiKeyItem }) {
  const queryClient = useQueryClient();
  const [confirm, setConfirm] = useState(false);
  const toggle = useMutation({
    mutationFn: () => updateApiKey(apiKey.id, { is_active: !apiKey.is_active }),
    onSuccess: () => { setConfirm(false); void queryClient.invalidateQueries({ queryKey: ["api-keys"] }); },
  });
  const now = Date.now();

  return (
    <div className={apiKey.is_active ? "p-3" : "p-3 opacity-60"}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold">{apiKey.name}</p>
        <Badge variant="secondary">{SCOPE_LABELS.get(apiKey.scope as ApiKeyScope) ?? apiKey.scope}</Badge>
        {apiKey.is_current && <Badge variant="default">この画面</Badge>}
        {!apiKey.is_active && <Badge variant="outline">無効</Badge>}
        <div className="ml-auto flex items-center gap-2">
          {apiKey.is_current ? null : confirm ? (
            <>
              <Button size="sm" variant="destructive" onClick={() => toggle.mutate()} disabled={toggle.isPending}>{toggle.isPending && <LoaderCircle className="size-3.5 animate-spin" />}無効にする</Button>
              <Button size="sm" variant="ghost" onClick={() => setConfirm(false)}>やめる</Button>
            </>
          ) : apiKey.is_active ? (
            <Button size="sm" variant="outline" onClick={() => setConfirm(true)}>無効化</Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => toggle.mutate()} disabled={toggle.isPending}>有効に戻す</Button>
          )}
        </div>
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        <span className="font-mono">{apiKey.prefix}…</span>　発行 {relativeTime(apiKey.created_at, now)}　最終使用 {apiKey.last_used_at ? relativeTime(apiKey.last_used_at, now) : "未使用"}
      </p>
      {confirm && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">無効にすると、このキーを使っている接続先（{SCOPE_LABELS.get(apiKey.scope as ApiKeyScope)}）はすぐに使えなくなります。</p>}
      {toggle.isError && <p className="mt-1 text-xs text-destructive">{toggle.error.message}</p>}
    </div>
  );
}

export function ApiKeySettings() {
  const [name, setName] = useState("");
  const [scope, setScope] = useState<ApiKeyScope>("mcp");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [showInactive, setShowInactive] = useState(false);
  const queryClient = useQueryClient();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: getApiKeys });

  const create = useMutation({
    mutationFn: () => createApiKey({ name: name.trim(), scope }),
    onSuccess: (next) => {
      setCreated(next);
      setName("");
      void queryClient.invalidateQueries({ queryKey: ["api-keys"] });
    },
  });

  const inactiveCount = keys.data?.filter((key) => !key.is_active).length ?? 0;
  const visible = keys.data?.filter((key) => showInactive || key.is_active) ?? [];

  return (
    <SettingsSection
      id="api-keys"
      icon={KeySquare}
      title="APIキー"
      description="ダッシュボードへ接続するためのキーです。接続先ごとに分けて発行し、使わなくなったものは無効化します。この画面が使っているキーは無効化できません。"
    >
      <div className="space-y-5">
        {keys.isLoading && <FieldHint>読み込み中…</FieldHint>}
        {keys.isError && <p className="text-sm text-destructive">{keys.error.message}</p>}
        <div className="divide-y rounded-lg border">{visible.map((apiKey) => <KeyRow key={apiKey.id} apiKey={apiKey} />)}</div>
        {inactiveCount > 0 && (
          <button type="button" className="text-xs text-primary hover:underline" onClick={() => setShowInactive(!showInactive)}>
            {showInactive ? "無効なキーを隠す" : `無効なキーも表示（${inactiveCount}件）`}
          </button>
        )}

        <form className="space-y-3 rounded-lg border bg-muted/25 p-4" onSubmit={(event) => { event.preventDefault(); create.mutate(); }}>
          <p className="text-sm font-semibold">新しいキーを発行</p>
          <div className="grid gap-3 sm:grid-cols-[1fr_16rem_auto] sm:items-end">
            <div className="space-y-2">
              <Label htmlFor="api-key-name">名前（どこで使うか）</Label>
              <Input id="api-key-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="例: ノートPCの Claude Code" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="api-key-scope">用途</Label>
              <NativeSelect id="api-key-scope" value={scope} onChange={(event) => setScope(event.target.value as ApiKeyScope)}>
                {SCOPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
              </NativeSelect>
            </div>
            <Button type="submit" disabled={!name.trim() || create.isPending}>{create.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Plus className="size-4" />}発行</Button>
          </div>
          {create.isError && <p role="alert" className="text-sm text-destructive">{create.error.message}</p>}
        </form>
      </div>
      <CreatedKeyDialog created={created} onClose={() => setCreated(null)} />
    </SettingsSection>
  );
}
