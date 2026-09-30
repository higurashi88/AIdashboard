import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { createTask, getAllProjects } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";

interface NewTaskDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NewTaskDialog({ open, onOpenChange }: NewTaskDialogProps) {
  const [project, setProject] = useState("");
  const [title, setTitle] = useState("");
  const [isHumanTask, setIsHumanTask] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const projects = useQuery({
    queryKey: ["projects", "all"],
    queryFn: getAllProjects,
    enabled: open,
    refetchInterval: false,
  });
  const availableProjects = projects.data?.filter((item) => !item.archived_at) ?? [];

  useEffect(() => {
    if (!project && availableProjects[0]) setProject(availableProjects[0].slug);
  }, [availableProjects, project]);

  const create = useMutation({
    mutationFn: () => createTask({ project, title, actor_type: isHumanTask ? "human" : "agent" }),
    onSuccess: (task) => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
      setTitle("");
      setIsHumanTask(false);
      onOpenChange(false);
      navigate(`/tasks/${encodeURIComponent(task.key)}`);
    },
  });

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (project && title.trim()) create.mutate();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Plus className="size-5 text-primary" />新しいタスク</DialogTitle>
          <DialogDescription>PJとタイトルだけで登録できます。詳細はあとから追加できます。</DialogDescription>
        </DialogHeader>
        <form className="space-y-5" onSubmit={submit}>
          <div className="space-y-2">
            <Label htmlFor="new-task-project">プロジェクト</Label>
            <NativeSelect
              id="new-task-project"
              value={project}
              onChange={(event) => setProject(event.target.value)}
              disabled={projects.isLoading || create.isPending}
            >
              {availableProjects.map((item) => <option key={item.slug} value={item.slug}>{item.name}{item.is_active ? "" : "（停止中）"}</option>)}
            </NativeSelect>
            {projects.isError && <p className="text-sm text-destructive">プロジェクトを取得できませんでした。</p>}
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-task-title">タイトル</Label>
            <Input
              id="new-task-title"
              autoFocus
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="次に進めること"
              disabled={create.isPending}
            />
          </div>
          <label className="flex cursor-pointer items-center gap-2 rounded-lg border bg-muted/30 p-4 text-sm">
            <input type="checkbox" checked={isHumanTask} onChange={(event) => setIsHumanTask(event.target.checked)} disabled={create.isPending} />
            人間が対応する（自動実行の対象外）
          </label>
          {create.isError && <p role="alert" className="text-sm text-destructive">{create.error.message}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>キャンセル</Button>
            <Button type="submit" disabled={!project || !title.trim() || create.isPending}>
              {create.isPending && <LoaderCircle className="size-4 animate-spin" />}
              登録
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
