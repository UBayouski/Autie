import { Component, input } from '@angular/core';

import { ChatMessage } from '../core/chat.service';
import { MarkdownPipe } from './markdown.pipe';

@Component({
  selector: 'app-message-bubble',
  imports: [MarkdownPipe],
  templateUrl: './message-bubble.html',
  styleUrl: './message-bubble.css',
})
export class MessageBubbleComponent {
  readonly message = input.required<ChatMessage>();
}
