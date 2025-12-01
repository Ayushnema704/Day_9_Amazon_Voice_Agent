import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Room, RoomEvent, TokenSource } from 'livekit-client';
import { AppConfig } from '@/app-config';
import { toastAlert } from '@/components/livekit/alert-toast';

export function useRoom(appConfig: AppConfig) {
  const aborted = useRef(false);
  const room = useMemo(() => new Room(), []);
  const [isSessionActive, setIsSessionActive] = useState(false);

  useEffect(() => {
    function onDisconnected() {
      setIsSessionActive(false);
    }

    function onMediaDevicesError(error: Error) {
      toastAlert({
        title: 'Encountered an error with your media devices',
        description: `${error.name}: ${error.message}`,
      });
    }

    room.on(RoomEvent.Disconnected, onDisconnected);
    room.on(RoomEvent.MediaDevicesError, onMediaDevicesError);

    // Diagnostic listeners to help debug connection lifecycle issues
    const onConnectionState = (state: string) => {
      console.info('[livekit-debug] connectionStateChanged', state);
    };

    const onReconnecting = () => {
      console.info('[livekit-debug] room reconnecting');
    };

    const onParticipantConnected = (p: any) => {
      try {
        console.info('[livekit-debug] participantConnected', p.identity, p.sid);
      } catch (e) {
        console.info('[livekit-debug] participantConnected', p);
      }
    };

    const onParticipantDisconnected = (p: any) => {
      try {
        console.info('[livekit-debug] participantDisconnected', p.identity, p.sid);
      } catch (e) {
        console.info('[livekit-debug] participantDisconnected', p);
      }
    };

    // Attach diagnostics (some events are available as strings too)
    try {
      // RoomEvent.ConnectionStateChanged is a newer enum; listen via string for compatibility
      // @ts-ignore
      room.on('connectionStateChanged', onConnectionState);
    } catch (e) {
      // ignore if not present in older SDK
    }
    room.on(RoomEvent.Reconnecting, onReconnecting);
    room.on(RoomEvent.ParticipantConnected, onParticipantConnected as any);
    room.on(RoomEvent.ParticipantDisconnected, onParticipantDisconnected as any);

    return () => {
      room.off(RoomEvent.Disconnected, onDisconnected);
      room.off(RoomEvent.MediaDevicesError, onMediaDevicesError);
      try {
        // @ts-ignore
        room.off('connectionStateChanged', onConnectionState);
      } catch (e) {
        // ignore
      }
      room.off(RoomEvent.Reconnecting, onReconnecting as any);
      room.off(RoomEvent.ParticipantConnected, onParticipantConnected as any);
      room.off(RoomEvent.ParticipantDisconnected, onParticipantDisconnected as any);
    };
  }, [room]);

  useEffect(() => {
    return () => {
      aborted.current = true;
      room.disconnect();
    };
  }, [room]);

  const tokenSource = useMemo(
    () =>
      TokenSource.custom(async () => {
        const url = new URL(
          process.env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT ?? '/api/connection-details',
          window.location.origin
        );

        try {
          const res = await fetch(url.toString(), {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-Sandbox-Id': appConfig.sandboxId ?? '',
            },
            body: JSON.stringify({
              room_config: appConfig.agentName
                ? {
                    agents: [{ agent_name: appConfig.agentName }],
                  }
                : undefined,
            }),
          });
          const payload = await res.json();
          // Log connection details for debug (do not print sensitive tokens in production)
          try {
            console.info('[livekit-debug] fetched connection details', {
              serverUrl: payload.serverUrl,
              roomName: payload.roomName,
              participantName: payload.participantName,
            });
          } catch (e) {
            // ignore
          }
          return payload;
        } catch (error) {
          console.error('Error fetching connection details:', error);
          throw new Error('Error fetching connection details!');
        }
      }),
    [appConfig]
  );

  const startSession = useCallback(() => {
    setIsSessionActive(true);

    if (room.state === 'disconnected') {
      const { isPreConnectBufferEnabled } = appConfig;
      Promise.all([
        room.localParticipant.setMicrophoneEnabled(true, undefined, {
          preConnectBuffer: isPreConnectBufferEnabled,
        }),
        tokenSource
          .fetch({ agentName: appConfig.agentName })
          .then((connectionDetails) => {
            // As a defensive measure in dev, if the server returned a non-unique
            // participant identity (rare), the server-side token generator already
            // creates a random identity. We log the connect attempt and then
            // connect the room using the provided token.
            console.info('[livekit-debug] connecting to', connectionDetails.serverUrl, 'room:', connectionDetails.roomName);
            return room.connect(connectionDetails.serverUrl, connectionDetails.participantToken);
          }),
      ]).catch((error) => {
        if (aborted.current) {
          // Once the effect has cleaned up after itself, drop any errors
          //
          // These errors are likely caused by this effect rerunning rapidly,
          // resulting in a previous run `disconnect` running in parallel with
          // a current run `connect`
          return;
        }

        toastAlert({
          title: 'There was an error connecting to the agent',
          description: `${error.name}: ${error.message}`,
        });
      });
    }
  }, [room, appConfig, tokenSource]);

  const endSession = useCallback(() => {
    setIsSessionActive(false);
  }, []);

  return { room, isSessionActive, startSession, endSession };
}
