'use client';

import { type HTMLAttributes, useCallback, useState } from 'react';
import { Track } from 'livekit-client';
import { useChat, useRemoteParticipants, useRoomContext } from '@livekit/components-react';
import { ChatTextIcon, PhoneDisconnectIcon } from '@phosphor-icons/react/dist/ssr';
import { useSession } from '@/components/app/session-provider';
import { TrackToggle } from '@/components/livekit/agent-control-bar/track-toggle';
import { Button } from '@/components/livekit/button';
import { Toggle } from '@/components/livekit/toggle';
import { cn } from '@/lib/utils';
import { ChatInput } from './chat-input';
import { UseInputControlsProps, useInputControls } from './hooks/use-input-controls';
import { usePublishPermissions } from './hooks/use-publish-permissions';
import { TrackSelector } from './track-selector';

export interface ControlBarControls {
  leave?: boolean;
  camera?: boolean;
  microphone?: boolean;
  screenShare?: boolean;
  chat?: boolean;
}

export interface AgentControlBarProps extends UseInputControlsProps {
  controls?: ControlBarControls;
  onDisconnect?: () => void;
  onChatOpenChange?: (open: boolean) => void;
  onDeviceError?: (error: { source: Track.Source; error: Error }) => void;
}

/**
 * A control bar specifically designed for voice assistant interfaces
 */
