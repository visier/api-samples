// Copyright 2023 Visier Solutions Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// This sample uses zustand to manage shared application state.
// Documentation: https://docs.pmnd.rs/zustand/getting-started/introduction
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