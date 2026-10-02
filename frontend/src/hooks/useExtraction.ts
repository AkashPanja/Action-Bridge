import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export function useCredentials() {
  return useQuery({ queryKey: ["credentials"], queryFn: api.credentials.list });
}

export function useCredentialMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["credentials"] });
  return {
    create: useMutation({ mutationFn: api.credentials.create, onSuccess: invalidate }),
    replaceSecret: useMutation({
      mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
        api.credentials.replaceSecret(id, payload),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: api.credentials.remove, onSuccess: invalidate }),
  };
}

export function useProviders() {
  return useQuery({ queryKey: ["providers"], queryFn: api.providers.list });
}

export function useProviderPresets() {
  return useQuery({ queryKey: ["provider-presets"], queryFn: api.providers.presets });
}

export function useProviderMutations() {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["providers"] });
  return {
    create: useMutation({ mutationFn: api.providers.create, onSuccess: invalidate }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
        api.providers.update(id, data),
      onSuccess: invalidate,
    }),
    remove: useMutation({ mutationFn: api.providers.remove, onSuccess: invalidate }),
  };
}

export function useProcessing() {
  return useQuery({ queryKey: ["processing"], queryFn: api.processing.get });
}

export function useUpdateProcessing() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.processing.update,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["processing"] }),
  });
}

export function useProfiles(projectId: string) {
  return useQuery({
    queryKey: ["profiles", projectId],
    queryFn: () => api.profiles.list(projectId),
    enabled: !!projectId,
  });
}

export function useProfileMutations(projectId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["profiles", projectId] });
  return {
    create: useMutation({
      mutationFn: (data: Record<string, unknown>) => api.profiles.create(projectId, data),
      onSuccess: invalidate,
    }),
    update: useMutation({
      mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
        api.profiles.update(projectId, id, data),
      onSuccess: invalidate,
    }),
    remove: useMutation({
      mutationFn: (id: string) => api.profiles.remove(projectId, id),
      onSuccess: invalidate,
    }),
  };
}

export function useProjectJobs(
  projectId: string,
  filters?: { status?: string; kind?: string },
  refetchInterval?: number | false,
) {
  return useQuery({
    queryKey: ["jobs", projectId, filters],
    queryFn: () => api.jobs.listForProject(projectId, filters),
    enabled: !!projectId,
    refetchInterval: refetchInterval ?? false,
  });
}

export function useJobMutations(projectId: string) {
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["jobs", projectId] });
  return {
    retry: useMutation({ mutationFn: api.jobs.retry, onSuccess: invalidate }),
    cancel: useMutation({ mutationFn: api.jobs.cancel, onSuccess: invalidate }),
  };
}

export function useSubmission(id: string | null) {
  return useQuery({
    queryKey: ["submission", id],
    queryFn: () => api.submissions.get(id!),
    enabled: !!id,
  });
}
