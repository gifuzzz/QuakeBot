import { useEffect, useMemo, useState } from 'react';
import { getLayouts, getSnapshots, startEpisode, streamEpisode } from './api';
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

const defaultConfig: ScenarioConfigRequest = {
  agent_type: 'mock',
  active_floors: ['ground', 'floor_1', 'basement'],
  survivor_count_mode: 'exact',
  survivor_location_mode: 'known',
  survivor_count: 3,
  survivor_count_min: 3,
  survivor_count_max: 5,
  seed: 42,
  random_events_enabled: false,
  max_steps: 140,
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLayouts().then(setLayouts).catch((err: unknown) => setError(String(err)));
  }, []);

  useEffect(() => {
    if (!playing || snapshots.length === 0) return;
    const timer = window.setInterval(() => {
      setStepIndex((current) => {
        if (current >= snapshots.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 750);
    return () => window.clearInterval(timer);
  }, [playing, snapshots.length]);

  const snapshot = snapshots[stepIndex];
  const floorNames = useMemo(() => Object.keys(layouts?.visual.floors ?? {}), [layouts]);

  function start() {
    setLoading(true);
    setError(null);
    setSnapshots([]);
    setStepIndex(0);
    setEpisodeId("stream");
    
    streamEpisode(
      config,
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
      (err) => setError(String(err)),
      () => setLoading(false)
    );
  }

  function changeStep(index: number) {
    setStepIndex(index);
    const next = snapshots[index];
    if (next) setSelectedFloor(next.floor_name);
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>QuakeBot Mission Control / Replay Dashboard</h1>
          <p>React viewer consuming Python-owned rescue simulation snapshots.</p>
          <p style={{ fontSize: '0.8rem', color: '#ffb300' }}>Dashboard view: shows full replay state. Agent observations are restricted by scenario mode.</p>
        </div>
        <div className="episode-pill">{episodeId ? `Episode ${episodeId.slice(0, 8)}` : 'No episode loaded'}</div>
      </header>

      <aside className="left-rail">
        <ScenarioConfigPanel config={config} loading={loading} onChange={setConfig} onStart={start} />
        <Legend />
      </aside>

      <main className="main-stage">
        {error && <div className="error-banner">{error}</div>}
        {!snapshot && <div className="empty-state">Start an episode to load the pixel replay.</div>}
        {snapshot && layouts && (
          <>
            <ReplayControls
              stepIndex={stepIndex}
              maxIndex={snapshots.length - 1}
              playing={playing}
              onChange={changeStep}
              onTogglePlay={() => setPlaying((value) => !value)}
              onReset={() => changeStep(0)}
            />
            <FloorSelector floors={floorNames} selectedFloor={selectedFloor} onSelect={setSelectedFloor} />
            <PixelFloorMap floorName={selectedFloor} layout={layouts.visual.floors[selectedFloor]} snapshot={snapshot} />
            <CurrentActionPanel snapshot={snapshot} />
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
