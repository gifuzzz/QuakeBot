import type { EpisodeSnapshot, LayoutsResponse, ScenarioConfigRequest, StartEpisodeResponse } from './types';

const API_BASE = import.meta.env.VITE_QUAKEBOT_API ?? 'http://localhost:8000';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function getLayouts(): Promise<LayoutsResponse> {
  return request<LayoutsResponse>('/layouts');
}

export function startEpisode(config: ScenarioConfigRequest): Promise<StartEpisodeResponse> {
  return request<StartEpisodeResponse>('/episodes/start', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function getSnapshots(episodeId: string): Promise<EpisodeSnapshot[]> {
  const payload = await request<{ snapshots: EpisodeSnapshot[] }>(`/episodes/${episodeId}/snapshots`);
  return payload.snapshots;
}

export function getSnapshot(episodeId: string, step: number): Promise<EpisodeSnapshot> {
  return request<EpisodeSnapshot>(`/episodes/${episodeId}/snapshot/${step}`);
}

export async function stepEpisode(episodeId: string): Promise<EpisodeSnapshot> {
  const payload = await request<{ snapshot: EpisodeSnapshot }>(`/episodes/${episodeId}/step`, { method: 'POST' });
  return payload.snapshot;
}

export async function resetEpisode(episodeId: string): Promise<EpisodeSnapshot> {
  const payload = await request<{ snapshot: EpisodeSnapshot }>(`/episodes/${episodeId}/reset`, { method: 'POST' });
  return payload.snapshot;
}
