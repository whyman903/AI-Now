import { useQuery, useQueryClient } from "@tanstack/react-query";

export function useAuth() {
  const queryClient = useQueryClient();
  
  // Check if token exists to conditionally enable the query
  const token = localStorage.getItem('auth_token');
  
  const { data: user, isLoading, error } = useQuery({
    queryKey: ["/auth/me"],
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchInterval: false,
    enabled: !!token, // Only enable the query if we have a token
    queryFn: async () => {
      const API_BASE = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000';
      const token = localStorage.getItem('auth_token');
      
      // If no token exists, return null immediately without making request
      if (!token) {
        return null;
      }
      
      const response = await fetch(`${API_BASE}/api/v1/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        // Clear invalid token
        if (response.status === 401 || response.status === 403) {
          localStorage.removeItem('auth_token');
          return null;
        }
        
        throw new Error(`${response.status}: ${response.statusText}`);
      }

      return response.json();
    },
  });

  const logout = () => {
    localStorage.removeItem('auth_token');
    queryClient.setQueryData(["/auth/me"], null);
    queryClient.invalidateQueries({ queryKey: ["/auth/me"] });
  };

  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    error,
    logout,
  };
}
