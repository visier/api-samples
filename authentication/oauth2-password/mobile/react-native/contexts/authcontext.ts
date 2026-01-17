import React from 'react';

type AuthContextType = {
    accessToken: string | null;
    setAccessToken: (accessToken: string) => void;
  };

  export const AuthContext = React.createContext<AuthContextType>({
    accessToken: null,
    setAccessToken: () => {},
  });