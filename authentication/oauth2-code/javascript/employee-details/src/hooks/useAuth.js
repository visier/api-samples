"use client"
// hooks/useAuth.js
import { createContext, useContext, useState } from 'react';

// Create a context to hold the authentication state
const AuthContext = createContext();

// Custom hook to access the authentication context
export function useAuth() {
  return useContext(AuthContext);
}

// Provider component to wrap the entire application
export function AuthProvider({ children }) {
  const [accessToken, setAccessToken] = useState(null);
  const [tokenType, setTokenType] = useState(null);

  // Function to set the authentication state
  const setAuth = (newAccessToken, newTokenType) => {
    setAccessToken(newAccessToken);
    setTokenType(newTokenType);
  };

  const logout = () => {
    setAccessToken(null);
    setTokenType(null);
  };

  const isAuthenticated = () => {
    return accessToken !== null && tokenType !== null;
  };

  return (
    <AuthContext.Provider value={{ accessToken, tokenType, setAuth, logout, isAuthenticated }}>
      {children}
    </AuthContext.Provider>
  );
}
