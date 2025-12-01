"use client";

import React, { useEffect } from 'react';
import { type ReceivedChatMessage } from '@livekit/components-react';
import { ChatEntry } from '@/components/livekit/chat-entry';

interface ChatTranscriptProps {
  hidden?: boolean;
  messages?: ReceivedChatMessage[];
}

export function ChatTranscript({
  hidden = false,
  messages = [],
  ...props
}: ChatTranscriptProps & React.HTMLAttributes<HTMLDivElement>) {
  if (hidden) return null;
  useEffect(() => {
    try {
      // eslint-disable-next-line no-console
      console.info('[ChatTranscript] messages prop', messages);
    } catch (e) {
      /* ignore */
    }
  }, [messages]);

  return (
    <div {...props} style={{ color: 'white' }}>
      {messages.map(({ id, timestamp, from, message, editTimestamp }: ReceivedChatMessage) => {
        const locale = navigator?.language ?? 'en-US';
        const messageOrigin = from?.isLocal ? 'local' : 'remote';
        const hasBeenEdited = !!editTimestamp;

        // derive a friendly sender name when possible
        let senderName: string | undefined = undefined;
        try {
          const identity = from?.identity as string | undefined;
          if (identity) {
            if (identity.toLowerCase().startsWith('agent') || identity.toLowerCase().includes('agent')) {
              senderName = 'Alexa';
            } else if (identity.toLowerCase().includes('assistant')) {
              senderName = 'Alexa';
            } else {
              // show a short, readable identity for remote participants
              senderName = identity.split(/[\-@_\.]/)[0];
            }
          } else if (!from?.isLocal && messageOrigin === 'remote') {
            senderName = 'Alexa';
          }
        } catch (e) {
          senderName = undefined;
        }

        return (
          <ChatEntry
            key={id}
            name={senderName}
            locale={locale}
            timestamp={timestamp}
            message={message}
            messageOrigin={messageOrigin}
            hasBeenEdited={hasBeenEdited}
            style={{ color: 'white' }}
          />
        );
      })}
    </div>
  );
}
