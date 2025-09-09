import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { Podcast, Check } from "lucide-react";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { useMutation } from "@tanstack/react-query";
import { isUnauthorizedError } from "@/lib/authUtils";

const INTEREST_OPTIONS = [
  "Artificial Intelligence",
  "Technology",
  "Business",
  "Startups",
  "Science", 
  "Medicine",
  "Research",
  "Programming",
  "Design",
  "Marketing",
  "Finance",
  "Education",
  "Climate",
  "Space",
  "Cybersecurity",
  "Blockchain",
  "Data Science",
  "Machine Learning"
];

export default function Onboarding() {
  const [selectedInterests, setSelectedInterests] = useState<string[]>([]);
  const { toast } = useToast();

  const updateInterestsMutation = useMutation({
    mutationFn: async (interests: string[]) => {
      await apiRequest("PATCH", "/api/user/interests", { interests });
    },
    onSuccess: () => {
      toast({
        title: "Success",
        description: "Your interests have been saved!",
      });
      queryClient.invalidateQueries({ queryKey: ["/api/auth/user"] });
    },
    onError: (error) => {
      if (isUnauthorizedError(error)) {
        toast({
          title: "Unauthorized",
          description: "You are logged out. Logging in again...",
          variant: "destructive",
        });
        setTimeout(() => {
          window.location.href = "/api/login";
        }, 500);
        return;
      }
      toast({
        title: "Error",
        description: "Failed to save interests. Please try again.",
        variant: "destructive",
      });
    },
  });

  const toggleInterest = (interest: string) => {
    setSelectedInterests(prev =>
      prev.includes(interest)
        ? prev.filter(i => i !== interest)
        : [...prev, interest]
    );
  };

  const handleContinue = () => {
    if (selectedInterests.length === 0) {
      toast({
        title: "Select Interests",
        description: "Please select at least one interest to continue.",
        variant: "destructive",
      });
      return;
    }

    updateInterestsMutation.mutate(selectedInterests);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <Card className="w-full max-w-2xl">
        <CardHeader className="text-center">
          <div className="flex items-center justify-center space-x-2 mb-4">
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Podcast className="w-4 h-4 text-white" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">FeedCurator</h1>
          </div>
          <CardTitle className="text-2xl">Welcome! Let's personalize your feed</CardTitle>
          <p className="text-gray-600">
            Select your interests so we can curate the most relevant content for you
          </p>
        </CardHeader>

        <CardContent className="space-y-6">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">
              Choose your interests ({selectedInterests.length} selected)
            </h3>
            
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {INTEREST_OPTIONS.map((interest) => {
                const isSelected = selectedInterests.includes(interest);
                return (
                  <button
                    key={interest}
                    onClick={() => toggleInterest(interest)}
                    className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
                      isSelected
                        ? "bg-blue-50 border-blue-200 text-blue-900"
                        : "bg-white border-gray-200 text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    <span className="text-sm font-medium">{interest}</span>
                    {isSelected && <Check className="w-4 h-4 text-blue-600" />}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="pt-6 border-t">
            <Button
              onClick={handleContinue}
              disabled={selectedInterests.length === 0 || updateInterestsMutation.isPending}
              className="w-full"
              size="lg"
            >
              {updateInterestsMutation.isPending ? "Saving..." : "Continue to Feed"}
            </Button>
            
            <p className="text-xs text-gray-500 text-center mt-3">
              You can always change your interests later in settings
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
