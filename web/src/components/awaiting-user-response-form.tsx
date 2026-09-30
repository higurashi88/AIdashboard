import { useId, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";

import { updateTask, type TaskUpdate } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

type Decision = "approve" | "reject";

export function AwaitingUserResponseForm({ taskKey }: { taskKey: string }) {
  const answerId = useId();
  const [note, setNote] = useState("");
  const queryClient = useQueryClient();
  const respond = useMutation({
    mutationFn: ({ decision, supplement }: { decision: Decision; supplement: string }) => {
      const prefix = decision === "approve" ? "【承認】" : "【非承認】";
      const body: TaskUpdate = { note: supplement ? `${prefix}\n${supplement}` : prefix, status: "todo" };
      return updateTask(taskKey, body);
    },
    onSuccess: async () => {
      setNote("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["dashboard"] }),
        queryClient.invalidateQueries({ queryKey: ["tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["task", taskKey] }),
        queryClient.invalidateQueries({ queryKey: ["task-events", taskKey] }),
      ]);
    },
  });

  function submitDecision(decision: Decision) {
    if (respond.isPending) return;
    respond.mutate({ decision, supplement: note.trim() });
  }

  const isApproving = respond.isPending && respond.variables?.decision === "approve";
  const isRejecting = respond.isPending && respond.variables?.decision === "reject";

  return (
    <form className="space-y-3" aria-busy={respond.isPending} onSubmit={(event) => event.preventDefault()}>
      <div className="space-y-2">
        <Label htmlFor={answerId}>補足・条件（任意）</Label>
        <Textarea id={answerId} className="min-h-24" value={note} disabled={respond.isPending} onChange={(event) => setNote(event.target.value)} placeholder="補足・条件があれば入力（任意）" />
      </div>
      {respond.isError && <p role="alert" className="text-sm text-destructive">{respond.error.message}</p>}
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" disabled={respond.isPending} onClick={() => submitDecision("reject")}>{isRejecting && <LoaderCircle className="size-4 animate-spin" />}{isRejecting ? "非承認を送信中" : "承認しない"}</Button>
        <Button type="button" disabled={respond.isPending} onClick={() => submitDecision("approve")}>{isApproving && <LoaderCircle className="size-4 animate-spin" />}{isApproving ? "承認を送信中" : "承認する"}</Button>
      </div>
    </form>
  );
}
