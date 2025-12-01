"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion } from "motion/react";
import { ChatTranscript } from "@/components/app/chat-transcript";
import { PreConnectMessage } from "@/components/app/preconnect-message";
import { TileLayout } from "@/components/app/tile-layout";
import {
  AgentControlBar,
  type ControlBarControls,
} from "@/components/livekit/agent-control-bar/agent-control-bar";
import { useChatMessages } from "@/hooks/useChatMessages";
import { useConnectionTimeout } from "@/hooks/useConnectionTimout";
import { useDebugMode } from "@/hooks/useDebug";
import { cn } from "@/lib/utils";
import { ScrollArea } from "../livekit/scroll-area/scroll-area";
import type { AppConfig } from "@/app-config";

interface SessionViewProps {
  playerName: string;
  appConfig: AppConfig;
}

export const SessionView = ({ playerName, appConfig }: SessionViewProps) => {
  useConnectionTimeout(200_000);
  useDebugMode({ enabled: process.env.NODE_ENV !== "production" });

  const messages = useChatMessages();
  const [chatOpen, setChatOpen] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  const controls: ControlBarControls = {
    leave: true,
    microphone: true,
    chat: appConfig.supportsChatInput,
    camera: appConfig.supportsVideoInput,
    screenShare: appConfig.supportsVideoInput,
  };

  return (
    <section className="bg-background relative z-10 h-full w-full overflow-hidden">
      {/* UI remains same */}
    </section>
  );
};