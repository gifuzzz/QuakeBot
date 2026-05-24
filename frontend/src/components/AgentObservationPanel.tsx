import { useState } from 'react';
import type { EpisodeSnapshot } from '../types';

/* ---------- tiny helpers ---------- */

function ObsSection({ title, data, defaultOpen = false }: { title: string; data: unknown; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const isEmpty = data === null || data === undefined || (Array.isArray(data) && data.length === 0) || (typeof data === 'object' && !Array.isArray(data) && Object.keys(data as Record<string, unknown>).length === 0);

  return (
    <div className="obs-section">
      <button
        type="button"
        className={`obs-section-toggle ${open ? 'open' : ''}`}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="obs-toggle-icon">{open ? '▾' : '▸'}</span>
        <span className="obs-section-title">{title}</span>
        {isEmpty && <span className="obs-empty-badge">empty</span>}
      </button>
      {open && (
        <div className="obs-section-body">
          <pre className="obs-json">{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}

function KVRow({ label, value }: { label: string; value: unknown }) {
  const display = typeof value === 'object' ? JSON.stringify(value) : String(value ?? '—');
  return (
    <>
      <dt>{label}</dt>
      <dd>{display}</dd>
    </>
  );
}

/* ---------- main component ---------- */

type ViewMode = 'structured' | 'raw';

export function AgentObservationPanel({ snapshot }: { snapshot: EpisodeSnapshot }) {
  const obs = snapshot.agent_observation;
  const [mode, setMode] = useState<ViewMode>('structured');
  const [panelOpen, setPanelOpen] = useState(true);

  if (!obs || Object.keys(obs).length === 0) {
    return (
      <section className="panel obs-panel">
        <h2>🤖 Agent Observation</h2>
        <p style={{ color: '#91a4ad', fontSize: '0.85rem' }}>No observation data available for this step.</p>
      </section>
    );
  }

  return (
    <section className="panel obs-panel">
      <div className="obs-header">
        <button
          type="button"
          className="obs-collapse-toggle"
          onClick={() => setPanelOpen(!panelOpen)}
          aria-expanded={panelOpen}
          title={panelOpen ? 'Collapse panel' : 'Expand panel'}
        >
          {panelOpen ? '▾' : '▸'}
        </button>
        <h2>🤖 Agent Observation <span className="obs-step-badge">Step {Number(obs.step ?? snapshot.step)}</span></h2>
        <div className="obs-mode-toggle">
          <button type="button" className={mode === 'structured' ? 'active' : ''} onClick={() => setMode('structured')}>Structured</button>
          <button type="button" className={mode === 'raw' ? 'active' : ''} onClick={() => setMode('raw')}>Raw JSON</button>
        </div>
      </div>

      {panelOpen && mode === 'raw' && (
        <pre className="obs-json obs-raw-json">{JSON.stringify(obs, null, 2)}</pre>
      )}

      {panelOpen && mode === 'structured' && (
        <div className="obs-structured">
          {/* --- Quick glance row --- */}
          <div className="obs-glance">
            <dl className="stat-list">
              <KVRow label="Location" value={obs.location} />
              <KVRow label="Floor" value={obs.floor_name} />
              <KVRow label="Battery" value={obs.battery} />
              <KVRow label="Step" value={obs.step} />
              <KVRow label="Survivor mode" value={obs.survivor_count_mode} />
              <KVRow label="Location mode" value={obs.survivor_location_mode} />
            </dl>
          </div>

          {/* --- Goal --- */}
          {obs.goal ? (
            <div className="obs-goal">
              <strong>Goal:</strong> {String(obs.goal)}
            </div>
          ) : null}

          {/* --- Sections --- */}
          <ObsSection title="🚪 Visible Exits" data={obs.visible_exits} defaultOpen />
          <ObsSection title="🪜 Vertical Exits" data={obs.vertical_exits} />
          <ObsSection title="🌡️ Local Conditions" data={obs.local_conditions} defaultOpen />
          <ObsSection title="👁️ Visible Objects" data={obs.visible_objects} />
          <ObsSection title="👂 Heard Sounds" data={obs.heard_sounds} defaultOpen />
          <ObsSection title="📳 Vibration Cues" data={obs.vibration_cues} />
          <ObsSection title="🆘 Survivor Cues" data={obs.survivor_cues} defaultOpen />
          <ObsSection title="🧑‍🤝‍🧑 Local Survivors" data={obs.local_survivors} defaultOpen />
          <ObsSection title="🎒 Inventory" data={obs.inventory} />
          <ObsSection title="🚧 Blocked Paths" data={obs.blocked_paths} />
          <ObsSection title="🔗 Blocked Connections" data={obs.blocked_connections} />
          <ObsSection title="⚠️ Active Hazards" data={obs.active_hazards} />
          <ObsSection title="📋 Recommended Next Actions" data={obs.recommended_next_actions} defaultOpen />
          <ObsSection title="💡 Priority Reason" data={obs.priority_reason} />
          <ObsSection title="📊 Known/Estimated Survivor Count" data={obs.known_or_estimated_survivor_count} />
          <ObsSection title="🔍 Room Search Status" data={obs.room_search_status} />
          <ObsSection title="📍 Rooms to Search" data={obs.rooms_to_search} />
          <ObsSection title="🚫 Rooms Confirmed Inaccessible" data={obs.rooms_confirmed_inaccessible} />
          <ObsSection title="🏠 Rooms with Survivor Cues" data={obs.rooms_with_survivor_cues} />
          <ObsSection title="❓ Unknown Survivor Cues" data={obs.unknown_survivor_cues} />
          <ObsSection title="✅ Discovered Survivors" data={obs.discovered_survivors} />
          <ObsSection title="👥 Known Survivors (Status)" data={obs.known_survivors} />
          <ObsSection title="📐 Mission Accounting" data={obs.mission_accounting} />
          <ObsSection title="🏢 Known Floors" data={obs.known_floors} />
          <ObsSection title="🗺️ Known Map (Memory)" data={obs.known_map} />
          <ObsSection title="📰 Recent Events" data={obs.recent_events} />
          <ObsSection title="⏱️ Events This Step" data={obs.events_this_step} />
          <ObsSection title="🔄 Condition Changes Since Last Step" data={obs.condition_changes_since_last_step} />
        </div>
      )}
    </section>
  );
}
