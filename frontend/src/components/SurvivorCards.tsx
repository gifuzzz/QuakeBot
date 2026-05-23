import type { EpisodeSnapshot, SurvivorSnapshot } from '../types';

export function SurvivorCards({ snapshot }: { snapshot: EpisodeSnapshot }) {
  return (
    <section className="panel survivor-panel">
      <h2>Survivors</h2>
      {Object.values(snapshot.all_survivors).map((survivor) => <SurvivorCard key={survivor.id} survivor={survivor} />)}
    </section>
  );
}

function SurvivorCard({ survivor }: { survivor: SurvivorSnapshot }) {
  return (
    <article className={`survivor-card ${survivor.priority} ${survivor.accounting_status}`}>
      <header>
        <strong>{survivor.name ?? survivor.id}</strong>
        <span>{survivor.accounting_status}</span>
      </header>
      <div className="meter"><span style={{ width: `${survivor.stability}%` }} /></div>
      <dl className="compact-list">
        <dt>Location</dt><dd>{survivor.location}</dd>
        <dt>Priority</dt><dd>{survivor.priority}</dd>
        <dt>Airway</dt><dd>{survivor.airway_clear ? 'clear' : 'blocked'}</dd>
        <dt>Breathing</dt><dd>{survivor.breathing_status}{survivor.breathing_supported ? ' supported' : ''}</dd>
        <dt>Pulse</dt><dd>{survivor.pulse_status}</dd>
        <dt>Bleeding</dt><dd>{survivor.bleeding}{survivor.bleeding_controlled ? ' controlled' : ''}</dd>
        <dt>Mobility</dt><dd>{survivor.can_walk ? 'can walk' : 'cannot walk'}</dd>
        <dt>Trapped</dt><dd>{survivor.trapped ? 'yes' : 'free'}</dd>
      </dl>
      <div className="checks">{survivor.checks_completed.slice(-5).join(' · ') || 'no checks yet'}</div>
    </article>
  );
}
