import { Injectable, inject, signal } from '@angular/core';

import { AuthService } from './auth.service';

export interface CrisisResource {
  name: string;
  contact: string;
  note: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  error?: boolean;
  crisis?: { message: string; resources: CrisisResource[] };
}

type StreamEvent =
  | { type: 'session'; session_id: string }
  | { type: 'crisis_resources'; message: string; resources: CrisisResource[] }
  | { type: 'text_delta'; text: string }
  | { type: 'text_final'; text: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

/**
 * Streams chat turns over SSE from POST /api/chat (same-origin: dev-server
 * proxy locally, Firebase Hosting rewrite in production).
 */
const SESSION_STORAGE_KEY = 'autie-session-id';

@Injectable({ providedIn: 'root' })
export class ChatService {
  private readonly auth = inject(AuthService);

  readonly messages = signal<ChatMessage[]>([]);
  readonly busy = signal(false);

  private sessionId: string | null = null;

  constructor() {
    const saved = localStorage.getItem(SESSION_STORAGE_KEY);
    if (saved) {
      void this.restore(saved);
    }
  }

  /** Reloads a previous conversation so a page refresh doesn't lose it. */
  private async restore(sessionId: string): Promise<void> {
    this.busy.set(true);
    try {
      const token = await this.auth.idToken();
      const response = await fetch(`/api/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        localStorage.removeItem(SESSION_STORAGE_KEY);
        return;
      }
      const history = (await response.json()) as { messages: ChatMessage[] };
      this.sessionId = sessionId;
      this.messages.set(history.messages);
    } catch {
      // Network hiccup: leave the saved id for the next load.
    } finally {
      this.busy.set(false);
    }
  }

  newConversation(): void {
    this.sessionId = null;
    localStorage.removeItem(SESSION_STORAGE_KEY);
    this.messages.set([]);
  }

  async send(text: string): Promise<void> {
    const trimmed = text.trim();
    if (!trimmed || this.busy()) {
      return;
    }
    this.busy.set(true);
    this.lastSegmentDone = false;
    this.messages.update((m) => [
      ...m,
      { role: 'user', text: trimmed },
      { role: 'assistant', text: '' },
    ]);

    try {
      const token = await this.auth.idToken();
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ message: trimmed, session_id: this.sessionId }),
      });
      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }
      await this.consumeStream(response.body);
    } catch {
      this.setLast('Sorry, something went wrong. Please try again.', true);
    } finally {
      this.busy.set(false);
    }
  }

  private async consumeStream(body: ReadableStream<Uint8Array>): Promise<void> {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        for (const line of rawEvent.split('\n')) {
          if (line.startsWith('data: ')) {
            this.handleEvent(JSON.parse(line.slice(6)) as StreamEvent);
          }
        }
      }
    }
  }

  /** True when the last assistant bubble holds a completed (final) segment. */
  private lastSegmentDone = false;

  private handleEvent(event: StreamEvent): void {
    switch (event.type) {
      case 'session':
        this.sessionId = event.session_id;
        localStorage.setItem(SESSION_STORAGE_KEY, event.session_id);
        break;
      case 'crisis_resources':
        // Insert the resources card before the streaming assistant bubble.
        this.messages.update((m) => [
          ...m.slice(0, -1),
          {
            role: 'assistant',
            text: '',
            crisis: { message: event.message, resources: event.resources },
          },
          m[m.length - 1],
        ]);
        break;
      case 'text_delta':
        if (this.lastSegmentDone) {
          // New segment after a completed one (e.g. text -> tool call -> text):
          // start a fresh bubble instead of touching the finished one.
          this.messages.update((m) => [...m, { role: 'assistant', text: '' }]);
          this.lastSegmentDone = false;
        }
        this.appendToLast(event.text);
        break;
      case 'text_final':
        if (this.lastSegmentDone) {
          // Final with no preceding deltas (e.g. the sources footer): its own bubble.
          this.messages.update((m) => [
            ...m,
            { role: 'assistant', text: event.text },
          ]);
        } else {
          // Authoritative full text for the CURRENT segment only.
          this.setLast(event.text);
        }
        this.lastSegmentDone = true;
        break;
      case 'error':
        this.setLast(event.message, true);
        break;
      case 'done':
        break;
    }
  }

  private appendToLast(text: string): void {
    this.messages.update((m) => {
      const last = m[m.length - 1];
      return [...m.slice(0, -1), { ...last, text: last.text + text }];
    });
  }

  private setLast(text: string, error = false): void {
    this.messages.update((m) => [
      ...m.slice(0, -1),
      { role: 'assistant', text, error },
    ]);
  }
}
