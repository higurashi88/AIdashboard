import { CheckCircle2, LoaderCircle, Save } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function SettingsSection({
  id,
  icon: Icon,
  title,
  description,
  children,
}: {
  id: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Card id={id} className="scroll-mt-24">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg font-bold"><Icon className="size-5 text-primary" />{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="text-xs leading-5 text-muted-foreground">{children}</p>;
}

export function SaveRow({
  pending,
  error,
  saved,
  disabled,
  label = "保存",
  note,
}: {
  pending: boolean;
  error?: Error | null;
  saved?: boolean;
  disabled?: boolean;
  label?: string;
  note?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-4">
      {error && <p role="alert" className="mr-auto text-sm text-destructive">{error.message}</p>}
      {!error && saved && <p className="mr-auto flex items-center gap-1.5 text-sm text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="size-4" />保存しました{note ? <span className="text-muted-foreground">　{note}</span> : null}</p>}
      <Button type="submit" disabled={pending || disabled}>
        {pending ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}{label}
      </Button>
    </div>
  );
}

export function relativeTime(value: string | null | undefined, now: number) {
  if (!value) return "—";
  const seconds = Math.max(0, Math.round((now - new Date(value).getTime()) / 1000));
  if (seconds < 60) return `${seconds}秒前`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}分前`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}時間前`;
  return `${Math.round(hours / 24)}日前`;
}
