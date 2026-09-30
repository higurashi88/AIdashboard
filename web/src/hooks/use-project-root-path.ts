import { useQuery } from "@tanstack/react-query";

import { getAllProjects } from "@/api/client";

export function useProjectRootPath(slug: string) {
  const projects = useQuery({ queryKey: ["projects", "all"], queryFn: getAllProjects });
  const rootPath = projects.data?.find((project) => project.slug === slug)?.root_path;
  return rootPath?.trim() ? rootPath : undefined;
}
