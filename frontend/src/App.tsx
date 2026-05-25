import { useEffect, useMemo, useState, useRef } from 'react';
import { getLayouts, saveReplay, streamEpisode, getReplays, loadReplay, previewEpisode } from './api';
import { starterCustomLayout } from './components/ScenarioConfigPanel';
import type { EpisodeSnapshot, LayoutsResponse, ScenarioConfigRequest } from './types';
import { CurrentActionPanel } from './components/CurrentActionPanel';
import { EventTimeline } from './components/EventTimeline';
import { FloorSelector } from './components/FloorSelector';
import { Legend } from './components/Legend';
import { MissionAccountingPanel } from './components/MissionAccountingPanel';
import { MissionLog } from './components/MissionLog';
import { PixelFloorMap } from './components/PixelFloorMap';
import { ReplayControls } from './components/ReplayControls';
import { RobotStatusPanel } from './components/RobotStatusPanel';
import { ScenarioConfigPanel } from './components/ScenarioConfigPanel';
import { SurvivorCards } from './components/SurvivorCards';
import { AgentObservationPanel } from './components/AgentObservationPanel';

const defaultConfig: ScenarioConfigRequest = {
  agent_type: 'mock',
  active_floors: starterCustomLayout.floors.map(f => f.id),
  survivor_count_mode: 'exact',
  survivor_location_mode: 'known',
  survivor_count: starterCustomLayout.survivors.length,
  survivor_count_min: starterCustomLayout.survivors.length,
  survivor_count_max: starterCustomLayout.survivors.length,
  seed: 42,
  random_events_enabled: false,
  max_steps: 140,
  custom_layout: starterCustomLayout,
  save_json: false,
};

