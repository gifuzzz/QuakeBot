import { useState } from 'react';
import type { CustomLayoutRequest, ScenarioConfigRequest } from '../types';
import { CustomLayoutBuilder } from './CustomLayoutBuilder';
import { CommaInput } from './CommaInput';

interface Props {
  config: ScenarioConfigRequest;
  loading: boolean;
  onChange: (config: ScenarioConfigRequest) => void;
  onStart: () => void;
  onStop?: () => void;
}

export function ScenarioConfigPanel({ config, loading, onChange, onStart, onStop }: Props) {
  const [layoutError, setLayoutError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const update = <K extends keyof ScenarioConfigRequest>(key: K, value: ScenarioConfigRequest[K]) => {
    onChange({ ...config, [key]: value });
  };

  const useCustomLayout = Boolean(config.custom_layout);

  function toggleCustomLayout(enabled: boolean) {
    if (enabled) {
      update('custom_layout', config.custom_layout ?? starterCustomLayout);
    } else {
      update('custom_layout', null);
    }
  }

  function updateLayoutObj(layout: CustomLayoutRequest) {
    if (!Array.isArray(layout.floors) || !Array.isArray(layout.survivors)) {
      setLayoutError('Layout requires floors and survivors arrays.');
      return;
    }
    setLayoutError(null);
    update('custom_layout', layout);
  }

  return (
    <section className="panel scenario-panel">
      <h2>Scenario</h2>
      <label>
        Agent
        <select value={config.agent_type} onChange={(event) => update('agent_type', event.target.value)}>
          <option value="mock">Mock</option>
          <option value="ollama">Ollama</option>
        </select>
      </label>
      <label>
        Floors
        <CommaInput
          value={useCustomLayout ? config.custom_layout?.floors.map((floor) => floor.id) ?? [] : config.active_floors}
          disabled={useCustomLayout}
          onChange={(val) => update('active_floors', val)}
        />
      </label>
      <label>
        Survivor Count Mode
        <select value={config.survivor_count_mode} onChange={(event) => update('survivor_count_mode', event.target.value as ScenarioConfigRequest['survivor_count_mode'])}>
          <option value="exact">Exact</option>
          <option value="approximate">Approximate</option>
        </select>
      </label>
      <label>
        Survivor Locations
        <select value={config.survivor_location_mode} onChange={(event) => update('survivor_location_mode', event.target.value as ScenarioConfigRequest['survivor_location_mode'])}>
          <option value="known">Known</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>
      <div className="field-row">
        <label>
          Count
          <input type="number" value={config.survivor_count ?? 0} onChange={(event) => update('survivor_count', Number(event.target.value))} />
        </label>
        <label>
          Min
          <input type="number" value={config.survivor_count_min ?? 3} onChange={(event) => update('survivor_count_min', Number(event.target.value))} />
        </label>
        <label>
          Max
          <input type="number" value={config.survivor_count_max ?? 5} onChange={(event) => update('survivor_count_max', Number(event.target.value))} />
        </label>
      </div>
      <div className="field-row">
        <label>
          Seed
          <input type="number" value={config.seed} onChange={(event) => update('seed', Number(event.target.value))} />
        </label>
        <label>
          Max Steps
          <input type="number" value={config.max_steps} onChange={(event) => update('max_steps', Number(event.target.value))} />
        </label>
      </div>
      <label className="checkbox-line">
        <input type="checkbox" checked={config.random_events_enabled} onChange={(event) => update('random_events_enabled', event.target.checked)} />
        Seeded random events
      </label>
      <label className="checkbox-line">
        <input type="checkbox" checked={useCustomLayout} onChange={(event) => toggleCustomLayout(event.target.checked)} />
        Custom semantic layout
      </label>
      {useCustomLayout && (
        <div className="scenario-editor">
          <div className="editor-toolbar">
            <span>{config.custom_layout?.name ?? 'Custom scenario'}</span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button type="button" onClick={() => updateLayoutObj(starterCustomLayout)}>
                Reset to Starter
              </button>
              <button type="button" className="primary-button" onClick={() => setIsModalOpen(true)}>
                Edit Layout
              </button>
            </div>
          </div>
          <div className="field-hint">Configure floors, rooms, connections, hazards, blocked access, cues, and survivors. The backend remains the source of truth for all transitions.</div>
          
          {isModalOpen && (
            <div className="modal-overlay">
              <div className="modal-content">
                <div className="modal-header">
                  <h2>Edit Custom Layout</h2>
                  <button type="button" onClick={() => setIsModalOpen(false)}>Close</button>
                </div>
                <div className="modal-body">
                  {layoutError && <div className="inline-error">{layoutError}</div>}
                  <CustomLayoutBuilder 
                    value={config.custom_layout || starterCustomLayout} 
                    onChange={updateLayoutObj} 
                  />
                </div>
                <div className="modal-footer">
                  <button type="button" className="primary-button" onClick={() => setIsModalOpen(false)}>Done</button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', gap: '8px' }}>
        <button className="primary-button" style={{ flex: 1 }} onClick={onStart} disabled={loading}>{loading ? 'Starting...' : 'Start Episode'}</button>
        {loading && onStop && (
          <button type="button" onClick={onStop} style={{ borderColor: '#8b3f3f', color: '#ff9999' }}>Stop</button>
        )}
      </div>
    </section>
  );
}

const starterCustomLayout: CustomLayoutRequest = {
  id: 'frontend_custom',
  name: 'Frontend Custom Rescue',
  floors: [
    {
      id: 'ground',
      name: 'Ground Floor',
      level: 0,
      rooms: [
        {
          name: 'Entrance',
          connects_to: ['Hallway'],
          hazards: { smoke: 'none', structural_risk: 'low' },
        },
        {
          name: 'Hallway',
          connects_to: ['Entrance', 'Office'],
          hazards: { smoke: 'light', structural_risk: 'medium' },
          sounds: ['muffled tapping to the east'],
          vibration_cues: ['weak vibration near the office doorway'],
          survivor_cues: ['voice beyond rubble'],
          objects: ['loose_debris'],
        },
        {
          name: 'Office',
          connects_to: ['Hallway'],
          hazards: { smoke: 'light', structural_risk: 'medium' },
          objects: ['rubble'],
          blocked_by: {
            type: 'rubble',
            status: 'blocking',
            required_location: 'Hallway',
          },
        },
      ],
    },
  ],
  survivors: [
    {
      id: 'survivor_office',
      name: 'Elena',
      location: 'Office',
      trapped: true,
      reachable: false,
      conscious: true,
      responsive: true,
      breathing_status: 'fast',
      pulse_status: 'rapid',
      bleeding: 'minor',
      pain_level: 6,
      can_walk: false,
      suspected_injuries: ['leg pinned under desk'],
      priority: 'high',
    },
  ],
};
