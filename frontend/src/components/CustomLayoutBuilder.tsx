import { useState } from 'react';
import type { BlockedByConfig, CustomLayoutRequest, FloorLayoutRequest, RoomHazards, RoomLayoutRequest, SurvivorLayoutRequest } from '../types';
import { CommaInput } from './CommaInput';

interface Props {
  value: CustomLayoutRequest;
  onChange: (value: CustomLayoutRequest) => void;
}

export function CustomLayoutBuilder({ value, onChange }: Props) {
  const [activeTab, setActiveTab] = useState<'floors' | 'survivors' | 'json'>('floors');
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);

  const updateField = <K extends keyof CustomLayoutRequest>(key: K, val: CustomLayoutRequest[K]) => {
    onChange({ ...value, [key]: val });
  };

  const allRoomNames = value.floors.flatMap(f => f.rooms.map(r => r.name));

  const addFloor = () => {
    const newFloor: FloorLayoutRequest = {
      id: `floor_${value.floors.length + 1}`,
      name: `Floor ${value.floors.length + 1}`,
      level: value.floors.length,
      rooms: [],
    };
    updateField('floors', [...value.floors, newFloor]);
  };

  const updateFloor = (index: number, floor: FloorLayoutRequest) => {
    const newFloors = [...value.floors];
    newFloors[index] = floor;
    updateField('floors', newFloors);
  };

  const removeFloor = (index: number) => {
    updateField('floors', value.floors.filter((_, i) => i !== index));
  };

  const addSurvivor = () => {
    const newSurvivor: SurvivorLayoutRequest = {
      id: `survivor_${value.survivors.length + 1}`,
      name: `Survivor ${value.survivors.length + 1}`,
      location: allRoomNames[0] || 'Unknown',
      trapped: true,
      reachable: false,
      conscious: true,
      responsive: true,
      breathing_status: 'normal',
      pulse_status: 'normal',
      bleeding: 'none',
      pain_level: 0,
      can_walk: false,
      suspected_injuries: [],
      priority: 'medium',
    };
    updateField('survivors', [...value.survivors, newSurvivor]);
  };

  const updateSurvivor = (index: number, survivor: SurvivorLayoutRequest) => {
    const newSurvivors = [...value.survivors];
    newSurvivors[index] = survivor;
    updateField('survivors', newSurvivors);
  };

  const removeSurvivor = (index: number) => {
    updateField('survivors', value.survivors.filter((_, i) => i !== index));
  };

  return (
    <div className="custom-layout-builder" style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div className="field-row">
        <label>
          Scenario ID
          <input value={value.id} onChange={(e) => updateField('id', e.target.value)} />
        </label>
        <label>
          Scenario Name
          <input value={value.name} onChange={(e) => updateField('name', e.target.value)} />
        </label>
      </div>

      <div style={{ display: 'flex', gap: '8px', borderBottom: '2px solid #35424d', paddingBottom: '8px' }}>
        <button type="button" className={activeTab === 'floors' ? 'active' : ''} onClick={() => setActiveTab('floors')}>
          Floors & Rooms
        </button>
        <button type="button" className={activeTab === 'survivors' ? 'active' : ''} onClick={() => setActiveTab('survivors')}>
          Survivors
        </button>
        <button type="button" className={activeTab === 'json' ? 'active' : ''} onClick={() => {
          setJsonText(JSON.stringify(value, null, 2));
          setJsonError(null);
          setActiveTab('json');
        }}>
          Import/Export JSON
        </button>
      </div>

      {activeTab === 'floors' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {value.floors.map((floor, floorIndex) => (
            <FloorBlock
              key={floorIndex}
              floor={floor}
              allRoomNames={allRoomNames}
              onChange={(f) => updateFloor(floorIndex, f)}
              onRemove={() => removeFloor(floorIndex)}
            />
          ))}
          <button type="button" onClick={addFloor} style={{ alignSelf: 'flex-start' }}>+ Add Floor</button>
        </div>
      )}

      {activeTab === 'survivors' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {value.survivors.map((survivor, survivorIndex) => (
            <SurvivorBlock
              key={survivorIndex}
              survivor={survivor}
              onChange={(s) => updateSurvivor(survivorIndex, s)}
              onRemove={() => removeSurvivor(survivorIndex)}
              availableLocations={allRoomNames}
            />
          ))}
          <button type="button" onClick={addSurvivor} style={{ alignSelf: 'flex-start' }}>+ Add Survivor</button>
        </div>
      )}

      {activeTab === 'json' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ color: '#aebbc0', fontSize: '13px' }}>
            Copy this JSON to save your layout, or paste a new JSON configuration below and click Apply.
          </div>
          <textarea
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
            style={{ width: '100%', height: '300px', fontFamily: 'monospace', fontSize: '12px', padding: '8px', background: '#1c2328', color: '#e5e7eb', border: '1px solid #4b5962' }}
          />
          {jsonError && <div style={{ color: '#ff9999', fontSize: '13px' }}>{jsonError}</div>}
          <button type="button" className="primary-button" style={{ alignSelf: 'flex-start' }} onClick={() => {
            try {
              const parsed = JSON.parse(jsonText);
              if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.floors) || !Array.isArray(parsed.survivors)) {
                throw new Error("Invalid format: Must contain 'floors' and 'survivors' arrays.");
              }
              onChange(parsed as CustomLayoutRequest);
              setJsonError(null);
              setActiveTab('floors');
            } catch (err: any) {
              setJsonError(err.message || 'Invalid JSON format');
            }
          }}>
            Apply JSON
          </button>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────── Floor Block ────────────────────────── */