export default function App() {
  const [config, setConfig] = useState<ScenarioConfigRequest>(defaultConfig);
  const [layouts, setLayouts] = useState<LayoutsResponse | null>(null);
  const [episodeId, setEpisodeId] = useState<string | null>(null);
  const [snapshots, setSnapshots] = useState<EpisodeSnapshot[]>([]);
  const [stepIndex, setStepIndex] = useState(0);
  const [selectedFloor, setSelectedFloor] = useState('Ground');
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [savingReplay, setSavingReplay] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [replays, setReplays] = useState<string[]>([]);
  const [previewSnapshot, setPreviewSnapshot] = useState<EpisodeSnapshot | null>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    previewEpisode(config).then(setPreviewSnapshot).catch(console.error);
  }, [config]);

  useEffect(() => {
    getLayouts().then(setLayouts).catch((err: unknown) => setError(String(err)));
    getReplays().then((data) => setReplays(data.replays)).catch((err: unknown) => console.error(err));
  }, []);

  useEffect(() => {
    if (!playing || snapshots.length === 0) return;
    const timer = window.setInterval(() => {
      setStepIndex((current) => {
        if (current >= snapshots.length - 1) {
          if (!loading) {
            setPlaying(false);
          }
          return current;
        }
        return current + 1;
      });
    }, 750);
    return () => window.clearInterval(timer);
  }, [playing, snapshots.length, loading]);

  useEffect(() => {
    if (playing && snapshots[stepIndex]) {
      setSelectedFloor(snapshots[stepIndex].floor_name);
    }
  }, [stepIndex, playing, snapshots]);

  const snapshot = snapshots[stepIndex];
  const activeSnapshot = snapshot || previewSnapshot;
  const floorNames = useMemo(() => {
    if (activeSnapshot) {
      const snapshotFloors = Array.from(new Set(Object.values(activeSnapshot.room_states).map((room) => room.floor_name)));
      if (snapshotFloors.length > 0) return snapshotFloors;
    }
    return Object.keys(layouts?.visual.floors ?? {});
  }, [layouts, activeSnapshot]);

  useEffect(() => {
    if (floorNames.length > 0 && !floorNames.includes(selectedFloor)) {
      setSelectedFloor(floorNames[0]);
    }
  }, [floorNames, selectedFloor]);

  function start(startConfig: ScenarioConfigRequest = config) {
    setLoading(true);
    setError(null);
    setSaveNotice(null);
    setSnapshots([]);
    setStepIndex(0);
    setPlaying(false);
    setEpisodeId("stream");
    
    if (stopStreamRef.current) {
      stopStreamRef.current();
    }
    
    stopStreamRef.current = streamEpisode(
      startConfig,
      (snapshot) => {
        setSnapshots((prev) => {
          const next = [...prev, snapshot];
          if (prev.length === 0) {
            setSelectedFloor(snapshot.floor_name);
            setPlaying(true);
          }
          return next;
        });
      },
      (err) => {
        setError(String(err));
        setLoading(false);
        stopStreamRef.current = null;
      },
      () => {
        setLoading(false);
        stopStreamRef.current = null;
      }
    );
  }

  function stop() {
    if (stopStreamRef.current) {
      stopStreamRef.current();
      stopStreamRef.current = null;
    }
    setLoading(false);
  }

  async function saveCurrentSimulation() {
    if (snapshots.length === 0) return;
    setSavingReplay(true);
    setError(null);
    setSaveNotice(null);
    try {
      const saved = await saveReplay(snapshots);
      const replayData = await getReplays();
      setReplays(replayData.replays);
      setSaveNotice(`Saved current simulation as ${saved.filename}`);
    } catch (err) {
      setError("Failed to save replay: " + String(err));
    } finally {
      setSavingReplay(false);
    }
  }

  function changeStep(index: number) {
    setStepIndex(index);
    const next = snapshots[index];
    if (next) setSelectedFloor(next.floor_name);
  }

  function handleReplaySelect(event: React.ChangeEvent<HTMLSelectElement>) {
    const filename = event.target.value;
    if (!filename) return;
    loadReplay(filename).then((data) => {
      if (Array.isArray(data) && data.length > 0 && 'step' in data[0]) {
        setSnapshots(data);
        setStepIndex(0);
        setEpisodeId(filename.replace('.json', ''));
        setPlaying(false);
        setError(null);
        setSelectedFloor(data[0].floor_name);
      } else {
        setError("Invalid replay file format");
      }
    }).catch((err) => setError("Failed to load replay: " + String(err)));
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>QuakeBot Mission Control / Replay Dashboard</h1>
          <p>React viewer consuming Python-owned rescue simulation snapshots.</p>
          <p style={{ fontSize: '0.8rem', color: '#ffb300' }}>Dashboard view: shows full replay state. Agent observations are restricted by scenario mode.</p>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', alignItems: 'flex-end' }}>
          <div className="episode-pill">{episodeId ? `Episode ${episodeId.slice(0, 8)}` : 'No episode loaded'}</div>
          <button
            type="button"
            onClick={saveCurrentSimulation}
            disabled={snapshots.length === 0 || savingReplay}
            style={{ cursor: snapshots.length === 0 || savingReplay ? 'not-allowed' : 'pointer', fontSize: '12px', padding: '4px 8px', background: 'transparent', border: '1px solid #74b889', color: '#74b889', borderRadius: '4px', opacity: snapshots.length === 0 || savingReplay ? 0.5 : 1 }}
          >
            {savingReplay ? 'Saving...' : 'Save Current Simulation'}
          </button>
          <select 
            onChange={handleReplaySelect} 
            value="" 
            style={{ cursor: 'pointer', fontSize: '12px', padding: '4px 8px', background: 'transparent', border: '1px solid #4a9eff', color: '#4a9eff', borderRadius: '4px', outline: 'none' }}
          >
            <option value="" disabled>Load Saved Replay</option>
            {replays.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
      </header>

      <aside className="left-rail">
        <ScenarioConfigPanel config={config} loading={loading} onChange={setConfig} onStart={start} onStop={stop} />
        <Legend />
      </aside>

      <main className="main-stage">
        {error && <div className="error-banner">{error}</div>}
        {saveNotice && <div className="panel" style={{ marginBottom: '12px', color: '#74b889' }}>{saveNotice}</div>}
        
        {layouts && (
          <>
            {snapshot && (
              <ReplayControls
                stepIndex={stepIndex}
                maxIndex={snapshots.length - 1}
                playing={playing}
                onChange={changeStep}
                onTogglePlay={() => setPlaying((value) => !value)}
                onReset={() => changeStep(0)}
              />
            )}
            
            <FloorSelector floors={floorNames} selectedFloor={selectedFloor} onSelect={setSelectedFloor} />
            <PixelFloorMap 
              floorName={selectedFloor} 
              layout={config.custom_layout ? undefined : layouts.visual.floors[selectedFloor]} 
              snapshot={activeSnapshot}
            />
            
            {snapshot ? (
              <>
                <CurrentActionPanel snapshot={snapshot} />
                <AgentObservationPanel snapshot={snapshot} />
                
                <section className="panel" style={{ marginTop: '14px' }}>
                  <h2>Full Action Log</h2>
                  <textarea 
                    readOnly 
                    value={snapshots.slice(0, stepIndex + 1).map(s => `[Step ${s.step}] ${s.action_description}\nResult: ${s.action_result}`).join('\n\n')} 
                    style={{ height: '200px', fontSize: '13px' }}
                    aria-label="Action log for copying"
                  />
                </section>
              </>
            ) : (
              <div className="empty-state">Click "Start Episode" to run the simulation.</div>
            )}
          </>
        )}
      </main>

      {snapshot && (
        <aside className="right-rail">
          <RobotStatusPanel snapshot={snapshot} />
          <MissionAccountingPanel snapshot={snapshot} />
          <SurvivorCards snapshot={snapshot} />
          <EventTimeline snapshots={snapshots.slice(0, stepIndex + 1)} />
          <MissionLog snapshot={snapshot} />
        </aside>
      )}
    </div>
  );
}
