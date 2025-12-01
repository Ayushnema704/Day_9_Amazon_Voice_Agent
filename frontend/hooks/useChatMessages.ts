import { useMemo, useEffect, useState, useCallback } from 'react';
import { Room } from 'livekit-client';
import {
  type ReceivedChatMessage,
  type TextStreamData,
  useChat,
  useRoomContext,
  useTranscriptions,
} from '@livekit/components-react';

function transcriptionToChatMessage(textStream: TextStreamData, room: Room): ReceivedChatMessage {
  return {
    id: textStream.streamInfo.id,
    timestamp: textStream.streamInfo.timestamp,
    message: textStream.text,
    from:
      textStream.participantInfo.identity === room.localParticipant.identity
        ? room.localParticipant
        : Array.from(room.remoteParticipants.values()).find(
            (p) => p.identity === textStream.participantInfo.identity
          ),
  };
}

export type UseChatMessagesOptions = {
  chatTextStreams?: TextStreamData[];
  legacyChatTextStreams?: TextStreamData[];
};

export function useChatMessages(options?: UseChatMessagesOptions) {
  const chat = useChat();
  const room = useRoomContext();
  const transcriptions: TextStreamData[] = useTranscriptions();
  const chatTextStreams: TextStreamData[] = options?.chatTextStreams ?? [];
  const legacyChatTextStreams: TextStreamData[] = options?.legacyChatTextStreams ?? [];
  const [dataMessages, setDataMessages] = useState<Array<ReceivedChatMessage>>([]);

  const addDataMessage = useCallback((msg: ReceivedChatMessage) => {
    setDataMessages((prev) => {
      // simple dedupe: avoid identical message text within the last 5 messages
      const recent = prev.slice(-5).map((m) => m.message);
      if (recent.includes(msg.message)) return prev;
      return [...prev, msg];
    });
  }, []);

  const mergedTranscriptions = useMemo(() => {
    // Debug: show raw sources
    try {
      // eslint-disable-next-line no-console
      console.info('[useChatMessages] transcriptions count', transcriptions?.length ?? 0, 'chatMessages count', chat?.chatMessages?.length ?? 0, 'room', room?.name);
    } catch (e) {
      /* ignore */
    }

    const merged: Array<ReceivedChatMessage> = [
      // text stream sources (chat & legacy chat topic)
      ...chatTextStreams.map((ts) => transcriptionToChatMessage(ts, room)),
      ...legacyChatTextStreams.map((ts) => transcriptionToChatMessage(ts, room)),
      ...transcriptions.map((transcription) => transcriptionToChatMessage(transcription, room)),
      ...chat.chatMessages,
      ...dataMessages,
    ];

    const sorted = merged.sort((a, b) => a.timestamp - b.timestamp);

    // Collapse near-duplicate messages coming from different sources
    // (text stream, data channel, local fallback). If two messages have
    // identical text and originate from the same sender (or both local)
    // within a short timeframe, prefer the earliest and drop the duplicate.
    const deduped: Array<ReceivedChatMessage> = [];
    for (const msg of sorted) {
      const last = deduped[deduped.length - 1];
      if (last) {
        const sameText = (last.message || '').trim() === (msg.message || '').trim();
        const timeClose = Math.abs((msg.timestamp || 0) - (last.timestamp || 0)) <= 2000; // 2s window
        const sameSender = (() => {
          try {
            const a = last.from?.identity ?? last.from?.id ?? (last.from === room.localParticipant ? 'local' : undefined);
            const b = msg.from?.identity ?? msg.from?.id ?? (msg.from === room.localParticipant ? 'local' : undefined);
            return a && b && String(a) === String(b);
          } catch (e) {
            return false;
          }
        })();

        if (sameText && timeClose && (sameSender || (!last.from && !msg.from))) {
          // duplicate — skip adding
          continue;
        }
      }
      deduped.push(msg);
    }

    return deduped;
  }, [transcriptions, chat.chatMessages, room, chatTextStreams, legacyChatTextStreams, dataMessages]);

  useEffect(() => {
    try {
      // eslint-disable-next-line no-console
      console.info('[useChatMessages] mergedTranscriptions', mergedTranscriptions);
    } catch (e) {
      /* ignore */
    }
  }, [mergedTranscriptions]);

  // Debug: attach raw data/data-channel listeners to the room so we can
  // observe any incoming text published by the backend (reliable or lossy).
  useEffect(() => {
    if (!room) return undefined;

    const r: any = room as any;

    const decodePayloadToString = (payload: any): string | null => {
      try {
        if (!payload && payload !== 0) return null;
        if (typeof payload === 'string') return payload;
        if (payload instanceof ArrayBuffer) return new TextDecoder().decode(new Uint8Array(payload));
        if (payload instanceof Uint8Array) return new TextDecoder().decode(payload);
        // Some SDKs pass { data: { '0': 106, ... } } or an array
        if (typeof payload === 'object') {
          const data = (payload as any).data ?? payload;
          if (!data) return null;
          if (data instanceof Uint8Array) return new TextDecoder().decode(data);
          if (data instanceof ArrayBuffer) return new TextDecoder().decode(new Uint8Array(data));
          if (Array.isArray(data)) return new TextDecoder().decode(new Uint8Array(data));
          // object with numeric keys
          const keys = Object.keys(data).map((k) => parseInt(k, 10)).filter((n) => !Number.isNaN(n)).sort((a, b) => a - b);
          if (keys.length) {
            const arr = new Uint8Array(keys.length);
            keys.forEach((k, i) => {
              arr[i] = data[k];
            });
            return new TextDecoder().decode(arr);
          }
        }
      } catch (e) {
        // ignore
      }
      return null;
    };

    const rawHandler = (payload: any, participant?: any) => {
      try {
        const decoded = decodePayloadToString(payload);
        // eslint-disable-next-line no-console
        console.debug('[room.dataReceived] payload:', decoded ?? payload, 'from:', participant?.identity ?? participant);

        if (decoded && decoded.length > 0) {
          // build a ReceivedChatMessage-like object and add to dataMessages
          const id = `data-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
          const ts = Date.now();
          // try to find an agent participant as the sender
          let sender = null;
          try {
            const remotes = Array.from(room.remoteParticipants.values());
            sender = remotes.find((p: any) => {
              try {
                // check common attributes
                if (p._attributes && (p._attributes['lk.agent.state'] || p._attributes['lk.agent.state'] === 'listening')) return true;
                if (p.kind === 'AGENT' || p._kind === 4) return true;
                if (typeof p.identity === 'string' && p.identity.startsWith('agent-')) return true;
                return false;
              } catch (e) {
                return false;
              }
            }) || remotes[0];
          } catch (e) {
            sender = undefined;
          }

          const newMsg: ReceivedChatMessage = {
            id,
            timestamp: ts,
            message: decoded,
            from: sender ?? room.localParticipant,
          };

          addDataMessage(newMsg);
        }
      } catch (e) {
        /* ignore */
      }
    };

    // Try room-level event (SDKs expose varied event names across versions)
    if (typeof r.on === 'function') {
      try {
        r.on('dataReceived', rawHandler);
        r.on('data', rawHandler);
      } catch (e) {
        // ignore if events not supported
      }
    }

    // Attach to existing remote participants as well
    try {
      for (const p of Array.from(room.remoteParticipants.values())) {
        if (typeof p.on === 'function') {
          try {
            p.on('dataReceived', (payload: any) => rawHandler(payload, p));
            p.on('data', (payload: any) => rawHandler(payload, p));
          } catch (e) {
            /* ignore */
          }
        }
      }
    } catch (e) {
      /* ignore */
    }

    // Listen for future participants connecting so we can attach their data listeners
    const onParticipantConnected = (p: any) => {
      try {
        if (typeof p.on === 'function') {
          p.on('dataReceived', (payload: any) => rawHandler(payload, p));
          p.on('data', (payload: any) => rawHandler(payload, p));
        }
      } catch (e) {
        /* ignore */
      }
    };

    try {
      if (typeof r.on === 'function') r.on('participantConnected', onParticipantConnected);
    } catch (e) {
      /* ignore */
    }

    return () => {
      try {
        if (typeof r.off === 'function') {
          r.off('dataReceived', rawHandler);
          r.off('data', rawHandler);
          r.off('participantConnected', onParticipantConnected);
        }
      } catch (e) {
        /* ignore */
      }
    };
  }, [room]);

  // Listen for local typed-chat fallbacks so we can show the user's message
  // immediately in the transcript even if useChat.send or data publishing
  // takes a different path on various SDK versions.
  useEffect(() => {
    if (typeof window === 'undefined') return undefined;
    const handler = (ev: any) => {
      try {
        const msg = ev?.detail?.message ?? ev?.detail ?? ev;
        if (!msg || typeof msg !== 'string') return;
        // eslint-disable-next-line no-console
        console.info('[useChatMessages] local-chat-message received:', msg);
        const id = `local-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
        const ts = Date.now();
        const newMsg = {
          id,
          timestamp: ts,
          message: msg,
          from: room?.localParticipant,
        } as ReceivedChatMessage;
        addDataMessage(newMsg);
      } catch (e) {
        /* ignore */
      }
    };

    window.addEventListener('local-chat-message', handler as EventListener);
    return () => {
      try {
        window.removeEventListener('local-chat-message', handler as EventListener);
      } catch (e) {
        /* ignore */
      }
    };
  }, [room, addDataMessage]);

  return mergedTranscriptions;
}