export function AgentControlBar({
  controls,
  saveUserChoices = true,
  className,
  onDisconnect,
  onDeviceError,
  onChatOpenChange,
  ...props
}: AgentControlBarProps & HTMLAttributes<HTMLDivElement>) {
  const { send } = useChat();
  const participants = useRemoteParticipants();
  const room = useRoomContext();
  const [chatOpen, setChatOpen] = useState(false);
  const publishPermissions = usePublishPermissions();
  const { isSessionActive, endSession } = useSession();

  const {
    micTrackRef,
    cameraToggle,
    microphoneToggle,
    screenShareToggle,
    handleAudioDeviceChange,
    handleVideoDeviceChange,
    handleMicrophoneDeviceSelectError,
    handleCameraDeviceSelectError,
  } = useInputControls({ onDeviceError, saveUserChoices });

  const handleSendMessage = async (message: string) => {
    // Debug: log attempt
    try {
      // eslint-disable-next-line no-console
      console.info('[AgentControlBar] handleSendMessage called, message:', message);
      await send(message);
      // eslint-disable-next-line no-console
      console.info('[AgentControlBar] useChat.send completed');
    } catch (e) {
      // ensure this doesn't break the UI
      // eslint-disable-next-line no-console
      console.info('useChat.send failed, continuing to publish data fallback', e);
    }

    // Best-effort: also publish to data channels/text streams so the agent
    // and other participants receive the typed chat even if one path fails.
    try {
      const lp: any = room?.localParticipant;
      if (lp) {
        const payload = new TextEncoder().encode(message);

        const tryPublishToTopic = async (topic: string) => {
          const fn = lp.publishData || lp.publishData?.bind(lp) || lp.sendData || lp.sendData?.bind(lp) || lp.sendData;
          if (!fn || typeof fn !== 'function') return false;

          const attempts: Array<() => Promise<void>> = [
            // common option-based signature
            async () => await fn(payload, { topic, reliable: true }),
            async () => await fn(payload, { topic }),
            // some SDKs accept (data, topic, reliable)
            async () => await fn(payload, topic, true),
            async () => await fn(payload, topic),
            // fallback: publish raw
            async () => await fn(payload),
          ];

          for (const attempt of attempts) {
            try {
              // eslint-disable-next-line no-await-in-loop
              await attempt();
              return true;
            } catch (err) {
              // try next signature
            }
          }

          return false;
        };

        // try both common topics
        try {
          await tryPublishToTopic('lk-chat-topic');
        } catch (e2) {
          // ignore
        }


        // Dispatch a lightweight event to show UI that the assistant is processing
        try {
          if (typeof window !== 'undefined' && window.dispatchEvent) {
            // eslint-disable-next-line no-console
            console.info('[AgentControlBar] dispatching user-sent-chat');
            window.dispatchEvent(new CustomEvent('user-sent-chat'));
          }
        } catch (e) {
          /* ignore */
        }
        try {
          await tryPublishToTopic('lk.chat');
        } catch (e3) {
          // ignore
        }
        // Also dispatch a local-chat-message event so the UI shows the
        // user's typed message immediately as a local message fallback.
        try {
          if (typeof window !== 'undefined' && window.dispatchEvent) {
            // eslint-disable-next-line no-console
            console.info('[AgentControlBar] dispatching local-chat-message', message);
            window.dispatchEvent(new CustomEvent('local-chat-message', { detail: { message } }));
          }
        } catch (e) {
          /* ignore */
        }
      }
    } catch (e) {
      // eslint-disable-next-line no-console
      console.debug('failed to publish typed chat as data fallback', e);
    }
  };

  const handleToggleTranscript = useCallback(
    (open: boolean) => {
      setChatOpen(open);
      onChatOpenChange?.(open);
    },
    [onChatOpenChange, setChatOpen]
  );

  const handleDisconnect = useCallback(async () => {
    endSession();
    onDisconnect?.();
  }, [endSession, onDisconnect]);

  const visibleControls = {
    leave: controls?.leave ?? true,
    microphone: controls?.microphone ?? publishPermissions.microphone,
    screenShare: controls?.screenShare ?? publishPermissions.screenShare,
    camera: controls?.camera ?? publishPermissions.camera,
    chat: controls?.chat ?? publishPermissions.data,
  };

  const isAgentAvailable = participants.some((p) => p.isAgent);

  return (
    <div
      aria-label="Voice assistant controls"
      className={cn(
        'bg-background border-input/50 dark:border-muted flex flex-col rounded-[31px] border p-3 drop-shadow-md/3',
        className
      )}
      {...props}
    >
      {/* Chat Input */}
      {visibleControls.chat && (
        <ChatInput
          chatOpen={chatOpen}
          isAgentAvailable={isAgentAvailable}
          onSend={handleSendMessage}
        />
      )}

      <div className="flex gap-1">
        <div className="flex grow gap-1">
          {/* Toggle Microphone */}
          {visibleControls.microphone && (
            <TrackSelector
              kind="audioinput"
              aria-label="Toggle microphone"
              source={Track.Source.Microphone}
              pressed={microphoneToggle.enabled}
              disabled={microphoneToggle.pending}
              audioTrackRef={micTrackRef}
              onPressedChange={microphoneToggle.toggle}
              onMediaDeviceError={handleMicrophoneDeviceSelectError}
              onActiveDeviceChange={handleAudioDeviceChange}
            />
          )}

          {/* Toggle Camera */}
          {visibleControls.camera && (
            <TrackSelector
              kind="videoinput"
              aria-label="Toggle camera"
              source={Track.Source.Camera}
              pressed={cameraToggle.enabled}
              pending={cameraToggle.pending}
              disabled={cameraToggle.pending}
              onPressedChange={cameraToggle.toggle}
              onMediaDeviceError={handleCameraDeviceSelectError}
              onActiveDeviceChange={handleVideoDeviceChange}
            />
          )}

          {/* Toggle Screen Share */}
          {visibleControls.screenShare && (
            <TrackToggle
              size="icon"
              variant="secondary"
              aria-label="Toggle screen share"
              source={Track.Source.ScreenShare}
              pressed={screenShareToggle.enabled}
              disabled={screenShareToggle.pending}
              onPressedChange={screenShareToggle.toggle}
            />
          )}

          {/* Toggle Transcript */}
          <Toggle
            size="icon"
            variant="secondary"
            aria-label="Toggle transcript"
            pressed={chatOpen}
            onPressedChange={handleToggleTranscript}
          >
            <ChatTextIcon weight="bold" />
          </Toggle>
        </div>

        {/* Disconnect */}
        {visibleControls.leave && (
          <Button
            variant="destructive"
            onClick={handleDisconnect}
            disabled={!isSessionActive}
            className="font-mono"
          >
            <PhoneDisconnectIcon weight="bold" />
            <span className="hidden md:inline">END CALL</span>
            <span className="inline md:hidden">END</span>
          </Button>
        )}
      </div>
    </div>
  );
}
