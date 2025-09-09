import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Check, Plus } from "lucide-react";

interface InterestSelectorProps {
  interests: string[];
  selectedInterests: string[];
  onSelectionChange: (interests: string[]) => void;
  maxSelections?: number;
}

export default function InterestSelector({
  interests,
  selectedInterests,
  onSelectionChange,
  maxSelections = 10,
}: InterestSelectorProps) {
  const toggleInterest = (interest: string) => {
    const isSelected = selectedInterests.includes(interest);
    
    if (isSelected) {
      onSelectionChange(selectedInterests.filter(i => i !== interest));
    } else if (selectedInterests.length < maxSelections) {
      onSelectionChange([...selectedInterests, interest]);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          Select Your Interests
        </h3>
        <span className="text-sm text-gray-500">
          {selectedInterests.length}/{maxSelections} selected
        </span>
      </div>
      
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {interests.map((interest) => {
          const isSelected = selectedInterests.includes(interest);
          const isMaxReached = selectedInterests.length >= maxSelections && !isSelected;
          
          return (
            <Button
              key={interest}
              variant="outline"
              size="sm"
              onClick={() => toggleInterest(interest)}
              disabled={isMaxReached}
              className={`flex items-center justify-between p-3 h-auto ${
                isSelected
                  ? "bg-blue-50 border-blue-200 text-blue-900"
                  : "hover:bg-gray-50"
              } ${isMaxReached ? "opacity-50 cursor-not-allowed" : ""}`}
            >
              <span className="text-sm font-medium">{interest}</span>
              {isSelected ? (
                <Check className="w-4 h-4 text-blue-600" />
              ) : (
                <Plus className="w-4 h-4 text-gray-400" />
              )}
            </Button>
          );
        })}
      </div>
    </div>
  );
}
