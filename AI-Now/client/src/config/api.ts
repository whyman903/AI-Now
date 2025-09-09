// API configuration for frontend
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:8000',
  API_PREFIX: '/api/v1'
};

export const API_ENDPOINTS = {
  // Auth endpoints
  AUTH: {
    SIGNUP: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/auth/signup`,
    LOGIN: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/auth/login`,
    ME: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/auth/me`,
  },
  // Content endpoints  
  CONTENT: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/content`,
  // User endpoints
  USERS: `${API_CONFIG.BASE_URL}${API_CONFIG.API_PREFIX}/users`,
  // Other endpoints will be added as needed
};