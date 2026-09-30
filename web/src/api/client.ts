import createClient from "openapi-fetch";

import type { paths } from "@/api/schema";

const client = createClient<paths>({ baseUrl: "" });

export type DashboardSummary = paths["/api/v1/dashboard/summary/"]["get"]["responses"][200]["content"]["application/json"];
export type ProjectPage = paths["/api/v1/projects/"]["get"]["responses"][200]["content"]["application/json"];
export type Project = ProjectPage["results"][number];
export type ProjectCreate = NonNullable<paths["/api/v1/projects/"]["post"]["requestBody"]>["content"]["application/json"];
export type ProjectUpdate = NonNullable<paths["/api/v1/projects/{slug}/"]["patch"]["requestBody"]>["content"]["application/json"];
export type TaskPage = paths["/api/v1/tasks/"]["get"]["responses"][200]["content"]["application/json"];
export type Task = TaskPage["results"][number];
export type TaskStatus = NonNullable<Task["status"]>;
export type TaskPriority = NonNullable<Task["priority"]>;
export type TaskActorType = NonNullable<Task["actor_type"]>;
export type TaskCreate = NonNullable<paths["/api/v1/tasks/"]["post"]["requestBody"]>["content"]["application/json"];
export type TaskUpdate = NonNullable<paths["/api/v1/tasks/{key}/"]["patch"]["requestBody"]>["content"]["application/json"];
export type TaskEventPage = paths["/api/v1/tasks/{key}/events/"]["get"]["responses"][200]["content"]["application/json"];
export type TaskEvent = TaskEventPage["results"][number];
export type TaskListQuery = NonNullable<paths["/api/v1/tasks/"]["get"]["parameters"]["query"]>;
export type AppSettings = paths["/api/v1/settings/"]["get"]["responses"][200]["content"]["application/json"];
export type AppSettingsUpdate = NonNullable<paths["/api/v1/settings/"]["patch"]["requestBody"]>["content"]["application/json"];
export type DiscordStatus = AppSettings["discord_status"];
export type ApiKeyItem = paths["/api/v1/api-keys/"]["get"]["responses"][200]["content"]["application/json"][number];
export type ApiKeyCreate = NonNullable<paths["/api/v1/api-keys/"]["post"]["requestBody"]>["content"]["application/json"];
export type ApiKeyCreated = paths["/api/v1/api-keys/"]["post"]["responses"][201]["content"]["application/json"];
export type ApiKeyScope = ApiKeyCreate["scope"];
export type Repository = paths["/api/v1/repositories/"]["get"]["responses"][200]["content"]["application/json"][number];
export type RepositoryCreate = NonNullable<paths["/api/v1/repositories/"]["post"]["requestBody"]>["content"]["application/json"];
export type RepositoryUpdate = NonNullable<paths["/api/v1/repositories/{repository_id}/"]["patch"]["requestBody"]>["content"]["application/json"];

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
    readonly errors?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// {"errors": {"discord": {"channel_id": ["..."]}}} のような入れ子から、入力エラーの文面を集める
function fieldMessages(errors: unknown): string[] {
  if (typeof errors === "string") return [errors];
  if (Array.isArray(errors)) return errors.flatMap(fieldMessages);
  if (typeof errors === "object" && errors !== null) return Object.values(errors).flatMap(fieldMessages);
  return [];
}