function FloorBlock({ floor, allRoomNames, onChange, onRemove }: { floor: FloorLayoutRequest; allRoomNames: string[]; onChange: (f: FloorLayoutRequest) => void; onRemove: () => void }) {
  const updateField = <K extends keyof FloorLayoutRequest>(key: K, val: FloorLayoutRequest[K]) => {
    onChange({ ...floor, [key]: val });
  };

  const addRoom = () => {
    const newRoom: RoomLayoutRequest = {
      name: `Room ${floor.rooms.length + 1}`,
      connects_to: [],
      hazards: {},
    };
    updateField('rooms', [...floor.rooms, newRoom]);
  };

  const updateRoom = (index: number, room: RoomLayoutRequest) => {
    const newRooms = [...floor.rooms];
    newRooms[index] = room;
    updateField('rooms', newRooms);
  };

  const removeRoom = (index: number) => {
    updateField('rooms', floor.rooms.filter((_, i) => i !== index));
  };

  return (
    <div style={{ border: '2px solid #4b5962', padding: '12px', background: '#1c2328' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, color: '#cce7d0' }}>Floor: {floor.name}</h3>
        <button type="button" onClick={onRemove} style={{ padding: '2px 6px', fontSize: '12px', borderColor: '#8b3f3f', color: '#ff9999' }}>Remove Floor</button>
      </div>
      <div className="field-row">
        <label>
          Floor ID
          <input value={floor.id} onChange={(e) => updateField('id', e.target.value)} />
        </label>
        <label>
          Name
          <input value={floor.name} onChange={(e) => updateField('name', e.target.value)} />
        </label>
        <label>
          Level
          <input type="number" value={floor.level} onChange={(e) => updateField('level', Number(e.target.value))} />
        </label>
      </div>
      
      <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <h4 style={{ margin: '0 0 8px 0', color: '#aebbc0' }}>Rooms</h4>
        {floor.rooms.map((room, roomIndex) => (
          <RoomBlock
            key={roomIndex}
            room={room}
            allRoomNames={allRoomNames}
            onChange={(r) => updateRoom(roomIndex, r)}
            onRemove={() => removeRoom(roomIndex)}
          />
        ))}
        <button type="button" onClick={addRoom} style={{ alignSelf: 'flex-start', marginTop: '8px' }}>+ Add Room</button>
      </div>
    </div>
  );
}

