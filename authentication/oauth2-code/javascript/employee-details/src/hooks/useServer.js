"use client"
import { createContext, useContext, useState } from 'react';

const ServerContext = createContext();

export function useServer() {
    return useContext(ServerContext);
}

export function ServerProvider({ children}) {
    const [instance, setInstance] = useState(null);

    const setServerInstance = newInstance => {
        setInstance(newInstance);
    }

    const isAuthenticated = () => {
        return instance !== null;
    }

    return (
        <ServerContext.Provider value={{ instance, setServerInstance, isAuthenticated}}>
            {children}
        </ServerContext.Provider>
    );
}