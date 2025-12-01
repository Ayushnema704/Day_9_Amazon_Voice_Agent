import * as React from 'react';
import { cn } from '@/lib/utils';

export interface ChatEntryProps extends React.HTMLAttributes<HTMLLIElement> {
  /** The locale to use for the timestamp. */
  locale: string;
  /** The timestamp of the message. */
  timestamp: number;
  /** The message to display. */
  message: string;
  /** The origin of the message. */
  messageOrigin: 'local' | 'remote';
  /** The sender's name. */
  name?: string;
  /** Whether the message has been edited. */
  hasBeenEdited?: boolean;
}

export const ChatEntry = ({
  name,
  locale,
  timestamp,
  message,
  messageOrigin,
  hasBeenEdited = false,
  className,
  ...props
}: ChatEntryProps) => {
  const time = new Date(timestamp);
  const title = time.toLocaleTimeString(locale, { timeStyle: 'full' });

  return (
    <li
      title={title}
      data-lk-message-origin={messageOrigin}
      className={cn('group flex w-full flex-col gap-2 my-3', className)}
      {...props}
    >
      <header
        className={cn(
          'flex items-center gap-2 text-sm',
          messageOrigin === 'local' ? 'flex-row-reverse' : 'text-left'
        )}
        style={{ color: 'rgba(255, 255, 255, 0.7)' }}
      >
        {name && <strong style={{ color: 'white' }}>{name}</strong>}
        <span className="font-mono text-xs opacity-0 transition-opacity ease-linear group-hover:opacity-100">
          {hasBeenEdited && '*'}
          {time.toLocaleTimeString(locale, { timeStyle: 'short' })}
        </span>
      </header>
      <div
        className={messageOrigin === 'local' ? 'ml-auto' : 'mr-auto'}
        style={{
          maxWidth: '80%',
          borderRadius: '18px',
          padding: '14px 18px',
          wordBreak: 'break-word',
          color: '#FFFFFF',
          backgroundColor: messageOrigin === 'local' ? '#FF9900' : 'rgba(22,29,40,0.98)',
          fontSize: '16px',
          lineHeight: '1.6',
          display: 'block',
          opacity: 1,
          visibility: 'visible',
          zIndex: 1000,
          boxShadow: messageOrigin === 'local' ? '0 6px 18px rgba(255,153,0,0.15)' : 'none',
        }}
        aria-live={messageOrigin === 'remote' ? 'polite' : undefined}
      >
        <span style={{ color: '#FFFFFF' }}>{message}</span>
      </div>
    </li>
  );
};
