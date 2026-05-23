import type { EpisodeSnapshot } from '../types';

export function CurrentActionPanel({ snapshot }: { snapshot: EpisodeSnapshot }) {
  return (
    <section className={`panel action-panel ${snapshot.action_ok ? 'ok' : 'rejected'}`}>
      <h2>Step {snapshot.step}</h2>
      <div className="action-result">{snapshot.action_result}</div>
      <pre>{JSON.stringify(snapshot.action ?? { type: 'initial_state' }, null, 2)}</pre>
      <div className="event-badges">
        {snapshot.events_this_step.length ? snapshot.events_this_step.map((event) => <span key={event.id}>{event.type}: {event.location}</span>) : <span>No dynamic events this step</span>}
      </div>
    </section>
  );
}
