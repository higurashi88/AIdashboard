import { Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { DashboardPage } from "@/pages/dashboard-page";
import { ProjectsPage } from "@/pages/projects-page";
import { SettingsPage } from "@/pages/settings-page";
import { TaskDetailPage } from "@/pages/task-detail-page";
import { TasksPage } from "@/pages/tasks-page";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="tasks" element={<TasksPage />} />
        <Route path="tasks/:key" element={<TaskDetailPage />} />
        <Route path="projects" element={<ProjectsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
