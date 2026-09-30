import { useEffect, useState } from "react";
import { FolderKanban, Home, ListTodo, Moon, Plus, Settings, Sun } from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { NewTaskDialog } from "@/components/new-task-dialog";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/use-theme";
import { cn } from "@/lib/utils";

const navigation = [
  { to: "/", label: "ホーム", icon: Home, end: true },
  { to: "/tasks", label: "タスク", icon: ListTodo },
  { to: "/projects", label: "PJ管理", icon: FolderKanban },
  { to: "/settings", label: "設定", icon: Settings },
];

function isTypingTarget(target: EventTarget | null) {
  return target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || (target instanceof HTMLElement && target.isContentEditable);
}

export function AppShell() {
  const [newTaskOpen, setNewTaskOpen] = useState(false);
  const { theme, toggleTheme } = useTheme();
  const navigate = useNavigate();

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key.toLowerCase() === "n") {
        event.preventDefault();
        setNewTaskOpen(true);
      }
      if (event.key === "/") {
        event.preventDefault();
        navigate("/tasks");
        window.setTimeout(() => document.querySelector<HTMLInputElement>("#task-search")?.focus(), 0);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [navigate]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-3 px-4 sm:px-6">
          <NavLink to="/" className="mr-auto flex min-w-0 items-center gap-3">
            <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary text-sm font-black text-primary-foreground shadow-lg shadow-primary/20">AI</span>
            <span className="hidden min-w-0 sm:block">
              <span className="block truncate text-sm font-bold tracking-wide">AIdashboard</span>
              <span className="block text-[11px] tracking-[0.16em] text-muted-foreground">PROJECT CONTROL DESK</span>
            </span>
          </NavLink>

          <nav aria-label="メインナビゲーション" className="flex items-center rounded-lg bg-muted/65 p-1">
            {navigation.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) => cn(
                  "flex h-9 items-center gap-2 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground",
                  isActive && "bg-background text-foreground shadow-sm",
                )}
              >
                <Icon className="size-4" />
                <span className="hidden md:inline">{label}</span>
              </NavLink>
            ))}
          </nav>

          <Button size="sm" onClick={() => setNewTaskOpen(true)}>
            <Plus className="size-4" /><span className="hidden sm:inline">新規</span><kbd className="hidden rounded border border-primary-foreground/30 px-1 text-[10px] lg:inline">N</kbd>
          </Button>
          <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label={theme === "dark" ? "ライトモードに切り替え" : "ダークモードに切り替え"}>
            {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
        </div>
      </header>
      <main className="mx-auto max-w-[1500px] px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
      <NewTaskDialog open={newTaskOpen} onOpenChange={setNewTaskOpen} />
    </div>
  );
}
