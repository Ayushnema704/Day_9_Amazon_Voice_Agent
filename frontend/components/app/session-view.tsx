'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import type { AppConfig } from '@/app-config';
import { ChatTranscript } from '@/components/app/chat-transcript';
import { PreConnectMessage } from '@/components/app/preconnect-message';
import { TileLayout } from '@/components/app/tile-layout';
import {
  AgentControlBar,
  type ControlBarControls,
} from '@/components/livekit/agent-control-bar/agent-control-bar';
import { useChatMessages } from '@/hooks/useChatMessages';
import { useTextStream } from '@livekit/components-react';
import { useRoomContext, useChat } from '@livekit/components-react';
import { useConnectionTimeout } from '@/hooks/useConnectionTimout';
import { useDebugMode } from '@/hooks/useDebug';
import { cn } from '@/lib/utils';
import { ScrollArea } from '../livekit/scroll-area/scroll-area';

const MotionBottom = motion.create('div');

const IN_DEVELOPMENT = process.env.NODE_ENV !== 'production';
const BOTTOM_VIEW_MOTION_PROPS = {
  variants: {
    visible: {
      opacity: 1,
      translateY: '0%',
    },
    hidden: {
      opacity: 0,
      translateY: '100%',
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.3,
    delay: 0.5,
    ease: 'easeOut',
  },
};

interface FadeProps {
  top?: boolean;
  bottom?: boolean;
  className?: string;
}

export function Fade({ top = false, bottom = false, className }: FadeProps) {
  return (
    <div
      className={cn(
        'from-background pointer-events-none h-4 bg-linear-to-b to-transparent',
        top && 'bg-linear-to-b',
        bottom && 'bg-linear-to-t',
        className
      )}
    />
  );
}
interface SessionViewProps {
  appConfig: AppConfig;
}

export const SessionView = ({
  appConfig,
  ...props
}: React.ComponentProps<'section'> & SessionViewProps) => {
  useConnectionTimeout(200_000);
  useDebugMode({ enabled: IN_DEVELOPMENT });

  // Centralize text-stream registration here to avoid duplicate handler errors
  // (register handlers once per room/topic). We pass the resulting textStreams
  // into the `useChatMessages` hook so it can merge them with other sources.
  // NOTE: some LiveKit client versions will throw if a handler for the same
  // topic is registered multiple times (dev/StrictMode double-mount). Wrap
  // the hook call in a try/catch and fall back to empty arrays if registration
  // fails so the UI won't crash.
  let chatTextStreams: any[] = [];
  let legacyChatTextStreams: any[] = [];
  try {
    const _chat = useTextStream('lk.chat');
    chatTextStreams = _chat?.textStreams ?? [];
  } catch (e) {
    // eslint-disable-next-line no-console
    console.debug('useTextStream(lk.chat) registration failed, continuing without it', e);
    chatTextStreams = [];
  }

  try {
    const _legacy = useTextStream('lk-chat-topic');
    legacyChatTextStreams = _legacy?.textStreams ?? [];
  } catch (e) {
    // eslint-disable-next-line no-console
    console.debug('useTextStream(lk-chat-topic) registration failed, continuing without it', e);
    legacyChatTextStreams = [];
  }

  const messages = useChatMessages({ chatTextStreams, legacyChatTextStreams });
  const room = useRoomContext();
  const chat = useChat();
  // Guard: some LiveKit client versions throw when the same text stream
  // handler is registered more than once. Patch the room's
  // `registerTextStreamHandler` to swallow the duplicate-handler error so
  // the UI doesn't crash in StrictMode or when multiple components subscribe.
  React.useEffect(() => {
    if (!room) return undefined;
    try {
      const r: any = room as any;
      if (r && typeof r.registerTextStreamHandler === 'function') {
        const orig = r.registerTextStreamHandler.bind(r);
        r.registerTextStreamHandler = (topic: string, handler: any) => {
          try {
            return orig(topic, handler);
          } catch (err: any) {
            const message = String(err?.message ?? err);
            if (message.includes('already been set') || message.includes('already registered') || message.includes('A text stream handler')) {
              // eslint-disable-next-line no-console
              console.debug('Ignored duplicate text stream handler registration for topic', topic, err);
              return null;
            }
            throw err;
          }
        };
      }
    } catch (e) {
      // ignore patch failure
    }
    return undefined;
  }, [room]);
  const [chatOpen, setChatOpen] = useState(true);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  const [assistantThinking, setAssistantThinking] = useState(false);
  const thinkingTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const onUserSent = () => {
      // show typing indicator
      setAssistantThinking(true);
      if (thinkingTimeoutRef.current) window.clearTimeout(thinkingTimeoutRef.current);
      // fallback: clear after 8s if no response
      thinkingTimeoutRef.current = window.setTimeout(() => {
        setAssistantThinking(false);
        thinkingTimeoutRef.current = null;
      }, 8000);
    };

    window.addEventListener('user-sent-chat', onUserSent as EventListener);
    return () => {
      window.removeEventListener('user-sent-chat', onUserSent as EventListener);
      if (thinkingTimeoutRef.current) window.clearTimeout(thinkingTimeoutRef.current);
    };
  }, []);

  const controls: ControlBarControls = {
    leave: true,
    microphone: true,
    chat: appConfig.supportsChatInput,
    camera: appConfig.supportsVideoInput,
    screenShare: appConfig.supportsVideoInput,
  };

  useEffect(() => {
    const lastMessage = messages.at(-1);
    const lastMessageIsLocal = lastMessage?.from?.isLocal === true;

    if (scrollAreaRef.current && lastMessageIsLocal) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }

    // If an assistant message arrived, hide the thinking indicator
    try {
      const last = messages.at(-1);
      const from = last?.from;
      const isAssistant = Boolean(
        from && (from.isAgent || from.identity?.startsWith?.('agent-') || (from._attributes && from._attributes['lk.agent.state']))
      );
      if (isAssistant) {
        setAssistantThinking(false);
        if (thinkingTimeoutRef.current) {
          window.clearTimeout(thinkingTimeoutRef.current);
          thinkingTimeoutRef.current = null;
        }
      }
    } catch (e) {
      /* ignore */
    }
  }, [messages]);

  return (
    <section className="relative z-10 h-full w-full overflow-hidden" style={{ backgroundColor: '#161d28' }} {...props}>
      {/* Chat Transcript */}
      <div
        className={cn(
          'fixed inset-0 grid grid-cols-1 grid-rows-1',
          !chatOpen && 'pointer-events-none'
        )}
      >
        <Fade top className="absolute inset-x-4 top-0 h-40" />
        <ScrollArea ref={scrollAreaRef} className="px-4 pt-40 pb-[150px] md:px-6 md:pb-[180px]">
          <ChatTranscript
            hidden={!chatOpen}
            messages={messages}
            className="mx-auto max-w-2xl space-y-3 transition-opacity duration-300 ease-out text-white"
            style={{ color: 'white' }}
          />
          {/* Dev-only debug panel removed for production UX */}
        </ScrollArea>
      </div>

      {/* Tile Layout */}
      <TileLayout chatOpen={chatOpen} />

      {/* Bottom */}
      <MotionBottom
        {...BOTTOM_VIEW_MOTION_PROPS}
        className="fixed inset-x-3 bottom-0 z-50 md:inset-x-12"
      >
        {appConfig.isPreConnectBufferEnabled && (
          <PreConnectMessage messages={messages} className="pb-4" />
        )}
        <div className="bg-background relative mx-auto max-w-2xl pb-3 md:pb-12">
          <Fade bottom className="absolute inset-x-0 top-0 h-4 -translate-y-full" />
          <AgentControlBar controls={controls} onChatOpenChange={setChatOpen} />
        </div>
      </MotionBottom>
    </section>
  );
};
