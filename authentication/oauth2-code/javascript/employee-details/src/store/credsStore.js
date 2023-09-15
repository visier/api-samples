import { create } from 'zustand';

const useCredsStore = create((set, get) => ({
    jwt: undefined,
    config: undefined,

    setJWT: jwt => set(state => ({
        ...state,
        jwt
    })),

    setConfig: config => set(state => ({
        ...state,
        config
    })),

    invalidateCreds: () => set(state => ({
        ...state,
        jwt: undefined,
        config: undefined
    })),

    isAuthenticated: () => get().jwt !== undefined,

    authHeader: () => {
        const { access_token, token_type } = get().jwt;
        return `${token_type} ${access_token}`
    }
}));

export default useCredsStore;