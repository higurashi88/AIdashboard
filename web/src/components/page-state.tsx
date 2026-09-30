import { AlertTriangle, LoaderCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

export function PageLoading({ label = "読み込み中" }: { label?: string }) {
  return <div className="grid min-h-64 place-items-center text-sm text-muted-foreground"><span className="flex items-center gap-2"><LoaderCircle className="size-5 animate-spin text-primary" />{label}</span></div>;
}

export function PageError({ error, retry }: { error: Error; retry?: () => void }) {
  return (
    <div className="grid min-h-64 place-items-center">
      <div className="max-w-md rounded-xl border border-destructive/25 bg-destructive/5 p-6 text-center">
        <AlertTriangle className="mx-auto mb-3 size-7 text-destructive" />
        <p className="font-semibold">データを読み込めませんでした</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{error.message}</p>
        {retry && <Button className="mt-4" variant="outline" onClick={retry}><RefreshCw className="size-4" />再試行</Button>}
      </div>
    </div>
  );
}
