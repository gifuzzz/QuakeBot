export type SurvivorCountMode = 'exact' | 'approximate';

export interface ScenarioConfigRequest {
  active_floors: string[];
  survivor_count_mode: SurvivorCountMode;
  survivor_count: number | null;
  survivor_count_min: number | null;
  survivor_count_max: number | null;
  seed: number;
  random_events_enabled: boolean;
  max_steps: number;
}

export interface StartEpisodeResponse {
  episode_id: string;
  snapshot_count: number;
  final_score: number;
  final_step: number;
  config: Record<string, unknown>;
}

export interface RoomRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface VisualFloor {
  width: number;
  height: number;
  rooms: Record<string, RoomRegion>;
  doors?: [number, number][];
  stairs?: [number, number][];
  rubble?: Record<string, [number, number]>;
  items?: Record<string, [number, number]>;
}

export interface LayoutsResponse {
  scenario: Record<string, unknown>;
  semantic: {
    id: string;
    name: string;
    floors: Record<string, { name: string; rooms: Record<string, unknown> }>;
    room_to_floor: Record<string, string>;
    blocked_paths: Record<string, unknown>;
  };
  visual: {
    floors: Record<string, VisualFloor>;
  };
}

export interface SurvivorSnapshot {
  id: string;
  name: string | null;
  location: string;
  trapped: boolean;
  reachable: boolean;
  conscious: boolean;
  responsive: boolean;
  breathing_status: string;
  pulse_status: string;
  bleeding: string;
  pain_level: number;
  can_walk: boolean;
  checks_completed: string[];
  stabilised: boolean;
  carried: boolean;
  evacuated: boolean;
  priority: string;
  accounting_status: string;
  stability: number;
  bleeding_controlled: boolean;
  airway_clear: boolean;
  breathing_supported: boolean;
  condition_history: string[];
}

export interface RoomState {
  floor: number;
  floor_name: string;
  exits: string[];
  objects: string[];
  items: string[];
  survivors: string[];
  conditions: Record<string, string | boolean | number | null>;
}

export interface MissionAccounting {
  survivor_count_mode: SurvivorCountMode;
  estimated_survivors: number | null;
  survivor_count_min: number | null;
  survivor_count_max: number | null;
  confirmed_survivors: number;
  total_known_or_suspected_survivors: number;
  evacuated: string[];
  directly_assessed: string[];
  awaiting_specialised_extraction: string[];
  unaccounted: string[];
  unaccounted_survivors: string[];
  uncleared_reachable_rooms: string[];
  mission_can_finish: boolean;
  reason_not_finished: string;
}

export interface WorldEvent {
  id: string;
  type: string;
  step: number;
  location: string;
  severity: string;
  message: string;
  effects: Record<string, unknown>;
  affected_survivor_id?: string;
  affected_connection?: string[];
}

export interface EpisodeSnapshot {
  step: number;
  robot_location: string;
  current_floor: number;
  floor_name: string;
  action: Record<string, unknown> | null;
  action_description: string;
  action_result: string;
  action_ok: boolean;
  battery: number;
  inventory: string[];
  carrying_survivor: string | null;
  room_states: Record<string, RoomState>;
  rubble_states: Record<string, string>;
  hazard_states: Record<string, Record<string, unknown>>;
  known_survivors: Record<string, Record<string, unknown>>;
  all_survivors: Record<string, SurvivorSnapshot>;
  score: number;
  dialogue_event_log: string[];
  recommended_next_actions: Record<string, string>[];
  blocked_paths: Record<string, Record<string, string>>;
  mission_accounting: MissionAccounting;
  room_search_status: Record<string, string>;
  rooms_to_search: string[];
  events_this_step: WorldEvent[];
  blocked_connections: string[][];
  transcript_text: string;
}
