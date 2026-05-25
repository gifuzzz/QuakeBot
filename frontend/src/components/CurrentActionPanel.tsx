import type { EpisodeSnapshot } from '../types';

export function CurrentActionPanel({ snapshot }: { snapshot: EpisodeSnapshot }) {
  return (
    <section className={`panel action-panel ${snapshot.action_ok ? 'ok' : 'rejected'}`}>
      <h2>Step {snapshot.step}</h2>
      <div className="action-result">{snapshot.action_result}</div>
      <pre>{JSON.stringify(snapshot.action ?? { type: 'initial_state' }, null, 2)}</pre>
      <div style={{ marginTop: '10px' }}>
        <strong>Mission Control Debug Hints</strong>
        <p style={{ margin: '6px 0', fontSize: '0.85rem', color: '#91a4ad' }}>
          These internal recommendations are shown for debugging and replay inspection. They are not part of the LLM prompt.
        </p>
        <pre>{JSON.stringify(snapshot.recommended_next_actions ?? [], null, 2)}</pre>
      </div>
      <div className="event-badges">
        {snapshot.events_this_step.length ? snapshot.events_this_step.map((event) => <span key={event.id as string}>{event.type as string}: {event.location as string}</span>) : <span>No dynamic events this step</span>}
      </div>
    </section>
  );
}
