import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BotMessageSquare, KeyRound, LoaderCircle, Send, Trash2, Undo2 } from "lucide-react";

import { getSettings, requestDiscordTest, updateSettings, type AppSettings, type AppSettingsUpdate, type DiscordStatus } from "@/api/client";
import { FieldHint, SaveRow, SettingsSection, relativeTime } from "@/components/settings/settings-section";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type BadgeVariant = "default" | "secondary" | "outline" | "warning" | "success" | "danger";

const STATE_LABELS: Record<string, { label: string; variant: BadgeVariant }> = {
  unknown: { label: "bot から報告なし", variant: "secondary" },
  waiting_config: { label: "設定待ち", variant: "warning" },
  connecting: { label: "接続中…", variant: "secondary" },
  connected: { label: "接続済み", variant: "success" },
  login_failed: { label: "トークンが無効", variant: "danger" },
  channel_error: { label: "チャンネルに投稿できない", variant: "danger" },
  error: { label: "エラー", variant: "danger" },
};

// bot は15秒ごとに状態を報告する。これより古ければ止まっているとみなす。
const STALE_STATUS_MS = 90_000;
// テスト送信の結果をこれ以上待っても来なければ、bot が動いていない
const TEST_TIMEOUT_MS = 60_000;

type DiscordForm = {
  channel_id: string;
  mention_user_id: string;
  daily_summary_time: string;
  poll_interval_sec: number;
};

type TokenMode = "keep" | "replace" | "clear";

function formFrom(settings: AppSettings): DiscordForm {
  const { channel_id, mention_user_id, daily_summary_time, poll_interval_sec } = settings.discord;
  return { channel_id, mention_user_id, daily_summary_time, poll_interval_sec };
}

function StatusPanel({ status, now }: { status: DiscordStatus; now: number }) {
  const reportedAt = status.reported_at ? new Date(status.reported_at).getTime() : null;
  const stale = status.state !== "unknown" && reportedAt !== null && now - reportedAt > STALE_STATUS_MS;
  const shown = stale ? { label: "bot から応答なし", variant: "warning" as const } : STATE_LABELS[status.state] ?? { label: status.state, variant: "outline" as const };

  return (
    <div className="space-y-2 rounded-lg border bg-muted/30 p-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-semibold">bot の状態</span>
        <Badge variant={shown.variant}>{shown.label}</Badge>
        {status.bot_user && <span className="font-mono text-xs text-muted-foreground">{status.bot_user}</span>}
        <span className="ml-auto text-xs text-muted-foreground">最終報告 {relativeTime(status.reported_at, now)}</span>
      </div>
      {status.detail && !stale && <p className="leading-6 text-muted-foreground">{status.detail}</p>}
      {(stale || status.state === "unknown") && (
        <p className="leading-6 text-muted-foreground">
          discord-bot が動いていない可能性があります。<code className="rounded bg-muted px-1">.env</code> に <code className="rounded bg-muted px-1">COMPOSE_PROFILES=discord</code> と <code className="rounded bg-muted px-1">DASHBOARD_DISCORD_API_KEY</code> があるか確認し、<code className="rounded bg-muted px-1">docker compose -f compose.yaml up -d --build discord-bot</code> で起動してください。
        </p>
      )}
    </div>
  );
}

function TestSend({ status, now }: { status: DiscordStatus; now: number }) {
  const [pending, setPending] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const waiting = pending !== null && status.test_handled_at !== pending;
  const timedOut = waiting && now - new Date(pending).getTime() > TEST_TIMEOUT_MS;

  // 結果が届くまで速めに読み直す
  useQuery({ queryKey: ["settings"], queryFn: getSettings, refetchInterval: 3_000, enabled: waiting && !timedOut });

  const request = useMutation({
    mutationFn: requestDiscordTest,
    onSuccess: (next) => {
      setPending(next.test_requested_at ?? null);
      queryClient.setQueryData<AppSettings>(["settings"], (current) => current && { ...current, discord_status: next });
    },
  });

  const finished = pending !== null && status.test_handled_at === pending;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button type="button" variant="outline" onClick={() => request.mutate()} disabled={request.isPending || (waiting && !timedOut)}>
        {request.isPending || (waiting && !timedOut) ? <LoaderCircle className="size-4 animate-spin" /> : <Send className="size-4" />}テスト送信
      </Button>
      <p className="text-sm" role="status">
        {request.isError && <span className="text-destructive">{request.error.message}</span>}
        {waiting && !timedOut && <span className="text-muted-foreground">bot に依頼しました。15秒ほどで Discord に届きます…</span>}
        {timedOut && <span className="text-amber-700 dark:text-amber-300">bot から応答がありません。bot の状態を確認してください。</span>}
        {finished && !status.test_error && <span className="text-emerald-700 dark:text-emerald-300">送信しました。Discord のチャンネルを確認してください。</span>}
        {finished && status.test_error && <span className="text-destructive">{status.test_error}</span>}
      </p>
    </div>
  );
}

