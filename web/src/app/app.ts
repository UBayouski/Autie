import { Component } from '@angular/core';

import { ChatPageComponent } from './chat/chat-page';

@Component({
  selector: 'app-root',
  imports: [ChatPageComponent],
  template: '<app-chat-page />',
})
export class App {}
