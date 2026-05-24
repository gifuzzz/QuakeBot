import { useEffect, useState } from 'react';

interface Props {
  value: string[];
  onChange: (val: string[]) => void;
  disabled?: boolean;
}

export function CommaInput({ value, onChange, disabled }: Props) {
  const [text, setText] = useState((value || []).join(', '));

  useEffect(() => {
    const propString = (value || []).join(', ');
    const currentParsed = text.split(',').map(s => s.trim()).filter(Boolean).join(', ');
    if (propString !== currentParsed) {
      setText(propString);
    }
  }, [value, text]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newText = e.target.value;
    setText(newText);
    onChange(newText.split(',').map(s => s.trim()).filter(Boolean));
  };

  const handleBlur = () => {
    setText((value || []).join(', '));
  };

  return (
    <input 
      value={text} 
      onChange={handleChange} 
      onBlur={handleBlur} 
      disabled={disabled} 
    />
  );
}