export function DiscordSettings({ settings }: { settings: AppSettings }) {
  const [form, setForm] = useState<DiscordForm>(() => formFrom(settings));
  const [tokenMode, setTokenMode] = useState<TokenMode>(settings.discord.bot_token_set ? "keep" : "replace");
  const [token, setToken] = useState("");
  const [saved, setSaved] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const queryClient = useQueryClient();

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 5_000);
    return () => window.clearInterval(timer);
  }, []);

  const current = formFrom(settings);
  const changes: NonNullable<AppSettingsUpdate["discord"]> = {};
  (Object.keys(form) as (keyof DiscordForm)[]).forEach((field) => {
    if (form[field] !== current[field]) Object.assign(changes, { [field]: form[field] });
  });
  if (tokenMode === "replace" && token.trim()) changes.bot_token = token.trim();
  if (tokenMode === "clear" && settings.discord.bot_token_set) changes.bot_token = "";
  const dirty = Object.keys(changes).length > 0;

  const save = useMutation({
    mutationFn: () => updateSettings({ discord: changes }),
    onSuccess: (next) => {
      queryClient.setQueryData(["settings"], next);
      setForm(formFrom(next));
      setToken("");
      setTokenMode(next.discord.bot_token_set ? "keep" : "replace");
      setSaved(true);
    },
  });

  function update<K extends keyof DiscordForm>(field: K, value: DiscordForm[K]) {
    setSaved(false);
    setForm({ ...form, [field]: value });
  }

  return (
    <SettingsSection
      id="discord"
      icon={BotMessageSquare}
      title="Discord bot"
      description={<>判断待ち・自動実行の失敗・朝のまとめを投稿する bot の接続先です。保存すると15秒ほどで bot に反映され、作り直しは要りません。Discord 側の bot の作り方は <code className="rounded bg-muted px-1">docs/discord-setup.md</code> を参照してください。</>}
    >
      <div className="space-y-5">
        <StatusPanel status={settings.discord_status} now={now} />
        <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
          <div className="space-y-2">
            <Label htmlFor="discord-token" className="flex items-center gap-1.5"><KeyRound className="size-4" />Bot トークン</Label>
            {tokenMode === "keep" ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="flex h-10 flex-1 items-center rounded-md border bg-muted/40 px-3 font-mono text-sm text-muted-foreground">設定済み（末尾 …{settings.discord.bot_token_hint}）</p>
                <Button type="button" variant="outline" onClick={() => { setSaved(false); setTokenMode("replace"); }}>入れ直す</Button>
                <Button type="button" variant="ghost" onClick={() => { setSaved(false); setTokenMode("clear"); }}><Trash2 className="size-4" />削除</Button>
              </div>
            ) : tokenMode === "clear" ? (
              <div className="flex flex-wrap items-center gap-2">
                <p className="flex h-10 flex-1 items-center rounded-md border border-destructive/40 bg-destructive/5 px-3 text-sm text-destructive">保存するとトークンを削除し、bot は Discord から切断します</p>
                <Button type="button" variant="ghost" onClick={() => setTokenMode("keep")}><Undo2 className="size-4" />取り消し</Button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <Input id="discord-token" type="password" autoComplete="off" className="flex-1 font-mono" value={token} onChange={(event) => { setSaved(false); setToken(event.target.value); }} placeholder="Developer Portal の Bot → Reset Token で発行した値" />
                {settings.discord.bot_token_set && <Button type="button" variant="ghost" onClick={() => { setToken(""); setTokenMode("keep"); }}><Undo2 className="size-4" />取り消し</Button>}
              </div>
            )}
            <FieldHint>保存後は画面に表示されません（末尾4文字だけ表示）。変えると bot が新しいトークンで接続し直します。</FieldHint>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="discord-channel">通知チャンネル ID</Label>
              <Input id="discord-channel" inputMode="numeric" className="font-mono" value={form.channel_id} onChange={(event) => update("channel_id", event.target.value.trim())} placeholder="123456789012345678" />
              <FieldHint>Discord の開発者モードをオンにし、チャンネルを右クリック →「チャンネルIDをコピー」。</FieldHint>
            </div>
            <div className="space-y-2">
              <Label htmlFor="discord-mention">メンションするユーザー ID（任意）</Label>
              <Input id="discord-mention" inputMode="numeric" className="font-mono" value={form.mention_user_id} onChange={(event) => update("mention_user_id", event.target.value.trim())} placeholder="空欄ならメンションしない" />
              <FieldHint>判断待ちと失敗の通知で自分をメンションし、スマホに確実に通知を届けます。</FieldHint>
            </div>
            <div className="space-y-2">
              <Label htmlFor="discord-summary-time">朝のまとめの時刻</Label>
              <Input id="discord-summary-time" type="time" value={form.daily_summary_time} onChange={(event) => update("daily_summary_time", event.target.value)} />
              <FieldHint>タイムゾーンは {settings.time_zone}。</FieldHint>
            </div>
            <div className="space-y-2">
              <Label htmlFor="discord-interval">確認間隔（秒）</Label>
              <Input id="discord-interval" type="number" min={10} max={3600} value={form.poll_interval_sec} onChange={(event) => update("poll_interval_sec", Number(event.target.value))} />
              <FieldHint>判断待ちと失敗を確認する間隔。10〜3600秒。</FieldHint>
            </div>
          </div>

          <SaveRow pending={save.isPending} error={save.error} saved={saved && !dirty} disabled={!dirty} note="15秒ほどで bot に反映されます" />
        </form>
        <div className="space-y-2 border-t pt-4">
          <p className="text-sm font-semibold">動作確認</p>
          <FieldHint>保存済みの設定で、通知チャンネルにテストメッセージを1件送ります。</FieldHint>
          <TestSend status={settings.discord_status} now={now} />
        </div>
      </div>
    </SettingsSection>
  );
}
