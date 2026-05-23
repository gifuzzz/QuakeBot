import type { ScenarioConfigRequest } from '../types';

interface Props {
  config: ScenarioConfigRequest;
  loading: boolean;
  onChange: (config: ScenarioConfigRequest) => void;
  onStart: () => void;
}

export function ScenarioConfigPanel({ config, loading, onChange, onStart }: Props) {
  const update = <K extends keyof ScenarioConfigRequest>(key: K, value: ScenarioConfigRequest[K]) => {
    onChange({ ...config, [key]: value });
  };

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
        <input
          value={config.active_floors.join(', ')}
          onChange={(event) => update('active_floors', event.target.value.split(',').map((item) => item.trim()).filter(Boolean))}
        />
      </label>
      <label>
        Survivor Count
        <select value={config.survivor_count_mode} onChange={(event) => update('survivor_count_mode', event.target.value as ScenarioConfigRequest['survivor_count_mode'])}>
          <option value="exact">Exact</option>
          <option value="approximate">Approximate</option>
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
      <button className="primary-button" onClick={onStart} disabled={loading}>{loading ? 'Starting...' : 'Start Episode'}</button>
    </section>
  );
}
