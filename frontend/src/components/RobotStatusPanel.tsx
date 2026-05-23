import type { EpisodeSnapshot } from '../types';

export function RobotStatusPanel({ snapshot }: { snapshot: EpisodeSnapshot }) {
  return (
    <section className="panel">
      <h2>QuakeBot</h2>
      <dl className="stat-list">
        <dt>Room</dt><dd>{snapshot.robot_location}</dd>
        <dt>Floor</dt><dd>{snapshot.floor_name}</dd>
        <dt>Battery</dt><dd>{snapshot.battery}</dd>
        <dt>Carrying</dt><dd>{snapshot.carrying_survivor ?? 'none'}</dd>
        <dt>Inventory</dt><dd>{snapshot.inventory.join(', ') || 'empty'}</dd>
        <dt>Score</dt><dd>{snapshot.score}</dd>
      </dl>
    </section>
  );
}
