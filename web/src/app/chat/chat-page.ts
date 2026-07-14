import {
  Component,
  ElementRef,
  effect,
  inject,
  viewChild,
} from '@angular/core';

import { ChatService } from '../core/chat.service';
import { ComposerComponent } from './composer';
import { MessageBubbleComponent } from './message-bubble';

@Component({
  selector: 'app-chat-page',
  imports: [MessageBubbleComponent, ComposerComponent],
  templateUrl: './chat-page.html',
  styleUrl: './chat-page.css',
})
export class ChatPageComponent {
  protected readonly chat = inject(ChatService);

  private readonly scroller = viewChild.required<ElementRef<HTMLElement>>('scroller');

  constructor() {
    // Keep the newest message in view while tokens stream in.
    effect(() => {
      this.chat.messages();
      queueMicrotask(() => {
        const el = this.scroller().nativeElement;
        el.scrollTop = el.scrollHeight;
      });
    });
  }
}
