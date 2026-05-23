import type { EpisodeSnapshot, WorldEvent } from '../types';

export function EventTimeline({ snapshots }: { snapshots: EpisodeSnapshot[] }) {
  const events = snapshots.flatMap((snapshot) => snapshot.events_this_step as WorldEvent[]);
  return (
    <section className="panel event-panel">
      <h2>Event Timeline</h2>
      {events.length === 0 ? <p>No dynamic events yet.</p> : (
        <ol>
          {events.map((event) => (
            <li key={event.id}>
              <span className={`event-type ${event.severity}`}>{event.type}</span>
              <span>Step {event.step}: {event.message}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
