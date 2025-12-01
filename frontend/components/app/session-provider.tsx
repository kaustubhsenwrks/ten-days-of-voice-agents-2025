'use client';

import { createContext, useContext, useMemo, useState } from 'react';
import { RoomContext } from '@livekit/components-react';
import { APP_CONFIG_DEFAULTS, type AppConfig } from '@/app-config';
import { useRoom } from '@/hooks/useRoom';

const SessionContext = createContext({
  appConfig: APP_CONFIG_DEFAULTS,
  isSessionActive: false,
  startSession: () => {},
  endSession: () => {},
  setPlayerName: (name: string) => {},
});

export function SessionProvider({ appConfig, children }) {
  const [playerName, setPlayerName] = useState("");

  const { room, isSessionActive, startSession, endSession } = useRoom(appConfig, playerName);


  const contextValue = useMemo(
    () => ({
      appConfig,       // ⭐ restored → SessionView now receives appConfig
      isSessionActive,
      startSession,
      endSession,
      setPlayerName,
    }),
    [appConfig, isSessionActive, startSession, endSession, setPlayerName]
  );

  return (
    <RoomContext.Provider value={room}>
      <SessionContext.Provider value={contextValue}>
        {children}
      </SessionContext.Provider>
    </RoomContext.Provider>
  );
}

export function useSession() {
  return useContext(SessionContext);
}