interface Props {
  stepIndex: number;
  maxIndex: number;
  playing: boolean;
  onChange: (index: number) => void;
  onTogglePlay: () => void;
  onReset: () => void;
}

export function ReplayControls({ stepIndex, maxIndex, playing, onChange, onTogglePlay, onReset }: Props) {
  return (
    <section className="panel replay-controls">
      <button onClick={() => onChange(0)}>Start</button>
      <button onClick={() => onChange(Math.max(0, stepIndex - 1))}>Previous</button>
      <button className="primary-button" onClick={onTogglePlay}>{playing ? 'Pause' : 'Play'}</button>
      <button onClick={() => onChange(Math.min(maxIndex, stepIndex + 1))}>Next</button>
      <button onClick={() => onChange(maxIndex)}>End</button>
      <button onClick={onReset}>Reset</button>
      <input type="range" min={0} max={maxIndex} value={stepIndex} onChange={(event) => onChange(Number(event.target.value))} />
      <span>{stepIndex} / {maxIndex}</span>
    </section>
  );
}
