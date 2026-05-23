import type { EpisodeSnapshot } from '../types';

export function MissionLog({ snapshot }: { snapshot: EpisodeSnapshot }) {
  return (
    <section className="panel log-panel">
      <h2>Mission Log</h2>
      <ol>
        {snapshot.dialogue_event_log.slice(-18).map((event, index) => <li key={`${index}-${event}`}>{event}</li>)}
      </ol>
    </section>
  );
}
