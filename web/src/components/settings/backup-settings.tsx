import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DatabaseBackup } from "lucide-react";

import { updateSettings, type AppSettings } from "@/api/client";
import { FieldHint, SaveRow, SettingsSection } from "@/components/settings/settings-section";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function BackupSettings({ settings }: { settings: AppSettings }) {
  const [keep, setKeep] = useState(settings.backup.keep);
  const [saved, setSaved] = useState(false);
  const queryClient = useQueryClient();
  const dirty = keep !== settings.backup.keep;

  const save = useMutation({
    mutationFn: () => updateSettings({ backup: { keep } }),
    onSuccess: (next) => {
      queryClient.setQueryData(["settings"], next);
      setKeep(next.backup.keep);
      setSaved(true);
    },
  });

  return (
    <SettingsSection
      id="backup"
      icon={DatabaseBackup}
      title="バックアップ"
      description={<>毎日のバックアップ（<code className="rounded bg-muted px-1">scripts\backup.ps1</code>）が残す世代数です。これより古いダンプは削除されます。</>}
    >
      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <div className="max-w-xs space-y-2">
          <Label htmlFor="backup-keep">保持する世代数</Label>
          <Input id="backup-keep" type="number" min={1} max={365} value={keep} onChange={(event) => { setSaved(false); setKeep(Number(event.target.value)); }} />
          <FieldHint>1〜365。日次実行なら「日数」と同じです。次回のバックアップから反映されます（-Keep を付けて手動実行したときはその値が優先）。</FieldHint>
        </div>
        <SaveRow pending={save.isPending} error={save.error} saved={saved && !dirty} disabled={!dirty} note="次回のバックアップから反映されます" />
      </form>
    </SettingsSection>
  );
}
