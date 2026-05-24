import type { EpisodeSnapshot, VisualFloor } from '../types';

interface Props {
  floorName: string;
  layout: VisualFloor | undefined;
  snapshot: EpisodeSnapshot;
}

export function PixelFloorMap({ floorName, layout, snapshot }: Props) {
  const roomEntries = layout
    ? Object.entries(layout.rooms)
    : Object.entries(snapshot.room_states)
        .filter(([, room]) => room.floor_name === floorName)
        .map(([room], index) => [room, { x: index % 3, y: Math.floor(index / 3), width: 1, height: 1 }] as const);
  const width = layout?.width ?? 3;
  const height = layout?.height ?? Math.max(1, Math.ceil(roomEntries.length / 3));

  return (
    <section className="map-shell">
      <div className="map-title">{floorName}</div>
      <div className="pixel-map" style={{ gridTemplateColumns: `repeat(${width}, minmax(22px, 1fr))`, gridTemplateRows: `repeat(${height}, minmax(30px, auto))` }}>
        {roomEntries.map(([roomName, region]) => (
          <RoomTile key={roomName} roomName={roomName} region={region} snapshot={snapshot} />
        ))}
      </div>
    </section>
  );
}

function RoomTile({ roomName, region, snapshot }: { roomName: string; region: { x: number; y: number; width: number; height: number }; snapshot: EpisodeSnapshot }) {
  const room = snapshot.room_states[roomName];
  const isRobot = snapshot.robot_location === roomName;
  const searchStatus = snapshot.room_search_status[roomName] ?? 'unknown';
  const rubble = snapshot.rubble_states[roomName];
  const blocked = snapshot.blocked_connections.some((pair) => pair.includes(roomName));
  const survivors = Object.values(snapshot.all_survivors).filter((survivor) => survivor.location === roomName);
  const conditions = room?.conditions ?? {};
  const classes = ['room-tile', isRobot ? 'robot-room' : '', searchStatus, blocked ? 'blocked-room' : ''].filter(Boolean).join(' ');

  return (
    <div className={classes} style={{ gridColumn: `${region.x + 1} / span ${region.width}`, gridRow: `${region.y + 1} / span ${region.height}` }}>
      <div className="room-name">{roomName}</div>
      <div className="sprite-row">
        {isRobot && <span title="QuakeBot">{snapshot.carrying_survivor ? '🤖+' : '🤖'}</span>}
        {survivors.map((survivor) => (
          <span key={survivor.id} title={`${survivor.id}: ${survivor.accounting_status}`}>
            {survivor.evacuated ? '✅' : survivor.accounting_status === 'awaiting_specialised_extraction' ? '🚑' : survivor.bleeding !== 'none' ? '🩸' : '🧍'}
          </span>
        ))}
        {rubble && rubble !== 'removed' && <span title={`Rubble ${rubble}`}>🪨</span>}
        {blocked && <span title="Blocked connection">🚧</span>}
        {room?.items.includes('first_aid_kit') && <span title="First aid kit">🩹</span>}
        {roomName.toLowerCase().includes('stair') && <span title="Stairs">↕️</span>}
      </div>
      <div className="hazard-row">
        {conditions.smoke && conditions.smoke !== 'none' && <span title="Smoke">💨</span>}
        {conditions.structural_risk && !['low', 'none'].includes(String(conditions.structural_risk)) && <span title={`Structural ${conditions.structural_risk}`}>⚠️</span>}
        {conditions.electrical_hazard && <span title="Electrical">⚡</span>}
        {conditions.gas_detected && <span title="Gas">☣️</span>}
      </div>
      <div className="room-status">{searchStatus}</div>
    </div>
  );
}
