// API configuration for frontend
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000',
  API_PREFIX: '/api/v1'
};

export const API_ENDPOINTS = {
  CONTENT: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/content`,
  SOURCES: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/sources`,
};
