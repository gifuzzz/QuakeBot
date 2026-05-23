interface Props {
  floors: string[];
  selectedFloor: string;
  onSelect: (floor: string) => void;
}

export function FloorSelector({ floors, selectedFloor, onSelect }: Props) {
  return (
    <div className="floor-selector">
      {floors.map((floor) => (
        <button key={floor} className={floor === selectedFloor ? 'active' : ''} onClick={() => onSelect(floor)}>
          {floor}
        </button>
      ))}
    </div>
  );
}
