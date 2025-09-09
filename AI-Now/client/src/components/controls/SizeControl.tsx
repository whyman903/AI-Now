import { useState } from "react";
import { Slider } from "@/components/ui/slider";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";

interface SizeControlProps {
  onSizeChange: (size: number) => void;
  initialSize?: number;
}

export function SizeControl({ onSizeChange, initialSize = 1 }: SizeControlProps) {
  const [size, setSize] = useState([initialSize]);

  const handleSizeChange = (value: number[]) => {
    setSize(value);
    onSizeChange(value[0]);
  };

  const getSizeLabel = (value: number) => {
    if (value <= 0.7) return "Small";
    if (value <= 1.3) return "Medium";
    return "Large";
  };

  return (
    <Card className="p-4 w-64">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label htmlFor="size-slider" className="text-sm font-medium">
            Card Size
          </Label>
          <span className="text-xs text-muted-foreground">
            {getSizeLabel(size[0])}
          </span>
        </div>
        <Slider
          id="size-slider"
          min={0.5}
          max={2.0}
          step={0.1}
          value={size}
          onValueChange={handleSizeChange}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>Small</span>
          <span>Large</span>
        </div>
      </div>
    </Card>
  );
}