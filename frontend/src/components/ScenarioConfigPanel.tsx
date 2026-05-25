import { useState } from 'react';
import type { CustomLayoutRequest, ScenarioConfigRequest } from '../types';
import { CustomLayoutBuilder } from './CustomLayoutBuilder';
import { CommaInput } from './CommaInput';

interface Props {
  config: ScenarioConfigRequest;
  loading: boolean;
  onChange: (config: ScenarioConfigRequest) => void;
  onStart: (cfg?: ScenarioConfigRequest) => void;
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

  function loadFeaturedLayout(layout: CustomLayoutRequest) {
    setLayoutError(null);
    const newConfig = {
      ...config,
      scenario: '',
      custom_layout: layout,
      active_floors: layout.floors.map((floor) => floor.id),
      survivor_count_mode: 'exact' as const,
      survivor_location_mode: 'known' as const,
      survivor_count: layout.survivors.length,
      survivor_count_min: layout.survivors.length,
      survivor_count_max: layout.survivors.length,
    };
    onChange(newConfig);
  }

  return (
    <section className="panel scenario-panel">
      <h2>Scenario Setup</h2>
      <div style={{ marginBottom: '16px', padding: '10px', border: '1px solid #35424d', background: '#12181d', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ fontSize: '0.85rem', color: '#cce7d0', fontWeight: 700 }}>Choose a Scenario</div>
        <button 
          type="button" 
          className="primary-button" 
          style={{ background: config.custom_layout?.id === starterCustomLayout.id ? '#2a4365' : undefined }}
          onClick={() => loadFeaturedLayout(starterCustomLayout)}
        >
          Starter Scenario
        </button>
        <button 
          type="button" 
          className="primary-button" 
          style={{ background: config.custom_layout?.id === featuredOfficeRescueLayout.id ? '#2a4365' : undefined }}
          onClick={() => loadFeaturedLayout(featuredOfficeRescueLayout)}
        >
          Featured Office Rescue
        </button>
        <button 
          type="button" 
          className="primary-button" 
          onClick={() => {
            if (!config.custom_layout || (config.custom_layout.id === starterCustomLayout.id || config.custom_layout.id === featuredOfficeRescueLayout.id)) {
              updateLayoutObj({ ...starterCustomLayout, id: 'custom_edited', name: 'Custom Setup' });
            }
            setIsModalOpen(true);
          }}
        >
          Custom Scenario (Edit Layout)
        </button>
        <div className="field-hint" style={{ marginTop: '4px' }}>
          Select a scenario to configure your mission. You can use a preset or build a custom layout.
        </div>
      </div>
      <label>
        Debug Preset
        <select value={config.scenario || ''} onChange={(event) => update('scenario', event.target.value)}>
          <option value="">Default / Custom Harness</option>
          <option value="hidden_survivors_exact">Debug: Hidden Survivors (Exact)</option>
          <option value="hidden_survivors_approximate">Debug: Hidden Survivors (Approximate)</option>
          <option value="generated_small">Debug: Generated Small</option>
          <option value="severe_risk_bleeding_survivor">Debug: Severe Risk Bleeding Survivor</option>
        </select>
      </label>
      <label>
        Agent
        <select value={config.agent_type} onChange={(event) => update('agent_type', event.target.value)}>
          <option value="mock">Mock</option>
          <option value="openai">OpenAI</option>
          <option value="ollama">Ollama</option>
          <option value="ollama-cloud">Ollama Cloud</option>
        </select>
      </label>
      {config.agent_type !== 'mock' && (
        <>
          <label>
            Model
            <input
              type="text"
              placeholder={config.agent_type === 'openai' ? 'gpt-4o' : config.agent_type === 'ollama-cloud' ? 'gpt-oss:120b' : 'llama3.1'}
              value={config.model || ''}
              onChange={(event) => update('model', event.target.value)}
            />
          </label>
          <label>
            API Key
            <input
              type="password"
              placeholder="Leave blank for env variable"
              value={config.api_key || ''}
              onChange={(event) => update('api_key', event.target.value)}
            />
          </label>
          <label>
            API Base URL
            <input
              type="text"
              placeholder={config.agent_type === 'openai' ? 'https://api.openai.com/v1' : config.agent_type === 'ollama-cloud' ? 'https://ollama.com' : 'http://localhost:11434'}
              value={config.api_url || ''}
              onChange={(event) => update('api_url', event.target.value)}
            />
          </label>
        </>
      )}
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
        <input type="checkbox" checked={config.save_json || false} onChange={(event) => update('save_json', event.target.checked)} />
        Save to JSON
      </label>
      
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
      <div style={{ display: 'flex', gap: '8px' }}>
        <button className="primary-button" style={{ flex: 1 }} onClick={() => onStart()} disabled={loading}>{loading ? 'Starting...' : 'Start Episode'}</button>
        {loading && onStop && (
          <button type="button" onClick={onStop} style={{ borderColor: '#8b3f3f', color: '#ff9999' }}>Stop</button>
        )}
      </div>
    </section>
  );
}

