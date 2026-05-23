import type { EpisodeSnapshot } from '../types';

export function MissionAccountingPanel({ snapshot }: { snapshot: EpisodeSnapshot }) {
  const accounting = snapshot.mission_accounting;
  return (
    <section className={`panel accounting-panel ${accounting.mission_can_finish ? 'finish-ready' : ''}`}>
      <h2>Mission Accounting</h2>
      <dl className="compact-list">
        <dt>Mode</dt><dd>{accounting.survivor_count_mode}</dd>
        <dt>Estimate</dt><dd>{accounting.estimated_survivors ?? `${accounting.survivor_count_min}-${accounting.survivor_count_max}`}</dd>
        <dt>Evacuated</dt><dd>{accounting.evacuated.join(', ') || 'none'}</dd>
        <dt>Assessed</dt><dd>{accounting.directly_assessed.join(', ') || 'none'}</dd>
        <dt>Awaiting extraction</dt><dd>{accounting.awaiting_specialised_extraction.join(', ') || 'none'}</dd>
        <dt>Unaccounted</dt><dd>{accounting.unaccounted.join(', ') || 'none'}</dd>
        <dt>Rooms to clear</dt><dd>{accounting.uncleared_reachable_rooms.join(', ') || 'none'}</dd>
      </dl>
      <div className="mission-ready">{accounting.mission_can_finish ? 'Mission can finish' : accounting.reason_not_finished}</div>
    </section>
  );
}
