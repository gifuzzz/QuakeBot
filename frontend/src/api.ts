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

export function getReplays(): Promise<{ replays: string[] }> {
  return request<{ replays: string[] }>('/replays');
}

export function loadReplay(filename: string): Promise<EpisodeSnapshot[]> {
  return request<EpisodeSnapshot[]>(`/replays/${filename}`);
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

export function streamEpisode(
  config: ScenarioConfigRequest,
  onSnapshot: (snapshot: EpisodeSnapshot) => void,
  onError: (error: Error) => void,
  onClose: () => void
): () => void {
  const wsUrl = API_BASE.replace(/^http/, 'ws') + '/episodes/stream';
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    ws.send(JSON.stringify(config));
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.error) {
        onError(new Error(data.error));
        ws.close();
      } else {
        onSnapshot(data as EpisodeSnapshot);
      }
    } catch (e) {
      onError(e as Error);
    }
  };

  ws.onerror = () => {
    onError(new Error('WebSocket error occurred'));
  };

  ws.onclose = () => {
    onClose();
  };

  return () => {
    ws.onmessage = null;
    ws.onerror = null;
    ws.onclose = null;
    ws.close();
  };
}