export const starterCustomLayout: CustomLayoutRequest = {
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
          connects_to: ['Lobby'],
          hazards: {},
        },
        {
          name: 'Lobby',
          connects_to: ['Entrance', 'Hallway', 'Stairwell_G'],
          hazards: {},
        },
        {
          name: 'Hallway',
          connects_to: ['Lobby', 'Office', 'Storage'],
          hazards: { structural_risk: 'medium' },
          objects: ['rubble'],
          sounds: ['muffled tapping to the east'],
          vibration_cues: ['weak vibration near the office doorway'],
          survivor_cues: ['voice beyond rubble'],
        },
        {
          name: 'Office',
          connects_to: ['Hallway'],
          hazards: { structural_risk: 'medium' },
          objects: ['rubble'],
          blocked_by: {
            type: 'rubble',
            status: 'blocking',
            required_location: 'Hallway',
          },
        },
        {
          name: 'Storage',
          connects_to: ['Hallway'],
          hazards: {},
          items: ['first_aid_kit'],
        },
        {
          name: 'Stairwell_G',
          connects_to: ['Lobby', 'Stairwell_1', 'Stairwell_B'],
          hazards: { smoke: 'low' },
        },
      ],
    },
    {
      id: 'floor_1',
      name: 'Floor 1',
      level: 1,
      rooms: [
        {
          name: 'Stairwell_1',
          connects_to: ['Stairwell_G', 'Upper_Hallway'],
          hazards: {},
        },
        {
          name: 'Upper_Hallway',
          connects_to: ['Stairwell_1', 'Apartment_A', 'Apartment_B'],
          hazards: {},
        },
        {
          name: 'Apartment_A',
          connects_to: ['Upper_Hallway'],
          hazards: {},
        },
        {
          name: 'Apartment_B',
          connects_to: ['Upper_Hallway', 'Balcony'],
          hazards: { structural_risk: 'medium' },
        },
        {
          name: 'Balcony',
          connects_to: ['Apartment_B'],
          hazards: { structural_risk: 'high' },
        },
      ],
    },
    {
      id: 'basement',
      name: 'Basement',
      level: -1,
      rooms: [
        {
          name: 'Stairwell_B',
          connects_to: ['Stairwell_G', 'Basement'],
          hazards: { structural_risk: 'medium' },
        },
        {
          name: 'Basement',
          connects_to: ['Stairwell_B', 'Utility_Room', 'Generator_Room'],
          hazards: { structural_risk: 'high' },
        },
        {
          name: 'Utility_Room',
          connects_to: ['Basement'],
          hazards: { electrical_hazard: true, structural_risk: 'medium' },
        },
        {
          name: 'Generator_Room',
          connects_to: ['Basement'],
          hazards: { smoke: 'moderate', structural_risk: 'medium' },
        },
      ],
    },
  ],
  survivors: [
    {
      id: 'survivor_office',
      name: 'Pari',
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
      suspected_injuries: ['leg pinned under desk', 'left arm cut'],
      priority: 'high',
    },
    {
      id: 'survivor_apartment_a',
      name: 'Luigi',
      location: 'Apartment_A',
      trapped: false,
      reachable: true,
      conscious: true,
      responsive: true,
      breathing_status: 'normal',
      pulse_status: 'normal',
      bleeding: 'none',
      pain_level: 4,
      can_walk: true,
      suspected_injuries: ['sprained ankle', 'anxiety'],
      priority: 'medium',
    },
    {
      id: 'survivor_basement',
      name: 'Niya',
      location: 'Basement',
      trapped: true,
      reachable: false,
      conscious: true,
      responsive: true,
      breathing_status: 'laboured',
      pulse_status: 'weak',
      bleeding: 'severe',
      pain_level: 8,
      can_walk: false,
      suspected_injuries: ['possible crush injury', 'severe bleeding'],
      priority: 'critical',
    },
  ],
};