function errorMessage(error: unknown, fallback: string) {
  if (typeof error === "object" && error !== null && "detail" in error) {
    const { detail, errors } = error as { detail?: unknown; errors?: unknown };
    const messages = fieldMessages(errors);
    if (detail === "Validation failed." && messages.length > 0) return messages.slice(0, 3).join(" / ");
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

function assertData<T>(data: T | undefined, error: unknown, status: number, fallback: string): T {
  if (data !== undefined) return data;
  throw new ApiError(errorMessage(error, fallback), status, error);
}

export async function getDashboardSummary() {
  const { data, error, response } = await client.GET("/api/v1/dashboard/summary/");
  return assertData(data, error, response.status, "ダッシュボードを取得できませんでした。");
}

export async function getProjects(page = 1) {
  const { data, error, response } = await client.GET("/api/v1/projects/", {
    params: { query: { page } },
  });
  return assertData(data, error, response.status, "プロジェクトを取得できませんでした。");
}

export async function getAllProjects() {
  const first = await getProjects(1);
  const projects = [...first.results];
  let page = 2;
  while (projects.length < first.count) {
    const next = await getProjects(page);
    projects.push(...next.results);
    if (!next.next || next.results.length === 0) break;
    page += 1;
  }
  return projects;
}

export async function createProject(body: ProjectCreate) {
  const { data, error, response } = await client.POST("/api/v1/projects/", { body });
  return assertData(data, error, response.status, "プロジェクトを登録できませんでした。");
}

export async function updateProject(slug: string, body: ProjectUpdate) {
  const { data, error, response } = await client.PATCH("/api/v1/projects/{slug}/", {
    params: { path: { slug } },
    body,
  });
  return assertData(data, error, response.status, "プロジェクトを更新できませんでした。");
}

export async function getTasks(query: TaskListQuery = {}) {
  const { data, error, response } = await client.GET("/api/v1/tasks/", {
    params: { query },
  });
  return assertData(data, error, response.status, "タスクを取得できませんでした。");
}

export async function getTask(key: string) {
  const { data, error, response } = await client.GET("/api/v1/tasks/{key}/", {
    params: { path: { key } },
  });
  return assertData(data, error, response.status, "タスクを取得できませんでした。");
}

export async function createTask(body: TaskCreate) {
  const { data, error, response } = await client.POST("/api/v1/tasks/", { body });
  return assertData(data, error, response.status, "タスクを登録できませんでした。");
}

export async function updateTask(key: string, body: TaskUpdate) {
  const { data, error, response } = await client.PATCH("/api/v1/tasks/{key}/", {
    params: { path: { key } },
    body,
  });
  return assertData(data, error, response.status, "タスクを更新できませんでした。");
}

export async function deleteTask(key: string) {
  const { error, response } = await client.DELETE("/api/v1/tasks/{key}/", {
    params: { path: { key } },
  });
  if (!response.ok) throw new ApiError(errorMessage(error, "タスクを削除できませんでした。"), response.status, error);
}

export async function getTaskEvents(key: string, page = 1) {
  const { data, error, response } = await client.GET("/api/v1/tasks/{key}/events/", {
    params: { path: { key }, query: { page } },
  });
  return assertData(data, error, response.status, "タイムラインを取得できませんでした。");
}

export async function getSettings() {
  const { data, error, response } = await client.GET("/api/v1/settings/");
  return assertData(data, error, response.status, "設定を取得できませんでした。");
}

export async function updateSettings(body: AppSettingsUpdate) {
  const { data, error, response } = await client.PATCH("/api/v1/settings/", { body });
  return assertData(data, error, response.status, "設定を保存できませんでした。");
}

export async function requestDiscordTest() {
  const { data, error, response } = await client.POST("/api/v1/settings/discord/test/");
  return assertData(data, error, response.status, "テスト送信を依頼できませんでした。");
}

export async function getApiKeys() {
  const { data, error, response } = await client.GET("/api/v1/api-keys/");
  return assertData(data, error, response.status, "APIキーを取得できませんでした。");
}

export async function createApiKey(body: ApiKeyCreate) {
  const { data, error, response } = await client.POST("/api/v1/api-keys/", { body });
  return assertData(data, error, response.status, "APIキーを発行できませんでした。");
}

export async function updateApiKey(keyId: string, body: { name?: string; is_active?: boolean }) {
  const { data, error, response } = await client.PATCH("/api/v1/api-keys/{key_id}/", {
    params: { path: { key_id: keyId } },
    body,
  });
  return assertData(data, error, response.status, "APIキーを更新できませんでした。");
}

export async function getRepositories() {
  const { data, error, response } = await client.GET("/api/v1/repositories/", {
    params: { query: { include_inactive: true } },
  });
  return assertData(data, error, response.status, "リポジトリを取得できませんでした。");
}

export async function createRepository(body: RepositoryCreate) {
  const { data, error, response } = await client.POST("/api/v1/repositories/", { body });
  return assertData(data, error, response.status, "リポジトリを登録できませんでした。");
}

export async function updateRepository(repositoryId: string, body: RepositoryUpdate) {
  const { data, error, response } = await client.PATCH("/api/v1/repositories/{repository_id}/", {
    params: { path: { repository_id: repositoryId } },
    body,
  });
  return assertData(data, error, response.status, "リポジトリを更新できませんでした。");
}

export async function deleteRepository(repositoryId: string) {
  const { error, response } = await client.DELETE("/api/v1/repositories/{repository_id}/", {
    params: { path: { repository_id: repositoryId } },
  });
  if (!response.ok) throw new ApiError(errorMessage(error, "リポジトリを削除できませんでした。"), response.status, error);
}
