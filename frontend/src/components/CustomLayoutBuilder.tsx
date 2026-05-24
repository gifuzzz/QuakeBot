import { useState } from 'react';
import type { CustomLayoutRequest, FloorLayoutRequest, RoomLayoutRequest, SurvivorLayoutRequest } from '../types';
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
      location: value.floors[0]?.rooms[0]?.name || 'Unknown',
      trapped: true,
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
              availableLocations={value.floors.flatMap(f => f.rooms.map(r => r.name))}
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

function FloorBlock({ floor, onChange, onRemove }: { floor: FloorLayoutRequest; onChange: (f: FloorLayoutRequest) => void; onRemove: () => void }) {
  const updateField = <K extends keyof FloorLayoutRequest>(key: K, val: FloorLayoutRequest[K]) => {
    onChange({ ...floor, [key]: val });
  };

  const addRoom = () => {
    const newRoom: RoomLayoutRequest = {
      name: `Room ${floor.rooms.length + 1}`,
      connects_to: [],
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
            onChange={(r) => updateRoom(roomIndex, r)}
            onRemove={() => removeRoom(roomIndex)}
          />
        ))}
        <button type="button" onClick={addRoom} style={{ alignSelf: 'flex-start', marginTop: '8px' }}>+ Add Room</button>
      </div>
    </div>
  );
}

function RoomBlock({ room, onChange, onRemove }: { room: RoomLayoutRequest; onChange: (r: RoomLayoutRequest) => void; onRemove: () => void }) {
  const updateField = <K extends keyof RoomLayoutRequest>(key: K, val: RoomLayoutRequest[K]) => {
    onChange({ ...room, [key]: val });
  };

  return (
    <div style={{ border: '1px solid #35424d', padding: '10px', background: '#12181d' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
        <strong style={{ color: '#fff' }}>{room.name || 'Unnamed Room'}</strong>
        <button type="button" onClick={onRemove} style={{ padding: '2px 6px', fontSize: '12px', background: 'transparent', border: 'none', color: '#8b3f3f' }}>Remove</button>
      </div>
      <div className="field-row">
        <label>
          Name
          <input value={room.name} onChange={(e) => updateField('name', e.target.value)} />
        </label>
        <label>
          Connects To (comma-separated)
          <CommaInput value={room.connects_to || []} onChange={(val) => updateField('connects_to', val)} />
        </label>
      </div>
      <div className="field-row" style={{ marginTop: '8px' }}>
        <label>
          Objects (comma-separated)
          <CommaInput value={room.objects || []} onChange={(val) => updateField('objects', val.length > 0 ? val : undefined)} />
        </label>
        <label>
          Sounds (comma-separated)
          <CommaInput value={room.sounds || []} onChange={(val) => updateField('sounds', val.length > 0 ? val : undefined)} />
        </label>
        <label>
          Survivor Cues (comma-separated)
          <CommaInput value={room.survivor_cues || []} onChange={(val) => updateField('survivor_cues', val.length > 0 ? val : undefined)} />
        </label>
      </div>
    </div>
  );
}

function SurvivorBlock({ survivor, onChange, onRemove, availableLocations }: { survivor: SurvivorLayoutRequest; onChange: (s: SurvivorLayoutRequest) => void; onRemove: () => void; availableLocations: string[] }) {
  const updateField = <K extends keyof SurvivorLayoutRequest>(key: K, val: SurvivorLayoutRequest[K]) => {
    onChange({ ...survivor, [key]: val });
  };

  return (
    <div style={{ border: '2px solid #51616a', padding: '12px', background: '#12181d' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, color: '#f08c3a' }}>{survivor.name || survivor.id}</h3>
        <button type="button" onClick={onRemove} style={{ padding: '2px 6px', fontSize: '12px', borderColor: '#8b3f3f', color: '#ff9999' }}>Remove Survivor</button>
      </div>
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
      <div className="field-row" style={{ marginTop: '8px' }}>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.trapped} onChange={(e) => updateField('trapped', e.target.checked)} />
          Trapped
        </label>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.conscious} onChange={(e) => updateField('conscious', e.target.checked)} />
          Conscious
        </label>
        <label className="checkbox-line">
          <input type="checkbox" checked={survivor.responsive} onChange={(e) => updateField('responsive', e.target.checked)} />
          Responsive
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
          Pain Level (0-10)
          <input type="number" min="0" max="10" value={survivor.pain_level} onChange={(e) => updateField('pain_level', Number(e.target.value))} />
        </label>
      </div>
      <div className="field-row" style={{ marginTop: '8px' }}>
        <label>
          Injuries (comma-separated)
          <CommaInput value={survivor.suspected_injuries || []} onChange={(val) => updateField('suspected_injuries', val)} />
        </label>
      </div>
    </div>
  );
}