export const featuredOfficeRescueLayout: CustomLayoutRequest = {
  id: 'featured_office_rescue',
  name: 'Featured Office Rescue',
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
          connects_to: ['Entrance', 'Office 0', 'Cafeteria', 'Stairs Level 0'],
          hazards: { smoke: 'light', structural_risk: 'medium' },
          objects: ['loose_debris'],
          blocked_by: {
            type: 'collapsed_wall',
            status: 'blocking',
            required_location: 'Entrance',
          },
        },
        {
          name: 'Office 0',
          connects_to: ['Hallway'],
          hazards: { smoke: 'light', structural_risk: 'medium' },
          objects: ['rubble'],
          blocked_by: {
            type: 'rubble',
            status: 'blocking',
            required_location: 'Hallway',
          },
        },
        {
          name: 'Cafeteria',
          connects_to: ['Hallway'],
        },
        {
          name: 'Stairs Level 0',
          connects_to: ['Stairs Level 1', 'Hallway'],
          blocked_by: null,
        },
      ],
    },
    {
      id: 'floor_level_1',
      name: 'Floor 1',
      level: 1,
      rooms: [
        {
          name: 'Office 1',
          connects_to: ['Hallway 1', 'Board Room'],
        },
        {
          name: 'Office 2',
          connects_to: ['Hallway 1'],
          hazards: {},
          blocked_by: {
            type: 'furniture',
            status: 'blocking',
            required_location: 'Hallway 1',
          },
        },
        {
          name: 'Office 3',
          connects_to: ['Hallway 1'],
          items: ['first_aid_kit'],
        },
        {
          name: 'Board Room',
          connects_to: ['Office 1'],
          blocked_by: {
            type: 'furniture',
            status: 'blocking',
            required_location: 'Office 1',
          },
          hazards: {
            smoke: 'moderate',
          },
        },
        {
          name: 'Hallway 1',
          connects_to: ['Office 3', 'Office 2', 'Office 1'],
        },
        {
          name: 'Stairs Level 1',
          connects_to: ['Stairs Level 0', 'Hallway 1'],
        },
      ],
    },
  ],
  survivors: [
    {
      id: 'survivor_pari',
      name: 'Pari',
      location: 'Board Room',
      trapped: false,
      reachable: false,
      conscious: false,
      responsive: false,
      breathing_status: 'laboured',
      pulse_status: 'weak',
      bleeding: 'severe',
      pain_level: 10,
      can_walk: false,
      suspected_injuries: [],
      priority: 'critical',
    },
    {
      id: 'survivor_luigi',
      name: 'Luigi',
      location: 'Office 1',
      trapped: true,
      reachable: false,
      conscious: false,
      responsive: false,
      breathing_status: 'normal',
      pulse_status: 'normal',
      bleeding: 'none',
      pain_level: 3,
      can_walk: false,
      suspected_injuries: ['lost his pp'],
      priority: 'medium',
    },
  ],
};