/* ────────────────────────── Room Block ────────────────────────── */

function RoomBlock({ room, allRoomNames, onChange, onRemove }: { room: RoomLayoutRequest; allRoomNames: string[]; onChange: (r: RoomLayoutRequest) => void; onRemove: () => void }) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const hazards = room.hazards || {};
  const blocked = room.blocked_by;

  const updateField = <K extends keyof RoomLayoutRequest>(key: K, val: RoomLayoutRequest[K]) => {
    onChange({ ...room, [key]: val });
  };

  const updateHazard = <K extends keyof RoomHazards>(key: K, val: RoomHazards[K]) => {
    updateField('hazards', { ...hazards, [key]: val });
  };

  const setBlockedBy = (enabled: boolean) => {
    if (enabled) {
      updateField('blocked_by', { type: 'rubble', status: 'blocking', required_location: '' });
    } else {
      updateField('blocked_by', null);
    }
  };

  const updateBlocked = <K extends keyof BlockedByConfig>(key: K, val: BlockedByConfig[K]) => {
    if (blocked) {
      updateField('blocked_by', { ...blocked, [key]: val });
    }
  };

  const hasHazards = hazards.electrical_hazard || (hazards.smoke && hazards.smoke !== 'none') || (hazards.structural_risk && hazards.structural_risk !== 'low') || (hazards.temperature && hazards.temperature !== 'normal');

  return (
    <div className="room-block" style={{ border: '1px solid #35424d', padding: '10px', background: '#12181d' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <strong style={{ color: '#fff' }}>{room.name || 'Unnamed Room'}</strong>
          {hasHazards && <span style={{ fontSize: '11px', color: '#f08c3a', border: '1px solid #f08c3a', padding: '1px 6px' }}>⚠ HAZARDS</span>}
          {blocked && <span style={{ fontSize: '11px', color: '#e15e4f', border: '1px solid #e15e4f', padding: '1px 6px' }}>🚧 BLOCKED</span>}
        </div>
        <button type="button" onClick={onRemove} style={{ padding: '2px 6px', fontSize: '12px', background: 'transparent', border: 'none', color: '#8b3f3f' }}>Remove</button>
      </div>

      {/* Row 1: Name + Connections */}
      <div className="field-row">
        <label>
          Name
          <input value={room.name} onChange={(e) => updateField('name', e.target.value)} />
        </label>
        <label>
          Connects To
          <CommaInput value={room.connects_to || []} onChange={(val) => updateField('connects_to', val)} />
        </label>
      </div>

      {/* Row 2: Hazards */}
      <div style={{ marginTop: '10px', borderTop: '1px solid #2a3a42', paddingTop: '10px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
          <span style={{ color: '#f5d36f', fontWeight: 600, fontSize: '13px' }}>⚠ Hazards & Conditions</span>
        </div>
        <div className="field-row">
          <label>
            Smoke
            <select value={hazards.smoke || 'none'} onChange={(e) => updateHazard('smoke', e.target.value as RoomHazards['smoke'])}>
              <option value="none">None</option>
              <option value="low">Low</option>
              <option value="light">Light</option>
              <option value="moderate">Moderate</option>
              <option value="heavy">Heavy</option>
            </select>
          </label>
          <label>
            Structural Risk
            <select value={hazards.structural_risk || 'low'} onChange={(e) => updateHazard('structural_risk', e.target.value as RoomHazards['structural_risk'])}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="severe">Severe</option>
            </select>
          </label>
          <label>
            Temperature
            <select value={hazards.temperature || 'normal'} onChange={(e) => updateHazard('temperature', e.target.value as RoomHazards['temperature'])}>
              <option value="normal">Normal</option>
              <option value="elevated">Elevated</option>
              <option value="hot">Hot</option>
            </select>
          </label>
        </div>
        <div style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
          <label className="checkbox-line">
            <input type="checkbox" checked={hazards.electrical_hazard || false} onChange={(e) => updateHazard('electrical_hazard', e.target.checked)} />
            ⚡ Electrical Hazard
          </label>
        </div>
      </div>

      {/* Row 3: Objects & Items */}
      <div className="field-row" style={{ marginTop: '8px' }}>
        <label>
          Objects
          <CommaInput value={room.objects || []} onChange={(val) => updateField('objects', val.length > 0 ? val : undefined)} />
        </label>
        <label>
          Items
          <CommaInput value={room.items || []} onChange={(val) => updateField('items', val.length > 0 ? val : undefined)} />
        </label>
      </div>

      {/* Advanced toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        style={{ marginTop: '8px', background: 'none', border: 'none', color: '#74b889', fontSize: '12px', cursor: 'pointer', padding: '2px 0' }}
      >
        {showAdvanced ? '▾ Hide' : '▸ Show'} advanced (cues, blockage)
      </button>

      {showAdvanced && (
        <div style={{ marginTop: '8px', borderTop: '1px solid #2a3a42', paddingTop: '8px' }}>
          {/* Sensory cues */}
          <div className="field-row">
            <label>
              Sounds
              <CommaInput value={room.sounds || []} onChange={(val) => updateField('sounds', val.length > 0 ? val : undefined)} />
            </label>
            <label>
              Vibration Cues
              <CommaInput value={room.vibration_cues || []} onChange={(val) => updateField('vibration_cues', val.length > 0 ? val : undefined)} />
            </label>
            <label>
              Survivor Cues
              <CommaInput value={room.survivor_cues || []} onChange={(val) => updateField('survivor_cues', val.length > 0 ? val : undefined)} />
            </label>
          </div>

          {/* Blocked by */}
          <div style={{ marginTop: '10px', borderTop: '1px solid #2a3a42', paddingTop: '8px' }}>
            <label className="checkbox-line">
              <input type="checkbox" checked={Boolean(blocked)} onChange={(e) => setBlockedBy(e.target.checked)} />
              🚧 Room is blocked / obstructed
            </label>
            {blocked && (
              <div className="field-row" style={{ marginTop: '8px' }}>
                <label>
                  Blockage Type
                  <select value={blocked.type} onChange={(e) => updateBlocked('type', e.target.value)}>
                    <option value="rubble">Rubble</option>
                    <option value="debris">Debris</option>
                    <option value="collapsed_wall">Collapsed Wall</option>
                    <option value="furniture">Furniture</option>
                  </select>
                </label>
                <label>
                  Status
                  <select value={blocked.status} onChange={(e) => updateBlocked('status', e.target.value)}>
                    <option value="blocking">Blocking</option>
                    <option value="partial">Partial</option>
                  </select>
                </label>
                <label>
                  Required Location
                  <select value={blocked.required_location} onChange={(e) => updateBlocked('required_location', e.target.value)}>
                    <option value="">— select —</option>
                    {allRoomNames.filter(n => n !== room.name).map(n => (
                      <option key={n} value={n}>{n}</option>
                    ))}
                  </select>
                </label>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ────────────────────────── Survivor Block ────────────────────────── */

function SurvivorBlock({ survivor, onChange, onRemove, availableLocations }: { survivor: SurvivorLayoutRequest; onChange: (s: SurvivorLayoutRequest) => void; onRemove: () => void; availableLocations: string[] }) {
  const updateField = <K extends keyof SurvivorLayoutRequest>(key: K, val: SurvivorLayoutRequest[K]) => {
    onChange({ ...survivor, [key]: val });
  };

  const priorityColor: Record<string, string> = {
    low: '#73c883',
    medium: '#d4b847',
    high: '#f08c3a',
    critical: '#e15e4f',
  };

  return (
    <div style={{ border: `2px solid ${priorityColor[survivor.priority] || '#51616a'}`, padding: '12px', background: '#12181d' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, color: priorityColor[survivor.priority] || '#f08c3a' }}>{survivor.name || survivor.id}</h3>
        <button type="button" onClick={onRemove} style={{ padding: '2px 6px', fontSize: '12px', borderColor: '#8b3f3f', color: '#ff9999' }}>Remove Survivor</button>
      </div>

      {/* Row 1: Identity */}
      <div className="field-row">
        <label>
          ID
          <input value={survivor.id} onChange={(e) => updateField('id', e.target.value)} />
        </label>
        <label>
          Name
          <input value={survivor.name || ''} onChange={(e) => updateField('name', e.target.value)} />
        </label>
        <label>
          Location
          <select value={survivor.location} onChange={(e) => updateField('location', e.target.value)}>
            {availableLocations.length === 0 && <option value={survivor.location}>{survivor.location}</option>}
            {availableLocations.map(loc => (
              <option key={loc} value={loc}>{loc}</option>
            ))}
          </select>
        </label>
      </div>

      {/* Row 2: State flags */}
      <div style={{ display: 'flex', gap: '16px', marginTop: '8px', flexWrap: 'wrap' }}>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.trapped} onChange={(e) => updateField('trapped', e.target.checked)} />
          Trapped
        </label>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.reachable ?? !survivor.trapped} onChange={(e) => updateField('reachable', e.target.checked)} />
          Reachable
        </label>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.conscious} onChange={(e) => updateField('conscious', e.target.checked)} />
          Conscious
        </label>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.responsive} onChange={(e) => updateField('responsive', e.target.checked)} />
          Responsive
        </label>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.can_walk} onChange={(e) => updateField('can_walk', e.target.checked)} />
          Can Walk
        </label>
      </div>

      {/* Row 3: Medical status */}
      <div style={{ marginTop: '10px', borderTop: '1px solid #2a3a42', paddingTop: '8px' }}>
        <span style={{ color: '#e15e4f', fontWeight: 600, fontSize: '13px', marginBottom: '6px', display: 'block' }}>🩺 Medical Status</span>
        <div className="field-row">
          <label>
            Breathing
            <select value={survivor.breathing_status} onChange={(e) => updateField('breathing_status', e.target.value)}>
              <option value="normal">Normal</option>
              <option value="fast">Fast</option>
              <option value="laboured">Laboured</option>
              <option value="not_breathing">Not Breathing</option>
            </select>
          </label>
          <label>
            Pulse
            <select value={survivor.pulse_status} onChange={(e) => updateField('pulse_status', e.target.value)}>
              <option value="normal">Normal</option>
              <option value="rapid">Rapid</option>
              <option value="weak">Weak</option>
              <option value="none">None</option>
            </select>
          </label>
          <label>
            Bleeding
            <select value={survivor.bleeding} onChange={(e) => updateField('bleeding', e.target.value)}>
              <option value="none">None</option>
              <option value="minor">Minor</option>
              <option value="severe">Severe</option>
            </select>
          </label>
        </div>
        <div className="field-row" style={{ marginTop: '8px' }}>
          <label>
            Priority
            <select value={survivor.priority} onChange={(e) => updateField('priority', e.target.value)}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </label>
          <label>
            Pain Level (0–10)
            <input type="number" min="0" max="10" value={survivor.pain_level} onChange={(e) => updateField('pain_level', Number(e.target.value))} />
          </label>
        </div>
      </div>

      {/* Row 4: Injuries */}
      <div style={{ marginTop: '8px' }}>
        <label>
          Suspected Injuries
          <CommaInput value={survivor.suspected_injuries || []} onChange={(val) => updateField('suspected_injuries', val)} />
        </label>
      </div>
    </div>
  );
}
